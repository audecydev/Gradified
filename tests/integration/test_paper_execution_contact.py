"""criterion scoring internal contact barrier; authenticated issuer and runtime are fixture, NOT production proof."""
from dataclasses import replace
import pytest

from grading.integration.paper_execution_contact import (
    CurrentQuestionContactFact, ProductionPaperQuestionContact,
    PaperContactDenied, PaperContactUnavailable, PaperContactContractError,
)
from grading.integration.paper_execution_correlation import (
    IssuedPaperExecutionRelation, IssuedQuestionExecutionRelation,
    ProductionPaperExecutionCorrelation,
)
from grading.integration.paper_readiness_admission import (
    PaperAdmissionRequest, AdmittedPaperPlan, AdmittedPaperQuestion,
)
from grading.integration.evaluator_execution_binding import ProductionExecutionHandoff
from grading.integration.grading_orchestration import ProductionGradingEntry
from grading.integration.trusted_preparation import PreparationRequest
from tests.integration.test_execution_eligibility_runtime import assemble
from tests.integration.test_authorized_preparation import _compose


class PaperIssuer:
    def __init__(self, relation):
        self.relation = relation
        self.calls = 0
        self.action = None

    def correlate_paper_execution(self, *, plan):
        self.calls += 1
        if self.action:
            self.action(plan)
        return self.relation


class FreshIssuer:
    def __init__(self, expected):
        self.expected = expected
        self.calls = 0
        self.action = None
        self.response = None

    def confirm_current_question_contact(self, *, correlation, question, scope):
        self.calls += 1
        if self.action:
            self.action(correlation, question, scope)
        if self.response is not None:
            return self.response
        p = correlation.plan
        return CurrentQuestionContactFact(1, p.request, p.actor_ref,
            correlation.issuer_relation.issuance_ref, question, scope, p.approval_ref,
            p.approval_revision, p.selection_decision_ref, p.selection_revision,
            p.source_revision, p.readiness_revision, 'CONFIRM', 'CURRENT_AUTHORIZED')


def rig():
    request, prep_ports, choices, admitted, ports, eligibility, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=eligibility, runtime=binder)
    scope = admitted.scope
    preq = PaperAdmissionRequest(scope.tenant_ref, scope.session_ref,
        scope.grading_run_id, scope.submission_ref, scope.exam_ref,
        'PAPER-1', 'SET-1', scope.grading_spec_ref)
    question = AdmittedPaperQuestion(request, 'CHOICE', scope.source_artifact_ref,
        scope.source_revision, scope.evidence_scope_ref, 'REGION-1', scope.ocr_provenance)
    plan = AdmittedPaperPlan(preq, scope.actor_ref, 'APP', 'APP-REV',
        'SELECTION', 'SEL-REV', scope.source_revision, 'READ-REV', (question,))
    issued_question = IssuedQuestionExecutionRelation(scope.question_id, 'CHOICE',
        scope.source_artifact_ref, scope.evidence_scope_ref, 'REGION-1',
        scope.source_revision, scope.ocr_provenance, 'RUBRIC', 'SCORE-POLICY')
    issued = IssuedPaperExecutionRelation(1, preq, scope.actor_ref, 'SCHOOL-ISSUER',
        'ISSUANCE', preq.paper_ref, preq.set_ref, plan.approval_ref,
        plan.approval_revision, plan.selection_decision_ref, plan.selection_revision,
        plan.source_revision, plan.readiness_revision, (issued_question,))
    paper_issuer = PaperIssuer(issued)
    fresh = FreshIssuer(issued_question)
    correlation = ProductionPaperExecutionCorrelation(
        issuer=paper_issuer, max_questions=10, max_identifier_characters=128)
    root = ProductionPaperQuestionContact(
        correlation=correlation, handoff=handoff, issuer=fresh,
        max_questions=10, max_identifier_characters=128)
    return root, plan, paper_issuer, fresh, ports, prep_ports, issued


def test_real_installed_choice_runtime_preflight_is_nonexecuting():
    root, plan, paper, fresh, runtime, prep, _ = rig()
    out = root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert out.state == 'PREFLIGHT_ONLY'
    assert out.paper_issuance_ref == 'ISSUANCE'
    assert (paper.calls, fresh.calls) == (1, 1)
    assert runtime.events == ['selection', 'facts', 'policy', 'runtime']
    assert out.runtime_id == 'choice-native'
    assert not hasattr(out, 'attempt_id') and not hasattr(out, 'execute')


