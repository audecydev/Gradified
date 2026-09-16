import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.policy import (
    SCORING_SEMANTICS_V1,
    CriterionCondition,
    PositiveCreditDependencyRule,
    QuestionScoringPolicy,
)
from grading.contracts.rubric import (
    AtomicCriterion,
    CompiledQuestionRubric,
    PerformanceLevel,
)
from grading.contracts.result import RuleType, ScoreStage
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.reducer import reduce_question


def sd(value: str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(value)


def criterion(
    criterion_id: str,
    *levels: tuple[str, str],
) -> AtomicCriterion:
    return AtomicCriterion(
        criterion_id=criterion_id,
        operational_description=f"Assess {criterion_id}.",
        performance_levels=tuple(
            PerformanceLevel(
                level_id=level_id,
                contribution=sd(contribution),
            )
            for level_id, contribution in levels
        ),
    )


def dependency(
    rule_id: str,
    target_criterion_id: str,
    *conditions: tuple[str, tuple[str, ...]],
) -> PositiveCreditDependencyRule:
    return PositiveCreditDependencyRule(
        rule_id=rule_id,
        target_criterion_id=target_criterion_id,
        prerequisite_conditions=tuple(
            CriterionCondition(
                criterion_id=criterion_id,
                allowed_level_ids=allowed_level_ids,
            )
            for criterion_id, allowed_level_ids in conditions
        ),
    )


def authority(
    *criteria: AtomicCriterion,
    dependencies: tuple[PositiveCreditDependencyRule, ...] = (),
    minimum_score: str = "0",
    maximum_score: str = "10",
) -> QuestionScoringAuthority:
    maximum = sd(maximum_score)

    rubric = CompiledQuestionRubric(
        rubric_id="rubric-q1",
        version=1,
        question_id="Q1",
        max_marks=maximum,
        criteria=criteria,
    )

    policy = QuestionScoringPolicy(
        policy_id="policy-q1",
        version=1,
        question_id="Q1",
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=sd(minimum_score),
        maximum_score=maximum,
        positive_credit_dependencies=dependencies,
    )

    return QuestionScoringAuthority(
        rubric=rubric,
        policy=policy,
    )


def effects_by_id(result):
    return {
        effect.criterion_id: effect
        for effect in result.criterion_effects
    }


@pytest.mark.parametrize(
    ("selected_level", "expected"),
    (
        ("FULL", "2"),
        ("PARTIAL", "1"),
        ("ZERO", "0"),
        ("NEGATIVE", "-0.5"),
    ),
)
def test_selected_level_maps_only_to_rubric_authorized_contribution(
    selected_level: str,
    expected: str,
) -> None:
    scoring_authority = authority(
        criterion(
            "C1",
            ("FULL", "2"),
            ("PARTIAL", "1"),
            ("ZERO", "0"),
            ("NEGATIVE", "-0.5"),
        ),
        minimum_score="-1",
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment(
                criterion_id="C1",
                selected_level=selected_level,
            ),
        ),
    )

    expected_score = sd(expected)

    assert result.base_subtotal == expected_score
    assert result.final_score == expected_score

    effect = result.criterion_effects[0]
    assert effect.criterion_id == "C1"
    assert effect.selected_level == selected_level
    assert effect.base_contribution == expected_score
    assert effect.effective_contribution == expected_score
    assert effect.blocking_dependency_rule_ids == ()


def test_contribution_comes_from_rubric_not_level_name_or_fixed_mapping() -> None:
    scoring_authority = authority(
        criterion(
            "C1",
            ("TOP", "1.75"),
            ("MID", "0.80"),
            ("ZERO", "0"),
            ("PENALTY", "-0.40"),
        ),
        minimum_score="-1",
        maximum_score="1.75",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment(
                criterion_id="C1",
                selected_level="MID",
            ),
        ),
    )

    assert result.base_subtotal == sd("0.8")
    assert result.final_score == sd("0.8")

    effect = result.criterion_effects[0]
    assert effect.criterion_id == "C1"
    assert effect.selected_level == "MID"
    assert effect.base_contribution == sd("0.8")
    assert effect.effective_contribution == sd("0.8")
    assert effect.blocking_dependency_rule_ids == ()


def test_no_downstream_rules_emit_identity_stage_provenance() -> None:
    scoring_authority = authority(
        criterion(
            "C1",
            ("FULL", "1.25"),
            ("ZERO", "0"),
        ),
        maximum_score="1.25",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("C1", "FULL"),
        ),
    )

    expected_score = sd("1.25")

    assert result.base_subtotal == expected_score
    assert result.score_before_rounding == expected_score
    assert result.final_score == expected_score
    assert result.rule_decisions == ()

    assert tuple(
        effect.stage
        for effect in result.stage_effects
    ) == (
        ScoreStage.GATES,
        ScoreStage.CAPS,
        ScoreStage.DEDUCTIONS,
        ScoreStage.ROUNDING,
    )

    for effect in result.stage_effects:
        assert effect.before == expected_score
        assert effect.after == expected_score
        assert effect.source_rule_ids == ()


