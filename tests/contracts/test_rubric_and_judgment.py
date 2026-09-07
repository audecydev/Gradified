from dataclasses import FrozenInstanceError

import pytest

from grading.contracts.errors import (
    InvalidCriterionJudgmentError,
    InvalidScoringAuthorityError,
)
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.rubric import (
    AtomicCriterion,
    CompiledQuestionRubric,
    PerformanceLevel,
)
from grading.contracts.scoring_decimal import ScoringDecimal


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def level(level_id: str, contribution: object) -> PerformanceLevel:
    return PerformanceLevel(level_id, sd(contribution))


def criterion(
    criterion_id: str = "C1",
    description: str = "Demonstrates the required step.",
) -> AtomicCriterion:
    return AtomicCriterion(
        criterion_id,
        description,
        (level("FULL", 2), level("PARTIAL", 1), level("NONE", 0)),
    )


def test_valid_atomic_criterion_preserves_operational_description() -> None:
    item = criterion(description="Uses the correct formula.")

    assert item.operational_description == "Uses the correct formula."


@pytest.mark.parametrize(
    "invalid_description",
    ["", "   ", 123, None],
)
def test_atomic_criterion_rejects_invalid_operational_description(
    invalid_description: object,
) -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        AtomicCriterion(
            "C1",
            invalid_description,  # type: ignore[arg-type]
            (level("FULL", 2),),
        )




def test_operational_description_preserves_human_prose_without_imposing_whitespace_policy() -> None:
    item = criterion(description="  Uses the correct formula.  ")

    assert item.operational_description == "  Uses the correct formula.  "


def test_performance_level_requires_scoring_decimal_contribution() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        PerformanceLevel("FULL", "2")  # type: ignore[arg-type]


def test_atomic_criterion_rejects_no_levels() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        AtomicCriterion("C1", "Required step.", ())


def test_atomic_criterion_rejects_duplicate_level_ids() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        AtomicCriterion(
            "C1",
            "Required step.",
            (level("FULL", 2), level("FULL", 1)),
        )


def test_atomic_criterion_requires_immutable_tuple_levels() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        AtomicCriterion(
            "C1",
            "Required step.",
            [level("FULL", 2)],  # type: ignore[arg-type]
        )


def test_compiled_rubric_rejects_duplicate_criterion_ids() -> None:
    item = criterion()
    with pytest.raises(InvalidScoringAuthorityError):
        CompiledQuestionRubric("R1", 1, "Q1", sd(4), (item, item))


def test_compiled_rubric_requires_positive_integer_version() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        CompiledQuestionRubric("R1", 0, "Q1", sd(2), (criterion(),))


@pytest.mark.parametrize("invalid_version", [True, 0, -1, 1.5, "1"])
def test_compiled_rubric_rejects_invalid_version(invalid_version: object) -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        CompiledQuestionRubric(
            "R1",
            invalid_version,  # type: ignore[arg-type]
            "Q1",
            sd(2),
            (criterion(),),
        )


@pytest.mark.parametrize("field_value", ["", " Q1", "Q1 ", 1, None])
def test_rubric_question_id_must_be_strict_identifier(field_value: object) -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        CompiledQuestionRubric(
            "R1",
            1,
            field_value,  # type: ignore[arg-type]
            sd(2),
            (criterion(),),
        )


def test_identifiers_reject_surrounding_whitespace() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        PerformanceLevel(" FULL", sd(1))
    with pytest.raises(InvalidCriterionJudgmentError):
        CriterionJudgment("C1 ", "FULL")


def test_contract_objects_are_immutable() -> None:
    judgment = CriterionJudgment("C1", "FULL")
    with pytest.raises(FrozenInstanceError):
        judgment.selected_level = "NONE"  # type: ignore[misc]


def test_criterion_judgment_has_no_numeric_scoring_field() -> None:
    judgment = CriterionJudgment("C1", "FULL")
    assert not hasattr(judgment, "score")
    assert not hasattr(judgment, "marks")
    assert not hasattr(judgment, "awarded_marks")
    assert not hasattr(judgment, "contribution")
    assert not hasattr(judgment, "deduction")
    assert not hasattr(judgment, "suggested_total")


@pytest.mark.parametrize(
    "field_name",
    ["score", "marks", "awarded_marks", "contribution", "deduction", "suggested_total"],
)
def test_criterion_judgment_rejects_unexpected_score_like_field(
    field_name: str,
) -> None:
    kwargs = {field_name: 1}
    with pytest.raises(TypeError):
        CriterionJudgment("C1", "FULL", **kwargs)  # type: ignore[call-arg]
