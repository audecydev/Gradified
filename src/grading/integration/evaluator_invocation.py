"""evaluator invocation single-question CHOICE invocation from an installed whole-paper execution/execution eligibility/evaluator handler binding root.

This runs the actual frozen evaluator and scoring consumer in one owned call frame.
Neither a returned candidate nor an attempt reservation is a publication credential.
The attempt-claim port MUST be supplied by an authorized production allocator before live use;
structural tests cannot establish uniqueness, durability, or issuer authentication.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import local
from typing import Protocol

from grading.choice_evaluator import evaluate_single_select_choice
from grading.contracts.choice import (
    DETERMINISTIC_CHOICE_EVALUATOR_ID, DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    ChoiceEvaluationError,
)
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
from grading.contracts.errors import ScoringError
from grading.contracts.result import (
    PaperScoreResult, QuestionScoreResult, RubricRef, ScoringPolicyRef,
    CriterionEffect, RuleDecision, ScoreStageEffect, ScoreStage,
)
from grading.contracts.paper_aggregation import (
    GradingSpecRef, _validate_grading_spec_ref, _validate_rubric_ref,
    _validate_scoring_policy_ref, _validate_scoring_decimal_structure,
    _validate_identifier, _validate_positive_version,
)
from grading.verification.evidence import EvidenceVerificationError, VerifiedCriterionJudgments
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.scoring.paper_aggregation import _validate_consumed_score_fields
from grading.scoring.arithmetic import exact_compare
from grading.execution import (
    GradingExecutionResult, InvalidGradingExecutionError, QuestionExecutionInput,
    QuestionExecutionRecord,
    execute_grading_from_evaluations,
)
from grading.integration.choice_authority_admission import (
    ChoiceAdmissionScope, ChoiceAdmissionDenied, ChoiceAdmissionUnavailable,
    ChoiceAdmissionContractError,
)
from grading.integration.authorized_preparation import (
    PreparationAuthorizationRejected, PreparationAuthorityUnavailable,
    PreparationAuthorityContractError,
)
from grading.integration.trusted_preparation import (
    PreparationScopeRejected, PreparationSourceUnavailable,
    PreparationSourceContractError, PreparationResourceLimitError,
)
from grading.integration.choice_binding import (
    ChoiceInputBindingError, bind_choice_evaluation_inputs,
)
from grading.integration.evaluator_execution_binding import (
    BoundEvaluatorRuntime, ProductionExecutionHandoff, RuntimeBindingDenied,
    _runtime_record, _installed_snapshot,
)
from grading.integration.execution_eligibility import (
    ExecutionEligibilityDenied, ExecutionEligibilityUnavailable,
    ExecutionEligibilityContractError, AdmittedExecutionEligibility,
    _capture, _choice_identity, _id, _scope, _strip,
    _selection, _facts, _policy, _attr,
)


# These are the accepted frozen implementations at module installation time.
# Installed invokers retain the objects themselves, never call mutable aliases.
_EXPECTED_CHOICE_BINDER = bind_choice_evaluation_inputs
_EXPECTED_S2A_CONSUMER = execute_grading_from_evaluations


class InvocationDenied(ValueError):
    """Installed authority, reservation, or source continuity does not permit invocation."""


class InvocationUnavailable(Exception):
    """Attempt authority or evaluator execution was unavailable; outcome may be unknown."""


class InvocationContractError(ValueError):
    """Installed port or emitted result violates the exact CHOICE contract."""


class AttemptReservationRejected(Exception):
    """physical attempt claim authority explicitly refused the requested attempt reservation."""


class AttemptReservationUnavailable(Exception):
    """physical attempt claim authority cannot establish an authoritative reservation outcome."""


@dataclass(frozen=True, slots=True, repr=False)
class AttemptReservation:
    """attempt issuer's reported reservation; structural data, not durability proof."""
    scope: ChoiceAdmissionScope
    attempt_id: str
    reservation_ref: str
    family: str
    runtime_id: str
    runtime_version: str
    implementation_ref: str
    eligibility_policy_id: str
    eligibility_policy_version: int
    request_ref: str | None = None  # required by claimed physical attempt claim; optional only in old fixtures
    predecessor_result_ref: str | None = None
    regrade_approval_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class OneQuestionExecutionCandidate:
    """Owned-call result, never independently transferable execution authority."""
    reservation: AttemptReservation
    emitted_judgments: tuple[EvaluatedCriterionJudgment, ...]
    execution: GradingExecutionResult