@pytest.mark.parametrize('field,value', [
    ('question_id','FOREIGN'), ('question_id',''), ('question_id',object()),
    ('question_id','LONG'*40),
])
def test_unselected_question_fails_before_any_callback(field, value):
    root, plan, paper, fresh, runtime, _, _ = rig()
    with pytest.raises((PaperContactDenied, PaperContactContractError)):
        root.preflight_choice(plan=plan, question_id=value)
    assert paper.calls == 0 and fresh.calls == 0 and runtime.events == []


def test_invalid_plan_fails_before_paper_issuer():
    root, _, paper, fresh, runtime, _, _ = rig()
    with pytest.raises(PaperContactContractError):
        root.preflight_choice(plan=object(), question_id='Q')
    assert paper.calls == 0 and fresh.calls == 0 and runtime.events == []


def test_foreign_paper_answer_region_disallows_runtime_contact():
    root, plan, paper, fresh, runtime, _, issued = rig()
    paper.relation = replace(issued, questions=(replace(issued.questions[0], answer_region_ref='FOREIGN'),))
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert paper.calls == 1 and fresh.calls == 0 and runtime.events == []


def test_changed_plan_during_paper_callback_stops_before_runtime():
    root, plan, paper, fresh, runtime, _, _ = rig()
    paper.action = lambda _: object.__setattr__(plan, 'selection_revision', 'REVOKED')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 0 and runtime.events == []


@pytest.mark.parametrize('field,value', [
    ('state','REVOKED'), ('actor_ref','FOREIGN'), ('paper_issuance_ref','FOREIGN'),
    ('approval_revision','STALE'), ('source_revision','STALE'),
    ('readiness_revision','STALE'), ('selection_revision','STALE'),
    ('confirmation_ref',object()), ('version',True),
])
def test_fresh_confirmation_mismatch_or_invalid_contract_denied(field,value):
    root, plan, paper, fresh, runtime, _, issued = rig()
    question = issued.questions[0]
    from grading.integration.choice_authority_admission import ChoiceAdmissionScope
    # Real scope is obtained from installed eligibility fixtures; build a test
    # copy solely to exercise later school-issuer contract validations.
    request, _, _, admitted, _, _, _ = assemble()
    scope = admitted.scope
    fact = CurrentQuestionContactFact(1, plan.request, plan.actor_ref, issued.issuance_ref,
        question, scope, plan.approval_ref, plan.approval_revision,
        plan.selection_decision_ref, plan.selection_revision, plan.source_revision,
        plan.readiness_revision, 'CONFIRM', 'CURRENT_AUTHORIZED')
    fresh.response = replace(fact, **{field: value})
    with pytest.raises((PaperContactDenied, PaperContactContractError)):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1 and runtime.events == ['selection','facts','policy','runtime']


def test_current_issuer_mutates_paper_while_returning_valid_fact():
    root, plan, paper, fresh, runtime, _, _ = rig()
    fresh.action = lambda *_: object.__setattr__(plan, 'approval_revision', 'REVOKED')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1


def test_current_issuer_mutates_its_own_scope_before_return():
    root, plan, paper, fresh, runtime, _, _ = rig()
    fresh.action = lambda c,q,scope: object.__setattr__(scope, 'source_revision', 'REVOKED')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1


def test_issuer_outage_sanitizes_private_context():
    root, plan, paper, fresh, runtime, _, _ = rig()
    fresh.action=lambda *_: (_ for _ in ()).throw(RuntimeError('PRIVATE_TOKEN'))
    with pytest.raises(PaperContactUnavailable) as captured:
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    exc = captured.value
    assert exc.__cause__ is None and exc.__context__ is None
    assert 'PRIVATE' not in str(exc)


def test_direct_declared_question_is_not_silently_invoked():
    root, plan, paper, fresh, runtime, _, issued = rig()
    q = replace(plan.questions[0], family='DIRECT')
    plan = replace(plan, questions=(q,))
    paper.relation = replace(issued, questions=(replace(issued.questions[0], family='DIRECT'),))
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=q.request.question_id)
    assert fresh.calls == 0 and runtime.events == []


