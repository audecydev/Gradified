from dataclasses import fields, is_dataclass
from enum import Enum
from importlib import import_module
from typing import get_type_hints

import pytest

from grading.contracts.errors import ScoringError
from grading.contracts.scoring_decimal import ScoringDecimal


EXPECTED_FIELDS = {
    "RubricRef": (
        "id",
        "version",
    ),
    "ScoringPolicyRef": (
        "id",
        "version",
        "scoring_semantics_version",
    ),
    "CriterionEffect": (
        "criterion_id",
        "selected_level",
        "base_contribution",
        "effective_contribution",
        "blocking_dependency_rule_ids",
    ),
    "RuleDecision": (
        "rule_id",
        "rule_type",
        "triggered",
        "configured_effect",
    ),
    "ScoreStageEffect": (
        "stage",
        "before",
        "after",
        "source_rule_ids",
    ),
    "QuestionScoreResult": (
        "question_id",
        "rubric_ref",
        "scoring_policy_ref",
        "numeric_profile_version",
        "criterion_effects",
        "rule_decisions",
        "stage_effects",
        "base_subtotal",
        "score_before_rounding",
        "final_score",
        "minimum_score",
        "maximum_score",
    ),
}


def _import_result_module():
    try:
        return import_module("grading.contracts.result")
    except ModuleNotFoundError as exc:
        if exc.name == "grading.contracts.result":
            pytest.fail(
                "B2 RED-2A: grading.contracts.result does not exist yet.",
                pytrace=False,
            )
        raise


def test_b2_result_and_provenance_contract_surface_exists() -> None:
    """B2 exposes the frozen immutable result/provenance surface."""

    result_module = _import_result_module()

    for class_name, expected_fields in EXPECTED_FIELDS.items():
        contract_type = getattr(result_module, class_name, None)

        assert contract_type is not None, (
            f"B2 RED-2A: grading.contracts.result.{class_name} is missing."
        )
        assert is_dataclass(contract_type), f"{class_name} must be a dataclass."
        assert contract_type.__dataclass_params__.frozen is True, (
            f"{class_name} must be immutable."
        )
        assert tuple(field.name for field in fields(contract_type)) == expected_fields


def test_b2_result_contract_uses_closed_rule_and_stage_enums() -> None:
    result_module = _import_result_module()

    rule_type = getattr(result_module, "RuleType", None)
    score_stage = getattr(result_module, "ScoreStage", None)

    assert rule_type is not None
    assert score_stage is not None
    assert issubclass(rule_type, Enum)
    assert issubclass(score_stage, Enum)

    assert tuple(member.name for member in rule_type) == (
        "DEPENDENCY",
        "GATE",
        "CAP",
        "DEDUCTION",
    )
    assert tuple(member.name for member in score_stage) == (
        "GATES",
        "CAPS",
        "DEDUCTIONS",
        "ROUNDING",
    )


def test_b2_result_contract_declares_exact_field_types() -> None:
    result_module = _import_result_module()

    rubric_ref_hints = get_type_hints(result_module.RubricRef)
    assert rubric_ref_hints == {
        "id": str,
        "version": int,
    }

    scoring_policy_ref_hints = get_type_hints(result_module.ScoringPolicyRef)
    assert scoring_policy_ref_hints == {
        "id": str,
        "version": int,
        "scoring_semantics_version": str,
    }

    criterion_effect_hints = get_type_hints(result_module.CriterionEffect)
    assert criterion_effect_hints == {
        "criterion_id": str,
        "selected_level": str,
        "base_contribution": ScoringDecimal,
        "effective_contribution": ScoringDecimal,
        "blocking_dependency_rule_ids": tuple[str, ...],
    }

    rule_decision_hints = get_type_hints(result_module.RuleDecision)
    assert rule_decision_hints == {
        "rule_id": str,
        "rule_type": result_module.RuleType,
        "triggered": bool,
        "configured_effect": ScoringDecimal | None,
    }

    stage_effect_hints = get_type_hints(result_module.ScoreStageEffect)
    assert stage_effect_hints == {
        "stage": result_module.ScoreStage,
        "before": ScoringDecimal,
        "after": ScoringDecimal,
        "source_rule_ids": tuple[str, ...],
    }

    result_hints = get_type_hints(result_module.QuestionScoreResult)
    assert result_hints == {
        "question_id": str,
        "rubric_ref": result_module.RubricRef,
        "scoring_policy_ref": result_module.ScoringPolicyRef,
        "numeric_profile_version": str,
        "criterion_effects": tuple[result_module.CriterionEffect, ...],
        "rule_decisions": tuple[result_module.RuleDecision, ...],
        "stage_effects": tuple[result_module.ScoreStageEffect, ...],
        "base_subtotal": ScoringDecimal,
        "score_before_rounding": ScoringDecimal,
        "final_score": ScoringDecimal,
        "minimum_score": ScoringDecimal,
        "maximum_score": ScoringDecimal,
    }


def test_score_out_of_range_error_is_a_scoring_domain_failure() -> None:
    errors_module = import_module("grading.contracts.errors")
    error_type = getattr(errors_module, "ScoreOutOfRangeError", None)

    assert error_type is not None, (
        "B2 RED-2A: ScoreOutOfRangeError does not exist yet."
    )
    assert issubclass(error_type, ScoringError)


