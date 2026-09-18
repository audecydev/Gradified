from __future__ import annotations

from grading.contracts.errors import (
    InvalidPaperAggregationInputError,
    ScoreOutOfRangeError,
)
from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult,
    ResolvedPaperScoringAuthority,
    _required_field,
    _validate_identifier,
    _validate_resolved_paper_scoring_authority,
    _validate_rubric_ref,
    _validate_scoring_decimal_structure,
    _validate_scoring_policy_ref,
)
from grading.contracts.result import PaperScoreResult, QuestionScoreResult
from grading.scoring.arithmetic import exact_compare, exact_sum


def _input_field(value: object, field_name: str, owner_name: str) -> object:
    return _required_field(
        value,
        field_name,
        error_type=InvalidPaperAggregationInputError,
        owner_name=owner_name,
    )


def _validate_submitted_collection(
    question_results: object,
) -> tuple[QuestionScoreResult, ...]:
    if type(question_results) is not tuple:
        raise InvalidPaperAggregationInputError(
            "question_results must be an exact tuple."
        )

    for result in question_results:
        if type(result) is not QuestionScoreResult:
            raise InvalidPaperAggregationInputError(
                "question_results contains an invalid item."
            )
    return question_results


def _validated_submitted_ids(
    question_results: tuple[QuestionScoreResult, ...],
) -> tuple[str, ...]:
    ids: list[str] = []
    for index, result in enumerate(question_results):
        question_id = _input_field(
            result,
            "question_id",
            f"question_results[{index}]",
        )
        validated = _validate_identifier(
            question_id,
            field_name=f"question_results[{index}].question_id",
            error_type=InvalidPaperAggregationInputError,
        )
        ids.append(validated)
    return tuple(ids)