def test_reentrancy_denied_before_fresh_reentry():
    root, plan, paper, fresh, runtime, _, _ = rig()
    nested=[]
    def reenter(*args):
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        nested.append('blocked')
    fresh.action = reenter
    out = root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert out.state == 'PREFLIGHT_ONLY' and nested == ['blocked']
    assert paper.calls == 1 and fresh.calls == 1


def test_installed_issuer_cannot_be_replaced_by_normal_assignment():
    root, *_ = rig()
    with pytest.raises(PaperContactContractError):
        root._installation = object()
    with pytest.raises(PaperContactContractError):
        root.__class__ = object


def test_authoritative_question_region_bound_before_current_issuer():
    root, plan, paper, fresh, runtime, _, issued = rig()
    replaced = replace(plan.questions[0], answer_region_ref='NEW-REGION')
    changed = replace(plan, questions=(replaced,))
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=changed, question_id=replaced.request.question_id)
    assert fresh.calls == 0 and runtime.events == []


def test_current_issuer_returns_wrong_region_no_nonbearer_candidate():
    root, plan, paper, fresh, runtime, _, issued = rig()
    request, _, _, admitted, _, _, _ = assemble()
    q = replace(issued.questions[0], answer_region_ref='OTHER-REGION')
    fresh.response = CurrentQuestionContactFact(
        1, plan.request, plan.actor_ref, issued.issuance_ref, q, admitted.scope,
        plan.approval_ref, plan.approval_revision, plan.selection_decision_ref,
        plan.selection_revision, plan.source_revision, plan.readiness_revision,
        'C', 'CURRENT_AUTHORIZED')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1


def test_issuer_mutates_correlation_question_but_returns_apparent_success():
    root, plan, paper, fresh, runtime, _, _ = rig()
    fresh.action=lambda correlation, question, scope: object.__setattr__(
        correlation.issuer_relation.questions[0], 'rubric_ref', 'FOREIGN')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1


def test_issuer_mutates_original_question_but_returns_apparent_success():
    root, plan, paper, fresh, runtime, _, _ = rig()
    fresh.action=lambda *_: object.__setattr__(plan.questions[0], 'answer_region_ref', 'FOREIGN')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1


def test_issuer_method_getter_private_failure_has_no_context():
    root, plan, paper, fresh, runtime, _, _ = rig()
    class Invalid:
        @property
        def confirm_current_question_contact(self):
            raise RuntimeError('PRIVATE_INSTALLATION')
    with pytest.raises(PaperContactContractError) as exc:
        ProductionPaperQuestionContact(
            correlation=root._installation.correlation,
            handoff=root._installation.handoff, issuer=Invalid(),
            max_questions=10, max_identifier_characters=128)
    assert 'PRIVATE' not in str(exc.value)
    assert exc.value.__context__ is None


def test_precontact_cannot_reuse_mutated_plan_on_next_call():
    root, plan, paper, fresh, runtime, _, _ = rig()
    assert root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id).state == 'PREFLIGHT_ONLY'
    paper.action=lambda _: object.__setattr__(plan, 'readiness_revision', 'STALE')
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert fresh.calls == 1


def test_consistent_foreign_paper_evidence_scope_still_blocked_by_real_pre_scope():
    root, plan, paper, fresh, runtime, _, issued = rig()
    forged = replace(plan.questions[0], evidence_scope_ref='FOREIGN-SCOPE')
    forged_issued = replace(issued.questions[0], evidence_scope_ref='FOREIGN-SCOPE')
    plan = replace(plan, questions=(forged,))
    paper.relation = replace(issued, questions=(forged_issued,))
    with pytest.raises(PaperContactDenied):
        root.preflight_choice(plan=plan, question_id=forged.request.question_id)
    # numeric scoring profile matching IDs alone may allow the fabricated source, but fresh CHOICE
    # scope from installed PRE/CHOICE must stop it BEFORE the next school port.
    assert paper.calls == 1 and fresh.calls == 0
    assert runtime.events == ['selection','facts','policy','runtime']

