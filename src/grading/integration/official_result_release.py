"""Purpose-bound, conditional official-result or student-feedback release.

This is the grading engine's *effect-time* integration seam, not an issuer,
publication policy, database, notification provider or authentication service.
A qualified backend must compare every named original/teacher/policy/academic
revision and target audience atomically WITH its durable release effect.
Synthetic implementations establish the contract, not production authority.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.integration.assessment_readiness_views import (
    AssessmentReadiness, AssessmentOrigin, AssessmentViewFact, EvidenceView, ReadinessState,
)
from grading.integration.execution_eligibility import _capture
from grading.integration.governed_operation_consumer import (
    GovernedOperationState, ScoredOperationIdentity,
)
from grading.integration.governed_paper_handoff import GovernedPaperHandoff
from grading.integration.governed_result_disposition import ResultDisposition
from grading.integration.recovered_original_governance import (
    ProductionRecoveredOriginalGovernance, RecoveredOriginalGovernance,
)
from grading.integration.recovered_teacher_review_candidate import (
    ProductionRecoveredTeacherReviewCandidate, RecoveredTeacherReviewCandidate,
    RecoveredTeacherReviewState,
)
from grading.integration.recovered_feedback_candidate import (
    ProductionRecoveredFeedbackCandidate, RecoveredFeedbackCandidate,
    FeedbackCandidateState,
)
from grading.integration.student_safe_feedback import (
    StudentSafeFeedback, FeedbackCategory, FeedbackOriginal,
)
from grading.integration.teacher_review_journal import (
    TeacherReviewRecoveryObservation, TeacherReviewRecoveryState,
)


class ReleasePurpose(str, Enum):
    OFFICIAL_RESULT = 'OFFICIAL_RESULT'
    STUDENT_FEEDBACK = 'STUDENT_FEEDBACK'


class ReleaseState(str, Enum):
    RELEASED = 'RELEASED'     # Qualified backend's durable effect ACK, never local inference
    DENIED = 'DENIED'         # Backend asserted no release effect was committed
    UNKNOWN = 'UNKNOWN'       # Outcome may have occurred; reconcile, do NOT resend


@dataclass(frozen=True, slots=True)
class ReleaseOperationIdentity:
    """Stable logical release key: exact scored original + separate purpose.

    This is an engine correlation key, NOT a school-issued permission, a
    durable backend lease, or proof that any effect has occurred. A new
    scoring original creates a different key; a policy/teacher change for
    the same original MUST NOT silently create a fresh effect.
    """
    original: ScoredOperationIdentity
    purpose: ReleasePurpose


@dataclass(frozen=True, slots=True)
class ConditionalReleaseIntent:
    purpose: ReleasePurpose
    operation: ScoredOperationIdentity
    policy_ref: str
    policy_revision: str
    decision_ref: str
    journal_event_ref: str
    # Exact authorized result release views including issuer and source revisions: three distinct facts.
    readiness_views: tuple[AssessmentViewFact, AssessmentViewFact, AssessmentViewFact]
    # Only STUDENT_FEEDBACK carries an independently admitted, *fixed* message.
    feedback: StudentSafeFeedback | None = None
    feedback_binding_revision: str | None = None

    @property
    def release_identity(self) -> ReleaseOperationIdentity:
        return ReleaseOperationIdentity(self.operation, self.purpose)


@dataclass(frozen=True, slots=True)
class ConditionalReleaseReceipt:
    intent: ConditionalReleaseIntent
    release_event_ref: str
    authorization_ref: str
    issuer_ref: str
    release_generation_ref: str


@dataclass(frozen=True, slots=True)
class ConditionalReleaseReply:
    intent: ConditionalReleaseIntent
    state: ReleaseState
    receipt: ConditionalReleaseReceipt | None = None


class QualifiedConditionalResultRelease(Protocol):
    """ONE authenticated effect-owner contact, conditional and durable.

    The real backend must enforce actor/audience eligibility; approved school
    release policy and current teacher decision; original CAS/governed scored-paper handoff provenance;
    all authorized result release issuer revisions; student-safe feedback academic confirmation and joint snapshot for
    feedback; revocation; and duplicate identity/transaction atomicity INSIDE
    the release write. UNKNOWN forbids blind retries. Engine does not invent
    authorization, threshold values, or a student destination.
    """
    def commit_if_current(self, *, request: ConditionalReleaseIntent) -> ConditionalReleaseReply: ...


class QualifiedConditionalReleaseHistory(Protocol):
    """Authenticated, read-only lookup of one previously contacted intent.

    Must not enqueue, publish, notify, retry, or mutate any release effect.
    An external durable ledger must correlate the exact original and purpose;
    this local query does not establish backend authenticity or restart custody.
    """
    def read_release_outcome(self, *, request: ConditionalReleaseIntent) -> ConditionalReleaseReply: ...


class ReleaseIntentEstablishmentState(str, Enum):
    """Authoritative write-ahead result, never inferred from a source read."""
    ESTABLISHED = 'ESTABLISHED'  # New immutable intent durably persisted
    ALREADY_ESTABLISHED = 'ALREADY_ESTABLISHED'  # Same frozen original exists
    CONFLICT = 'CONFLICT'  # Identity is bound to a different intent
    UNKNOWN = 'UNKNOWN'  # May have persisted; NEVER contact release writer


@dataclass(frozen=True, slots=True)
class ReleaseIntentEstablishmentReply:
    state: ReleaseIntentEstablishmentState
    intent: ConditionalReleaseIntent | None = None


class QualifiedReleaseIntentCustody(Protocol):
    """Atomically establish exactly one immutable intent BEFORE physical release.

    Qualified backend must persist the full request under its exact
    ReleaseOperationIdentity, with durable uniqueness across workers/restarts.
    ESTABLISHED is legal only once the new intent is durably readable and no
    previous intent existed. ALREADY_ESTABLISHED preserves the original full
    intent, CONFLICT reports reuse with different content, UNKNOWN covers
    ambiguous persistence. An exception is UNKNOWN, not a free retry.
    This is an *intent write*, NOT a publication/notification effect. It must
    never contact the physical release writer. Backend release must still
    atomically deduplicate/recheck authority when applying the real effect.
    """
    def establish_original_intent(self, *, request: ConditionalReleaseIntent) -> ReleaseIntentEstablishmentReply: ...


class QualifiedPreparedReleaseResolver(Protocol):
    """Resolve an ALREADY DURABLY ESTABLISHED original, possibly effectfully.

    Unlike read_release_outcome this call MAY complete a previously PREPARED
    release, but MUST do so atomically under the SAME immutable release key.
    A qualified backend must verify the exact full stored intent, durable
    in-progress/committed state, current academic/teacher/policy/recipient
    authority and revocations WITH any first physical release. Concurrent
    workers, retries and restarts must converge on one durable outcome. No
    negative inference is permitted from absent history or a transport error.

    This is NOT a second call to commit_if_current, a new authorization or an
    engine-managed lease. The trusted backend owns the atomic state transition.
    """
    def resolve_fixed_intent_if_current(self, *, request: ConditionalReleaseIntent) -> ConditionalReleaseReply: ...


class QualifiedOriginalReleaseIntentSource(Protocol):
    """Read only durable selection by original CAS + release purpose.

    Must return the original frozen, authenticated intent persisted BEFORE
    the first conditional release contact, or None if unestablished. None is
    NOT evidence that no external release effect happened. It must never
    choose a newer decision/generation by querying a mutable current result.
    """
    def read_fixed_intent(self, *, release: ReleaseOperationIdentity) -> ConditionalReleaseIntent | None: ...


@dataclass(frozen=True, slots=True)
class ResultReleaseObservation:
    state: ReleaseState
    original: ScoredOperationIdentity | None = None
    intent: ConditionalReleaseIntent | None = None
    receipt: ConditionalReleaseReceipt | None = None

    @property
    def authorizes_publication(self) -> bool:
        # An observation of a claimed backend effect is not a reusable credential.
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class ProductionGovernedResultRelease:
    """Consume ACTUAL fixed-original/teacher review/authorized result release/student-safe feedback owners; commit at most once.

    The callback is a trusted, deployment-controlled backend adapter, not an
    arbitrary in-process Python sandbox. No grading/physical attempt claim/provider/scored CAS,
    new teacher decision, journal append or inferred mark is performed here.
    """
    __slots__ = ('_recover', '_teacher', '_feedback', '_commit', '_limit',
                 '_gate', '_contacted', '_fixed_operation', '_history', '_original_intent', '_custody', '_prepared_resolver')

    def __init__(self, *, recovery: ProductionRecoveredOriginalGovernance,
                 teacher_review: ProductionRecoveredTeacherReviewCandidate,
                 effect_owner: QualifiedConditionalResultRelease,
                 max_identifier_characters: int,
                 feedback_candidate: ProductionRecoveredFeedbackCandidate | None = None,
                 release_history: QualifiedConditionalReleaseHistory | None = None,
                 original_intent_source: QualifiedOriginalReleaseIntentSource | None = None,
                 intent_custody: QualifiedReleaseIntentCustody | None = None,
                 prepared_resolver: QualifiedPreparedReleaseResolver | None = None):
        if (type(recovery) is not ProductionRecoveredOriginalGovernance
                or type(teacher_review) is not ProductionRecoveredTeacherReviewCandidate
                or teacher_review._recovery is not recovery
                or (feedback_candidate is not None and (
                    type(feedback_candidate) is not ProductionRecoveredFeedbackCandidate
                    or feedback_candidate._recovery is not recovery))
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or recovery._limit != max_identifier_characters):
            raise ValueError('Exact shared original, journal and bounded release installations required.')
        object.__setattr__(self, '_recover', recovery)
        object.__setattr__(self, '_teacher', teacher_review)
        object.__setattr__(self, '_feedback', feedback_candidate)
        object.__setattr__(self, '_commit', _capture(effect_owner, 'commit_if_current', ('request',)))
        object.__setattr__(self, '_limit', max_identifier_characters)
        object.__setattr__(self, '_gate', Lock())
        # Local no-resend fence. The backend still owns durable, cross-worker
        # idempotency and read-only reconciliation after uncertain contact.
        object.__setattr__(self, '_contacted', {})
        object.__setattr__(self, '_fixed_operation', None)
        object.__setattr__(self, '_history', None if release_history is None else
            _capture(release_history, 'read_release_outcome', ('request',)))
        object.__setattr__(self, '_original_intent', None if original_intent_source is None else
            _capture(original_intent_source, 'read_fixed_intent', ('release',)))
        object.__setattr__(self, '_custody', None if intent_custody is None else
            _capture(intent_custody, 'establish_original_intent', ('request',)))
        object.__setattr__(self, '_prepared_resolver', None if prepared_resolver is None else
            _capture(prepared_resolver, 'resolve_fixed_intent_if_current', ('request',)))

    def __setattr__(self, name, value):
        raise AttributeError('Release installation is immutable.')

    def transition(self, *, purpose: ReleasePurpose) -> ResultReleaseObservation:
        unknown = ResultReleaseObservation(ReleaseState.UNKNOWN)
        if type(purpose) is not ReleasePurpose:
            raise ValueError('Explicit exact result-release purpose required.')
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            return self._transition(purpose)
        except Exception:
            return unknown
        finally:
            self._gate.release()

    def reconcile(self, *, purpose: ReleasePurpose) -> ResultReleaseObservation:
        """Read a previously contacted original; NEVER contact the release writer.

        This is instance-local, same-process recovery of a prior exact intent.
        Durable post-crash recovery requires the backend's independently
        authenticated original-intent ledger and qualified read-only adapter.
        """
        if type(purpose) is not ReleasePurpose:
            raise ValueError('Explicit exact result-release purpose required.')
        unknown = ResultReleaseObservation(ReleaseState.UNKNOWN)
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            original = self._contacted.get(purpose)
            if original is None:
                return unknown
            frozen = deepcopy(original)
            operation = frozen.operation
            history = self._history
            if history is None or self._fixed_operation != operation:
                return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
            query = deepcopy(frozen)
            try:
                reply = history(request=query)
            except Exception:
                return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
            if (query != frozen or self._contacted.get(purpose) != original
                    or self._history is not history or self._fixed_operation != operation
                    or type(reply) is not ConditionalReleaseReply
                    or type(reply.intent) is not ConditionalReleaseIntent
                    or reply.intent != frozen or type(reply.state) is not ReleaseState):
                return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
            if reply.state is ReleaseState.DENIED and reply.receipt is None:
                return ResultReleaseObservation(ReleaseState.DENIED, operation, frozen)
            if reply.state is ReleaseState.RELEASED and _valid_receipt(reply.receipt, frozen, self._limit):
                return ResultReleaseObservation(ReleaseState.RELEASED, operation,
                                                frozen, deepcopy(reply.receipt))
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        except Exception:
            return unknown
        finally:
            self._gate.release()

    def reconcile_original(self, *, release: ReleaseOperationIdentity) -> ResultReleaseObservation:
        """Restart-safe *read-only* reconciliation of an independently selected original.

        Unlike ``reconcile()``, this does not depend on instance-local prior
        contact. A trusted durable source must return the EXACT original intent;
        the historical outcome must then match it. No release writer is called.
        Backend authenticity, uniqueness and atomicity need real conformance.
        """
        unknown = ResultReleaseObservation(ReleaseState.UNKNOWN)
        if not _valid_release_identity(release, self._limit):
            raise ValueError('Exact original release identity required.')
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            select, history = self._original_intent, self._history
            if select is None or history is None:
                return unknown
            key = deepcopy(release)
            original = select(release=key)
            if (key != release or not _valid_intent(original, self._limit)
                    or original.release_identity != release
                    or select is not self._original_intent or history is not self._history):
                return unknown
            frozen = deepcopy(original)
            # Historical student-safe feedback must still belong to the fixed scored original.
            # A matching persisted intent/receipt alone cannot prove that a
            # feedback question was actually scored.
            if not _valid_original_feedback_membership(self._recover, self._feedback, frozen):
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
            request = deepcopy(frozen)
            reply = history(request=request)
            if (request != frozen or key != release
                    or select is not self._original_intent or history is not self._history
                    or type(reply) is not ConditionalReleaseReply
                    or type(reply.intent) is not ConditionalReleaseIntent
                    or reply.intent != frozen or type(reply.state) is not ReleaseState):
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
            if reply.state is ReleaseState.DENIED and reply.receipt is None:
                return ResultReleaseObservation(ReleaseState.DENIED, release.original, frozen)
            if (reply.state is ReleaseState.RELEASED
                    and _valid_receipt(reply.receipt, frozen, self._limit)):
                return ResultReleaseObservation(ReleaseState.RELEASED, release.original,
                                                frozen, deepcopy(reply.receipt))
            return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
        except Exception:
            return unknown
        finally:
            self._gate.release()

    def resolve_prepared(self, *, release: ReleaseOperationIdentity) -> ResultReleaseObservation:
        """Explicit effect-capable resolution of ONE historical prepared release.

        Never replays ``commit_if_current`` and never constructs a fresh intent.
        A qualified backend must atomically decide if an effect is already
        committed, safely denied, in progress, or may be executed once under
        the same durable key. ``UNKNOWN`` is not evidence of noncommit.

        Installations without both the authenticated immutable-intent source
        and the qualified idempotent resolver fail closed. This call is NOT
        read-only: for history observation use ``reconcile_original``.
        """
        if not _valid_release_identity(release, self._limit):
            raise ValueError('Exact original release identity required.')
        unknown = ResultReleaseObservation(ReleaseState.UNKNOWN)
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            select, resolve, contacted = (
                self._original_intent, self._prepared_resolver, self._contacted)
            if select is None or resolve is None:
                return unknown
            if self._fixed_operation is not None and self._fixed_operation != release.original:
                return unknown
            if release.purpose in contacted:
                # Earlier effect or resolution is possibly committed. Never
                # make another effect-capable contact from the same owner.
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original,
                                                deepcopy(contacted[release.purpose]))
            key = deepcopy(release)
            original = select(release=key)
            if (key != release or not _valid_intent(original, self._limit)
                    or original.release_identity != release
                    or select is not self._original_intent
                    or resolve is not self._prepared_resolver):
                return unknown
            frozen = deepcopy(original)
            # Do not invoke an effect-capable PREPARED resolver for feedback
            # outside the independently recovered scored-question inventory.
            if not _valid_original_feedback_membership(self._recover, self._feedback, frozen):
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
            # PREPARED resolution is effect-capable, unlike historical read-only
            # reconciliation. Recheck installed teacher review/authorized result release/governed scored-paper handoff currentness for BOTH
            # purposes before any resolver contact. The real backend must still
            # repeat these checks atomically with publication/notification.
            if not _valid_prepared_local_authority(self._recover, self._teacher, frozen):
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
            if self._fixed_operation is None:
                object.__setattr__(self, '_fixed_operation', deepcopy(release.original))
            # Fence BEFORE the effect-capable resolver. Its ACK may be lost
            # after a real commit. Only a fresh instance may reconcile the
            # same immutable identity; backend idempotency is indispensable.
            contacted[release.purpose] = frozen
            request = deepcopy(frozen)
            try:
                reply = resolve(request=request)
            except Exception:
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
            if (key != release or request != frozen
                    or select is not self._original_intent
                    or resolve is not self._prepared_resolver
                    or contacted.get(release.purpose) != frozen
                    or self._fixed_operation != release.original
                    or type(reply) is not ConditionalReleaseReply
                    or type(reply.intent) is not ConditionalReleaseIntent
                    or reply.intent != frozen or type(reply.state) is not ReleaseState):
                return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
            if reply.state is ReleaseState.DENIED and reply.receipt is None:
                return ResultReleaseObservation(ReleaseState.DENIED, release.original, frozen)
            if (reply.state is ReleaseState.RELEASED
                    and _valid_receipt(reply.receipt, frozen, self._limit)):
                return ResultReleaseObservation(ReleaseState.RELEASED, release.original,
                                                frozen, deepcopy(reply.receipt))
            return ResultReleaseObservation(ReleaseState.UNKNOWN, release.original, frozen)
        except Exception:
            return unknown
        finally:
            self._gate.release()

    def _transition(self, purpose: ReleasePurpose) -> ResultReleaseObservation:
        recover, teacher, feedback, commit, limit, contacted = (
            self._recover, self._teacher, self._feedback, self._commit,
            self._limit, self._contacted)
        def intact():
            return (self._recover is recover and self._teacher is teacher
                    and self._feedback is feedback and self._commit is commit
                    and self._limit == limit and self._contacted is contacted)
        unknown = ResultReleaseObservation(ReleaseState.UNKNOWN)
        first = recover.recover()
        if (type(first) is not RecoveredOriginalGovernance
                or first.state is not GovernedOperationState.HANDOFF_ELIGIBLE
                or type(first.operation) is not ScoredOperationIdentity
                or first.original_c5 is None
                or type(first.handoff) is not GovernedPaperHandoff
                or first.handoff.decision.disposition is not
                    ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
                or not intact()):
            return unknown
        operation = first.operation
        handoff = first.handoff
        decision, readiness = handoff.decision, handoff.readiness
        if (type(readiness) is not AssessmentReadiness
                or readiness.state is not ReadinessState.READY
                or type(readiness.views) is not tuple or len(readiness.views) != 3
                or (decision.tenant_ref, decision.grading_run_id,
                    decision.original_scored_result_ref, decision.source_revision) !=
                   (operation.tenant_ref, operation.grading_run_id,
                    operation.original_scored_result_ref, operation.source_revision)
                or type(decision.policy_ref) is not str
                or type(decision.policy_revision) is not str):
            return unknown
        for i, v in enumerate(readiness.views):
            if (type(v) is not AssessmentViewFact
                    or v.view is not tuple(EvidenceView)[i]
                    or v.satisfactory is not True
                    or (v.origin.tenant_ref, v.origin.grading_run_id,
                        v.origin.scored_result_ref, v.origin.source_revision) !=
                       (operation.tenant_ref, operation.grading_run_id,
                        operation.original_scored_result_ref, operation.source_revision)):
                return unknown
        review = teacher.assess()
        if (type(review) is not RecoveredTeacherReviewCandidate
                or review.state is not RecoveredTeacherReviewState.RECORDED_CANDIDATE
                or review.original != operation
                or type(review.review) is not TeacherReviewRecoveryObservation
                or review.review.state is not TeacherReviewRecoveryState.COMMITTED
                or not intact()):
            return unknown
        visible = None
        binding = None
        if purpose is ReleasePurpose.STUDENT_FEEDBACK:
            if feedback is None:
                return unknown
            candidate = feedback.assess()
            if (type(candidate) is not RecoveredFeedbackCandidate
                    or candidate.state is not FeedbackCandidateState.CANDIDATE
                    or candidate.operation != operation
                    or type(candidate.feedback) is not StudentSafeFeedback
                    or type(candidate.feedback.original) is not FeedbackOriginal
                    or candidate.feedback.category in (
                        FeedbackCategory.UNKNOWN, FeedbackCategory.NOT_APPLICABLE)
                    or type(candidate.binding_revision) is not str
                    or candidate.feedback.original.question_id not in first.scored_question_ids
                    or not intact()):
                return unknown
            visible = candidate.feedback
            binding = candidate.binding_revision
        final = recover.recover()
        if (type(final) is not RecoveredOriginalGovernance or final != first or not intact()):
            return unknown
        intent = ConditionalReleaseIntent(
            purpose, operation, decision.policy_ref, decision.policy_revision,
            review.review.decision_ref, review.review.journal_event_ref,
            tuple(readiness.views), visible, binding)
        # Validate what WILL be sent, not merely the shape of the earlier source.
        if not _valid_intent(intent, limit):
            return unknown
        frozen = deepcopy(intent)
        # A second call for the same purpose and original must NEVER become
        # another effect-owner contact, even after a lost acknowledgement or
        # a malformed reply. Do not fence malformed/unqualified preflight.
        # This is process-local only: backend durable idempotency is mandatory.
        # One release-owner installation is bound to ONE fixed original.
        # The purpose fence therefore holds at most two entries, not an
        # unbounded history of unrelated scoring operations.
        fixed_operation = self._fixed_operation
        if fixed_operation is not None and fixed_operation != frozen.operation:
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if purpose in contacted:
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        # An installed durable original selector can detect a previous attempt
        # across owner instances/restarts. An absent record is NOT proof of
        # non-commit: the effect backend must still atomically deduplicate.
        selector = self._original_intent
        if selector is not None:
            try:
                key = frozen.release_identity
                prior = selector(release=deepcopy(key))
                if (prior is not None or selector is not self._original_intent
                        or not intact()):
                    return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
            except Exception:
                return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        # The release writer is unreachable without an explicit write-ahead
        # durable intent establishment. The optional constructor argument only
        # preserves source compatibility: absence is a fail-closed installation.
        custody = self._custody
        if custody is None:
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if fixed_operation is None:
            object.__setattr__(self, '_fixed_operation', deepcopy(frozen.operation))
        # Fence before even the persistence callback: if its ACK is lost after
        # persistence, another local transition must not send a release.
        contacted[purpose] = frozen
        write_request = deepcopy(frozen)
        try:
            established = custody(request=write_request)
        except Exception:
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if (write_request != frozen or custody is not self._custody
                or not intact() or contacted.get(purpose) != frozen
                or type(established) is not ReleaseIntentEstablishmentReply
                or type(established.state) is not ReleaseIntentEstablishmentState
                or type(established.intent) is not ConditionalReleaseIntent
                or not _valid_intent(established.intent, limit)
                or established.intent.release_identity != frozen.release_identity):
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if established.state is not ReleaseIntentEstablishmentState.ESTABLISHED:
            # ALREADY_ESTABLISHED (even the same immutable intent) is NOT a
            # permit to reissue; CONFLICT and UNKNOWN also never release.
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if established.intent != frozen:
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        # The backend MUST requalify all of this in its *atomic effect*; the
        # engine does not infer authorization from a READY view or teacher log.
        try:
            reply = commit(request=intent)
        except Exception:
            # A transport exception can occur AFTER a successful remote write.
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if intent != frozen or not intact():
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if (type(reply) is not ConditionalReleaseReply
                or type(reply.state) is not ReleaseState
                or type(reply.intent) is not ConditionalReleaseIntent
                or reply.intent != frozen):
            return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)
        if reply.state is ReleaseState.DENIED and reply.receipt is None:
            return ResultReleaseObservation(ReleaseState.DENIED, operation, frozen)
        if reply.state is ReleaseState.RELEASED and _valid_receipt(reply.receipt, frozen, limit):
            return ResultReleaseObservation(ReleaseState.RELEASED, operation,
                                            frozen, deepcopy(reply.receipt))
        # UNKNOWN or invalid/contradictory acknowledgement: never resend.
        return ResultReleaseObservation(ReleaseState.UNKNOWN, operation, frozen)



def _valid_prepared_local_authority(
        recovery: ProductionRecoveredOriginalGovernance,
        teacher: ProductionRecoveredTeacherReviewCandidate,
        intent: ConditionalReleaseIntent) -> bool:
    """Read-only current teacher review/authorized result release/governed scored-paper handoff preflight for an effect-capable retry.

    An immutable historical intent proves what was once prepared, not that its
    original, teacher journal, governed policy and three readiness issuers are
    still locally qualified. Never use this check as a publication credential:
    external backend effect-time authorization must still be atomic.
    """
    first = recovery.recover()
    if (type(first) is not RecoveredOriginalGovernance
            or first.state is not GovernedOperationState.HANDOFF_ELIGIBLE
            or first.operation != intent.operation
            or first.original_c5 is None
            or type(first.handoff) is not GovernedPaperHandoff):
        return False
    handoff = first.handoff
    from grading.integration.governed_result_disposition import GovernedResultDecision
    decision, readiness = handoff.decision, handoff.readiness
    if (type(decision) is not GovernedResultDecision
            or decision.disposition is not ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
            or (decision.tenant_ref, decision.grading_run_id,
                decision.original_scored_result_ref, decision.source_revision) !=
               (intent.operation.tenant_ref, intent.operation.grading_run_id,
                intent.operation.original_scored_result_ref, intent.operation.source_revision)
            or decision.policy_ref != intent.policy_ref
            or decision.policy_revision != intent.policy_revision
            or type(readiness) is not AssessmentReadiness
            or readiness.state is not ReadinessState.READY
            or type(readiness.views) is not tuple
            or readiness.views != intent.readiness_views):
        return False
    review = teacher.assess()
    if (type(review) is not RecoveredTeacherReviewCandidate
            or review.state is not RecoveredTeacherReviewState.RECORDED_CANDIDATE
            or review.original != intent.operation
            or type(review.review) is not TeacherReviewRecoveryObservation
            or review.review.state is not TeacherReviewRecoveryState.COMMITTED
            or review.review.decision_ref != intent.decision_ref
            or review.review.journal_event_ref != intent.journal_event_ref):
        return False
    last = recovery.recover()
    return (type(last) is RecoveredOriginalGovernance
            and last == first
            and teacher._recovery is recovery)


def _valid_original_feedback_membership(
        recovery: ProductionRecoveredOriginalGovernance,
        feedback_candidate: ProductionRecoveredFeedbackCandidate | None,
        intent: ConditionalReleaseIntent) -> bool:
    """Re-admit historical student-safe feedback against independent fixed-original academic proof.

    Neither a stored release intent nor its agreeing receipt proves that the
    named criterion/evidence was admitted, the error was confirmed, or the
    original-bound joint selection remains current. Reuse the installed student-safe feedback
    read-only consumer instead of creating a second academic interpreter.
    This conservative check can return UNKNOWN for a genuine historical effect
    when its original sources are unavailable. It never revokes that effect;
    the qualified backend still owns atomic effect-time currentness.
    """
    if intent.purpose is ReleasePurpose.OFFICIAL_RESULT:
        return True
    if (type(feedback_candidate) is not ProductionRecoveredFeedbackCandidate
            or feedback_candidate._recovery is not recovery):
        return False
    recovered = recovery.recover()
    if not (type(recovered) is RecoveredOriginalGovernance
            and recovered.state is GovernedOperationState.HANDOFF_ELIGIBLE
            and type(recovered.operation) is ScoredOperationIdentity
            and recovered.operation == intent.operation
            and recovered.original_c5 is not None
            and type(recovered.scored_question_ids) is tuple
            and type(intent.feedback) is StudentSafeFeedback
            and intent.feedback.question_id in recovered.scored_question_ids):
        return False
    current = feedback_candidate.assess()
    return (type(current) is RecoveredFeedbackCandidate
            and current.state is FeedbackCandidateState.CANDIDATE
            and current.operation == intent.operation
            and type(current.feedback) is StudentSafeFeedback
            and current.feedback == intent.feedback
            and type(current.binding_revision) is str
            and current.binding_revision == intent.feedback_binding_revision)


def _valid_id(value: object, limit: int) -> bool:
    return type(value) is str and 0 < len(value) <= limit and value == value.strip()


def _valid_release_identity(release: object, limit: int) -> bool:
    if (type(release) is not ReleaseOperationIdentity
            or type(release.purpose) is not ReleasePurpose
            or type(release.original) is not ScoredOperationIdentity):
        return False
    from grading.integration.production_paper_operations import PaperOperationKind
    op = release.original
    return (type(op.kind) is PaperOperationKind and
        all(_valid_id(getattr(op, n), limit) for n in (
            'tenant_ref', 'grading_run_id', 'original_scored_result_ref',
            'source_revision', 'transaction_ref', 'transaction_event_ref', 'commit_ref')))



# The restart/history path does not pass through the student-safe feedback formatter. Re-admit
# its exact Gradified-owned student wording here; equality to a durable record
# or a receipt is not sufficient to admit arbitrary academic claims.
# This contract must stay synchronized with student_safe_feedback.py's
# deliberately fixed vocabulary (covered by a differential regression).
_CANONICAL_RELEASE_FEEDBACK_MESSAGES = {
    FeedbackCategory.CONCEPTUAL_ERROR:
        'A verified conceptual issue was identified for review.',
    FeedbackCategory.CALCULATION_ERROR:
        'A verified calculation issue was identified for review.',
    FeedbackCategory.FORMULA_ERROR:
        'A verified formula issue was identified for review.',
    FeedbackCategory.INCOMPLETE_SOLUTION:
        'The admitted evidence confirms an incomplete solution.',
}


def _valid_fixed_feedback(feedback: StudentSafeFeedback, limit: int) -> bool:
    if (type(feedback) is not StudentSafeFeedback
            or type(feedback.category) is not FeedbackCategory
            or feedback.category not in _CANONICAL_RELEASE_FEEDBACK_MESSAGES
            or not _valid_id(feedback.criterion_ref, limit)
            or not _valid_id(feedback.evidence_ref, limit)
            or type(feedback.message) is not str):
        return False
    return feedback.message == _CANONICAL_RELEASE_FEEDBACK_MESSAGES[feedback.category]


def _valid_intent(i: ConditionalReleaseIntent, limit: int) -> bool:
    if type(i) is not ConditionalReleaseIntent or type(i.purpose) is not ReleasePurpose:
        return False
    op = i.operation
    if type(op) is not ScoredOperationIdentity:
        return False
    from grading.integration.production_paper_operations import PaperOperationKind
    if type(op.kind) is not PaperOperationKind or not all(_valid_id(getattr(op, n), limit)
        for n in ('tenant_ref','grading_run_id','original_scored_result_ref',
                  'source_revision','transaction_ref','transaction_event_ref','commit_ref')):
        return False
    if not all(_valid_id(v, limit) for v in (
        i.policy_ref, i.policy_revision, i.decision_ref, i.journal_event_ref)):
        return False
    if type(i.readiness_views) is not tuple or len(i.readiness_views) != 3:
        return False
    for index, view in enumerate(i.readiness_views):
        if (type(view) is not AssessmentViewFact
                or type(view.origin) is not AssessmentOrigin
                or view.view is not tuple(EvidenceView)[index]
                or view.satisfactory is not True
                or (view.origin.tenant_ref, view.origin.grading_run_id,
                    view.origin.scored_result_ref, view.origin.source_revision) !=
                   (op.tenant_ref, op.grading_run_id,
                    op.original_scored_result_ref, op.source_revision)
                or not _valid_id(view.issuer_ref, limit)
                or not _valid_id(view.issuer_revision, limit)):
            return False
    if i.purpose is ReleasePurpose.OFFICIAL_RESULT:
        return i.feedback is None and i.feedback_binding_revision is None
    f = i.feedback
    if (not _valid_fixed_feedback(f, limit)
            or type(f.original) is not FeedbackOriginal
            or not _valid_id(i.feedback_binding_revision, limit)
            or (f.original.tenant_ref,f.original.grading_run_id,
                f.original.original_scored_result_ref,f.original.source_revision) !=
                (op.tenant_ref,op.grading_run_id,
                 op.original_scored_result_ref,op.source_revision)
            or not _valid_id(f.question_id, limit)
            or f.original.question_id != f.question_id
            or not _valid_id(f.message, 1024)):
        return False
    return True


def _valid_receipt(receipt: object, original: ConditionalReleaseIntent, limit: int) -> bool:
    return (type(receipt) is ConditionalReleaseReceipt
            and type(receipt.intent) is ConditionalReleaseIntent
            and receipt.intent == original
            and all(_valid_id(v, limit) for v in (
                receipt.release_event_ref, receipt.authorization_ref,
                receipt.issuer_ref, receipt.release_generation_ref)))
