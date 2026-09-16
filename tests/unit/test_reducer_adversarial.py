from __future__ import annotations

import ast
import copy
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from decimal import ROUND_CEILING, localcontext
from enum import Enum

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import MissingJudgmentError, ScoreOutOfRangeError, ScoringError
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
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
from grading.contracts.rubric import (
    AtomicCriterion,
    CompiledQuestionRubric,
    PerformanceLevel,
)
from grading.contracts.scoring_decimal import ScoringDecimal
import grading.scoring.reducer as reducer_module
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
            PerformanceLevel(level_id, sd(contribution))
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
    ceiling: str,
    *conditions: CriterionCondition,
) -> GateRule:
    return GateRule(
        rule_id=rule_id,
        required_conditions=conditions,
        failure_ceiling=sd(ceiling),
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
    rule_id: str = "ROUND",
    increment: str = "0.5",
    mode: RoundingMode = RoundingMode.HALF_UP,
) -> RoundingRule:
    return RoundingRule(
        rule_id=rule_id,
        increment=sd(increment),
        mode=mode,
    )


def full_authority() -> QuestionScoringAuthority:
    maximum = sd("10")
    rubric = CompiledQuestionRubric(
        rubric_id="rubric-full",
        version=3,
        question_id="Q-FULL",
        max_marks=maximum,
        criteria=(
            criterion("S", ("FULL", "8"), ("ZERO", "0")),
            criterion("A", ("FULL", "1"), ("ZERO", "0")),
            criterion("B", ("FULL", "1"), ("ZERO", "0")),
            criterion("C", ("FULL", "0"), ("NO", "0")),
            criterion("G", ("FULL", "0"), ("NO", "0")),
            criterion("T", ("YES", "0"), ("NO", "0")),
        ),
    )
    policy = QuestionScoringPolicy(
        policy_id="policy-full",
        version=4,
        question_id="Q-FULL",
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=sd("0"),
        maximum_score=maximum,
        positive_credit_dependencies=(
            dependency("DEP-B-C", "B", condition("C", "FULL")),
            dependency("DEP-A-C", "A", condition("C", "FULL")),
            dependency("DEP-S-T", "S", condition("T", "YES")),
        ),
        gates=(
            gate("G-8", "8", condition("G", "FULL")),
            gate("G-7", "7", condition("G", "FULL")),
            gate("G-PASS", "9", condition("T", "YES")),
        ),
        caps=(
            cap("C-6", "6", condition("T", "YES")),
            cap("C-5", "5", condition("T", "YES")),
            cap("C-OFF", "4", condition("G", "FULL")),
        ),
        deductions=(
            deduction("D-025", "0.25", condition("T", "YES")),
            deduction("D-050", "0.50", condition("T", "YES")),
            deduction("D-OFF", "0.10", condition("G", "FULL")),
        ),
        rounding=rounding(),
    )
    return QuestionScoringAuthority(rubric=rubric, policy=policy)


def full_judgments() -> tuple[CriterionJudgment, ...]:
    return (
        CriterionJudgment("S", "FULL"),
        CriterionJudgment("A", "FULL"),
        CriterionJudgment("B", "FULL"),
        CriterionJudgment("C", "NO"),
        CriterionJudgment("G", "NO"),
        CriterionJudgment("T", "YES"),
    )


def authority_with_policy(
    authority: QuestionScoringAuthority,
    policy: QuestionScoringPolicy,
) -> QuestionScoringAuthority:
    return QuestionScoringAuthority(
        rubric=authority.rubric,
        policy=policy,
    )


def stage_by_name(
    result: QuestionScoreResult,
    stage: ScoreStage,
) -> ScoreStageEffect:
    return next(effect for effect in result.stage_effects if effect.stage is stage)


