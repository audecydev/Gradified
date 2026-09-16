import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import ScoreOutOfRangeError
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.policy import (
    SCORING_SEMANTICS_V1,
    CapRule,
    CriterionCondition,
    DeductionRule,
    GateRule,
    PositiveCreditDependencyRule,
    QuestionScoringPolicy,
    RoundingMode,
    RoundingRule,
)
from grading.contracts.result import RuleType, ScoreStage
from grading.contracts.rubric import (
    AtomicCriterion,
    CompiledQuestionRubric,
    PerformanceLevel,
)
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


def condition(
    criterion_id: str,
    *allowed_level_ids: str,
) -> CriterionCondition:
    return CriterionCondition(
        criterion_id=criterion_id,
        allowed_level_ids=allowed_level_ids,
    )


def dependency(
    rule_id: str,
    target_criterion_id: str,
    *conditions: CriterionCondition,
) -> PositiveCreditDependencyRule:
    return PositiveCreditDependencyRule(
        rule_id=rule_id,
        target_criterion_id=target_criterion_id,
        prerequisite_conditions=conditions,
    )


def gate(
    rule_id: str,
    failure_ceiling: str,
    *conditions: CriterionCondition,
) -> GateRule:
    return GateRule(
        rule_id=rule_id,
        required_conditions=conditions,
        failure_ceiling=sd(failure_ceiling),
    )


def cap(
    rule_id: str,
    ceiling: str,
    *conditions: CriterionCondition,
) -> CapRule:
    return CapRule(
        rule_id=rule_id,
        trigger_conditions=conditions,
        ceiling=sd(ceiling),
    )


def deduction(
    rule_id: str,
    amount: str,
    *conditions: CriterionCondition,
) -> DeductionRule:
    return DeductionRule(
        rule_id=rule_id,
        trigger_conditions=conditions,
        amount=sd(amount),
    )


def rounding(
    rule_id: str,
    increment: str,
    mode: RoundingMode,
) -> RoundingRule:
    return RoundingRule(
        rule_id=rule_id,
        increment=sd(increment),
        mode=mode,
    )


def authority(
    *criteria: AtomicCriterion,
    dependencies: tuple[PositiveCreditDependencyRule, ...] = (),
    gates: tuple[GateRule, ...] = (),
    caps: tuple[CapRule, ...] = (),
    deductions: tuple[DeductionRule, ...] = (),
    rounding_rule: RoundingRule | None = None,
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
        gates=gates,
        caps=caps,
        deductions=deductions,
        rounding=rounding_rule,
    )

    return QuestionScoringAuthority(rubric=rubric, policy=policy)


def decision_by_id(result, rule_id: str):
    return next(
        decision
        for decision in result.rule_decisions
        if decision.rule_id == rule_id
    )


def stage_by_name(result, stage: ScoreStage):
    return next(
        effect
        for effect in result.stage_effects
        if effect.stage is stage
    )


@pytest.mark.parametrize(
    ("b_level", "expected_score", "gate_triggered", "cap_triggered", "deduction_triggered"),
    (
        ("FULL", "3", False, True, True),
        ("NOT_MET", "5", True, False, False),
    ),
)
def test_gate_cap_and_deduction_share_frozen_condition_semantics(
    b_level: str,
    expected_score: str,
    gate_triggered: bool,
    cap_triggered: bool,
    deduction_triggered: bool,
) -> None:
    shared_conditions = (
        condition("A", "FULL", "PARTIAL"),
        condition("B", "FULL"),
    )
    scoring_authority = authority(
        criterion("S", ("FULL", "6"), ("ZERO", "0")),
        criterion("A", ("FULL", "0"), ("PARTIAL", "0")),
        criterion("B", ("FULL", "0"), ("NOT_MET", "0")),
        gates=(gate("G1", "5", *shared_conditions),),
        caps=(cap("C1", "4", *shared_conditions),),
        deductions=(deduction("D1", "1", *shared_conditions),),
        maximum_score="6",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "FULL"),
            CriterionJudgment("A", "PARTIAL"),
            CriterionJudgment("B", b_level),
        ),
    )

    assert result.final_score == sd(expected_score)
    assert decision_by_id(result, "G1").triggered is gate_triggered
    assert decision_by_id(result, "C1").triggered is cap_triggered
    assert decision_by_id(result, "D1").triggered is deduction_triggered
    gate_stage = stage_by_name(result, ScoreStage.GATES)
    cap_stage = stage_by_name(result, ScoreStage.CAPS)
    deduction_stage = stage_by_name(result, ScoreStage.DEDUCTIONS)

    assert gate_stage.source_rule_ids == (
        ("G1",) if gate_triggered else ()
    )
    assert cap_stage.source_rule_ids == (
        ("C1",) if cap_triggered else ()
    )
    assert deduction_stage.source_rule_ids == (
        ("D1",) if deduction_triggered else ()
    )

    for stage, triggered in (
        (gate_stage, gate_triggered),
        (cap_stage, cap_triggered),
        (deduction_stage, deduction_triggered),
    ):
        if not triggered:
            assert stage.before == stage.after