# Independent reviewers' confirmed failures: permanent behavioral regressions.
# The obsolete root._installation.thread_state attribute is deliberately not
# retained: a callback must not be handed a writable security decision flag.
@pytest.mark.parametrize('at', ['paper', 'fresh'])
def test_issuer_cannot_clear_inflight_state_or_make_nested_contact(at):
    root, plan, paper, fresh, runtime, _, _ = rig()
    qid = plan.questions[0].request.question_id
    observed = []
    def callback(*args):
        # A legacy writable busy marker must not be present in the installed
        # contact configuration; even if it were, clearing it cannot bypass.
        legacy = getattr(root._installation, 'thread_state', None)
        if legacy is not None:
            legacy.busy = False
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=qid)
        observed.append('denied')
    if at == 'paper':
        paper.action = callback
    else:
        fresh.action = callback
    assert root.preflight_choice(plan=plan, question_id=qid).state == 'PREFLIGHT_ONLY'
    assert observed == ['denied']
    assert (paper.calls, fresh.calls) == (1, 1)
    assert runtime.events == ['selection','facts','policy','runtime']


def test_handoff_compatible_subclass_rejected_before_paper_issuer():
    root, plan, paper, fresh, runtime, _, _ = rig()
    handoff = root._installation.handoff
    class Swapped(ProductionExecutionHandoff):
        __slots__ = ()
        def _require_root(self):
            return None
        def prepare_choice_runtime(self, *, request):
            raise AssertionError('substituted method must never execute')
    handoff.__class__ = Swapped
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        assert (paper.calls, fresh.calls) == (0,0)
        assert runtime.events == []
    finally:
        handoff.__class__ = ProductionExecutionHandoff


@pytest.mark.parametrize('at', ['paper','fresh'])
def test_handoff_class_swap_during_authority_callback_denies(at):
    root, plan, paper, fresh, runtime, _, _ = rig()
    handoff = root._installation.handoff
    qid = plan.questions[0].request.question_id
    class Swapped(ProductionExecutionHandoff):
        __slots__ = ()
        def _require_root(self):
            return None
        def prepare_choice_runtime(self, *, request):
            raise AssertionError('substituted method must never execute')
    if at == 'paper':
        paper.action = lambda *_: setattr(handoff,'__class__',Swapped)
    else:
        fresh.action = lambda *_: setattr(handoff,'__class__',Swapped)
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=qid)
        if at == 'paper':
            assert fresh.calls == 0 and runtime.events == []
        else:
            assert fresh.calls == 1
    finally:
        handoff.__class__ = ProductionExecutionHandoff


def test_contact_guard_resets_after_issuer_exception():
    root, plan, paper, fresh, runtime, _, _ = rig()
    qid = plan.questions[0].request.question_id
    fresh.action = lambda *_: (_ for _ in ()).throw(RuntimeError('private-data'))
    with pytest.raises(PaperContactUnavailable):
        root.preflight_choice(plan=plan, question_id=qid)
    fresh.action = None
    assert root.preflight_choice(plan=plan, question_id=qid).state == 'PREFLIGHT_ONLY'
    assert (paper.calls, fresh.calls) == (2,2)


def test_contact_guard_allows_independent_threads_without_shared_busy_lock():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    root, plan, paper, fresh, runtime, _, _ = rig()
    qid = plan.questions[0].request.question_id
    barrier = Barrier(2, timeout=4)
    fresh.action = lambda *_: barrier.wait()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(root.preflight_choice, plan=plan, question_id=qid)
        b = pool.submit(root.preflight_choice, plan=plan, question_id=qid)
        assert a.result(timeout=8).state == 'PREFLIGHT_ONLY'
        assert b.result(timeout=8).state == 'PREFLIGHT_ONLY'
    assert (paper.calls, fresh.calls) == (2,2)

@pytest.mark.parametrize('at', ['paper', 'fresh'])
def test_handoff_change_and_callback_failure_preserves_corruption_denial(at):
    root, plan, paper, fresh, runtime, _, _ = rig()
    handoff = root._installation.handoff
    qid = plan.questions[0].request.question_id
    class Swapped(ProductionExecutionHandoff):
        __slots__ = ()
        def _require_root(self):
            return None
        def prepare_choice_runtime(self, *, request):
            raise AssertionError('hijacked')
    def fail(*_):
        handoff.__class__ = Swapped
        raise RuntimeError('PRIVATE_CALLBACK_PAYLOAD')
    if at == 'paper': paper.action = fail
    else: fresh.action = fail
    try:
        with pytest.raises(PaperContactDenied) as exc:
            root.preflight_choice(plan=plan, question_id=qid)
        assert exc.value.__context__ is None and exc.value.__cause__ is None
        assert 'PRIVATE' not in str(exc.value)
        if at == 'paper':
            assert fresh.calls == 0 and runtime.events == []
        else: assert fresh.calls == 1
    finally:
        handoff.__class__ = ProductionExecutionHandoff


