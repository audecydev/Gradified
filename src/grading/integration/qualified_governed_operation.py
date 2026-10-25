"""Read-only governed scored-paper handoff-qualified continuation of a real, scored governed operation.

This is an additional, stricter nonpublishing consumer.  It never grades,
replays CAS/physical attempt claim, queries an alternative original, or grants publication.
The installed governed scored-paper handoff owner must independently recover the exact scored original.
"""
from __future__ import annotations

from dataclasses import dataclass

from grading.integration.governed_operation_consumer import (
    GovernedOperationOutcome, GovernedOperationState,
    ProductionGovernedOperationConsumer,
)
from grading.integration.scored_paper_promotion import (
    PaperHandoffEligibilityState, PaperHandoffAssessment, ProductionPaperPromotion,
)
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.paper_readiness_admission import PaperAdmissionRequest
from grading.integration.whole_paper_cas import PaperCASOutcome, PaperCASTransaction, PaperCASState


@dataclass(frozen=True, slots=True)
class OriginalQualifiedGovernedOutcome:
    state: GovernedOperationState
    governed: GovernedOperationOutcome
    original_c5: PaperHandoffAssessment | None = None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class ProductionOriginalQualifiedGovernedConsumer:
    """Require the SAME originally committed paper at governance and governed scored-paper handoff.

    The existing governed consumer only assesses original academic/readiness
    records.  This stricter entry also requires the independently sourced,
    read-only governed scored-paper handoff legal operation transition/physical attempt claim/accounting/audit assessment for the actual CAS.
    A foreign, missing, conflicting or uncertain governed scored-paper handoff record is never eligible.
    The governed scored-paper handoff adapter's authenticity, physical provenance and durable reads are
    genuine integration gates, not inferred from object types or IDs.
    """
    __slots__ = ('_governed', '_c5')

    def __init__(self, *, governed: ProductionGovernedOperationConsumer):
        if type(governed) is not ProductionGovernedOperationConsumer:
            raise ValueError('Exact installed governed-operation consumer required.')
        operations = governed._execute.__self__
        c5 = operations._promotion
        if type(c5) is not ProductionPaperPromotion:
            raise ValueError('Actual strict-root scored-paper promotion installation required.')
        object.__setattr__(self, '_governed', governed)
        object.__setattr__(self, '_c5', c5)

    def __setattr__(self, name, value):
        raise AttributeError('Original-qualified governed installation is immutable.')

    def execute_and_assess(self, *, request: PaperAdmissionRequest,
                           kind: PaperOperationKind) -> OriginalQualifiedGovernedOutcome:
        # Admission errors remain the original typed pre-effect failures.
        observation = self._governed.execute_and_assess(request=request, kind=kind)
        def uncertain(c5=None):
            return OriginalQualifiedGovernedOutcome(GovernedOperationState.UNKNOWN,
                                                     observation, c5)
        if (type(observation) is not GovernedOperationOutcome
                or observation.state is not GovernedOperationState.HANDOFF_ELIGIBLE):
            return OriginalQualifiedGovernedOutcome(observation.state, observation)
        try:
            cas = observation.operation.execution.cas
            if (type(cas) is not PaperCASOutcome
                    or cas.state is not PaperCASState.COMMITTED
                    or type(cas.transaction) is not PaperCASTransaction
                    or cas.receipt is None
                    or self._governed._execute.__self__._promotion is not self._c5):
                return uncertain()
            transaction = cas.transaction
            commit = cas.receipt.commit_ref
            if type(commit) is not str or not commit:
                return uncertain()
            result = self._c5.assess(expected_transaction=transaction,
                                     expected_commit_ref=commit)
            if (type(result) is not PaperHandoffAssessment
                    or result.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
                    or self._governed._execute.__self__._promotion is not self._c5
                    or observation.operation.execution.cas is not cas
                    or cas.transaction is not transaction
                    or cas.receipt.commit_ref != commit):
                return uncertain(result if type(result) is PaperHandoffAssessment else None)
            return OriginalQualifiedGovernedOutcome(
                GovernedOperationState.HANDOFF_ELIGIBLE, observation, result)
        except Exception:
            # Post-CAS recovery cannot start another physical attempt.
            return uncertain()