def _assert_no_mutable_container_reachable(value: object) -> None:
    if isinstance(value, (list, dict, set, bytearray)):
        pytest.fail(
            f"Mutable container {type(value).__name__} is reachable from result."
        )

    if value is None or isinstance(
        value,
        (str, int, bool, Enum, ScoringDecimal),
    ):
        return

    if isinstance(value, tuple):
        for item in value:
            _assert_no_mutable_container_reachable(item)
        return

    if is_dataclass(value):
        for field in fields(value):
            _assert_no_mutable_container_reachable(getattr(value, field.name))
        return

    pytest.fail(f"Unexpected reachable result type: {type(value).__name__}.")


def test_full_pipeline_replay_and_judgment_permutation_are_identical() -> None:
    authority = full_authority()
    judgments = full_judgments()

    expected = reduce_question(authority, judgments)

    assert reduce_question(authority, judgments) == expected
    assert reduce_question(authority, tuple(reversed(judgments))) == expected


def test_dependency_rule_tuple_permutation_is_identical() -> None:
    authority = full_authority()
    reversed_policy = replace(
        authority.policy,
        positive_credit_dependencies=tuple(
            reversed(authority.policy.positive_credit_dependencies)
        ),
    )

    assert reduce_question(
        authority_with_policy(authority, reversed_policy),
        full_judgments(),
    ) == reduce_question(authority, full_judgments())


def test_gate_cap_and_deduction_tuple_permutations_are_identical() -> None:
    authority = full_authority()
    reversed_policy = replace(
        authority.policy,
        gates=tuple(reversed(authority.policy.gates)),
        caps=tuple(reversed(authority.policy.caps)),
        deductions=tuple(reversed(authority.policy.deductions)),
    )

    assert reduce_question(
        authority_with_policy(authority, reversed_policy),
        full_judgments(),
    ) == reduce_question(authority, full_judgments())


def test_provenance_is_referentially_complete_and_stage_chain_is_consistent() -> None:
    authority = full_authority()
    result = reduce_question(authority, full_judgments())

    assert result.question_id == authority.rubric.question_id
    assert result.rubric_ref == RubricRef(
        authority.rubric.rubric_id,
        authority.rubric.version,
    )
    assert result.scoring_policy_ref == ScoringPolicyRef(
        authority.policy.policy_id,
        authority.policy.version,
        authority.policy.scoring_semantics_version,
    )
    assert result.numeric_profile_version == NUMERIC_PROFILE_VERSION

    decisions = {decision.rule_id: decision for decision in result.rule_decisions}
    assert tuple(decision.rule_id for decision in result.rule_decisions) == tuple(
        sorted(decisions)
    )

    configured = {
        "DEP-A-C": (RuleType.DEPENDENCY, True, None),
        "DEP-B-C": (RuleType.DEPENDENCY, True, None),
        "DEP-S-T": (RuleType.DEPENDENCY, False, None),
        "G-7": (RuleType.GATE, True, sd("7")),
        "G-8": (RuleType.GATE, True, sd("8")),
        "G-PASS": (RuleType.GATE, False, sd("9")),
        "C-5": (RuleType.CAP, True, sd("5")),
        "C-6": (RuleType.CAP, True, sd("6")),
        "C-OFF": (RuleType.CAP, False, sd("4")),
        "D-025": (RuleType.DEDUCTION, True, sd("0.25")),
        "D-050": (RuleType.DEDUCTION, True, sd("0.5")),
        "D-OFF": (RuleType.DEDUCTION, False, sd("0.1")),
    }
    assert set(decisions) == set(configured)
    for rule_id, (rule_type, triggered, configured_effect) in configured.items():
        decision = decisions[rule_id]
        assert decision.rule_type is rule_type
        assert decision.triggered is triggered
        assert decision.configured_effect == configured_effect

    assert all(decision.rule_id != "ROUND" for decision in result.rule_decisions)

    effects = {effect.criterion_id: effect for effect in result.criterion_effects}
    assert effects["A"].blocking_dependency_rule_ids == ("DEP-A-C",)
    assert effects["B"].blocking_dependency_rule_ids == ("DEP-B-C",)

    gates = stage_by_name(result, ScoreStage.GATES)
    caps = stage_by_name(result, ScoreStage.CAPS)
    deductions = stage_by_name(result, ScoreStage.DEDUCTIONS)
    rounding_effect = stage_by_name(result, ScoreStage.ROUNDING)

    assert gates.source_rule_ids == ("G-7", "G-8")
    assert caps.source_rule_ids == ("C-5", "C-6")
    assert deductions.source_rule_ids == ("D-025", "D-050")
    assert rounding_effect.source_rule_ids == ("ROUND",)

    assert result.base_subtotal == gates.before
    assert gates.after == caps.before
    assert caps.after == deductions.before
    assert deductions.after == rounding_effect.before
    assert result.score_before_rounding == deductions.after
    assert result.final_score == rounding_effect.after