# paper execution contact source-review closure: ContextVar contexts are not synchronous call
# stacks. A callback may start a fresh Context without returning to its caller.
@pytest.mark.parametrize('stage', ['paper', 'current_question'])
def test_same_root_fresh_python_context_cannot_contact_issuer_twice(stage):
    from contextvars import Context
    root, plan, paper, fresh, runtime, *_ = rig()
    question_id = plan.questions[0].request.question_id
    checked = []

    def nested(*_):
        with pytest.raises(PaperContactDenied):
            Context().run(root.preflight_choice, plan=plan, question_id=question_id)
        checked.append('denied')

    if stage == 'paper':
        paper.action = nested
    else:
        fresh.action = nested
    assert root.preflight_choice(plan=plan, question_id=question_id).state == 'PREFLIGHT_ONLY'
    assert checked == ['denied']
    assert (paper.calls, fresh.calls) == (1, 1)
    assert runtime.events == ['selection', 'facts', 'policy', 'runtime']


def test_same_thread_guard_released_after_private_issuer_exception():
    root, plan, paper, fresh, *_ = rig()
    question_id = plan.questions[0].request.question_id

    def secret_failure(*_):
        raise RuntimeError('secret callback payload')

    fresh.action = secret_failure
    with pytest.raises(PaperContactUnavailable) as caught:
        root.preflight_choice(plan=plan, question_id=question_id)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    fresh.action = None
    assert root.preflight_choice(plan=plan, question_id=question_id).state == 'PREFLIGHT_ONLY'
    assert (paper.calls, fresh.calls) == (2, 2)


# Independently reproduced 2026-10-16: a callback could call the module's
# unqualified leave(previous_set) helper to clear an in-progress root guard.
@pytest.mark.parametrize('stage', ['paper', 'current_question'])
@pytest.mark.parametrize('fresh_context', [False, True])
def test_issuer_cannot_reset_guard_without_current_invocation_lease(stage, fresh_context):
    from contextvars import Context
    from grading.integration import paper_execution_contact as contact

    root, plan, paper, fresh, runtime, *_ = rig()
    question_id = plan.questions[0].request.question_id
    rejected = []

    def callback(*_):
        with pytest.raises(PaperContactDenied):
            contact._leave_thread_preflight(frozenset())
        # Do not recurse via the callback itself: test the guard at the
        # actual authority-contact boundary, not an infinite recursion.
        if stage == 'paper':
            paper.action = None
        else:
            fresh.action = None
        with pytest.raises(PaperContactDenied):
            if fresh_context:
                Context().run(root.preflight_choice, plan=plan, question_id=question_id)
            else:
                root.preflight_choice(plan=plan, question_id=question_id)
        rejected.append(True)

    if stage == 'paper':
        paper.action = callback
    else:
        fresh.action = callback
    assert root.preflight_choice(plan=plan, question_id=question_id).state == 'PREFLIGHT_ONLY'
    assert rejected == [True]
    assert (paper.calls, fresh.calls) == (1, 1)
    assert runtime.events == ['selection', 'facts', 'policy', 'runtime']
    # The acquired lease was released by its real owner, allowing later calls.
    assert root.preflight_choice(plan=plan, question_id=question_id).state == 'PREFLIGHT_ONLY'
    assert (paper.calls, fresh.calls) == (2, 2)


# Independent criterion scoring review: outer handoff continuity cannot attest replaced
# nested PRE/CHOICE/approved eligibility and execution policy dispatchers or cached admission records.
from grading.integration.evaluator_execution_binding import ProductionEvaluatorRuntimeBinder

@pytest.mark.parametrize('stage', ['before', 'during_paper_issuer'])
def test_b2_dispatch_substituted_binder_must_not_return_replayed_runtime(stage):
    root, plan, paper, fresh, runtime, _, _ = rig()
    handoff = root._installation.handoff
    binder = handoff._installation.runtime
    qid = plan.questions[0].request.question_id
    cached = handoff.prepare_choice_runtime(request=plan.questions[0].request)
    runtime.events.clear()
    class ForgedRuntime(ProductionEvaluatorRuntimeBinder):
        __slots__ = ()
        def _require_installed_eligibility(self):
            return None
        def bind_choice(self, *, admitted):
            return cached
    if stage == 'before':
        binder.__class__ = ForgedRuntime
    else:
        paper.action = lambda *_: setattr(binder,'__class__', ForgedRuntime)
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=qid)
        assert fresh.calls == 0
        assert runtime.events == []
    finally:
        binder.__class__ = ProductionEvaluatorRuntimeBinder

