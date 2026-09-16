from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from grading.contracts.result import (
    CriterionEffect,
    QuestionScoreResult,
    RubricRef,
    RuleDecision,
    RuleType,
    ScoreStage,
    ScoreStageEffect,
    ScoringPolicyRef,
)
from grading.contracts.scoring_decimal import ScoringDecimal


def sd(raw: str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


BASE_RUBRIC_REF = RubricRef(id="R1", version=1)

BASE_POLICY_REF = ScoringPolicyRef(
    id="P1",
    version=1,
    scoring_semantics_version="1",
)

BASE_CRITERION_EFFECT = CriterionEffect(
    criterion_id="C1",
    selected_level="FULL",
    base_contribution=sd("1"),
    effective_contribution=sd("1"),
    blocking_dependency_rule_ids=(),
)

BASE_RULE_DECISION = RuleDecision(
    rule_id="D1",
    rule_type=RuleType.DEDUCTION,
    triggered=False,
    configured_effect=None,
)

BASE_STAGE_EFFECT = ScoreStageEffect(
    stage=ScoreStage.GATES,
    before=sd("1"),
    after=sd("1"),
    source_rule_ids=(),
)

BASE_RESULT = QuestionScoreResult(
    question_id="Q1",
    rubric_ref=BASE_RUBRIC_REF,
    scoring_policy_ref=BASE_POLICY_REF,
    numeric_profile_version="1",
    criterion_effects=(BASE_CRITERION_EFFECT,),
    rule_decisions=(BASE_RULE_DECISION,),
    stage_effects=(BASE_STAGE_EFFECT,),
    base_subtotal=sd("1"),
    score_before_rounding=sd("1"),
    final_score=sd("1"),
    minimum_score=sd("0"),
    maximum_score=sd("1"),
)


@pytest.mark.parametrize(
    ("case_id", "instance", "field_name", "wrong_value"),
    (
        ("RubricRef.id", BASE_RUBRIC_REF, "id", 123),
        ("RubricRef.version", BASE_RUBRIC_REF, "version", True),
        ("ScoringPolicyRef.id", BASE_POLICY_REF, "id", 123),
        ("ScoringPolicyRef.version", BASE_POLICY_REF, "version", "1"),
        (
            "ScoringPolicyRef.scoring_semantics_version",
            BASE_POLICY_REF,
            "scoring_semantics_version",
            1,
        ),
        ("CriterionEffect.criterion_id", BASE_CRITERION_EFFECT, "criterion_id", 123),
        ("CriterionEffect.selected_level", BASE_CRITERION_EFFECT, "selected_level", 123),
        (
            "CriterionEffect.base_contribution",
            BASE_CRITERION_EFFECT,
            "base_contribution",
            Decimal("1"),
        ),
        (
            "CriterionEffect.effective_contribution",
            BASE_CRITERION_EFFECT,
            "effective_contribution",
            "1",
        ),
        ("RuleDecision.rule_id", BASE_RULE_DECISION, "rule_id", 123),
        ("RuleDecision.rule_type", BASE_RULE_DECISION, "rule_type", "DEDUCTION"),
        ("RuleDecision.triggered", BASE_RULE_DECISION, "triggered", 1),
        (
            "RuleDecision.configured_effect",
            BASE_RULE_DECISION,
            "configured_effect",
            Decimal("0.5"),
        ),
        ("ScoreStageEffect.stage", BASE_STAGE_EFFECT, "stage", "GATES"),
        (
            "ScoreStageEffect.before",
            BASE_STAGE_EFFECT,
            "before",
            Decimal("1"),
        ),
        ("ScoreStageEffect.after", BASE_STAGE_EFFECT, "after", "1"),
        ("QuestionScoreResult.question_id", BASE_RESULT, "question_id", 123),
        (
            "QuestionScoreResult.rubric_ref",
            BASE_RESULT,
            "rubric_ref",
            BASE_POLICY_REF,
        ),
        (
            "QuestionScoreResult.scoring_policy_ref",
            BASE_RESULT,
            "scoring_policy_ref",
            BASE_RUBRIC_REF,
        ),
        (
            "QuestionScoreResult.numeric_profile_version",
            BASE_RESULT,
            "numeric_profile_version",
            1,
        ),
        (
            "QuestionScoreResult.base_subtotal",
            BASE_RESULT,
            "base_subtotal",
            Decimal("1"),
        ),
        (
            "QuestionScoreResult.score_before_rounding",
            BASE_RESULT,
            "score_before_rounding",
            "1",
        ),
        ("QuestionScoreResult.final_score", BASE_RESULT, "final_score", 1),
        (
            "QuestionScoreResult.minimum_score",
            BASE_RESULT,
            "minimum_score",
            Decimal("0"),
        ),
        (
            "QuestionScoreResult.maximum_score",
            BASE_RESULT,
            "maximum_score",
            object(),
        ),
    ),
    ids=lambda value: value if isinstance(value, str) and "." in value else None,
)
def test_every_scalar_or_reference_field_rejects_wrong_runtime_type(
    case_id: str,
    instance,
    field_name: str,
    wrong_value: object,
) -> None:
    """Every non-collection field is a closed exact-runtime-type boundary."""

    del case_id

    with pytest.raises(TypeError):
        replace(instance, **{field_name: wrong_value})


def test_mutable_str_subclass_cannot_cross_exact_string_boundary() -> None:
    """A str subclass may carry mutable state and must not enter the result graph."""

    class MutableStr(str):
        pass

    value = MutableStr("R1")
    value.mutable_payload = []

    with pytest.raises(TypeError):
        RubricRef(id=value, version=1)


def test_exact_enum_and_scoring_types_are_accepted() -> None:
    """The closed boundary accepts the exact immutable contract types."""

    effect = sd("0.5")

    decision_with_none = RuleDecision(
        rule_id="D-NONE",
        rule_type=RuleType.DEDUCTION,
        triggered=False,
        configured_effect=None,
    )
    decision_with_effect = RuleDecision(
        rule_id="D-EFFECT",
        rule_type=RuleType.DEDUCTION,
        triggered=True,
        configured_effect=effect,
    )
    stage = ScoreStageEffect(
        stage=ScoreStage.ROUNDING,
        before=sd("1.25"),
        after=sd("1.5"),
        source_rule_ids=("ROUND-1",),
    )
    result = QuestionScoreResult(
        question_id="Q-VALID",
        rubric_ref=RubricRef(id="R-VALID", version=1),
        scoring_policy_ref=ScoringPolicyRef(
            id="P-VALID",
            version=1,
            scoring_semantics_version="1",
        ),
        numeric_profile_version="1",
        criterion_effects=(),
        rule_decisions=(decision_with_none, decision_with_effect),
        stage_effects=(stage,),
        base_subtotal=sd("1.25"),
        score_before_rounding=sd("1.25"),
        final_score=sd("1.5"),
        minimum_score=sd("0"),
        maximum_score=sd("2"),
    )

    assert decision_with_none.configured_effect is None
    assert decision_with_effect.configured_effect == effect
    assert decision_with_effect.rule_type is RuleType.DEDUCTION
    assert stage.stage is ScoreStage.ROUNDING
    assert type(result.rubric_ref) is RubricRef
    assert type(result.scoring_policy_ref) is ScoringPolicyRef
    assert type(result.final_score) is ScoringDecimal

@pytest.mark.parametrize(
    ("instance", "field_name", "valid_items"),
    (
        (
            BASE_CRITERION_EFFECT,
            "blocking_dependency_rule_ids",
            ("DEP-1",),
        ),
        (
            BASE_STAGE_EFFECT,
            "source_rule_ids",
            ("G-1",),
        ),
        (
            BASE_RESULT,
            "criterion_effects",
            (BASE_CRITERION_EFFECT,),
        ),
        (
            BASE_RESULT,
            "rule_decisions",
            (BASE_RULE_DECISION,),
        ),
        (
            BASE_RESULT,
            "stage_effects",
            (BASE_STAGE_EFFECT,),
        ),
    ),
)
def test_collection_fields_reject_mutable_tuple_subclasses(
    instance,
    field_name: str,
    valid_items: tuple[object, ...],
) -> None:
    """Every collection boundary requires the exact built-in tuple type."""

    class MutableTuple(tuple):
        pass

    value = MutableTuple(valid_items)
    value.mutable_payload = []

    with pytest.raises(TypeError):
        replace(instance, **{field_name: value})


@pytest.mark.parametrize(
    ("instance", "field_name"),
    (
        (
            BASE_CRITERION_EFFECT,
            "blocking_dependency_rule_ids",
        ),
        (
            BASE_STAGE_EFFECT,
            "source_rule_ids",
        ),
    ),
)
def test_string_collection_items_reject_mutable_str_subclasses(
    instance,
    field_name: str,
) -> None:
    """String-valued provenance tuples require exact built-in str elements."""

    class MutableStr(str):
        pass

    value = MutableStr("RULE-1")
    value.mutable_payload = []

    with pytest.raises(TypeError):
        replace(instance, **{field_name: (value,)})
