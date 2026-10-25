"""Adversarial regressions for independent effectful paper-execution failure paths."""
import pytest
from tests.integration.test_whole_paper_choice_execution import _setup_two
from grading.integration.whole_paper_choice_execution import PaperExecutionDenied


def test_regular_nested_execute_denied_before_attempts():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    nested=[]; fired=[False]
    def action(*args):
        if not fired[0]:
            fired[0]=True
            try: nested.append(root.execute(plan=plan))
            except PaperExecutionDenied: nested.append('blocked')
    issuer.action=action
    outcome=root.execute(plan=plan)
    assert nested==['blocked']
    assert outcome.state=='COMPLETE'
    assert store.claims==2


def test_mutating_callback_reentry_must_not_consume_any_nested_attempt():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    nested=[]; fired=[False]
    def action(*args):
        if not fired[0]:
            fired[0]=True
            # Normal callback-visible attribute mutation, identical class of
            # threat that earlier criterion scoring source guard was designed to resist.
            root._thread.busy = False
            try: nested.append(root.execute(plan=plan))
            except PaperExecutionDenied: nested.append('blocked')
    issuer.action=action
    outcome=root.execute(plan=plan)
    print('NESTED STATES', [x if isinstance(x,str) else x.state for x in nested], 'outer', outcome.state, 'attempt reservations',store.claims)
    assert nested == ['blocked'], 'Nested execution was admitted during an unfinished outer operation'
    assert store.claims == 2


def test_mutating_current_question_callback_must_not_execute_nested_paper():
    root, plan, issuer, fresh, runtime, store=_setup_two()
    nested=[]; fired=[False]
    def action(*args):
        if not fired[0]:
            fired[0]=True
            root._thread.busy=False
            try: nested.append(root.execute(plan=plan))
            except PaperExecutionDenied: nested.append('blocked')
    fresh.action=action
    outcome=root.execute(plan=plan)
    print('FRESH NESTED', [x if isinstance(x,str) else x.state for x in nested], 'outer', outcome.state, 'attempt reservations',store.claims)
    assert nested==['blocked'], 'Nested execution was admitted during authority contact'
    assert store.claims==2

def test_committed_f25_malformed_fresh_response_must_remain_indeterminate():
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    root, plan, *_ = _setup_one()
    store=AtomicStore(); store.mode='wrong_scope'  # FRESH commits, then returns foreign runtime field
    allocator=ClaimedAttemptAllocator(issuer=Issuer(),store=store, max_identifier_characters=128)
    # Substitute a qualified test physical attempt claim root only in fixture setup, before execution.
    object.__setattr__(root,'_attempts',allocator)
    outcome=root.execute(plan=plan)
    print('INVALID F25 RESPONSE', outcome.state, outcome.failure_kind, 'physical_claims',store.claims, 'claimed',len(store.claimed))
    assert store.claims==1 and len(store.claimed)==1
    assert outcome.result is None
    assert outcome.state=='INDETERMINATE', 'A committed but malformed new attempt reply is not a definitive no-effect denial'

@pytest.mark.parametrize('mode', ['wrong_scope', 'wrong_request_ref', 'missing_request_ref', 'no_reservation'])
def test_post_claim_invalid_fresh_cannot_be_called_definite_denial(mode):
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    root,plan,*_= _setup_one()
    store=AtomicStore();store.mode=mode
    object.__setattr__(root,'_attempts',ClaimedAttemptAllocator(issuer=Issuer(),store=store,max_identifier_characters=128))
    out=root.execute(plan=plan)
    print('MODE',mode,'STATE',out.state,'physical claim',store.claims,'committed',len(store.claimed))
    assert store.claims==1 and len(store.claimed)==1
    assert out.result is None
    assert out.state=='INDETERMINATE'


def test_definitive_pre_claim_refusal_remains_denied():
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    root,plan,*_= _setup_one()
    store=AtomicStore();store.mode='revoked'
    object.__setattr__(root,'_attempts',ClaimedAttemptAllocator(issuer=Issuer(),store=store,max_identifier_characters=128))
    out=root.execute(plan=plan)
    print('REVOKED STATE',out.state,'claims',store.claims,'committed',len(store.claimed))
    assert out.state=='DENIED' and len(store.claimed)==0

