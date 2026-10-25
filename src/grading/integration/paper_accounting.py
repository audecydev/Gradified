"""original attempt accounting: reconcile actual provider-operation records against complete physical attempt claim custody.

Fixed installed original operations are assertions from qualified sources, never
credentials created from a score. This consumer issues no provider call or retry.
Native CHOICE has no provider transport and therefore no fabricated zero usage.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.integration.attempt_lineage import _snapshot_owned
from grading.integration.whole_paper_cas import PaperCASIntent, _same_validated_value
from grading.integration.execution_eligibility import _capture, _id
from grading.integration.paper_readiness_admission import PaperAdmissionRequest, _request
from grading.integration.paper_execution_correlation import _plan, _relation
from grading.integration.attempt_authority import _request_snapshot as _original_f25_request_snapshot
from grading.integration.whole_paper_attempt_custody import _matches_paper
from grading.execution import GradingExecutionResult, GradingExecutionContext
from grading.contracts.result import PaperScoreResult
from grading.providers.accounting_recovery import (
    ReadOnlyAccountingReconciler, AccountingRecoveryDisposition,
)
from grading.providers.attempt_accounting import ProviderAttemptIdentity, _identity


class PaperAccountingState(str, Enum):
    NOT_APPLICABLE = 'NOT_APPLICABLE'
    REPORTED_RECORDED = 'REPORTED_RECORDED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class OriginalProviderOperation:
    """Qualified, fixed original provider operation, scoped to one question."""
    question_id: str
    identity: ProviderAttemptIdentity
    reconciler: ReadOnlyAccountingReconciler


@dataclass(frozen=True, slots=True, repr=False)
class PaperProviderApplicability:
    """Qualified original operation policy, not inferred from declared family."""
    request: PaperAdmissionRequest
    approval_revision: str
    provider_question_ids: tuple[str, ...]


class QualifiedOriginalPaperAccountingIntent(Protocol):
    """Read the independently selected original paper CAS intent.

    Never select history using an untrusted caller's request/attempt identifier.
    The qualified source must establish durability and authenticity externally.
    """
    def resolve_original_paper_accounting_intent(self) -> PaperCASIntent: ...


class QualifiedPaperProviderApplicability(Protocol):
    """Independently selected approved applicability; ZERO caller selectors."""
    def resolve_original_provider_applicability(self) -> PaperProviderApplicability: ...


@dataclass(frozen=True, slots=True, repr=False)
class PaperAccountingObservation:
    state: PaperAccountingState

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class ProductionPaperAccounting:
    """Fixed per-run accounting ports; no caller-provided recovery selector.

    Every declared provider-backed question must have precisely one original
    operation whose physical attempt and request match genuine paper custody.
    The composition root must supply truthful applicability and real provider
    records; this engine cannot derive vendor usage from CHOICE scores.
    """
    __slots__ = ('_original', '_maximum', '_gate', '_applicability', '_origin')

    def __init__(self, *, operations: tuple[OriginalProviderOperation, ...],
                 max_identifier_characters: int,
                 applicability_source: QualifiedPaperProviderApplicability | None = None,
                 original_intent_source: QualifiedOriginalPaperAccountingIntent | None = None) -> None:
        if (type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(operations) is not tuple):
            raise ValueError('Accounting requires a finite fixed original-operation scope.')
        original = []
        seen = (set(), set(), set())
        for record in operations:
            if (type(record) is not OriginalProviderOperation
                    or type(record.reconciler) is not ReadOnlyAccountingReconciler):
                raise ValueError('Original accounting operation must have a qualified reconciler.')
            question = _id(record.question_id, max_identifier_characters)
            identity = _identity(record.identity, max_identifier_characters)
            installed = record.reconciler._installation[0]
            if _identity(installed, max_identifier_characters) != identity:
                raise ValueError('Installed accounting read would use another operation.')
            for index, key in enumerate((question, identity.operation_ref, identity.event_ref)):
                if key in seen[index]:
                    raise ValueError('Duplicated original provider/accounting identity.')
                seen[index].add(key)
            original.append(OriginalProviderOperation(question, identity, record.reconciler))
        object.__setattr__(self, '_original', tuple(original))
        object.__setattr__(self, '_applicability', None if applicability_source is None else
            _capture(applicability_source, 'resolve_original_provider_applicability', ()))
        object.__setattr__(self, '_origin', None if original_intent_source is None else
            _capture(original_intent_source, 'resolve_original_paper_accounting_intent', ()))
        object.__setattr__(self, '_maximum', max_identifier_characters)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Original provider-accounting installation is fixed.')

    def reconcile(self, *, intent: PaperCASIntent) -> PaperAccountingObservation:
        if not self._gate.acquire(blocking=False):
            return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
        try:
            if type(intent) is not PaperCASIntent:
                return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
            try:
                baseline = _snapshot_owned(intent)
                # All physical/provider IDs must belong to one approved paper.
                # Validate the entire paper relationship BEFORE accounting read.
                plan = _plan(intent.plan, len(intent.plan.questions), self._maximum)
                issued = _relation(intent.issued, len(plan.questions), self._maximum)
                if (issued.request != plan.request
                        or issued.actor_ref != plan.actor_ref
                        or issued.paper_ref != plan.request.paper_ref
                        or issued.set_ref != plan.request.set_ref
                        or any(getattr(issued, name) != getattr(plan, name)
                               for name in ('approval_ref', 'approval_revision',
                                            'selection_decision_ref', 'selection_revision',
                                            'source_revision', 'readiness_revision'))
                        or len(issued.questions) != len(plan.questions)
                        or any((q.question_id, q.family, q.source_artifact_ref,
                                q.evidence_scope_ref, q.answer_region_ref,
                                q.source_revision, q.provenance_ref)
                               != (p.request.question_id, p.family, p.source_artifact_ref,
                                   p.evidence_scope_ref, p.answer_region_ref,
                                   p.source_revision, p.provenance_ref)
                               for q, p in zip(issued.questions, plan.questions, strict=True))):
                    raise ValueError('Provider accounting intent contradicts original issuance.')
                by_question = {q.request.question_id: q for q in plan.questions}
                if len(by_question) != len(intent.plan.questions):
                    raise ValueError('Duplicate question.')
                original_requests = {q.scope.question_id: q for q in intent.original_claim_requests}
                if len(original_requests) != len(intent.original_claim_requests):
                    raise ValueError('Duplicate original claim.')
                claims = {q[0]: q for q in intent.question_claims}
                if len(claims) != len(intent.question_claims):
                    raise ValueError('Duplicate claim.')
                # A reported provider operation is only an original physical attempt claim
                # observation when the *entire* paper's physical identities
                # and actual claim scopes are coherent. Comparing selected
                # provider IDs alone cannot establish that relationship.
                expected_ids = tuple(q.request.question_id for q in plan.questions)
                if (type(intent.original_claim_requests) is not tuple
                        or type(intent.question_claims) is not tuple
                        or len(intent.original_claim_requests) != len(expected_ids)
                        or len(intent.question_claims) != len(expected_ids)
                        or set(original_requests) != set(expected_ids)
                        or set(claims) != set(expected_ids)
                        or type(intent.result) is not GradingExecutionResult
                        or tuple(q.score.question_id for q in intent.result.questions) != expected_ids):
                    raise ValueError('Incomplete original attempt reservation and scoring inventory.')
                # The completed-paper intent must not use a score from a
                # different run/spec, or a paper aggregate for other questions.
                # This is identity validation only: do not recompute or
                # reinterpret the accepted frozen scoring arithmetic here.
                context = intent.result.context
                aggregate = intent.result.paper_score
                if (type(context) is not GradingExecutionContext
                        or type(aggregate) is not PaperScoreResult
                        or context.grading_run_id != plan.request.grading_run_id
                        or context.submission_ref != plan.request.submission_ref
                        or context.exam_ref != plan.request.exam_ref
                        or context.grading_spec_ref != plan.request.grading_spec_ref
                        or aggregate.grading_spec_ref != plan.request.grading_spec_ref
                        or aggregate.question_results != tuple(
                            q.score for q in intent.result.questions)):
                    raise ValueError('Scored candidate belongs to a different paper/run.')
                seen_reqs, seen_attempts, seen_reservations = set(), set(), set()
                for question in plan.questions:
                    qid = question.request.question_id
                    request = original_requests[qid]
                    snapshot = _original_f25_request_snapshot(request, self._maximum)
                    claim = claims[qid]
                    if (type(claim) is not tuple or len(claim) != 4
                            or snapshot[2] != question.family
                            or not _matches_paper(snapshot[0], plan, question, self._maximum)
                            or snapshot[1] != claim[1]
                            or any(_id(ref, self._maximum) != ref for ref in claim)):
                        raise ValueError('Foreign original grading-attempt claim or question scope.')
                    if (claim[1] in seen_reqs or claim[2] in seen_attempts
                            or claim[3] in seen_reservations):
                        raise ValueError('Physical attempt identity reused within paper.')
                    seen_reqs.add(claim[1])
                    seen_attempts.add(claim[2])
                    seen_reservations.add(claim[3])
                # Even a complete physical inventory is not an academic
                # original if the issued rubric/policy identity disagrees
                # with the score actually captured for that question. This
                # admits identity only; frozen scoring arithmetic is untouched.
                for issued_q, result_q in zip(issued.questions,
                                               intent.result.questions, strict=True):
                    score = result_q.score
                    if (type(score.rubric_ref.id) is not str
                            or type(score.scoring_policy_ref.id) is not str
                            or issued_q.question_id != score.question_id
                            or issued_q.rubric_ref != score.rubric_ref.id
                            or issued_q.scoring_policy_ref != score.scoring_policy_ref.id):
                        raise ValueError('Issued academic references disagree with scored paper.')
                # Native CHOICE never uses an external provider. For other
                # families, only an approved source can decide applicability;
                # family name by itself cannot invent transport or zero usage.
                nonchoice = {q.request.question_id for q in intent.plan.questions if q.family != 'CHOICE'}
                declared = {p.question_id for p in self._original}
                if declared - nonchoice:
                    raise ValueError('Provider operation claimed for native CHOICE or foreign question.')
                if self._applicability is None:
                    if nonchoice:
                        return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
                    needs = set()
                else:
                    try:
                        original_applicability = self._applicability()
                    except Exception:
                        # A missing external applicability decision is NOT a
                        # definitive conflict, nor approval of no transport.
                        if _snapshot_owned(intent) != baseline:
                            return PaperAccountingObservation(PaperAccountingState.CONFLICT)
                        return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
                    if (type(original_applicability) is not PaperProviderApplicability
                            or _request(original_applicability.request, self._maximum) != intent.plan.request
                            or _id(original_applicability.approval_revision, self._maximum) != intent.plan.approval_revision
                            or type(original_applicability.provider_question_ids) is not tuple):
                        raise ValueError('Provider applicability not bound to original paper.')
                    approved_ids = tuple(_id(q, self._maximum)
                                         for q in original_applicability.provider_question_ids)
                    if len(set(approved_ids)) != len(approved_ids):
                        raise ValueError('Duplicate provider applicability question.')
                    needs = set(approved_ids)
                    if needs - nonchoice:
                        raise ValueError('Provider applicability includes native CHOICE or foreign question.')
                if declared != needs:
                    return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
                # Provider-accounting positive must bind to a separately fixed
                # ORIGINAL physical attempt claim/CAS history, not a caller-constructed matching
                # request. This is a qualified source-of-record contract, not
                # proof of actual backend authentication by Python equality.
                if self._original:
                    if self._origin is None:
                        return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
                    try:
                        original_intent = self._origin()  # NO caller selector
                    except Exception:
                        if _snapshot_owned(intent) != baseline:
                            return PaperAccountingObservation(PaperAccountingState.CONFLICT)
                        return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
                    if (type(original_intent) is not PaperCASIntent
                            or not _same_validated_value(original_intent, intent)):
                        raise ValueError('Accounting intent not bound to original qualified paper.')
                    original_snapshot = _snapshot_owned(original_intent)
                for port in self._original:
                    request = original_requests[port.question_id]
                    claim = claims[port.question_id]
                    if (port.identity.request_ref != request.request_ref
                            or port.identity.attempt_id != claim[2]
                            or request.request_ref != claim[1]
                            or _identity(port.reconciler._installation[0], self._maximum) != port.identity):
                        raise ValueError('Provider operation differs from actual grading-attempt custody.')
                if _snapshot_owned(intent) != baseline:
                    raise ValueError('Paper authority changed before provider reads.')
            except Exception:
                return PaperAccountingObservation(PaperAccountingState.CONFLICT)
            if not self._original:
                return PaperAccountingObservation(PaperAccountingState.NOT_APPLICABLE)
            for port in self._original:
                try:
                    fact = port.reconciler.reconcile()
                    if (_snapshot_owned(intent) != baseline
                            or (self._original and _snapshot_owned(original_intent) != original_snapshot)
                            or _identity(fact.identity, self._maximum) != port.identity):
                        return PaperAccountingObservation(PaperAccountingState.CONFLICT)
                    if fact.disposition is AccountingRecoveryDisposition.CONFLICT:
                        return PaperAccountingObservation(PaperAccountingState.CONFLICT)
                    if (fact.disposition is not AccountingRecoveryDisposition.RECORDED
                            or fact.recorded_status != 'RESULT_RETURNED'):
                        return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
                except Exception:
                    return PaperAccountingObservation(PaperAccountingState.UNKNOWN)
            # This means reported accounting events were recorded; it is NOT
            # proof of complete numeric telemetry or actual backend durability.
            return PaperAccountingObservation(PaperAccountingState.REPORTED_RECORDED)
        finally:
            self._gate.release()
