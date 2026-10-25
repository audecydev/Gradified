"""whole-paper: actual physical attempt claim, genuine evaluator, and once-only frozen whole-paper grading."""
from dataclasses import replace

from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from tests.integration.test_attempt_authority import Issuer, AtomicStore
from tests.integration.test_paper_execution_contact import rig


def _setup_one():
    contact, plan, paper_issuer, fresh, runtime, prep, issued = rig()
    scoring = prep.resolved.source.question_authority.scoring_authority
    relation = replace(issued.questions[0], rubric_ref=scoring.rubric.rubric_id,
                       scoring_policy_ref=scoring.policy.policy_id)
    paper_issuer.relation = replace(issued, questions=(relation,))
    store = AtomicStore()
    attempts = ClaimedAttemptAllocator(issuer=Issuer(), store=store,
                                       max_identifier_characters=128)
    root = ProductionWholePaperChoiceExecutor(
        contact=contact, correlation=contact._installation.correlation,
        handoff=contact._installation.handoff, attempts=attempts,
        max_identifier_characters=128, max_questions=10)
    return root, plan, paper_issuer, fresh, runtime, store


def test_real_one_question_f25_choice_s1_frozen_scoring():
    root, plan, issuer, fresh, runtime, store = _setup_one()
    result = root.execute(plan=plan)
    assert result.state == 'COMPLETE', result
    assert len(result.completed) == 1
    assert store.claims == 1 and fresh.calls == 1
    assert len(result.result.questions) == 1
    assert result.result.questions[0].verified.evaluated_judgments == result.completed[0].judgments
    assert result.result.paper_score is not None


def test_duplicate_f25_claim_never_executes_another_evaluation():
    root, plan, issuer, fresh, runtime, store = _setup_one()
    assert root.execute(plan=plan).state == 'COMPLETE'
    again = root.execute(plan=plan)
    assert again.state in ('DENIED', 'INCOMPLETE') and again.result is None
    assert store.claims == 2


def test_issuer_denial_before_attempt_blocks_f25():
    root, plan, issuer, fresh, runtime, store = _setup_one()
    fresh.response = object()
    result = root.execute(plan=plan)
    assert result.result is None and store.claims == 0