def test_authoritative_policy_changes_at_current_contact_must_not_grade_stale_policy():
    from dataclasses import replace
    from tests.integration.test_whole_paper_choice_execution import _setup_two
    root,plan,issuer,fresh,_,store=_setup_two()
    def next_issuer_response(_plan):
        if issuer.calls==2:
            q1=issuer.relation.questions[0]
            issuer.relation=replace(issuer.relation,questions=(replace(q1,scoring_policy_ref='SCHOOL-NEW-POLICY'),issuer.relation.questions[1]))
    issuer.action=next_issuer_response
    out=root.execute(plan=plan)
    print('CURRENT POLICY DRIFT',out.state,out.failure_kind,'claims',store.claims,'issuer calls',issuer.calls,'result?',out.result is not None)
    assert out.result is None and store.claims==0, 'Changed issuer policy must block initial attempt reservation before effects'

@pytest.mark.parametrize('field,new_value',[
    ('scoring_policy_ref','SCHOOL-NEW-POLICY'),
    ('rubric_ref','SCHOOL-NEW-RUBRIC'),
    ('answer_region_ref','SCHOOL-OTHER-ANSWER-REGION'),
])
def test_current_issuer_authority_drift_not_bound_to_execute_input(field,new_value):
    from dataclasses import replace
    from tests.integration.test_whole_paper_choice_execution import _setup_two
    root,plan,issuer,fresh,_,store=_setup_two()
    def on_paper_issuer(_plan):
        if issuer.calls==2:
            q1=issuer.relation.questions[0]
            issuer.relation=replace(issuer.relation,questions=(replace(q1,**{field:new_value}),issuer.relation.questions[1]))
    issuer.action=on_paper_issuer
    out=root.execute(plan=plan)
    print('CURRENT FACT CHANGED',field,'OUT',out.state,'attempt reservations',store.claims,'RESULT',out.result is not None)
    assert store.claims==0 and out.result is None, 'Official current authority drift was not bound back to grading execution'


from tests.integration.test_whole_paper_choice_execution import _setup_two


def test_effectful_same_thread_reentrancy_tamper_should_not_enable_nested_f25():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    observed = []
    entered = [False]

    def inner(_correlation, _question, _scope):
        if not entered[0]:
            entered[0] = True
            # Ordinary instance-member mutation of the public thread-local object.
            root._thread.busy = False
            outcome = root.execute(plan=plan)
            observed.append(outcome)

    fresh.action = inner
    outer = root.execute(plan=plan)
    assert all(x.state != 'COMPLETE' for x in observed)
    assert store.claims <= 2


def test_paper_issuer_can_reenter_effectful_root_before_contact_guard():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    entered = [False]
    inner_results = []

    def reenter(_plan):
        if not entered[0]:
            entered[0] = True
            root._thread.busy = False
            inner_results.append(root.execute(plan=plan))
    issuer.action = reenter
    outer = root.execute(plan=plan)
    assert not inner_results, (
        f'Nested scoring allowed from paper issuer: inner={[(o.state,len(o.completed), bool(o.result)) for o in inner_results]}, '
        f'outer={outer.state}, claims={store.claims}')


def _root_with_mutating_store(action):
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    base, plan, issuer, fresh, runtime, original_store = _setup_two()
    holder = {}
    class MutatingStore(type(original_store)):
        def claim_fresh_attempt(self, *, request):
            returned = super().claim_fresh_attempt(request=request)
            action(holder['root'])
            holder['triggered'] = holder.get('triggered', 0) + 1
            return returned
    store = MutatingStore()
    allocator = ClaimedAttemptAllocator(issuer=base._attempts._identify.__self__, store=store,
                                        max_identifier_characters=128)
    root = type(base)(contact=base._contact, correlation=base._correlation,
                      handoff=base._handoff, attempts=allocator,
                      max_identifier_characters=128, max_questions=10)
    holder['root'] = root
    return root, plan, store, holder


