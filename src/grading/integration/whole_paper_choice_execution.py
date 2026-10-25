"""whole-paper effectful CHOICE paper execution using installed physical attempt claim and deterministic question scoring and paper aggregation.

An admission record is not an execution grant.  Every question is freshly admitted
inside this call; attempts are claimed by the installed physical attempt claim allocator.  Execution
is never official or publishable, and an incomplete paper has no aggregate score.

Executable issuer/adapter implementations must be qualified by the trusted
composition root.  In-process checks do not sandbox hostile executable Python.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import local

from grading.choice_evaluator import evaluate_single_select_choice
from grading.contracts.choice import (
    DETERMINISTIC_CHOICE_EVALUATOR_ID, DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
)
from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.contracts.paper_aggregation import ResolvedPaperScoringAuthority
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.verification.evidence import verify_evaluated_judgments
from grading.execution import (
    GradingExecutionResult, GradingExecutionContext, QuestionExecutionInput,
    execute_grading_from_evaluations,
)
from grading.integration.attempt_authority import ClaimedAttemptAllocator, AttemptClaimRequest, DefinitiveAttemptClaimRefusal
from grading.integration.evaluator_invocation import (
    AttemptReservation, AttemptReservationRejected, AttemptReservationUnavailable,
    InvocationContractError, InvocationDenied, _reservation_copy,
    _validated_binding_snapshot,
)
from grading.integration.evaluator_execution_binding import ProductionExecutionHandoff, RuntimeBindingDenied
from grading.integration.paper_execution_contact import (
    ProductionPaperQuestionContact, PaperContactDenied, PaperContactUnavailable,
    PaperContactContractError,
)
from grading.integration.paper_execution_correlation import (
    IssuedPaperExecutionRelation, ProductionPaperExecutionCorrelation,
    PaperExecutionDenied as CorrelationDenied,
    PaperExecutionUnavailable, PaperExecutionContractError, _plan, _relation,
)
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.choice_binding import bind_choice_evaluation_inputs
from grading.integration.execution_eligibility import _scope, _strip


class PaperExecutionDenied(ValueError):
    """The selected paper, installed authority or fresh attempt was denied."""


class PaperExecutionUnavailable(Exception):
    """An installed authority or execution mechanism could not resolve an outcome."""


class PaperFamilyUnsupported(PaperExecutionDenied):
    """A selected family has no approved whole-paper execution implementation."""


def _make_effectful_guard():
    """Same-thread, operation-owned guard; callback-visible diagnostics do not own it.

    Qualified installed callbacks remain trusted executable code, not sandboxed.
    This only protects documented synchronous reentry against ordinary mutation.
    """
    state = local()

    def enter(root: object) -> tuple[int, object]:
        active = getattr(state, 'active', None)
        if active is None:
            active = {}
            state.active = active
        rid = id(root)
        if rid in active:
            raise PaperExecutionDenied('Nested whole-paper execution is forbidden.')
        token = object()
        active[rid] = token
        return rid, token

    def leave(lease: tuple[int, object]) -> None:
        rid, token = lease
        active = getattr(state, 'active', None)
        if active is None or active.get(rid) is not token:
            raise PaperExecutionDenied('Effectful operation ownership changed.')
        del active[rid]

    return enter, leave


_enter_effectful, _leave_effectful = _make_effectful_guard()


@dataclass(frozen=True, slots=True, repr=False)
class CapturedChoiceAttempt:
    """One physical attempt reservation and the actual emitted evaluator judgments."""
    question_id: str
    reservation: AttemptReservation
    judgments: tuple[EvaluatedCriterionJudgment, ...]


@dataclass(frozen=True, slots=True, repr=False)
class AttemptContactTrace:
    """Local observation, never an authenticated ledger or execution credential.

    Unknown/malformed post-contact facts are NOT converted into usable permits.
    A stable request ID is exposed only when physical attempt claim actually supplies one.
    """
    question_id: str
    request_ref: str | None
    f25_call_started: bool
    reservation_returned: bool
    reservation_validated: bool
    evaluator_invoked: bool
    judgments_emitted: bool
    s1_verified: bool
    # Local, detached pre-claim issuer observation. It is NOT a permit, audit
    # acknowledgment, or school-authoritative proof of backend enforcement.
    original_f25_request: AttemptClaimRequest | None = None
    academic_preparation: object = None  # backend-reported academic-bound physical claim preclaim; non-bearer
    approved_runtime: object = None  # original runtime snapshot for conditional CAS


@dataclass(frozen=True, slots=True, repr=False)
class NonpublishingPaperOutcome:
    """A complete result exists ONLY in COMPLETE; no publication authority."""
    state: str  # COMPLETE, UNSUPPORTED, DENIED, UNAVAILABLE, INDETERMINATE, INCOMPLETE
    completed: tuple[CapturedChoiceAttempt, ...]
    result: GradingExecutionResult | None
    failed_question_id: str | None
    failure_kind: str | None = None  # DENIED, UNAVAILABLE, UNKNOWN
    observed_reservations: tuple[AttemptReservation, ...] = ()
    contact_trace: tuple[AttemptContactTrace, ...] = ()
    issued_paper: IssuedPaperExecutionRelation | None = None  # original non-bearer issued relationship


class ProductionWholePaperChoiceExecutor:
    """Owns genuine CHOICE invocation and once-only whole-paper deterministic scoring/scoring.

    Caller cannot inject evaluator judgments, resolved runtime bindings, or physical attempt claim
    reservations.  External durable state, issuer authenticity and revision
    leases are governed integration prerequisites, not fabricated by this class.
    """

    __slots__ = ('_contact', '_correlation', '_handoff', '_attempts', '_limit', '_maximum', '_thread')

    def __init__(self, *, contact: ProductionPaperQuestionContact,
                 correlation: ProductionPaperExecutionCorrelation,
                 handoff: ProductionExecutionHandoff,
                 attempts: ClaimedAttemptAllocator,
                 max_identifier_characters: int, max_questions: int) -> None:
        if (type(contact) is not ProductionPaperQuestionContact
                or type(correlation) is not ProductionPaperExecutionCorrelation
                or type(handoff) is not ProductionExecutionHandoff
                or type(attempts) is not ClaimedAttemptAllocator
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10_000):
            raise ValueError('An exact installed whole-paper execution root is required.')
        handoff._require_root()
        if (contact._installation.correlation is not correlation
                or contact._installation.handoff is not handoff):
            raise ValueError('The paper contact, issuer and runtime roots differ.')
        object.__setattr__(self, '_contact', contact)
        object.__setattr__(self, '_correlation', correlation)
        object.__setattr__(self, '_handoff', handoff)
        object.__setattr__(self, '_attempts', attempts)
        object.__setattr__(self, '_limit', max_identifier_characters)
        object.__setattr__(self, '_maximum', max_questions)
        object.__setattr__(self, '_thread', local())

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError('Installed whole-paper execution root is immutable.')

    def __delattr__(self, name: str) -> None:
        raise AttributeError('Installed whole-paper execution root is immutable.')

    def _check_installed_contact(self) -> None:
        """Reuse the original criterion scoring installed graph validation, never a substituted method."""
        if type(self._contact) is not ProductionPaperQuestionContact:
            raise PaperExecutionDenied('Installed paper contact class changed.')
        ProductionPaperQuestionContact._require_installed_handoff(
            object.__getattribute__(self._contact, '_installation'))

    def _prepared(self, request: object, original: AdmittedPaperPlan, issued_question):
        """Fresh installed PRE/CHOICE/approved eligibility and execution policy, no evaluation or physical attempt effects."""
        self._check_installed_contact()
        self._handoff._require_root()
        bound = self._handoff.prepare_choice_runtime(request=request)
        self._check_installed_contact()
        snapshot = _validated_binding_snapshot(bound, handoff=self._handoff, maximum=self._limit)
        scope, selection, _, policy, _, _, _, approved, runtime = snapshot
        qid = issued_question.question_id
        if (runtime.handler is not evaluate_single_select_choice
                or scope.question_id != qid
                or scope.tenant_ref != original.request.tenant_ref
                or scope.session_ref != original.request.session_ref
                or scope.grading_run_id != original.request.grading_run_id
                or scope.submission_ref != original.request.submission_ref
                or scope.exam_ref != original.request.exam_ref
                or scope.grading_spec_ref != original.request.grading_spec_ref
                or scope.actor_ref != original.actor_ref
                or scope.source_artifact_ref != issued_question.source_artifact_ref
                or scope.source_revision != issued_question.source_revision
                or scope.evidence_scope_ref != issued_question.evidence_scope_ref
                or scope.ocr_provenance != issued_question.provenance_ref
                or selection.classification.answer_type != 'CHOICE'
                or selection.selected_capability_ref.evaluator_metadata.evaluator_id
                    != DETERMINISTIC_CHOICE_EVALUATOR_ID
                or selection.selected_capability_ref.evaluator_metadata.version
                    != DETERMINISTIC_CHOICE_EVALUATOR_VERSION):
            raise PaperExecutionDenied('Current CHOICE runtime is not authorized for the selected paper.')
        raw = bound.eligibility.admitted_choice.bound
        detached = bind_choice_evaluation_inputs(
            prepared=raw.prepared, choice_authority=raw.choice_authority,
            selection=raw.selection,
        )
        prepared = detached.prepared
        ctx = prepared.context
        qa = prepared.question_authority.scoring_authority
        paper = prepared.paper_authority
        matching = [expected for expected in paper.expected_questions if expected.question_id == qid]
        if (len(matching) != 1 or matching[0].rubric_ref.id != issued_question.rubric_ref
                or matching[0].scoring_policy_ref.id != issued_question.scoring_policy_ref
                or matching[0].rubric_ref != RubricRef(qa.rubric.rubric_id, qa.rubric.version)
                or matching[0].scoring_policy_ref != ScoringPolicyRef(
                    qa.policy.policy_id, qa.policy.version, qa.policy.scoring_semantics_version)
                or qa.rubric.question_id != qid or qa.policy.question_id != qid
                or ctx.grading_run_id != original.request.grading_run_id
                or ctx.exam_ref != original.request.exam_ref):
            raise PaperExecutionDenied('Original paper scoring authority does not bind the issuer relation.')
        return bound, snapshot, detached

    def _reconfirm_runtime(self, request, original, issued_question, snapshot, detached, baseline):
        """Re-admit the installed approval source, not the earlier detached binding.

        This is a bounded local continuity check, not an external revocation
        lease or an atomic contract between independently installed issuers.
        """
        _, current, current_inputs = self._prepared(request, original, issued_question)
        if (current != snapshot
                or current_inputs.choice_authority != detached.choice_authority
                or current_inputs.selection != detached.selection
                or current_inputs.prepared.question_authority
                   != detached.prepared.question_authority
                or (current_inputs.prepared.context,
                    current_inputs.prepared.paper_authority,
                    current_inputs.prepared.admitted_evidence.evidence) != baseline):
            raise PaperExecutionDenied('Installed evaluator approval changed during the operation.')

    def _confirm_issuer_after_runtime(self, plan, original, issued):
        """Observe paper-issued authority after the runtime resolver's callback.

        This catches *locally witnessed* cross-port changes before another
        avoidable effect. It is not an atomic joint authorization lease.
        """
        self._check_installed_contact()
        current = self._correlation.preflight(plan=plan)
        self._check_installed_contact()
        if (current.execution_state != 'CORRELATED_CHOICE_ONLY'
                or _relation(current.issuer_relation, self._maximum, self._limit) != issued
                or _plan(plan, self._maximum, self._limit) != original):
            raise PaperExecutionDenied('Paper issuer changed during runtime reconfirmation.')

    def execute(self, *, plan: AdmittedPaperPlan) -> NonpublishingPaperOutcome:
        """Execute every selected CHOICE question, or return truthful partial custody.

        No retry after uncertain physical attempt claim/evaluator contact. Missing school/provider
        facts cause denied/unavailable outcomes; they are never defaulted.
        """
        lease = _enter_effectful(self)
        completed: list[CapturedChoiceAttempt] = []
        observed: list[AttemptReservation] = []
        traces: list[AttemptContactTrace] = []
        active_id = None
        possible_contact = False
        issued = None  # preserve only actually admitted original issuance on partial results
        try:
            try:
                original = _plan(plan, self._maximum, self._limit)
                if (self._attempts._joint_effect is not None
                        and self._attempts._regrade_permission() is None
                        and self._attempts._first_permission() is None):
                    raise PaperExecutionDenied('FIRST operation authorization missing before paper contact.')
                correlation = self._correlation.preflight(plan=plan)
                issued = _relation(correlation.issuer_relation, self._maximum, self._limit)
                if (_plan(plan, self._maximum, self._limit) != original
                        or len(issued.questions) != len(original.questions)
                        or tuple(q.question_id for q in issued.questions)
                            != tuple(q.request.question_id for q in original.questions)):
                    raise PaperExecutionDenied('Whole-paper selection or issuer inventory changed.')
                if correlation.execution_state != 'CORRELATED_CHOICE_ONLY':
                    raise PaperFamilyUnsupported('Official paper includes unsupported families.')
                # Before ANY physical attempt claim, check all official questions and the complete
                # deterministic scoring paper authority. Do not score subsets or infer optional rules.
                baseline = None
                for admitted, relation in zip(original.questions, issued.questions, strict=True):
                    if admitted.family != 'CHOICE' or relation.family != 'CHOICE':
                        raise PaperFamilyUnsupported('An unsupported question family blocks the entire paper.')
                    _, _, detached = self._prepared(admitted.request, original, relation)
                    prepared = detached.prepared
                    whole = (prepared.context, prepared.paper_authority,
                             prepared.admitted_evidence.evidence)
                    if baseline is None:
                        baseline = whole
                    elif whole != baseline:
                        raise PaperExecutionDenied('Installed question inputs disagree on whole-paper scoring or evidence.')
                context, paper, evidence = baseline
                if (type(context) is not GradingExecutionContext
                        or type(paper) is not ResolvedPaperScoringAuthority
                        or tuple(q.question_id for q in paper.expected_questions)
                            != tuple(q.request.question_id for q in original.questions)):
                    raise PaperExecutionDenied('Complete official paper scoring inventory is unavailable.')
                prepared_inputs = []
                for admitted, relation in zip(original.questions, issued.questions, strict=True):
                    active_id = relation.question_id
                    # Current-question issuer is RECONTACTED here, not cached from
                    # the initial paper review or any previous grading attempt.
                    bound, snapshot, detached = self._prepared(admitted.request, original, relation)
                    if ((detached.prepared.context,
                         detached.prepared.paper_authority,
                         detached.prepared.admitted_evidence.evidence) != baseline
                            or _plan(plan, self._maximum, self._limit) != original):
                        raise PaperExecutionDenied('Current paper/source/scoring revision changed.')
                    # The preflight is run only as an immediate, freshly installed
                    # issuer check; it is NEVER consumed as a reusable credential.
                    self._check_installed_contact()
                    confirmation = ProductionPaperQuestionContact.preflight_choice(
                        self._contact, plan=plan, question_id=active_id)
                    self._check_installed_contact()
                    if (confirmation.state != 'PREFLIGHT_ONLY'
                            or confirmation.question_id != active_id
                            or confirmation.current_question != relation
                            or _relation(confirmation.current_paper, self._maximum, self._limit) != issued
                            or _plan(plan, self._maximum, self._limit) != original
                            or _validated_binding_snapshot(bound, handoff=self._handoff,
                                    maximum=self._limit) != snapshot):
                        raise PaperExecutionDenied('Current-question confirmation or source changed.')
                    # The installed current-question confirmation is a
                    # no-effect fact, not a leased permit. A callback can
                    # change the independently issued whole-paper revision
                    # while returning an otherwise valid older confirmation.
                    # Reconfirm against the fixed paper issuer immediately
                    # before starting this question's physical attempt.
                    # Real atomic revision/claim enforcement still belongs to
                    # the qualified issuer/physical-attempt backend.
                    self._check_installed_contact()
                    fresh_paper = self._correlation.preflight(plan=plan)
                    self._check_installed_contact()
                    if (fresh_paper.execution_state != 'CORRELATED_CHOICE_ONLY'
                            or _relation(fresh_paper.issuer_relation,
                                         self._maximum, self._limit) != issued
                            or _plan(plan, self._maximum, self._limit) != original
                            or _validated_binding_snapshot(bound, handoff=self._handoff,
                                    maximum=self._limit) != snapshot):
                        raise PaperExecutionDenied('Academic issuance changed during current-question confirmation.')
                    # The paper issuer itself is a callback boundary. It can
                    # change a separate installed evaluator approval while
                    # returning the previously issued paper unchanged.
                    self._reconfirm_runtime(admitted.request, original, relation,
                                            snapshot, detached, baseline)
                    self._confirm_issuer_after_runtime(plan, original, issued)
                    scope, _, _, policy, _, _, _, approved, runtime = snapshot
                    if (confirmation.runtime_id, confirmation.runtime_version,
                            confirmation.implementation_ref) != (
                            approved.runtime_id, approved.runtime_version, approved.implementation_ref):
                        raise PaperExecutionDenied('Current confirmation does not bind installed runtime.')
                    # The physical attempt claim owner guarantees atomic fresh-request claims. Its
                    # real backend must also enforce qualified policy/revision
                    # freshness or leasing; a local callback is NOT a transaction.
                    if type(self._attempts) is not ClaimedAttemptAllocator:
                        raise PaperExecutionDenied('Installed grading-attempt allocator class changed.')
                    token = self._attempts.begin_operation()
                    reservation = None
                    contact_attempted = False
                    returned = False
                    validated = False
                    evaluator_invoked = False
                    emitted_judgments = False
                    verified_s1 = False
                    stable_ref = None
                    original_f25_request = None
                    academic_preparation = None
                    try:
                        if type(self._attempts) is not ClaimedAttemptAllocator:
                            raise PaperExecutionDenied('Installed grading-attempt allocator class changed.')
                        possible_contact = True
                        contact_attempted = True
                        # Keep the original evaluator invocation reserve_attempt signature
                        # untouched. Only an installed academic-bound physical claim binder takes the
                        # academic-paper-scoped claim operation.
                        reserve = (self._attempts.reserve_academically_bound_attempt
                                   if self._attempts.academic_binding_enabled
                                   else self._attempts.reserve_attempt)
                        reservation_kwargs = dict(
                            scope=_scope(scope, self._limit), family='CHOICE',
                            runtime_id=approved.runtime_id,
                            runtime_version=approved.runtime_version,
                            implementation_ref=approved.implementation_ref,
                            eligibility_policy_id=policy.policy_id,
                            eligibility_policy_version=policy.policy_version,
                        )
                        if self._attempts.academic_binding_enabled:
                            reservation_kwargs.update(academic_paper=issued,
                                                      academic_scoring=paper,
                                                      approved_runtime=approved)
                        reservation = reserve(**reservation_kwargs)
                        # A returned physical claim is observation, not a validated
                        # execution permit. Capture it before all local checks.
                        if type(reservation) is AttemptReservation:
                            observed.append(reservation)
                            returned = True
                            if type(reservation.request_ref) is str:
                                stable_ref = reservation.request_ref
                        else:
                            raise PaperExecutionDenied('grading-attempt failed to issue an exact attempt.')
                        expected = AttemptReservation(scope, '', '', 'CHOICE',
                            approved.runtime_id, approved.runtime_version,
                            approved.implementation_ref, policy.policy_id,
                            policy.policy_version)
                        _reservation_copy(reservation, expected=expected, maximum=self._limit)
                        if reservation.request_ref is None:
                            raise PaperExecutionDenied('grading-attempt stable request reference is required.')
                        validated = True
                        if type(self._attempts) is not ClaimedAttemptAllocator:
                            raise PaperExecutionDenied('Installed grading-attempt allocator class changed.')
                        self._check_installed_contact()
                        self._handoff._require_root()
                        if (_validated_binding_snapshot(bound, handoff=self._handoff,
                                maximum=self._limit) != snapshot
                                or _plan(plan, self._maximum, self._limit) != original):
                            raise PaperExecutionDenied('Runtime or official paper changed after grading-attempt claim.')
                        # A physically issued physical attempt claim can invoke an installed
                        # backend callback after the last paper-issuer preflight.
                        # Keep the claim as actual custody, but do not evaluate
                        # or finalize a grade under an independently changed
                        # original academic issuer. This is a local continuity
                        # check, not a distributed revision lease or an physical attempt claim undo.
                        self._check_installed_contact()
                        after_f25 = self._correlation.preflight(plan=plan)
                        self._check_installed_contact()
                        if (after_f25.execution_state != 'CORRELATED_CHOICE_ONLY'
                                or _relation(after_f25.issuer_relation,
                                             self._maximum, self._limit) != issued
                                or _plan(plan, self._maximum, self._limit) != original
                                or _validated_binding_snapshot(bound, handoff=self._handoff,
                                        maximum=self._limit) != snapshot):
                            raise PaperExecutionDenied('Academic issuance changed during the physical attempt claim.')
                        # physical attempt claim's physical callback may likewise change the
                        # independent runtime source. Preserve real claim
                        # custody but withhold evaluation of that claim.
                        self._reconfirm_runtime(admitted.request, original, relation,
                                                snapshot, detached, baseline)
                        self._confirm_issuer_after_runtime(plan, original, issued)
                        if (reservation.attempt_id in {a.reservation.attempt_id for a in completed}
                                or reservation.reservation_ref in {a.reservation.reservation_ref for a in completed}
                                or reservation.request_ref in {a.reservation.request_ref for a in completed}):
                            raise PaperExecutionDenied('grading-attempt reused physical attempt or reservation identity.')
                        # Real original frozen handler; no caller-provided or
                        # replayed judgments ever enter this call frame.
                        evaluator_invoked = True
                        emitted = evaluate_single_select_choice(
                            authority=detached.choice_authority,
                            selection=detached.selection,
                            scoring_authority=detached.prepared.question_authority.scoring_authority,
                        )
                        emitted_judgments = True
                        if (type(emitted) is not tuple or not emitted
                                or any(type(j) is not EvaluatedCriterionJudgment for j in emitted)
                                or tuple(j.criterion_id for j in emitted) != tuple(
                                    c.criterion_id for c in detached.prepared.question_authority.scoring_authority.rubric.criteria)):
                            raise PaperExecutionDenied('Installed evaluator returned invalid judgments.')
                        self._check_installed_contact()
                        if (_validated_binding_snapshot(bound, handoff=self._handoff,
                                maximum=self._limit) != snapshot
                                or _plan(plan, self._maximum, self._limit) != original):
                            raise PaperExecutionDenied('Source changed during evaluator invocation.')
                        # Verify actual emitted evidence BEFORE contacting the
                        # next question, then deterministic scoring verifies again in the canonical
                        # whole-paper consumer at the final scoring boundary.
                        verified = verify_evaluated_judgments(
                            evidence=evidence, question_id=active_id, judgments=emitted)
                        if verified.evaluated_judgments != emitted:
                            raise PaperExecutionDenied('evidence verification verified a different evaluator emission.')
                        verified_s1 = True
                        completed.append(CapturedChoiceAttempt(active_id, reservation, emitted))
                        prepared_inputs.append(QuestionExecutionInput(active_id, emitted,
                            detached.prepared.question_authority.scoring_authority))
                    finally:
                        # Even when physical attempt claim throws after a possible commit, recover
                        # its *known* stable request reference before operation
                        # cleanup. Never make up an attempt or reservation ID.
                        if contact_attempted and stable_ref is None:
                            try:
                                context_ref = self._attempts.current_request_context()
                                if (type(context_ref) is tuple and len(context_ref) == 4
                                        and type(context_ref[1]) is str):
                                    stable_ref = context_ref[1]
                            except Exception:
                                pass  # absence remains an explicit unknown
                        if contact_attempted:
                            try:
                                original_f25_request = self._attempts.observed_original_request()
                            except Exception:
                                pass  # never reconstruct a missing original from recovery
                            try:
                                academic_preparation = self._attempts.observed_academic_preparation()
                            except Exception:
                                pass  # no proof may be invented after a callback failure
                            traces.append(AttemptContactTrace(
                                active_id, stable_ref, True, returned, validated,
                                evaluator_invoked, emitted_judgments, verified_s1,
                                original_f25_request, academic_preparation, approved))
                        self._attempts.finish_operation(token=token)
                    # A failed release still leaves potentially consumed physical attempt claim
                    # and evaluator effects; only clean release closes the span.
                    possible_contact = False
                # Complete inventory only. One invocation of the accepted deterministic scoring +
                # frozen criterion scoring/scoring aggregation engine, not one scoring pass per question.
                if tuple(c.question_id for c in completed) != tuple(
                        q.request.question_id for q in original.questions):
                    raise PaperExecutionDenied('Paper attempt inventory is incomplete.')
                execution = execute_grading_from_evaluations(
                    context=context, evidence=evidence, questions=tuple(prepared_inputs),
                    paper_authority=paper,
                )
                return NonpublishingPaperOutcome('COMPLETE', tuple(completed), execution, None, None, tuple(observed), tuple(traces), issued)
            except PaperFamilyUnsupported:
                return NonpublishingPaperOutcome('UNSUPPORTED', tuple(completed), None,
                                                 active_id, 'UNSUPPORTED', tuple(observed), tuple(traces), issued)
            except (PaperExecutionDenied, CorrelationDenied, PaperContactDenied, PaperExecutionContractError,
                    PaperContactContractError, RuntimeBindingDenied, InvocationDenied,
                    AttemptReservationRejected) as exc:
                state = 'INCOMPLETE' if completed else 'DENIED'
                if possible_contact and not isinstance(exc, DefinitiveAttemptClaimRefusal):
                    state = 'INDETERMINATE'
                return NonpublishingPaperOutcome(state, tuple(completed), None, active_id,
                                                 'UNKNOWN' if state == 'INDETERMINATE' else 'DENIED',
                                                 tuple(observed), tuple(traces), issued)
            except (PaperContactUnavailable, PaperExecutionUnavailable,
                    AttemptReservationUnavailable) as exc:
                return NonpublishingPaperOutcome(
                    'INDETERMINATE' if possible_contact else ('INCOMPLETE' if completed else 'UNAVAILABLE'),
                    tuple(completed), None, active_id,
                    'UNKNOWN' if possible_contact else 'UNAVAILABLE', tuple(observed), tuple(traces), issued)
            except Exception:
                # Includes technical evaluator, deterministic scoring and frozen scorer exceptions;
                # physical attempt claim may already have consumed one or more real attempts.
                return NonpublishingPaperOutcome(
                    'INDETERMINATE' if possible_contact or completed else 'UNAVAILABLE',
                    tuple(completed), None, active_id,
                    'UNKNOWN' if possible_contact or completed else 'UNAVAILABLE', tuple(observed), tuple(traces), issued)
        finally:
            _leave_effectful(lease)
