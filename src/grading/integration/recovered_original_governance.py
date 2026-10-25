"""Read-only, fixed-original governed scored-paper handoff/governance reconciliation after an earlier score.

A recovery invocation performs no grading, legal operation transition/physical attempt claim, provider dispatch or CAS
write.  It never converts a missing durable acknowledgment to a success: an
independently recovered committed original and matching governed scored-paper handoff assessment must
exist before any governed-readiness evaluation can be called. The actual
issuer, durability and atomic currentness guarantees are adapter obligations.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from grading.integration.execution_eligibility import _capture

from grading.integration.assessment_readiness_views import ReadinessState
from grading.integration.governed_operation_consumer import (
    GovernedOperationState, ScoredOperationIdentity,
)
from grading.integration.governed_original_assessment import GovernedOriginalKey
from grading.integration.governed_paper_handoff import GovernedPaperHandoff
from grading.integration.governed_result_disposition import ResultDisposition
from grading.integration.paper_lifecycle import (
    PaperLifecycleState, PaperLifecycleKind, PaperLifecycleObservation,
)
from grading.integration.scored_paper_promotion import (
    PaperHandoffEligibilityState, PaperHandoffAssessment,
)
from grading.integration.paper_readiness_admission import _request
from grading.integration.paper_retry_grading import GradedRetryOutcome, GradedRetryState
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.qualified_governed_operation import (
    ProductionOriginalQualifiedGovernedConsumer,
)
from grading.integration.whole_paper_cas import (
    PaperCASOutcome, PaperCASState, PaperCASTransaction, _receipt,
)


@dataclass(frozen=True, slots=True)
class RecoveredOriginalGovernance:
    state: GovernedOperationState
    operation: ScoredOperationIdentity | None = None
    original_c5: PaperHandoffAssessment | None = None
    handoff: GovernedPaperHandoff | None = None
    scored_question_ids: tuple[str, ...] = ()

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class FixedRecoveryTargetSource(Protocol):
    """Backend-owned zero-selector pending original, independently admitted."""
    def read_fixed_recovery_target(self) -> ScoredOperationIdentity: ...


class ProductionRecoveredOriginalGovernance:
    """Read-only recovery for the original installed governed scored-paper handoff/governed source set.

    This is an explicitly separate recovery API from execute_and_assess(). It
    must never invoke the grading root to discover an original. The fixed governed scored-paper handoff
    source, not a caller-provided key, chooses the original being recovered.
    The installed external adapters must enforce authentic fixed-original
    selection, consistent reads, revocation and physical-history durability.
    """
    __slots__ = ('_c5', '_original', '_key', '_handoff', '_target', '_limit', '_gate')

    def __init__(self, *, qualified: ProductionOriginalQualifiedGovernedConsumer,
                 target_source: FixedRecoveryTargetSource):
        if type(qualified) is not ProductionOriginalQualifiedGovernedConsumer:
            raise ValueError('Exact strict original-qualified governed installation required.')
        c5 = qualified._c5
        governed = qualified._governed
        if (governed._execute.__self__._promotion is not c5
                or governed._limit != c5._maximum):
            raise ValueError('Scored-paper promotion and governed sources must use one installed paper root.')
        object.__setattr__(self, '_target', _capture(target_source,
            'read_fixed_recovery_target', ()))
        object.__setattr__(self, '_c5', c5)
        object.__setattr__(self, '_original', c5._original)
        object.__setattr__(self, '_key', governed._read)
        object.__setattr__(self, '_handoff', governed._handoff)
        object.__setattr__(self, '_limit', governed._limit)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Recovery installation cannot be replaced.')

    def recover(self) -> RecoveredOriginalGovernance:
        unknown = RecoveredOriginalGovernance(GovernedOperationState.UNKNOWN)
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            return self._read_original()
        finally:
            self._gate.release()

    def _read_original(self) -> RecoveredOriginalGovernance:
        unknown = RecoveredOriginalGovernance(GovernedOperationState.UNKNOWN)
        c5, read_original, read_key, handoff, read_target, limit = (
            self._c5, self._original, self._key, self._handoff,
            self._target, self._limit)
        def installation_intact():
            return (self._c5 is c5 and self._original is read_original
                    and c5._original is read_original
                    and self._key is read_key and self._handoff is handoff
                    and self._target is read_target
                    and self._limit == limit)
        try:
            # The fixed governed scored-paper handoff history alone could belong to a PREVIOUS operation.
            # An independently selected durable pending target must identify
            # the same exact operation. Neither source accepts caller selectors.
            target = read_target()
            if type(target) is not ScoredOperationIdentity:
                return unknown
            fields = (target.tenant_ref, target.grading_run_id,
                      target.original_scored_result_ref, target.source_revision,
                      target.transaction_ref, target.transaction_event_ref,
                      target.commit_ref)
            if (type(target.kind) is not PaperOperationKind
                    or any(type(v) is not str or not v or v.strip() != v
                           or len(v) > limit for v in fields)
                    or not installation_intact()):
                return unknown
            history = read_original()  # fixed original, no caller-provided selectors
            if type(history) is PaperLifecycleObservation:
                if (history.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
                        or history.kind not in (PaperLifecycleKind.FIRST, PaperLifecycleKind.REGRADE)):
                    return unknown
                kind = (PaperOperationKind.FIRST if history.kind is PaperLifecycleKind.FIRST
                        else PaperOperationKind.REGRADE)
            elif type(history) is GradedRetryOutcome:
                if history.state is not GradedRetryState.CAS_ACKNOWLEDGED:
                    return unknown
                kind = PaperOperationKind.RETRY
            else:
                return unknown
            cas = history.cas
            if (type(cas) is not PaperCASOutcome
                    or cas.state is not PaperCASState.COMMITTED
                    or cas.academic_binding_verified is not True
                    or type(cas.transaction) is not PaperCASTransaction
                    or cas.receipt is None or not installation_intact()):
                return unknown
            tx = cas.transaction
            receipt = _receipt(cas.receipt, tx, limit)
            plan = tx.intent.plan
            request = _request(plan.request, limit)
            revision = plan.source_revision
            refs = (tx.result_ref, tx.request_ref, tx.event_ref, receipt.commit_ref, revision)
            if any(type(ref) is not str or not ref or ref.strip() != ref or len(ref) > limit
                   for ref in refs):
                return unknown
            operation = ScoredOperationIdentity(
                kind, request.tenant_ref, request.grading_run_id,
                tx.result_ref, revision, tx.request_ref, tx.event_ref, receipt.commit_ref)
            if operation != target or not installation_intact():
                return unknown
            original_c5 = c5.assess(expected_transaction=tx,
                                    expected_commit_ref=receipt.commit_ref)
            if (type(original_c5) is not PaperHandoffAssessment
                    or original_c5.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
                    or not installation_intact()):
                return unknown
            key = read_key(operation=ScoredOperationIdentity(
                operation.kind, operation.tenant_ref, operation.grading_run_id,
                operation.original_scored_result_ref, operation.source_revision,
                operation.transaction_ref, operation.transaction_event_ref,
                operation.commit_ref))
            if type(key) is not GovernedOriginalKey:
                return unknown
            names = ('tenant_ref', 'grading_run_id', 'original_scored_result_ref',
                     'source_revision', 'policy_ref', 'policy_revision')
            values = tuple(getattr(key, name) for name in names)
            if (values[:4] != (operation.tenant_ref, operation.grading_run_id,
                                operation.original_scored_result_ref, operation.source_revision)
                    or any(type(v) is not str or not v or v.strip() != v or len(v) > limit
                           for v in values) or not installation_intact()):
                return unknown
            result = handoff.assess(original=GovernedOriginalKey(*values))
            if (type(result) is not GovernedPaperHandoff
                    or (result.decision.tenant_ref, result.decision.grading_run_id,
                        result.decision.original_scored_result_ref,
                        result.decision.source_revision, result.decision.policy_ref,
                        result.decision.policy_revision) != values
                    or not installation_intact()):
                return unknown
            # Any original change during governed reads invalidates the result.
            final = c5.assess(expected_transaction=tx,
                              expected_commit_ref=receipt.commit_ref)
            if (type(final) is not PaperHandoffAssessment
                    or final.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
                    or not installation_intact()):
                return unknown
            # The independent pending-original selection can change during
            # governance callbacks even while governed scored-paper handoff's original remains stable.
            # Re-read the same zero-selector source before returning any
            # positive / REVIEW observation; never qualify a prior target
            # after the owner has moved to another pending original.
            current_target = read_target()
            if (type(current_target) is not ScoredOperationIdentity
                    or current_target != target or not installation_intact()):
                return unknown
            if (result.decision.disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
                    and result.readiness.state is ReadinessState.READY):
                state = GovernedOperationState.HANDOFF_ELIGIBLE
            elif (result.decision.disposition is ResultDisposition.REVIEW
                  or result.readiness.state is ReadinessState.REVIEW_REQUIRED):
                state = GovernedOperationState.REVIEW
            else:
                return unknown
            # governed scored-paper handoff has already admitted the original scored paper. Preserve its
            # actual scored question inventory for later academic consumers;
            # a new independent issuer may select only a question in this
            # immutable original, never an invented same-result question.
            scored = tx.intent.result.paper_score.question_results
            question_ids = tuple(q.question_id for q in scored)
            planned_ids = tuple(q.request.question_id for q in plan.questions)
            if (not question_ids or len(set(question_ids)) != len(question_ids)
                    or set(question_ids) != set(planned_ids)
                    or any(type(q) is not str or not q or q.strip() != q
                           or len(q) > limit for q in question_ids)):
                return unknown
            return RecoveredOriginalGovernance(state, operation, final, result,
                                               question_ids)
        except Exception:
            # No post-contact re-execution. No guess from unknown / absent history.
            return unknown