def test_independent_criteria_sum_exactly_and_judgment_order_is_irrelevant() -> None:
    scoring_authority = authority(
        criterion("C1", ("FULL", "2"), ("ZERO", "0")),
        criterion("C2", ("FULL", "1.5"), ("ZERO", "0")),
        maximum_score="5",
    )

    forward = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("C1", "FULL"),
            CriterionJudgment("C2", "FULL"),
        ),
    )

    reversed_order = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("C2", "FULL"),
            CriterionJudgment("C1", "FULL"),
        ),
    )

    assert forward.base_subtotal == sd("3.5")
    assert forward.final_score == sd("3.5")
    assert reversed_order == forward


def test_satisfied_dependency_preserves_positive_credit() -> None:
    scoring_authority = authority(
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("T", ("FULL", "2"), ("ZERO", "0")),
        dependencies=(
            dependency(
                "DEP-T-P",
                "T",
                ("P", ("FULL",)),
            ),
        ),
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("P", "FULL"),
            CriterionJudgment("T", "FULL"),
        ),
    )

    target = effects_by_id(result)["T"]

    assert target.base_contribution == sd("2")
    assert target.effective_contribution == sd("2")
    assert target.blocking_dependency_rule_ids == ()
    assert result.final_score == sd("2")


def test_failed_dependency_suppresses_positive_credit() -> None:
    scoring_authority = authority(
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("T", ("FULL", "2"), ("ZERO", "0")),
        dependencies=(
            dependency(
                "DEP-T-P",
                "T",
                ("P", ("FULL",)),
            ),
        ),
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("P", "NOT_MET"),
            CriterionJudgment("T", "FULL"),
        ),
    )

    target = effects_by_id(result)["T"]

    assert target.base_contribution == sd("2")
    assert target.effective_contribution == sd("0")
    assert target.blocking_dependency_rule_ids == ("DEP-T-P",)
    assert result.final_score == sd("0")


def test_failed_dependency_preserves_negative_contribution() -> None:
    scoring_authority = authority(
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        criterion(
            "T",
            ("FULL", "2"),
            ("NEGATIVE", "-0.5"),
        ),
        dependencies=(
            dependency(
                "DEP-T-P",
                "T",
                ("P", ("FULL",)),
            ),
        ),
        minimum_score="-1",
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("P", "NOT_MET"),
            CriterionJudgment("T", "NEGATIVE"),
        ),
    )

    target = effects_by_id(result)["T"]

    assert target.base_contribution == sd("-0.5")
    assert target.effective_contribution == sd("-0.5")
    assert target.blocking_dependency_rule_ids == ("DEP-T-P",)

    decision = next(
        decision
        for decision in result.rule_decisions
        if decision.rule_id == "DEP-T-P"
    )

    assert decision.rule_type is RuleType.DEPENDENCY
    assert decision.triggered is True
    assert decision.configured_effect is None

    assert result.final_score == sd("-0.5")


