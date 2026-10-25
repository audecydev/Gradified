"""Validate current operation permission and original-attempt lineage before paper effects.

Reuses strict whole-paper score commit CAS, original physical attempt claim academic preparation and read-only
predecessor/audit reconciliation. A legal operation-transition decision authorizes only its particular
new run and policy edge: no result or recovery object is a bearer permit.
No unknown claim, missing receipt or CAS acknowledgement implies retry or
institutional publication. Cross-worker persistence and policy authenticity
require independently qualified external implementations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy, _snapshot_owned
from grading.integration.execution_eligibility import _capture, _id
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.paper_execution_correlation import _plan
from grading.integration.whole_paper_attempt_custody import PaperAttemptCustody
from grading.integration.whole_paper_cas import (
    ProductionWholePaperCAS, PaperCASOutcome, PaperCASState, PaperCASTransaction,
    PaperCASRecovery, PaperCASDisposition, _receipt, _approved_intent,
    _validate_transaction, _same_validated_value, ProductionPaperCASDurableRecovery,
)


class PaperLifecycleKind(str, Enum):
    FIRST = 'FIRST'
    REGRADE = 'REGRADE'


class PaperLifecycleAuditState(str, Enum):
    """Read-only backend assertion, never an institutional publication grant."""
    REPORTED_COMMITTED = 'REPORTED_COMMITTED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class PaperLifecycleAuditObservation:
    state: PaperLifecycleAuditState

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def authorizes_publication(self) -> bool:
        return False


class PaperLifecycleState(str, Enum):
    PRE_EFFECT_BLOCKED = 'PRE_EFFECT_BLOCKED'
    UNKNOWN = 'UNKNOWN'
    CAS_ACKNOWLEDGED = 'CAS_ACKNOWLEDGED'
    CAS_BLOCKED = 'CAS_BLOCKED'
    REGRADE_LINEAGE_VERIFIED = 'REGRADE_LINEAGE_VERIFIED'


@dataclass(frozen=True, slots=True, repr=False)
class PaperLifecyclePermission:
    """Qualified external legal operation-transition decision; not a locally mintable execution token."""
    plan: AdmittedPaperPlan
    kind: PaperLifecycleKind
    approval_ref: str
    policy_id: str
    policy_version: int
    source_state: GradingJobState
    target_state: GradingJobState
    predecessor: PaperCASTransaction | None = None
    predecessor_custody: PaperAttemptCustody | None = None


@dataclass(frozen=True, slots=True, repr=False)
class PaperLifecycleObservation:
    state: PaperLifecycleState
    kind: PaperLifecycleKind | None = None
    cas: PaperCASOutcome | None = None
    predecessor: PaperCASTransaction | None = None
    permission: PaperLifecyclePermission | None = None  # observed legal operation transition pre-effect grant, non-bearer

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def authorizes_publication(self) -> bool:
        return False


class QualifiedPaperLifecyclePermissionSource(Protocol):
    """Must independently authorize the exact NEW run/paper and legal legal operation transition edge.

    No caller-provided predecessor selector. A REGRADE predecessor must be
    independently selected by this authorized source, not guessed from the
    current paper or recovered from a caller-created score. Authenticity and
    legal-policy approval are required external qualification evidence.
    """
    def resolve_paper_execution_permission(self, *, plan: AdmittedPaperPlan) -> PaperLifecyclePermission: ...


def _guard_factory():
    mutex = Lock()
    active: dict[int, object] = {}
    def enter(owner):
        with mutex:
            key = id(owner)
            if key in active:
                raise ValueError('Nested/concurrent paper lifecycle operation denied.')
            token = object()
            active[key] = token
            return token
    def leave(owner, token):
        with mutex:
            key = id(owner)
            if active.get(key) is not token:
                raise RuntimeError('paper lifecycle lease owner changed.')
            del active[key]
    return enter, leave


_enter_c4, _leave_c4 = _guard_factory()


class ProductionPaperLifecycle:
    """Original legal operation transition authority before physical attempt claim; genuine whole-paper score commit CAS only after approval.

    Native deterministic CHOICE makes no provider transport call, so there is
    no provider usage event to fabricate. P-D accounting/recovery already
    owns actual provider operations for families that execute them; this
    CHOICE-only port does not misrepresent missing telemetry as zero cost.
    """
    __slots__ = ('_cas', '_authorize', '_read_previous', '_policy', '_maximum', '_questions', '_audit_recovery')

    def __init__(self, *, cas: ProductionWholePaperCAS,
                 permission_source: QualifiedPaperLifecyclePermissionSource,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int, max_questions: int,
                 audit_recovery: ProductionPaperCASDurableRecovery | None = None):
        if (type(cas) is not ProductionWholePaperCAS
                or cas._require_academic is not True
                or type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000
                or legal_policy != cas._allowed):
            raise ValueError('paper lifecycle requires the strict academic-bound paper CAS and exact lifecycle authorization policy.')
        if audit_recovery is not None and type(audit_recovery) is not ProductionPaperCASDurableRecovery:
            raise ValueError('paper lifecycle audit recovery must use installed original-operation consumer.')
        _id(legal_policy.policy_id, max_identifier_characters)
        object.__setattr__(self, '_audit_recovery', audit_recovery)
        object.__setattr__(self, '_cas', cas)
        object.__setattr__(self, '_authorize', _capture(permission_source,
            'resolve_paper_execution_permission', ('plan',)))
        # Read using the ORIGINAL installed CAS backend. No new write operation.
        object.__setattr__(self, '_read_previous', cas._recover)
        object.__setattr__(self, '_policy', legal_policy)
        object.__setattr__(self, '_maximum', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)

    def __setattr__(self, name, value):
        raise AttributeError('paper lifecycle installation cannot be replaced.')

    def __delattr__(self, name):
        raise AttributeError('paper lifecycle installation cannot be replaced.')

    def _permission(self, plan: AdmittedPaperPlan):
        verified = _plan(plan, self._questions, self._maximum)
        original = _snapshot_owned(verified)
        try:
            claimed = self._authorize(plan=verified)
        except Exception:
            return None, PaperLifecycleState.UNKNOWN, None
        try:
            if (_snapshot_owned(verified) != original
                    or _plan(plan, self._questions, self._maximum) != verified
                    or type(claimed) is not PaperLifecyclePermission
                    or type(claimed.plan) is not AdmittedPaperPlan
                    or _plan(claimed.plan, self._questions, self._maximum) != verified
                    or type(claimed.kind) is not PaperLifecycleKind
                    or type(claimed.source_state) is not GradingJobState
                    or type(claimed.target_state) is not GradingJobState
                    or type(claimed.policy_version) is not int
                    or claimed.policy_version != self._policy.policy_version
                    or _id(claimed.policy_id, self._maximum) != self._policy.policy_id
                    or (claimed.source_state, claimed.target_state)
                       not in self._policy.allowed_edges):
                return None, PaperLifecycleState.PRE_EFFECT_BLOCKED, None
            _id(claimed.approval_ref, self._maximum)
            if ((claimed.kind is PaperLifecycleKind.FIRST
                     and (claimed.predecessor is not None or claimed.predecessor_custody is not None))
                    or (claimed.kind is PaperLifecycleKind.REGRADE
                        and (type(claimed.predecessor) is not PaperCASTransaction
                             or type(claimed.predecessor_custody) is not PaperAttemptCustody))):
                return None, PaperLifecycleState.PRE_EFFECT_BLOCKED, None
        except Exception:
            return None, PaperLifecycleState.PRE_EFFECT_BLOCKED, None
        return claimed, None, verified

    def execute_first(self, *, plan: AdmittedPaperPlan) -> PaperLifecycleObservation:
        """One approved first execution; no retry on any outcome."""
        token = _enter_c4(self)
        try:
            permission, failure, verified = self._permission(plan)
            if failure is not None:
                return PaperLifecycleObservation(failure)
            if permission.kind is not PaperLifecycleKind.FIRST:
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
            immutable = _snapshot_owned(permission)
            try:
                result = self._cas.execute_and_commit(plan=verified, permission=permission)
            except Exception:
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.FIRST,
                                                 permission=permission)
            if _snapshot_owned(permission) != immutable:
                # A callback mutated the original legal decision. Retain no
                # authorization observation that could be used for promotion.
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.FIRST, result)
            if (type(result) is not PaperCASOutcome
                    or result.custody.plan != verified):
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.FIRST)
            if (result.state is PaperCASState.COMMITTED
                    and result.academic_binding_verified is True
                    and type(result.transaction) is PaperCASTransaction):
                try:
                    _receipt(result.receipt, result.transaction, self._maximum)
                except Exception:
                    return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.FIRST, result,
                                                     permission=permission)
                # Acknowledged by the qualified CAS *adapter*. Not institutional
                # publication authority or a claim of independently proven durability.
                return PaperLifecycleObservation(PaperLifecycleState.CAS_ACKNOWLEDGED, PaperLifecycleKind.FIRST,
                                                 result, permission=permission)
            # A possibly committed physical attempt claim cannot become a definitive CAS
            # refusal merely because complete-paper scoring was not possible.
            if (result.state is PaperCASState.NOT_ELIGIBLE
                    and result.custody.outcome.state == 'INDETERMINATE'):
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.FIRST, result,
                                                     permission=permission)
            if result.state in (PaperCASState.BLOCKED, PaperCASState.NOT_ELIGIBLE):
                return PaperLifecycleObservation(PaperLifecycleState.CAS_BLOCKED, PaperLifecycleKind.FIRST, result)
            return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.FIRST, result,
                                                     permission=permission)
        finally:
            _leave_c4(self, token)

    def _verify_predecessor(self, *, permission: PaperLifecyclePermission,
                            verified: AdmittedPaperPlan) -> PaperLifecycleObservation:
        """One qualified approved operation-transition grant and one read-only predecessor verification."""
        prior = permission.predecessor
        before = _snapshot_owned(permission)
        try:
            old = _approved_intent(permission.predecessor_custody,
                                   self._questions, self._maximum)
            # Admit every historical transaction field BEFORE selecting the
            # backend read target. A later denial cannot undo a foreign read.
            # Older policies require an explicitly qualified historical adapter.
            _validate_transaction(prior, old, self._policy, self._maximum)
            if old != prior.intent:
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
            for key in ('request_ref', 'event_ref', 'result_ref', 'expected_ledger_revision',
                        'f57_policy_id', 'f57_approval_ref'):
                _id(getattr(prior, key), self._maximum)
            if (type(prior.f57_policy_version) is not int
                    or prior.f57_policy_version <= 0
                    or type(prior.source_state) is not GradingJobState
                    or type(prior.target_state) is not GradingJobState):
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
            old_request = prior.intent.plan.request
            new_request = verified.request
            if (old_request.session_ref != new_request.session_ref
                    or old_request.tenant_ref != new_request.tenant_ref
                    or old_request.submission_ref != new_request.submission_ref
                    or old_request.exam_ref != new_request.exam_ref
                    or old_request.paper_ref != new_request.paper_ref
                    or old_request.set_ref != new_request.set_ref
                    or old_request.grading_run_id == new_request.grading_run_id):
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
        except Exception:
            return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
        try:
            response = self._read_previous(transaction=prior)
            if _snapshot_owned(permission) != before:
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN)
            if (type(response) is not PaperCASRecovery
                    or type(response.disposition) is not PaperCASDisposition):
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN)
            # Full structural validation MUST precede equality; malformed
            # nested values must not control their own equality semantics.
            _validate_transaction(response.transaction, old, self._policy, self._maximum)
            if not _same_validated_value(response.transaction, prior):
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN)
            if response.disposition is PaperCASDisposition.COMMITTED:
                _receipt(response.receipt, prior, self._maximum)
                return PaperLifecycleObservation(PaperLifecycleState.REGRADE_LINEAGE_VERIFIED,
                    PaperLifecycleKind.REGRADE, predecessor=prior)
            if response.receipt is not None:
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN)
            if response.disposition in (PaperCASDisposition.STALE, PaperCASDisposition.CONFLICT):
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
        except Exception:
            return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN)
        return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN)
    def admit_regrade(self, *, plan: AdmittedPaperPlan) -> PaperLifecycleObservation:
        """A read-only observation; never a transferable regrade permission."""
        token = _enter_c4(self)
        try:
            permission, failure, verified = self._permission(plan)
            if failure is not None:
                return PaperLifecycleObservation(failure)
            if permission.kind is not PaperLifecycleKind.REGRADE:
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
            return self._verify_predecessor(permission=permission, verified=verified)
        finally:
            _leave_c4(self, token)

    def execute_regrade(self, *, plan: AdmittedPaperPlan) -> PaperLifecycleObservation:
        """Execute only a fresh operation-transition-authorized and original-attempt-predecessor-bound regrade.

        The observation is not a retry/publication credential. A qualified
        physical-attempt backend must durably enforce the predecessor/regrade relationship
        and the prepared academic revision across distributed workers.
        """
        token = _enter_c4(self)
        try:
            permission, failure, verified = self._permission(plan)
            if failure is not None:
                return PaperLifecycleObservation(failure)
            if permission.kind is not PaperLifecycleKind.REGRADE:
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED)
            prior_check = self._verify_predecessor(permission=permission, verified=verified)
            if prior_check.state is not PaperLifecycleState.REGRADE_LINEAGE_VERIFIED:
                return prior_check
            baseline = _snapshot_owned(permission)
            try:
                # This exact allocator will make each original physical attempt request.
                # Its regrade gate checks request fields BEFORE academic
                # preparation, bound claim and actual physical attempt effects.
                attempts = self._cas._custody._attempts
                owner = attempts.begin_authorized_regrade(
                    plan=verified, predecessor_result_ref=permission.predecessor.result_ref,
                    regrade_approval_ref=permission.approval_ref,
                    predecessor_request_refs=tuple(req.request_ref for req in
                        permission.predecessor.intent.original_claim_requests),
                    permission=permission)
            except Exception:
                return PaperLifecycleObservation(PaperLifecycleState.PRE_EFFECT_BLOCKED, PaperLifecycleKind.REGRADE)
            try:
                try:
                    result = self._cas.execute_and_commit(
                        plan=verified, predecessor=permission.predecessor,
                        permission=permission)
                except Exception:
                    return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.REGRADE,
                        predecessor=permission.predecessor, permission=permission)
            finally:
                attempts.finish_authorized_regrade(token=owner)
            if (_snapshot_owned(permission) != baseline
                    or type(result) is not PaperCASOutcome
                    or result.custody.plan != verified):
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.REGRADE,
                                                 result if type(result) is PaperCASOutcome else None,
                                                 permission.predecessor)
            if (result.state is PaperCASState.COMMITTED
                    and result.academic_binding_verified is True
                    and type(result.transaction) is PaperCASTransaction):
                try:
                    _validate_transaction(result.transaction, _approved_intent(
                        result.custody, self._questions, self._maximum), self._policy, self._maximum)
                    if any(q.original_f25_request is None
                           or q.original_f25_request.predecessor_result_ref != permission.predecessor.result_ref
                           or q.original_f25_request.regrade_approval_ref != permission.approval_ref
                           for q in result.custody.questions):
                        raise ValueError('Regrade grading-attempt claims lack the original predecessor.')
                    _receipt(result.receipt, result.transaction, self._maximum)
                except Exception:
                    return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.REGRADE,
                                                     result, permission.predecessor, permission)
                return PaperLifecycleObservation(PaperLifecycleState.CAS_ACKNOWLEDGED,
                    PaperLifecycleKind.REGRADE, result, permission.predecessor, permission)
            if (result.state is PaperCASState.NOT_ELIGIBLE
                    and result.custody.outcome.state == 'INDETERMINATE'):
                return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN, PaperLifecycleKind.REGRADE,
                                                 result, permission.predecessor, permission)
            if result.state in (PaperCASState.BLOCKED, PaperCASState.NOT_ELIGIBLE):
                return PaperLifecycleObservation(PaperLifecycleState.CAS_BLOCKED,
                    PaperLifecycleKind.REGRADE, result, permission.predecessor)
            return PaperLifecycleObservation(PaperLifecycleState.UNKNOWN,
                PaperLifecycleKind.REGRADE, result, permission.predecessor, permission)
        finally:
            _leave_c4(self, token)

    def reconcile_audit(self, *, observation: PaperLifecycleObservation) -> PaperLifecycleAuditObservation:
        """Read-only original paper-CAS recovery, no retry and no publication.

        Native CHOICE never makes a provider transport call; no artificial
        provider accounting receipt or numerical zero is produced here.
        Provider-backed family accounting continues to use P-D's actual
        operation-bound ReadOnlyAccountingReconciler when applicable.
        """
        token = _enter_c4(self)
        try:
            if (self._audit_recovery is None
                    or type(observation) is not PaperLifecycleObservation
                    or type(observation.state) is not PaperLifecycleState
                    or type(observation.kind) is not PaperLifecycleKind
                    or type(observation.permission) is not PaperLifecyclePermission
                    or type(observation.permission.kind) is not PaperLifecycleKind
                    or observation.permission.kind is not observation.kind
                    or type(observation.cas) is not PaperCASOutcome
                    or type(observation.cas.state) is not PaperCASState
                    or type(observation.cas.academic_binding_verified) is not bool
                    or observation.state not in (PaperLifecycleState.CAS_ACKNOWLEDGED, PaperLifecycleState.UNKNOWN)):
                return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            # An acknowledged result must carry the actually validated local
            # whole-paper receipt. An uncertain reply may have no receipt or an
            # inconsistent local state; only the fixed-original recovery can
            # establish durable truth in that case.
            cas = observation.cas
            if observation.state is PaperLifecycleState.CAS_ACKNOWLEDGED:
                if (cas.state is not PaperCASState.COMMITTED
                        or cas.academic_binding_verified is not True):
                    return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
                try:
                    _receipt(cas.receipt, cas.transaction, self._maximum)
                except Exception:
                    return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            try:
                original_observation = _snapshot_owned(observation)
            except Exception:
                return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            # The supplied lifecycle label is not evidence of what was claimed.
            # Re-establish FIRST/REGRADE from the original physical attempt request lineage
            # before reading the independently fixed original paper CAS.
            try:
                intent = _approved_intent(observation.cas.custody,
                                          self._questions, self._maximum)
                requests = intent.original_claim_requests
                permission = observation.permission
                # This read-only audit concerns the complete original lifecycle
                # operation, not an arbitrary caller-selected CAS transaction.
                # Do not equate FIRST/REGRADE authority with the later CAS legal operation transition
                # approval: these can legitimately be distinct authorized edges.
                if (type(permission.plan) is not AdmittedPaperPlan
                        or _plan(permission.plan, self._questions, self._maximum) != intent.plan
                        or _id(permission.policy_id, self._maximum) != self._policy.policy_id
                        or type(permission.policy_version) is not int
                        or permission.policy_version != self._policy.policy_version
                        or type(permission.source_state) is not GradingJobState
                        or type(permission.target_state) is not GradingJobState
                        or (permission.source_state, permission.target_state)
                           not in self._policy.allowed_edges):
                    return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
                _id(permission.approval_ref, self._maximum)
                if observation.kind is PaperLifecycleKind.FIRST:
                    valid_kind = (observation.predecessor is None
                                  and permission.predecessor is None
                                  and permission.predecessor_custody is None
                                  and all(q.predecessor_result_ref is None
                                          and q.regrade_approval_ref is None
                                          for q in requests))
                else:
                    # Read-only REGRADE audit is a second, independent positive
                    # consumer. Readmit the COMPLETE predecessor generation;
                    # a matching result reference does not validate its CAS,
                    # legal policy, academic custody or attempt history.
                    valid_kind = (type(permission.predecessor) is PaperCASTransaction
                                  and type(permission.predecessor_custody) is PaperAttemptCustody
                                  and type(observation.predecessor) is PaperCASTransaction
                                  and _snapshot_owned(observation.predecessor)
                                      == _snapshot_owned(permission.predecessor)
                                  and all(q.predecessor_result_ref == permission.predecessor.result_ref
                                          and q.regrade_approval_ref == permission.approval_ref
                                          for q in requests))
                    if valid_kind:
                        old_intent = _approved_intent(permission.predecessor_custody,
                                                      self._questions, self._maximum)
                        _validate_transaction(permission.predecessor, old_intent,
                                              self._policy, self._maximum)
                        previous = old_intent.plan.request
                        current = intent.plan.request
                        valid_kind = (all(getattr(previous, field) == getattr(current, field)
                                          for field in ('tenant_ref', 'session_ref',
                                                        'submission_ref', 'exam_ref',
                                                        'paper_ref', 'set_ref'))
                                      and previous.grading_run_id != current.grading_run_id
                                      and not any(
                                          {claim[index] for claim in old_intent.question_claims}
                                          & {claim[index] for claim in intent.question_claims}
                                          for index in (1, 2, 3)))
                        # When the current CAS issuer replied, reject reuse
                        # before the first avoidable backend read. If its
                        # reply was lost, the fixed-original CAS consumer
                        # must enforce the same disjointness before its read.
                        if valid_kind and cas.transaction is not None:
                            valid_kind = (type(cas.transaction) is PaperCASTransaction
                                          and all(getattr(permission.predecessor, field)
                                                  != getattr(cas.transaction, field)
                                                  for field in ('request_ref', 'event_ref',
                                                                'result_ref')))
                if not valid_kind:
                    return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            except Exception:
                return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            try:
                state = self._audit_recovery.reconcile(
                    outcome=observation.cas,
                    disjoint_from=(permission.predecessor if observation.kind
                                   is PaperLifecycleKind.REGRADE else None))
                # The installed reader may call arbitrary qualified external
                # code. Never endorse an assertion whose effective original
                # observation drifted during that read.
                if _snapshot_owned(observation) != original_observation:
                    return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            except Exception:
                return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
            if state is PaperCASState.COMMITTED:
                return PaperLifecycleAuditObservation(PaperLifecycleAuditState.REPORTED_COMMITTED)
            if state is PaperCASState.BLOCKED:
                return PaperLifecycleAuditObservation(PaperLifecycleAuditState.CONFLICT)
            return PaperLifecycleAuditObservation(PaperLifecycleAuditState.UNKNOWN)
        finally:
            _leave_c4(self, token)