def _setup_two(*, grading_run_id=None, on_physical_claim=None):
    """Two actually admitted questions using real normalized OCR evidence admission/question evidence binding/PRE/CHOICE/approved eligibility and execution policy fixture ports.

    Fixture issuers are deliberately NOT operational school/physical attempt claim authentication.
    """
    from grading.rubric.lifecycle import (activate_version, approve_version,
        create_initial_version, validate_version, get_active_scoring_authority)
    from grading.rubric.fingerprint import compiled_authority_fingerprint
    from tests.support.rubric_authoring import simple_basis, simple_content, authoring_test_limits, sd
    from tests.integration.test_authorized_preparation import _inputs, _compose
    from tests.integration.test_trusted_preparation import _payload
    from tests.integration.test_choice_authority_admission import ChoicePorts
    from tests.integration.test_execution_eligibility_runtime import FixtureAuthorities
    from grading.integration.choice_authority_admission import ProductionChoiceAdmissionComposer
    from grading.integration.grading_orchestration import ProductionGradingEntry
    from grading.integration.evaluator_execution_binding import (
        ProductionEvaluatorRuntimeBinder, InstalledRuntime, ProductionExecutionHandoff)
    from grading.integration.execution_eligibility import ProductionExecutionEligibilityComposer
    from grading.integration.paper_execution_correlation import (
        IssuedQuestionExecutionRelation, IssuedPaperExecutionRelation,
        ProductionPaperExecutionCorrelation)
    from grading.integration.paper_execution_contact import ProductionPaperQuestionContact
    from grading.integration.paper_readiness_admission import (
        AdmittedPaperQuestion, AdmittedPaperPlan, PaperAdmissionRequest)
    from grading.integration.trusted_preparation import PreparationRequest
    from grading.contracts.paper_aggregation import (ExpectedQuestionResult,
        ResolvedPaperScoringAuthority)
    from grading.contracts.result import RubricRef, ScoringPolicyRef
    from grading.contracts.scoring_decimal import ScoringDecimal
    from grading.active_question_authority import ResolvedQuestionAuthority
    from grading.choice_evaluator import evaluate_single_select_choice
    from grading.contracts.choice import DETERMINISTIC_CHOICE_EVALUATOR_ID

    req1, src1, pre_ports = _inputs(_payload(2))
    if grading_run_id is not None:
        # Same genuine PRE/CHOICE fixture composition, independently scoped to
        # a successor run. Used to verify preclaimed re-evaluation is genuine.
        req1 = replace(req1, grading_run_id=grading_run_id)
        prepared_source = pre_ports.resolved.source
        pre_ports.resolved = replace(pre_ports.resolved, source=replace(
            prepared_source, context=replace(prepared_source.context,
                                             grading_run_id=grading_run_id)))
    original = pre_ports.resolved.source
    scoring1 = original.question_authority.scoring_authority
    limits = authoring_test_limits()
    content2 = replace(simple_content(), rubric_id='R-Q2', policy_id='P-Q2')
    rubric2 = activate_version(approve_version(validate_version(
        create_initial_version(simple_basis(question_id='Q2'), content2),
        limits=limits), teacher_ref='fixture-teacher'), limits=limits)
    scoring2 = get_active_scoring_authority(rubric2)
    paper = ResolvedPaperScoringAuthority(original.paper_authority.grading_spec_ref,
        tuple(ExpectedQuestionResult(qid, RubricRef(s.rubric.rubric_id, s.rubric.version),
              ScoringPolicyRef(s.policy.policy_id, s.policy.version,
                               s.policy.scoring_semantics_version))
              for qid, s in (('Q1', scoring1), ('Q2', scoring2))),
        ScoringDecimal.from_raw('0'), ScoringDecimal.from_raw('10'))
    q2 = ResolvedQuestionAuthority(original.question_authority.grading_spec_ref,
        'Q2', 'Select the second option', original.question_authority.context_policy,
        rubric2.content, scoring2)
    sources = {
        'Q1': replace(original, paper_authority=paper),
        'Q2': replace(original, paper_authority=paper, question_authority=q2),
    }
    request2 = replace(req1, question_id='Q2')

    class PREPorts(type(pre_ports)):
        def authorize_preparation(self, *, actor, request):
            self.events.append('authorize')
            return replace(self.grant, request=request)
        def resolve_revisioned_preparation(self, *, grant):
            self.events.append('source')
            return replace(self.resolved, source=sources[grant.request.question_id])
    pre_ports.__class__ = PREPorts
    prep_composer = _compose(pre_ports)
    prepared = {qid: prep_composer.prepare(request=req) for qid, req
                in (('Q1', req1), ('Q2', request2))}
    cp = {qid: ChoicePorts(prepared[qid]) for qid in prepared}
    # Q2 source is an actual approved compiled question, not a copied Q1 key.
    qp = cp['Q2']
    qp.key = replace(qp.key, authority=replace(qp.key.authority,
        question_id='Q2', compiled_authority_hash=compiled_authority_fingerprint(scoring2)))
    qp.selection = replace(qp.selection, selection=replace(
        qp.selection.selection, question_id='Q2', evidence_refs=('EVIDENCE-2',)))

    class ChoiceAuthority:
        def authorize_choice_request(self, *, request):
            return cp[request.question_id].authorize_choice_request(request=request)
        def authorize_choice(self, *, scope):
            return cp[scope.question_id].authorize_choice(scope=scope)
        def resolve_approved_choice_key(self, *, grant):
            return cp[grant.scope.question_id].resolve_approved_choice_key(grant=grant)
        def resolve_verified_choice_selection(self, *, grant):
            return cp[grant.scope.question_id].resolve_verified_choice_selection(grant=grant)
        def confirm_choice_revisions(self, *, grant):
            return cp[grant.scope.question_id].confirm_choice_revisions(grant=grant)
    choice_ports = ChoiceAuthority()
    choices = ProductionChoiceAdmissionComposer(
        pre_evidence=choice_ports, access=choice_ports, approved_keys=choice_ports,
        selections=choice_ports, revisions=choice_ports,
        max_identifier_characters=128, max_choice_options=64, max_choice_criteria=64)
    admitted = {
        qid: choices.admit(prepared=prepared[qid]) for qid in prepared
    }
    runtime_ports = {qid: FixtureAuthorities(admitted[qid]) for qid in prepared}

    class RuntimeAuthorities:
        def resolve_admitted_selection(self, *, scope):
            return runtime_ports[scope.question_id].resolve_admitted_selection(scope=scope)
        def resolve_execution_facts(self, *, scope, capability_ref):
            return runtime_ports[scope.question_id].resolve_execution_facts(scope=scope, capability_ref=capability_ref)
        def resolve_approved_eligibility_policy(self, *, scope, capability_ref):
            return runtime_ports[scope.question_id].resolve_approved_eligibility_policy(scope=scope, capability_ref=capability_ref)
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            return runtime_ports[scope.question_id].resolve_approved_runtime(scope=scope,
                capability_ref=capability_ref, policy_id=policy_id, policy_version=policy_version)
    inventory = RuntimeAuthorities()
    eligibility = ProductionExecutionEligibilityComposer(
        selection=inventory, facts=inventory, policy=inventory,
        max_identifier_characters=128, max_facts=8)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=inventory, eligibility=eligibility,
        installed=(InstalledRuntime('CHOICE', 'choice-native', '1',
                                  'content-sha256-ref-1', evaluate_single_select_choice),),
        max_identifier_characters=128, max_modalities=8, max_installed_runtimes=8,
        max_facts=8)
    entry = ProductionGradingEntry(preparation=prep_composer, choices=choices)
    handoff = ProductionExecutionHandoff(admission_entry=entry, eligibility=eligibility,
                                         runtime=binder)
    scope = admitted['Q1'].scope
    p_req = PaperAdmissionRequest(scope.tenant_ref, scope.session_ref, scope.grading_run_id,
        scope.submission_ref, scope.exam_ref, 'PAPER-1', 'SET-1', scope.grading_spec_ref)
    plan = AdmittedPaperPlan(p_req, scope.actor_ref, 'APP', 'APP-REV', 'SELECTION',
        'SEL-REV', scope.source_revision, 'READ-REV', tuple(
            AdmittedPaperQuestion(req, 'CHOICE', admitted[qid].scope.source_artifact_ref,
                scope.source_revision, admitted[qid].scope.evidence_scope_ref,
                f'REGION-{i}', scope.ocr_provenance)
            for i, (qid, req) in enumerate((('Q1', req1), ('Q2', request2)), 1)))
    relations = tuple(IssuedQuestionExecutionRelation(
        q.request.question_id, q.family, q.source_artifact_ref, q.evidence_scope_ref,
        q.answer_region_ref, q.source_revision, q.provenance_ref,
        sources[q.request.question_id].question_authority.scoring_authority.rubric.rubric_id,
        sources[q.request.question_id].question_authority.scoring_authority.policy.policy_id,
    ) for q in plan.questions)
    issued = IssuedPaperExecutionRelation(1, p_req, scope.actor_ref, 'SCHOOL',
        'ISSUANCE', p_req.paper_ref, p_req.set_ref, plan.approval_ref,
        plan.approval_revision, plan.selection_decision_ref, plan.selection_revision,
        plan.source_revision, plan.readiness_revision, relations)
    from tests.integration.test_paper_execution_contact import PaperIssuer, FreshIssuer
    paper_issuer = PaperIssuer(issued)
    fresh = FreshIssuer(relations[0])
    correlation = ProductionPaperExecutionCorrelation(issuer=paper_issuer,
        max_questions=10, max_identifier_characters=128)
    contact = ProductionPaperQuestionContact(correlation=correlation,
        handoff=handoff, issuer=fresh, max_questions=10, max_identifier_characters=128)

    class StablePerQuestionIssuer(Issuer):
        def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                         implementation_ref, eligibility_policy_id,
                                         eligibility_policy_version):
            issued = super().identify_reservation_request(scope=scope, family=family,
                runtime_id=runtime_id, runtime_version=runtime_version,
                implementation_ref=implementation_ref, eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version)
            return replace(issued, request_ref='REQUEST-' + scope.question_id)
    from grading.integration.attempt_authority import AttemptClaim, AttemptClaimDisposition
    class DistinctPhysicalStore(AtomicStore):
        def claim_fresh_attempt(self, *, request):
            if getattr(self, 'timeout_second', False) and request.scope.question_id == 'Q2':
                super().claim_fresh_attempt(request=request)  # may be durably committed
                raise RuntimeError('PRIVATE_F25_RESPONSE_LOST')
            result = super().claim_fresh_attempt(request=request)
            if on_physical_claim is not None:
                on_physical_claim(request)
            if result.disposition is AttemptClaimDisposition.FRESH:
                claim = replace(result.reservation,
                    attempt_id='ATT-' + request.scope.question_id,
                    reservation_ref='RES-' + request.scope.question_id)
                if getattr(self, 'duplicate_attempt_id', False) and request.scope.question_id == 'Q2':
                    claim = replace(claim, attempt_id='ATT-Q1')
                self.last_reservation = claim
                return AttemptClaim(request, result.disposition, claim)
            return result
    store = DistinctPhysicalStore()
    attempts = ClaimedAttemptAllocator(issuer=StablePerQuestionIssuer(),
        store=store, max_identifier_characters=128)
    root = ProductionWholePaperChoiceExecutor(contact=contact, correlation=correlation,
        handoff=handoff, attempts=attempts, max_identifier_characters=128, max_questions=10)
    return root, plan, paper_issuer, fresh, runtime_ports, store