def test_multiple_dependency_conditions_use_and_semantics() -> None:
    scoring_authority = authority(
        criterion("P1", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("P2", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("T", ("FULL", "2"), ("ZERO", "0")),
        dependencies=(
            dependency(
                "DEP-T-PREREQS",
                "T",
                ("P1", ("FULL",)),
                ("P2", ("FULL",)),
            ),
        ),
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("P1", "FULL"),
            CriterionJudgment("P2", "NOT_MET"),
            CriterionJudgment("T", "FULL"),
        ),
    )

    target = effects_by_id(result)["T"]

    assert target.effective_contribution == sd("0")
    assert target.blocking_dependency_rule_ids == ("DEP-T-PREREQS",)


@pytest.mark.parametrize(
    (
        "p1_level",
        "p2_level",
        "expected_effective",
        "expected_blocking_ids",
        "expected_triggered",
    ),
    (
        ("FULL", "FULL", "2", (), (False, False)),
        ("NOT_MET", "FULL", "0", ("DEP-T-P1",), (True, False)),
        ("FULL", "NOT_MET", "0", ("DEP-T-P2",), (False, True)),
        (
            "NOT_MET",
            "NOT_MET",
            "0",
            ("DEP-T-P1", "DEP-T-P2"),
            (True, True),
        ),
    ),
)
def test_all_dependency_rules_targeting_one_criterion_are_evaluated(
    p1_level: str,
    p2_level: str,
    expected_effective: str,
    expected_blocking_ids: tuple[str, ...],
    expected_triggered: tuple[bool, bool],
) -> None:
    scoring_authority = authority(
        criterion("P1", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("P2", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("T", ("FULL", "2"), ("ZERO", "0")),
        dependencies=(
            dependency(
                "DEP-T-P1",
                "T",
                ("P1", ("FULL",)),
            ),
            dependency(
                "DEP-T-P2",
                "T",
                ("P2", ("FULL",)),
            ),
        ),
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("P1", p1_level),
            CriterionJudgment("P2", p2_level),
            CriterionJudgment("T", "FULL"),
        ),
    )

    target = effects_by_id(result)["T"]

    assert target.base_contribution == sd("2")
    assert target.effective_contribution == sd(expected_effective)
    assert target.blocking_dependency_rule_ids == expected_blocking_ids

    decisions = {
        decision.rule_id: decision
        for decision in result.rule_decisions
    }

    assert decisions["DEP-T-P1"].rule_type is RuleType.DEPENDENCY
    assert decisions["DEP-T-P1"].triggered is expected_triggered[0]
    assert decisions["DEP-T-P1"].configured_effect is None

    assert decisions["DEP-T-P2"].rule_type is RuleType.DEPENDENCY
    assert decisions["DEP-T-P2"].triggered is expected_triggered[1]
    assert decisions["DEP-T-P2"].configured_effect is None

    assert result.final_score == sd(expected_effective)


def test_blocking_dependency_ids_are_canonical_across_rule_order() -> None:
    criteria = (
        criterion("P1", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("P2", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("T", ("FULL", "2"), ("ZERO", "0")),
    )

    dependency_p1 = dependency(
        "DEP-T-P1",
        "T",
        ("P1", ("FULL",)),
    )
    dependency_p2 = dependency(
        "DEP-T-P2",
        "T",
        ("P2", ("FULL",)),
    )

    noncanonical_authority = authority(
        *criteria,
        dependencies=(
            dependency_p2,
            dependency_p1,
        ),
        maximum_score="2",
    )

    canonical_authority = authority(
        *criteria,
        dependencies=(
            dependency_p1,
            dependency_p2,
        ),
        maximum_score="2",
    )

    judgments = (
        CriterionJudgment("P1", "NOT_MET"),
        CriterionJudgment("P2", "NOT_MET"),
        CriterionJudgment("T", "FULL"),
    )

    noncanonical_result = reduce_question(
        noncanonical_authority,
        judgments,
    )
    canonical_result = reduce_question(
        canonical_authority,
        judgments,
    )

    target = effects_by_id(noncanonical_result)["T"]

    assert target.blocking_dependency_rule_ids == (
        "DEP-T-P1",
        "DEP-T-P2",
    )
    assert noncanonical_result == canonical_result


def test_condition_allowed_levels_use_membership_or_semantics() -> None:
    scoring_authority = authority(
        criterion(
            "P",
            ("FULL", "0"),
            ("PARTIAL", "0"),
            ("NOT_MET", "0"),
        ),
        criterion("T", ("FULL", "2"), ("ZERO", "0")),
        dependencies=(
            dependency(
                "DEP-T-P",
                "T",
                ("P", ("FULL", "PARTIAL")),
            ),
        ),
        maximum_score="2",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("P", "PARTIAL"),
            CriterionJudgment("T", "FULL"),
        ),
    )

    target = effects_by_id(result)["T"]

    assert target.effective_contribution == sd("2")
    assert target.blocking_dependency_rule_ids == ()


def test_dependency_predicates_use_original_judgments_not_effective_credit() -> None:
    scoring_authority = authority(
        criterion("C", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("B", ("FULL", "2"), ("ZERO", "0")),
        criterion("A", ("FULL", "2"), ("ZERO", "0")),
        dependencies=(
            dependency(
                "DEP-B-C",
                "B",
                ("C", ("FULL",)),
            ),
            dependency(
                "DEP-A-B",
                "A",
                ("B", ("FULL",)),
            ),
        ),
        maximum_score="4",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("C", "NOT_MET"),
            CriterionJudgment("B", "FULL"),
            CriterionJudgment("A", "FULL"),
        ),
    )

    effects = effects_by_id(result)

    assert effects["B"].base_contribution == sd("2")
    assert effects["B"].effective_contribution == sd("0")
    assert effects["B"].blocking_dependency_rule_ids == ("DEP-B-C",)

    assert effects["A"].base_contribution == sd("2")
    assert effects["A"].effective_contribution == sd("2")
    assert effects["A"].blocking_dependency_rule_ids == ()

    assert result.final_score == sd("2")