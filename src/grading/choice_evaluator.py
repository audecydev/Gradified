from __future__ import annotations

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.choice import (
    CHOICE_MATCH_RATIONALE,
    CHOICE_MATCH_REASON_CODE,
    CHOICE_MISMATCH_RATIONALE,
    CHOICE_MISMATCH_REASON_CODE,
    DETERMINISTIC_CHOICE_EVALUATOR_ID,
    DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    CanonicalChoiceSelection,
    ChoiceEvaluationAuthority,
    InvalidCanonicalChoiceSelectionError,
    InvalidChoiceEvaluationAuthorityError,
    ChoiceProjectionScoringMismatchError,
    ChoiceScoringAuthorityBindingError,
    ChoiceSelectionBindingError,
    UnsupportedChoiceInputError,
)
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
from grading.rubric.fingerprint import compiled_authority_fingerprint


def _validate_scoring_binding(
    *,
    authority: ChoiceEvaluationAuthority,
    scoring_authority: QuestionScoringAuthority,
) -> None:
    question_id = authority.question_id
    if (
        scoring_authority.rubric.question_id != question_id
        or scoring_authority.policy.question_id != question_id
    ):
        raise ChoiceScoringAuthorityBindingError(
            "CHOICE authority question_id must match scoring rubric and policy question_id."
        )

    if compiled_authority_fingerprint(scoring_authority) != authority.compiled_authority_hash:
        raise ChoiceScoringAuthorityBindingError(
            "CHOICE compiled_authority_hash must match the supplied scoring authority."
        )


def _validate_projection_compatibility(
    *,
    authority: ChoiceEvaluationAuthority,
    scoring_authority: QuestionScoringAuthority,
) -> None:
    criteria = scoring_authority.rubric.criteria
    expected_criterion_ids = tuple(criterion.criterion_id for criterion in criteria)
    match_ids = tuple(item.criterion_id for item in authority.match_projection)
    mismatch_ids = tuple(item.criterion_id for item in authority.mismatch_projection)

    if match_ids != expected_criterion_ids or mismatch_ids != expected_criterion_ids:
        raise ChoiceProjectionScoringMismatchError(
            "CHOICE projections must match the complete scoring-rubric criterion order."
        )

    for criterion, match_item, mismatch_item in zip(
        criteria,
        authority.match_projection,
        authority.mismatch_projection,
        strict=True,
    ):
        admitted_levels = criterion.level_ids()
        if (
            match_item.selected_level not in admitted_levels
            or mismatch_item.selected_level not in admitted_levels
        ):
            raise ChoiceProjectionScoringMismatchError(
                "CHOICE projected selected_level must be admitted by its scoring criterion."
            )


def evaluate_single_select_choice(
    *,
    authority: ChoiceEvaluationAuthority,
    selection: CanonicalChoiceSelection,
    scoring_authority: QuestionScoringAuthority,
) -> tuple[EvaluatedCriterionJudgment, ...]:
    """Evaluate one admitted canonical single-select CHOICE response."""

    if type(authority) is not ChoiceEvaluationAuthority:
        raise InvalidChoiceEvaluationAuthorityError(
            "authority must be an exact ChoiceEvaluationAuthority."
        )
    if type(selection) is not CanonicalChoiceSelection:
        raise InvalidCanonicalChoiceSelectionError(
            "selection must be an exact CanonicalChoiceSelection."
        )
    if type(scoring_authority) is not QuestionScoringAuthority:
        raise ChoiceScoringAuthorityBindingError(
            "scoring_authority must be an exact QuestionScoringAuthority."
        )

    if selection.question_id != authority.question_id:
        raise ChoiceSelectionBindingError(
            "Canonical selection question_id must match CHOICE authority question_id."
        )

    _validate_scoring_binding(
        authority=authority,
        scoring_authority=scoring_authority,
    )
    _validate_projection_compatibility(
        authority=authority,
        scoring_authority=scoring_authority,
    )

    if selection.selected_option_id not in authority.option_ids:
        raise UnsupportedChoiceInputError(
            "Canonical selected_option_id is not admitted by the CHOICE option universe."
        )

    matched = selection.selected_option_id == authority.official_option_id
    projection = authority.match_projection if matched else authority.mismatch_projection
    reason_code = CHOICE_MATCH_REASON_CODE if matched else CHOICE_MISMATCH_REASON_CODE
    rationale = CHOICE_MATCH_RATIONALE if matched else CHOICE_MISMATCH_RATIONALE
    metadata = EvaluatorMetadata(
        evaluator_id=DETERMINISTIC_CHOICE_EVALUATOR_ID,
        version=DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    )

    return tuple(
        EvaluatedCriterionJudgment(
            criterion_id=item.criterion_id,
            selected_level=item.selected_level,
            evidence_refs=selection.evidence_refs,
            reason_codes=(reason_code,),
            concise_rationale=rationale,
            uncertainties=(),
            evaluator_metadata=metadata,
        )
        for item in projection
    )