class AttemptReservationAuthority(Protocol):
    """Trusted installed attempt-claim port; not evidence of a production deployment.

    Raise AttemptReservationRejected for explicit refusal, or
    AttemptReservationUnavailable when no authoritative answer is possible.
    Other exceptions are technical failures with potentially unknown outcome.
    """
    def reserve_attempt(self, *, scope: ChoiceAdmissionScope, family: str,
                        runtime_id: str, runtime_version: str,
                        implementation_ref: str, eligibility_policy_id: str,
                        eligibility_policy_version: int) -> AttemptReservation: ...


def _reservation_copy(value: object, *, expected: AttemptReservation, maximum: int) -> AttemptReservation:
    if type(value) is not AttemptReservation:
        raise InvocationContractError('grading attempt reservation has invalid type.')
    try:
        reservation = AttemptReservation(
            scope=_scope(object.__getattribute__(value, 'scope'), maximum),
            attempt_id=_id(object.__getattribute__(value, 'attempt_id'), maximum),
            reservation_ref=_id(object.__getattribute__(value, 'reservation_ref'), maximum),
            family=_id(object.__getattribute__(value, 'family'), maximum),
            runtime_id=_id(object.__getattribute__(value, 'runtime_id'), maximum),
            runtime_version=_id(object.__getattribute__(value, 'runtime_version'), maximum),
            implementation_ref=_id(object.__getattribute__(value, 'implementation_ref'), maximum),
            eligibility_policy_id=_id(object.__getattribute__(value, 'eligibility_policy_id'), maximum),
            eligibility_policy_version=object.__getattribute__(value, 'eligibility_policy_version'),
            request_ref=object.__getattribute__(value, 'request_ref'),
            predecessor_result_ref=object.__getattribute__(value,'predecessor_result_ref'),
            regrade_approval_ref=object.__getattribute__(value,'regrade_approval_ref'),
        )
        if reservation.request_ref is not None:
            _id(reservation.request_ref, maximum)
        if (reservation.predecessor_result_ref is None) != (reservation.regrade_approval_ref is None):
            raise InvocationContractError('grading-attempt regrade lineage is incomplete.')
        for reference in (reservation.predecessor_result_ref,reservation.regrade_approval_ref):
            if reference is not None:
                _id(reference, maximum)
        if (type(reservation.eligibility_policy_version) is not int
                or reservation.eligibility_policy_version <= 0):
            raise InvocationContractError('grading-attempt policy version is invalid.')
    except (AttributeError, ExecutionEligibilityContractError, ValueError, TypeError):
        raise InvocationContractError('grading attempt reservation is malformed.') from None
    if (reservation.scope != expected.scope
            or reservation.family != expected.family
            or reservation.runtime_id != expected.runtime_id
            or reservation.runtime_version != expected.runtime_version
            or reservation.implementation_ref != expected.implementation_ref
            or reservation.eligibility_policy_id != expected.eligibility_policy_id
            or reservation.eligibility_policy_version != expected.eligibility_policy_version):
        raise InvocationDenied('grading-attempt reservation does not match the installed invocation.')
    return reservation