def test_two_real_choice_evaluations_one_complete_paper_score():
    root, plan, paper_issuer, fresh, runtime, store = _setup_two()
    outcome = root.execute(plan=plan)
    assert outcome.state == 'COMPLETE', outcome.state
    assert [q.question_id for q in outcome.completed] == ['Q1', 'Q2']
    assert [q.score.question_id for q in outcome.result.questions] == ['Q1', 'Q2']
    assert all(q.verified.evaluated_judgments == emitted.judgments
               for q, emitted in zip(outcome.result.questions, outcome.completed, strict=True))
    assert store.claims == 2
    assert fresh.calls == 2
    assert [a.reservation.attempt_id for a in outcome.completed] == ['ATT-Q1', 'ATT-Q2']
    assert str(outcome.result.paper_score.final_score) == '10'


def test_second_question_denied_retains_first_attempt_but_never_scores_partial_paper():
    root, plan, paper_issuer, fresh, runtime, store = _setup_two()
    # The installed callback is captured at contact root construction; mutate
    # issuer-level state instead of substituting an installed method.
    fresh.action = lambda _correlation, question, _scope: (_ for _ in ()).throw(RuntimeError('revoked')) if question.question_id == 'Q2' else None
    outcome = root.execute(plan=plan)
    assert outcome.state in ('INCOMPLETE', 'UNAVAILABLE')
    assert outcome.result is None
    assert tuple(c.question_id for c in outcome.completed) == ('Q1',)
    assert store.claims == 1