def test_reducer_returned_result_graph_is_deeply_immutable() -> None:
    result = reduce_question(full_authority(), full_judgments())

    _assert_no_mutable_container_reachable(result)

    with pytest.raises(FrozenInstanceError):
        result.final_score = sd("0")
    with pytest.raises(FrozenInstanceError):
        result.rubric_ref.id = "other"
    with pytest.raises(FrozenInstanceError):
        result.criterion_effects[0].selected_level = "ZERO"
    with pytest.raises(AttributeError):
        result.criterion_effects.append(None)
    with pytest.raises(AttributeError):
        result.rule_decisions.append(None)
    with pytest.raises(AttributeError):
        result.stage_effects.append(None)


@pytest.mark.parametrize(
    ("factory", "mutable_alias", "attribute"),
    (
        (
            lambda alias: CriterionEffect(
                criterion_id="C1",
                selected_level="FULL",
                base_contribution=sd("1"),
                effective_contribution=sd("1"),
                blocking_dependency_rule_ids=alias,  # type: ignore[arg-type]
            ),
            ["DEP-1"],
            "blocking_dependency_rule_ids",
        ),
        (
            lambda alias: ScoreStageEffect(
                stage=ScoreStage.GATES,
                before=sd("1"),
                after=sd("1"),
                source_rule_ids=alias,  # type: ignore[arg-type]
            ),
            ["G-1"],
            "source_rule_ids",
        ),
        (
            lambda alias: QuestionScoreResult(
                question_id="Q1",
                rubric_ref=RubricRef("R1", 1),
                scoring_policy_ref=ScoringPolicyRef("P1", 1, "1"),
                numeric_profile_version=NUMERIC_PROFILE_VERSION,
                criterion_effects=alias,  # type: ignore[arg-type]
                rule_decisions=(),
                stage_effects=(),
                base_subtotal=sd("0"),
                score_before_rounding=sd("0"),
                final_score=sd("0"),
                minimum_score=sd("0"),
                maximum_score=sd("1"),
            ),
            [],
            "criterion_effects",
        ),
        (
            lambda alias: QuestionScoreResult(
                question_id="Q1",
                rubric_ref=RubricRef("R1", 1),
                scoring_policy_ref=ScoringPolicyRef("P1", 1, "1"),
                numeric_profile_version=NUMERIC_PROFILE_VERSION,
                criterion_effects=(),
                rule_decisions=alias,  # type: ignore[arg-type]
                stage_effects=(),
                base_subtotal=sd("0"),
                score_before_rounding=sd("0"),
                final_score=sd("0"),
                minimum_score=sd("0"),
                maximum_score=sd("1"),
            ),
            [],
            "rule_decisions",
        ),
        (
            lambda alias: QuestionScoreResult(
                question_id="Q1",
                rubric_ref=RubricRef("R1", 1),
                scoring_policy_ref=ScoringPolicyRef("P1", 1, "1"),
                numeric_profile_version=NUMERIC_PROFILE_VERSION,
                criterion_effects=(),
                rule_decisions=(),
                stage_effects=alias,  # type: ignore[arg-type]
                base_subtotal=sd("0"),
                score_before_rounding=sd("0"),
                final_score=sd("0"),
                minimum_score=sd("0"),
                maximum_score=sd("1"),
            ),
            [],
            "stage_effects",
        ),
    ),
)
def test_result_contract_does_not_retain_mutable_collection_aliases(
    factory,
    mutable_alias: list[object],
    attribute: str,
) -> None:
    try:
        result = factory(mutable_alias)
    except (TypeError, ValueError, ScoringError):
        return

    marker = object()
    mutable_alias.append(marker)

    stored = getattr(result, attribute)
    assert not isinstance(stored, list)
    assert marker not in stored