@pytest.mark.parametrize('stage', ['before', 'during_paper_issuer'])
def test_b2_dispatch_shadowed_entry_must_not_replay_pre_choice_admission(stage):
    root, plan, paper, fresh, runtime, _, _ = rig()
    entry = root._installation.handoff._installation.entry
    request = plan.questions[0].request
    cached = entry.prepare_choice(request=request)
    runtime.events.clear()
    shadow_calls = []
    def fake(*, request):
        shadow_calls.append(request.question_id)
        return cached
    if stage == 'before':
        entry.prepare_choice = fake
    else:
        paper.action = lambda *_: setattr(entry, 'prepare_choice', fake)
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=request.question_id)
        assert fresh.calls == 0
        assert shadow_calls == []
    finally:
        if 'prepare_choice' in entry.__dict__:
            del entry.prepare_choice

def test_b2_dispatch_legitimate_live_runtime_and_real_admission_control():
    root, plan, paper, fresh, runtime, _, _ = rig()
    out = root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    assert out.state == 'PREFLIGHT_ONLY'
    assert runtime.events == ['selection','facts','policy','runtime']
    assert (paper.calls,fresh.calls) == (1,1)

def test_b2_dispatch_nested_contact_guard_without_tampering_remains_active():
    root, plan, paper, fresh, runtime, _, _ = rig()
    qid = plan.questions[0].request.question_id
    seen=[]
    def reenter(*_):
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=qid)
        seen.append(1)
    paper.action = reenter
    assert root.preflight_choice(plan=plan,question_id=qid).state == 'PREFLIGHT_ONLY'
    assert seen==[1] and (paper.calls, fresh.calls)==(1,1)

@pytest.mark.parametrize('stage', ['before', 'during_paper_issuer'])
def test_b2_dispatch_swapped_entry_delegates_must_not_replay_admitted_choice(stage):
    root, plan, paper, fresh, runtime, _, _ = rig()
    entry = root._installation.handoff._installation.entry
    request = plan.questions[0].request
    original_choices, original_prep = entry._choices, entry._preparation
    admitted = entry.prepare_choice(request=request)
    pregrant = original_choices.preauthorize(request=request)
    runtime.events.clear()
    class FakeChoices:
        def preauthorize(self, *, request): return pregrant
        def admit(self, *, prepared, pre_evidence_grant): return admitted
    class FakePrep:
        def prepare(self, *, request): return object()
    def swap(*_):
        entry._choices = FakeChoices()
        entry._preparation = FakePrep()
    if stage == 'before': swap()
    else: paper.action = swap
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=request.question_id)
        assert fresh.calls == 0
    finally:
        entry._choices, entry._preparation = original_choices, original_prep


@pytest.mark.parametrize('stage', ['before', 'during_paper_issuer'])
@pytest.mark.parametrize('kind', ['choice_preauthorize', 'choice_admit', 'preparation_prepare'])
def test_b2_dispatch_instance_method_shadow_is_denied_before_current_issuer(stage, kind):
    root, plan, paper, fresh, runtime, *_ = rig()
    entry = root._installation.handoff._installation.entry
    qid = plan.questions[0].request.question_id
    obj, method = {
        'choice_preauthorize': (entry._choices, 'preauthorize'),
        'choice_admit': (entry._choices, 'admit'),
        'preparation_prepare': (entry._preparation, 'prepare'),
    }[kind]
    calls = []
    original = getattr(obj, method)

    def replay(*args, **kwargs):
        calls.append(method)
        return original(*args, **kwargs)

    if stage == 'before':
        setattr(obj, method, replay)
    else:
        paper.action = lambda *_: setattr(obj, method, replay)
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=qid)
        assert fresh.calls == 0
        assert calls == []
        assert runtime.events == []
    finally:
        if method in obj.__dict__:
            delattr(obj, method)