def test_f25_duplicate_physical_attempt_blocks_second_evaluator_and_complete_grade():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    store.duplicate_attempt_id = True
    with _track_frozen_calls() as count:
        outcome = root.execute(plan=plan)
    assert count == [1]  # Q1 evaluated, Q2 blocked before evaluator
    assert store.claims == 2
    assert outcome.result is None
    assert outcome.state == 'INDETERMINATE'
    assert [x.question_id for x in outcome.completed] == ['Q1']


def test_revocation_between_questions_blocks_second_f25_claim():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    fresh.action = lambda _p, q, _s: (_ for _ in ()).throw(RuntimeError('private revoked')) if q.question_id == 'Q2' else None
    with _track_frozen_calls() as count:
        outcome = root.execute(plan=plan)
    assert count == [1]
    assert outcome.state == 'INCOMPLETE' and outcome.result is None
    assert len(outcome.completed) == 1 and store.claims == 1


def test_unsupported_family_blocks_entire_paper_before_any_claim():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    q2 = replace(plan.questions[1], family='DIRECT')
    revised_plan = replace(plan, questions=(plan.questions[0], q2))
    issuer.relation = replace(issuer.relation, questions=(issuer.relation.questions[0],
        replace(issuer.relation.questions[1], family='DIRECT')))
    with _track_frozen_calls() as count:
        outcome = root.execute(plan=revised_plan)
    assert outcome.state == 'UNSUPPORTED' and outcome.result is None
    assert outcome.failure_kind == 'UNSUPPORTED'
    assert store.claims == 0 and count == [0]


def test_foreign_scoring_policy_reference_blocks_before_claim():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    wrong = replace(issuer.relation.questions[1], scoring_policy_ref='FOREIGN-POLICY')
    issuer.relation = replace(issuer.relation,
        questions=(issuer.relation.questions[0], wrong))
    with _track_frozen_calls() as count:
        outcome = root.execute(plan=plan)
    assert outcome.state == 'DENIED' and outcome.result is None
    assert outcome.failure_kind == 'DENIED'
    assert store.claims == 0 and count == [0]


def test_duplicate_or_missing_paper_question_never_contacts_attempt_store():
    import pytest
    root, plan, issuer, fresh, runtime, store = _setup_two()
    for wrong in (
        replace(plan, questions=(plan.questions[0], plan.questions[0])),
        replace(plan, questions=(plan.questions[0],)),
        replace(plan, questions=(replace(plan.questions[0], source_revision='OLD'),
                                 plan.questions[1])),
    ):
        outcome = root.execute(plan=wrong)
        assert outcome.result is None
    assert store.claims == 0


