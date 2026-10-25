"""Commit paper-scoped candidate scores, state and audit evidence conditionally.

A local score and observed physical attempt claim permits are NOT audit commitments. A qualified
external store must atomically compare its original paper/ledger revision and
persist the complete candidate, state and audit. No official publication or
retry permission is conferred. The physical attempt claim pre-claim durable revision/lease gate is
separately required before production use; this port does not fake it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from threading import Lock
from weakref import ref
from typing import Protocol

from grading.contracts.job_state import GradingJobState
from grading.execution import GradingExecutionResult, QuestionExecutionRecord
from grading.contracts.result import PaperScoreResult, QuestionScoreResult, ScoreStage, RuleType
from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.contracts.paper_aggregation import (
    _validate_grading_spec_ref, _validate_rubric_ref, _validate_scoring_policy_ref,
)
from grading.verification.evidence import VerifiedCriterionJudgments
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import exact_compare, exact_sum, exact_minimum, exact_subtract
from grading.integration.attempt_authority import AttemptClaimRequest, _request_snapshot
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy, _snapshot_owned
from grading.integration.attempt_history import _private_constructor
from grading.integration.execution_eligibility import _capture, _id
from grading.integration.paper_execution_correlation import (
    IssuedPaperExecutionRelation, _relation,
)
from grading.integration.paper_readiness_admission import AdmittedPaperPlan, PaperAdmissionRequest, _request
from grading.integration.paper_execution_correlation import _plan
from grading.integration.whole_paper_attempt_custody import (
    ProductionPaperAttemptCustody, PaperAttemptCustody, _admit,
)


def _make_paper_cas_guard():
    """Invocation-owned instance exclusion, including callback-induced reentry.

    Active tokens live in this private closure rather than on a callback-
    reachable ``threading.Lock``. This does not sandbox hostile Python or
    replace backend transaction atomicity across workers/processes.
    """
    mutex = Lock()
    active: dict[int, object] = {}

    def enter(owner):
        identity = id(owner)
        with mutex:
            if identity in active:
                raise ValueError('Nested paper CAS operation or concurrent call is forbidden.')
            token = object()
            active[identity] = token
            return token

    def leave(owner, token):
        identity = id(owner)
        with mutex:
            if active.get(identity) is not token:
                raise RuntimeError('Paper CAS operation lease ownership mismatch.')
            del active[identity]

    return enter, leave


_enter_cas, _leave_cas = _make_paper_cas_guard()


class PaperCASState(str, Enum):
    NOT_ELIGIBLE = 'NOT_ELIGIBLE'
    COMMITTED = 'COMMITTED'
    BLOCKED = 'BLOCKED'
    UNKNOWN = 'UNKNOWN'


class PaperCASDisposition(str, Enum):
    COMMITTED = 'COMMITTED'
    CONFLICT = 'CONFLICT'
    STALE = 'STALE'
    INDETERMINATE = 'INDETERMINATE'


@dataclass(frozen=True, slots=True, repr=False)
class PaperCASIntent:
    """Non-bearer exact original academic and physical attempt relationship."""
    plan: AdmittedPaperPlan
    issued: IssuedPaperExecutionRelation
    question_claims: tuple[tuple[str, str, str, str], ...]  # question, request, attempt, reservation
    original_claim_requests: tuple[AttemptClaimRequest, ...]
    result: GradingExecutionResult  # the exact nonpublishing scored candidate


@dataclass(frozen=True, slots=True, repr=False)
class PaperCASTransaction:
    """Issued by an installed qualified authority, not generated from a score."""
    intent: PaperCASIntent
    request_ref: str
    event_ref: str
    result_ref: str
    expected_ledger_revision: str
    source_state: GradingJobState
    target_state: GradingJobState
    f57_policy_id: str
    f57_policy_version: int
    f57_approval_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class PaperCASReceipt:
    """Backend-reported *whole-paper* atomic acknowledgment, not one-question audit."""
    transaction: PaperCASTransaction
    commit_ref: str
    committed_ledger_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class PaperCASDecision:
    transaction: PaperCASTransaction
    disposition: PaperCASDisposition
    receipt: PaperCASReceipt | None


@dataclass(frozen=True, slots=True, repr=False)
class PaperCASRecovery:
    transaction: PaperCASTransaction
    disposition: PaperCASDisposition
    receipt: PaperCASReceipt | None


@dataclass(frozen=True, slots=True, repr=False, weakref_slot=True)
class PaperCASOutcome:
    state: PaperCASState
    custody: PaperAttemptCustody
    transaction: PaperCASTransaction | None = None
    receipt: PaperCASReceipt | None = None
    academic_binding_verified: bool = False  # local validation ONLY; not authenticated history

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


@dataclass(frozen=True, slots=True, repr=False)
class ScoredPaperPurpose:
    """Original source-issued legal operation transition *operation* purpose, not a CAS approval.

    The independently issued scored-CAS transition may legitimately have a
    different approval reference. A qualified CAS owner must check the
    authenticated relation and current state of BOTH inside its write boundary.
    """
    kind: str
    permission: object = None
    retry_grant: object = None
    retry_original: object = None


def _admit_scored_purpose(purpose: object, intent: PaperCASIntent,
                          predecessor: PaperCASTransaction | None,
                          transaction: PaperCASTransaction,
                          maximum: int, questions: int) -> ScoredPaperPurpose:
    from grading.integration.paper_lifecycle import PaperLifecyclePermission, PaperLifecycleKind
    from grading.integration.paper_retry_claim import AuthorizedPaperRetry
    from grading.integration.paper_retry_recovery import OriginalPaperRecovery, OriginalPaperRecoveryState
    from grading.integration.whole_paper_attempt_custody import (
        PaperAttemptCustody, PaperAttemptClaimRecovery, PaperRecoveryState,
    )
    from grading.integration.paper_execution_correlation import _plan
    if type(purpose) is not ScoredPaperPurpose or type(purpose.kind) is not str:
        raise ValueError('Exact source-issued operation purpose required.')
    if purpose.kind in ('FIRST', 'REGRADE'):
        grant = purpose.permission
        required = (PaperLifecycleKind.FIRST if purpose.kind == 'FIRST'
                    else PaperLifecycleKind.REGRADE)
        if (type(grant) is not PaperLifecyclePermission
                or grant.kind is not required
                or purpose.retry_grant is not None or purpose.retry_original is not None
                or _plan(grant.plan, questions, maximum) != intent.plan
                or type(grant.policy_version) is not int
                or type(grant.source_state) is not GradingJobState
                or type(grant.target_state) is not GradingJobState):
            raise ValueError('Wrong lifecycle source for scored operation.')
        for value in (grant.approval_ref, grant.policy_id):
            _id(value, maximum)
        if purpose.kind == 'FIRST':
            if (predecessor is not None or grant.predecessor is not None
                    or grant.predecessor_custody is not None
                    or any(r.predecessor_result_ref is not None
                           or r.regrade_approval_ref is not None
                           for r in intent.original_claim_requests)):
                raise ValueError('FIRST cannot carry a scored predecessor.')
        else:
            if (type(predecessor) is not PaperCASTransaction
                    or type(grant.predecessor) is not PaperCASTransaction
                    or not _same_validated_value(grant.predecessor, predecessor)
                    or any(r.predecessor_result_ref != predecessor.result_ref
                           or r.regrade_approval_ref != grant.approval_ref
                           for r in intent.original_claim_requests)):
                raise ValueError('REGRADE source does not authorize original predecessor.')
    elif purpose.kind == 'RETRY':
        grant, original = purpose.retry_grant, purpose.retry_original
        if (purpose.permission is not None
                or predecessor is not None
                or type(grant) is not AuthorizedPaperRetry
                or type(original) is not OriginalPaperRecovery
                or _plan(grant.new_plan, questions, maximum) != intent.plan
                or type(grant.new_requests) is not tuple
                or len(grant.new_requests) != len(intent.original_claim_requests)
                or any(_request_snapshot(a, maximum) != _request_snapshot(b, maximum)
                       for a, b in zip(grant.new_requests,
                                       intent.original_claim_requests, strict=True))
                or type(grant.policy_version) is not int
                or type(grant.source_state) is not GradingJobState
                or type(grant.target_state) is not GradingJobState
                or any(r.predecessor_result_ref is not None
                       or r.regrade_approval_ref is not None
                       for r in intent.original_claim_requests)):
            raise ValueError('RETRY must bind original absence and new source-issued purpose.')
        # The original absence must remain bound to this exact successor.
        # This is local relation validation, never a replacement for the
        # effect owner's authoritative original-absence compare-and-write.
        if (original.state is not OriginalPaperRecoveryState.ABSENCE_REPORTED
                or type(original.paper) is not PaperAttemptCustody
                or type(original.details) is not PaperAttemptClaimRecovery
                or type(original.details.questions) is not tuple
                or type(grant.original_request_refs) is not tuple):
            raise ValueError('RETRY lacks a qualified original-absence observation.')
        previous = _plan(original.paper.plan, questions, maximum)
        if (len(original.paper.questions) != len(original.details.questions)
                or len(previous.questions) != len(intent.original_claim_requests)
                or len(grant.original_request_refs) != len(previous.questions)
                or _id(grant.original_run_id, maximum) != previous.request.grading_run_id
                or previous.request.grading_run_id == intent.plan.request.grading_run_id
                or any(getattr(previous.request, field) != getattr(intent.plan.request, field)
                       for field in ('tenant_ref', 'session_ref', 'submission_ref',
                                     'exam_ref', 'paper_ref', 'set_ref', 'grading_spec_ref'))):
            raise ValueError('RETRY original source does not match successor paper.')
        for prior, observed, question, ref in zip(
                original.paper.questions, original.details.questions,
                previous.questions, grant.original_request_refs, strict=True):
            if (prior.question_id != question.request.question_id
                    or observed.question_id != prior.question_id
                    or ref != prior.request_ref
                    or type(observed.state) is not PaperRecoveryState
                    or observed.state not in (PaperRecoveryState.NOT_RESERVED,
                                              PaperRecoveryState.NOT_CONTACTED)
                    or (observed.state is PaperRecoveryState.NOT_CONTACTED
                        and prior.f25_call_started)
                    or (observed.state is not PaperRecoveryState.NOT_CONTACTED
                        and observed.request_ref != prior.request_ref)):
                raise ValueError('RETRY cannot reuse a contradictory original grading-attempt record.')
        _id(grant.approval_ref, maximum)
        _id(grant.policy_id, maximum)
    else:
        raise ValueError('Unrecognized scored-paper purpose.')
    # This is NOT an inference that the operation grant is the separately
    # issued scored-CAS transition approval. The atomic adapter qualifies
    # their true source-issued relation and current authorization.
    return purpose


class QualifiedPaperCASTransactionIssuer(Protocol):
    def identify_paper_transaction(self, *, intent: PaperCASIntent) -> PaperCASTransaction: ...


class QualifiedOriginalPaperCASSource(Protocol):
    """Authenticated read-only source of the ORIGINAL paper CAS request.

    Must be durable and permit reads only for the exact authorized paper and
    request. Caller-supplied outcomes are never historical credentials.
    """
    def resolve_original_paper_transaction(self, *, plan: AdmittedPaperPlan,
                                           request_ref: str) -> PaperCASTransaction: ...


class AtomicWholePaperResultStateAuditStore(Protocol):
    """Must durably CAS one *entire* result/state/audit transaction or return unknown."""
    def commit_whole_paper(self, *, transaction: PaperCASTransaction,
                           custody: PaperAttemptCustody) -> PaperCASDecision: ...
    def reconcile_whole_paper(self, *, transaction: PaperCASTransaction) -> PaperCASRecovery: ...


def _approved_intent(custody: PaperAttemptCustody, max_questions: int,
                     maximum: int) -> PaperCASIntent:
    # Re-admit whole-paper custody before ANY external CAS contact.
    if type(custody) is not PaperAttemptCustody:
        raise ValueError('Not a paper custody record.')
    admitted = _admit(custody.plan, custody.outcome, max_questions, maximum)
    if (admitted != custody or admitted.outcome.state != 'COMPLETE'
            or admitted.outcome.result is None
            or any(q.claim_conflict or not q.s1_verified or not q.reservation_validated
                   or q.reservation is None or q.request_ref is None
                   or q.original_f25_request is None for q in admitted.questions)):
        raise ValueError('Paper has unverified or incomplete attempts.')
    issued = _relation(admitted.outcome.issued_paper, max_questions, maximum)
    if (issued.request != admitted.plan.request
            or issued.actor_ref != admitted.plan.actor_ref
            or issued.approval_ref != admitted.plan.approval_ref
            or issued.approval_revision != admitted.plan.approval_revision
            or issued.selection_decision_ref != admitted.plan.selection_decision_ref
            or issued.selection_revision != admitted.plan.selection_revision
            or issued.source_revision != admitted.plan.source_revision
            or issued.readiness_revision != admitted.plan.readiness_revision
            or tuple(q.question_id for q in issued.questions)
               != tuple(q.question_id for q in admitted.questions)
            or any((r.family, r.source_artifact_ref, r.evidence_scope_ref,
                    r.answer_region_ref, r.source_revision, r.provenance_ref)
                != (q.family, q.source_artifact_ref, q.evidence_scope_ref,
                    q.answer_region_ref, q.source_revision, q.provenance_ref)
                for r, q in zip(issued.questions, admitted.plan.questions, strict=True))):
        raise ValueError('Academic issuance contradicts executed paper.')
    claims = []
    originals = []
    for q in admitted.questions:
        r = q.reservation
        if (q.original_f25_request.request_ref != q.request_ref
                or q.original_f25_request.request_ref != r.request_ref
                or q.original_f25_request.scope != r.scope):
            raise ValueError('Original claim binding differs from verified attempt.')
        original = q.original_f25_request
        _request_snapshot(original, maximum)
        if (original.runtime_id != r.runtime_id
                or original.runtime_version != r.runtime_version
                or original.implementation_ref != r.implementation_ref
                or original.eligibility_policy_id != r.eligibility_policy_id
                or original.eligibility_policy_version != r.eligibility_policy_version
                or original.predecessor_result_ref != r.predecessor_result_ref
                or original.regrade_approval_ref != r.regrade_approval_ref):
            raise ValueError('Pre-claim runtime, policy or regrade identity changed.')
        claims.append((q.question_id, q.request_ref, r.attempt_id, r.reservation_ref))
        originals.append(original)
    if any(len({claim[i] for claim in claims}) != len(claims) for i in (1, 2, 3)):
        raise ValueError('Duplicate physical paper identity.')
    return PaperCASIntent(admitted.plan, issued, tuple(claims), tuple(originals),
                          admitted.outcome.result)


def _same_validated_value(left: object, right: object) -> bool:
    # Allow backend records reconstructed after transport/restart, but reject
    # foreign Python equality hooks before comparing their values.
    _snapshot_owned(left)
    _snapshot_owned(right)
    return left == right


def _validate_transaction(transaction: object, intent: PaperCASIntent,
                          allowed: LegalGradingTransitionPolicy, maximum: int) -> None:
    if (type(transaction) is not PaperCASTransaction
            or type(transaction.intent) is not PaperCASIntent
            or not _same_validated_value(transaction.intent, intent)):
        raise ValueError('Paper transaction has foreign academic or attempt identity.')
    for name in ('request_ref', 'event_ref', 'result_ref', 'expected_ledger_revision',
                 'f57_policy_id', 'f57_approval_ref'):
        _id(getattr(transaction, name), maximum)
    if (type(transaction.f57_policy_version) is not int
            or transaction.f57_policy_version != allowed.policy_version
            or transaction.f57_policy_id != allowed.policy_id
            or type(transaction.source_state) is not GradingJobState
            or type(transaction.target_state) is not GradingJobState
            or (transaction.source_state, transaction.target_state) not in allowed.allowed_edges):
        raise ValueError('No exact qualified legal transition for paper CAS.')


def _receipt(receipt: object, transaction: PaperCASTransaction, maximum: int) -> PaperCASReceipt:
    if (type(receipt) is not PaperCASReceipt
            or type(receipt.transaction) is not PaperCASTransaction
            or not _same_validated_value(receipt.transaction, transaction)):
        raise ValueError('Receipt is not for the entire original paper CAS.')
    _id(receipt.commit_ref, maximum)
    _id(receipt.committed_ledger_revision, maximum)
    # A CAS that advanced the revision must not claim its *old* revision is current.
    if receipt.committed_ledger_revision == transaction.expected_ledger_revision:
        raise ValueError('Receipt does not identify an advanced ledger revision.')
    return receipt


def _valid_locally_replayable_rule_trace(score: QuestionScoreResult) -> bool:
    """Reconcile recorded reducer effects, not unknown historical rubric policy.

    The original issuer must still authenticate the policy, rubric, and input
    evidence; this validates only relationships fixed by the v1 reducer.
    """
    replace(score)  # Enforce frozen, exact nested result types.
    zero = ScoringDecimal.from_raw('0')
    decisions = score.rule_decisions
    ids = tuple(item.rule_id for item in decisions)
    if (ids != tuple(sorted(ids)) or len(ids) != len(set(ids))
            or any(not rule or rule.strip() != rule for rule in ids)):
        return False
    for decision in decisions:
        replace(decision)
        if ((decision.rule_type is RuleType.DEPENDENCY)
                != (decision.configured_effect is None)):
            return False
        # Frozen policy constructors reject non-positive configured deductions,
        # and require gate/cap ceilings within the question score range,
        # regardless of whether a rule's conditions were triggered.
        if (decision.rule_type is RuleType.DEDUCTION
                and exact_compare(decision.configured_effect, zero) <= 0):
            return False
        if (decision.rule_type in (RuleType.GATE, RuleType.CAP)
                and (exact_compare(decision.configured_effect, score.minimum_score) < 0
                     or exact_compare(decision.configured_effect, score.maximum_score) > 0)):
            return False
    dependency = tuple(d.rule_id for d in decisions
                       if d.rule_type is RuleType.DEPENDENCY and d.triggered)
    blocked = []
    for effect in score.criterion_effects:
        replace(effect)
        blockers = effect.blocking_dependency_rule_ids
        if (blockers != tuple(sorted(set(blockers)))
                or any(not x or x.strip() != x for x in blockers)):
            return False
        blocked.extend(blockers)
        required = (zero if blockers and exact_compare(effect.base_contribution, zero) > 0
                    else effect.base_contribution)
        if exact_compare(effect.effective_contribution, required) != 0:
            return False
    # Every triggered dependency has exactly one configured target in the
    # frozen policy and must be represented by that criterion's blocker list.
    if tuple(sorted(blocked)) != dependency:
        return False

    stages = score.stage_effects
    if len(stages) != 4:
        return False
    stage_rules = ((RuleType.GATE, 0), (RuleType.CAP, 1),
                   (RuleType.DEDUCTION, 2))
    for kind, index in stage_rules:
        stage = stages[index]
        triggered = tuple(d for d in decisions
                          if d.rule_type is kind and d.triggered)
        expected_ids = tuple(d.rule_id for d in triggered)
        if stage.source_rule_ids != expected_ids:
            return False
        if kind is RuleType.DEDUCTION:
            expected_after = (exact_subtract(stage.before, exact_sum(tuple(
                d.configured_effect for d in triggered))) if triggered
                else stage.before)
        else:
            expected_after = stage.before
            for decision in triggered:
                expected_after = exact_minimum(expected_after,
                                               decision.configured_effect)
        if exact_compare(stage.after, expected_after) != 0:
            return False
    rounding = stages[3]
    # Any valid positive-increment rounding maps exact zero to exact zero,
    # regardless of rounding increment or tie-breaking mode.
    # The original rounding increment/mode is not stored here, but any
    # positive-increment nearest rounding has these necessary properties:
    # zero remains zero; a nonzero rounded value keeps the input sign and
    # has magnitude between 2/3 and 2 times the input magnitude. Check exact
    # integer ratios to avoid Decimal context and new scoring arithmetic.
    before_num, before_den = rounding.before.as_decimal().as_integer_ratio()
    after_num, after_den = rounding.after.as_decimal().as_integer_ratio()
    if before_num == 0:
        if after_num != 0:
            return False
    elif after_num != 0:
        if (before_num < 0) != (after_num < 0):
            return False
        scaled_after = abs(after_num) * before_den
        scaled_before = abs(before_num) * after_den
        if not (2 * scaled_before < 3 * scaled_after
                and scaled_after <= 2 * scaled_before):
            return False
    if (len(rounding.source_rule_ids) > 1
            or any(not rule or rule.strip() != rule
                   for rule in rounding.source_rule_ids)
            or any(rule in ids for rule in rounding.source_rule_ids)
            or (not rounding.source_rule_ids
                and exact_compare(rounding.before, rounding.after) != 0)):
        return False
    return True


def _separate_paper_cas_generation(current: PaperCASTransaction,
                                   previous: PaperCASTransaction) -> bool:
    """Local cross-generation contradiction test, not historical authenticity.

    Used both before optional original-source contact (when a retained current
    transaction exists) and against the independently recovered original.
    """
    if any(getattr(current, name) == getattr(previous, name)
           for name in ('request_ref', 'event_ref', 'result_ref')):
        return False
    new_request = current.intent.plan.request
    old_request = previous.intent.plan.request
    if any(getattr(new_request, field) != getattr(old_request, field)
           for field in ('tenant_ref', 'session_ref', 'submission_ref',
                         'exam_ref', 'paper_ref', 'set_ref')):
        return False
    if new_request.grading_run_id == old_request.grading_run_id:
        return False
    old_claims = previous.intent.question_claims
    new_claims = current.intent.question_claims
    return not any({claim[index] for claim in old_claims}
                   & {claim[index] for claim in new_claims}
                   for index in (1, 2, 3))


class ProductionWholePaperCAS:
    """Owns the actual whole-paper execution; never accepts caller-supplied score/receipt.

    whole-paper score commit consumes an installed versioned legal operation transition policy. Qualification of that
    policy, the transaction issuer and backend durability is an external gate.
    The paper lifecycle retry/regrade state machine and governed scored-paper handoff promotion gate are NOT claimed.
    """
    __slots__ = ('_custody', '_issue', '_original', '_commit', '_joint_commit', '_recover', '_allowed', '_max', '_questions', '_issued', '_require_academic', '_purpose_commit')

    @_private_constructor
    def __init__(self, *, custody: ProductionPaperAttemptCustody,
                 issuer: QualifiedPaperCASTransactionIssuer,
                 original_source: QualifiedOriginalPaperCASSource,
                 store: AtomicWholePaperResultStateAuditStore,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int, max_questions: int,
                 require_academic_preclaim: bool = False,
                 joint_scored_store: object = None,
                 purpose_scored_store: object = None):
        if (type(custody) is not ProductionPaperAttemptCustody
                or type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000
                or type(legal_policy.policy_version) is not int or legal_policy.policy_version <= 0
                or type(legal_policy.allowed_edges) is not tuple or not legal_policy.allowed_edges
                or any(type(edge) is not tuple or len(edge) != 2
                       or any(type(st) is not GradingJobState for st in edge)
                       for edge in legal_policy.allowed_edges)):
            raise ValueError('Qualified whole-paper CAS installation required.')
        if type(require_academic_preclaim) is not bool:
            raise ValueError('Exact academic preclaim requirement is needed.')
        _id(legal_policy.policy_id, max_identifier_characters)
        if require_academic_preclaim:
            # Before the first possible physical attempt effect, establish that strict
            # academic-bound claiming is really installed in the executor.
            from grading.integration.attempt_authority import ClaimedAttemptAllocator
            from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
            from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
            executor = custody._executor
            if (type(executor) not in (ProductionWholePaperChoiceExecutor, ProductionWholePaperFamilyExecutor)
                    or type(executor._attempts) is not ClaimedAttemptAllocator
                    or executor._attempts is not custody._attempts
                    or executor._attempts.academic_binding_enabled is not True):
                raise ValueError('Strict paper CAS requires a bound academic grading-attempt allocator.')
        # A conditional physical attempt claim installation may never fall back to a legacy scored
        # CAS writer. Conversely, the conditional scored writer cannot be
        # installed alongside the legacy physical-claim path.
        if joint_scored_store is not None:
            raise ValueError('Purpose-unaware scored CAS is forbidden with conditional grading-attempt.')
        conditional_store = purpose_scored_store
        joint_first = (type(custody) is ProductionPaperAttemptCustody
                       and getattr(custody._executor._attempts, '_joint_effect', None) is not None)
        if (joint_first != (conditional_store is not None)
                or (conditional_store is not None and not require_academic_preclaim)):
            raise ValueError('Joint FIRST attempt reservation and scored CAS must be installed together.')
        joint_write = None
        # Retain the historical attribute for read-only compatibility checks,
        # but never capture or invoke a purpose-unaware conditional positive writer.
        purpose_write = None
        if purpose_scored_store is not None:
            try:
                purpose_write = _capture(purpose_scored_store,
                    'commit_scored_paper_if_authorized',
                    ('transaction', 'custody', 'authorities', 'purpose'))
            except Exception:
                raise ValueError('Exact purpose-aware conditional CAS writer required.') from None
        object.__setattr__(self, '_purpose_commit', purpose_write)
        object.__setattr__(self, '_joint_commit', joint_write)
        object.__setattr__(self, '_require_academic', require_academic_preclaim)
        object.__setattr__(self, '_custody', custody)
        object.__setattr__(self, '_issue', _capture(issuer, 'identify_paper_transaction', ('intent',)))
        object.__setattr__(self, '_original', _capture(original_source,
            'resolve_original_paper_transaction', ('plan','request_ref')))
        object.__setattr__(self, '_commit', (None if conditional_store is not None else
            _capture(store, 'commit_whole_paper', ('transaction','custody'))))
        object.__setattr__(self, '_recover', _capture(store, 'reconcile_whole_paper', ('transaction',)))
        object.__setattr__(self, '_allowed', legal_policy)
        object.__setattr__(self, '_max', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        # Identity-keyed, weakly retained original operation observations. Not
        # durable: process restart needs a qualified source-of-record anchor.
        object.__setattr__(self, '_issued', {})

    def __setattr__(self, name, value):
        raise AttributeError('Installed paper CAS cannot be reconfigured.')

    def __delattr__(self, name):
        raise AttributeError('Installed paper CAS cannot be reconfigured.')

    def execute_and_commit(self, *, plan: AdmittedPaperPlan,
                           predecessor: PaperCASTransaction | None = None,
                           permission: object = None) -> PaperCASOutcome:
        # Explicit source-issued permission must predate the first physical attempt effect.
        if self._purpose_commit is not None and permission is None:
            raise ValueError("Purpose-aware CAS cannot grade without original FIRST/REGRADE authority.")
        lease = _enter_cas(self)
        try:
            outcome = self._execute_and_commit(plan=plan, predecessor=predecessor,
                                               permission=permission)
            self._track_issued_outcome(outcome)
            return outcome
        finally:
            _leave_cas(self, lease)

    def _track_issued_outcome(self, outcome: PaperCASOutcome) -> None:
        """Track this exact in-flight outcome for same-process original CAS reads.

        Only trusted internal producers call this after the actual CAS operation;
        the record is not durable and confers no publication/retry authority.
        """
        if type(outcome) is PaperCASOutcome and type(outcome.transaction) is PaperCASTransaction:
            original = _snapshot_owned(outcome.transaction)
            key = id(outcome)
            issued = self._issued
            issued[key] = (ref(outcome, lambda unused, k=key: issued.pop(k, None)), original,
                           outcome.state, outcome.academic_binding_verified,
                           _snapshot_owned(outcome.custody),
                           None if outcome.receipt is None else _snapshot_owned(outcome.receipt))

    def _execute_and_commit(self, *, plan: AdmittedPaperPlan,
                            predecessor: PaperCASTransaction | None = None,
                            permission: object = None) -> PaperCASOutcome:
        if predecessor is not None and type(predecessor) is not PaperCASTransaction:
            raise ValueError('Original predecessor must have exact CAS transaction type.')
        # The only way to create a candidate is the ACTUAL installed evaluator.
        if self._purpose_commit is not None:
            # Local BEFORE-effect admission is necessary but not sufficient:
            # the installed effect owner must revalidate CURRENT source facts.
            from grading.integration.paper_lifecycle import PaperLifecyclePermission
            if type(permission) is not PaperLifecyclePermission:
                raise ValueError('Source-issued FIRST/REGRADE permission required.')
            from grading.integration.paper_lifecycle import PaperLifecycleKind
            # The qualified legal operation transition port may return a malformed frozen record.
            # Re-admit its nested paper before any Python dataclass equality:
            # an unadmitted field can have side-effectful __eq__.
            _plan(permission.plan, self._questions, self._max)
            if (permission.plan != plan
                    or (predecessor is None) != (permission.predecessor is None)
                    or permission.kind is not (PaperLifecycleKind.FIRST if predecessor is None
                                               else PaperLifecycleKind.REGRADE)
                    or type(permission.policy_id) is not str
                    or permission.policy_id != self._allowed.policy_id
                    or type(permission.policy_version) is not int
                    or permission.policy_version != self._allowed.policy_version
                    or type(permission.source_state) is not GradingJobState
                    or type(permission.target_state) is not GradingJobState
                    or (permission.source_state, permission.target_state)
                       not in self._allowed.allowed_edges):
                raise ValueError('Original lifecycle authorization source/transition contradicts CAS operation.')
        first_owner = None
        attempts = self._custody._attempts
        from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
        family = type(self._custody._executor) is ProductionWholePaperFamilyExecutor
        if family and self._purpose_commit is None:
            raise ValueError('Family CAS requires exact purpose-aware conditional scoring.')
        if self._purpose_commit is not None and predecessor is None and not family:
            # The family executor owns its original FIRST physical-purpose lease.
            first_owner = attempts.begin_authorized_first(plan=plan, permission=permission)
        try:
            custody = self._custody.execute_and_capture(plan=plan, permission=permission) if family else self._custody.execute_and_capture(plan=plan)
            purpose = (None if permission is None else ScoredPaperPurpose(
                'FIRST' if predecessor is None else 'REGRADE', permission=permission))
            return self._commit_owned_custody(custody, predecessor=predecessor, purpose=purpose)
        finally:
            if first_owner is not None:
                attempts.finish_authorized_first(token=first_owner)

    def _commit_owned_custody(self, custody: PaperAttemptCustody,
                              predecessor: PaperCASTransaction | None = None,
                              purpose: ScoredPaperPurpose | None = None) -> PaperCASOutcome:
        """Internal trusted-producer path shared by normal and already-claimed grading.

        This is NOT a public caller-score import interface. The retry owner
        invokes it only under the CAS operation guard after actual grading.
        """
        try:
            intent = _approved_intent(custody, self._questions, self._max)
            if self._require_academic:
                from grading.integration.academic_claim_binding import academic_intent, validate_preparation
                from grading.contracts.paper_aggregation import ExpectedQuestionResult
                scores = custody.outcome.result.questions
                for q, score_record in zip(custody.questions, scores, strict=True):
                    expected = academic_intent(q.original_f25_request, intent.issued,
                                               q.academic_preparation.intent.scoring,
                                               self._max, self._questions)
                    validate_preparation(q.academic_preparation, expected, self._max)
                    approved_version = next((v for v in expected.scoring.expected_questions
                                              if v.question_id == q.question_id), None)
                    if (type(approved_version) is not ExpectedQuestionResult
                            or score_record.score.question_id != q.question_id
                            or score_record.score.rubric_ref != approved_version.rubric_ref
                            or score_record.score.scoring_policy_ref != approved_version.scoring_policy_ref):
                        raise ValueError('Scored rubric/policy version differs from bound preclaim.')
        except Exception:
            return PaperCASOutcome(PaperCASState.NOT_ELIGIBLE, custody)
        if predecessor is not None:
            # An authorized regrade must not reuse physical identities or
            # stable request identities from the immutable predecessor paper.
            prior = predecessor.intent.question_claims
            new = intent.question_claims
            if any({c[i] for c in prior} & {c[i] for c in new}
                   for i in (1, 2, 3)):
                # physical attempt claim has already been contacted. The backend may have made a
                # real claim; never label this as clean pre-effect refusal.
                return PaperCASOutcome(PaperCASState.UNKNOWN, custody)
        baseline = _snapshot_owned(custody)
        intended = _snapshot_owned(intent)
        try:
            transaction = self._issue(intent=intent)
        except Exception:
            # The qualified issuer is expected to identify rather than commit,
            # but may have persisted an operation before an exception. We have
            # no reliable original reference, so cannot claim definitive denial.
            return PaperCASOutcome(PaperCASState.UNKNOWN, custody)
        try:
            if _snapshot_owned(custody) != baseline or _snapshot_owned(intent) != intended:
                return PaperCASOutcome(PaperCASState.UNKNOWN, custody)
            _validate_transaction(transaction, intent, self._allowed, self._max)
            if (predecessor is not None
                    and (transaction.request_ref == predecessor.request_ref
                         or transaction.event_ref == predecessor.event_ref
                         or transaction.result_ref == predecessor.result_ref
                         or transaction.intent.plan.request.grading_run_id ==
                            predecessor.intent.plan.request.grading_run_id)):
                raise ValueError('New paper CAS cannot reuse predecessor run or ledger references.')
        except Exception:
            # Even a malformed *returned* transaction may follow issuer-side
            # durable effects. It cannot prove definite no-operation.
            return PaperCASOutcome(PaperCASState.UNKNOWN, custody)
        original = _snapshot_owned(transaction)
        try:
            if self._purpose_commit is not None:
                _admit_scored_purpose(purpose, intent, predecessor, transaction,
                                      self._max, self._questions)
            if self._joint_commit is not None or self._purpose_commit is not None:
                from grading.integration.joint_effect_authority import JointAuthoritySnapshot
                # Actual original, deterministic scoring-scored custody; no caller-submitted CAS
                # references. Every question must bind an independently admitted
                # academic issuer and installed runtime approval from FIRST.
                authorities = tuple(JointAuthoritySnapshot(
                    q.academic_preparation.intent, q.approved_runtime,
                    self._max, self._questions) for q in custody.questions)
                if (len(authorities) != len(custody.questions)
                        or any(a.academic.original_request != q.original_f25_request
                               or a.academic.issued_paper != intent.issued
                               or a.academic.scoring.grading_spec_ref != intent.issued.request.grading_spec_ref
                               for a, q in zip(authorities, custody.questions, strict=True))):
                    raise ValueError('Scored CAS joint authority does not bind actual claims.')
                authority_before = _snapshot_owned(authorities)
                if self._purpose_commit is not None:
                    purpose_before = _snapshot_owned(purpose)
                    decision = self._purpose_commit(transaction=transaction, custody=custody,
                                                    authorities=authorities, purpose=purpose)
                    if _snapshot_owned(purpose) != purpose_before:
                        raise ValueError('Original lifecycle authorization purpose mutated during scored CAS contact.')
                else:
                    decision = self._joint_commit(transaction=transaction, custody=custody,
                                                  authorities=authorities)
                if _snapshot_owned(authorities) != authority_before:
                    raise ValueError('Joint authority changed during scored CAS contact.')
            else:
                decision = self._commit(transaction=transaction, custody=custody)
        except Exception:
            return PaperCASOutcome(PaperCASState.UNKNOWN, custody, transaction)
        try:
            if (_snapshot_owned(custody) != baseline or _snapshot_owned(transaction) != original
                    or _snapshot_owned(intent) != intended
                    or type(decision) is not PaperCASDecision
                    or type(decision.disposition) is not PaperCASDisposition
                    or type(decision.transaction) is not PaperCASTransaction
                    or not _same_validated_value(decision.transaction, transaction)):
                raise ValueError('Post-contact paper CAS identity changed.')
            if decision.disposition is PaperCASDisposition.COMMITTED:
                return PaperCASOutcome(PaperCASState.COMMITTED, custody, transaction,
                                       _receipt(decision.receipt, transaction, self._max),
                                       self._require_academic)
            if decision.receipt is not None:
                raise ValueError('Noncommitted response carried an audit acknowledgment.')
            return PaperCASOutcome(
                PaperCASState.BLOCKED if decision.disposition in (
                    PaperCASDisposition.STALE, PaperCASDisposition.CONFLICT)
                else PaperCASState.UNKNOWN, custody, transaction)
        except Exception:
            return PaperCASOutcome(PaperCASState.UNKNOWN, custody, transaction)

    def reconcile(self, *, outcome: PaperCASOutcome) -> PaperCASState:
        lease = _enter_cas(self)
        try:
            return self._reconcile(outcome=outcome)
        finally:
            _leave_cas(self, lease)

    def _reconcile(self, *, outcome: PaperCASOutcome) -> PaperCASState:
        """Original-transaction-bound backend READ, never a resubmitted CAS.

        Missing durable source-of-record => UNKNOWN. No caller-supplied record
        can alone select a different backend recovery target.
        """
        if (type(outcome) is not PaperCASOutcome
                or type(outcome.state) is not PaperCASState
                or type(outcome.academic_binding_verified) is not bool
                or outcome.transaction is None
                or type(outcome.transaction) is not PaperCASTransaction
                or (outcome.receipt is not None
                    and type(outcome.receipt) is not PaperCASReceipt)):
            return PaperCASState.UNKNOWN
        # The caller's transaction reference MUST NOT select historical
        # authority. The exact outcome issued by this instance selects the
        # original local operation. A rehydrated/caller-built outcome cannot
        # establish that identity after a restart; it remains UNKNOWN until a
        # separately qualified durable recovery seam is used (academic-bound physical claim).
        observed = self._issued.get(id(outcome))
        if observed is None or observed[0]() is not outcome:
            return PaperCASState.UNKNOWN
        original_operation = observed[1]
        # Compare against the state issued by this engine, not just a fresh
        # snapshot of an already-tampered outcome at reconciliation entry.
        try:
            if (outcome.state is not observed[2]
                    or outcome.academic_binding_verified is not observed[3]
                    or _snapshot_owned(outcome.custody) != observed[4]
                    or (None if outcome.receipt is None else _snapshot_owned(outcome.receipt)) != observed[5]):
                return PaperCASState.UNKNOWN
        except Exception:
            return PaperCASState.UNKNOWN
        # These callback-accessible fields must remain the exact admitted
        # values across original-source and backend reads. The deeper custody
        # and transaction graphs are already separately snapshotted below.
        admitted_fields = (outcome.state, outcome.academic_binding_verified,
                           outcome.custody, outcome.transaction, outcome.receipt)
        def unchanged_fields():
            return (type(outcome.state) is PaperCASState
                    and type(outcome.academic_binding_verified) is bool
                    and all(current is original for current, original in zip(
                        (outcome.state, outcome.academic_binding_verified,
                         outcome.custody, outcome.transaction, outcome.receipt),
                        admitted_fields, strict=True))
                    and (outcome.receipt is None or
                         _snapshot_owned(outcome.receipt) == admitted_receipt_snapshot))
        try:
            admitted_receipt_snapshot = (None if outcome.receipt is None
                                         else _snapshot_owned(outcome.receipt))
            intent = _approved_intent(outcome.custody, self._questions, self._max)
            submitted = outcome.transaction
            _validate_transaction(submitted, intent, self._allowed, self._max)
            # Do not contact even the fixed historical source for a receipt
            # already known to contradict this locally issued CAS transaction.
            # Revalidate it again after original-source/backend callbacks.
            if outcome.receipt is not None:
                _receipt(outcome.receipt, submitted, self._max)
            if _snapshot_owned(submitted) != original_operation:
                return PaperCASState.BLOCKED
            original_snapshot = _snapshot_owned(submitted)
            paper_snapshot = _snapshot_owned(outcome.custody)
        except Exception:
            return PaperCASState.UNKNOWN
        try:
            qualified_original = self._original(plan=outcome.custody.plan,
                                                request_ref=submitted.request_ref)
        except Exception:
            return PaperCASState.UNKNOWN
        try:
            if (not unchanged_fields()
                    or _snapshot_owned(outcome.custody) != paper_snapshot
                    or _snapshot_owned(submitted) != original_snapshot):
                return PaperCASState.UNKNOWN
            _validate_transaction(qualified_original, intent, self._allowed, self._max)
            if not _same_validated_value(qualified_original, submitted):
                return PaperCASState.BLOCKED
            if outcome.receipt is not None:
                _receipt(outcome.receipt, submitted, self._max)
        except Exception:
            return PaperCASState.UNKNOWN
        try:
            # IMPORTANT: read the separately qualified ORIGINAL, never the
            # caller-supplied record, even after a matching value comparison.
            before = _snapshot_owned(qualified_original)
            fact = self._recover(transaction=qualified_original)
            if (not unchanged_fields()
                    or _snapshot_owned(outcome.custody) != paper_snapshot
                    or _snapshot_owned(submitted) != original_snapshot
                    or _snapshot_owned(qualified_original) != before
                    or type(fact) is not PaperCASRecovery
                    or type(fact.disposition) is not PaperCASDisposition
                    or type(fact.transaction) is not PaperCASTransaction
                    or not _same_validated_value(fact.transaction, qualified_original)):
                return PaperCASState.UNKNOWN
            if fact.disposition is PaperCASDisposition.COMMITTED:
                _receipt(fact.receipt, qualified_original, self._max)
                if (outcome.receipt is not None and
                        not _same_validated_value(outcome.receipt, fact.receipt)):
                    return PaperCASState.UNKNOWN
                return PaperCASState.COMMITTED
            if fact.receipt is not None:
                return PaperCASState.UNKNOWN
            return (PaperCASState.BLOCKED if fact.disposition in
                    (PaperCASDisposition.CONFLICT, PaperCASDisposition.STALE)
                    else PaperCASState.UNKNOWN)
        except Exception:
            return PaperCASState.UNKNOWN


class QualifiedOwnedPaperCASOriginal(Protocol):
    """Installed source with a FIXED independently authorized execution scope.

    The composition root must authenticate the specific original execution
    BEFORE installation. This method accepts no caller-supplied plan, result
    or transaction reference and MUST select that run's genuine original CAS
    operation, resolving duplicate/regrade generations under approved policy.
    """
    def resolve_owned_original_paper_transaction(self) -> PaperCASTransaction: ...


class ProductionPaperCASDurableRecovery:
    """academic-bound physical claim source-of-record route for cross-process paper-CAS recovery.

    The caller's record is an assertion to validate, NEVER the lookup key.
    Only the installed no-argument original-operation provider chooses the
    transaction. Its authentication/persistence remains a real external gate.
    """
    __slots__ = ('_original', '_recover', '_allowed', '_max', '_questions', '_gate')

    def __init__(self, *, original_source: QualifiedOwnedPaperCASOriginal,
                 store: AtomicWholePaperResultStateAuditStore,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int, max_questions: int):
        if (type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int
                or not 0 < max_questions <= 10000):
            raise ValueError('Qualified, bounded original CAS recovery required.')
        _id(legal_policy.policy_id, max_identifier_characters)
        object.__setattr__(self, '_original', _capture(original_source,
            'resolve_owned_original_paper_transaction', ()))
        object.__setattr__(self, '_recover', _capture(store,
            'reconcile_whole_paper', ('transaction',)))
        object.__setattr__(self, '_allowed', legal_policy)
        object.__setattr__(self, '_max', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, key, value):
        raise AttributeError('Installed durable CAS recovery cannot be changed.')

    def reconcile(self, *, outcome: PaperCASOutcome,
                  disjoint_from: PaperCASTransaction | None = None) -> PaperCASState:
        if not self._gate.acquire(blocking=False):
            return PaperCASState.UNKNOWN
        try:
            if (type(outcome) is not PaperCASOutcome
                    or type(outcome.state) is not PaperCASState
                    or type(outcome.academic_binding_verified) is not bool
                    or (outcome.receipt is not None
                        and type(outcome.receipt) is not PaperCASReceipt)):
                return PaperCASState.UNKNOWN
            # A transaction issuer may persist an original CAS operation but
            # lose its response. The separately qualified fixed-origin source
            # can still identify it after a crash; a caller-supplied request
            # never chooses the backend read. For a non-UNKNOWN outcome the
            # missing transaction is contradictory and must remain blocked.
            # A definite negative local decision cannot silently be upgraded to
            # COMMITTED under an unresolved source-precedence contract.
            if outcome.state in (PaperCASState.BLOCKED, PaperCASState.NOT_ELIGIBLE):
                return PaperCASState.UNKNOWN
            if (outcome.transaction is None and
                    (outcome.state is not PaperCASState.UNKNOWN
                     or outcome.receipt is not None)):
                return PaperCASState.UNKNOWN
            if (outcome.transaction is not None
                    and type(outcome.transaction) is not PaperCASTransaction):
                return PaperCASState.UNKNOWN
            if disjoint_from is not None:
                # Validate the independently supplied predecessor's locally
                # inspectable shape before contacting even the fixed original
                # resolver. This does NOT authenticate historical issuance.
                if type(disjoint_from) is not PaperCASTransaction:
                    return PaperCASState.BLOCKED
                try:
                    old = disjoint_from.intent
                    if (type(old) is not PaperCASIntent
                            or type(old.plan) is not AdmittedPaperPlan
                            or type(old.plan.request) is not PaperAdmissionRequest):
                        return PaperCASState.BLOCKED
                    _plan(old.plan, self._questions, self._max)
                    issued = _relation(old.issued, self._questions, self._max)
                    if (issued.request != old.plan.request
                            or issued.actor_ref != old.plan.actor_ref
                            or issued.approval_ref != old.plan.approval_ref
                            or issued.approval_revision != old.plan.approval_revision
                            or issued.selection_decision_ref != old.plan.selection_decision_ref
                            or issued.selection_revision != old.plan.selection_revision
                            or issued.source_revision != old.plan.source_revision
                            or issued.readiness_revision != old.plan.readiness_revision
                            or tuple(q.question_id for q in issued.questions)
                               != tuple(q.request.question_id for q in old.plan.questions)):
                        return PaperCASState.BLOCKED
                    for rel, question in zip(issued.questions, old.plan.questions, strict=True):
                        if (rel.family, rel.source_artifact_ref, rel.evidence_scope_ref,
                            rel.answer_region_ref, rel.source_revision, rel.provenance_ref) != (
                            question.family, question.source_artifact_ref, question.evidence_scope_ref,
                            question.answer_region_ref, question.source_revision, question.provenance_ref):
                            return PaperCASState.BLOCKED
                    # No evidence here that old and current legal operation transition policy versions
                    # must be equal. Validate the prior's exact local shape,
                    # leave historical issuer authenticity externally qualified.
                    for field in ('request_ref', 'event_ref', 'result_ref',
                                  'expected_ledger_revision', 'f57_policy_id', 'f57_approval_ref'):
                        _id(getattr(disjoint_from, field), self._max)
                    if (type(disjoint_from.f57_policy_version) is not int
                            or disjoint_from.f57_policy_version <= 0
                            or type(disjoint_from.source_state) is not GradingJobState
                            or type(disjoint_from.target_state) is not GradingJobState):
                        return PaperCASState.BLOCKED
                    claims = old.question_claims
                    if (type(claims) is not tuple or not 0 < len(claims) <= self._questions
                            or any(type(c) is not tuple or len(c) != 4
                                   for c in claims)):
                        return PaperCASState.BLOCKED
                    for claim in claims:
                        for identifier in claim:
                            _id(identifier, self._max)
                    if any(len({claim[i] for claim in claims}) != len(claims)
                           for i in (0, 1, 2, 3)):
                        return PaperCASState.BLOCKED
                    if tuple(claim[0] for claim in claims) != tuple(
                            question.request.question_id for question in old.plan.questions):
                        return PaperCASState.BLOCKED
                    # An earlier paper CAS intent also asserts original physical attempt claim
                    # request custody and a scored result. Do not accept a
                    # malformed or self-contradictory prior generation merely
                    # because its three CAS identifiers are distinct.
                    originals = old.original_claim_requests
                    if (type(originals) is not tuple
                            or len(originals) != len(claims)
                            or type(old.result) is not GradingExecutionResult
                            or old.result.context.grading_run_id != old.plan.request.grading_run_id
                            or old.result.context.submission_ref != old.plan.request.submission_ref
                            or old.result.context.exam_ref != old.plan.request.exam_ref
                            or old.result.context.grading_spec_ref != old.plan.request.grading_spec_ref
                            or len(old.result.questions) != len(claims)):
                        return PaperCASState.BLOCKED
                    # The alleged prior scored paper must agree with its own
                    # original question inventory and paper-level result. A
                    # well-shaped but foreign score is not a valid historical
                    # generation simply because its CAS refs are disjoint.
                    scored = old.result
                    if (type(scored.questions) is not tuple
                            or type(scored.paper_score) is not PaperScoreResult
                            or scored.paper_score.grading_spec_ref != old.plan.request.grading_spec_ref
                            or type(scored.paper_score.numeric_profile_version) is not str
                            or scored.paper_score.numeric_profile_version != NUMERIC_PROFILE_VERSION
                            or any(type(record) is not QuestionExecutionRecord
                                   or type(record.verified) is not VerifiedCriterionJudgments
                                   or type(record.score) is not QuestionScoreResult
                                   or type(record.score.numeric_profile_version) is not str
                                   or record.score.numeric_profile_version != NUMERIC_PROFILE_VERSION
                                   for record in scored.questions)
                            or tuple(record.score.question_id for record in scored.questions)
                               != tuple(q.request.question_id for q in old.plan.questions)
                            or type(scored.paper_score.question_results) is not tuple
                            or not _same_validated_value(
                                scored.paper_score.question_results,
                                tuple(record.score for record in scored.questions))
                            or any(exact_compare(record.score.final_score,
                                                 record.score.minimum_score) < 0
                                   or exact_compare(record.score.final_score,
                                                    record.score.maximum_score) > 0
                                   for record in scored.questions)
                            or exact_compare(scored.paper_score.final_score,
                                             scored.paper_score.minimum_score) < 0
                            or exact_compare(scored.paper_score.final_score,
                                             scored.paper_score.maximum_score) > 0
                            or exact_compare(scored.paper_score.final_score,
                                exact_sum(tuple(record.score.final_score
                                                for record in scored.questions))) != 0):
                        return PaperCASState.BLOCKED
                    # A recovered predecessor is an original grading operation,
                    # not a collection of independently well-shaped records.
                    # Validate every score/evidence/issued-authority join before
                    # either the historical source or CAS backend is contacted.
                    _validate_grading_spec_ref(scored.paper_score.grading_spec_ref)
                    for record, question, relation in zip(
                            scored.questions, old.plan.questions,
                            issued.questions, strict=True):
                        _id(record.verified.question_id, self._max)
                        _id(record.verified.submission_ref, self._max)
                        # Revalidate the old deterministic scoring projection and its exact scored
                        # criterion selections. An internally coherent paper
                        # total cannot legitimize a score for different judged
                        # criteria or selected levels.
                        replace(record.verified)
                        # The frozen deterministic scoring verifier cannot produce a scoring
                        # judgment without an original evidence reference.
                        # Historical source authentication remains external;
                        # this is a locally provable verifier-output invariant.
                        for evaluated in record.verified.evaluated_judgments:
                            replace(evaluated)
                            if (not evaluated.evidence_refs
                                    or any(type(ref) is not str or not ref
                                           or ref.strip() != ref
                                           for ref in evaluated.evidence_refs)):
                                return PaperCASState.BLOCKED
                        # The frozen reducer always records all four ordered
                        # transformations, including no-op stages. Validate
                        # their exact arithmetic continuity without inventing
                        # original rubric/policy contents or rerunning grading.
                        stages = record.score.stage_effects
                        if type(stages) is not tuple or len(stages) != 4:
                            return PaperCASState.BLOCKED
                        for stage in stages:
                            replace(stage)
                        if tuple(stage.stage for stage in stages) != (
                                ScoreStage.GATES, ScoreStage.CAPS,
                                ScoreStage.DEDUCTIONS, ScoreStage.ROUNDING):
                            return PaperCASState.BLOCKED
                        if (exact_compare(record.score.base_subtotal,
                                exact_sum(tuple(effect.effective_contribution
                                                for effect in record.score.criterion_effects))) != 0
                                or exact_compare(stages[0].before, record.score.base_subtotal) != 0
                                or any(exact_compare(left.after, right.before) != 0
                                       for left, right in zip(stages, stages[1:]))
                                or exact_compare(stages[3].before,
                                                 record.score.score_before_rounding) != 0
                                or exact_compare(stages[3].after,
                                                 record.score.final_score) != 0):
                            return PaperCASState.BLOCKED
                        if not _valid_locally_replayable_rule_trace(record.score):
                            return PaperCASState.BLOCKED
                        verified_pairs = []
                        for judgment in record.verified.scoring_judgments:
                            replace(judgment)
                            verified_pairs.append((judgment.criterion_id,
                                                   judgment.selected_level))
                        scored_pairs = []
                        for effect in record.score.criterion_effects:
                            replace(effect)
                            scored_pairs.append((effect.criterion_id,
                                                 effect.selected_level))
                        if (not verified_pairs
                                or len(verified_pairs) != len(scored_pairs)
                                or len({item[0] for item in verified_pairs}) != len(verified_pairs)
                                or len({item[0] for item in scored_pairs}) != len(scored_pairs)
                                or set(verified_pairs) != set(scored_pairs)):
                            return PaperCASState.BLOCKED
                        _validate_rubric_ref(
                            record.score.rubric_ref, field_name='predecessor.rubric',
                            error_type=ValueError)
                        _validate_scoring_policy_ref(
                            record.score.scoring_policy_ref,
                            field_name='predecessor.scoring_policy',
                            error_type=ValueError, require_supported_semantics=True)
                        if (record.verified.question_id != question.request.question_id
                                or record.verified.submission_ref != old.plan.request.submission_ref
                                or record.score.rubric_ref.id != relation.rubric_ref
                                or record.score.scoring_policy_ref.id != relation.scoring_policy_ref):
                            return PaperCASState.BLOCKED
                    from grading.integration.whole_paper_attempt_custody import _matches_paper
                    for original_request, claim, question in zip(
                            originals, claims, old.plan.questions, strict=True):
                        _request_snapshot(original_request, self._max)
                        if (original_request.request_ref != claim[1]
                                or original_request.family != question.family
                                or not _matches_paper(original_request.scope,
                                                      old.plan, question, self._max)):
                            return PaperCASState.BLOCKED
                except Exception:
                    return PaperCASState.BLOCKED
            try:
                # Previous-generation custody must remain stable too: callbacks
                # cannot change the supplied predecessor to hide a collision.
                disjoint_snapshot = (None if disjoint_from is None
                                     else _snapshot_owned(disjoint_from))
                intent = _approved_intent(outcome.custody, self._questions, self._max)
                submitted = outcome.transaction
                if submitted is not None:
                    _validate_transaction(submitted, intent, self._allowed, self._max)
                # Known local contradictions do not need historical-source
                # contact. Missing submitted transaction must still use the
                # independently qualified fixed-original recovery path.
                if disjoint_from is not None and submitted is not None:
                    if not _separate_paper_cas_generation(submitted, disjoint_from):
                        return PaperCASState.BLOCKED
                if outcome.receipt is not None:
                    if submitted is None:
                        return PaperCASState.UNKNOWN
                    _receipt(outcome.receipt, submitted, self._max)
                submitted_snapshot = (None if submitted is None else _snapshot_owned(submitted))
                custody_snapshot = _snapshot_owned(outcome.custody)
                admitted_receipt_snapshot = (None if outcome.receipt is None
                                             else _snapshot_owned(outcome.receipt))
                admitted_fields = (outcome.state, outcome.academic_binding_verified,
                                   outcome.custody, outcome.transaction, outcome.receipt)
                def unchanged_fields():
                    return (type(outcome.state) is PaperCASState
                            and type(outcome.academic_binding_verified) is bool
                            and all(current is original for current, original in zip(
                                (outcome.state, outcome.academic_binding_verified,
                                 outcome.custody, outcome.transaction, outcome.receipt),
                                admitted_fields, strict=True))
                    and (outcome.receipt is None or
                         _snapshot_owned(outcome.receipt) == admitted_receipt_snapshot))
            except Exception:
                return PaperCASState.UNKNOWN
            try:
                original = self._original()  # ZERO caller-controlled lookup arguments
            except Exception:
                return PaperCASState.UNKNOWN
            try:
                if (not unchanged_fields()
                        or (disjoint_from is not None
                            and _snapshot_owned(disjoint_from) != disjoint_snapshot)
                        or (submitted is not None and _snapshot_owned(submitted) != submitted_snapshot)
                        or _snapshot_owned(outcome.custody) != custody_snapshot):
                    return PaperCASState.UNKNOWN
                _validate_transaction(original, intent, self._allowed, self._max)
                if outcome.receipt is not None:
                    if submitted is None:
                        return PaperCASState.UNKNOWN
                    _receipt(outcome.receipt, submitted, self._max)
                # Independently resolved original must belong to a NEW CAS
                # generation. This check is essential when the current issuer
                # lost its response, so the caller has no submitted CAS ref.
                if disjoint_from is not None:
                    if type(disjoint_from) is not PaperCASTransaction:
                        return PaperCASState.BLOCKED
                    # Repeat against the independently recovered original:
                    # the local transaction is never historical authority.
                    if not _separate_paper_cas_generation(original, disjoint_from):
                        return PaperCASState.BLOCKED
                if submitted is not None and not _same_validated_value(original, submitted):
                    return PaperCASState.BLOCKED
                original_snapshot = _snapshot_owned(original)
            except Exception:
                return PaperCASState.UNKNOWN
            try:
                fact = self._recover(transaction=original)
                if (not unchanged_fields()
                        or (disjoint_from is not None
                            and _snapshot_owned(disjoint_from) != disjoint_snapshot)
                        or _snapshot_owned(original) != original_snapshot
                        or _snapshot_owned(outcome.custody) != custody_snapshot
                        or (submitted is not None and _snapshot_owned(submitted) != submitted_snapshot)
                        or type(fact) is not PaperCASRecovery
                        or type(fact.transaction) is not PaperCASTransaction
                        or type(fact.disposition) is not PaperCASDisposition
                        or not _same_validated_value(fact.transaction, original)):
                    return PaperCASState.UNKNOWN
                if fact.disposition is PaperCASDisposition.COMMITTED:
                    _receipt(fact.receipt, original, self._max)
                    if (outcome.receipt is not None and
                            not _same_validated_value(outcome.receipt, fact.receipt)):
                        return PaperCASState.UNKNOWN
                    return PaperCASState.COMMITTED
                if fact.receipt is not None:
                    return PaperCASState.UNKNOWN
                return (PaperCASState.BLOCKED if fact.disposition in (
                    PaperCASDisposition.CONFLICT, PaperCASDisposition.STALE)
                    else PaperCASState.UNKNOWN)
            except Exception:
                return PaperCASState.UNKNOWN
        finally:
            self._gate.release()
