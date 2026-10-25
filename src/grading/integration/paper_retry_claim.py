"""Bind an approved retry to an original attempt before any new physical claim.

This is the engine-owned atomic-claim *boundary*, not an implementation of
institutional operation-transition authorization, distributed CAS, scoring or publication.
Unlike a normal regrade, an absent original attempt may have no result_ref.
It must NEVER be passed off as a completed-predecessor regrade.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.contracts.job_state import GradingJobState
from grading.contracts.paper_aggregation import ResolvedPaperScoringAuthority
from grading.integration.academic_claim_binding import (
    AcademicClaimPreparation, AcademicallyBoundClaim, AcademicClaimIntent,
    QualifiedAcademicClaimBindingStore, academic_intent, validate_preparation,
    validate_bound_claim,
)
from grading.integration.attempt_authority import (
    AttemptClaimRequest, AttemptClaimDisposition, _request_snapshot,
)
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy, _snapshot_owned
from grading.integration.retry_purpose_authorization import RetryPurposeTransitionPolicy, retry_purpose_admitted
from grading.integration.execution_eligibility import _capture, _id
from grading.integration.evaluator_invocation import AttemptReservation, _reservation_copy
from grading.integration.paper_execution_correlation import IssuedPaperExecutionRelation, _plan
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.paper_retry_recovery import (
    ProductionPaperOriginalRecovery, OriginalPaperRecovery,
    OriginalPaperRecoveryState,
)
from grading.integration.whole_paper_attempt_custody import PaperRecoveryState


class RetryClaimState(str, Enum):
    CLAIMED = 'CLAIMED'  # actual backend-asserted physical attempt claim; NOT a score
    PRE_EFFECT_BLOCKED = 'PRE_EFFECT_BLOCKED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedPaperRetry:
    """Fixed original/new run legal operation-transition decision, never self-issued by this consumer."""
    original_run_id: str
    new_plan: AdmittedPaperPlan
    issued_paper: IssuedPaperExecutionRelation
    scoring: ResolvedPaperScoringAuthority
    original_request_refs: tuple[str | None, ...]
    new_requests: tuple[AttemptClaimRequest, ...]
    approval_ref: str
    policy_id: str
    policy_version: int
    source_state: GradingJobState
    target_state: GradingJobState
    purpose_policy_id: str | None = None
    purpose_policy_version: int | None = None


@dataclass(frozen=True, slots=True, repr=False)
class AtomicRetryClaimReceipt:
    """Adapter assertion of ONE original-to-new atomic claim, not durable proof."""
    original_request_ref: str | None
    new_request_ref: str
    approval_ref: str
    transaction_ref: str
    bound_claim: AcademicallyBoundClaim


@dataclass(frozen=True, slots=True, repr=False)
class RetryQuestionObservation:
    question_id: str
    original_request_ref: str | None
    new_request_ref: str
    reservation: AttemptReservation
    transaction_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class PaperRetryClaimObservation:
    state: RetryClaimState
    claimed: tuple[RetryQuestionObservation, ...] = ()
    original: OriginalPaperRecovery | None = None

    @property
    def authorizes_retry(self) -> bool:
        return False  # a past successful claim cannot be replayed as a new grant

    @property
    def authorizes_publication(self) -> bool:
        return False


class QualifiedPaperRetryAuthority(Protocol):
    """Authentic stage-specific legal operation-transition decision, for this recovered original/new run."""
    def resolve_authorized_retry(self, *, original: OriginalPaperRecovery,
                                 new_plan: AdmittedPaperPlan) -> AuthorizedPaperRetry: ...


class AtomicAcademicRetryClaimStore(Protocol):
    """Must atomically compare original physical attempt claim absence, legal transition AND bound prep.

    Before issuing FRESH, recheck every original operation under one qualified
    linearizable original-to-new transition/lease; revalidate both generic legal operation transition
    and RETRY_CLAIM purpose-policy IDs/versions at the physical-claim instant. Reject stale authorization,
    contradictory late original reservations, different successor runs and
    expired/revoked academic revisions. The same logical retry cannot claim
    twice across workers. This adapter guarantee REQUIRES live qualification.
    """
    def claim_authorized_retry(self, *, original: OriginalPaperRecovery,
                               authorization: AuthorizedPaperRetry,
                               question_id: str,
                               preparation: AcademicClaimPreparation) -> AtomicRetryClaimReceipt: ...


class ProductionAuthorizedPaperRetry:
    """Genuine physical attempt claim bound retry effects; never grades or calls paper-CAS itself.

    The first claim is possible ONLY after original recovery, complete academic
    preparation and qualified operation-transition authorization. Partial claims are retained
    as original facts even when a later question's outcome becomes UNKNOWN.
    """
    __slots__ = ('_recovery', '_authorize', '_prepare', '_claim', '_policy', '_max', '_questions', '_gate', '_started', '_last_material', '_retry_purpose', '_joint_effect', '_runtime_executor')

    def __init__(self, *, recovery: ProductionPaperOriginalRecovery,
                 retry_authority: QualifiedPaperRetryAuthority,
                 academic_store: QualifiedAcademicClaimBindingStore,
                 atomic_retry_store: AtomicAcademicRetryClaimStore,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int, max_questions: int,
                 retry_purpose_policy: RetryPurposeTransitionPolicy | None = None,
                 joint_effect: object = None, runtime_executor: object = None) -> None:
        if (type(recovery) is not ProductionPaperOriginalRecovery
                or type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000):
            raise ValueError('authorized retry requires finite original recovery and a versioned lifecycle authorization policy.')
        object.__setattr__(self, '_recovery', recovery)
        object.__setattr__(self, '_authorize', _capture(retry_authority,
            'resolve_authorized_retry', ('original', 'new_plan')))
        object.__setattr__(self, '_prepare', _capture(academic_store,
            'prepare_original_binding', ('intent',)))
        object.__setattr__(self, '_claim', (None if joint_effect is not None else
            _capture(atomic_retry_store, 'claim_authorized_retry',
                     ('original','authorization','question_id','preparation'))))
        # Independently installed institutional purpose policy; None blocks retry.
        if joint_effect is not None:
            from grading.integration.joint_effect_authority import JointEffectAdmission
            from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
            from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
            if (type(joint_effect) is not JointEffectAdmission
                    or type(runtime_executor) not in (
                        ProductionWholePaperChoiceExecutor, ProductionWholePaperFamilyExecutor)):

                raise ValueError('RETRY joint effects require the installed graded runtime owner.')
        elif runtime_executor is not None:
            raise ValueError('Standalone runtime source is not a retry authority.')
        object.__setattr__(self, '_joint_effect', joint_effect)
        object.__setattr__(self, '_runtime_executor', runtime_executor)
        object.__setattr__(self, '_retry_purpose', retry_purpose_policy)
        object.__setattr__(self, '_policy', legal_policy)
        object.__setattr__(self, '_max', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        object.__setattr__(self, '_gate', Lock())
        object.__setattr__(self, '_started', False)
        object.__setattr__(self, '_last_material', None)

    def __setattr__(self, name, value):
        raise AttributeError('authorized retry authority installation is fixed.')

    def claim(self, *, plan: AdmittedPaperPlan,
              _pre_effect_grade_check=None) -> PaperRetryClaimObservation:
        """Claims exactly the approved new run, never silently retries after UNKNOWN."""
        if not self._gate.acquire(blocking=False):
            return PaperRetryClaimObservation(RetryClaimState.UNKNOWN)
        try:
            # A failed preparation or lost claim response may already have
            # persisted an effect. Never contact the same installed operation
            # twice; a new worker must use the qualified backend idempotency CAS.
            if self._started:
                return PaperRetryClaimObservation(RetryClaimState.UNKNOWN)
            try:
                verified = _plan(plan, self._questions, self._max)
                before_plan = _snapshot_owned(verified)
            except Exception:
                return PaperRetryClaimObservation(RetryClaimState.PRE_EFFECT_BLOCKED)
            original = self._recovery.reconcile()  # fixed-source, read-only
            if original.state is not OriginalPaperRecoveryState.ABSENCE_REPORTED:
                return PaperRetryClaimObservation(RetryClaimState.UNKNOWN, original=original)
            try:
                if original.paper is None or original.details is None:
                    raise ValueError('Original observation missing.')
                previous = _plan(original.paper.plan, self._questions, self._max)
                new = verified.request; old = previous.request
                if (type(original.details.questions) is not tuple
                        or len(original.details.questions) != len(previous.questions)
                        or len(previous.questions) != len(verified.questions)
                        or any((a.request.question_id, a.family,
                                a.source_artifact_ref, a.source_revision,
                                a.evidence_scope_ref, a.answer_region_ref,
                                a.provenance_ref) !=
                               (b.request.question_id, b.family,
                                b.source_artifact_ref, b.source_revision,
                                b.evidence_scope_ref, b.answer_region_ref,
                                b.provenance_ref)
                               for a,b in zip(previous.questions, verified.questions, strict=True))
                        or any(getattr(old, name) != getattr(new, name) for name in (
                            'tenant_ref','session_ref','submission_ref','exam_ref',
                            'paper_ref','set_ref','grading_spec_ref'))
                        or old.grading_run_id == new.grading_run_id):
                    raise ValueError('Retry scope does not preserve the original academic subject.')
                for old_q, read_q in zip(original.paper.questions,
                                         original.details.questions, strict=True):
                    if (old_q.question_id != read_q.question_id
                            or read_q.state not in (PaperRecoveryState.NOT_RESERVED,
                                                     PaperRecoveryState.NOT_CONTACTED)
                            or (read_q.state is PaperRecoveryState.NOT_CONTACTED
                                and old_q.f25_call_started)):
                        raise ValueError('Original grading-attempt outcome is not confirmed absent.')
                baseline = _snapshot_owned(original)
                grant = self._authorize(original=original, new_plan=verified)
                if (_snapshot_owned(original) != baseline or _snapshot_owned(verified) != before_plan
                        or _plan(plan, self._questions, self._max) != verified
                        or type(grant) is not AuthorizedPaperRetry
                        or _plan(grant.new_plan, self._questions, self._max) != verified
                        or _id(grant.original_run_id, self._max) != old.grading_run_id
                        or _id(grant.approval_ref, self._max) == ''
                        or _id(grant.policy_id, self._max) != self._policy.policy_id
                        or type(grant.policy_version) is not int
                        or grant.policy_version != self._policy.policy_version
                        or type(grant.source_state) is not GradingJobState
                        or type(grant.target_state) is not GradingJobState
                        or not retry_purpose_admitted(purpose_policy=self._retry_purpose,
                            legal_policy=self._policy, grant=grant, maximum=self._max)
                        or type(grant.original_request_refs) is not tuple
                        or len(grant.original_request_refs) != len(previous.questions)
                        or type(grant.new_requests) is not tuple
                        or len(grant.new_requests) != len(verified.questions)):
                    raise ValueError('lifecycle authorization retry grant is not scoped to original/new paper.')
                from grading.integration.paper_execution_correlation import _relation
                issued = _relation(grant.issued_paper, self._questions, self._max)
                if (issued.request != verified.request
                        or issued.actor_ref != verified.actor_ref
                        or issued.paper_ref != verified.request.paper_ref
                        or issued.set_ref != verified.request.set_ref
                        or any(getattr(issued, name) != getattr(verified, name)
                               for name in ('approval_ref', 'approval_revision',
                                            'selection_decision_ref', 'selection_revision',
                                            'source_revision', 'readiness_revision'))
                        or len(issued.questions) != len(verified.questions)
                        or any((aq.question_id, aq.family, aq.source_artifact_ref,
                                aq.evidence_scope_ref, aq.answer_region_ref,
                                aq.source_revision, aq.provenance_ref)
                               != (pq.request.question_id,pq.family,pq.source_artifact_ref,
                                   pq.evidence_scope_ref,pq.answer_region_ref,
                                   pq.source_revision,pq.provenance_ref)
                               for aq,pq in zip(issued.questions,verified.questions,strict=True))):
                    raise ValueError('Retry academic issuer not bound to approved new paper.')
                from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
                is_family = type(self._runtime_executor) is ProductionWholePaperFamilyExecutor
                family_inventory = tuple(q.family for q in verified.questions)
                if is_family:
                    if not set(family_inventory).issubset({'DIRECT', 'NUMERIC'}):
                        raise ValueError('Unsupported RETRY family inventory.')
                elif any(family != 'CHOICE' for family in family_inventory):
                    raise ValueError('CHOICE retry runtime cannot execute non-CHOICE paper.')
                # Validate every new request before any preparation/claim.
                seen = set()
                original_refs = set()
                intents = []
                for original_q, read_q, new_q, req_ref, new_req in zip(
                    original.paper.questions, original.details.questions,
                    verified.questions, grant.original_request_refs,
                    grant.new_requests, strict=True):
                    expected_original = original_q.request_ref
                    if (req_ref != expected_original or read_q.request_ref != expected_original
                            and read_q.state is not PaperRecoveryState.NOT_CONTACTED):
                        raise ValueError('lifecycle authorization retry grant changed original grading-attempt custody.')
                    if req_ref is not None:
                        original_refs.add(_id(req_ref, self._max))
                    snap = _request_snapshot(new_req, self._max)
                    from grading.integration.whole_paper_attempt_custody import _matches_paper
                    if (snap[0].question_id != new_q.request.question_id
                            or snap[2] != new_q.family
                            or not _matches_paper(snap[0], verified, new_q, self._max)
                            or snap[1] in seen or snap[8] is not None or snap[9] is not None):
                        raise ValueError('New grading-attempt request is not an original authorized retry.')
                    seen.add(snap[1])
                    intents.append(academic_intent(new_req, issued, grant.scoring,
                        self._max, self._questions))
                if seen & original_refs:
                    raise ValueError('Retry cannot reuse original grading-attempt request.')
                grant_snapshot = _snapshot_owned(grant)
                if _pre_effect_grade_check is not None:
                    # Optional internal genuine-evaluator preflight runs BEFORE
                    # the first academic preparation or physical attempt effect.
                    # Ordinary claim() does not use the grading continuation.
                    if (_pre_effect_grade_check(grant) is not True
                            or _snapshot_owned(grant) != grant_snapshot
                            or _snapshot_owned(original) != baseline
                            or _plan(plan,self._questions,self._max) != verified):
                        raise ValueError('Approved retry differs from installed grading runtime.')
            except Exception:
                return PaperRetryClaimObservation(RetryClaimState.PRE_EFFECT_BLOCKED,
                                                   original=original)
            object.__setattr__(self, '_started', True)  # before first durable preparation
            claimed = []
            known_preparations = []
            for intent in intents:
                try:
                    # The current installed grader/issuer can change after an
                    # earlier question's physical claim. Do not issue another
                    # academic preparation or physical attempt claim on a stale preflight.
                    if (_pre_effect_grade_check is not None
                            and _pre_effect_grade_check(grant) is not True):
                        raise ValueError('Current grading authority changed before retry effect.')
                    prepared = self._prepare(intent=intent)
                    validate_preparation(prepared, intent, self._max)
                    if (_snapshot_owned(grant) != grant_snapshot
                            or _snapshot_owned(original) != baseline
                            or _snapshot_owned(verified) != before_plan
                            or (_pre_effect_grade_check is not None
                                and _pre_effect_grade_check(grant) is not True)):
                        raise ValueError('lifecycle approval, original source, or installed grader changed during preparation.')
                except Exception:
                    return PaperRetryClaimObservation(RetryClaimState.UNKNOWN, tuple(claimed), original)
                try:
                    # The only physical claim. Backend MUST enforce original
                    # absence and legal operation transition+academic validity atomically at contact.
                    if self._joint_effect is not None:
                        from grading.integration.joint_effect_authority import (
                            JointAuthoritySnapshot, ConditionalEffectClaim,
                            GradingEffectKind, EffectDecision,
                        )
                        executor = self._runtime_executor
                        selected = next(q for q in verified.questions
                                        if q.request.question_id == intent.question_id)
                        relation = next(q for q in issued.questions
                                        if q.question_id == intent.question_id)
                        if is_family:
                            from grading.integration.paper_family_evaluation import _admitted_values
                            full = executor._current(verified, verified, issued)
                            index = next(i for i, question in enumerate(verified.questions)
                                         if question.request.question_id == intent.question_id)
                            op = full.operations[index]
                            scope = full.scopes[index]
                            runtime = executor._binder.bind_family(
                                scope=scope, family=relation.family,
                                context_policy=op.authority.context_policy)
                            approval = runtime.approved_runtime
                            # The exact installed evaluator selection capability must be the
                            # authorized executable that physical attempt claim will use.
                            metadata = runtime.eligibility.selection.selected_capability_ref.evaluator_metadata
                            from grading.integration.paper_family_evaluation import DirectQuestionEvaluation
                            from grading.contracts.numeric_evaluation import (
                                DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION)
                            if relation.family == 'DIRECT':
                                if (type(op) is not DirectQuestionEvaluation
                                        or _admitted_values(op.evaluator._evaluator_metadata) !=
                                           _admitted_values(metadata)):
                                    raise ValueError('Foreign DIRECT RETRY installation.')
                            elif (metadata.evaluator_id, metadata.version) != (
                                DETERMINISTIC_NUMERIC_EVALUATOR_ID,
                                DETERMINISTIC_NUMERIC_EVALUATOR_VERSION):
                                raise ValueError('Foreign NUMERIC RETRY installation.')
                        else:
                            _, runtime_snapshot, _ = executor._prepared(
                                selected.request, verified, relation)
                            approval = runtime_snapshot[7]
                        joint = ConditionalEffectClaim(
                            JointAuthoritySnapshot(intent, approval,
                                                   self._max, self._questions),
                            prepared, GradingEffectKind.RETRY_F25, original, grant)
                        response = self._joint_effect.claim(request=joint)
                        if response.state is not EffectDecision.COMMITTED:
                            raise ValueError('RETRY joint effect was rejected or is uncertain.')
                        answer = response.retry_receipt
                    else:
                        answer = self._claim(original=original, authorization=grant,
                            question_id=intent.question_id, preparation=prepared)
                    if (type(answer) is not AtomicRetryClaimReceipt
                            or answer.original_request_ref != grant.original_request_refs[len(claimed)]
                            or answer.new_request_ref != intent.original_request.request_ref
                            or answer.approval_ref != grant.approval_ref
                            or not isinstance(answer.transaction_ref, str)):
                        raise ValueError('Retry claim receipt mismatched original identity.')
                    _id(answer.transaction_ref, self._max)
                    claim = validate_bound_claim(answer.bound_claim, prepared, self._max)
                    if claim.disposition is not AttemptClaimDisposition.FRESH:
                        raise ValueError('No new fresh retry claim.')
                    from grading.integration.evaluator_invocation import AttemptReservation
                    if type(claim.reservation) is not AttemptReservation:
                        raise ValueError('Missing bound retry physical claim.')
                    original_scope = _request_snapshot(intent.original_request,self._max)
                    expected = AttemptReservation(original_scope[0], '', '', *original_scope[2:8],
                        request_ref=original_scope[1])
                    reservation = _reservation_copy(claim.reservation, expected=expected,
                                                    maximum=self._max)
                    if (_snapshot_owned(grant) != grant_snapshot
                            or _snapshot_owned(original) != baseline
                            or _snapshot_owned(verified) != before_plan
                            or any(reservation.attempt_id == x.reservation.attempt_id
                                   or reservation.reservation_ref == x.reservation.reservation_ref
                                   or answer.transaction_ref == x.transaction_ref for x in claimed)):
                        raise ValueError('Claim changed original identity or duplicated an effect.')
                    known_preparations.append(prepared)
                    claimed.append(RetryQuestionObservation(intent.question_id,
                        answer.original_request_ref, answer.new_request_ref,
                        reservation, answer.transaction_ref))
                except Exception:
                    # After possible claim contact, even a malformed reply or
                    # stale version may indicate a committed physical effect.
                    return PaperRetryClaimObservation(RetryClaimState.UNKNOWN, tuple(claimed), original)
            observation = PaperRetryClaimObservation(RetryClaimState.CLAIMED, tuple(claimed), original)
            # Private provenance is produced ONLY by this same completed real
            # physical claim span; public observations confer no bearer right.
            object.__setattr__(self, '_last_material',
                               (observation, grant, tuple(known_preparations), grant_snapshot))
            return observation
        finally:
            self._gate.release()
