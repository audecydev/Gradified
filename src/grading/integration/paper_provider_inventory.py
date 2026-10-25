"""physical provider inventory: original physical provider operations, including incomplete paper attempts.

Separate real transport events from the logical question and from metric/cost
completeness. This module never invents transport for deterministic CHOICE,
reconstructs a score for an incomplete paper, or issues provider requests.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.integration.attempt_authority import AttemptClaimRequest, _request_snapshot
from grading.integration.attempt_lineage import _snapshot_owned
from grading.integration.execution_eligibility import _capture, _id
from grading.integration.paper_execution_correlation import _plan, _relation
from grading.integration.whole_paper_attempt_custody import _matches_paper
from grading.integration.evaluator_invocation import AttemptReservation, _reservation_copy
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.paper_execution_correlation import IssuedPaperExecutionRelation
from grading.providers.accounting_recovery import AccountingRecoveryDisposition, ReadOnlyAccountingReconciler
from grading.providers.attempt_accounting import ProviderAttemptIdentity, _identity


class QuestionTransportDisposition(str, Enum):
    PROVIDER_REQUIRED = 'PROVIDER_REQUIRED'
    APPROVED_NO_TRANSPORT = 'APPROVED_NO_TRANSPORT'
    UNRESOLVED = 'UNRESOLVED'


class ProviderInventoryState(str, Enum):
    NOT_APPLICABLE = 'NOT_APPLICABLE'
    EVENTS_RECORDED = 'EVENTS_RECORDED'  # does not prove metric completeness
    COMPLETENESS_REPORTED = 'COMPLETENESS_REPORTED'  # metric names only, not values
    MEASUREMENTS_REPORTED = 'MEASUREMENTS_REPORTED'  # bounded actual Decimal values reported per operation
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class PhysicalProviderOperation:
    question_id: str
    identity: ProviderAttemptIdentity
    recovery: ReadOnlyAccountingReconciler


@dataclass(frozen=True, slots=True, repr=False)
class PhysicalAttemptObservation:
    question_id: str
    f25_contact_started: bool
    original_request: AttemptClaimRequest | None
    reservation: AttemptReservation | None


@dataclass(frozen=True, slots=True, repr=False)
class OriginalProviderInventory:
    """Original physical call history independent of a completed academic score.

    Unlike PaperCASIntent/PaperAttemptCustody, this supports every admitted
    family without pretending a failed provider execution completed CHOICE.
    """
    plan: AdmittedPaperPlan
    issued: IssuedPaperExecutionRelation | None
    f25_observations: tuple[PhysicalAttemptObservation, ...]
    inventory_ref: str
    required_question_ids: tuple[str, ...]
    operations: tuple[PhysicalProviderOperation, ...]
    complete_operation_inventory: bool


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplicabilityFact:
    """Qualified versioned, whole-paper provider requirement/exception decision.

    A source configured by the trusted composition root must genuinely own the
    policy and original paper; this structural record does not authenticate it.
    """
    inventory_ref: str
    plan: AdmittedPaperPlan
    policy_id: str
    policy_version: int
    question_dispositions: tuple[tuple[str, QuestionTransportDisposition], ...]


@dataclass(frozen=True, slots=True, repr=False)
class ProviderCompletenessFact:
    """Versioned provider-policy assertion; no invented metric or zero-value."""
    inventory_ref: str
    policy_id: str
    policy_version: int
    operation_refs: tuple[str, ...]
    required_measurements: tuple[str, ...]
    present_measurements: tuple[str, ...]
    complete: bool


@dataclass(frozen=True, slots=True, repr=False)
class PhysicalProviderMeasurement:
    metric_ref: str
    unit_ref: str
    value: Decimal  # exact, finite; real metric/rate meaning is externally approved
    evidence_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class OperationMeasurementFact:
    operation_ref: str
    source_ref: str
    measurements: tuple[PhysicalProviderMeasurement, ...]


@dataclass(frozen=True, slots=True, repr=False)
class ProviderMeasurementInventory:
    inventory_ref: str
    policy_id: str
    policy_version: int
    operations: tuple[OperationMeasurementFact, ...]
    complete: bool


@dataclass(frozen=True, slots=True, repr=False)
class ProviderInventoryObservation:
    state: ProviderInventoryState
    plan: AdmittedPaperPlan | None = None
    original_requests: tuple[AttemptClaimRequest | None, ...] = ()
    physical_reservations: tuple[AttemptReservation | None, ...] = ()
    required_question_ids: tuple[str, ...] = ()
    operation_refs: tuple[str, ...] = ()
    # Immutable detached *source-reported* evidence. This is not an invoice,
    # authenticated provider ledger or an approved metric interpretation.
    measurement_policy: tuple[str, int] | None = None
    measurement_evidence: tuple[OperationMeasurementFact, ...] = ()
    # Bounded, detached original physical event outcomes, for the independent
    # original attempt accounting/physical provider inventory original-transport join. Additional operations may share a question.
    original_operations: tuple[tuple[str, ProviderAttemptIdentity, str], ...] = ()

    @property
    def authorizes_publication(self): return False

    @property
    def authorizes_retry(self): return False


class QualifiedOriginalProviderInventory(Protocol):
    """Select fixed original paper/calls, without untrusted caller selector."""
    def resolve_original_provider_inventory(self) -> OriginalProviderInventory: ...


class QualifiedProviderCompletenessSource(Protocol):
    """Only a policy owner/provider backend can attest required usage fields."""
    def resolve_provider_completeness(self) -> ProviderCompletenessFact: ...


class QualifiedProviderApplicabilitySource(Protocol):
    """Fixed-origin whole-paper question transport policy; no caller lookup key."""
    def resolve_provider_applicability(self) -> ProviderApplicabilityFact: ...


class QualifiedProviderMeasurementSource(Protocol):
    """Fixed-origin, genuinely persisted per-operation metric evidence.

    The external policy determines what each metric/unit means; this consumer
    merely validates exact nonfloating records and their correlation.
    """
    def resolve_provider_measurements(self) -> ProviderMeasurementInventory: ...


class ProductionProviderInventory:
    """Read real per-operation event receipts, then optional metric completeness.

    One question can have several physical provider operations. An incomplete
    grading outcome can have billable transport; it must never be disguised as
    a PaperCASIntent containing a complete/fabricated score.
    """
    __slots__=('_source','_completeness','_applicability','_measurements','_max','_questions','_max_ops','_max_metrics','_max_digits','_max_exponent','_gate')

    def __init__(self, *, original_source: QualifiedOriginalProviderInventory,
                 max_identifier_characters: int, max_questions: int,
                 completeness_source: QualifiedProviderCompletenessSource | None = None,
                 applicability_source: QualifiedProviderApplicabilitySource | None = None,
                 measurement_source: QualifiedProviderMeasurementSource | None = None,
                 max_physical_operations: int = 10000,
                 max_measurement_entries: int = 256,
                 max_measurement_coefficient_digits: int = 128,
                 max_measurement_absolute_exponent: int = 1024):
        if (type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000
                or type(max_physical_operations) is not int
                or not 0 < max_physical_operations <= 1000000
                or type(max_measurement_entries) is not int
                or not 0 < max_measurement_entries <= 100000
                or type(max_measurement_coefficient_digits) is not int
                or not 0 < max_measurement_coefficient_digits <= 4096
                or type(max_measurement_absolute_exponent) is not int
                or not 0 < max_measurement_absolute_exponent <= 100000):
            raise ValueError('Finite provider inventory bounds are required.')
        object.__setattr__(self,'_source',_capture(original_source,
            'resolve_original_provider_inventory',()))
        object.__setattr__(self,'_completeness', None if completeness_source is None else
            _capture(completeness_source,'resolve_provider_completeness',()))
        object.__setattr__(self,'_applicability', None if applicability_source is None else
            _capture(applicability_source,'resolve_provider_applicability',()))
        object.__setattr__(self,'_measurements', None if measurement_source is None else
            _capture(measurement_source,'resolve_provider_measurements',()))
        object.__setattr__(self,'_max_ops',max_physical_operations)
        object.__setattr__(self,'_max_metrics',max_measurement_entries)
        object.__setattr__(self,'_max_digits',max_measurement_coefficient_digits)
        object.__setattr__(self,'_max_exponent',max_measurement_absolute_exponent)
        object.__setattr__(self,'_max',max_identifier_characters)
        object.__setattr__(self,'_questions',max_questions)
        object.__setattr__(self,'_gate',Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Original provider inventory installation is immutable.')

    def reconcile(self) -> ProviderInventoryObservation:
        if not self._gate.acquire(blocking=False):
            return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
        try:
            try:
                fact = self._source()
            except Exception:
                return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
            try:
                if (type(fact) is not OriginalProviderInventory
                        or type(fact.operations) is not tuple
                        or type(fact.f25_observations) is not tuple
                        or type(fact.required_question_ids) is not tuple
                        or type(fact.complete_operation_inventory) is not bool
                        or len(fact.operations) > self._max_ops):
                    raise ValueError('Original provider inventory has foreign type.')
                plan=_plan(fact.plan,self._questions,self._max)
                original_plan=_snapshot_owned(fact.plan)
                inventory_ref=_id(fact.inventory_ref,self._max)
                required=tuple(_id(q,self._max) for q in fact.required_question_ids)
                if len(set(required)) != len(required):
                    raise ValueError('Repeated provider question in original inventory.')
                qids=tuple(p.request.question_id for p in plan.questions)
                plan_by_id={p.request.question_id:p for p in plan.questions}
                if not set(required).issubset(qids):
                    raise ValueError('Foreign provider question.')
                # An inventory subset is not evidence that omitted non-CHOICE
                # questions had no physical transport. Only independently
                # installed whole-paper, versioned applicability can assert it.
                applicability_snapshot = None
                if self._applicability is None:
                    if any(q.family != 'CHOICE' and q.request.question_id not in required
                           for q in plan.questions):
                        return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                else:
                    try:
                        app = self._applicability()
                        if (type(app) is not ProviderApplicabilityFact
                                or app.inventory_ref != inventory_ref
                                or _plan(app.plan,self._questions,self._max) != plan
                                or not _id(app.policy_id,self._max)
                                or type(app.policy_version) is not int
                                or app.policy_version <= 0
                                or type(app.question_dispositions) is not tuple
                                or len(app.question_dispositions) != len(qids)):
                            raise ValueError('Foreign applicability attestation.')
                        classification = {}
                        for line in app.question_dispositions:
                            if (type(line) is not tuple or len(line) != 2
                                    or type(line[1]) is not QuestionTransportDisposition):
                                raise ValueError('Malformed provider applicability line.')
                            qid = _id(line[0],self._max)
                            if qid in classification:
                                raise ValueError('Repeated question applicability.')
                            classification[qid] = line[1]
                        if tuple(classification) != qids:
                            raise ValueError('Incomplete/unsorted question applicability.')
                        for question in plan.questions:
                            state = classification[question.request.question_id]
                            if (state is QuestionTransportDisposition.UNRESOLVED
                                    or (question.family == 'DIRECT' and
                                        state is not QuestionTransportDisposition.PROVIDER_REQUIRED)
                                    or (state is QuestionTransportDisposition.PROVIDER_REQUIRED)
                                       != (question.request.question_id in required)
                                    or (question.family == 'CHOICE'
                                        and state is QuestionTransportDisposition.PROVIDER_REQUIRED)):
                                return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                        applicability_snapshot = _snapshot_owned(app)
                    except Exception:
                        return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                if (len(fact.f25_observations) != len(qids)
                        or tuple(x.question_id for x in fact.f25_observations) != qids):
                    raise ValueError('Original grading-attempt inventory must cover every admitted question.')
                by_id={}
                attempts=set(); reservations=set(); req_refs=set()
                for q, pq in zip(fact.f25_observations,plan.questions,strict=True):
                    if (type(q) is not PhysicalAttemptObservation
                            or type(q.f25_contact_started) is not bool):
                        raise ValueError('Foreign grading-attempt observation.')
                    if q.original_request is None:
                        if q.reservation is not None:
                            raise ValueError('Reservation has no original request.')
                        if q.f25_contact_started:
                            # A call could have begun without recoverable origin;
                            # never accept an invented negative claim.
                            return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                    else:
                        original=_request_snapshot(q.original_request,self._max)
                        if (not q.f25_contact_started
                                or original[2] != pq.family
                                or not _matches_paper(original[0],plan,pq,self._max)
                                or original[1] in req_refs):
                            raise ValueError('Original grading-attempt request foreign or duplicated.')
                        req_refs.add(original[1])
                        if q.reservation is not None:
                            if type(q.reservation) is not AttemptReservation:
                                raise ValueError('Invalid physical reservation type.')
                            expectation=AttemptReservation(original[0],'','',*original[2:8],
                                request_ref=original[1],
                                predecessor_result_ref=original[8],
                                regrade_approval_ref=original[9])
                            physical=_reservation_copy(q.reservation,expected=expectation,
                                                       maximum=self._max)
                            if (physical.request_ref != original[1]
                                    or physical.attempt_id in attempts
                                    or physical.reservation_ref in reservations):
                                raise ValueError('Duplicate or foreign physical attempt claim.')
                            attempts.add(physical.attempt_id)
                            reservations.add(physical.reservation_ref)
                    by_id[q.question_id]=q
                # Do not fabricate issuance if admission failed before contact.
                if fact.issued is None:
                    if required or fact.operations:
                        return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                else:
                    issued=_relation(fact.issued,self._questions,self._max)
                    if (issued.request != plan.request or issued.actor_ref != plan.actor_ref
                            or issued.paper_ref != plan.request.paper_ref
                            or issued.set_ref != plan.request.set_ref
                            or any(getattr(issued,key) != getattr(plan,key)
                                   for key in ('approval_ref','approval_revision',
                                               'selection_decision_ref','selection_revision',
                                               'source_revision','readiness_revision'))
                            or len(issued.questions) != len(plan.questions)
                            or any((iq.question_id,iq.family,iq.source_artifact_ref,
                                    iq.evidence_scope_ref,iq.answer_region_ref,
                                    iq.source_revision,iq.provenance_ref)
                                != (pq.request.question_id,pq.family,pq.source_artifact_ref,
                                    pq.evidence_scope_ref,pq.answer_region_ref,
                                    pq.source_revision,pq.provenance_ref)
                                for iq,pq in zip(issued.questions,plan.questions,strict=True))):
                        raise ValueError('Provider inventory has contradictory original issuance.')
                verified=[]
                used_ops=set(); used_events=set(); by_q={q:0 for q in required}
                for item in fact.operations:
                    if (type(item) is not PhysicalProviderOperation
                            or type(item.recovery) is not ReadOnlyAccountingReconciler):
                        raise ValueError('Unqualified provider physical operation.')
                    qid=_id(item.question_id,self._max)
                    identity=_identity(item.identity,self._max)
                    if (qid not in by_q or plan_by_id[qid].family == 'CHOICE'
                            or identity.operation_ref in used_ops
                            or identity.event_ref in used_events
                            or _identity(item.recovery._installation[0],self._max) != identity):
                        raise ValueError('Foreign, duplicate or CHOICE provider operation.')
                    q=by_id[qid]
                    original_request=q.original_request
                    if q.reservation is None or original_request is None:
                        # Provider transport may exist after a partial failure,
                        # but a missing authenticated physical attempt claim mapping is NOT permission
                        # to guess the physical attempt that incurred it.
                        return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                    original=_request_snapshot(original_request,self._max)
                    if (original[2] != plan_by_id[qid].family
                            or not _matches_paper(original[0],plan,plan_by_id[qid],self._max)
                            or original[1] != identity.request_ref
                            or q.reservation.request_ref != identity.request_ref
                            or q.reservation.attempt_id != identity.attempt_id):
                        raise ValueError('Provider operation not bound to admitted grading-attempt identity.')
                    used_ops.add(identity.operation_ref);used_events.add(identity.event_ref)
                    by_q[qid]+=1
                    verified.append(item)
                if set(required) != set(by_q):
                    raise ValueError('Missing provider question admission.')
                if (_snapshot_owned(fact.plan) != original_plan):
                    raise ValueError('Provider original changed across admission.')
                # Installed reader objects are qualified executable ports, not
                # serializable record values. Snapshot only original records,
                # then check each installed reader identity before every read.
                def original_snapshot():
                    return _snapshot_owned((fact.plan, fact.issued, fact.f25_observations,
                        fact.inventory_ref, fact.required_question_ids,
                        fact.complete_operation_inventory,
                        tuple((op.question_id,op.identity) for op in fact.operations)))
                baseline=original_snapshot()
                def applicability_unchanged():
                    return (applicability_snapshot is None or
                            _snapshot_owned(app) == applicability_snapshot)
                bound = (plan, tuple(q.original_request for q in fact.f25_observations),
                         tuple(q.reservation for q in fact.f25_observations), required,
                         tuple(item.identity.operation_ref for item in verified))
            except Exception:
                return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
            if not applicability_unchanged():
                return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
            if not fact.complete_operation_inventory:
                return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
            if required and any(by_q[q] == 0 for q in required):
                # Without an explicit source-of-record 'zero operations' policy,
                # absence of receipts cannot be treated as confirmed no cost.
                return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
            if not required and not fact.operations:
                # Only the native CHOICE evaluator is established to avoid
                # provider transport. Other families require explicit approved
                # no-transport semantics, not an empty inventory assertion.
                if (self._applicability is None and
                        any(q.family != 'CHOICE' for q in plan.questions)):
                    return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                return ProviderInventoryObservation(ProviderInventoryState.NOT_APPLICABLE, *bound)
            recorded_events=[]
            for item in verified:
                try:
                    response=item.recovery.reconcile()
                    if (not applicability_unchanged() or original_snapshot() != baseline
                            or _identity(item.recovery._installation[0],self._max) !=
                               _identity(item.identity,self._max)
                            or _identity(response.identity,self._max) != _identity(item.identity,self._max)):
                        return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                    if response.disposition is AccountingRecoveryDisposition.CONFLICT:
                        return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                    if response.disposition is not AccountingRecoveryDisposition.RECORDED or \
                            response.recorded_status not in ('RESULT_RETURNED','INDETERMINATE'):
                        return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                    recorded_events.append((item.question_id,
                        _identity(item.identity, self._max), response.recorded_status))
                except Exception:
                    return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
            if self._completeness is None:
                return ProviderInventoryObservation(ProviderInventoryState.EVENTS_RECORDED, *bound)
            try:
                completion=self._completeness()
                if (type(completion) is not ProviderCompletenessFact
                        or completion.inventory_ref != inventory_ref
                        or _id(completion.policy_id,self._max) == ''
                        or type(completion.policy_version) is not int
                        or type(completion.complete) is not bool
                        or completion.policy_version <= 0
                        or type(completion.operation_refs) is not tuple
                        or tuple(completion.operation_refs) != tuple(
                            x.identity.operation_ref for x in verified)
                        or type(completion.required_measurements) is not tuple
                        or len(completion.required_measurements) > self._max_metrics
                        or len(completion.present_measurements) > self._max_metrics
                        or type(completion.present_measurements) is not tuple):
                    return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                required_metrics=tuple(_id(x,self._max) for x in completion.required_measurements)
                observed_metrics=tuple(_id(x,self._max) for x in completion.present_measurements)
                if (not required_metrics or len(set(required_metrics)) != len(required_metrics)
                        or len(set(observed_metrics)) != len(observed_metrics)
                        or not set(required_metrics).issubset(observed_metrics)
                        or not applicability_unchanged() or original_snapshot() != baseline):
                    return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                if not completion.complete:
                    return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
                if self._measurements is None:
                    # A boolean and a list of metric NAMES are not actual usage
                    # values, still less provider-authenticated billing totals.
                    return ProviderInventoryObservation(ProviderInventoryState.COMPLETENESS_REPORTED, *bound)
                # Keep the *original* admitted completeness policy independent
                # of the measurement reader. That callback cannot revise the
                # measurement requirements for its own returned observations.
                original_completion = _snapshot_owned(completion)
                measured = self._measurements()
                if _snapshot_owned(completion) != original_completion:
                    return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                if (type(measured) is not ProviderMeasurementInventory
                        or measured.inventory_ref != inventory_ref
                        or measured.policy_id != completion.policy_id
                        or type(measured.policy_version) is not int
                        or measured.policy_version != completion.policy_version
                        or type(measured.complete) is not bool
                        or not measured.complete
                        or type(measured.operations) is not tuple
                        or len(measured.operations) != len(verified)
                        or len(measured.operations) > self._max_ops):
                    return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                total_metrics = 0
                accepted_measurements=[]
                for actual_op, expected_op in zip(measured.operations,verified,strict=True):
                    if (type(actual_op) is not OperationMeasurementFact
                            or actual_op.operation_ref != expected_op.identity.operation_ref
                            or not _id(actual_op.source_ref,self._max)
                            or type(actual_op.measurements) is not tuple):
                        return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                    total_metrics += len(actual_op.measurements)
                    if (total_metrics > self._max_metrics
                            or len(actual_op.measurements) != len(observed_metrics)):
                        return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                    recorded = set()
                    detached_metrics=[]
                    for metric in actual_op.measurements:
                        if (type(metric) is not PhysicalProviderMeasurement
                                or not _id(metric.metric_ref,self._max)
                                or not _id(metric.unit_ref,self._max)
                                or not _id(metric.evidence_ref,self._max)
                                or type(metric.value) is not Decimal
                                or not metric.value.is_finite()
                                or len(metric.value.as_tuple().digits) > self._max_digits
                                or abs(metric.value.as_tuple().exponent) > self._max_exponent
                                or metric.metric_ref in recorded):
                            return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                        recorded.add(metric.metric_ref)
                        detached_metrics.append(PhysicalProviderMeasurement(
                            metric.metric_ref, metric.unit_ref, metric.value,
                            metric.evidence_ref))
                    accepted_measurements.append(OperationMeasurementFact(
                        actual_op.operation_ref, actual_op.source_ref,
                        tuple(detached_metrics)))
                    if recorded != set(observed_metrics):
                        return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                if (not applicability_unchanged() or original_snapshot() != baseline
                        or _snapshot_owned(completion) != original_completion):
                    return ProviderInventoryObservation(ProviderInventoryState.CONFLICT)
                return ProviderInventoryObservation(
                    ProviderInventoryState.MEASUREMENTS_REPORTED, *bound,
                    (measured.policy_id, measured.policy_version),
                    tuple(accepted_measurements), tuple(recorded_events))
            except Exception:
                return ProviderInventoryObservation(ProviderInventoryState.UNKNOWN)
        finally:
            self._gate.release()