def _validated_binding_snapshot(
    bound: object, *, handoff: ProductionExecutionHandoff, maximum: int,
) -> tuple[object, ...]:
    """Pure, bounded handler-binding handoff snapshot; no issuer or evaluator effects.

    Capture before invoking physical attempt claim, then revalidate after every external effect.
    Validate exact domain types before comparing returned values.
    """
    if type(bound) is not BoundEvaluatorRuntime:
        raise InvocationContractError('evaluator handoff returned an invalid runtime handoff.')
    eligibility = _attr(bound, 'eligibility')
    if type(eligibility) is not AdmittedExecutionEligibility:
        raise InvocationContractError('evaluator handoff eligibility is not an exact admitted record.')
    installed = handoff._installation.runtime._installation
    scope = _scope(_attr(eligibility, 'scope'), maximum)
    selected = _selection(_attr(eligibility, 'selection'), maximum)
    ref = selected.selected_capability_ref
    facts = _facts(_attr(eligibility, 'facts'), scope, ref, maximum, installed.fact_limit)
    policy = _policy(_attr(eligibility, 'policy'), scope, ref, maximum, installed.fact_limit)
    key_revision = _id(_attr(eligibility, 'key_revision'), maximum)
    selection_revision = _id(_attr(eligibility, 'selection_revision'), maximum)
    admitted = _choice_identity(_attr(eligibility, 'admitted_choice'), maximum)
    approved = _runtime_record(
        _attr(bound, 'approved_runtime'), eligibility, maximum, installed.modality_limit,
    )
    runtime = _installed_snapshot(_attr(bound, 'installed'), maximum)
    if (scope != admitted[0] or key_revision != admitted[4]
            or selection_revision != admitted[5]
            or approved.family != 'CHOICE' or runtime.family != approved.family
            or (runtime.runtime_id, runtime.runtime_version, runtime.implementation_ref)
               != (approved.runtime_id, approved.runtime_version, approved.implementation_ref)
):
        raise InvocationDenied('evaluator handoff or CHOICE admission identity changed.')
    return (scope, selected, facts, policy, key_revision, selection_revision,
            admitted, approved, runtime)



def _owned_result_field(record: object, name: str) -> object:
    """Read an already exact-known slotted contract record without descriptor lookup."""
    return object.__getattribute__(record, name)


def _owned_ref_identity(ref: object, kind: str) -> tuple[object, ...]:
    """Check the full reference's primitive identity before ANY value comparison."""
    if kind == 'spec':
        _validate_grading_spec_ref(ref, error_type=InvocationContractError)
        return (_owned_result_field(ref, 'id'), _owned_result_field(ref, 'version'))
    if kind == 'rubric':
        _validate_rubric_ref(ref, field_name='result.rubric_ref',
                             error_type=InvocationContractError)
        return (_owned_result_field(ref, 'id'), _owned_result_field(ref, 'version'))
    _validate_scoring_policy_ref(ref, field_name='result.scoring_policy_ref',
                                 error_type=InvocationContractError,
                                 require_supported_semantics=True)
    return (_owned_result_field(ref, 'id'), _owned_result_field(ref, 'version'),
            _owned_result_field(ref, 'scoring_semantics_version'))


def _owned_scoring_decimal(value: object) -> None:
    _validate_scoring_decimal_structure(value, field_name='owned_s2a.score',
                                         error_type=InvocationContractError)