def test_triggered_gate_ceiling_cannot_increase_score() -> None:
    scoring_authority = authority(
        criterion(
            "S",
            ("MAX", "5"),
            ("VALUE", "3"),
        ),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        gates=(
            gate(
                "G-NOOP",
                "5",
                condition("P", "FULL"),
            ),
        ),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "VALUE"),
            CriterionJudgment("P", "NOT_MET"),
        ),
    )

    stage = stage_by_name(result, ScoreStage.GATES)
    decision = decision_by_id(result, "G-NOOP")

    assert decision.rule_type is RuleType.GATE
    assert decision.triggered is True
    assert decision.configured_effect == sd("5")

    assert stage.before == sd("3")
    assert stage.after == sd("3")
    assert stage.source_rule_ids == ("G-NOOP",)

    assert result.final_score == sd("3")


def test_triggered_cap_ceiling_cannot_increase_score() -> None:
    scoring_authority = authority(
        criterion(
            "S",
            ("MAX", "5"),
            ("VALUE", "3"),
        ),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        caps=(
            cap(
                "C-NOOP",
                "5",
                condition("P", "FULL"),
            ),
        ),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "VALUE"),
            CriterionJudgment("P", "FULL"),
        ),
    )

    stage = stage_by_name(result, ScoreStage.CAPS)
    decision = decision_by_id(result, "C-NOOP")

    assert decision.rule_type is RuleType.CAP
    assert decision.triggered is True
    assert decision.configured_effect == sd("5")

    assert stage.before == sd("3")
    assert stage.after == sd("3")
    assert stage.source_rule_ids == ("C-NOOP",)

    assert result.final_score == sd("3")


def test_multiple_triggered_gates_use_most_restrictive_ceiling() -> None:
    scoring_authority = authority(
        criterion("S", ("FULL", "8"), ("ZERO", "0")),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        gates=(
            gate("G-6", "6", condition("P", "FULL")),
            gate("G-4", "4", condition("P", "FULL")),
        ),
        maximum_score="10",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "FULL"),
            CriterionJudgment("P", "NOT_MET"),
        ),
    )

    stage = stage_by_name(result, ScoreStage.GATES)
    assert result.final_score == sd("4")
    assert stage.before == sd("8")
    assert stage.after == sd("4")
    assert stage.source_rule_ids == ("G-4", "G-6")

    for rule_id, ceiling in (("G-4", "4"), ("G-6", "6")):
        decision = decision_by_id(result, rule_id)
        assert decision.rule_type is RuleType.GATE
        assert decision.triggered is True
        assert decision.configured_effect == sd(ceiling)


def test_multiple_triggered_caps_use_most_restrictive_ceiling() -> None:
    scoring_authority = authority(
        criterion("S", ("FULL", "8"), ("ZERO", "0")),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        caps=(
            cap("C-5", "5", condition("P", "FULL")),
            cap("C-3", "3", condition("P", "FULL")),
        ),
        maximum_score="10",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "FULL"),
            CriterionJudgment("P", "FULL"),
        ),
    )

    stage = stage_by_name(result, ScoreStage.CAPS)
    assert result.final_score == sd("3")
    assert stage.before == sd("8")
    assert stage.after == sd("3")
    assert stage.source_rule_ids == ("C-3", "C-5")

    for rule_id, ceiling in (("C-3", "3"), ("C-5", "5")):
        decision = decision_by_id(result, rule_id)
        assert decision.rule_type is RuleType.CAP
        assert decision.triggered is True
        assert decision.configured_effect == sd(ceiling)


def test_one_deduction_with_multiple_matching_conditions_applies_once() -> None:
    conditions = (
        condition("P1", "FULL"),
        condition("P2", "FULL"),
    )
    scoring_authority = authority(
        criterion("S", ("FULL", "5"), ("ZERO", "0")),
        criterion("P1", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("P2", ("FULL", "0"), ("NOT_MET", "0")),
        deductions=(deduction("D1", "1", *conditions),),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "FULL"),
            CriterionJudgment("P1", "FULL"),
            CriterionJudgment("P2", "FULL"),
        ),
    )

    stage = stage_by_name(result, ScoreStage.DEDUCTIONS)
    decision = decision_by_id(result, "D1")

    assert result.final_score == sd("4")
    assert stage.before == sd("5")
    assert stage.after == sd("4")
    assert stage.source_rule_ids == ("D1",)
    assert decision.rule_type is RuleType.DEDUCTION
    assert decision.triggered is True
    assert decision.configured_effect == sd("1")