@pytest.mark.parametrize('component', ['preparation', 'choices'])
def test_b2_dispatch_nested_class_replacement_rejected(component):
    from grading.integration.authorized_preparation import ProductionPreparationComposer
    from grading.integration.choice_authority_admission import ProductionChoiceAdmissionComposer

    root, plan, paper, fresh, runtime, *_ = rig()
    entry = root._installation.handoff._installation.entry
    obj = getattr(entry, '_'+component)
    original_class = type(obj)
    base = ProductionPreparationComposer if component == 'preparation' else ProductionChoiceAdmissionComposer
    class Replaced(base):
        pass
    obj.__class__ = Replaced
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        assert (paper.calls, fresh.calls) == (0,0)
        assert runtime.events == []
    finally:
        obj.__class__ = original_class


@pytest.mark.parametrize('kind', ['entry_method', 'preparation_delegate', 'runtime_class'])
def test_b2_dispatch_changed_by_final_issuer_is_denied(kind):
    root, plan, paper, fresh, runtime, *_ = rig()
    handoff = root._installation.handoff
    entry = handoff._installation.entry
    binder = handoff._installation.runtime
    original_prep = entry._preparation
    original_runtime_class = type(binder)
    original_choice_method = entry.prepare_choice
    def mutate(*_):
        if kind == 'entry_method':
            entry.prepare_choice = lambda *, request: original_choice_method(request=request)
        elif kind == 'preparation_delegate':
            entry._preparation = object()
        else:
            class Replaced(type(binder)):
                __slots__ = ()
            binder.__class__ = Replaced
    fresh.action = mutate
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        assert (paper.calls,fresh.calls)==(1,1)
        assert runtime.events == ['selection','facts','policy','runtime']
    finally:
        if 'prepare_choice' in entry.__dict__: del entry.prepare_choice
        entry._preparation = original_prep
        binder.__class__ = original_runtime_class


# Independent reproductions, preserved as permanent criterion scoring regression cases.

def test_paper_callback_cannot_replace_pre_identity_operation():
    root, plan, paper, fresh, runtime, prep_ports, _ = rig()
    preparation = root._installation.installed_preparation
    original_op = preparation._operations['current_actor']
    captured_actor = prep_ports.actor
    baseline_events = tuple(prep_ports.events)
    def replace_identity(_plan):
        preparation._operations['current_actor'] = lambda: captured_actor
    paper.action = replace_identity
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan,question_id=plan.questions[0].request.question_id)
        assert tuple(prep_ports.events) == baseline_events
        assert fresh.calls == 0
    finally:
        preparation._operations['current_actor'] = original_op


def test_paper_callback_cannot_replace_choice_pregrant_operation():
    root, plan, paper, fresh, runtime, prep_ports, _ = rig()
    choices = root._installation.installed_choices
    original_op = choices._operations['authorize_choice_request']
    captured = original_op(request=plan.questions[0].request)
    def replace_preauth(_plan):
        choices._operations['authorize_choice_request'] = lambda *,request: captured
    paper.action = replace_preauth
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        assert fresh.calls == 0
    finally:
        choices._operations['authorize_choice_request'] = original_op


def test_valid_unmodified_preflight():
    root, plan, *_ = rig()
    result=root.preflight_choice(plan=plan,question_id=plan.questions[0].request.question_id)
    assert result.state=='PREFLIGHT_ONLY'

@pytest.mark.parametrize('owner,operation', [
    ('installed_preparation','current_actor'),
    ('installed_choices','authorize_choice_request'),
])
def test_current_question_callback_cannot_poison_next_call(owner, operation):
    root, plan, paper, fresh, runtime, prep_ports, _ = rig()
    composer = getattr(root._installation, owner)
    ops = composer._operations
    old = ops[operation]
    if operation == 'current_actor':
        fake = lambda: prep_ports.actor
    else:
        canned = old(request=plan.questions[0].request)
        fake = lambda *, request: canned
    def poison(*_):
        ops[operation] = fake
    fresh.action = poison
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
    finally:
        ops[operation] = old

@pytest.mark.parametrize('owner', ['installed_preparation', 'installed_choices'])
def test_paper_callback_cannot_replace_full_operation_mapping(owner):
    root, plan, paper, fresh, runtime, prep_ports, _ = rig()
    composer = getattr(root._installation, owner)
    original = composer._operations
    paper.action = lambda *_: setattr(composer, '_operations', dict(original))
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        assert fresh.calls == 0
    finally:
        composer._operations = original

@pytest.mark.parametrize('owner,field', [('installed_preparation','_maximum'),
                                         ('installed_choices','_limit')])