def _owned_result_shape(result: object, *, context: object, scope: object,
                        emitted: tuple[EvaluatedCriterionJudgment, ...],
                        paper: object, question: object) -> None:
    """Re-admit the COMPLETE exposed criterion scoring/scoring aggregation result shape, not scoring arithmetic.

    Exact records are not inherently trustworthy: frozen slotted records may be
    altered using privileged Python. Check scalar types and canonical numbers
    before comparisons; do not call untrusted attributes/equality/conversions.
    """
    try:
        if type(result) is not GradingExecutionResult:
            raise InvocationContractError('Owned scoring result has invalid type.')
        questions = _owned_result_field(result, 'questions')
        paper_score = _owned_result_field(result, 'paper_score')
        if (type(questions) is not tuple or len(questions) != 1
                or type(questions[0]) is not QuestionExecutionRecord
                or type(paper_score) is not PaperScoreResult):
            raise InvocationContractError('Owned scoring result has invalid nested shape.')
        record = questions[0]
        verified = _owned_result_field(record, 'verified')
        score = _owned_result_field(record, 'score')
        if type(verified) is not VerifiedCriterionJudgments or type(score) is not QuestionScoreResult:
            raise InvocationContractError('Owned scoring result has invalid question records.')

        v_question = _owned_result_field(verified, 'question_id')
        v_submission = _owned_result_field(verified, 'submission_ref')
        s_question = _owned_result_field(score, 'question_id')
        for ident in (v_question, v_submission, s_question):
            _validate_identifier(ident, field_name='owned_s2a.identity',
                                 error_type=InvocationContractError)
        projections = _owned_result_field(verified, 'scoring_judgments')
        if (type(projections) is not tuple or len(projections) != len(emitted)
                or any(type(x) is not CriterionJudgment for x in projections)):
            raise InvocationContractError('Owned scoring verification projection is malformed.')
        # Check every primitive field before comparing validated values.
        for evaluated, projected in zip(emitted, projections):
            if type(evaluated) is not EvaluatedCriterionJudgment:
                raise InvocationContractError('Owned scoring emitted record is invalid.')
            replace(evaluated)
            metadata = _owned_result_field(evaluated, 'evaluator_metadata')
            if type(metadata) is not EvaluatorMetadata:
                raise InvocationContractError('Owned evaluator metadata is malformed.')
            replace(metadata)
            for key in ('criterion_id', 'selected_level'):
                v1 = _owned_result_field(evaluated, key)
                v2 = _owned_result_field(projected, key)
                for value in (v1, v2):
                    _validate_identifier(value, field_name='owned_s2a.criterion',
                                         error_type=InvocationContractError)
                if v1 != v2:
                    raise InvocationContractError('Owned scoring projection origin changed.')

        q_scores = _owned_result_field(paper_score, 'question_results')
        if (type(q_scores) is not tuple or len(q_scores) != 1 or q_scores[0] is not score
                or _owned_result_field(verified, 'evaluated_judgments') is not emitted
                or _owned_result_field(result, 'context') is not context):
            raise InvocationContractError('Owned scoring result does not preserve object identity.')

        spec = _owned_ref_identity(_owned_result_field(paper_score, 'grading_spec_ref'), 'spec')
        expected_spec = _owned_ref_identity(_owned_result_field(context, 'grading_spec_ref'), 'spec')
        rubric = _owned_ref_identity(_owned_result_field(score, 'rubric_ref'), 'rubric')
        policy = _owned_ref_identity(_owned_result_field(score, 'scoring_policy_ref'), 'policy')
        expected_question = _owned_result_field(paper, 'expected_questions')[0]
        expected_rubric = _owned_ref_identity(_owned_result_field(expected_question, 'rubric_ref'), 'rubric')
        expected_policy = _owned_ref_identity(_owned_result_field(expected_question, 'scoring_policy_ref'), 'policy')
        if (spec != expected_spec or rubric != expected_rubric or policy != expected_policy
                or v_question != scope.question_id or v_submission != scope.submission_ref
                or s_question != scope.question_id):
            raise InvocationContractError('Owned scoring result does not retain invocation origin.')

        for result_record in (score, paper_score):
            profile = _owned_result_field(result_record, 'numeric_profile_version')
            if type(profile) is not str or profile != NUMERIC_PROFILE_VERSION:
                raise InvocationContractError('Owned scoring numerical profile is invalid.')
        for field in ('base_subtotal', 'score_before_rounding', 'final_score',
                      'minimum_score', 'maximum_score'):
            _owned_scoring_decimal(_owned_result_field(score, field))
        for field in ('final_score', 'minimum_score', 'maximum_score'):
            _owned_scoring_decimal(_owned_result_field(paper_score, field))
        # Reuse scoring aggregation's already frozen numerical range rules (no new reducer).
        _validate_consumed_score_fields(score, result_index=0)
        if (exact_compare(paper_score.minimum_score, paper_score.maximum_score) > 0
                or exact_compare(paper_score.final_score, paper_score.minimum_score) < 0
                or exact_compare(paper_score.final_score, paper_score.maximum_score) > 0):
            raise InvocationContractError('Owned scoring paper score has an invalid range.')

        # Finite provenance limits are derived from the admitted scoring
        # authority, never guessed from a test fixture or artificial constant.
        policy_authority = _owned_result_field(
            _owned_result_field(question, 'scoring_authority'), 'policy')
        dependency_count = len(policy_authority.positive_credit_dependencies)
        rule_count = sum(len(values) for values in (
            policy_authority.positive_credit_dependencies,
            policy_authority.gates, policy_authority.caps,
            policy_authority.deductions))
        if (type(score.criterion_effects) is not tuple
                or len(score.criterion_effects) != len(emitted)
                or type(score.rule_decisions) is not tuple
                or len(score.rule_decisions) != rule_count
                or type(score.stage_effects) is not tuple
                or len(score.stage_effects) != 4):
            raise InvocationContractError('Owned scoring provenance inventory is invalid.')
        # Validate the structural provenance of *every* exposed scoring layer.
        specs = (
            ('criterion_effects', CriterionEffect,
             ('criterion_id', 'selected_level'),
             ('base_contribution', 'effective_contribution'),
             ('blocking_dependency_rule_ids',)),
            ('rule_decisions', RuleDecision, ('rule_id',),
             ('configured_effect',), ()),
            ('stage_effects', ScoreStageEffect, (),
             ('before', 'after'), ('source_rule_ids',)),
        )
        for field, element_type, ids, nums, tuple_fields in specs:
            items = _owned_result_field(score, field)
            if type(items) is not tuple:
                raise InvocationContractError('Owned scoring score provenance is malformed.')
            for item in items:
                if type(item) is not element_type:
                    raise InvocationContractError('Owned scoring score provenance item is malformed.')
                # Reconstruct exact trusted records to reuse their closed enum,
                # tuple and primitive-type checks. Never trust their original __post_init__.
                replace(item)
                for key in ids:
                    _validate_identifier(_owned_result_field(item, key),
                                         field_name='owned_s2a.provenance',
                                         error_type=InvocationContractError)
                for key in nums:
                    numeric = _owned_result_field(item, key)
                    if numeric is not None:
                        _owned_scoring_decimal(numeric)
                for key in tuple_fields:
                    refs = _owned_result_field(item, key)
                    allowed_count = (dependency_count if key == 'blocking_dependency_rule_ids'
                                     else rule_count)
                    if type(refs) is not tuple or len(refs) > allowed_count:
                        raise InvocationContractError('Owned scoring provenance references are malformed.')
                    for ref in refs:
                        _validate_identifier(ref, field_name='owned_s2a.provenance_ref',
                                             error_type=InvocationContractError)

        effects = _owned_result_field(score, 'criterion_effects')
        if (len(effects) != len(emitted)
                or any(effect.criterion_id != judgment.criterion_id
                       or effect.selected_level != judgment.selected_level
                       for effect, judgment in zip(effects, emitted))):
            raise InvocationContractError('Owned scoring criterion provenance identity changed.')
        # These lists are defined by the installed immutable scoring authority;
        # ensure that *all* provenance records are retained, without
        # re-evaluating conditions, contributions, caps or reductions.
        rule_ids = tuple(sorted(
            rule.rule_id for collection in (
                policy_authority.positive_credit_dependencies,
                policy_authority.gates, policy_authority.caps,
                policy_authority.deductions)
            for rule in collection))
        decisions = _owned_result_field(score, 'rule_decisions')
        if tuple(decision.rule_id for decision in decisions) != rule_ids:
            raise InvocationContractError('Owned scoring rule provenance is incomplete.')
        stages = _owned_result_field(score, 'stage_effects')
        if (tuple(stage.stage for stage in stages) !=
                (ScoreStage.GATES, ScoreStage.CAPS, ScoreStage.DEDUCTIONS, ScoreStage.ROUNDING)):
            raise InvocationContractError('Owned scoring stage provenance is incomplete.')
    except InvocationContractError:
        raise
    except Exception:
        # The scorer may have already executed and physical attempt claim may have reserved.
        # A corrupted returned contract is not automatically an physical attempt claim outage.
        raise InvocationContractError('Owned scoring result is structurally malformed.') from None