def test_multiple_triggered_deductions_stack_once_each() -> None:
    scoring_authority = authority(
        criterion("S", ("FULL", "5"), ("ZERO", "0")),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        deductions=(
            deduction("D-025", "0.25", condition("P", "FULL")),
            deduction("D-050", "0.5", condition("P", "FULL")),
        ),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "FULL"),
            CriterionJudgment("P", "FULL"),
        ),
    )

    stage = stage_by_name(result, ScoreStage.DEDUCTIONS)
    assert result.final_score == sd("4.25")
    assert stage.before == sd("5")
    assert stage.after == sd("4.25")
    assert stage.source_rule_ids == ("D-025", "D-050")


def test_fixed_stage_order_is_gate_then_cap_then_deduction_then_rounding() -> None:
    scoring_authority = authority(
        criterion("S", ("FULL", "8"), ("ZERO", "0")),
        criterion("G", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("T", ("YES", "0"), ("NO", "0")),
        gates=(gate("GATE", "6", condition("G", "FULL")),),
        caps=(cap("CAP", "4", condition("T", "YES")),),
        deductions=(deduction("DED", "1", condition("T", "YES")),),
        maximum_score="10",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "FULL"),
            CriterionJudgment("G", "NOT_MET"),
            CriterionJudgment("T", "YES"),
        ),
    )

    assert result.base_subtotal == sd("8")
    assert result.score_before_rounding == sd("3")
    assert result.final_score == sd("3")

    stages = result.stage_effects
    assert tuple(effect.stage for effect in stages) == (
        ScoreStage.GATES,
        ScoreStage.CAPS,
        ScoreStage.DEDUCTIONS,
        ScoreStage.ROUNDING,
    )
    assert (stages[0].before, stages[0].after) == (sd("8"), sd("6"))
    assert (stages[1].before, stages[1].after) == (sd("6"), sd("4"))
    assert (stages[2].before, stages[2].after) == (sd("4"), sd("3"))
    assert (stages[3].before, stages[3].after) == (sd("3"), sd("3"))
    assert result.base_subtotal == stages[0].before

    assert stages[0].after == stages[1].before
    assert stages[1].after == stages[2].before
    assert stages[2].after == stages[3].before

    assert result.score_before_rounding == stages[2].after
    assert result.final_score == stages[3].after


def test_rounding_occurs_only_after_criterion_contributions_are_summed() -> None:
    scoring_authority = authority(
        criterion("C1", ("RAW", "0.26"), ("MAX", "0.5")),
        criterion("C2", ("RAW", "0.26"), ("MAX", "0.5")),
        rounding_rule=rounding("ROUND", "0.5", RoundingMode.HALF_UP),
        maximum_score="1",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("C1", "RAW"),
            CriterionJudgment("C2", "RAW"),
        ),
    )

    assert result.base_subtotal == sd("0.52")
    assert result.score_before_rounding == sd("0.52")
    assert result.final_score == sd("0.5")


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        (RoundingMode.HALF_UP, "3"),
        (RoundingMode.HALF_EVEN, "2"),
    ),
)
def test_reducer_honors_configured_rounding_mode(
    mode: RoundingMode,
    expected: str,
) -> None:
    scoring_authority = authority(
        criterion("C1", ("MAX", "3"), ("TIE", "2.5")),
        rounding_rule=rounding("ROUND", "1", mode),
        maximum_score="3",
    )

    result = reduce_question(
        scoring_authority,
        (CriterionJudgment("C1", "TIE"),),
    )

    assert result.score_before_rounding == sd("2.5")
    assert result.final_score == sd(expected)

    rounding_stage = stage_by_name(result, ScoreStage.ROUNDING)
    assert rounding_stage.before == sd("2.5")
    assert rounding_stage.after == sd(expected)
    assert rounding_stage.source_rule_ids == ("ROUND",)
    assert all(
        decision.rule_id != "ROUND"
        for decision in result.rule_decisions
    )


def test_rounding_occurs_after_deductions() -> None:
    scoring_authority = authority(
        criterion("C1", ("MAX", "3"), ("TIE", "2.5")),
        deductions=(deduction("DED", "0.4", condition("C1", "TIE")),),
        rounding_rule=rounding("ROUND", "1", RoundingMode.HALF_UP),
        maximum_score="3",
    )

    result = reduce_question(
        scoring_authority,
        (CriterionJudgment("C1", "TIE"),),
    )

    deduction_stage = stage_by_name(result, ScoreStage.DEDUCTIONS)
    rounding_stage = stage_by_name(result, ScoreStage.ROUNDING)

    assert deduction_stage.before == sd("2.5")
    assert deduction_stage.after == sd("2.1")
    assert rounding_stage.before == sd("2.1")
    assert rounding_stage.after == sd("2")
    assert result.score_before_rounding == sd("2.1")
    assert result.final_score == sd("2")