@pytest.mark.parametrize(
    "factory",
    (
        lambda result_module: result_module.CriterionEffect(
            criterion_id="C1",
            selected_level="FULL",
            base_contribution=ScoringDecimal.from_raw("1"),
            effective_contribution=ScoringDecimal.from_raw("1"),
            blocking_dependency_rule_ids=["DEP-1"],
        ),
        lambda result_module: result_module.ScoreStageEffect(
            stage=result_module.ScoreStage.GATES,
            before=ScoringDecimal.from_raw("1"),
            after=ScoringDecimal.from_raw("1"),
            source_rule_ids=["G-1"],
        ),
        lambda result_module: result_module.QuestionScoreResult(
            question_id="Q1",
            rubric_ref=result_module.RubricRef("R1", 1),
            scoring_policy_ref=result_module.ScoringPolicyRef("P1", 1, "1"),
            numeric_profile_version="1",
            criterion_effects=[],
            rule_decisions=(),
            stage_effects=(),
            base_subtotal=ScoringDecimal.from_raw("0"),
            score_before_rounding=ScoringDecimal.from_raw("0"),
            final_score=ScoringDecimal.from_raw("0"),
            minimum_score=ScoringDecimal.from_raw("0"),
            maximum_score=ScoringDecimal.from_raw("1"),
        ),
        lambda result_module: result_module.QuestionScoreResult(
            question_id="Q1",
            rubric_ref=result_module.RubricRef("R1", 1),
            scoring_policy_ref=result_module.ScoringPolicyRef("P1", 1, "1"),
            numeric_profile_version="1",
            criterion_effects=(),
            rule_decisions=[],
            stage_effects=(),
            base_subtotal=ScoringDecimal.from_raw("0"),
            score_before_rounding=ScoringDecimal.from_raw("0"),
            final_score=ScoringDecimal.from_raw("0"),
            minimum_score=ScoringDecimal.from_raw("0"),
            maximum_score=ScoringDecimal.from_raw("1"),
        ),
        lambda result_module: result_module.QuestionScoreResult(
            question_id="Q1",
            rubric_ref=result_module.RubricRef("R1", 1),
            scoring_policy_ref=result_module.ScoringPolicyRef("P1", 1, "1"),
            numeric_profile_version="1",
            criterion_effects=(),
            rule_decisions=(),
            stage_effects=[],
            base_subtotal=ScoringDecimal.from_raw("0"),
            score_before_rounding=ScoringDecimal.from_raw("0"),
            final_score=ScoringDecimal.from_raw("0"),
            minimum_score=ScoringDecimal.from_raw("0"),
            maximum_score=ScoringDecimal.from_raw("1"),
        ),
        lambda result_module: result_module.CriterionEffect(
            criterion_id="C1",
            selected_level="FULL",
            base_contribution=ScoringDecimal.from_raw("1"),
            effective_contribution=ScoringDecimal.from_raw("1"),
            blocking_dependency_rule_ids=(object(),),
        ),
        lambda result_module: result_module.ScoreStageEffect(
            stage=result_module.ScoreStage.GATES,
            before=ScoringDecimal.from_raw("1"),
            after=ScoringDecimal.from_raw("1"),
            source_rule_ids=(object(),),
        ),
        lambda result_module: result_module.QuestionScoreResult(
            question_id="Q1",
            rubric_ref=result_module.RubricRef("R1", 1),
            scoring_policy_ref=result_module.ScoringPolicyRef("P1", 1, "1"),
            numeric_profile_version="1",
            criterion_effects=(object(),),
            rule_decisions=(),
            stage_effects=(),
            base_subtotal=ScoringDecimal.from_raw("0"),
            score_before_rounding=ScoringDecimal.from_raw("0"),
            final_score=ScoringDecimal.from_raw("0"),
            minimum_score=ScoringDecimal.from_raw("0"),
            maximum_score=ScoringDecimal.from_raw("1"),
        ),
        lambda result_module: result_module.QuestionScoreResult(
            question_id="Q1",
            rubric_ref=result_module.RubricRef("R1", 1),
            scoring_policy_ref=result_module.ScoringPolicyRef("P1", 1, "1"),
            numeric_profile_version="1",
            criterion_effects=(),
            rule_decisions=(object(),),
            stage_effects=(),
            base_subtotal=ScoringDecimal.from_raw("0"),
            score_before_rounding=ScoringDecimal.from_raw("0"),
            final_score=ScoringDecimal.from_raw("0"),
            minimum_score=ScoringDecimal.from_raw("0"),
            maximum_score=ScoringDecimal.from_raw("1"),
        ),
        lambda result_module: result_module.QuestionScoreResult(
            question_id="Q1",
            rubric_ref=result_module.RubricRef("R1", 1),
            scoring_policy_ref=result_module.ScoringPolicyRef("P1", 1, "1"),
            numeric_profile_version="1",
            criterion_effects=(),
            rule_decisions=(),
            stage_effects=(object(),),
            base_subtotal=ScoringDecimal.from_raw("0"),
            score_before_rounding=ScoringDecimal.from_raw("0"),
            final_score=ScoringDecimal.from_raw("0"),
            minimum_score=ScoringDecimal.from_raw("0"),
            maximum_score=ScoringDecimal.from_raw("1"),
        ),
    ),
)
def test_result_collection_fields_require_exact_immutable_tuple_shapes(
    factory,
) -> None:
    result_module = _import_result_module()

    with pytest.raises(TypeError):
        factory(result_module)
