"""Score an authorized, already-claimed paper retry and conditionally commit the candidate.

The installed retry claimer alone contacts physical attempt claim. This consumer never
calls the normal physical attempt claim allocator. The approved current executable and scoring
version are checked BEFORE the first retry claim and again after claiming.
No locally complete score constitutes school publication or retry authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock

from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.contracts.paper_aggregation import ResolvedPaperScoringAuthority
from grading.execution import (
    GradingExecutionContext, QuestionExecutionInput,
    execute_grading_from_evaluations,
)
from grading.verification.evidence import verify_evaluated_judgments
from grading.integration.attempt_lineage import _snapshot_owned
from grading.integration.paper_execution_correlation import _plan, _relation
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.paper_execution_contact import ProductionPaperQuestionContact
from grading.integration.attempt_authority import _request_snapshot
from grading.integration.evaluator_invocation import _validated_binding_snapshot, _reservation_copy
from grading.integration.academic_claim_binding import academic_intent, validate_preparation
from grading.integration import whole_paper_choice_execution as _choice_exec
from grading.integration.whole_paper_choice_execution import (
    ProductionWholePaperChoiceExecutor, NonpublishingPaperOutcome,
    CapturedChoiceAttempt, AttemptContactTrace,
)
from grading.integration.whole_paper_attempt_custody import PaperAttemptCustody, _admit
from grading.integration.whole_paper_cas import (
    ProductionWholePaperCAS, PaperCASOutcome, PaperCASState,
    _enter_cas, _leave_cas,
)
from grading.integration.paper_retry_claim import (
    ProductionAuthorizedPaperRetry, PaperRetryClaimObservation, RetryClaimState,
)


class GradedRetryState(str, Enum):
    PRE_EFFECT_BLOCKED = 'PRE_EFFECT_BLOCKED'
    UNKNOWN = 'UNKNOWN'
    CAS_ACKNOWLEDGED = 'CAS_ACKNOWLEDGED'
    CAS_BLOCKED = 'CAS_BLOCKED'


@dataclass(frozen=True, slots=True, repr=False)
class GradedRetryOutcome:
    state: GradedRetryState
    physical: PaperRetryClaimObservation | None = None
    custody: PaperAttemptCustody | None = None
    cas: PaperCASOutcome | None = None
    authorization: object = None  # original stage-specific legal operation transition observation; NON-bearer

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def authorizes_publication(self) -> bool:
        return False


class ProductionGradedPaperRetry:
    """Single-use integrated retry producer, not a caller-provided score API.

    A qualified installation of current PRE/evaluator/deterministic scoring and whole-paper score commit paper CAS is
    mandatory. This operation retains partial physical custody on failure;
    externally supplied claim observations can never be grading credentials.
    """
    __slots__ = ('_claims', '_executor', '_cas', '_questions', '_maximum', '_gate', '_started')

    def __init__(self, *, claims: ProductionAuthorizedPaperRetry,
                 executor: ProductionWholePaperChoiceExecutor | "ProductionWholePaperFamilyExecutor",
                 cas: ProductionWholePaperCAS):
        from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
        family = type(executor) is ProductionWholePaperFamilyExecutor
        if (type(claims) is not ProductionAuthorizedPaperRetry
                or type(executor) not in (ProductionWholePaperChoiceExecutor, ProductionWholePaperFamilyExecutor)
                or type(cas) is not ProductionWholePaperCAS
                or cas._custody._executor is not executor
                or cas._require_academic is not True
                or claims._questions != cas._questions
                or claims._max != cas._max
                or (executor._questions if family else executor._maximum) != cas._questions
                or (executor._max if family else executor._limit) != cas._max
                or ((claims._joint_effect is not None) != (cas._joint_commit is not None or cas._purpose_commit is not None))
                or (claims._joint_effect is not None and claims._runtime_executor is not executor)):
            raise ValueError('Exact qualified retry/current evaluator/strict paper CAS roots required.')
        object.__setattr__(self, '_claims', claims)
        object.__setattr__(self, '_executor', executor)
        object.__setattr__(self, '_cas', cas)
        object.__setattr__(self, '_questions', claims._questions)
        object.__setattr__(self, '_maximum', claims._max)
        object.__setattr__(self, '_gate', Lock())
        object.__setattr__(self, '_started', False)

    def __setattr__(self, key, value):
        raise AttributeError('Qualified graded retry composition is immutable.')

    def execute_and_commit(self, *, plan: AdmittedPaperPlan) -> GradedRetryOutcome:
        if not self._gate.acquire(blocking=False):
            return GradedRetryOutcome(GradedRetryState.UNKNOWN)
        try:
            if self._started:
                return GradedRetryOutcome(GradedRetryState.UNKNOWN)
            object.__setattr__(self, '_started', True)
            try:
                lease = _enter_cas(self._cas)
            except Exception:
                return GradedRetryOutcome(GradedRetryState.UNKNOWN)
            try:
                return self._execute_owned(plan=plan)
            finally:
                _leave_cas(self._cas, lease)
        finally:
            self._gate.release()

    def _execute_owned(self, *, plan):
        executor = self._executor
        from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
        if type(executor) is ProductionWholePaperFamilyExecutor:
            return self._execute_family_owned(plan=plan)
        try:
            verified = _plan(plan, self._questions, self._maximum)
            plan_snapshot = _snapshot_owned(verified)
            preflight = {}
            def before_effect(grant):
                # This callback executes INSIDE authorized retry claim after authentic legal operation transition retry
                # admission, and BEFORE the academic preparation/physical attempt claim.
                # In particular, opening PRE evidence cannot precede legal operation transition.
                try:
                    if _plan(plan,self._questions,self._maximum) != verified:
                        return False
                    executor._check_installed_contact()
                    correlated = executor._correlation.preflight(plan=verified)
                    issued = _relation(correlated.issuer_relation,self._questions,self._maximum)
                    if (correlated.execution_state != 'CORRELATED_CHOICE_ONLY'
                            or issued.request != verified.request
                            or issued != grant.issued_paper
                            or len(issued.questions) != len(verified.questions)
                            or tuple(q.question_id for q in issued.questions) != tuple(
                                q.request.question_id for q in verified.questions)):
                        return False
                    baseline = None
                    for q, relation, request in zip(verified.questions,issued.questions,
                                                     grant.new_requests,strict=True):
                        if q.family != 'CHOICE' or relation.family != 'CHOICE':
                            return False
                        _, snapshot, detached = executor._prepared(q.request,verified,relation)
                        whole=(detached.prepared.context,detached.prepared.paper_authority,
                               detached.prepared.admitted_evidence.evidence)
                        if baseline is None:
                            baseline=whole
                        elif baseline != whole:
                            return False
                        scope,_,_,policy,_,_,_,approved,_=snapshot
                        original=_request_snapshot(request,self._maximum)
                        if (original[0] != scope or original[2] != q.family
                                or original[3:8] != (
                                    approved.runtime_id,approved.runtime_version,
                                    approved.implementation_ref,policy.policy_id,
                                    policy.policy_version)):
                            return False
                    context,paper,evidence=baseline
                    if (type(context) is not GradingExecutionContext
                            or type(paper) is not ResolvedPaperScoringAuthority
                            or paper != grant.scoring
                            or _plan(plan,self._questions,self._maximum) != verified):
                        return False
                    preflight.clear()
                    preflight.update(issued=issued,baseline=baseline,
                        snapshot=_snapshot_owned((verified,issued,paper)))
                    return True
                except Exception:
                    return False
            # Exactly one invocation of authorized retry claim's genuine atomic retry-claim route.
            physical=self._claims.claim(plan=verified,_pre_effect_grade_check=before_effect)
        except Exception:
            return GradedRetryOutcome(GradedRetryState.PRE_EFFECT_BLOCKED)
        if physical.state is not RetryClaimState.CLAIMED:
            return GradedRetryOutcome(
                GradedRetryState.PRE_EFFECT_BLOCKED if physical.state is RetryClaimState.PRE_EFFECT_BLOCKED
                else GradedRetryState.UNKNOWN,physical)
        if 'baseline' not in preflight:
            return GradedRetryOutcome(GradedRetryState.UNKNOWN,physical)
        issued=preflight['issued']
        baseline=preflight['baseline']
        context,paper,evidence=baseline
        base_snapshot=preflight['snapshot']
        # The observation is NOT a credential. Require the exact privately
        # retained claim span produced by this installed physical attempt claim owner.
        material=self._claims._last_material
        if (type(material) is not tuple or len(material) != 4
                or material[0] is not physical):
            return GradedRetryOutcome(GradedRetryState.UNKNOWN,physical)
        _, grant, preparations, original_grant_snapshot = material
        if len(preparations) != len(verified.questions):
            return GradedRetryOutcome(GradedRetryState.UNKNOWN,physical)
        completed=[]
        traces=[]
        observed=[]
        prepared_inputs=[]
        try:
            if (_snapshot_owned(grant) != original_grant_snapshot
                    or _snapshot_owned((verified,issued,paper)) != base_snapshot
                    or not before_effect(grant)) :
                raise ValueError('Academic/installed grader drifted after grading-attempt claim.')
            # Every physical attempt claim has already happened. NO allocator, no attempt issuer,
            # no physical retry store method can be reached from this loop.
            for q,relation,physical_q,request,preparation in zip(
                    verified.questions,issued.questions,physical.claimed,
                    grant.new_requests,preparations,strict=True):
                scope = _request_snapshot(request,self._maximum)
                if (physical_q.question_id != q.request.question_id
                        or physical_q.new_request_ref != scope[1]
                        or physical_q.reservation.request_ref != scope[1]):
                    raise ValueError('Claim material is not exact new paper.')
                academic = academic_intent(request,issued,paper,self._maximum,self._questions)
                validate_preparation(preparation,academic,self._maximum)
                reservation=_reservation_copy(physical_q.reservation,
                    expected=physical_q.reservation,maximum=self._maximum)
                observed.append(reservation)
                traces.append(AttemptContactTrace(q.request.question_id,scope[1],
                    True,True,True,False,False,False,request,preparation))
                bound,snapshot,detached=executor._prepared(q.request,verified,relation)
                if ((detached.prepared.context,detached.prepared.paper_authority,
                        detached.prepared.admitted_evidence.evidence)!=baseline
                        or _snapshot_owned(grant) != original_grant_snapshot
                        or _snapshot_owned((verified,issued,paper)) != base_snapshot):
                    raise ValueError('Changed runtime/paper during graded retry.')
                confirm=ProductionPaperQuestionContact.preflight_choice(
                    executor._contact,plan=verified,question_id=q.request.question_id)
                # Current-question confirmation can trigger issuer callback
                # state drift after the initial whole-paper preflight. The
                # physical retry claims already exist; do not turn them into
                # a scored CAS result if the independent paper issuer changed.
                executor._check_installed_contact()
                renewed = executor._correlation.preflight(plan=verified)
                executor._check_installed_contact()
                if (renewed.execution_state != 'CORRELATED_CHOICE_ONLY'
                        or _relation(renewed.issuer_relation, self._questions,
                                     self._maximum) != issued
                        or _plan(plan, self._questions, self._maximum) != verified
                        or _snapshot_owned(grant) != original_grant_snapshot
                        or _snapshot_owned((verified, issued, paper)) != base_snapshot):
                    raise ValueError('Issued paper changed during retry question confirmation.')
                # A paper-issuer callback can replace independently installed
                # runtime approval without mutating the earlier bound record.
                # Physical retry claims remain real if fresh admission fails.
                executor._reconfirm_runtime(q.request, verified, relation,
                                            snapshot, detached, baseline)
                executor._confirm_issuer_after_runtime(verified, verified, issued)
                scope_now,_,_,policy,_,_,_,approved,_=snapshot
                if (confirm.state != 'PREFLIGHT_ONLY'
                        or (confirm.runtime_id,confirm.runtime_version,
                            confirm.implementation_ref) != (
                            approved.runtime_id,approved.runtime_version,
                            approved.implementation_ref)
                        or _request_snapshot(request,self._maximum)[0] != scope_now):
                    raise ValueError('Current PRE permission changed after retry claim.')
                traces[-1] = AttemptContactTrace(q.request.question_id,scope[1],
                    True,True,True,True,False,False,request,preparation,approved)
                emitted=_choice_exec.evaluate_single_select_choice(
                    authority=detached.choice_authority,
                    selection=detached.selection,
                    scoring_authority=detached.prepared.question_authority.scoring_authority)
                if (type(emitted) is not tuple or not emitted
                        or any(type(j) is not EvaluatedCriterionJudgment for j in emitted)):
                    raise ValueError('Non-genuine evaluator output.')
                traces[-1] = AttemptContactTrace(q.request.question_id,scope[1],
                    True,True,True,True,True,False,request,preparation,approved)
                s1=verify_evaluated_judgments(evidence=evidence,
                    question_id=q.request.question_id,judgments=emitted)
                if (s1.evaluated_judgments != emitted
                        or _snapshot_owned(grant) != original_grant_snapshot
                        or _snapshot_owned((verified,issued,paper)) != base_snapshot):
                    raise ValueError('evidence verification result/academic authority changed.')
                traces[-1] = AttemptContactTrace(q.request.question_id,scope[1],
                    True,True,True,True,True,True,request,preparation,approved)
                completed.append(CapturedChoiceAttempt(q.request.question_id,reservation,emitted))
                prepared_inputs.append(QuestionExecutionInput(q.request.question_id,emitted,
                    detached.prepared.question_authority.scoring_authority))
            scored=execute_grading_from_evaluations(context=context,evidence=evidence,
                questions=tuple(prepared_inputs),paper_authority=paper)
            outcome=NonpublishingPaperOutcome('COMPLETE',tuple(completed),scored,None,
                None,tuple(observed),tuple(traces),issued)
            custody=_admit(verified,outcome,self._questions,self._maximum)
        except Exception:
            # Physical claims are real even when evaluator/deterministic scoring/scoring fails.
            # Preserve known requests and reservations, no aggregate score.
            # The remaining already-claimed questions are physical facts, too.
            for q,claim,request,preparation in zip(verified.questions[len(traces):],
                    physical.claimed[len(traces):],
                    grant.new_requests[len(traces):],preparations[len(traces):],strict=True):
                traces.append(AttemptContactTrace(q.request.question_id,
                    claim.new_request_ref,True,True,True,False,False,False,
                    request,preparation))
                observed.append(claim.reservation)
            try:
                partial = NonpublishingPaperOutcome('INDETERMINATE',tuple(completed),None,
                    None,'UNKNOWN',tuple(observed),tuple(traces),issued)
                custody=_admit(verified,partial,self._questions,self._maximum)
            except Exception:
                custody=None
            return GradedRetryOutcome(GradedRetryState.UNKNOWN,physical,custody,authorization=grant)
        # Only this trusted, in-flight producer provides the real scored custody.
        # The CAS writer uses the EXISTING strict whole-paper validation and
        # issuer/store path; it does not replay an physical attempt claim to obtain custody.
        try:
            from grading.integration.whole_paper_cas import ScoredPaperPurpose
            purpose=ScoredPaperPurpose('RETRY',retry_grant=grant,
                                       retry_original=physical.original)
            cas=self._cas._commit_owned_custody(custody,predecessor=None,purpose=purpose)
            self._cas._track_issued_outcome(cas)
        except Exception:
            return GradedRetryOutcome(GradedRetryState.UNKNOWN,physical,custody,authorization=grant)
        return GradedRetryOutcome(
            GradedRetryState.CAS_ACKNOWLEDGED if cas.state is PaperCASState.COMMITTED
            else GradedRetryState.CAS_BLOCKED if cas.state is PaperCASState.BLOCKED
            else GradedRetryState.UNKNOWN, physical,custody,cas,grant)


    def _execute_family_owned(self, *, plan):
        """authorized retry claim physical original-to-new claim, then existing deterministic scoring/frozen family grade.

        This method cannot claim physical attempt claim independently: only the already-installed
        ProductionAuthorizedPaperRetry owner may contact its joint store.
        Failed/uncertain claims are observations, never a completed paper grade.
        """
        from dataclasses import replace
        from grading.integration.whole_paper_family_execution import (
            FamilyPaperExecutionOutcome, CapturedFamilyAttempt,
        )
        from grading.integration.paper_family_evaluation import (
            DirectQuestionEvaluation, NumericQuestionEvaluation,
            _admitted_values, _detached_admitted, evaluate_supported_paper_questions,
        )
        from grading.integration.evaluator_execution_binding import BoundEvaluatorRuntime
        from grading.contracts.numeric_evaluation import (
            DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION,
        )
        from grading.integration.whole_paper_cas import ScoredPaperPurpose
        executor = self._executor
        preflight = {}
        try:
            from grading.integration.direct_provider_route import (
                capture_direct_route_installation, require_direct_route_installation,
            )
            route = executor._direct_route
            original_route_installation = capture_direct_route_installation(route)

            def unchanged_route():
                require_direct_route_installation(executor._direct_route,
                                                  original_route_installation)
                return True

            verified = _plan(plan, self._questions, self._maximum)
            plan_snapshot = _admitted_values(verified)

            def before_effect(grant):
                # Called inside the installed authorized retry claim owner after legal operation transition original
                # recovery and before each avoidable academic/physical attempt claim contact.
                try:
                    if _admitted_values(_plan(plan, self._questions, self._maximum)) != plan_snapshot:
                        return False
                    corr = executor._correlation.preflight(plan=verified)
                    issued = _relation(corr.issuer_relation, self._questions, self._maximum)
                    if (corr.execution_state != 'CORRELATED_DIRECT_NUMERIC'
                            or issued != grant.issued_paper
                            or issued.request != verified.request
                            or tuple(q.family for q in issued.questions) != tuple(
                                q.family for q in verified.questions)):
                        return False
                    full = executor._current(verified, verified, issued)
                    if _admitted_values(full.paper_authority) != _admitted_values(grant.scoring):
                        return False
                    values = _admitted_values((full.context, full.evidence.evidence,
                        full.paper_authority, tuple(op.authority for op in full.operations),
                        full.scopes))
                    installations = tuple(
                        (op.evaluator, op.evaluator._provider,
                         op.evaluator._model_answer_source,
                         _admitted_values(op.evaluator._limits),
                         _admitted_values(op.evaluator._evaluator_metadata))
                        if type(op) is DirectQuestionEvaluation else
                        (op.binding_source, op.authority_source)
                        for op in full.operations)
                    if 'values' in preflight and (
                        values != preflight['values']
                        or any(a != b for a,b in zip(
                            tuple(q.family for q in issued.questions),
                            preflight['families'], strict=True))
                        or any(
                            (type(op) is DirectQuestionEvaluation and
                             (op.evaluator is not inst[0]
                              or op.evaluator._provider is not inst[1]
                              or op.evaluator._model_answer_source is not inst[2]
                              or _admitted_values(op.evaluator._limits) != inst[3]
                              or _admitted_values(op.evaluator._evaluator_metadata) != inst[4]))
                            or (type(op) is NumericQuestionEvaluation and
                                (op.binding_source is not inst[0]
                                 or op.authority_source is not inst[1]))
                            for op, inst in zip(full.operations, preflight['installations'], strict=True))):
                        return False
                    if not unchanged_route():
                        return False
                    route_grants = tuple(
                        route.preflight(plan=verified,question_id=question.question_id,
                            purpose='RETRY',evaluator=op.evaluator)
                        if route is not None and type(op) is DirectQuestionEvaluation else None
                        for question,op in zip(issued.questions,full.operations,strict=True))
                    if 'route_grants' in preflight and route_grants != preflight['route_grants']:
                        return False
                    # Canonical request preparation is a reader-only academic
                    # operation. It must be qualified before the authorized retry claim physical attempt claim,
                    # never materialized from a mutable store after that claim.
                    if 'prepared_requests' not in preflight:
                        prepared_requests = tuple(
                            op.evaluator.prepare_request(
                                authority=op.authority, evidence=full.evidence.evidence,
                                execution_context=full.context,
                                evaluation_attempt_id=op.evaluation_attempt_id)
                            if route is not None and type(op) is DirectQuestionEvaluation else None
                            for op in full.operations)
                    else:
                        prepared_requests = preflight['prepared_requests']
                    # Recheck on every pre-effect pass, including cached requests;
                    # use transport's actual serializer, not a second byte shape.
                    from grading.providers.semantic_replay import (
                        direct_text_semantic_request_fingerprint, _direct_text_semantic_request_bytes,
                    )
                    if any(prepared is not None and (
                        prepared.question_id != approved_route.question_id or
                        direct_text_semantic_request_fingerprint(prepared) != approved_route.request_sha256 or
                        len(_direct_text_semantic_request_bytes(prepared)) > route._max_request)
                        for prepared, approved_route in zip(prepared_requests, route_grants, strict=True)):
                        return False
                    # Approval reads can mutate the evaluator or the separately
                    # installed sender/writer. Reject before the authorized retry claim physical attempt claim.
                    if not unchanged_route() or any(
                        (type(op) is DirectQuestionEvaluation and (
                            op.evaluator is not inst[0]
                            or op.evaluator._provider is not inst[1]
                            or op.evaluator._model_answer_source is not inst[2]
                            or _admitted_values(op.evaluator._limits) != inst[3]
                            or _admitted_values(op.evaluator._evaluator_metadata) != inst[4]))
                        or (type(op) is NumericQuestionEvaluation and
                            (op.binding_source is not inst[0] or op.authority_source is not inst[1]))
                        for op, inst in zip(full.operations, installations, strict=True)):
                        return False
                    for question, op, scope, request in zip(issued.questions, full.operations,
                            full.scopes, grant.new_requests, strict=True):
                        runtime = executor._binder.bind_family(
                            scope=scope, family=question.family,
                            context_policy=op.authority.context_policy)
                        if type(runtime) is not BoundEvaluatorRuntime:
                            return False
                        approved = runtime.approved_runtime
                        selected = runtime.eligibility.selection.selected_capability_ref.evaluator_metadata
                        if question.family == 'DIRECT':
                            if (type(op) is not DirectQuestionEvaluation
                                    or _admitted_values(op.evaluator._evaluator_metadata) !=
                                       _admitted_values(selected)):
                                return False
                        elif (selected.evaluator_id, selected.version) != (
                                DETERMINISTIC_NUMERIC_EVALUATOR_ID,
                                DETERMINISTIC_NUMERIC_EVALUATOR_VERSION):
                            return False
                        original_req = _request_snapshot(request, self._maximum)
                        if (original_req[0] != scope or original_req[2] != question.family
                                or original_req[3:8] != (
                                    approved.runtime_id, approved.runtime_version,
                                    approved.implementation_ref,
                                    runtime.eligibility.policy.policy_id,
                                    runtime.eligibility.policy.policy_version)):
                            return False
                    # Recheck source after potentially effectful installed
                    # runtime callbacks; the callback itself is not a grant.
                    renewed = executor._correlation.preflight(plan=verified)
                    if (renewed.execution_state != 'CORRELATED_DIRECT_NUMERIC'
                            or _relation(renewed.issuer_relation, self._questions,
                                         self._maximum) != issued):
                        return False
                    if not unchanged_route() or any(
                        type(op) is DirectQuestionEvaluation and (
                            op.evaluator._provider is not inst[1]
                            or op.evaluator._model_answer_source is not inst[2]
                            or _admitted_values(op.evaluator._limits) != inst[3]
                            or _admitted_values(op.evaluator._evaluator_metadata) != inst[4])
                        for op, inst in zip(full.operations, installations, strict=True)):
                        return False
                    if 'values' not in preflight:
                        preflight.update(issued=issued, full=full,
                            values=values, installations=installations,
                            families=tuple(q.family for q in issued.questions),
                            route_grants=route_grants, prepared_requests=prepared_requests)
                    return True
                except Exception:
                    return False

            physical = self._claims.claim(
                plan=verified, _pre_effect_grade_check=before_effect)
        except Exception:
            return GradedRetryOutcome(GradedRetryState.PRE_EFFECT_BLOCKED)
        if physical.state is not RetryClaimState.CLAIMED:
            return GradedRetryOutcome(
                GradedRetryState.PRE_EFFECT_BLOCKED
                if physical.state is RetryClaimState.PRE_EFFECT_BLOCKED
                else GradedRetryState.UNKNOWN, physical)
        material = self._claims._last_material
        if (type(material) is not tuple or len(material) != 4 or
                material[0] is not physical or 'issued' not in preflight):
            return GradedRetryOutcome(GradedRetryState.UNKNOWN, physical)
        _, grant, preparations, original_grant_snapshot = material
        issued, full = preflight['issued'], preflight['full']
        observed, traces, completed = [], [], []
        custody = None
        try:
            if (len(physical.claimed) != len(verified.questions)
                    or len(preparations) != len(verified.questions)
                    or _snapshot_owned(grant) != original_grant_snapshot
                    or not before_effect(grant)):
                raise ValueError('Physical RETRY is not current issued complete paper.')
            operations = []
            for q, relation, claim, request, preparation, op, scope in zip(
                    verified.questions, issued.questions, physical.claimed,
                    grant.new_requests, preparations, full.operations, full.scopes, strict=True):
                request_values = _request_snapshot(request, self._maximum)
                if (claim.question_id != q.request.question_id
                        or claim.new_request_ref != request_values[1]
                        or claim.reservation.request_ref != request_values[1]
                        or request_values[0] != scope
                        or request_values[2] != relation.family):
                    raise ValueError('RETRY physical observation is not original grading-attempt request.')
                intent = academic_intent(request, issued, grant.scoring,
                                         self._maximum, self._questions)
                validate_preparation(preparation, intent, self._maximum)
                reservation = _reservation_copy(claim.reservation,
                    expected=claim.reservation, maximum=self._maximum)
                observed.append(reservation)
                installed = executor._binder.bind_family(
                    scope=scope, family=q.family,
                    context_policy=op.authority.context_policy)
                traces.append(AttemptContactTrace(q.request.question_id,
                    claim.new_request_ref, True, True, True, False, False, False,
                    request, preparation, installed.approved_runtime))
                route = executor._direct_route
                operations.append(
                    replace(op, evaluation_attempt_id=reservation.attempt_id,
                        evaluator=route.bind_attempt(
                            approved=preflight['route_grants'][len(operations)],
                            plan=verified,evaluator=op.evaluator,reservation=reservation,
                            prepared_request=preflight['prepared_requests'][len(operations)])
                        if route is not None else op.evaluator)
                    if type(op) is DirectQuestionEvaluation else op)
            if (_snapshot_owned(grant) != original_grant_snapshot
                    or not before_effect(grant)):
                raise ValueError('RETRY executor/source changed after grading-attempt.')
            scored = evaluate_supported_paper_questions(
                context=full.context, evidence=_detached_admitted(full.evidence.evidence),
                paper_authority=full.paper_authority, operations=tuple(operations))
            if len(scored.questions) != len(verified.questions):
                raise ValueError('RETRY paper score incomplete.')
            completed = [CapturedFamilyAttempt(q.request.question_id, q.family,
                claim.reservation, record.verified.evaluated_judgments)
                for q, claim, record in zip(verified.questions, physical.claimed,
                                             scored.questions, strict=True)]
            # Do not accept a scored result if a callback changed the original
            # exact installed graph while semantic evaluation was running.
            if (_snapshot_owned(grant) != original_grant_snapshot
                    or not before_effect(grant)):
                raise ValueError('RETRY academic source changed during evaluation.')
            traces = [replace(trace, evaluator_invoked=True,
                              judgments_emitted=True, s1_verified=True)
                      for trace in traces]
            outcome = FamilyPaperExecutionOutcome('COMPLETE', tuple(completed),
                scored, None, tuple(traces), tuple(observed), issued)
            custody = _admit(verified, outcome, self._questions, self._maximum)
        except Exception:
            # Physical effects cannot be rolled back or counted as denial.
            for q, claim, request, preparation in zip(
                    verified.questions[len(traces):], physical.claimed[len(traces):],
                    grant.new_requests[len(traces):], preparations[len(traces):], strict=True):
                traces.append(AttemptContactTrace(q.request.question_id,
                    claim.new_request_ref, True, True, True, False, False, False,
                    request, preparation))
                observed.append(claim.reservation)
            try:
                custody = _admit(verified, FamilyPaperExecutionOutcome(
                    'INDETERMINATE', tuple(completed), None, None,
                    tuple(traces), tuple(observed), issued),
                    self._questions, self._maximum)
            except Exception:
                custody = None
            return GradedRetryOutcome(GradedRetryState.UNKNOWN, physical,
                                      custody, authorization=grant)
        try:
            purpose = ScoredPaperPurpose('RETRY', retry_grant=grant,
                                          retry_original=physical.original)
            cas = self._cas._commit_owned_custody(custody,
                                                  predecessor=None, purpose=purpose)
            self._cas._track_issued_outcome(cas)
        except Exception:
            return GradedRetryOutcome(GradedRetryState.UNKNOWN, physical,
                                      custody, authorization=grant)
        return GradedRetryOutcome(
            GradedRetryState.CAS_ACKNOWLEDGED if cas.state is PaperCASState.COMMITTED
            else GradedRetryState.CAS_BLOCKED if cas.state is PaperCASState.BLOCKED
            else GradedRetryState.UNKNOWN, physical, custody, cas, grant)