@dataclass(frozen=True, slots=True, repr=False)
class _InvocationInstallation:
    handoff: ProductionExecutionHandoff
    allocator_operation: object
    choice_binder: object
    s2a_consumer: object
    identifier_limit: int
    thread_state: object


class ProductionChoiceEvaluatorInvoker:
    """Trusted composition root; no API accepts external BoundEvaluatorRuntime/Judgments."""
    __slots__ = ('_installation',)

    def __setattr__(self, name: str, value: object) -> None:
        if name == '_installation':
            try:
                object.__getattribute__(self, '_installation')
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed invocation configuration is immutable.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == '_installation':
            raise AttributeError('Installed invocation configuration cannot be deleted.')
        object.__delattr__(self, name)

    def __init__(self, *, handoff: ProductionExecutionHandoff,
                 attempts: AttemptReservationAuthority,
                 max_identifier_characters: int) -> None:
        # Final sanitation occurs outside the inner translation handler. A new
        # exception raised *inside* its except block otherwise acquires the
        # handled private exception in __context__, even with ``from None``.
        try:
            try:
                self._install(handoff=handoff, attempts=attempts,
                              max_identifier_characters=max_identifier_characters)
            except InvocationContractError:
                raise
            except Exception:
                # Unexpected installation failures must not expose adapter or
                # inspection details; never catch process-level BaseException.
                raise InvocationContractError('Installed invocation configuration is invalid.') from None
        except InvocationContractError as exc:
            # Strip after the public exception has actually been raised:
            # implicit Python exception chaining is attached at raise-time.
            _strip(exc)
            raise

    def _install(self, *, handoff: ProductionExecutionHandoff,
                 attempts: AttemptReservationAuthority,
                 max_identifier_characters: int) -> None:
        try:
            if type(handoff) is not ProductionExecutionHandoff:
                raise InvocationContractError('An installed whole-paper execution/execution eligibility/evaluator handoff is required.')
            if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
                raise InvocationContractError('An explicit identifier limit is required.')
            if (bind_choice_evaluation_inputs is not _EXPECTED_CHOICE_BINDER
                    or execute_grading_from_evaluations is not _EXPECTED_S2A_CONSUMER):
                raise InvocationContractError('Accepted CHOICE binding or scoring operation changed before installation.')
            handoff._require_root()
            operation = _capture(attempts, 'reserve_attempt', (
                'scope', 'family', 'runtime_id', 'runtime_version', 'implementation_ref',
                'eligibility_policy_id', 'eligibility_policy_version',
            ))
        except (InvocationContractError, ExecutionEligibilityContractError, RuntimeBindingDenied):
            raise InvocationContractError('Installed invocation configuration is invalid.') from None
        self._installation = _InvocationInstallation(
            handoff, operation, _EXPECTED_CHOICE_BINDER, _EXPECTED_S2A_CONSUMER,
            max_identifier_characters, local(),
        )

    def run_one_question(self, *, request: object) -> OneQuestionExecutionCandidate:
        # Outer public boundary cleans the *already raised* public exception.
        # Technical or confidential exceptions must not escape to caller APIs.
        try:
            return self._run_with_error_mapping(request=request)
        except (InvocationDenied, InvocationUnavailable, InvocationContractError) as exc:
            _strip(exc)
            raise

    def _run_with_error_mapping(self, *, request: object) -> OneQuestionExecutionCandidate:
        state = self._installation.thread_state
        if getattr(state, 'busy', False):
            raise InvocationDenied('Nested invocation on one installed root is forbidden.')
        state.busy = True
        try:
            return self._run_one_question(request=request)
        except (InvocationDenied, InvocationUnavailable, InvocationContractError):
            raise
        except (ChoiceAdmissionDenied, PreparationAuthorizationRejected,
                PreparationScopeRejected, ExecutionEligibilityDenied, RuntimeBindingDenied):
            raise InvocationDenied('Installed admission or runtime denied invocation.') from None
        except (ChoiceAdmissionUnavailable, PreparationAuthorityUnavailable,
                PreparationSourceUnavailable, ExecutionEligibilityUnavailable):
            raise InvocationUnavailable('Installed admission or runtime unavailable.') from None
        except (ChoiceAdmissionContractError, PreparationAuthorityContractError,
                PreparationSourceContractError, PreparationResourceLimitError,
                ExecutionEligibilityContractError):
            raise InvocationContractError('Installed admission or runtime contract invalid.') from None
        except Exception:
            # The public entry point must not return a raw implementation or
            # backend exception (or assume a reservation was not committed).
            raise InvocationUnavailable('Installed execution failed technically; attempt status may be uncertain.') from None
        finally:
            state.busy = False

    def _run_one_question(self, *, request: object) -> OneQuestionExecutionCandidate:
        config = self._installation
        root = config.handoff
        root._require_root()
        # Real whole-paper execution/PRE, execution eligibility policy and evaluator handler binding evaluator invocation all occur on this owned path.
        bound = root.prepare_choice_runtime(request=request)
        root._require_root()
        original_binding = _validated_binding_snapshot(
            bound, handoff=root, maximum=config.identifier_limit,
        )
        scope, selected, _, policy, _, _, _, approved, installed_runtime = original_binding
        original_handler = installed_runtime.handler
        if original_handler is not evaluate_single_select_choice:
            raise InvocationDenied('Invocation requires the installed frozen CHOICE handler.')
        admitted = bound.eligibility.admitted_choice
        try:
            raw = admitted.bound
            prepared = raw.prepared
            detached = config.choice_binder(
                prepared=prepared, choice_authority=raw.choice_authority,
                selection=raw.selection,
            )
        except (AttributeError, TypeError, ValueError, ChoiceInputBindingError):
            raise InvocationContractError('Invocation CHOICE input is malformed.') from None
        except Exception:
            raise InvocationUnavailable('Installed CHOICE input binder failed technically.') from None
        question = detached.prepared.question_authority
        paper = detached.prepared.paper_authority
        if (len(paper.expected_questions) != 1
                or paper.expected_questions[0].question_id != scope.question_id
                or question.question_id != scope.question_id):
            raise InvocationDenied('Single-question CHOICE execution requires one exact paper question.')
        if (selected.classification.answer_type != 'CHOICE'
                or selected.selected_capability_ref.evaluator_metadata.evaluator_id
                   != DETERMINISTIC_CHOICE_EVALUATOR_ID
                or selected.selected_capability_ref.evaluator_metadata.version
                   != DETERMINISTIC_CHOICE_EVALUATOR_VERSION):
            raise InvocationDenied('Invocation requires the frozen CHOICE evaluator identity.')
        expected = AttemptReservation(
            scope, '', '', 'CHOICE', approved.runtime_id, approved.runtime_version,
            approved.implementation_ref, policy.policy_id, policy.policy_version,
        )
        callback_scope = _scope(scope, config.identifier_limit)
        # For physical attempt claim: an installed callback can report a reservation but cannot
        # establish durable uniqueness without a real backend transaction.
        failure = None
        returned = None
        try:
            returned = config.allocator_operation(
                scope=callback_scope, family=expected.family, runtime_id=expected.runtime_id,
                runtime_version=expected.runtime_version,
                implementation_ref=expected.implementation_ref,
                eligibility_policy_id=expected.eligibility_policy_id,
                eligibility_policy_version=expected.eligibility_policy_version,
            )
        except AttemptReservationRejected:
            # Subclasses of explicit physical attempt claim refusal are still definitive denials.
            # Store a non-sensitive category, not the backend exception.
            failure = AttemptReservationRejected
        except Exception:
            # Unavailable, uncertain and unknown errors remain technical.
            failure = AttemptReservationUnavailable
        # Integrity takes precedence over returned approval, explicit denial,
        # technical exception, or unknown external reservation outcome.
        root._require_root()
        try:
            callback_valid = (
                _validated_binding_snapshot(bound, handoff=root, maximum=config.identifier_limit)
                == original_binding
                and _scope(callback_scope, config.identifier_limit) == scope
            )
        except (InvocationContractError, ExecutionEligibilityContractError,
                AttributeError, ValueError, TypeError):
            callback_valid = False
        if not callback_valid:
            raise InvocationDenied('Invocation source or reservation arguments changed.')
        if failure is not None:
            if failure is AttemptReservationRejected:
                raise InvocationDenied('grading attempt reservation was rejected.') from None
            raise InvocationUnavailable('grading attempt reservation is unavailable or uncertain.') from None
        reservation = _reservation_copy(returned, expected=expected, maximum=config.identifier_limit)
        root._require_root()
        if _validated_binding_snapshot(bound, handoff=root, maximum=config.identifier_limit) != original_binding:
            raise InvocationDenied('Invocation source changed before evaluator call.')
        # Only this original, installed handler is invoked. The result is never
        # accepted from the caller or an unrelated earlier invocation.
        try:
            emitted = original_handler(
                authority=detached.choice_authority, selection=detached.selection,
                scoring_authority=question.scoring_authority,
            )
        except ChoiceEvaluationError:
            raise InvocationContractError('Frozen CHOICE evaluator rejected admitted inputs.') from None
        except Exception:
            raise InvocationUnavailable('Frozen CHOICE evaluator failed; attempt outcome requires reconciliation.') from None
        root._require_root()
        if _validated_binding_snapshot(bound, handoff=root, maximum=config.identifier_limit) != original_binding:
            raise InvocationDenied('Invocation source changed during evaluator call.')
        if (type(emitted) is not tuple or not emitted
                or len(emitted) != len(question.scoring_authority.rubric.criteria)
                or any(type(item) is not EvaluatedCriterionJudgment for item in emitted)
                or tuple(j.criterion_id for j in emitted)
                   != tuple(c.criterion_id for c in question.scoring_authority.rubric.criteria)
                or any(j.evaluator_metadata.evaluator_id != DETERMINISTIC_CHOICE_EVALUATOR_ID
                       or j.evaluator_metadata.version != DETERMINISTIC_CHOICE_EVALUATOR_VERSION
                       for j in emitted)):
            raise InvocationContractError('Frozen CHOICE invocation emitted invalid judgments.')
        # The scoring consumer receives only the tuple emitted inside this method.
        # No external caller can insert another tuple between invocation and deterministic scoring.
        try:
            result = config.s2a_consumer(
                context=detached.prepared.context,
                evidence=detached.prepared.admitted_evidence.evidence,
                questions=(QuestionExecutionInput(scope.question_id, emitted, question.scoring_authority),),
                paper_authority=paper,
            )
        except (InvalidGradingExecutionError, EvidenceVerificationError,
                ScoringError, ValueError, TypeError):
            raise InvocationContractError('Owned CHOICE result could not be verified and scored.') from None
        except Exception:
            # physical attempt claim may have reserved already: do not imply rollback or retry safety.
            raise InvocationUnavailable('Owned scoring consumer failed; attempt requires reconciliation.') from None
        _owned_result_shape(
            result, context=detached.prepared.context, scope=scope,
            emitted=emitted, paper=paper, question=question,
        )
        root._require_root()
        if _validated_binding_snapshot(bound, handoff=root, maximum=config.identifier_limit) != original_binding:
            raise InvocationDenied('Invocation source changed during scoring consumption.')
        return OneQuestionExecutionCandidate(reservation, emitted, result)