def _evaluator_calls(call):
    import sys
    from grading.choice_evaluator import evaluate_single_select_choice
    observed = [0]
    old = sys.getprofile()
    def trace(frame, event, arg):
        if event == 'call' and frame.f_code is evaluate_single_select_choice.__code__:
            observed[0] += 1
    sys.setprofile(trace)
    try:
        result = call()
    finally:
        sys.setprofile(old)
    return observed[0], result


def test_f25_callback_handoff_class_drift_must_block_evaluator():
    from grading.integration.evaluator_execution_binding import ProductionExecutionHandoff
    class ShadowHandoff(ProductionExecutionHandoff):
        __slots__ = ()
    root, plan, store, holder = _root_with_mutating_store(
        lambda r: setattr(r._handoff, '__class__', ShadowHandoff))
    calls, outcome = _evaluator_calls(lambda: root.execute(plan=plan))
    assert holder.get('triggered'), 'Attack did not execute: invalid test'
    assert calls == 0, (f'F25 class mutation permitted evaluator, count={calls}, state={outcome.state}')


def test_f25_mutates_installed_PRE_operation_before_evaluator():
    def mutate(root):
        prep = root._contact._installation.installed_preparation
        ops = prep._operations
        ops[next(iter(ops))] = lambda **kw: None
    root, plan, store, holder = _root_with_mutating_store(mutate)
    calls, outcome = _evaluator_calls(lambda: root.execute(plan=plan))
    assert holder.get('triggered'), 'Attack did not execute: invalid test'
    assert calls == 0, (f'Executor emitted {calls} judgments after installed PRE function drift, outcome={outcome.state}')


def test_explicit_runtime_binding_denial_is_not_outage():
    from grading.integration.evaluator_execution_binding import RuntimeBindingDenied
    root, plan, issuer, fresh, runtime, store = _setup_two()
    root._handoff._entry = object()  # normal assignment of installed alias; _require_root rejects
    outcome = root.execute(plan=plan)
    assert outcome.state == 'DENIED' and outcome.failure_kind == 'DENIED', (
        f'Explicit invalid installed root was classified {outcome.state}/{outcome.failure_kind}')


def test_normal_paper_issuer_reentrancy_rejected_before_f25():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    once = [False]
    denials = []
    nested_outcomes = []
    def callback(_):
        if not once[0]:
            once[0] = True
            try:
                nested_outcomes.append(root.execute(plan=plan))
            except Exception as exc:
                denials.append(type(exc).__name__)
    issuer.action = callback
    outcome = root.execute(plan=plan)
    assert denials == ['PaperExecutionDenied'], (denials, nested_outcomes)
    assert not nested_outcomes and outcome.state == 'COMPLETE' and store.claims == 2


def test_indeterminate_f25_has_known_request_custody_and_no_invented_attempt():
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    root, plan, *_ = _setup_one()
    store = AtomicStore()
    store.mode = 'wrong_scope'
    object.__setattr__(root, '_attempts', ClaimedAttemptAllocator(
        issuer=Issuer(), store=store, max_identifier_characters=128))
    outcome = root.execute(plan=plan)
    assert outcome.state == 'INDETERMINATE'
    assert len(store.claimed) == 1 and outcome.result is None
    assert outcome.observed_reservations == ()  # physical attempt claim rejected the untrusted reply internally
    assert len(outcome.contact_trace) == 1
    trace = outcome.contact_trace[0]
    assert trace.question_id == 'Q1'
    assert trace.request_ref == 'BACKEND-STABLE-REQUEST-REF'
    assert trace.f25_call_started and not trace.reservation_returned
    assert not trace.reservation_validated and not trace.evaluator_invoked
    assert not trace.judgments_emitted and not trace.s1_verified


def test_successful_two_question_contacts_have_full_validated_custody():
    from tests.integration.test_whole_paper_choice_execution import _setup_two
    root, plan, *_ = _setup_two()
    outcome = root.execute(plan=plan)
    assert outcome.state == 'COMPLETE' and outcome.result is not None
    assert len(outcome.observed_reservations) == 2
    assert tuple(t.question_id for t in outcome.contact_trace) == ('Q1', 'Q2')
    assert all((t.request_ref and t.f25_call_started and t.reservation_returned
                and t.reservation_validated and t.evaluator_invoked
                and t.judgments_emitted and t.s1_verified) for t in outcome.contact_trace)


