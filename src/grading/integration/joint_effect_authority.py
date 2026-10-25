"""Versioned effect-time authority interface for qualified physical attempt claim and scored-CAS owners.

The authoritative compare-and-effect MUST occur inside the actual durable effect
owner's consistency boundary. This module neither authenticates an issuer nor
makes separate source reads atomic. It is a contract/response validator, not a
replacement for the existing FIRST/RETRY executor or a publication permit.

Unqualified adapters MUST NOT be installed as production effect owners.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.integration.academic_claim_binding import (
    AcademicClaimPreparation, AcademicallyBoundClaim,
    AcademicClaimIntent, academic_intent, validate_preparation, validate_bound_claim,
)
from grading.integration.attempt_authority import _request_snapshot, AttemptClaimDisposition
from grading.integration.evaluator_invocation import AttemptReservation, _reservation_copy
from grading.integration.evaluator_execution_binding import ApprovedRuntimeRecord
from grading.integration.execution_eligibility import _id, _ref, _scope, _capture
from grading.integration.attempt_lineage import _snapshot_owned


class EffectDecision(str, Enum):
    COMMITTED = 'COMMITTED'
    REJECTED = 'REJECTED'
    UNKNOWN = 'UNKNOWN'


class GradingEffectKind(str, Enum):
    FIRST_F25 = 'FIRST_F25'
    REGRADE_F25 = 'REGRADE_F25'
    RETRY_F25 = 'RETRY_F25'
    SCORED_CAS = 'SCORED_CAS'


@dataclass(frozen=True, slots=True, repr=False)
class JointAuthoritySnapshot:
    """Exact academic/runtime identities. NOT an authorization token.

    ``approved_runtime.approval_ref`` is carried independently of the academic
    issuer's ``approval_revision``. The effect owner must establish that BOTH
    remain authorized at its actual effect, not merely compare their strings.
    """
    academic: AcademicClaimIntent
    runtime: ApprovedRuntimeRecord
    max_identifier_characters: int
    max_questions: int

    def __post_init__(self) -> None:
        limit, questions = self.max_identifier_characters, self.max_questions
        if (type(limit) is not int or not 0 < limit <= 4096
                or type(questions) is not int or not 0 < questions <= 10000
                or type(self.academic) is not AcademicClaimIntent
                or type(self.runtime) is not ApprovedRuntimeRecord):
            raise ValueError('Exact bounded joint authority records are required.')
        a, r = self.academic, self.runtime
        verified = academic_intent(a.original_request, a.issued_paper,
                                   a.scoring, limit, questions)
        if verified != a:
            raise ValueError('Academic source was not admitted unchanged.')
        scope = _request_snapshot(a.original_request, limit)[0]
        if (_scope(r.scope, limit) != scope
                or r.family != a.original_request.family
                or (r.runtime_id, r.runtime_version, r.implementation_ref,
                    r.eligibility_policy_id, r.eligibility_policy_version) !=
                   (a.original_request.runtime_id, a.original_request.runtime_version,
                    a.original_request.implementation_ref,
                    a.original_request.eligibility_policy_id,
                    a.original_request.eligibility_policy_version)):
            raise ValueError('Runtime approval is not bound to this exact original grading-attempt claim.')
        # ApprovedRuntimeRecord is a data container, not an admission token.
        # Enforce the existing locally determinable evaluator capability resolution runtime-record shapes.
        _ref(r.capability_ref)
        # The installed runtime contract requires exact values; Python equality
        # would otherwise treat bool/float versions or str subclasses as equal.
        for field in ('eligibility_policy_id', 'family', 'runtime_id',
                      'runtime_version', 'implementation_ref', 'approval_ref'):
            _id(getattr(r, field), limit)
        if (type(r.eligibility_policy_version) is not int
                or r.eligibility_policy_version <= 0):
            raise ValueError('Malformed approved runtime policy version.')
        modalities = r.approved_modalities
        if (type(modalities) is not tuple or len(modalities) > 10000
                or any(type(m) is not str or not m or m.strip() != m
                       or len(m) > limit for m in modalities)
                or len(set(modalities)) != len(modalities)):
            raise ValueError('Malformed approved runtime modalities.')
        _id(r.approval_ref, limit)
        _id(a.issued_paper.approval_revision, limit)


def _same_issued_paper_selection(plan, issued, *, limit: int, maximum: int) -> bool:
    """Compare every admitted paper-selection fact represented by both sources.

    The signed/issued paper additionally owns the rubric references; those are
    separately bound to the scored academic intent by ``academic_intent``.
    Equality here is structural continuity, NEVER issuer authentication.
    """
    from grading.integration.paper_execution_correlation import _plan, _relation
    selected = _plan(plan, maximum, limit)
    actual = _relation(issued, maximum, limit)
    if (selected.request != actual.request
            or selected.actor_ref != actual.actor_ref
            or any(getattr(selected, f) != getattr(actual, f) for f in (
                'approval_ref', 'approval_revision', 'selection_decision_ref',
                'selection_revision', 'source_revision', 'readiness_revision'))
            or len(selected.questions) != len(actual.questions)):
        return False
    return all(
        (p.request.question_id, p.family, p.source_artifact_ref,
         p.evidence_scope_ref, p.answer_region_ref, p.source_revision,
         p.provenance_ref) ==
        (q.question_id, q.family, q.source_artifact_ref,
         q.evidence_scope_ref, q.answer_region_ref, q.source_revision,
         q.provenance_ref)
        for p, q in zip(selected.questions, actual.questions, strict=True)
    )


@dataclass(frozen=True, slots=True, repr=False)
class ConditionalEffectClaim:
    authority: JointAuthoritySnapshot
    preparation: AcademicClaimPreparation
    operation: GradingEffectKind
    original_retry: object = None
    retry_grant: object = None
    regrade_permission: object = None
    first_permission: object = None

    def __post_init__(self) -> None:
        if type(self.authority) is not JointAuthoritySnapshot:
            raise ValueError('Joint claim needs an exact authority snapshot.')
        if type(self.operation) is not GradingEffectKind or self.operation not in (
                GradingEffectKind.FIRST_F25, GradingEffectKind.REGRADE_F25,
                GradingEffectKind.RETRY_F25):
            raise ValueError('Incorrect grading-attempt operation kind.')
        validate_preparation(self.preparation, self.authority.academic,
                             self.authority.max_identifier_characters)
        original = self.authority.academic.original_request
        if self.operation is GradingEffectKind.FIRST_F25:
            from grading.integration.paper_lifecycle import PaperLifecyclePermission, PaperLifecycleKind
            permission = self.first_permission
            if type(permission) is not PaperLifecyclePermission:
                raise ValueError('Source-issued FIRST lifecycle authorization permission is required.')
            from grading.integration.paper_execution_correlation import _plan
            _plan(permission.plan, self.authority.max_questions,
                  self.authority.max_identifier_characters)
            if (type(permission) is not PaperLifecyclePermission
                    or permission.kind is not PaperLifecycleKind.FIRST
                    or permission.predecessor is not None
                    or permission.predecessor_custody is not None
                    or permission.plan.request != self.authority.academic.issued_paper.request
                    or not _same_issued_paper_selection(
                        permission.plan, self.authority.academic.issued_paper,
                        limit=self.authority.max_identifier_characters,
                        maximum=self.authority.max_questions)):
                raise ValueError('FIRST attempt reservation needs exact source-issued lifecycle authorization operation permission.')
        elif self.first_permission is not None:
            raise ValueError('Non-FIRST operation cannot carry FIRST purpose.')
        if self.operation is GradingEffectKind.REGRADE_F25:
            from grading.integration.paper_lifecycle import (
                PaperLifecyclePermission, PaperLifecycleKind,
            )
            permission = self.regrade_permission
            if (type(permission) is not PaperLifecyclePermission
                    or permission.kind is not PaperLifecycleKind.REGRADE
                    or permission.predecessor is None
                    or permission.predecessor.result_ref != original.predecessor_result_ref
                    or permission.approval_ref != original.regrade_approval_ref
                    or not _same_issued_paper_selection(
                        permission.plan, self.authority.academic.issued_paper,
                        limit=self.authority.max_identifier_characters,
                        maximum=self.authority.max_questions)):
                raise ValueError('Source-issued regrade grant does not bind original CAS predecessor.')
        elif self.regrade_permission is not None:
            raise ValueError('Non-regrade claim cannot carry regrade grant.')
        if self.operation is GradingEffectKind.RETRY_F25:
            if self.original_retry is None or self.retry_grant is None:
                raise ValueError('RETRY requires both original absence and source-issued lifecycle authorization purpose evidence.')
            if self.original_retry is not None:
                from grading.integration.paper_retry_recovery import (
                    OriginalPaperRecovery, OriginalPaperRecoveryState,
                )
                from grading.integration.paper_retry_claim import AuthorizedPaperRetry
                from grading.integration.whole_paper_attempt_custody import (
                    PaperAttemptCustody, PaperAttemptClaimRecovery,
                    PaperRecoveryState,
                )
                recovered = self.original_retry
                grant = self.retry_grant
                if (type(recovered) is not OriginalPaperRecovery
                        or recovered.state is not OriginalPaperRecoveryState.ABSENCE_REPORTED
                        or type(recovered.paper) is not PaperAttemptCustody
                        or type(recovered.details) is not PaperAttemptClaimRecovery
                        or type(grant) is not AuthorizedPaperRetry
                        or type(grant.new_requests) is not tuple
                        or len(grant.new_requests) != len(
                            self.authority.academic.issued_paper.questions)
                        or not _same_issued_paper_selection(
                            grant.new_plan, self.authority.academic.issued_paper,
                            limit=self.authority.max_identifier_characters,
                            maximum=self.authority.max_questions)):
                    raise ValueError('RETRY requires exact original absence and issued new-paper purpose.')
                old = recovered.paper
                reads = recovered.details.questions
                if (type(reads) is not tuple
                        or len(reads) != len(old.questions)
                        or len(old.questions) != len(grant.new_requests)
                        or grant.original_run_id != old.plan.request.grading_run_id
                        or grant.new_plan.request.grading_run_id == old.plan.request.grading_run_id
                        or any((q.question_id != read.question_id
                                or read.state not in (PaperRecoveryState.NOT_RESERVED,
                                                      PaperRecoveryState.NOT_CONTACTED)
                                or (read.state is PaperRecoveryState.NOT_CONTACTED
                                    and q.f25_call_started))
                               for q, read in zip(old.questions, reads, strict=True))):
                    raise ValueError('RETRY original recovery does not confirm whole-paper absence.')
                # Locally re-admit the full original/new request relationships
                # at the physical boundary. A prior authorized retry claim validation is not a
                # transferable guarantee if caller-held nested facts change.
                from grading.integration.whole_paper_attempt_custody import _matches_paper, _admit
                from grading.integration.paper_execution_correlation import _plan
                maximum = self.authority.max_identifier_characters
                plan = _plan(grant.new_plan, self.authority.max_questions, maximum)
                # A complete original paper record is not made authoritative
                # just by possessing a recovery enum and matching question IDs.
                if _admit(old.plan, old.outcome, self.authority.max_questions, maximum) != old:
                    raise ValueError('RETRY original custody is not internally coherent.')
                if (type(grant.original_request_refs) is not tuple
                        or len(grant.original_request_refs) != len(old.questions)
                        or type(grant.policy_version) is not int
                        or grant.policy_version <= 0
                        or type(grant.purpose_policy_version) is not int
                        or grant.purpose_policy_version <= 0):
                    raise ValueError('Malformed original lifecycle authorization retry inventory or policy version.')
                _id(grant.policy_id, maximum)
                _id(grant.purpose_policy_id, maximum)
                if academic_intent(
                        original, grant.issued_paper, grant.scoring, maximum,
                        self.authority.max_questions) != self.authority.academic:
                    raise ValueError('RETRY grant issuer/scoring authority differs from admitted academic source.')
                issued_requests = set()
                original_requests = set()
                for old_q, read_q, orig_ref, new_q, new_request in zip(
                        old.questions, reads, grant.original_request_refs,
                        plan.questions, grant.new_requests, strict=True):
                    if (orig_ref != old_q.request_ref
                            or (read_q.state is PaperRecoveryState.NOT_CONTACTED
                                and read_q.request_ref is not None)
                            or (read_q.state is not PaperRecoveryState.NOT_CONTACTED
                                and read_q.request_ref != old_q.request_ref)
                            or old_q.question_id != new_q.request.question_id):
                        raise ValueError('RETRY original recovery and source grant disagree.')
                    if orig_ref is not None:
                        original_requests.add(_id(orig_ref, maximum))
                    bound = _request_snapshot(new_request, maximum)
                    if (bound[0].question_id != new_q.request.question_id
                            or bound[2] != new_q.family
                            or not _matches_paper(bound[0], plan, new_q, maximum)
                            or bound[8] is not None or bound[9] is not None
                            or bound[1] in issued_requests):
                        raise ValueError('RETRY issued grading-attempt inventory has a foreign question.')
                    issued_requests.add(bound[1])
                if original_requests & issued_requests:
                    raise ValueError('RETRY cannot reuse original request identity.')
                original_key = _request_snapshot(original, self.authority.max_identifier_characters)
                if sum(_request_snapshot(req, self.authority.max_identifier_characters) == original_key
                       for req in self.retry_grant.new_requests) != 1:
                    raise ValueError('RETRY original authorization does not bind this grading-attempt request.')
        elif self.original_retry is not None or self.retry_grant is not None:
            raise ValueError('Only RETRY carries original absence and purpose evidence.')
        # A new FIRST or RETRY claim has no scored predecessor. RETRY requires
        # a separately issued legal operation transition purpose grant: predecessor absence grants none.
        absent = original.predecessor_result_ref is None
        if ((self.operation in (GradingEffectKind.FIRST_F25,
                                GradingEffectKind.RETRY_F25) and not absent)
                or (self.operation is GradingEffectKind.REGRADE_F25 and absent)):
            raise ValueError('grading-attempt operation conflicts with original predecessor identity.')


@dataclass(frozen=True, slots=True, repr=False)
class ConditionalScoredCAS:
    authority: JointAuthoritySnapshot
    original_transaction_ref: str
    scored_generation_ref: str
    scored_result_ref: str

    def __post_init__(self) -> None:
        if type(self.authority) is not JointAuthoritySnapshot:
            raise ValueError('A scored CAS requires exact original joint authority.')
        limit = self.authority.max_identifier_characters
        for value in (self.original_transaction_ref, self.scored_generation_ref,
                      self.scored_result_ref):
            _id(value, limit)


@dataclass(frozen=True, slots=True, repr=False)
class ConditionalEffectClaimResponse:
    request: ConditionalEffectClaim
    state: EffectDecision
    bound_claim: AcademicallyBoundClaim | None = None
    retry_receipt: object = None


@dataclass(frozen=True, slots=True, repr=False)
class ConditionalCASResponse:
    request: ConditionalScoredCAS
    state: EffectDecision
    committed_transaction_ref: str | None = None


class QualifiedJointEffectOwner(Protocol):
    """REQUIRED external guarantee, not supplied by structural conformance.

    Both methods must compare academic issuance AND approved runtime revisions
    to authoritative current state atomically with their respective physical
    physical attempt reservation or scored-CAS write. On uncertain transport outcome, the
    implementation must return UNKNOWN, preserving the original effect identity.
    The source-of-record issuer, physical attempt claim and CAS teams must qualify this mechanism.
    """
    def claim_if_current(self, *, request: ConditionalEffectClaim) -> ConditionalEffectClaimResponse: ...
    def commit_if_current(self, *, request: ConditionalScoredCAS) -> ConditionalCASResponse: ...


class JointEffectAdmission:
    """One-contact validation of a qualified owner. No retries on UNKNOWN.

    A matching COMMITTED receipt is only a backend assertion. This class does
    not authenticate that backend or make an unqualified adapter production-safe.
    """
    __slots__ = ('_claim', '_commit')

    def __init__(self, *, owner: QualifiedJointEffectOwner):
        try:
            claim = _capture(owner, 'claim_if_current', ('request',))
            commit = _capture(owner, 'commit_if_current', ('request',))
        except Exception:
            raise ValueError('Both exact conditional effect operations are required.') from None
        object.__setattr__(self, '_claim', claim)
        object.__setattr__(self, '_commit', commit)

    def __setattr__(self, name, value):
        raise AttributeError('Installed joint effect operation cannot be replaced.')

    def claim(self, *, request: ConditionalEffectClaim) -> ConditionalEffectClaimResponse:
        if type(request) is not ConditionalEffectClaim:
            raise ValueError('Exact claim request required before contact.')
        # Caller-held frozen dataclasses are not a substitute for admission
        # at the actual effect boundary. Recheck the present exact record.
        JointAuthoritySnapshot(request.authority.academic, request.authority.runtime,
                               request.authority.max_identifier_characters,
                               request.authority.max_questions)
        ConditionalEffectClaim(request.authority, request.preparation, request.operation,
                            request.original_retry, request.retry_grant,
                            request.regrade_permission, request.first_permission)
        if request.operation is GradingEffectKind.RETRY_F25 and (
                request.original_retry is None or request.retry_grant is None):
            raise ValueError('RETRY physical effect requires original recovery and issued purpose.')
        original_request = request
        try:
            before = _snapshot_owned(request, limit=50000)
            # The backend may mutate a frozen dataclass through an installed
            # callback. UNKNOWN must carry the *original* recovery request,
            # not a reference to a now-mutated nested authority record.
            original_request = deepcopy(request)
            if _snapshot_owned(request, limit=50000) != before:
                raise ValueError('Original claim changed before effect contact.')
            reply = self._claim(request=request)
            if _snapshot_owned(request, limit=50000) != before:
                raise ValueError('Authority changed during physical attempt contact.')
            if (type(reply) is not ConditionalEffectClaimResponse
                    or reply.request != request or type(reply.state) is not EffectDecision):
                raise ValueError('Malformed post-contact conditional claim.')
            if reply.state is EffectDecision.COMMITTED:
                claim = validate_bound_claim(reply.bound_claim, request.preparation,
                                             request.authority.max_identifier_characters)
                if claim.disposition is not AttemptClaimDisposition.FRESH:
                    raise ValueError('Only FRESH can authorize a new execution.')
                maximum = request.authority.max_identifier_characters
                original = _request_snapshot(request.authority.academic.original_request, maximum)
                expected = AttemptReservation(
                    original[0], '', '', *original[2:8],
                    request_ref=original[1], predecessor_result_ref=original[8],
                    regrade_approval_ref=original[9])
                # A FRESH label is not an executable reservation. Use the
                # established attempt claim scope/type validator and bind all physical IDs.
                reservation = _reservation_copy(claim.reservation, expected=expected,
                                                maximum=maximum)
                if (reservation.request_ref != original[1]
                        or reservation.predecessor_result_ref != original[8]
                        or reservation.regrade_approval_ref != original[9]):
                    raise ValueError('FRESH permit has foreign grading-attempt identity.')
                if request.operation is GradingEffectKind.RETRY_F25:
                    from grading.integration.paper_retry_claim import AtomicRetryClaimReceipt
                    original = request.original_retry
                    grant = request.retry_grant
                    receipt = reply.retry_receipt
                    if (type(receipt) is not AtomicRetryClaimReceipt
                            or receipt.bound_claim != reply.bound_claim
                            or receipt.new_request_ref != request.authority.academic.original_request.request_ref
                            or receipt.approval_ref != grant.approval_ref
                            or receipt.original_request_ref not in grant.original_request_refs):
                        raise ValueError('RETRY physical receipt lacks issued original/new transition.')
                elif reply.retry_receipt is not None:
                    raise ValueError('Non-RETRY claim carried a retry transition receipt.')
            elif reply.bound_claim is not None or reply.retry_receipt is not None:
                raise ValueError('Noncommitted claim supplied a positive physical permit.')
            return reply
        except Exception:
            # The effect might already exist. A second claim is forbidden.
            return ConditionalEffectClaimResponse(original_request, EffectDecision.UNKNOWN)

    def commit(self, *, request: ConditionalScoredCAS) -> ConditionalCASResponse:
        if type(request) is not ConditionalScoredCAS:
            raise ValueError('Exact scored CAS request required before contact.')
        JointAuthoritySnapshot(request.authority.academic, request.authority.runtime,
                               request.authority.max_identifier_characters,
                               request.authority.max_questions)
        ConditionalScoredCAS(request.authority, request.original_transaction_ref,
                             request.scored_generation_ref, request.scored_result_ref)
        original_request = request
        try:
            before = _snapshot_owned(request, limit=50000)
            original_request = deepcopy(request)
            if _snapshot_owned(request, limit=50000) != before:
                raise ValueError('Original CAS changed before effect contact.')
            reply = self._commit(request=request)
            if _snapshot_owned(request, limit=50000) != before:
                raise ValueError('Authority changed during scored CAS contact.')
            if (type(reply) is not ConditionalCASResponse
                    or reply.request != request or type(reply.state) is not EffectDecision):
                raise ValueError('Malformed post-contact conditional CAS.')
            if reply.state is EffectDecision.COMMITTED:
                if reply.committed_transaction_ref != request.original_transaction_ref:
                    raise ValueError('Foreign scored transaction receipt.')
            elif reply.committed_transaction_ref is not None:
                raise ValueError('Noncommitted CAS carried a positive receipt.')
            return reply
        except Exception:
            # Unknown effect must be reconciled under original transaction id.
            return ConditionalCASResponse(original_request, EffectDecision.UNKNOWN)