def test_success_and_failure_do_not_mutate_inputs() -> None:
    authority = full_authority()
    judgments = full_judgments()
    authority_before = copy.deepcopy(authority)
    judgments_before = copy.deepcopy(judgments)

    reduce_question(authority, judgments)
    assert authority == authority_before
    assert judgments == judgments_before

    with pytest.raises(MissingJudgmentError):
        reduce_question(authority, judgments[:-1])

    assert authority == authority_before
    assert judgments == judgments_before

    maximum = sd("1")
    range_authority = QuestionScoringAuthority(
        rubric=CompiledQuestionRubric(
            rubric_id="range-rubric",
            version=1,
            question_id="Q-RANGE",
            max_marks=maximum,
            criteria=(criterion("C1", ("HIGH", "2")),),
        ),
        policy=QuestionScoringPolicy(
            policy_id="range-policy",
            version=1,
            question_id="Q-RANGE",
            scoring_semantics_version=SCORING_SEMANTICS_V1,
            minimum_score=sd("0"),
            maximum_score=maximum,
        ),
    )
    range_judgments = (CriterionJudgment("C1", "HIGH"),)
    range_authority_before = copy.deepcopy(range_authority)
    range_judgments_before = copy.deepcopy(range_judgments)

    with pytest.raises(ScoreOutOfRangeError):
        reduce_question(range_authority, range_judgments)

    assert range_authority == range_authority_before
    assert range_judgments == range_judgments_before


def test_unexpected_internal_exception_is_transparent(monkeypatch) -> None:
    authority = full_authority()
    judgments = full_judgments()

    def boom(_values):
        raise RuntimeError("synthetic internal defect")

    monkeypatch.setattr(reducer_module, "exact_sum", boom)

    with pytest.raises(RuntimeError, match="synthetic internal defect"):
        reduce_question(authority, judgments)


def test_base_subtotal_exact_sum_exception_cannot_be_swallowed(
    monkeypatch,
) -> None:
    maximum = sd("1")

    authority = QuestionScoringAuthority(
        rubric=CompiledQuestionRubric(
            rubric_id="exception-rubric",
            version=1,
            question_id="Q-EXCEPTION",
            max_marks=maximum,
            criteria=(
                criterion(
                    "C1",
                    ("FULL", "1"),
                    ("ZERO", "0"),
                ),
            ),
        ),
        policy=QuestionScoringPolicy(
            policy_id="exception-policy",
            version=1,
            question_id="Q-EXCEPTION",
            scoring_semantics_version=SCORING_SEMANTICS_V1,
            minimum_score=sd("0"),
            maximum_score=maximum,
        ),
    )

    judgments = (
        CriterionJudgment("C1", "FULL"),
    )

    calls = 0

    def boom(_values):
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic base subtotal defect")

    monkeypatch.setattr(reducer_module, "exact_sum", boom)

    with pytest.raises(
        RuntimeError,
        match="synthetic base subtotal defect",
    ):
        reduce_question(authority, judgments)

    assert calls == 1