def test_observed_f25_return_is_preserved_before_local_validation(monkeypatch):
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from grading.integration import whole_paper_choice_execution as impl
    root, plan, *_ = _setup_one()
    original_copy = impl._reservation_copy
    calls = []

    def rejecting_copy(*args, **kwargs):
        calls.append(args)
        raise impl.InvocationDenied('Injected rejection of returned grading-attempt object')

    monkeypatch.setattr(impl, '_reservation_copy', rejecting_copy)
    try:
        outcome = root.execute(plan=plan)
    finally:
        monkeypatch.setattr(impl, '_reservation_copy', original_copy)
    assert len(calls) == 1
    assert outcome.state == 'INDETERMINATE' and outcome.result is None
    assert len(outcome.observed_reservations) == 1
    assert len(outcome.contact_trace) == 1
    t = outcome.contact_trace[0]
    assert t.reservation_returned and not t.reservation_validated
    assert not t.evaluator_invoked and t.request_ref == outcome.observed_reservations[0].request_ref


def test_effectful_guard_is_released_after_noncontact_denial():
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    root, plan, _, fresh, _, store = _setup_one()
    prior = fresh.response
    fresh.response = object()
    first = root.execute(plan=plan)
    assert first.state != 'COMPLETE' and store.claims == 0
    fresh.response = prior
    second = root.execute(plan=plan)
    assert second.state == 'COMPLETE' and store.claims == 1


def test_f25_cleanup_failure_must_not_hide_possible_contact(monkeypatch):
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from grading.integration import whole_paper_choice_execution as impl
    root, plan, *_ = _setup_one()
    # Simulate physical attempt claim lifecycle cleanup failure after real evaluation was emitted.
    # We cannot patch its exact class method globally without changing all
    # objects, so patch the original concrete class's method within test scope.
    cls = type(root._attempts)
    def failed_finish(self, *, token):
        raise impl.PaperExecutionDenied('Injected grading-attempt release failure')
    monkeypatch.setattr(cls, 'finish_operation', failed_finish)
    outcome = root.execute(plan=plan)
    assert outcome.state == 'INDETERMINATE' and outcome.result is None
    assert outcome.contact_trace and outcome.contact_trace[0].s1_verified


def test_f25_contact_class_drift_prevents_further_evaluator_effects():
    from grading.integration.paper_execution_contact import ProductionPaperQuestionContact
    class ShadowContact(ProductionPaperQuestionContact):
        __slots__ = ()
        @staticmethod
        def _require_installed_handoff(_installation):
            pass  # a shadowing override must not be trusted
    def mutate(root):
        object.__setattr__(root._contact, '__class__', ShadowContact)
    root, plan, store, holder = _root_with_mutating_store(mutate)
    calls, out = _evaluator_calls(lambda: root.execute(plan=plan))
    assert holder['triggered'] == 1
    assert calls == 0 and out.result is None and out.state == 'INDETERMINATE'
    assert out.contact_trace[0].reservation_validated
    assert not out.contact_trace[0].evaluator_invoked


def test_concurrent_same_request_does_not_forge_local_exactly_once():
    from threading import Barrier
    from concurrent.futures import ThreadPoolExecutor
    from tests.integration.test_whole_paper_choice_execution import _setup_two
    root, plan, issuer, fresh, runtime, store = _setup_two()
    ready = Barrier(2, timeout=5)
    original_action = fresh.action
    def sync_first_question(_corr, question, _scope):
        if question.question_id == 'Q1':
            ready.wait()
        if original_action:
            original_action(_corr, question, _scope)
    fresh.action = sync_first_question
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(root.execute, plan=plan)
        second = pool.submit(root.execute, plan=plan)
        states = [first.result(timeout=12).state, second.result(timeout=12).state]
    # Only the atomic fixture store can decide fresh vs replay across threads.
    assert states.count('COMPLETE') == 1, states
    assert states.count('DENIED') == 1, states
    assert store.claims >= 2
