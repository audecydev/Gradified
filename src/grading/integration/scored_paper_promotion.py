"""governed scored-paper handoff: one nonpublishing, original-source-bound paper handoff eligibility gate.

The engine does NOT issue institutional publication permission. A candidate
is eligible for governed handoff only when original operation transition, academically bound
physical attempt claim, complete frozen scoring/deterministic scoring, paper CAS, durable audit and applicable
provider-accounting assertions can all be reconciled without conflict.
The real adapters must independently qualify authenticity and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy, _snapshot_owned
from grading.integration.retry_purpose_authorization import RetryPurposeTransitionPolicy, retry_purpose_admitted
from grading.integration.execution_eligibility import _capture, _id
from grading.integration.paper_execution_correlation import _plan
from grading.integration.paper_lifecycle import (
    PaperLifecycleObservation, PaperLifecyclePermission, PaperLifecycleKind, PaperLifecycleState,
)
from grading.integration.whole_paper_cas import (
    PaperCASState, PaperCASTransaction, PaperCASOutcome,
    ProductionPaperCASDurableRecovery, _approved_intent, _validate_transaction,
    _receipt,
)
from grading.integration.paper_accounting import (
    ProductionPaperAccounting, PaperAccountingState,
)
from grading.integration.paper_provider_inventory import (
    ProductionProviderInventory, ProviderInventoryState, ProviderInventoryObservation,
)
from grading.providers.attempt_accounting import ProviderAttemptIdentity
from grading.integration.attempt_authority import _request_snapshot
from grading.integration.evaluator_invocation import AttemptReservation, _reservation_copy
from grading.integration.academic_claim_binding import academic_intent, validate_preparation
from grading.contracts.paper_aggregation import ExpectedQuestionResult
from grading.integration.whole_paper_attempt_custody import PaperAttemptCustody
from grading.integration.paper_retry_grading import GradedRetryOutcome, GradedRetryState
from grading.integration.paper_retry_claim import (
    AuthorizedPaperRetry, RetryClaimState, PaperRetryClaimObservation,
    RetryQuestionObservation,
)
from grading.integration.paper_retry_recovery import (
    ProductionPaperOriginalRecovery, OriginalPaperRecoveryState, OriginalPaperRecovery,
)


class PaperHandoffEligibilityState(str, Enum):
    ELIGIBLE_FOR_GOVERNED_HANDOFF = 'ELIGIBLE_FOR_GOVERNED_HANDOFF'
    BLOCKED = 'BLOCKED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class PaperHandoffAssessment:
    state: PaperHandoffEligibilityState

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class QualifiedOriginalPaperLifecycleSource(Protocol):
    """FIXED, authenticated original paper/run history: no caller selector.

    Must return the actual legally permitted, effectfully executed operation;
    returning a structurally equivalent forgery is a backend contract failure.
    The original legal operation-transition decision's issuance time/order is an external guarantee.
    """
    def resolve_original_paper_lifecycle(self) -> PaperLifecycleObservation: ...


def _compatible_provider_evidence(native: bool, c4d: PaperAccountingState,
                                  c4f: ProviderInventoryState) -> bool:
    """An independent recorded-transport result cannot contradict no-transport.

    original attempt accounting reports one original per provider question, whereas physical provider inventory can report
    multiple originals. Only a compatible pair may feed handoff eligibility.
    """
    if native:
        return (c4d is PaperAccountingState.NOT_APPLICABLE
                and c4f is ProviderInventoryState.NOT_APPLICABLE)
    return ((c4d is PaperAccountingState.REPORTED_RECORDED
             and c4f is ProviderInventoryState.MEASUREMENTS_REPORTED)
            or (c4d is PaperAccountingState.NOT_APPLICABLE
                and c4f is ProviderInventoryState.NOT_APPLICABLE))


def _same_original_provider_operations(original, observed: ProviderInventoryObservation) -> bool:
    """Join complete source-admitted physical and logical ORIGINAL event facts.

    physical provider inventory may attest extra physical calls; every original attempt accounting original must agree on
    question, all identity fields, and the returned-outcome state. No
    `operation_ref`-only match, and no inference from provider metric totals.
    """
    if (type(observed) is not ProviderInventoryObservation
            or type(observed.original_operations) is not tuple
            or len(observed.original_operations) != len(observed.operation_refs)):
        return False
    by_ref = {}
    for event in observed.original_operations:
        if (type(event) is not tuple or len(event) != 3):
            return False
        question_id, identity, outcome = event
        if (type(question_id) is not str or type(identity) is not ProviderAttemptIdentity
                or type(outcome) is not str or identity.operation_ref in by_ref):
            return False
        by_ref[identity.operation_ref] = event
    if set(by_ref) != set(observed.operation_refs):
        return False
    return all(by_ref.get(port.identity.operation_ref) ==
               (port.question_id, port.identity, 'RESULT_RETURNED')
               for port in original)


def _required_transport_questions_accounted(plan, original,
                                           physical: ProviderInventoryObservation) -> bool:
    """Never omit a DIRECT or independently source-required transport question."""
    required = ({q.request.question_id for q in plan.questions if q.family == 'DIRECT'}
                | set(physical.required_question_ids))
    return required.issubset({op.question_id for op in original})


class ProductionPaperPromotion:
    """No alternative promotion heuristics and no grade/publication writes.

    A missing historical-policy qualification, prior CAS, numeric usage fact or
    source-of-record outcome remains blocked/unknown. This is an engine-side
    consumer of qualified facts, not a cryptographic authenticity primitive.
    """
    __slots__ = ('_original', '_audit', '_predecessor_audit', '_accounting',
                 '_policy', '_maximum', '_questions', '_gate', '_physical_accounting', '_retry_recovery', '_retry_purpose')

    def __init__(self, *, original_source: QualifiedOriginalPaperLifecycleSource,
                 audit_recovery: ProductionPaperCASDurableRecovery,
                 accounting: ProductionPaperAccounting,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int, max_questions: int,
                 predecessor_audit_recovery: ProductionPaperCASDurableRecovery | None = None,
                 physical_accounting: ProductionProviderInventory | None = None,
                 retry_original_recovery: ProductionPaperOriginalRecovery | None = None,
                 retry_purpose_policy: RetryPurposeTransitionPolicy | None = None):
        if (type(audit_recovery) is not ProductionPaperCASDurableRecovery
                or type(accounting) is not ProductionPaperAccounting
                or (physical_accounting is not None and
                    type(physical_accounting) is not ProductionProviderInventory)
                or (retry_original_recovery is not None and
                    type(retry_original_recovery) is not ProductionPaperOriginalRecovery)
                or type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000
                or (predecessor_audit_recovery is not None and
                    type(predecessor_audit_recovery) is not ProductionPaperCASDurableRecovery)
                or audit_recovery._allowed != legal_policy
                or audit_recovery._max != max_identifier_characters
                or audit_recovery._questions != max_questions
                or (predecessor_audit_recovery is not None
                    and (predecessor_audit_recovery._allowed != legal_policy
                         or predecessor_audit_recovery._max != max_identifier_characters
                         or predecessor_audit_recovery._questions != max_questions))):
            raise ValueError('scored-paper promotion requires exact original paper CAS and accounting ports.')
        _id(legal_policy.policy_id, max_identifier_characters)
        object.__setattr__(self, '_original', _capture(original_source,
            'resolve_original_paper_lifecycle', ()))
        object.__setattr__(self, '_audit', audit_recovery)
        object.__setattr__(self, '_predecessor_audit', predecessor_audit_recovery)
        object.__setattr__(self, '_accounting', accounting)
        object.__setattr__(self, '_physical_accounting', physical_accounting)
        object.__setattr__(self, '_retry_recovery', retry_original_recovery)
        object.__setattr__(self, '_retry_purpose', retry_purpose_policy)
        object.__setattr__(self, '_policy', legal_policy)
        object.__setattr__(self, '_maximum', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('scored-paper promotion installed original-source ports cannot be replaced.')

    def assess(self, *, expected_transaction: PaperCASTransaction | None = None,
               expected_commit_ref: str | None = None) -> PaperHandoffAssessment:
        """Read-only governed scored-paper handoff assessment, optionally tied to an exact acknowledged CAS.

        The expected transaction is only a comparison target, never an input
        used to select or manufacture a source record.  The original-history
        source must independently recover the actual originally executed paper.
        Both optional fields are required together when qualifying a scored
        operation. Legacy read-only assess() retains its original semantics.
        """
        if ((expected_transaction is None) != (expected_commit_ref is None)):
            raise ValueError('Original-qualified scored-paper promotion needs transaction and commit identity together.')
        if expected_transaction is not None:
            if type(expected_transaction) is not PaperCASTransaction:
                raise ValueError('Original-qualified scored-paper promotion requires an exact CAS transaction.')
            _id(expected_commit_ref, self._maximum)
        if not self._gate.acquire(blocking=False):
            return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
        try:
            try:
                history = self._original()  # ZERO caller-supplied lookup arguments
            except Exception:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            if expected_transaction is not None:
                # governed scored-paper handoff's fixed-history reader, not the caller, supplies the
                # recovered observation. In particular a prior run with a
                # successful governed scored-paper handoff result cannot qualify the new scored CAS.
                try:
                    cas = history.cas
                    if (type(cas) is not PaperCASOutcome
                            or cas.state is not PaperCASState.COMMITTED
                            or type(cas.transaction) is not PaperCASTransaction
                            or cas.transaction != expected_transaction
                            or cas.receipt is None
                            or _receipt(cas.receipt, cas.transaction,
                                        self._maximum).commit_ref != expected_commit_ref):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                except Exception:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            if type(history) is GradedRetryOutcome:
                return self._assess_original_retry(history)
            try:
                if (type(history) is not PaperLifecycleObservation
                        or type(history.state) is not PaperLifecycleState
                        or type(history.kind) is not PaperLifecycleKind
                        or history.state not in (PaperLifecycleState.CAS_ACKNOWLEDGED, PaperLifecycleState.UNKNOWN)
                        or history.kind not in (PaperLifecycleKind.FIRST, PaperLifecycleKind.REGRADE)
                        or type(history.permission) is not PaperLifecyclePermission
                        or type(history.permission.kind) is not PaperLifecycleKind
                        or type(history.cas) is not PaperCASOutcome
                        or (history.state is PaperLifecycleState.CAS_ACKNOWLEDGED and
                            (history.cas.state is not PaperCASState.COMMITTED
                             or history.cas.academic_binding_verified is not True))
                        or (history.state is PaperLifecycleState.UNKNOWN and
                            (history.cas.state is not PaperCASState.UNKNOWN
                             or history.cas.receipt is not None))):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                original = _snapshot_owned(history)
                perm = history.permission
                cas = history.cas
                intent = _approved_intent(cas.custody, self._questions, self._maximum)
                plan = _plan(perm.plan, self._questions, self._maximum)
                if (plan != intent.plan or perm.kind is not history.kind
                        or _id(perm.approval_ref, self._maximum) == ''
                        or _id(perm.policy_id, self._maximum) != self._policy.policy_id
                        or type(perm.policy_version) is not int
                        or perm.policy_version != self._policy.policy_version
                        or type(perm.source_state) is not GradingJobState
                        or type(perm.target_state) is not GradingJobState
                        or (perm.source_state, perm.target_state) not in self._policy.allowed_edges):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                tx = cas.transaction
                if tx is not None:
                    _validate_transaction(tx, intent, self._policy, self._maximum)
                elif cas.state is not PaperCASState.UNKNOWN:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                if cas.state is PaperCASState.COMMITTED:
                    _receipt(cas.receipt, tx, self._maximum)
                if history.kind is PaperLifecycleKind.FIRST:
                    if (history.predecessor is not None or perm.predecessor is not None
                            or perm.predecessor_custody is not None
                            or any(r.predecessor_result_ref is not None
                                   or r.regrade_approval_ref is not None
                                   for r in intent.original_claim_requests)):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                else:
                    prior = perm.predecessor
                    if (type(prior) is not PaperCASTransaction
                            or history.predecessor is None
                            or perm.predecessor_custody is None
                            or self._predecessor_audit is None):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                    old_intent = _approved_intent(perm.predecessor_custody,
                                                   self._questions, self._maximum)
                    _validate_transaction(prior, old_intent, self._policy, self._maximum)
                    # A regrade must not reuse an earlier generation's CAS
                    # request, event or result identity—even if each record is
                    # individually valid. Reject before avoidable backend reads.
                    if (tx is not None and any(
                            getattr(tx, name) == getattr(prior, name)
                            for name in ('request_ref', 'event_ref', 'result_ref'))):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                    if (_snapshot_owned(history.predecessor) != _snapshot_owned(prior)
                            or old_intent.plan.request.session_ref != plan.request.session_ref
                            or old_intent.plan.request.tenant_ref != plan.request.tenant_ref
                            or old_intent.plan.request.submission_ref != plan.request.submission_ref
                            or old_intent.plan.request.exam_ref != plan.request.exam_ref
                            or old_intent.plan.request.paper_ref != plan.request.paper_ref
                            or old_intent.plan.request.set_ref != plan.request.set_ref
                            or old_intent.plan.request.grading_run_id == plan.request.grading_run_id
                            or any(r.predecessor_result_ref != prior.result_ref
                                   or r.regrade_approval_ref != perm.approval_ref
                                   for r in intent.original_claim_requests)
                            or any({a[i] for a in old_intent.question_claims}
                                   & {a[i] for a in intent.question_claims}
                                   for i in (1, 2, 3))):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                # Verify the prepared academic revision really matches every
                # originally performed claim and the actual frozen score.
                if len(cas.custody.questions) != len(intent.result.questions):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                # Historical first-run and regrade admissions are independent of
                # the original executor. Every durable academic physical attempt claim preparation
                # must name ONE complete scored-paper authority, including
                # paper-level grading bounds and versioned question inventory.
                paper_score = intent.result.paper_score
                first_original_scoring = None
                for custody_q, scored in zip(cas.custody.questions,
                                             intent.result.questions, strict=True):
                    if custody_q.academic_preparation is None:
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                    prepared = custody_q.academic_preparation
                    expected = academic_intent(custody_q.original_f25_request,
                        intent.issued, prepared.intent.scoring, self._maximum, self._questions)
                    validate_preparation(prepared, expected, self._maximum)
                    whole = expected.scoring
                    if (whole.grading_spec_ref != paper_score.grading_spec_ref
                            or whole.minimum_score != paper_score.minimum_score
                            or whole.maximum_score != paper_score.maximum_score
                            or tuple((q.question_id, q.rubric_ref, q.scoring_policy_ref)
                                     for q in whole.expected_questions) !=
                               tuple((q.question_id, q.rubric_ref, q.scoring_policy_ref)
                                     for q in paper_score.question_results)
                            or (first_original_scoring is not None
                                and whole != first_original_scoring)):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                    first_original_scoring = whole
                    approved = next((e for e in expected.scoring.expected_questions
                                     if e.question_id == custody_q.question_id), None)
                    if (type(approved) is not ExpectedQuestionResult
                            or scored.score.question_id != custody_q.question_id
                            or scored.score.rubric_ref != approved.rubric_ref
                            or scored.score.scoring_policy_ref != approved.scoring_policy_ref):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                if _snapshot_owned(history) != original:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            except Exception:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            # No audit/provider read occurs until all local authority and
            # complete-paper observations have been admitted together.
            try:
                if history.kind is PaperLifecycleKind.REGRADE:
                    predecessor_assertion = PaperCASOutcome(
                        PaperCASState.UNKNOWN, perm.predecessor_custody, perm.predecessor)
                    predecessor = self._predecessor_audit.reconcile(outcome=predecessor_assertion)
                    if predecessor is PaperCASState.BLOCKED:
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                    if predecessor is not PaperCASState.COMMITTED:
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                current = self._audit.reconcile(
                    outcome=cas,
                    disjoint_from=(prior if history.kind is PaperLifecycleKind.REGRADE else None))
                if current is PaperCASState.BLOCKED:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                if current is not PaperCASState.COMMITTED:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                accounts = self._accounting.reconcile(intent=intent)
                if accounts.state is PaperAccountingState.CONFLICT:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                if accounts.state is PaperAccountingState.UNKNOWN:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                # The installed DIRECT evaluator uses semantic provider transport.
                # A separate applicability source cannot claim a provider-free
                # DIRECT operation merely by returning an empty inventory.
                requires_direct_transport = any(
                    q.family == 'DIRECT' for q in intent.plan.questions)
                # Both original applicability decisions must be independently
                # installed. A matching operation ID is not a substitute for
                # an approved whole-paper transport requirement.
                if (requires_direct_transport and (
                        self._physical_accounting is None
                        or self._physical_accounting._applicability is None
                        or self._accounting._applicability is None)):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                # original attempt accounting's REPORTED_RECORDED is not complete provider telemetry.
                # For actual transport an independently inventoried and
                # versioned completeness report is additionally required.
                nonchoice = any(q.family != 'CHOICE' for q in intent.plan.questions)
                if self._physical_accounting is None:
                    if nonchoice:
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                else:
                    physical = self._physical_accounting.reconcile()
                    if physical.state is ProviderInventoryState.CONFLICT:
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                    if physical.state is ProviderInventoryState.UNKNOWN:
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                    if (physical.plan != intent.plan
                            or len(physical.original_requests) != len(intent.original_claim_requests)
                            or len(physical.physical_reservations) != len(intent.question_claims)):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                    for original_request, accepted_request, reservation, claim in zip(
                        physical.original_requests, intent.original_claim_requests,
                        physical.physical_reservations, intent.question_claims, strict=True):
                        if (original_request is None or reservation is None
                                or _request_snapshot(original_request,self._maximum) !=
                                   _request_snapshot(accepted_request,self._maximum)
                                or reservation.request_ref != claim[1]
                                or reservation.attempt_id != claim[2]
                                or reservation.reservation_ref != claim[3]):
                            return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                    if ((requires_direct_transport
                         and (accounts.state is PaperAccountingState.NOT_APPLICABLE
                              or physical.state is ProviderInventoryState.NOT_APPLICABLE
                              or not _required_transport_questions_accounted(
                                  intent.plan, self._accounting._original, physical)))
                            or not _compatible_provider_evidence(
                                not nonchoice,accounts.state,physical.state)
                            or (physical.state is ProviderInventoryState.MEASUREMENTS_REPORTED
                                and (not _required_transport_questions_accounted(
                                    intent.plan, self._accounting._original, physical)
                                     or not _same_original_provider_operations(
                                    self._accounting._original, physical)))):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                if _snapshot_owned(history) != original:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            except Exception:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            # Positive means eligible for a downstream governed decision,
            # NEVER that an institution has published or approved the mark.
            return PaperHandoffAssessment(PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF)
        finally:
            self._gate.release()


    def _assess_original_retry(self, history: GradedRetryOutcome) -> PaperHandoffAssessment:
        """The same governed scored-paper handoff fixed-origin CAS/accounting join for a legally retried paper.

        Retry must have an absent/uncommitted physical predecessor, not a
        fabricated predecessor CAS result. A stage-specific legal operation-transition decision is
        necessary and never recreated by this handoff consumer.
        """
        if self._retry_recovery is None:
            return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
        try:
            if (type(history.state) is not GradedRetryState
                    or history.state not in (GradedRetryState.CAS_ACKNOWLEDGED,GradedRetryState.UNKNOWN)
                    or type(history.cas) is not PaperCASOutcome
                    or type(history.physical) is not PaperRetryClaimObservation
                    or history.physical.state is not RetryClaimState.CLAIMED
                    or type(history.authorization) is not AuthorizedPaperRetry
                    or type(history.custody) is not PaperAttemptCustody
                    or history.cas.custody != history.custody):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            grant = history.authorization
            cas = history.cas
            physical = history.physical
            original = physical.original
            if (type(original) is not OriginalPaperRecovery
                    or original.state is not OriginalPaperRecoveryState.ABSENCE_REPORTED
                    or original.paper is None or original.details is None):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            intent = _approved_intent(history.custody,self._questions,self._maximum)
            plan = _plan(grant.new_plan,self._questions,self._maximum)
            prior = _plan(original.paper.plan,self._questions,self._maximum)
            old = prior.request; new = plan.request
            if (plan != intent.plan
                    or intent.issued != grant.issued_paper
                    or grant.original_run_id != old.grading_run_id
                    or new.grading_run_id == old.grading_run_id
                    or any(getattr(new,name) != getattr(old,name) for name in (
                        'tenant_ref','session_ref','submission_ref','exam_ref','paper_ref',
                        'set_ref','grading_spec_ref'))
                    or tuple(q.request.question_id for q in prior.questions) != tuple(
                        q.request.question_id for q in plan.questions)
                    or _id(grant.approval_ref,self._maximum) == ''
                    or grant.policy_id != self._policy.policy_id
                    or type(grant.policy_version) is not int
                    or grant.policy_version != self._policy.policy_version
                    or type(grant.source_state) is not GradingJobState
                    or type(grant.target_state) is not GradingJobState
                    or not retry_purpose_admitted(purpose_policy=self._retry_purpose,
                        legal_policy=self._policy, grant=grant, maximum=self._maximum)
                    or type(grant.new_requests) is not tuple
                    or len(grant.new_requests) != len(intent.original_claim_requests)
                    or type(grant.original_request_refs) is not tuple
                    or len(grant.original_request_refs) != len(prior.questions)
                    or type(physical.claimed) is not tuple
                    or len(physical.claimed) != len(intent.question_claims)):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            # Scored-paper bounds and spec identity are separate from the
            # academic preclaim objects. They must bind to the exact original
            # versioned paper authority before the first avoidable CAS read.
            scored_paper = intent.result.paper_score
            if (grant.scoring.grading_spec_ref != plan.request.grading_spec_ref
                    or grant.scoring.grading_spec_ref != scored_paper.grading_spec_ref
                    or grant.scoring.minimum_score != scored_paper.minimum_score
                    or grant.scoring.maximum_score != scored_paper.maximum_score
                    or tuple((e.question_id, e.rubric_ref, e.scoring_policy_ref)
                             for e in grant.scoring.expected_questions) !=
                       tuple((q.question_id, q.rubric_ref, q.scoring_policy_ref)
                             for q in scored_paper.question_results)):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            # The recovered legal operation transition scoring authority must be the SAME complete
            # paper authority used at original academic physical-attempt preclaim time.
            # Matching only the individual rubric/policy refs is insufficient:
            # paper scoring bounds and grading-spec versions could otherwise
            # contradict the genuinely prepared/scored retry while governed scored-paper handoff reads CAS.
            for custody_q in history.custody.questions:
                if custody_q.academic_preparation is None:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                expected_preclaim = academic_intent(
                    custody_q.original_f25_request, intent.issued, grant.scoring,
                    self._maximum, self._questions)
                validate_preparation(custody_q.academic_preparation,
                                     expected_preclaim, self._maximum)
            # Recovery is an independent source-of-record boundary. Re-establish
            # the physical retry producer's complete atomic-transaction
            # inventory before reading the paper CAS backend. Per-question
            # physical attempt claim identities alone do not prove original-to-new retry custody.
            if any(type(claim) is not RetryQuestionObservation
                   for claim in physical.claimed):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            retry_transactions = tuple(_id(claim.transaction_ref, self._maximum)
                                       for claim in physical.claimed)
            if len(set(retry_transactions)) != len(retry_transactions):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            for i,(original_q,new_q,claimed,new_request,actual_request,score) in enumerate(zip(
                    original.paper.questions, intent.question_claims, physical.claimed,
                    grant.new_requests,intent.original_claim_requests,
                    intent.result.questions,strict=True)):
                # The claim-time producer validated the *entire* physical attempt claim receipt.
                # Historical governed scored-paper handoff recovery is independent and must repeat that
                # admission rather than trusting only matching attempt IDs.
                scope = _request_snapshot(actual_request, self._maximum)
                expected_reservation = AttemptReservation(
                    scope[0], '', '', *scope[2:8], request_ref=scope[1],
                    predecessor_result_ref=scope[8], regrade_approval_ref=scope[9])
                reservation = _reservation_copy(
                    claimed.reservation, expected=expected_reservation,
                    maximum=self._maximum)
                if (reservation.request_ref != scope[1]
                        or reservation.predecessor_result_ref != scope[8]
                        or reservation.regrade_approval_ref != scope[9]):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                approved = next((q for q in grant.scoring.expected_questions
                                 if q.question_id == actual_request.scope.question_id),None)
                if (grant.original_request_refs[i] != original_q.request_ref
                        or original_q.reservation is not None
                        or claimed.original_request_ref != original_q.request_ref
                        or claimed.new_request_ref != new_q[1]
                        or (claimed.question_id,claimed.new_request_ref,
                            reservation.attempt_id,
                            reservation.reservation_ref) != new_q
                        or _request_snapshot(new_request,self._maximum) !=
                           _request_snapshot(actual_request,self._maximum)
                        or (original_q.request_ref is not None
                            and original_q.request_ref == new_q[1])
                        or type(approved) is not ExpectedQuestionResult
                        or score.score.rubric_ref != approved.rubric_ref
                        or score.score.scoring_policy_ref != approved.scoring_policy_ref):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            if ({q.request_ref for q in original.paper.questions if q.request_ref}
                    & {claim[1] for claim in intent.question_claims}):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            if cas.transaction is not None:
                _validate_transaction(cas.transaction,intent,self._policy,self._maximum)
            elif cas.state is not PaperCASState.UNKNOWN:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            if cas.state is PaperCASState.COMMITTED:
                if (history.state is not GradedRetryState.CAS_ACKNOWLEDGED
                        or cas.academic_binding_verified is not True):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
                _receipt(cas.receipt,cas.transaction,self._maximum)
            elif (cas.state is not PaperCASState.UNKNOWN
                    or history.state is not GradedRetryState.UNKNOWN
                    or cas.receipt is not None):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.BLOCKED)
            original_snapshot = _snapshot_owned(history)
        except Exception:
            return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
        try:
            fresh = self._retry_recovery.reconcile()  # independently sourced original, read-only
            if (fresh.state is OriginalPaperRecoveryState.CONFLICT
                    or (fresh.paper is not None and original.paper != fresh.paper)):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            if (fresh.state is not OriginalPaperRecoveryState.ABSENCE_REPORTED
                    or fresh.details != original.details):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            current = self._audit.reconcile(outcome=cas)
            if current is PaperCASState.BLOCKED:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            if current is not PaperCASState.COMMITTED:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            accounts = self._accounting.reconcile(intent=intent)
            if accounts.state is PaperAccountingState.CONFLICT:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            if accounts.state is PaperAccountingState.UNKNOWN:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            # Retry executes the same installed DIRECT semantic provider as
            # FIRST/REGRADE. The original RETRY absence is not evidence that
            # semantic transport was unnecessary in the *new* attempt.
            requires_direct_transport = any(q.family == 'DIRECT' for q in plan.questions)
            if (requires_direct_transport and (
                    self._physical_accounting is None
                    or self._physical_accounting._applicability is None
                    or self._accounting._applicability is None)):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            if (requires_direct_transport
                    and accounts.state is PaperAccountingState.NOT_APPLICABLE):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            native = all(q.family == 'CHOICE' for q in plan.questions)
            if self._physical_accounting is not None:
                provider = self._physical_accounting.reconcile()
                if provider.state is ProviderInventoryState.CONFLICT:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                if provider.state is ProviderInventoryState.UNKNOWN:
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
                if (provider.plan != plan
                        or len(provider.original_requests) != len(intent.original_claim_requests)
                        or len(provider.physical_reservations) != len(intent.question_claims)):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                for request,expected,reservation,claim in zip(
                    provider.original_requests,intent.original_claim_requests,
                    provider.physical_reservations,intent.question_claims,strict=True):
                    if (request is None or reservation is None
                            or _request_snapshot(request,self._maximum) !=
                               _request_snapshot(expected,self._maximum)
                            or (reservation.request_ref,reservation.attempt_id,
                                reservation.reservation_ref) != claim[1:4]):
                        return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
                if ((requires_direct_transport
                     and (provider.state is ProviderInventoryState.NOT_APPLICABLE
                          or not _required_transport_questions_accounted(
                              plan, self._accounting._original, provider)))
                        or not _compatible_provider_evidence(native,accounts.state,provider.state)
                        or (provider.state is ProviderInventoryState.MEASUREMENTS_REPORTED
                            and (not _required_transport_questions_accounted(
                                plan, self._accounting._original, provider)
                                 or not _same_original_provider_operations(
                                self._accounting._original, provider)))):
                    return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            elif not native:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            if (self._physical_accounting is None and
                    accounts.state is not PaperAccountingState.NOT_APPLICABLE):
                return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
            if _snapshot_owned(history) != original_snapshot:
                return PaperHandoffAssessment(PaperHandoffEligibilityState.CONFLICT)
            return PaperHandoffAssessment(PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF)
        except Exception:
            return PaperHandoffAssessment(PaperHandoffEligibilityState.UNKNOWN)
