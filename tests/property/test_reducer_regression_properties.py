from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from itertools import chain

import pytest
from hypothesis import given, settings, strategies as st

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
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.reducer import reduce_question


_LEVEL_IDS = ("FULL", "PARTIAL", "ZERO", "NEGATIVE")
_ALLOWED_LEVEL_SETS = (
    ("FULL",),
    ("PARTIAL",),
    ("ZERO",),
    ("NEGATIVE",),
    ("FULL", "PARTIAL"),
    ("ZERO", "NEGATIVE"),
)
_POSITIVE_VALUES = ("0.25", "0.5", "0.75", "1", "1.25", "1.5", "2", "2.5", "3")
_NEGATIVE_VALUES = ("-0.25", "-0.5", "-0.75", "-1")
_CEILINGS = ("-2", "-1", "0", "0.5", "1", "2", "3")
_DEDUCTIONS = ("0.25", "0.5", "0.75", "1", "1.25", "1.5", "2")
_INCREMENTS = ("0.25", "0.5", "1")


def sd(raw: str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def as_fraction(value: ScoringDecimal) -> Fraction:
    """Convert the admitted exact decimal to the oracle's independent number type."""

    return Fraction(value.to_canonical_string())


def criterion(
    criterion_id: str,
    full: str,
    partial: str,
    negative: str,
) -> AtomicCriterion:
    return AtomicCriterion(
        criterion_id=criterion_id,
        operational_description=f"Assess {criterion_id}.",
        performance_levels=(
            PerformanceLevel("FULL", sd(full)),
            PerformanceLevel("PARTIAL", sd(partial)),
            PerformanceLevel("ZERO", sd("0")),
            PerformanceLevel("NEGATIVE", sd(negative)),
        ),
    )


def condition(criterion_id: str, allowed: tuple[str, ...]) -> CriterionCondition:
    return CriterionCondition(
        criterion_id=criterion_id,
        allowed_level_ids=allowed,
    )


def oracle_conditions_satisfied(
    conditions: tuple[CriterionCondition, ...],
    original_levels: dict[str, str],
) -> bool:
    """Independent AND-across-conditions / membership-within-condition semantics."""

    for configured_condition in conditions:
        selected = original_levels[configured_condition.criterion_id]
        if selected not in configured_condition.allowed_level_ids:
            return False
    return True


def oracle_round(
    value: Fraction,
    increment: Fraction,
    mode: RoundingMode,
) -> Fraction:
    """Round a Fraction to the nearest increment without production helpers."""

    ratio = value / increment
    sign = -1 if ratio < 0 else 1
    magnitude = abs(ratio)
    lower = magnitude.numerator // magnitude.denominator
    fraction = magnitude - lower
    half = Fraction(1, 2)

    if fraction < half:
        multiple = lower
    elif fraction > half:
        multiple = lower + 1
    elif mode is RoundingMode.HALF_UP:
        multiple = lower + 1
    elif mode is RoundingMode.HALF_EVEN:
        multiple = lower if lower % 2 == 0 else lower + 1
    else:
        raise AssertionError("Oracle received unsupported rounding mode.")

    return sign * multiple * increment


def oracle_reduce(
    authority: QuestionScoringAuthority,
    judgments: tuple[CriterionJudgment, ...],
) -> tuple[Fraction, Fraction, Fraction]:
    """Independent mathematical score oracle; does not import reducer helpers."""

    original_levels = {
        judgment.criterion_id: judgment.selected_level
        for judgment in judgments
    }

    effective_contributions: list[Fraction] = []
    for rubric_criterion in authority.rubric.criteria:
        selected_level = original_levels[rubric_criterion.criterion_id]
        performance_level = next(
            level
            for level in rubric_criterion.performance_levels
            if level.level_id == selected_level
        )
        base = as_fraction(performance_level.contribution)

        failed_dependency_exists = any(
            dependency.target_criterion_id == rubric_criterion.criterion_id
            and not oracle_conditions_satisfied(
                dependency.prerequisite_conditions,
                original_levels,
            )
            for dependency in authority.policy.positive_credit_dependencies
        )

        if failed_dependency_exists and base > 0:
            effective_contributions.append(Fraction(0))
        else:
            effective_contributions.append(base)

    base_subtotal = sum(effective_contributions, Fraction(0))

    triggered_gate_ceilings = (
        as_fraction(rule.failure_ceiling)
        for rule in authority.policy.gates
        if not oracle_conditions_satisfied(rule.required_conditions, original_levels)
    )
    after_gates = min(chain((base_subtotal,), triggered_gate_ceilings))

    triggered_cap_ceilings = (
        as_fraction(rule.ceiling)
        for rule in authority.policy.caps
        if oracle_conditions_satisfied(rule.trigger_conditions, original_levels)
    )
    after_caps = min(chain((after_gates,), triggered_cap_ceilings))

    deduction_total = sum(
        (
            as_fraction(rule.amount)
            for rule in authority.policy.deductions
            if oracle_conditions_satisfied(rule.trigger_conditions, original_levels)
        ),
        Fraction(0),
    )
    score_before_rounding = after_caps - deduction_total

    if authority.policy.rounding is None:
        final_score = score_before_rounding
    else:
        final_score = oracle_round(
            score_before_rounding,
            as_fraction(authority.policy.rounding.increment),
            authority.policy.rounding.mode,
        )

    return base_subtotal, score_before_rounding, final_score


def maybe_conditions(
    primary_id: str,
    primary_allowed: tuple[str, ...],
    include_secondary: bool,
    secondary_id: str,
    secondary_allowed: tuple[str, ...],
) -> tuple[CriterionCondition, ...]:
    values = [condition(primary_id, primary_allowed)]
    if include_secondary:
        values.append(condition(secondary_id, secondary_allowed))
    return tuple(values)


@st.composite
def valid_cases(draw):
    criteria = tuple(
        criterion(
            f"C{index}",
            draw(st.sampled_from(_POSITIVE_VALUES)),
            draw(st.sampled_from(_POSITIVE_VALUES)),
            draw(st.sampled_from(_NEGATIVE_VALUES)),
        )
        for index in range(3)
    )

    judgments = tuple(
        CriterionJudgment(
            criterion_id=f"C{index}",
            selected_level=draw(st.sampled_from(_LEVEL_IDS)),
        )
        for index in range(3)
    )

    dependencies: list[PositiveCreditDependencyRule] = []
    if draw(st.booleans()):
        dependencies.append(
            PositiveCreditDependencyRule(
                rule_id="DEP-C1-C0",
                target_criterion_id="C1",
                prerequisite_conditions=(
                    condition("C0", draw(st.sampled_from(_ALLOWED_LEVEL_SETS))),
                ),
            )
        )
    if draw(st.booleans()):
        dependencies.append(
            PositiveCreditDependencyRule(
                rule_id="DEP-C2-PRE",
                target_criterion_id="C2",
                prerequisite_conditions=maybe_conditions(
                    "C0",
                    draw(st.sampled_from(_ALLOWED_LEVEL_SETS)),
                    draw(st.booleans()),
                    "C1",
                    draw(st.sampled_from(_ALLOWED_LEVEL_SETS)),
                ),
            )
        )

    gates: list[GateRule] = []
    for index, primary, secondary in ((0, "C0", "C1"), (1, "C2", "C0")):
        if draw(st.booleans()):
            gates.append(
                GateRule(
                    rule_id=f"G{index}",
                    required_conditions=maybe_conditions(
                        primary,
                        draw(st.sampled_from(_ALLOWED_LEVEL_SETS)),
                        draw(st.booleans()),
                        secondary,
                        draw(st.sampled_from(_ALLOWED_LEVEL_SETS)),
                    ),
                    failure_ceiling=sd(draw(st.sampled_from(_CEILINGS))),
                )
            )

    caps: list[CapRule] = []
    for index, primary, secondary in ((0, "C1", "C2"), (1, "C0", "C2")):
        if draw(st.booleans()):
            caps.append(
                CapRule(
                    rule_id=f"CAP{index}",
                    trigger_conditions=maybe_conditions(
                        primary,
                        draw(st.sampled_from(_ALLOWED_LEVEL_SETS)),
                        draw(st.booleans()),
                        secondary,
                        draw(st.sampled_from(_ALLOWED_LEVEL_SETS)),
                    ),
                    ceiling=sd(draw(st.sampled_from(_CEILINGS))),
                )
            )

    deductions: list[DeductionRule] = []
    for index, primary in ((0, "C0"), (1, "C2")):
        if draw(st.booleans()):
            deductions.append(
                DeductionRule(
                    rule_id=f"DED{index}",
                    trigger_conditions=(
                        condition(primary, draw(st.sampled_from(_ALLOWED_LEVEL_SETS))),
                    ),
                    amount=sd(draw(st.sampled_from(_DEDUCTIONS))),
                )
            )

    rounding_rule = None
    if draw(st.booleans()):
        rounding_rule = RoundingRule(
            rule_id="ROUND",
            increment=sd(draw(st.sampled_from(_INCREMENTS))),
            mode=draw(
                st.sampled_from(
                    (RoundingMode.HALF_UP, RoundingMode.HALF_EVEN)
                )
            ),
        )

    maximum = sd("3")
    rubric = CompiledQuestionRubric(
        rubric_id="R",
        version=1,
        question_id="Q",
        max_marks=maximum,
        criteria=criteria,
    )
    policy = QuestionScoringPolicy(
        policy_id="P",
        version=1,
        question_id="Q",
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=sd("-2"),
        maximum_score=maximum,
        positive_credit_dependencies=tuple(dependencies),
        gates=tuple(gates),
        caps=tuple(caps),
        deductions=tuple(deductions),
        rounding=rounding_rule,
    )

    return QuestionScoringAuthority(rubric=rubric, policy=policy), judgments


@st.composite
def guaranteed_success_cases(draw):
    authority, judgments = draw(valid_cases())

    minimum = sd("-10")
    maximum = sd("10")

    widened_rubric = replace(
        authority.rubric,
        max_marks=maximum,
    )
    widened_policy = replace(
        authority.policy,
        minimum_score=minimum,
        maximum_score=maximum,
    )

    return (
        QuestionScoringAuthority(
            rubric=widened_rubric,
            policy=widened_policy,
        ),
        judgments,
    )


@settings(max_examples=200, deadline=None)
@given(guaranteed_success_cases())
def test_reducer_agrees_with_oracle_on_guaranteed_success_paths(case) -> None:
    authority, judgments = case

    expected_base, expected_before_rounding, expected_final = oracle_reduce(
        authority,
        judgments,
    )

    result = reduce_question(authority, judgments)

    assert as_fraction(result.base_subtotal) == expected_base
    assert as_fraction(result.score_before_rounding) == expected_before_rounding
    assert as_fraction(result.final_score) == expected_final

    gates, caps, deductions, rounding = result.stage_effects

    assert as_fraction(gates.after) <= as_fraction(gates.before)
    assert as_fraction(caps.after) <= as_fraction(caps.before)
    assert as_fraction(deductions.after) <= as_fraction(deductions.before)

    assert result.base_subtotal == gates.before
    assert gates.after == caps.before
    assert caps.after == deductions.before
    assert deductions.after == rounding.before
    assert result.score_before_rounding == deductions.after
    assert rounding.after == result.final_score


@settings(max_examples=300, deadline=None)
@given(valid_cases())
def test_reducer_agrees_with_independent_fraction_oracle(case) -> None:
    authority, judgments = case
    expected_base, expected_before_rounding, expected_final = oracle_reduce(
        authority,
        judgments,
    )

    minimum = as_fraction(authority.policy.minimum_score)
    maximum = as_fraction(authority.policy.maximum_score)

    if expected_final < minimum or expected_final > maximum:
        with pytest.raises(ScoreOutOfRangeError):
            reduce_question(authority, judgments)
        return

    result = reduce_question(authority, judgments)

    assert as_fraction(result.base_subtotal) == expected_base
    assert as_fraction(result.score_before_rounding) == expected_before_rounding
    assert as_fraction(result.final_score) == expected_final
    assert minimum <= expected_final <= maximum

    gates, caps, deductions, rounding = result.stage_effects
    assert as_fraction(gates.after) <= as_fraction(gates.before)
    assert as_fraction(caps.after) <= as_fraction(caps.before)
    assert as_fraction(deductions.after) <= as_fraction(deductions.before)
    assert gates.after == caps.before
    assert caps.after == deductions.before
    assert deductions.after == rounding.before
    assert rounding.after == result.final_score

# ---------------------------------------------------------------------------
# Metamorphic properties
# ---------------------------------------------------------------------------


def outcome(
    authority: QuestionScoringAuthority,
    judgments: tuple[CriterionJudgment, ...],
):
    try:
        return ("RESULT", reduce_question(authority, judgments))
    except ScoreOutOfRangeError:
        return ("RANGE", None)


def reordered_authority(
    authority: QuestionScoringAuthority,
) -> QuestionScoringAuthority:
    policy = authority.policy
    reordered_policy = replace(
        policy,
        positive_credit_dependencies=tuple(
            reversed(policy.positive_credit_dependencies)
        ),
        gates=tuple(reversed(policy.gates)),
        caps=tuple(reversed(policy.caps)),
        deductions=tuple(reversed(policy.deductions)),
    )
    return QuestionScoringAuthority(
        rubric=authority.rubric,
        policy=reordered_policy,
    )


def reordered_authority_family(
    authority: QuestionScoringAuthority,
    family: str,
) -> QuestionScoringAuthority:
    policy = authority.policy

    reordered_policy = replace(
        policy,
        **{
            family: tuple(
                reversed(getattr(policy, family))
            )
        },
    )

    return QuestionScoringAuthority(
        rubric=authority.rubric,
        policy=reordered_policy,
    )


@settings(max_examples=200, deadline=None)
@given(valid_cases())
def test_reducer_replay_and_permutations_are_semantically_identical(case) -> None:
    authority, judgments = case

    original = outcome(authority, judgments)
    replay = outcome(authority, judgments)
    reversed_judgments = outcome(authority, tuple(reversed(judgments)))
    reversed_rules = outcome(reordered_authority(authority), judgments)

    assert replay == original
    assert reversed_judgments == original
    assert reversed_rules == original

    for family in (
        "positive_credit_dependencies",
        "gates",
        "caps",
        "deductions",
    ):
        independently_reordered = outcome(
            reordered_authority_family(
                authority,
                family,
            ),
            judgments,
        )
        assert independently_reordered == original


@pytest.mark.parametrize(
    ("left_raw", "right_raw"),
    (
        ("1.5", "1.5000"),
        ("0.25", ".2500"),
        ("2", "2.000"),
        ("-0.5", "-.5000"),
        ("0", "-0E+3"),
    ),
)
def test_equivalent_scoring_decimal_representations_produce_identical_results(
    left_raw: str,
    right_raw: str,
) -> None:
    left_value = ScoringDecimal.from_raw(left_raw)
    right_value = ScoringDecimal.from_raw(right_raw)
    maximum = sd("3")

    def make_authority(contribution: ScoringDecimal) -> QuestionScoringAuthority:
        rubric = CompiledQuestionRubric(
            rubric_id="R-EQUIV",
            version=1,
            question_id="Q-EQUIV",
            max_marks=maximum,
            criteria=(
                AtomicCriterion(
                    criterion_id="C0",
                    operational_description="Assess C0.",
                    performance_levels=(
                        PerformanceLevel("SELECTED", contribution),
                    ),
                ),
            ),
        )
        policy = QuestionScoringPolicy(
            policy_id="P-EQUIV",
            version=1,
            question_id="Q-EQUIV",
            scoring_semantics_version=SCORING_SEMANTICS_V1,
            minimum_score=sd("-2"),
            maximum_score=maximum,
        )
        return QuestionScoringAuthority(rubric=rubric, policy=policy)

    judgments = (CriterionJudgment("C0", "SELECTED"),)

    assert outcome(make_authority(left_value), judgments) == outcome(
        make_authority(right_value),
        judgments,
    )