def test_hostile_decimal_context_does_not_change_result_or_context() -> None:
    authority = full_authority()
    judgments = full_judgments()
    expected = reduce_question(authority, judgments)

    with localcontext() as context:
        context.prec = 1
        context.Emin = -2
        context.Emax = 2
        context.rounding = ROUND_CEILING

        before = (
            context.prec,
            context.Emin,
            context.Emax,
            context.rounding,
            context.capitals,
            context.clamp,
            dict(context.flags),
            dict(context.traps),
        )

        actual = reduce_question(authority, judgments)

        after = (
            context.prec,
            context.Emin,
            context.Emax,
            context.rounding,
            context.capitals,
            context.clamp,
            dict(context.flags),
            dict(context.traps),
        )

    assert actual == expected
    assert after == before


def test_reducer_source_has_no_forbidden_external_authority_or_arithmetic() -> None:
    tree = ast.parse(inspect.getsource(reducer_module))
    forbidden_import_roots = {
        "os",
        "time",
        "random",
        "socket",
        "subprocess",
        "pathlib",
        "requests",
        "urllib",
        "http",
        "sqlite3",
    }
    forbidden_calls = {"float", "round", "sum", "min", "max", "Decimal", "open"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_import_roots
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in forbidden_import_roots
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls


def test_unrelated_external_numeric_environment_values_have_no_authority(
    monkeypatch,
) -> None:
    authority = full_authority()
    judgments = full_judgments()
    expected = reduce_question(authority, judgments)

    monkeypatch.setenv("GRADIFIED_SCORE_OVERRIDE", "999999")
    monkeypatch.setenv("GRADIFIED_MARKS_AWARDED", "-123")
    monkeypatch.setenv("GRADIFIED_CONFIDENCE_AS_MARKS", "88")

    assert reduce_question(authority, judgments) == expected


def _authority_with_only_conditional_rules(
    *,
    dependencies: tuple[PositiveCreditDependencyRule, ...] = (),
    gates: tuple[GateRule, ...] = (),
    caps: tuple[CapRule, ...] = (),
    deductions: tuple[DeductionRule, ...] = (),
) -> QuestionScoringAuthority:
    base = full_authority()
    policy = replace(
        base.policy,
        positive_credit_dependencies=dependencies,
        gates=gates,
        caps=caps,
        deductions=deductions,
        rounding=None,
    )
    return authority_with_policy(base, policy)


def _force_rule_decision_triggered(
    monkeypatch,
    forced_triggered: bool,
) -> list[RuleDecision]:
    constructed: list[RuleDecision] = []

    def controlled_rule_decision(
        *,
        rule_id: str,
        rule_type: RuleType,
        triggered: bool,
        configured_effect: ScoringDecimal | None,
    ) -> RuleDecision:
        del triggered

        decision = RuleDecision(
            rule_id=rule_id,
            rule_type=rule_type,
            triggered=forced_triggered,
            configured_effect=configured_effect,
        )
        constructed.append(decision)
        return decision

    monkeypatch.setattr(
        reducer_module,
        "RuleDecision",
        controlled_rule_decision,
    )
    return constructed


def _force_rule_decision_effect(
    monkeypatch,
    forced_effect: ScoringDecimal,
) -> list[RuleDecision]:
    constructed: list[RuleDecision] = []

    def controlled_rule_decision(
        *,
        rule_id: str,
        rule_type: RuleType,
        triggered: bool,
        configured_effect: ScoringDecimal | None,
    ) -> RuleDecision:
        del configured_effect

        decision = RuleDecision(
            rule_id=rule_id,
            rule_type=rule_type,
            triggered=triggered,
            configured_effect=forced_effect,
        )
        constructed.append(decision)
        return decision

    monkeypatch.setattr(
        reducer_module,
        "RuleDecision",
        controlled_rule_decision,
    )
    return constructed


def _force_rule_decision_rule_id(
    monkeypatch,
    forced_rule_id: str,
) -> list[RuleDecision]:
    constructed: list[RuleDecision] = []

    def controlled_rule_decision(
        *,
        rule_id: str,
        rule_type: RuleType,
        triggered: bool,
        configured_effect: ScoringDecimal | None,
    ) -> RuleDecision:
        del rule_id

        decision = RuleDecision(
            rule_id=forced_rule_id,
            rule_type=rule_type,
            triggered=triggered,
            configured_effect=configured_effect,
        )
        constructed.append(decision)
        return decision

    monkeypatch.setattr(
        reducer_module,
        "RuleDecision",
        controlled_rule_decision,
    )
    return constructed


def test_dependency_application_consumes_rule_decision_triggered(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        dependencies=(
            dependency(
                "DEP-RAW",
                "B",
                condition("T", "YES"),
            ),
        ),
    )
    constructed = _force_rule_decision_triggered(
        monkeypatch,
        True,
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    target_effect = next(
        effect
        for effect in result.criterion_effects
        if effect.criterion_id == "B"
    )

    assert len(constructed) == 1
    assert target_effect.effective_contribution == sd("0")
    assert result.final_score == sd("9")


def test_dependency_application_consumes_rule_decision_rule_id(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        dependencies=(
            dependency(
                "DEP-RAW",
                "B",
                condition("C", "FULL"),
            ),
        ),
    )
    constructed = _force_rule_decision_rule_id(
        monkeypatch,
        "DEP-CONTROLLED",
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    target_effect = next(
        effect
        for effect in result.criterion_effects
        if effect.criterion_id == "B"
    )

    assert len(constructed) == 1
    assert target_effect.effective_contribution == sd("0")
    assert target_effect.blocking_dependency_rule_ids == (
        "DEP-CONTROLLED",
    )


def test_gate_application_consumes_rule_decision_triggered(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        gates=(
            gate(
                "G-RAW",
                "6",
                condition("T", "YES"),
            ),
        ),
    )
    constructed = _force_rule_decision_triggered(
        monkeypatch,
        True,
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    gate_effect = stage_by_name(
        result,
        ScoreStage.GATES,
    )

    assert len(constructed) == 1
    assert gate_effect.after == sd("6")
    assert result.final_score == sd("6")


def test_gate_application_consumes_rule_decision_configured_effect(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        gates=(
            gate(
                "G-RAW",
                "8",
                condition("G", "FULL"),
            ),
        ),
    )
    constructed = _force_rule_decision_effect(
        monkeypatch,
        sd("6"),
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    gate_effect = stage_by_name(
        result,
        ScoreStage.GATES,
    )

    assert len(constructed) == 1
    assert gate_effect.after == sd("6")
    assert result.final_score == sd("6")


def test_gate_application_consumes_rule_decision_rule_id(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        gates=(
            gate(
                "G-RAW",
                "8",
                condition("G", "FULL"),
            ),
        ),
    )
    constructed = _force_rule_decision_rule_id(
        monkeypatch,
        "G-CONTROLLED",
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    gate_effect = stage_by_name(
        result,
        ScoreStage.GATES,
    )

    assert len(constructed) == 1
    assert gate_effect.after == sd("8")
    assert gate_effect.source_rule_ids == (
        "G-CONTROLLED",
    )


def test_cap_application_consumes_rule_decision_triggered(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        caps=(
            cap(
                "C-RAW",
                "6",
                condition("G", "FULL"),
            ),
        ),
    )
    constructed = _force_rule_decision_triggered(
        monkeypatch,
        True,
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    cap_effect = stage_by_name(
        result,
        ScoreStage.CAPS,
    )

    assert len(constructed) == 1
    assert cap_effect.after == sd("6")
    assert result.final_score == sd("6")


def test_cap_application_consumes_rule_decision_configured_effect(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        caps=(
            cap(
                "C-RAW",
                "8",
                condition("T", "YES"),
            ),
        ),
    )
    constructed = _force_rule_decision_effect(
        monkeypatch,
        sd("6"),
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    cap_effect = stage_by_name(
        result,
        ScoreStage.CAPS,
    )

    assert len(constructed) == 1
    assert cap_effect.after == sd("6")
    assert result.final_score == sd("6")


def test_cap_application_consumes_rule_decision_rule_id(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        caps=(
            cap(
                "C-RAW",
                "8",
                condition("T", "YES"),
            ),
        ),
    )
    constructed = _force_rule_decision_rule_id(
        monkeypatch,
        "C-CONTROLLED",
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    cap_effect = stage_by_name(
        result,
        ScoreStage.CAPS,
    )

    assert len(constructed) == 1
    assert cap_effect.after == sd("8")
    assert cap_effect.source_rule_ids == (
        "C-CONTROLLED",
    )


def test_deduction_application_consumes_rule_decision_triggered(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        deductions=(
            deduction(
                "D-RAW",
                "1",
                condition("G", "FULL"),
            ),
        ),
    )
    constructed = _force_rule_decision_triggered(
        monkeypatch,
        True,
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    deduction_effect = stage_by_name(
        result,
        ScoreStage.DEDUCTIONS,
    )

    assert len(constructed) == 1
    assert deduction_effect.after == sd("9")
    assert result.score_before_rounding == sd("9")
    assert result.final_score == sd("9")


def test_deduction_application_consumes_rule_decision_configured_effect(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        deductions=(
            deduction(
                "D-RAW",
                "1",
                condition("T", "YES"),
            ),
        ),
    )
    constructed = _force_rule_decision_effect(
        monkeypatch,
        sd("2"),
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    deduction_effect = stage_by_name(
        result,
        ScoreStage.DEDUCTIONS,
    )

    assert len(constructed) == 1
    assert deduction_effect.after == sd("8")
    assert result.score_before_rounding == sd("8")
    assert result.final_score == sd("8")


def test_deduction_application_consumes_rule_decision_rule_id(
    monkeypatch,
) -> None:
    authority = _authority_with_only_conditional_rules(
        deductions=(
            deduction(
                "D-RAW",
                "1",
                condition("T", "YES"),
            ),
        ),
    )
    constructed = _force_rule_decision_rule_id(
        monkeypatch,
        "D-CONTROLLED",
    )

    result = reduce_question(
        authority,
        full_judgments(),
    )
    deduction_effect = stage_by_name(
        result,
        ScoreStage.DEDUCTIONS,
    )

    assert len(constructed) == 1
    assert deduction_effect.after == sd("9")
    assert deduction_effect.source_rule_ids == (
        "D-CONTROLLED",
    )


def test_each_conditional_rule_predicate_is_evaluated_once(monkeypatch) -> None:
    authority = full_authority()
    judgments = full_judgments()
    original = reducer_module._conditions_satisfied
    calls: list[tuple[CriterionCondition, ...]] = []

    def counted(
        conditions: tuple[CriterionCondition, ...],
        selected_levels,
    ) -> bool:
        calls.append(conditions)
        with pytest.raises(TypeError):
            selected_levels["S"] = "ZERO"  # type: ignore[index]
        return original(conditions, selected_levels)

    monkeypatch.setattr(reducer_module, "_conditions_satisfied", counted)

    reduce_question(authority, judgments)

    expected_count = (
        len(authority.policy.positive_credit_dependencies)
        + len(authority.policy.gates)
        + len(authority.policy.caps)
        + len(authority.policy.deductions)
    )
    assert len(calls) == expected_count


def test_configured_rounding_transformation_is_invoked_once(monkeypatch) -> None:
    authority = full_authority()
    judgments = full_judgments()
    original = reducer_module._round_to_increment
    calls = 0

    def counted(value: ScoringDecimal, rule: RoundingRule) -> ScoringDecimal:
        nonlocal calls
        calls += 1
        return original(value, rule)

    monkeypatch.setattr(reducer_module, "_round_to_increment", counted)

    reduce_question(authority, judgments)

    assert calls == 1
