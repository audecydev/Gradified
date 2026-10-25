"""Deterministic outer-run binding for already-admitted single-select CHOICE data.

This is not source authentication, selection admission, evaluator eligibility,
student-evidence verification, or permission to invoke an evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from grading.contracts.choice import (
    CanonicalChoiceSelection,
    ChoiceCriterionProjection,
    ChoiceEvaluationAuthority,
    InvalidCanonicalChoiceSelectionError,
    InvalidChoiceEvaluationAuthorityError,
)
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import InvalidScoringAuthorityError, ScoringError
from grading.contracts.paper_aggregation import (
    GradingSpecRef, ResolvedPaperScoringAuthority,
    _validate_scoring_decimal_structure,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.execution import GradingExecutionContext
from grading.integration.evidence_ingress import AdmittedNormalizedEvidence
from grading.integration.evaluation_binding import (
    BoundQuestionEvaluationInputs,
    QuestionEvaluationBindingError,
    bind_question_evaluation_inputs,
)
from grading.rubric.fingerprint import compiled_authority_fingerprint
from grading.rubric.errors import InvalidRubricAuthoringInputError
from grading.contracts import evidence as evidence_contracts
from grading.contracts import policy as policy_contracts
from grading.contracts import result as result_contracts
from grading.contracts import rubric as rubric_contracts
from grading.rubric import models as rubric_models
from grading.integration.evidence_ingress import NormalizedEvidenceAdmissionPolicy
from grading.contracts.paper_aggregation import ExpectedQuestionResult


class ChoiceInputBindingError(ValueError):
    """Already-supplied CHOICE values do not bind to the prepared question."""


@dataclass(frozen=True, slots=True, repr=False, init=False)
class BoundChoiceEvaluationInputs:
    """Structurally bound data, NOT an authentication or execution token."""

    prepared: BoundQuestionEvaluationInputs
    choice_authority: ChoiceEvaluationAuthority
    selection: CanonicalChoiceSelection

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("Use bind_choice_evaluation_inputs() to create a bound result.")

    def __repr__(self) -> str:
        return "BoundChoiceEvaluationInputs(<bound>)"


def _snapshot_authority(value: ChoiceEvaluationAuthority) -> ChoiceEvaluationAuthority:
    """Reconstruct exact domain contracts, including their nested references."""
    try:
        spec = value.grading_spec_ref
        if type(spec) is not GradingSpecRef:
            raise ChoiceInputBindingError("CHOICE grading-spec reference is malformed.")
        match = value.match_projection
        mismatch = value.mismatch_projection
        if type(match) is not tuple or type(mismatch) is not tuple:
            raise ChoiceInputBindingError("CHOICE projections must be tuples.")
        if any(type(p) is not ChoiceCriterionProjection for p in match + mismatch):
            raise ChoiceInputBindingError("CHOICE projections contain invalid records.")
        return ChoiceEvaluationAuthority(
            schema_version=value.schema_version,
            grading_spec_ref=GradingSpecRef(id=spec.id, version=spec.version),
            question_id=value.question_id,
            compiled_authority_hash=value.compiled_authority_hash,
            option_ids=value.option_ids,
            official_option_id=value.official_option_id,
            match_projection=tuple(
                ChoiceCriterionProjection(p.criterion_id, p.selected_level) for p in match
            ),
            mismatch_projection=tuple(
                ChoiceCriterionProjection(p.criterion_id, p.selected_level) for p in mismatch
            ),
        )
    except ChoiceInputBindingError:
        raise
    except (AttributeError, InvalidChoiceEvaluationAuthorityError, TypeError, ValueError) as exc:
        raise ChoiceInputBindingError("CHOICE authority is malformed.") from exc


def _snapshot_selection(value: CanonicalChoiceSelection) -> CanonicalChoiceSelection:
    try:
        return CanonicalChoiceSelection(
            schema_version=value.schema_version,
            submission_ref=value.submission_ref,
            question_id=value.question_id,
            selected_option_id=value.selected_option_id,
            evidence_refs=value.evidence_refs,
        )
    except (AttributeError, InvalidCanonicalChoiceSelectionError) as exc:
        raise ChoiceInputBindingError("Canonical CHOICE selection is malformed.") from exc




# Only these frozen domain records may enter the detached prepared graph.
# Reconstructing each record through its own constructor rechecks nested shapes,
# including score-rule conditions and actual normalized OCR evidence admission evidence blocks. Unlike deepcopy,
# this never executes caller-supplied __deepcopy__ code.
_PREPARED_TYPES = (
    GradingExecutionContext, GradingSpecRef,
    NormalizedEvidenceAdmissionPolicy,
    evidence_contracts.AnswerEvidenceBundle,
    evidence_contracts.QuestionEvidence,
    evidence_contracts.EvidenceBlock,
    evidence_contracts.EvidenceLocation,
    ResolvedPaperScoringAuthority, ExpectedQuestionResult,
    result_contracts.RubricRef, result_contracts.ScoringPolicyRef,
    ResolvedQuestionAuthority, QuestionScoringAuthority,
    rubric_contracts.CompiledQuestionRubric,
    rubric_contracts.AtomicCriterion, rubric_contracts.PerformanceLevel,
    policy_contracts.QuestionScoringPolicy,
    policy_contracts.PositiveCreditDependencyRule,
    policy_contracts.CriterionCondition,
    policy_contracts.GateRule, policy_contracts.CapRule,
    policy_contracts.DeductionRule, policy_contracts.RoundingRule,
    rubric_models.QuestionRubricAuthoringContent,
    rubric_models.AuthoringCriterion,
    rubric_models.AuthoringPerformanceLevel,
    rubric_models.AuthoringCriterionCondition,
    rubric_models.AuthoringPositiveCreditDependencyRule,
    rubric_models.AuthoringGateRule,
    rubric_models.AuthoringCapRule,
    rubric_models.AuthoringDeductionRule,
    rubric_models.AuthoringRoundingRule,
)
_PREPARED_ENUMS = (
    ContextPolicy,
    evidence_contracts.EvidenceBlockType,
    evidence_contracts.EvidenceConfidenceStatus,
    evidence_contracts.EvidenceBlockState,
    evidence_contracts.EvidenceLocationStatus,
    policy_contracts.RoundingMode,
)


def _rebuild_prepared_value(value: object, depth: int = 0) -> object:
    """Copy only declared domain data, revalidating every nested constructor.

    Exactly typed leaves and class constructors are the executable boundary.
    Unsupported objects are rejected *before* their special methods can run.
    """
    if depth > 32:
        raise ChoiceInputBindingError("Prepared data exceeds its supported nesting depth.")
    kind = type(value)
    if value is None or kind in (str, int, float, bool):
        return value
    if kind is tuple:
        return tuple(_rebuild_prepared_value(item, depth + 1) for item in value)
    if kind is ScoringDecimal:
        _validate_scoring_decimal_structure(
            value, field_name="prepared.scoring_amount",
            error_type=InvalidScoringAuthorityError,
        )
        return ScoringDecimal(object.__getattribute__(value, "_value"))
    if kind in _PREPARED_ENUMS:
        if not any(value is member for member in kind):
            raise ChoiceInputBindingError("Prepared enum value is not canonical.")
        return value
    if kind is not AdmittedNormalizedEvidence and kind not in _PREPARED_TYPES:
        raise ChoiceInputBindingError("Prepared question has invalid or inconsistent nested data.")

    data = {
        field.name: _rebuild_prepared_value(
            object.__getattribute__(value, field.name), depth + 1,
        )
        for field in fields(kind)
    }
    if kind is AdmittedNormalizedEvidence:
        # The ingress contract intentionally has no public constructor. Rebuild
        # its validated fields without claiming to reauthenticate raw payload.
        result = object.__new__(AdmittedNormalizedEvidence)
        for name, field_value in data.items():
            object.__setattr__(result, name, field_value)
        result.__post_init__()
        return result
    return kind(**data)


def _validate_evidence_snapshot(admitted: AdmittedNormalizedEvidence) -> None:
    """Retain the normalized OCR evidence admission limits visible in an admitted, parsed evidence graph.

    Raw JSON lexical limits and source provenance cannot be reconstructed here;
    those remain evidence-ingress and trusted-source responsibilities.
    """
    evidence = admitted.evidence
    limits = admitted.effective_policy_snapshot

    def identifier(text: str) -> None:
        if not text or text.strip() != text or len(text) > limits.max_identifier_characters:
            raise ChoiceInputBindingError("Prepared evidence contains an invalid identifier.")

    def metadata(text: str | None) -> None:
        if text is not None and (
            not text or len(text) > limits.max_metadata_text_characters
        ):
            raise ChoiceInputBindingError("Prepared evidence metadata exceeds its admitted policy.")

    if evidence.schema_version != admitted.wire_schema_version:
        raise ChoiceInputBindingError("Prepared evidence schema does not match admission.")
    identifier(evidence.submission_ref)
    identifier(evidence.ocr_provenance)
    if admitted.source_artifact_ref is not None:
        identifier(admitted.source_artifact_ref)
    if len(evidence.questions) > limits.max_questions:
        raise ChoiceInputBindingError("Prepared evidence exceeds admitted question limit.")

    question_ids: set[str] = set()
    block_count = 0
    content_count = 0
    for question in evidence.questions:
        identifier(question.question_id)
        identifier(question.answer_scope_ref)
        if question.question_id in question_ids:
            raise ChoiceInputBindingError("Prepared evidence contains duplicate questions.")
        question_ids.add(question.question_id)
        if len(question.blocks) > limits.max_blocks_per_question:
            raise ChoiceInputBindingError("Prepared evidence exceeds per-question block limit.")
        block_count += len(question.blocks)
        if block_count > limits.max_total_blocks:
            raise ChoiceInputBindingError("Prepared evidence exceeds total block limit.")
        if len(question.warnings) > limits.max_warnings_per_question:
            raise ChoiceInputBindingError("Prepared evidence exceeds warning limit.")
        for warning in question.warnings:
            metadata(warning)
        for block in question.blocks:
            identifier(block.block_id)
            metadata(block.language)
            metadata(block.asset_ref)
            if len(block.content) > limits.max_block_content_characters:
                raise ChoiceInputBindingError("Prepared evidence block exceeds content limit.")
            content_count += len(block.content)
            if content_count > limits.max_total_content_characters:
                raise ChoiceInputBindingError("Prepared evidence exceeds aggregate content limit.")
            if (
                block.location.bbox is not None
                and len(block.location.bbox) > limits.max_location_coordinates
            ):
                raise ChoiceInputBindingError("Prepared evidence location exceeds coordinate limit.")



def _preflight_evidence_limits(admitted: AdmittedNormalizedEvidence) -> None:
    """Reject oversized admitted collections before rebuilding their children.

    This is a bounded check of already-parsed normalized OCR evidence admission values, not a substitute for
    ingress admission or the complete post-reconstruction validation below.
    Exact known domain types and tuple lengths avoid source-controlled methods.
    """
    if type(admitted) is not AdmittedNormalizedEvidence:
        raise ChoiceInputBindingError("Prepared evidence admission is malformed.")
    policy = _rebuild_prepared_value(
        object.__getattribute__(admitted, "effective_policy_snapshot")
    )
    if type(policy) is not NormalizedEvidenceAdmissionPolicy:
        raise ChoiceInputBindingError("Prepared evidence policy is malformed.")
    evidence = object.__getattribute__(admitted, "evidence")
    if type(evidence) is not evidence_contracts.AnswerEvidenceBundle:
        raise ChoiceInputBindingError("Prepared evidence bundle is malformed.")
    def check_text(value: object, *, metadata: bool = False, optional: bool = False) -> None:
        """Enforce already-admitted normalized OCR evidence admission text ceilings before domain reconstruction."""
        if optional and value is None:
            return
        limit = (
            policy.max_metadata_text_characters
            if metadata else policy.max_identifier_characters
        )
        if type(value) is not str or len(value) > limit:
            raise ChoiceInputBindingError("Prepared evidence exceeds admitted text limit or shape.")

    check_text(object.__getattribute__(evidence, "submission_ref"))
    check_text(object.__getattribute__(evidence, "ocr_provenance"))
    check_text(object.__getattribute__(admitted, "source_artifact_ref"), optional=True)

    questions = object.__getattribute__(evidence, "questions")
    if type(questions) is not tuple or len(questions) > policy.max_questions:
        raise ChoiceInputBindingError("Prepared evidence exceeds admitted question limit or shape.")

    block_count = 0
    total_content = 0
    for question in questions:
        if type(question) is not evidence_contracts.QuestionEvidence:
            raise ChoiceInputBindingError("Prepared evidence question is malformed.")
        check_text(object.__getattribute__(question, "question_id"))
        check_text(object.__getattribute__(question, "answer_scope_ref"))
        blocks = object.__getattribute__(question, "blocks")
        warnings = object.__getattribute__(question, "warnings")
        if type(blocks) is not tuple or len(blocks) > policy.max_blocks_per_question:
            raise ChoiceInputBindingError("Prepared evidence exceeds admitted per-question block limit or shape.")
        block_count += len(blocks)
        if block_count > policy.max_total_blocks:
            raise ChoiceInputBindingError("Prepared evidence exceeds admitted total block limit.")
        if type(warnings) is not tuple or len(warnings) > policy.max_warnings_per_question:
            raise ChoiceInputBindingError("Prepared evidence exceeds admitted warning limit or shape.")
        for warning in warnings:
            if type(warning) is not str or len(warning) > policy.max_metadata_text_characters:
                raise ChoiceInputBindingError("Prepared evidence exceeds admitted warning size or shape.")
        for block in blocks:
            if type(block) is not evidence_contracts.EvidenceBlock:
                raise ChoiceInputBindingError("Prepared evidence block is malformed.")
            check_text(object.__getattribute__(block, "block_id"))
            check_text(object.__getattribute__(block, "language"), metadata=True, optional=True)
            check_text(object.__getattribute__(block, "asset_ref"), metadata=True, optional=True)
            content = object.__getattribute__(block, "content")
            if type(content) is not str or len(content) > policy.max_block_content_characters:
                raise ChoiceInputBindingError("Prepared evidence exceeds admitted block content limit or shape.")
            total_content += len(content)
            if total_content > policy.max_total_content_characters:
                raise ChoiceInputBindingError("Prepared evidence exceeds admitted total content limit.")
            location = object.__getattribute__(block, "location")
            if type(location) is not evidence_contracts.EvidenceLocation:
                raise ChoiceInputBindingError("Prepared evidence location is malformed.")
            bbox = object.__getattribute__(location, "bbox")
            if bbox is not None and (
                type(bbox) is not tuple or len(bbox) > policy.max_location_coordinates
            ):
                raise ChoiceInputBindingError("Prepared evidence exceeds admitted coordinate limit or shape.")


def _snapshot_prepared(prepared: BoundQuestionEvaluationInputs) -> BoundQuestionEvaluationInputs:
    """Rebuild the four question evidence binding roots from verified domain values without aliases."""
    try:
        if (
            type(prepared.context) is not GradingExecutionContext
            or type(prepared.admitted_evidence) is not AdmittedNormalizedEvidence
            or type(prepared.paper_authority) is not ResolvedPaperScoringAuthority
            or type(prepared.question_authority) is not ResolvedQuestionAuthority
        ):
            raise ChoiceInputBindingError("Prepared question has invalid root types.")
        _preflight_evidence_limits(prepared.admitted_evidence)
        context = _rebuild_prepared_value(prepared.context)
        admitted = _rebuild_prepared_value(prepared.admitted_evidence)
        _validate_evidence_snapshot(admitted)
        paper = _rebuild_prepared_value(prepared.paper_authority)
        question = _rebuild_prepared_value(prepared.question_authority)
        return bind_question_evaluation_inputs(
            context=context,
            admitted_evidence=admitted,
            paper_authority=paper,
            question_authority=question,
        )
    except ChoiceInputBindingError:
        raise
    except (
        AttributeError, TypeError, ValueError, OverflowError, ScoringError,
        InvalidRubricAuthoringInputError, QuestionEvaluationBindingError,
    ) as exc:
        raise ChoiceInputBindingError(
            "Prepared question has invalid or inconsistent nested data."
        ) from exc


def _make_bound_result(
    *,
    prepared: BoundQuestionEvaluationInputs,
    authority: ChoiceEvaluationAuthority,
    selection: CanonicalChoiceSelection,
) -> BoundChoiceEvaluationInputs:
    result = object.__new__(BoundChoiceEvaluationInputs)
    object.__setattr__(result, "prepared", prepared)
    object.__setattr__(result, "choice_authority", authority)
    object.__setattr__(result, "selection", selection)
    return result


def _bind_choice_evaluation_inputs_impl(
    *,
    prepared: BoundQuestionEvaluationInputs,
    choice_authority: ChoiceEvaluationAuthority,
    selection: CanonicalChoiceSelection,
) -> BoundChoiceEvaluationInputs:
    """Bind one CHOICE question to its normalized OCR evidence admission/question evidence binding context and scoring identity.

    Input origin is trusted separately by the owning composition root. deterministic scoring owns
    evidence-ref verification; subsequent execution eligibility is independent.
    """
    if type(prepared) is not BoundQuestionEvaluationInputs:
        raise ChoiceInputBindingError("Expected an exact prepared question.")
    if type(choice_authority) is not ChoiceEvaluationAuthority:
        raise ChoiceInputBindingError("Expected an exact CHOICE authority.")
    if type(selection) is not CanonicalChoiceSelection:
        raise ChoiceInputBindingError("Expected an exact canonical CHOICE selection.")

    bound_prepared = _snapshot_prepared(prepared)
    authority = _snapshot_authority(choice_authority)
    canonical = _snapshot_selection(selection)
    context = bound_prepared.context
    evidence = bound_prepared.admitted_evidence.evidence
    question = bound_prepared.question_authority
    paper = bound_prepared.paper_authority
    question_id = question.question_id
    scoring = question.scoring_authority
    spec = context.grading_spec_ref

    if (
        context.submission_ref != evidence.submission_ref
        or canonical.submission_ref != context.submission_ref
    ):
        raise ChoiceInputBindingError("CHOICE submission does not match prepared evidence.")
    if canonical.question_id != question_id or authority.question_id != question_id:
        raise ChoiceInputBindingError("CHOICE question does not match the prepared question.")
    if (
        authority.grading_spec_ref != spec
        or question.grading_spec_ref != spec
        or paper.grading_spec_ref != spec
    ):
        raise ChoiceInputBindingError("CHOICE grading spec does not match prepared authority.")
    try:
        scoring_hash = compiled_authority_fingerprint(scoring)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ChoiceInputBindingError("Prepared scoring authority is malformed.") from exc
    if scoring_hash != authority.compiled_authority_hash:
        raise ChoiceInputBindingError("CHOICE authority does not match the bound scoring authority.")

    # All execution-facing identities are now rooted in detached, revalidated
    # values; callbacks on caller-owned inputs cannot rewrite this result.
    return _make_bound_result(prepared=bound_prepared, authority=authority, selection=canonical)


def bind_choice_evaluation_inputs(
    *,
    prepared: BoundQuestionEvaluationInputs,
    choice_authority: ChoiceEvaluationAuthority,
    selection: CanonicalChoiceSelection,
) -> BoundChoiceEvaluationInputs:
    """Return a detached CHOICE binding, keeping expected errors private.

    Match frozen question evidence binding's ambient-exception protection: clear exception chaining
    even when the caller invokes this binder inside an existing except block.
    Unexpected implementation failures are not translated.
    """
    try:
        return _bind_choice_evaluation_inputs_impl(
            prepared=prepared,
            choice_authority=choice_authority,
            selection=selection,
        )
    except ChoiceInputBindingError as caught:
        caught.__cause__ = None
        caught.__context__ = None
        caught.__suppress_context__ = True
        raise caught from None