def test_paper_callback_cannot_relax_installed_pre_choice_resource_ceiling(owner,field):
    root, plan, paper, fresh, runtime, prep_ports, _ = rig()
    composer = getattr(root._installation,owner)
    previous = getattr(composer,field)
    paper.action=lambda *_: setattr(composer,field,previous+1)
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan,question_id=plan.questions[0].request.question_id)
        assert fresh.calls == 0
    finally:
        setattr(composer,field,previous)


def test_revoked_actor_is_not_replaced_by_a_cached_one():
    from dataclasses import replace
    root, plan, paper, fresh, runtime, prep_ports, _ = rig()
    prep_comp = root._installation.installed_preparation
    original_op = prep_comp._operations['current_actor']
    cached_actor = prep_ports.actor
    def revoke_and_spoof(*_):
        prep_ports.actor = replace(prep_ports.actor, tenant_ref='REVOKED-TENANT')
        prep_comp._operations['current_actor'] = lambda: cached_actor
    paper.action = revoke_and_spoof
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan,question_id=plan.questions[0].request.question_id)
        assert fresh.calls == 0
    finally:
        prep_comp._operations['current_actor']=original_op


# The installed PRE/CHOICE dispatch inventory is part of the verified authority
# chain; an unchanged composer class or method is insufficient protection.
@pytest.mark.parametrize('owner,name', [
    ('installed_preparation', 'current_actor'),
    ('installed_preparation', 'authorize_preparation'),
    ('installed_preparation', 'resolve_approved_policy'),
    ('installed_preparation', 'resolve_revisioned_preparation'),
    ('installed_preparation', 'open_authorized_evidence'),
    ('installed_choices', 'authorize_choice_request'),
    ('installed_choices', 'authorize_choice'),
    ('installed_choices', 'resolve_approved_choice_key'),
    ('installed_choices', 'resolve_verified_choice_selection'),
    ('installed_choices', 'confirm_choice_revisions'),
])
@pytest.mark.parametrize('boundary', ['paper', 'question'])
def test_b2_all_installed_authority_targets_pinned(owner, name, boundary):
    root, plan, paper, fresh, runtime, *_ = rig()
    composer = getattr(root._installation, owner)
    mapping = composer._operations
    installed = mapping[name]
    # A plain callable replacement must be denied whether invoked or not.
    replacement = lambda *args, **kwargs: installed(*args, **kwargs)
    if boundary == 'paper':
        paper.action = lambda *_: mapping.__setitem__(name, replacement)
    else:
        fresh.action = lambda *_: mapping.__setitem__(name, replacement)
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        if boundary == 'paper':
            assert fresh.calls == 0
            assert runtime.events == []
        else:
            assert (paper.calls, fresh.calls) == (1, 1)
    finally:
        mapping[name] = installed


@pytest.mark.parametrize('owner,field', [
    ('installed_preparation', '_maximum'),
    ('installed_choices', '_limit'),
    ('installed_choices', '_max_options'),
    ('installed_choices', '_max_criteria'),
])
@pytest.mark.parametrize('boundary', ['paper', 'question'])
def test_b2_all_installed_authority_limits_pinned(owner, field, boundary):
    root, plan, paper, fresh, runtime, *_ = rig()
    composer = getattr(root._installation, owner)
    installed = getattr(composer, field)
    action = lambda *_: setattr(composer, field, installed + 1)
    if boundary == 'paper':
        paper.action = action
    else:
        fresh.action = action
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        if boundary == 'paper':
            assert fresh.calls == 0
            assert runtime.events == []
        else:
            assert (paper.calls, fresh.calls) == (1, 1)
    finally:
        setattr(composer, field, installed)


@pytest.mark.parametrize('owner,field', [
    ('installed_preparation', '_maximum'),
    ('installed_choices', '_limit'),
])
def test_b2_foreign_equal_limit_never_runs_comparison(owner, field):
    root, plan, paper, fresh, runtime, *_ = rig()
    composer = getattr(root._installation, owner)
    installed = getattr(composer, field)
    class ForeignEqual:
        def __eq__(self, _other):
            raise AssertionError('foreign equality must not run')
    paper.action = lambda *_: setattr(composer, field, ForeignEqual())
    try:
        with pytest.raises(PaperContactDenied):
            root.preflight_choice(plan=plan, question_id=plan.questions[0].request.question_id)
        assert fresh.calls == 0
        assert runtime.events == []
    finally:
        setattr(composer, field, installed)