def _reject_duplicate_ids(question_ids: tuple[str, ...]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for question_id in question_ids:
        if question_id in seen:
            duplicates.add(question_id)
        else:
            seen.add(question_id)

    if duplicates:
        rendered = ", ".join(sorted(duplicates))
        raise InvalidPaperAggregationInputError(
            f"question_results contains duplicate question IDs: {rendered}."
        )


def _expected_ids(
    authority: ResolvedPaperScoringAuthority,
) -> tuple[str, ...]:
    # Authority has already been completely re-admitted.
    return tuple(expected.question_id for expected in authority.expected_questions)


def _require_exact_question_set(
    expected_ids: tuple[str, ...],
    supplied_ids: tuple[str, ...],
) -> None:
    expected_set = set(expected_ids)
    supplied_set = set(supplied_ids)
    if expected_set == supplied_set:
        return

    missing = tuple(sorted(expected_set - supplied_set))
    unexpected = tuple(sorted(supplied_set - expected_set))
    raise InvalidPaperAggregationInputError(
        f"question result set mismatch; missing={missing!r}; unexpected={unexpected!r}."
    )


def _validate_result_identity(
    expected: ExpectedQuestionResult,
    result: QuestionScoreResult,
    *,
    result_index: int,
) -> None:
    owner = f"question_results[{result_index}]"
    rubric_ref = _input_field(result, "rubric_ref", owner)
    policy_ref = _input_field(result, "scoring_policy_ref", owner)

    _validate_rubric_ref(
        rubric_ref,
        field_name=f"{owner}.rubric_ref",
        error_type=InvalidPaperAggregationInputError,
    )
    _validate_scoring_policy_ref(
        policy_ref,
        field_name=f"{owner}.scoring_policy_ref",
        error_type=InvalidPaperAggregationInputError,
        require_supported_semantics=True,
    )

    if rubric_ref != expected.rubric_ref:
        raise InvalidPaperAggregationInputError(
            f"question result {expected.question_id!r} has the wrong rubric identity."
        )
    if policy_ref != expected.scoring_policy_ref:
        raise InvalidPaperAggregationInputError(
            f"question result {expected.question_id!r} has the wrong policy identity."
        )


def _validate_result_profile(
    result: QuestionScoreResult,
    *,
    result_index: int,
) -> None:
    owner = f"question_results[{result_index}]"
    profile = _input_field(result, "numeric_profile_version", owner)
    if type(profile) is not str or profile != NUMERIC_PROFILE_VERSION:
        raise InvalidPaperAggregationInputError(
            f"{owner}.numeric_profile_version is unsupported."
        )


def _validate_consumed_score_fields(
    result: QuestionScoreResult,
    *,
    result_index: int,
) -> None:
    owner = f"question_results[{result_index}]"
    minimum = _validate_scoring_decimal_structure(
        _input_field(result, "minimum_score", owner),
        field_name=f"{owner}.minimum_score",
        error_type=InvalidPaperAggregationInputError,
    )
    final = _validate_scoring_decimal_structure(
        _input_field(result, "final_score", owner),
        field_name=f"{owner}.final_score",
        error_type=InvalidPaperAggregationInputError,
    )
    maximum = _validate_scoring_decimal_structure(
        _input_field(result, "maximum_score", owner),
        field_name=f"{owner}.maximum_score",
        error_type=InvalidPaperAggregationInputError,
    )

    if exact_compare(minimum, maximum) > 0:
        raise InvalidPaperAggregationInputError(
            f"{owner} has minimum_score greater than maximum_score."
        )
    if exact_compare(final, minimum) < 0:
        raise InvalidPaperAggregationInputError(
            f"{owner}.final_score is below its minimum_score."
        )
    if exact_compare(final, maximum) > 0:
        raise InvalidPaperAggregationInputError(
            f"{owner}.final_score is above its maximum_score."
        )


def aggregate_paper(
    authority: ResolvedPaperScoringAuthority,
    question_results: tuple[QuestionScoreResult, ...],
) -> PaperScoreResult:
    """Aggregate one already-resolved paper composition deterministically."""

    validated_authority = _validate_resolved_paper_scoring_authority(authority)
    submitted = _validate_submitted_collection(question_results)

    supplied_ids = _validated_submitted_ids(submitted)
    _reject_duplicate_ids(supplied_ids)

    expected_ids = _expected_ids(validated_authority)
    _require_exact_question_set(expected_ids, supplied_ids)

    lookup = {question_id: result for question_id, result in zip(supplied_ids, submitted)}
    supplied_index_by_id = {
        question_id: index
        for index, question_id in enumerate(supplied_ids)
    }

    for expected in validated_authority.expected_questions:
        result = lookup[expected.question_id]
        supplied_index = supplied_index_by_id[expected.question_id]
        _validate_result_identity(
            expected,
            result,
            result_index=supplied_index,
        )

    for expected in validated_authority.expected_questions:
        supplied_index = supplied_index_by_id[expected.question_id]
        _validate_result_profile(
            lookup[expected.question_id],
            result_index=supplied_index,
        )

    for expected in validated_authority.expected_questions:
        supplied_index = supplied_index_by_id[expected.question_id]
        _validate_consumed_score_fields(
            lookup[expected.question_id],
            result_index=supplied_index,
        )

    canonical_results = tuple(
        lookup[expected.question_id]
        for expected in validated_authority.expected_questions
    )

    final_score = exact_sum(tuple(result.final_score for result in canonical_results))

    if exact_compare(final_score, validated_authority.minimum_score) < 0:
        raise ScoreOutOfRangeError(
            "Paper aggregate is below the authoritative minimum score."
        )
    if exact_compare(final_score, validated_authority.maximum_score) > 0:
        raise ScoreOutOfRangeError(
            "Paper aggregate is above the authoritative maximum score."
        )

    return PaperScoreResult(
        grading_spec_ref=validated_authority.grading_spec_ref,
        numeric_profile_version=NUMERIC_PROFILE_VERSION,
        question_results=canonical_results,
        final_score=final_score,
        minimum_score=validated_authority.minimum_score,
        maximum_score=validated_authority.maximum_score,
    )