def test_rules_still_inspect_original_judgment_after_dependency_suppression() -> None:
    scoring_authority = authority(
        criterion("C", ("FULL", "0"), ("NOT_MET", "0")),
        criterion("B", ("FULL", "4"), ("ZERO", "0")),
        criterion("A", ("FULL", "5"), ("ZERO", "0")),
        dependencies=(
            dependency("DEP-B-C", "B", condition("C", "FULL")),
        ),
        gates=(gate("GATE-B", "2", condition("B", "FULL")),),
        caps=(cap("CAP-B", "4", condition("B", "FULL")),),
        deductions=(deduction("DED-B", "1", condition("B", "FULL")),),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("C", "NOT_MET"),
            CriterionJudgment("B", "FULL"),
            CriterionJudgment("A", "FULL"),
        ),
    )

    effects = {effect.criterion_id: effect for effect in result.criterion_effects}
    assert effects["B"].effective_contribution == sd("0")

    assert decision_by_id(result, "GATE-B").triggered is False
    assert decision_by_id(result, "CAP-B").triggered is True
    assert decision_by_id(result, "DED-B").triggered is True
    assert result.final_score == sd("3")


@pytest.mark.parametrize(
    ("minimum", "maximum", "contribution"),
    (
        ("0", "1", "1.5"),
        ("0", "1", "-0.5"),
    ),
)
def test_final_range_violation_raises_without_clamping(
    minimum: str,
    maximum: str,
    contribution: str,
) -> None:
    scoring_authority = authority(
        criterion("C1", ("VALUE", contribution),),
        minimum_score=minimum,
        maximum_score=maximum,
    )

    with pytest.raises(ScoreOutOfRangeError):
        reduce_question(
            scoring_authority,
            (CriterionJudgment("C1", "VALUE"),),
        )


def test_range_is_checked_after_deductions_when_no_rounding_is_configured() -> None:
    scoring_authority = authority(
        criterion("S", ("VALUE", "1")),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        deductions=(
            deduction(
                "D-RANGE",
                "2",
                condition("P", "FULL"),
            ),
        ),
        minimum_score="0",
        maximum_score="1",
    )

    with pytest.raises(ScoreOutOfRangeError):
        reduce_question(
            scoring_authority,
            (
                CriterionJudgment("S", "VALUE"),
                CriterionJudgment("P", "FULL"),
            ),
        )


def test_range_is_checked_after_ceiling_stages_not_at_base_subtotal() -> None:
    scoring_authority = authority(
        criterion("S", ("OVER", "8"), ("ZERO", "0")),
        criterion("P", ("FULL", "0"), ("NOT_MET", "0")),
        gates=(gate("GATE", "5", condition("P", "FULL")),),
        caps=(cap("CAP", "4", condition("P", "NOT_MET")),),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (
            CriterionJudgment("S", "OVER"),
            CriterionJudgment("P", "NOT_MET"),
        ),
    )

    assert result.base_subtotal == sd("8")
    assert stage_by_name(result, ScoreStage.GATES).after == sd("5")
    assert stage_by_name(result, ScoreStage.CAPS).after == sd("4")
    assert result.final_score == sd("4")


def test_range_is_checked_after_rounding_when_rounding_pushes_above_maximum() -> None:
    scoring_authority = authority(
        criterion("C1", ("VALUE", "4.9"),),
        rounding_rule=rounding("ROUND", "0.25", RoundingMode.HALF_UP),
        maximum_score="4.9",
    )

    with pytest.raises(ScoreOutOfRangeError):
        reduce_question(
            scoring_authority,
            (CriterionJudgment("C1", "VALUE"),),
        )


def test_range_is_checked_after_rounding_when_rounding_pushes_below_minimum() -> None:
    scoring_authority = authority(
        criterion("C1", ("VALUE", "-0.125"),),
        rounding_rule=rounding("ROUND", "0.25", RoundingMode.HALF_UP),
        minimum_score="-0.2",
        maximum_score="1",
    )

    with pytest.raises(ScoreOutOfRangeError):
        reduce_question(
            scoring_authority,
            (CriterionJudgment("C1", "VALUE"),),
        )


def test_out_of_range_pre_round_score_can_round_back_into_range() -> None:
    scoring_authority = authority(
        criterion("C1", ("VALUE", "5.1"),),
        rounding_rule=rounding("ROUND", "1", RoundingMode.HALF_UP),
        maximum_score="5",
    )

    result = reduce_question(
        scoring_authority,
        (CriterionJudgment("C1", "VALUE"),),
    )

    assert result.score_before_rounding == sd("5.1")
    assert result.final_score == sd("5")
