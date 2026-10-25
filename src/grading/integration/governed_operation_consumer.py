"""Connect actual scored paper operations to independent governed-result readers.

A CAS observation is NOT an official result or a permission to publish.  The
source supplies an independently recovered original/policy reference, and the
existing four-reader + three-view mechanism determines only handoff readiness.
This module neither authenticates the school nor persists/publishes results.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.integration.execution_eligibility import _capture
from grading.integration.governed_original_assessment import GovernedOriginalKey
from grading.integration.governed_paper_handoff import (
    GovernedPaperHandoff, ProductionGovernedPaperHandoff,
)
from grading.integration.governed_result_disposition import ResultDisposition
from grading.integration.assessment_readiness_views import ReadinessState
from grading.integration.paper_readiness_admission import PaperAdmissionRequest, _request
from grading.integration.production_paper_operations import (
    PaperOperationKind, PaperOperationObservation, ProductionPaperOperations,
)
from grading.integration.paper_lifecycle import (
    PaperLifecycleState, PaperLifecycleKind, PaperLifecycleObservation,
)
from grading.integration.paper_retry_grading import GradedRetryOutcome, GradedRetryState
from grading.integration.whole_paper_cas import (
    PaperCASOutcome, PaperCASState, PaperCASTransaction, _receipt,
)


class GovernedOperationState(str, Enum):
    BLOCKED = 'BLOCKED'
    UNKNOWN = 'UNKNOWN'
    REVIEW = 'REVIEW'
    HANDOFF_ELIGIBLE = 'HANDOFF_ELIGIBLE'


@dataclass(frozen=True, slots=True)
class ScoredOperationIdentity:
    """Bounded original-scored-CAS observation, never a bearer authorization."""
    kind: PaperOperationKind
    tenant_ref: str
    grading_run_id: str
    original_scored_result_ref: str
    source_revision: str
    transaction_ref: str
    transaction_event_ref: str
    commit_ref: str


class GovernedOriginalSource(Protocol):
    """Trusted adapter independently reads this exact scored original/policy."""
    def read_governed_original(self, *, operation: ScoredOperationIdentity) -> GovernedOriginalKey: ...


@dataclass(frozen=True, slots=True)
class GovernedOperationOutcome:
    state: GovernedOperationState
    operation: PaperOperationObservation
    handoff: GovernedPaperHandoff | None = None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class ProductionGovernedOperationConsumer:
    """One nonpublishing consuming entry over installed real production owners.

    The four independent original readers and the three readiness readers are
    already owned by ProductionGovernedPaperHandoff.  Missing/late/malformed
    recovery remains UNKNOWN; we never invoke physical attempt claim/CAS a second time to recover.
    """
    __slots__ = ('_execute', '_read', '_handoff', '_limit')

    def __init__(self, *, operations: ProductionPaperOperations,
                 original_source: GovernedOriginalSource,
                 handoff: ProductionGovernedPaperHandoff,
                 max_identifier_characters: int):
        if (type(operations) is not ProductionPaperOperations
                or type(handoff) is not ProductionGovernedPaperHandoff
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or operations._max != max_identifier_characters):
            raise ValueError('Installed strict paper and governed original owners required.')
        object.__setattr__(self, '_execute', operations.execute)
        object.__setattr__(self, '_read', _capture(original_source,
            'read_governed_original', ('operation',)))
        object.__setattr__(self, '_handoff', handoff)
        object.__setattr__(self, '_limit', max_identifier_characters)

    def __setattr__(self, name, value):
        raise AttributeError('Governed operation installation is immutable.')

    def execute_and_assess(self, *, request: PaperAdmissionRequest,
                           kind: PaperOperationKind) -> GovernedOperationOutcome:
        limit = self._limit
        original = _request(request, limit)
        if type(kind) is not PaperOperationKind:
            raise ValueError('Exact paper operation kind required.')
        # Never swallow a failed school admission as a successful grading run.
        execute, source, handoff = self._execute, self._read, self._handoff
        observation = execute(request=original, kind=kind)
        if (type(observation) is not PaperOperationObservation
                or observation.kind is not kind):
            raise RuntimeError('Installed paper root returned an invalid operation.')
        def unavailable():
            return GovernedOperationOutcome(GovernedOperationState.UNKNOWN, observation)
        # A source/backend callback may invalidate the caller-owned request
        # after scored CAS. Do not discard a committed operation by leaking
        # an input-validation exception from this post-effect comparison.
        try:
            caller_unchanged = _request(request, limit) == original
        except Exception:
            caller_unchanged = False
        if (not caller_unchanged
                or self._execute is not execute or self._read is not source
                or self._handoff is not handoff or self._limit != limit):
            return unavailable()
        executed = observation.execution
        if kind is PaperOperationKind.RETRY:
            if type(executed) is not GradedRetryOutcome:
                return unavailable()
            if executed.state is not GradedRetryState.CAS_ACKNOWLEDGED:
                state = (GovernedOperationState.BLOCKED if executed.state in (
                    GradedRetryState.PRE_EFFECT_BLOCKED, GradedRetryState.CAS_BLOCKED)
                    else GovernedOperationState.UNKNOWN)
                return GovernedOperationOutcome(state, observation)
            cas = executed.cas
        else:
            if type(executed) is not PaperLifecycleObservation:
                return unavailable()
            if executed.state is not PaperLifecycleState.CAS_ACKNOWLEDGED:
                state = (GovernedOperationState.BLOCKED if executed.state in (
                    PaperLifecycleState.PRE_EFFECT_BLOCKED, PaperLifecycleState.CAS_BLOCKED)
                    else GovernedOperationState.UNKNOWN)
                return GovernedOperationOutcome(state, observation)
            if executed.kind is not (PaperLifecycleKind.FIRST if kind is PaperOperationKind.FIRST
                                      else PaperLifecycleKind.REGRADE):
                return unavailable()
            cas = executed.cas
        if (type(cas) is not PaperCASOutcome
                or cas.state is not PaperCASState.COMMITTED
                or cas.academic_binding_verified is not True
                or type(cas.transaction) is not PaperCASTransaction):
            return unavailable()
        try:
            transaction = cas.transaction
            planned = transaction.intent.plan
            # Original CAS identity, not a caller-selected or recovered/latest
            # transaction. Never call a reader for a mismatched original.
            if (type(planned.request) is not PaperAdmissionRequest
                    or _request(planned.request, limit) != original
                    or type(planned.source_revision) is not str):
                return unavailable()
            revision = planned.source_revision
            refs = (transaction.result_ref, transaction.request_ref,
                    transaction.event_ref, revision)
            if any(type(v) is not str or not v or v.strip() != v or len(v) > limit
                   for v in refs):
                return unavailable()
            receipt = _receipt(cas.receipt, transaction, limit)
            identity = ScoredOperationIdentity(kind, original.tenant_ref,
                original.grading_run_id, transaction.result_ref, revision,
                transaction.request_ref, transaction.event_ref, receipt.commit_ref)
            # Check the actual scored operation is the one this owner just ran.
            if (cas.custody.plan != planned or cas.custody.plan.request != original):
                return unavailable()
        except Exception:
            return unavailable()
        def source_still_original():
            try:
                return (cas.state is PaperCASState.COMMITTED
                    and cas.academic_binding_verified is True
                    and cas.transaction is transaction
                    and cas.receipt is not None
                    and cas.receipt.commit_ref == identity.commit_ref
                    and transaction.result_ref == identity.original_scored_result_ref
                    and transaction.request_ref == identity.transaction_ref
                    and transaction.event_ref == identity.transaction_event_ref
                    and transaction.intent.plan.request == original
                    and transaction.intent.plan.source_revision == identity.source_revision
                    and cas.custody.plan == planned)
            except Exception:
                return False
        try:
            key = source(operation=ScoredOperationIdentity(*(
                identity.kind, identity.tenant_ref, identity.grading_run_id,
                identity.original_scored_result_ref, identity.source_revision,
                identity.transaction_ref, identity.transaction_event_ref,
                identity.commit_ref)))
            if type(key) is not GovernedOriginalKey:
                return unavailable()
            strings = (key.tenant_ref, key.grading_run_id, key.original_scored_result_ref,
                       key.source_revision, key.policy_ref, key.policy_revision)
            if (any(type(v) is not str or not v or v.strip() != v or len(v) > limit
                    for v in strings)
                    or strings[:4] != (identity.tenant_ref, identity.grading_run_id,
                                      identity.original_scored_result_ref, identity.source_revision)
                    or self._execute is not execute or self._read is not source
                    or self._handoff is not handoff or self._limit != limit
                    or _request(request, limit) != original
                    or not source_still_original()):
                return unavailable()
            result = handoff.assess(original=GovernedOriginalKey(*strings))
            if (type(result) is not GovernedPaperHandoff
                    or result.decision.tenant_ref != strings[0]
                    or result.decision.grading_run_id != strings[1]
                    or result.decision.original_scored_result_ref != strings[2]
                    or result.decision.source_revision != strings[3]
                    or result.decision.policy_ref != strings[4]
                    or result.decision.policy_revision != strings[5]
                    or (result.readiness.origin.tenant_ref, result.readiness.origin.grading_run_id,
                        result.readiness.origin.scored_result_ref, result.readiness.origin.source_revision)
                       != strings[:4]
                    or self._execute is not execute or self._read is not source
                    or self._handoff is not handoff or self._limit != limit
                    or _request(request, limit) != original
                    or not source_still_original()):
                return unavailable()
            if (result.decision.disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
                    and result.readiness.state is ReadinessState.READY):
                state = GovernedOperationState.HANDOFF_ELIGIBLE
            elif (result.decision.disposition is ResultDisposition.REVIEW
                  or result.readiness.state is ReadinessState.REVIEW_REQUIRED):
                state = GovernedOperationState.REVIEW
            else:
                state = GovernedOperationState.UNKNOWN
            return GovernedOperationOutcome(state, observation, result)
        except Exception:
            # Scoring has already happened: retain its observation; never
            # return to the physical attempt claim/score/CAS contact to re-run an unknown result.
            return unavailable()
