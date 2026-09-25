from __future__ import annotations

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.models import (
    AuthoringCriterion,
    AuthoringPerformanceLevel,
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
    RubricCompilationLimits,
)


def sd(value: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def level(
    level_id: str,
    contribution: object,
    *,
    description: str | None = None,
) -> AuthoringPerformanceLevel:
    return AuthoringPerformanceLevel(
        level_id=level_id,
        operational_description=description or f"{level_id} level",
        contribution=sd(contribution),
    )


def criterion(
    criterion_id: str,
    full_contribution: object,
    *,
    none_contribution: object = 0,
    accepted_equivalents: tuple[str, ...] = (),
) -> AuthoringCriterion:
    return AuthoringCriterion(
        criterion_id=criterion_id,
        operational_description=f"Operational description for {criterion_id}",
        evidence_requirement=f"Evidence sufficient to judge {criterion_id}",
        performance_levels=(
            level("FULL", full_contribution, description="Criterion fully met"),
            level("NOT_MET", none_contribution, description="Criterion not met"),
        ),
        accepted_equivalents=accepted_equivalents,
    )


def simple_basis(*, question_id: str = "Q1", max_marks: object = 5) -> FinalizedQuestionScoringBasis:
    return FinalizedQuestionScoringBasis(question_id, sd(max_marks))


def authoring_test_limits(
    *,
    max_reconciliation_states: int = 1_000_000,
    max_serialized_authority_bytes: int = 100_000,
) -> RubricCompilationLimits:
    """Explicit test-only limits; these are not production policy defaults."""

    return RubricCompilationLimits(
        max_criteria=20,
        max_levels_per_criterion=10,
        max_accepted_equivalents_per_criterion=20,
        max_rules=50,
        max_conditions_per_rule=20,
        max_allowed_level_ids_per_condition=10,
        max_text_characters_per_field=1000,
        max_serialized_authority_bytes=max_serialized_authority_bytes,
        max_reconciliation_states=max_reconciliation_states,
    )


def simple_content() -> QuestionRubricAuthoringContent:
    return QuestionRubricAuthoringContent(
        rubric_id="R-Q1",
        policy_id="P-Q1",
        minimum_score=sd(0),
        criteria=(criterion("C1", 2), criterion("C2", 3)),
    )
