import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import (
    DuplicateJudgmentError,
    InvalidCriterionJudgmentError,
    MissingJudgmentError,
    UnknownCriterionError,
    UnknownJudgmentCriterionError,
    UnknownJudgmentPerformanceLevelError,
    UnknownPerformanceLevelError,
)
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.policy import SCORING_SEMANTICS_V1, QuestionScoringPolicy
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.contracts.validation import validate_criterion_judgments


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def atomic(
    criterion_id: str,
    description: str,
    full_marks: object,
) -> AtomicCriterion:
    return AtomicCriterion(
        criterion_id,
        description,
        (
            PerformanceLevel("FULL", sd(full_marks)),
            PerformanceLevel("NONE", sd(0)),
        ),
    )


def authority() -> QuestionScoringAuthority:
    rubric = CompiledQuestionRubric(
        "R1",
        1,
        "Q1",
        sd(3),
        (
            atomic("C1", "Uses the required formula.", 1),
            atomic("C2", "Completes the required calculation.", 2),
        ),
    )
    policy = QuestionScoringPolicy(
        "P1",
        1,
        "Q1",
        SCORING_SEMANTICS_V1,
        sd(0),
        sd(3),
    )
    return QuestionScoringAuthority(rubric, policy)


def test_valid_judgments_are_returned_in_rubric_order() -> None:
    validated = validate_criterion_judgments(
        authority(),
        (CriterionJudgment("C2", "NONE"), CriterionJudgment("C1", "FULL")),
    )
    assert tuple(j.criterion_id for j in validated) == ("C1", "C2")


def test_unknown_criterion_is_rejected() -> None:
    with pytest.raises(UnknownJudgmentCriterionError):
        validate_criterion_judgments(
            authority(),
            (
                CriterionJudgment("C1", "FULL"),
                CriterionJudgment("MISSING", "FULL"),
            ),
        )


def test_unknown_performance_level_is_rejected() -> None:
    with pytest.raises(UnknownJudgmentPerformanceLevelError):
        validate_criterion_judgments(
            authority(),
            (
                CriterionJudgment("C1", "UNKNOWN"),
                CriterionJudgment("C2", "FULL"),
            ),
        )


def test_duplicate_judgment_is_rejected() -> None:
    with pytest.raises(DuplicateJudgmentError):
        validate_criterion_judgments(
            authority(),
            (
                CriterionJudgment("C1", "FULL"),
                CriterionJudgment("C1", "NONE"),
                CriterionJudgment("C2", "FULL"),
            ),
        )


def test_missing_judgment_is_rejected_instead_of_becoming_zero() -> None:
    with pytest.raises(MissingJudgmentError):
        validate_criterion_judgments(
            authority(),
            (CriterionJudgment("C1", "FULL"),),
        )


def test_judgment_collection_must_be_immutable_tuple() -> None:
    with pytest.raises(InvalidCriterionJudgmentError):
        validate_criterion_judgments(
            authority(),
            [
                CriterionJudgment("C1", "FULL"),
                CriterionJudgment("C2", "FULL"),
            ],  # type: ignore[arg-type]
        )


def test_judgment_reference_failures_preserve_judgment_origin_and_reference_kind() -> None:
    with pytest.raises(UnknownJudgmentCriterionError) as criterion_exc:
        validate_criterion_judgments(
            authority(),
            (
                CriterionJudgment("C1", "FULL"),
                CriterionJudgment("MISSING", "FULL"),
            ),
        )

    assert isinstance(criterion_exc.value, InvalidCriterionJudgmentError)
    assert isinstance(criterion_exc.value, UnknownCriterionError)

    with pytest.raises(UnknownJudgmentPerformanceLevelError) as level_exc:
        validate_criterion_judgments(
            authority(),
            (
                CriterionJudgment("C1", "UNKNOWN"),
                CriterionJudgment("C2", "FULL"),
            ),
        )

    assert isinstance(level_exc.value, InvalidCriterionJudgmentError)
    assert isinstance(level_exc.value, UnknownPerformanceLevelError)


def test_missing_and_duplicate_judgments_are_judgment_input_failures() -> None:
    assert issubclass(DuplicateJudgmentError, InvalidCriterionJudgmentError)
    assert issubclass(MissingJudgmentError, InvalidCriterionJudgmentError)
