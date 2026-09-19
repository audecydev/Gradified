from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from grading.rubric.errors import InvalidRubricAuthoringInputError
from grading.rubric.models import (
    AuthoringCriterion,
    AuthoringCriterionCondition,
    AuthoringPerformanceLevel,
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
    RubricCompilationLimits,
)
from tests._rubric_authoring_support import sd, simple_content


def test_authoring_contracts_are_deeply_immutable() -> None:
    content = simple_content()

    with pytest.raises(FrozenInstanceError):
        content.rubric_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.criteria[0].operational_description = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.criteria[0].performance_levels[0].contribution = sd(99)  # type: ignore[misc]


def test_authoring_contracts_reject_mutable_or_wrong_runtime_shapes() -> None:
    with pytest.raises(InvalidRubricAuthoringInputError):
        AuthoringCriterionCondition("C1", ["FULL"])  # type: ignore[arg-type]

    with pytest.raises(InvalidRubricAuthoringInputError):
        AuthoringPerformanceLevel("FULL", "met", "2")  # type: ignore[arg-type]

    valid_criterion = AuthoringCriterion(
        "C1",
        "criterion",
        "evidence",
        (AuthoringPerformanceLevel("FULL", "met", sd(2)),),
    )
    with pytest.raises(InvalidRubricAuthoringInputError):
        QuestionRubricAuthoringContent(
            "R1",
            "P1",
            sd(0),
            [valid_criterion],  # type: ignore[arg-type]
        )

    with pytest.raises(InvalidRubricAuthoringInputError):
        FinalizedQuestionScoringBasis("Q1", "2")  # type: ignore[arg-type]

    with pytest.raises(InvalidRubricAuthoringInputError):
        RubricCompilationLimits(
            max_criteria=True,  # type: ignore[arg-type]
            max_levels_per_criterion=1,
            max_accepted_equivalents_per_criterion=1,
            max_rules=1,
            max_conditions_per_rule=1,
            max_allowed_level_ids_per_condition=1,
            max_text_characters_per_field=1,
            max_serialized_authority_bytes=1,
            max_reconciliation_states=1,
        )


def test_semantically_invalid_strings_can_exist_as_draft_and_are_left_for_linter() -> None:
    content = QuestionRubricAuthoringContent(
        rubric_id=" ",
        policy_id="P1",
        minimum_score=sd(0),
        criteria=(
            AuthoringCriterion(
                criterion_id="C1",
                operational_description=" ",
                evidence_requirement=" ",
                performance_levels=(
                    AuthoringPerformanceLevel("FULL", " ", sd(1)),
                ),
            ),
        ),
    )

    assert content.rubric_id == " "


def test_candidate_content_does_not_own_finalized_question_or_scoring_semantics() -> None:
    names = {field.name for field in fields(QuestionRubricAuthoringContent)}
    assert "question_id" not in names
    assert "max_marks" not in names
    assert "scoring_semantics_version" not in names