def test_technical_f25_lost_response_does_not_retry_or_score():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    store.mode = 'raise_after_commit'
    outcome = root.execute(plan=plan)
    assert outcome.state == 'INDETERMINATE'
    assert outcome.result is None
    assert store.claims == 1
    assert not outcome.completed


def test_second_execution_does_not_reuse_prior_emitted_judgments():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    with _track_frozen_calls() as count:
        first = root.execute(plan=plan)
        second = root.execute(plan=plan)
    assert count == [2]
    assert first.state == 'COMPLETE'
    assert second.result is None
    assert second.state == 'DENIED'


def test_one_scoring_consumer_call_after_both_real_evaluator_calls():
    import sys
    from grading.execution import execute_grading_from_evaluations
    from grading.choice_evaluator import evaluate_single_select_choice
    root, plan, *_ = _setup_two()
    calls = {'choice': 0, 'whole_scoring': 0}
    previous = sys.getprofile()
    def profile(frame, event, arg):
        if event == 'call':
            if frame.f_code is evaluate_single_select_choice.__code__:
                calls['choice'] += 1
            if frame.f_code is execute_grading_from_evaluations.__code__:
                calls['whole_scoring'] += 1
    sys.setprofile(profile)
    try:
        outcome = root.execute(plan=plan)
    finally:
        sys.setprofile(previous)
    assert outcome.state == 'COMPLETE'
    assert calls == {'choice': 2, 'whole_scoring': 1}


def test_paper_mutation_during_current_issuer_contact_stops_before_f25():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    def mutate_plan(_, question, __):
        if question.question_id == 'Q1':
            object.__setattr__(plan, 'selection_revision', 'REVOKED')
    fresh.action = mutate_plan
    outcome = root.execute(plan=plan)
    assert outcome.result is None and outcome.state == 'DENIED'
    assert store.claims == 0


def test_q2_attempt_reservation_remains_visible_after_duplicate_attempt_rejection():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    store.duplicate_attempt_id = True
    outcome = root.execute(plan=plan)
    assert outcome.result is None and outcome.state == 'INDETERMINATE'
    assert [r.request_ref for r in outcome.observed_reservations] == [
        'REQUEST-Q1', 'REQUEST-Q2']
    assert [r.attempt_id for r in outcome.observed_reservations] == ['ATT-Q1', 'ATT-Q1']


def test_fresh_callback_nested_execution_denied_without_nested_f25():
    root, plan, issuer, fresh, runtime, store = _setup_two()
    captured = []
    def attempt_reenter(*_):
        try:
            root.execute(plan=plan)
        except Exception as exc:
            captured.append(type(exc).__name__)
    fresh.action = attempt_reenter
    outcome = root.execute(plan=plan)
    assert captured == ['PaperExecutionDenied', 'PaperExecutionDenied']
    assert outcome.state == 'COMPLETE'
    assert store.claims == 2


def test_second_f25_timeout_after_possible_commit_preserves_first_attempt():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    store.timeout_second = True
    with _track_frozen_calls() as count:
        outcome = root.execute(plan=plan)
    assert outcome.state == 'INDETERMINATE' and outcome.failure_kind == 'UNKNOWN'
    assert outcome.result is None and store.claims == 2 and count == [1]
    assert [r.request_ref for r in outcome.observed_reservations] == ['REQUEST-Q1']
    assert [c.question_id for c in outcome.completed] == ['Q1']


def test_scope_mismatch_blocks_before_any_attempt_or_evaluation():
    from tests.integration.test_evaluator_invocation import _track_frozen_calls
    root, plan, issuer, fresh, runtime, store = _setup_two()
    altered = replace(issuer.relation.questions[1], evidence_scope_ref='FOREIGN-SCOPE')
    issuer.relation = replace(issuer.relation,
        questions=(issuer.relation.questions[0], altered))
    with _track_frozen_calls() as calls:
        outcome = root.execute(plan=plan)
    assert calls == [0] and store.claims == 0
    assert outcome.result is None


def test_confirmation_callback_revokes_original_issuer_before_second_f25():
    """Fresh confirmation is not a lease over independent paper issuance."""
    root, plan, issuer, fresh, runtime, store = _setup_two()
    seen = []
    def revoke(_paper, question, _scope):
        seen.append(question.question_id)
        if question.question_id == 'Q2':
            issuer.relation = replace(issuer.relation,
                approval_revision='REVOKED-DURING-Q2-CONFIRMATION')
    fresh.action = revoke
    outcome = root.execute(plan=plan)
    assert 'Q2' in seen
    assert store.claims == 1, 'Q2 attempt reservation after independent paper revocation'
    assert outcome.result is None and len(outcome.completed) == 1
