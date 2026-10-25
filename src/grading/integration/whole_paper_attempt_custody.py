"""Preserve original CHOICE paper attempts and provide read-only claim recovery.

This composes the actual installed whole-paper executor; callers cannot submit a
precomputed score or reservation as an execution grant. Returned records are
local observations, not authenticated ledger receipts, legal transitions, retry
permission, audit commits or publication. The request-source and physical-attempt backend
must be installed/qualified by the trusted workflow composition root.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.integration.attempt_authority import (
    ClaimedAttemptAllocator, AttemptClaimRequest, AttemptClaimRecoveryDisposition,
    _request_snapshot,
)
from grading.integration.evaluator_invocation import AttemptReservation, _reservation_copy
from grading.integration.execution_eligibility import _capture, _id, _scope
from grading.integration.paper_execution_correlation import _plan
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.whole_paper_choice_execution import (
    ProductionWholePaperChoiceExecutor, NonpublishingPaperOutcome,
    AttemptContactTrace, CapturedChoiceAttempt,
)
from grading.execution import GradingExecutionResult


class PaperCustodyDenied(ValueError):
    """The local result/request/recovery does not bind the original paper."""


class PaperRecoveryState(str, Enum):
    NOT_CONTACTED = 'NOT_CONTACTED'
    UNKNOWN = 'UNKNOWN'
    RESERVED = 'RESERVED'
    NOT_RESERVED = 'NOT_RESERVED'
    CONFLICT = 'CONFLICT'


@dataclass(frozen=True, slots=True, repr=False)
class QuestionAttemptCustody:
    question_id: str
    f25_call_started: bool
    request_ref: str | None
    reservation: AttemptReservation | None
    reservation_validated: bool
    evaluator_invoked: bool
    judgments_emitted: bool
    s1_verified: bool
    claim_conflict: bool
    original_f25_request: AttemptClaimRequest | None = None
    academic_preparation: object = None  # unqualified without trusted academic-bound physical claim backend
    approved_runtime: object = None  # bound original runtime approval


@dataclass(frozen=True, slots=True, repr=False)
class PaperAttemptCustody:
    """Original nonpublishing result and exact per-question effect observations."""
    plan: AdmittedPaperPlan
    outcome: NonpublishingPaperOutcome | FamilyPaperExecutionOutcome
    questions: tuple[QuestionAttemptCustody, ...]

    @property
    def nonpublishing(self) -> bool:
        return True

    @property
    def audit_commit_state(self) -> str:
        # No audit acknowledgment was consumed here. This does NOT prove that
        # an external write did or did not commit.
        return 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class QuestionAttemptClaimRecovery:
    question_id: str
    request_ref: str | None
    state: PaperRecoveryState
    reservation: AttemptReservation | None = None


@dataclass(frozen=True, slots=True, repr=False)
class PaperAttemptClaimRecovery:
    questions: tuple[QuestionAttemptClaimRecovery, ...]

    @property
    def authorizes_retry(self) -> bool:
        # In particular, even qualified NOT_RESERVED requires separate current
        # authority, backend transaction/lease, and approved legal operation transition retry policy.
        return False

    @property
    def audit_commit_state(self) -> str:
        # No audit acknowledgment was consumed here. This does NOT prove that
        # an external write did or did not commit.
        return 'UNKNOWN'


class QualifiedOriginalAttemptRequestSource(Protocol):
    """Read-only *original* issuer request; real source admission is external.

    No 'latest' or reconstructed physical attempt request. Must be authorized to read the
    exact original paper/run/question/request scope, including after restart.
    """
    def resolve_original_request(self, *, plan: AdmittedPaperPlan,
                                 question_id: str, request_ref: str) -> AttemptClaimRequest: ...


def _matches_paper(scope: object, plan: AdmittedPaperPlan, question: object,
                   maximum: int) -> bool:
    try:
        s = _scope(scope, maximum)
        r = plan.request
        return (s.actor_ref == plan.actor_ref
                and s.tenant_ref == r.tenant_ref
                and s.session_ref == r.session_ref
                and s.grading_run_id == r.grading_run_id
                and s.submission_ref == r.submission_ref
                and s.exam_ref == r.exam_ref
                and s.grading_spec_ref == r.grading_spec_ref
                and s.question_id == question.request.question_id
                and s.evidence_scope_ref == question.evidence_scope_ref
                and s.source_artifact_ref == question.source_artifact_ref
                and s.source_revision == question.source_revision
                and s.ocr_provenance == question.provenance_ref)
    except Exception:
        return False


def _admit(plan: object, outcome: object, max_questions: int,
           maximum: int) -> PaperAttemptCustody:
    """Validate facts consumed by original-attempt custody, without authenticating a school issuer."""
    try:
        admitted = _plan(plan, max_questions, maximum)
        from grading.integration.whole_paper_family_execution import (
            FamilyPaperExecutionOutcome, CapturedFamilyAttempt,
        )
        family = type(outcome) is FamilyPaperExecutionOutcome
        if (type(outcome) not in (NonpublishingPaperOutcome, FamilyPaperExecutionOutcome)
                or outcome.state not in ('COMPLETE', 'DENIED', 'UNAVAILABLE',
                       'UNSUPPORTED', 'INDETERMINATE', 'INCOMPLETE')
                or type(outcome.completed) is not tuple
                or type(outcome.observed_reservations) is not tuple
                or type(outcome.contact_trace) is not tuple
                or len(outcome.completed) > len(admitted.questions)
                or len(outcome.contact_trace) > len(admitted.questions)
                or (not family and type(outcome.failure_kind) not in (str, type(None)))):
            raise ValueError('malformed outcome')
        full = outcome.state == 'COMPLETE'
        if (full != (type(outcome.result) is GradingExecutionResult)
                or (full and outcome.failed_question_id is not None)
                or (not full and outcome.result is not None)):
            raise ValueError('unjustified complete result')
        qids = tuple(q.request.question_id for q in admitted.questions)
        if (outcome.failed_question_id is not None
                and (type(outcome.failed_question_id) is not str
                     or outcome.failed_question_id not in qids)):
            raise ValueError('foreign failed question')
        completed: dict[str, CapturedChoiceAttempt | CapturedFamilyAttempt] = {}
        used: dict[str, set[str]] = {key: set() for key in ('attempt_id', 'reservation_ref', 'request_ref')}
        for index, item in enumerate(outcome.completed):
            if (type(item) is not (CapturedFamilyAttempt if family else CapturedChoiceAttempt)
                    or (family and item.family != admitted.questions[index].family)
                    or item.question_id != qids[index]
                    or type(item.judgments) is not tuple or not item.judgments):
                raise ValueError('unbound completed attempt')
            r = _reservation_copy(item.reservation, expected=item.reservation, maximum=maximum)
            if not _matches_paper(r.scope, admitted, admitted.questions[index], maximum):
                raise ValueError('foreign reservation scope')
            if r.request_ref is None:
                raise ValueError('missing original request')
            for key in used:
                value = getattr(r, key)
                if value in used[key]:
                    raise ValueError('duplicate physical identity')
                used[key].add(value)
            completed[item.question_id] = item
        if (full and (len(completed) != len(qids)
                or tuple(q.score.question_id for q in outcome.result.questions) != qids
                or any(q.verified.evaluated_judgments != completed[q.score.question_id].judgments
                       for q in outcome.result.questions))):
            raise ValueError('incomplete final score')
        traces: dict[str, AttemptContactTrace] = {}
        all_validated = {key: set() for key in ('attempt_id', 'reservation_ref', 'request_ref')}
        all_request_refs = set()
        observations = iter(outcome.observed_reservations)
        questions = []
        for index, q in enumerate(admitted.questions):
            qid = q.request.question_id
            trace = outcome.contact_trace[index] if index < len(outcome.contact_trace) else None
            if trace is not None:
                if (type(trace) is not AttemptContactTrace or trace.question_id != qid
                        or type(trace.f25_call_started) is not bool or not trace.f25_call_started
                        or any(type(getattr(trace, key)) is not bool for key in (
                            'reservation_returned','reservation_validated',
                            'evaluator_invoked','judgments_emitted','s1_verified'))
                        or (trace.request_ref is not None
                            and _id(trace.request_ref, maximum) != trace.request_ref)
                        or (trace.s1_verified and not trace.judgments_emitted)
                        or (trace.evaluator_invoked and not trace.reservation_validated)
                        or (trace.judgments_emitted and not trace.evaluator_invoked)
                        or (trace.reservation_validated and not trace.reservation_returned)):
                    raise ValueError('invalid grading-attempt contact timeline')
                traces[qid] = trace
            original_request = None
            if trace is not None and trace.original_f25_request is not None:
                original_request = trace.original_f25_request
                original_snapshot = _request_snapshot(original_request, maximum)
                if (original_snapshot[2] != ('CHOICE' if not family else q.family)
                        or not _matches_paper(original_snapshot[0], admitted, q, maximum)):
                    raise ValueError('Original grading-attempt request observation has foreign paper scope')
            item = completed.get(qid)
            # A contradictory trace is retained as a blocking conflict, not a
            # second original request or a positive recovery credential.
            conflict = bool(original_request is not None and
                            original_snapshot[1] != trace.request_ref)
            if trace is not None and trace.request_ref is not None:
                if trace.request_ref in all_request_refs:
                    conflict = True
                all_request_refs.add(trace.request_ref)
            if item is not None and (trace is None or not trace.s1_verified or not trace.reservation_validated):
                raise ValueError('completed attempt has no verified physical timeline')
            returned = None
            if trace is not None and trace.reservation_returned:
                returned = next(observations)
                if type(returned) is not AttemptReservation:
                    raise ValueError('foreign observed reservation')
            reservation = None
            if trace is not None and trace.reservation_validated:
                reservation = _reservation_copy(returned, expected=returned, maximum=maximum)
                if not _matches_paper(reservation.scope, admitted, q, maximum):
                    raise ValueError('foreign validated reservation')
                if reservation.request_ref != trace.request_ref:
                    raise ValueError('contact request identity mismatch')
                if original_request is not None and (
                    _request_snapshot(original_request, maximum) != (
                        reservation.scope, reservation.request_ref, reservation.family,
                        reservation.runtime_id, reservation.runtime_version,
                        reservation.implementation_ref, reservation.eligibility_policy_id,
                        reservation.eligibility_policy_version,
                        reservation.predecessor_result_ref, reservation.regrade_approval_ref)):
                    raise ValueError('Verified reservation differs from original physical claim')
                for key in all_validated:
                    ref = getattr(reservation, key)
                    if ref in all_validated[key]:
                        conflict = True
                    all_validated[key].add(ref)
            if item is not None and item.reservation != reservation:
                raise ValueError('verified attempt was not the captured grading-attempt reservation')
            if trace is not None and trace.academic_preparation is not None:
                from grading.integration.academic_claim_binding import (
                    academic_intent, validate_preparation,
                )
                if original_request is None or outcome.issued_paper is None:
                    raise ValueError('Academic preclaim lacks an original authority record.')
                from grading.contracts.paper_aggregation import ResolvedPaperScoringAuthority
                # Actual scored result carries the already verified question
                # authority, while COMPLETE custody has an original paper
                # scoring authority only through its executed input path.
                # The issuer's versioned score authority is retained in the
                # preparation evidence, and CAS independently revalidates it.
                source_scoring = trace.academic_preparation.intent.scoring
                expected_preclaim = academic_intent(original_request, outcome.issued_paper,
                                                     source_scoring, maximum, max_questions)
                validate_preparation(trace.academic_preparation, expected_preclaim, maximum)
            questions.append(QuestionAttemptCustody(
                qid, trace is not None, trace.request_ref if trace else None,
                reservation, bool(trace and trace.reservation_validated),
                bool(trace and trace.evaluator_invoked),
                bool(trace and trace.judgments_emitted),
                bool(trace and trace.s1_verified), conflict, original_request,
                trace.academic_preparation if trace is not None else None,
                trace.approved_runtime if trace is not None else None))
        try:
            next(observations)
            raise ValueError('extra observed grading-attempt reservation')
        except StopIteration:
            pass
        if full and any(not q.s1_verified for q in questions):
            raise ValueError('complete result has missing verified question')
        # whole-paper is the only executor and the whole-paper result is NOT a
        # credential for audit, retry, legal operation transition or institutional publication.
        return PaperAttemptCustody(admitted, outcome, tuple(questions))
    except Exception:
        # Exit the active callback/validation handler before constructing the
        # public exception; 'raise ... from None' alone retains __context__.
        pass
    raise PaperCustodyDenied('whole-paper execution paper/attempt custody is inconsistent; never promote or retry.') from None


class ProductionPaperAttemptCustody:
    """Actual whole-paper invocation plus installed read-only physical attempt claim recovery consumer.

    No result/audit write is performed. This is original-attempt custody/original-attempt recovery only, not the complete
    whole-paper execution/teacher review state machine, provider accounting or operation-transition authorization.
    """
    __slots__ = ('_executor', '_attempts', '_resolve_request', '_maximum', '_max_questions')

    def __init__(self, *, executor: ProductionWholePaperChoiceExecutor | ProductionWholePaperFamilyExecutor,
                 attempts: ClaimedAttemptAllocator,
                 request_source: QualifiedOriginalAttemptRequestSource,
                 max_identifier_characters: int, max_questions: int):
        from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
        if (type(executor) not in (ProductionWholePaperChoiceExecutor, ProductionWholePaperFamilyExecutor)
                or type(attempts) is not ClaimedAttemptAllocator
                or executor._attempts is not attempts
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000):
            raise ValueError('Exact installed whole-paper execution/grading-attempt execution is required.')
        operation = _capture(request_source, 'resolve_original_request',
                             ('plan', 'question_id', 'request_ref'))
        object.__setattr__(self, '_executor', executor)
        object.__setattr__(self, '_attempts', attempts)
        object.__setattr__(self, '_resolve_request', operation)
        object.__setattr__(self, '_maximum', max_identifier_characters)
        object.__setattr__(self, '_max_questions', max_questions)

    def __setattr__(self, key, value):
        raise AttributeError('Installed paper custody is fixed.')

    def __delattr__(self, key):
        raise AttributeError('Installed paper custody is fixed.')

    def execute_and_capture(self, *, plan: AdmittedPaperPlan,
                            permission: PaperLifecyclePermission | None = None) -> PaperAttemptCustody:
        original = _plan(plan, self._max_questions, self._maximum)
        from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
        from grading.integration.paper_lifecycle import PaperLifecyclePermission
        if type(self._executor) is ProductionWholePaperFamilyExecutor:
            if type(permission) is not PaperLifecyclePermission:
                raise PaperCustodyDenied('Family grading-attempt needs exact original FIRST permission.')
            from grading.integration.paper_lifecycle import PaperLifecycleKind
            if permission.kind is PaperLifecycleKind.FIRST:
                outcome = self._executor.execute_first(plan=plan, permission=permission)
            elif permission.kind is PaperLifecycleKind.REGRADE:
                outcome = self._executor.execute_regrade(plan=plan, permission=permission)
            else:
                raise PaperCustodyDenied('Unsupported original family operation.')
        else:
            outcome = self._executor.execute(plan=plan)
        if _plan(plan, self._max_questions, self._maximum) != original:
            raise PaperCustodyDenied('Original paper changed during execution; effect state may be unknown.')
        return _admit(original, outcome, self._max_questions, self._maximum)

    def reconcile(self, *, record: PaperAttemptCustody) -> PaperAttemptClaimRecovery:
        """No fresh claim, no evaluator, no retry, no write, no academic grant."""
        if type(record) is not PaperAttemptCustody:
            raise PaperCustodyDenied('Paper recovery requires admitted custody.')
        original = _admit(record.plan, record.outcome, self._max_questions, self._maximum)
        if original != record:
            raise PaperCustodyDenied('Paper custody record changed.')
        fixed_plan = _plan(record.plan, self._max_questions, self._maximum)

        def unchanged_paper() -> bool:
            try:
                return _plan(record.plan, self._max_questions, self._maximum) == fixed_plan
            except Exception:
                return False

        out = []
        for q, question in zip(record.questions, record.plan.questions, strict=True):
            if q.claim_conflict:
                out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                               PaperRecoveryState.CONFLICT))
                continue
            if not q.f25_call_started:
                out.append(QuestionAttemptClaimRecovery(q.question_id, None,
                                               PaperRecoveryState.NOT_CONTACTED))
                continue
            if q.request_ref is None:
                out.append(QuestionAttemptClaimRecovery(q.question_id, None,
                                               PaperRecoveryState.UNKNOWN))
                continue
            # A future callback response must never define both sides of the
            # original-request comparison. Missing pre-claim observation gives
            # UNKNOWN, not fabricated positive original-claim recovery.
            if q.original_f25_request is None:
                out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                               PaperRecoveryState.UNKNOWN))
                continue
            expected_original = _request_snapshot(q.original_f25_request, self._maximum)
            lookup_failed = False
            try:
                request = self._resolve_request(plan=record.plan,
                    question_id=q.question_id, request_ref=q.request_ref)
            except Exception:
                # Exception origin is the installed callback, regardless of
                # exception class. Do not propagate its message/cause/context.
                lookup_failed = True
            if not unchanged_paper():
                raise PaperCustodyDenied('Paper changed during original-request lookup.')
            if lookup_failed:
                out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                               PaperRecoveryState.UNKNOWN))
                continue
            try:
                snap = _request_snapshot(request, self._maximum)
                if not unchanged_paper():
                    raise PaperCustodyDenied('Paper changed during original-request lookup.')
                if (snap != expected_original
                        or request.request_ref != q.request_ref
                        or not _matches_paper(request.scope, record.plan, question,
                                               self._maximum)
                        or request.family != question.family
                        or (q.reservation is not None and (
                            request.runtime_id != q.reservation.runtime_id
                            or request.runtime_version != q.reservation.runtime_version
                            or request.implementation_ref != q.reservation.implementation_ref
                            or request.eligibility_policy_id != q.reservation.eligibility_policy_id
                            or request.eligibility_policy_version != q.reservation.eligibility_policy_version
                            or request.predecessor_result_ref != q.reservation.predecessor_result_ref
                            or request.regrade_approval_ref != q.reservation.regrade_approval_ref))):
                    out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                                   PaperRecoveryState.CONFLICT))
                    continue
                fact = self._attempts.reconcile_request(
                    scope=request.scope, family=request.family, runtime_id=request.runtime_id,
                    runtime_version=request.runtime_version,
                    implementation_ref=request.implementation_ref,
                    eligibility_policy_id=request.eligibility_policy_id,
                    eligibility_policy_version=request.eligibility_policy_version,
                    original_request=request)
                if (_request_snapshot(request, self._maximum) != snap
                        or not unchanged_paper()):
                    raise PaperCustodyDenied('Paper or original recovery identity mutated.')
                if (_request_snapshot(fact.request, self._maximum) != snap
                        or fact.request.request_ref != q.request_ref):
                    out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                                   PaperRecoveryState.CONFLICT))
                    continue
                if fact.disposition is AttemptClaimRecoveryDisposition.RESERVED:
                    reservation = _reservation_copy(fact.reservation,
                        expected=fact.reservation, maximum=self._maximum)
                    if q.reservation is not None and reservation != q.reservation:
                        out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                                       PaperRecoveryState.CONFLICT))
                    else:
                        out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                            PaperRecoveryState.RESERVED, reservation))
                elif fact.disposition is AttemptClaimRecoveryDisposition.NOT_RESERVED:
                    # Contradiction with a previously validated physical claim.
                    out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                        PaperRecoveryState.CONFLICT if q.reservation is not None
                        else PaperRecoveryState.NOT_RESERVED))
                elif fact.disposition is AttemptClaimRecoveryDisposition.CONFLICT:
                    out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                                   PaperRecoveryState.CONFLICT))
                else:
                    out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                                   PaperRecoveryState.UNKNOWN))
            except PaperCustodyDenied:
                raise
            except Exception:
                # Denied/malformed/unavailable reads are not evidence of absence.
                out.append(QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                               PaperRecoveryState.UNKNOWN))
        if not unchanged_paper():
            raise PaperCustodyDenied('Original paper changed during reconciliation.')
        # Recovered records can be individually well-formed but collectively
        # impossible: one physical claim may not belong to two paper questions.
        # Include originally validated reservations even when a later backend
        # lookup was unavailable or contradicted them. This is a detection
        # boundary, not a new proof that any returned claim was durable.
        owners: dict[str, dict[str, set[int]]] = {
            'attempt_id': {}, 'reservation_ref': {},
        }
        for index, (original_q, recovered_q) in enumerate(
                zip(record.questions, out, strict=True)):
            for reservation in (
                    original_q.reservation,
                    recovered_q.reservation if recovered_q.state is PaperRecoveryState.RESERVED else None):
                if reservation is None:
                    continue
                for field, refs in owners.items():
                    refs.setdefault(getattr(reservation, field), set()).add(index)
        colliding = {
            index
            for refs in owners.values()
            for indices in refs.values() if len(indices) > 1
            for index in indices
        }
        for index in colliding:
            q = out[index]
            if q.state is PaperRecoveryState.RESERVED:
                # Preserve the conflicting physical facts in original custody;
                # never return them as two independent admitted reservations.
                out[index] = QuestionAttemptClaimRecovery(q.question_id, q.request_ref,
                                                  PaperRecoveryState.CONFLICT)
        return PaperAttemptClaimRecovery(tuple(out))
