from itertools import combinations

import pytest

from grading.contracts.errors import (
    InvalidRuleError,
    InvalidScoringAuthorityError,
    UnsupportedScoringSemanticsError,
)
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
from grading.contracts.scoring_decimal import ScoringDecimal


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def condition(criterion_id: str = "C1", *levels: str) -> CriterionCondition:
    return CriterionCondition(criterion_id, levels or ("FULL",))


def base_policy(**overrides: object) -> QuestionScoringPolicy:
    values: dict[str, object] = {
        "policy_id": "P1",
        "version": 1,
        "question_id": "Q1",
        "scoring_semantics_version": SCORING_SEMANTICS_V1,
        "minimum_score": sd(0),
        "maximum_score": sd(5),
    }
    values.update(overrides)
    return QuestionScoringPolicy(**values)  # type: ignore[arg-type]


def test_policy_rejects_minimum_above_maximum() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        base_policy(minimum_score=sd(6), maximum_score=sd(5))


@pytest.mark.parametrize("invalid_version", [True, 0, -1, 1.5, "1"])
def test_policy_rejects_invalid_version(invalid_version: object) -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        base_policy(version=invalid_version)


@pytest.mark.parametrize("invalid_question_id", ["", " Q1", "Q1 ", 1, None])
def test_policy_rejects_invalid_question_id(invalid_question_id: object) -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        base_policy(question_id=invalid_question_id)


def test_policy_rejects_unsupported_semantics_version() -> None:
    with pytest.raises(UnsupportedScoringSemanticsError):
        base_policy(scoring_semantics_version="2")


def test_policy_rejects_non_string_semantics_version() -> None:
    with pytest.raises(UnsupportedScoringSemanticsError):
        base_policy(scoring_semantics_version=1)


def test_policy_rejects_mutable_rule_collections() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        base_policy(positive_credit_dependencies=[])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "invalid_criterion_id",
    ["", " C1", "C1 ", 1, None],
)
def test_criterion_condition_rejects_invalid_criterion_id(
    invalid_criterion_id: object,
) -> None:
    with pytest.raises(InvalidRuleError):
        CriterionCondition(
            invalid_criterion_id,  # type: ignore[arg-type]
            ("FULL",),
        )


def test_criterion_condition_rejects_duplicate_levels() -> None:
    with pytest.raises(InvalidRuleError):
        CriterionCondition("C1", ("FULL", "FULL"))


@pytest.mark.parametrize(
    "bad_levels",
    [(), ["FULL"], ("",), (" FULL",), (1,)],
)
def test_criterion_condition_rejects_malformed_allowed_levels(
    bad_levels: object,
) -> None:
    with pytest.raises(InvalidRuleError):
        CriterionCondition("C1", bad_levels)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda conditions: PositiveCreditDependencyRule("RULE-1", "C2", conditions),
        lambda conditions: GateRule("RULE-1", conditions, sd(4)),
        lambda conditions: CapRule("RULE-1", conditions, sd(4)),
        lambda conditions: DeductionRule("RULE-1", conditions, sd("0.25")),
    ],
)
@pytest.mark.parametrize("bad_conditions", [(), [], ("not-a-condition",)])
def test_each_condition_bearing_rule_rejects_malformed_condition_collection(
    factory: object,
    bad_conditions: object,
) -> None:
    with pytest.raises(InvalidRuleError):
        factory(bad_conditions)  # type: ignore[operator]


def test_rule_rejects_multiple_conditions_for_same_criterion() -> None:
    conditions = (condition("C1", "FULL"), condition("C1", "PARTIAL"))
    with pytest.raises(InvalidRuleError):
        CapRule("CAP-1", conditions, sd(4))


@pytest.mark.parametrize("invalid_rule_id", ["", " RULE-1", "RULE-1 ", 1, None])
def test_rule_id_is_strict(invalid_rule_id: object) -> None:
    with pytest.raises(InvalidRuleError):
        CapRule(
            invalid_rule_id,  # type: ignore[arg-type]
            (condition(),),
            sd(4),
        )


@pytest.mark.parametrize("invalid_target", ["", " C2", "C2 ", 1, None])
def test_dependency_target_criterion_id_is_strict(invalid_target: object) -> None:
    with pytest.raises(InvalidRuleError):
        PositiveCreditDependencyRule(
            "DEP-1",
            invalid_target,  # type: ignore[arg-type]
            (condition(),),
        )


def test_deduction_amount_must_be_strictly_positive() -> None:
    for invalid in ("0", "-0.25"):
        with pytest.raises(InvalidRuleError):
            DeductionRule("DED-1", (condition(),), sd(invalid))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: GateRule("GATE-1", (condition(),), "4"),
        lambda: CapRule("CAP-1", (condition(),), "4"),
    ],
)
def test_gate_and_cap_ceiling_must_be_scoring_decimal(factory: object) -> None:
    with pytest.raises(InvalidRuleError):
        factory()  # type: ignore[operator]


def test_rounding_increment_must_be_strictly_positive() -> None:
    with pytest.raises(InvalidRuleError):
        RoundingRule("ROUND-1", sd(0), RoundingMode.HALF_UP)


def test_rounding_mode_must_be_explicit_enum() -> None:
    with pytest.raises(InvalidRuleError):
        RoundingRule("ROUND-1", sd("0.25"), "HALF_UP")  # type: ignore[arg-type]


def _rule_variant(kind: str, rule_id: str) -> object:
    if kind == "dependency":
        return PositiveCreditDependencyRule(rule_id, "C2", (condition(),))
    if kind == "gate":
        return GateRule(rule_id, (condition(),), sd(4))
    if kind == "cap":
        return CapRule(rule_id, (condition(),), sd(4))
    if kind == "deduction":
        return DeductionRule(rule_id, (condition(),), sd("0.25"))
    if kind == "rounding":
        return RoundingRule(rule_id, sd("0.5"), RoundingMode.HALF_EVEN)
    raise AssertionError(f"unknown test rule kind: {kind}")


def _policy_kwargs_for_rules(*items: tuple[str, object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    for kind, rule in items:
        if kind == "dependency":
            kwargs["positive_credit_dependencies"] = (rule,)
        elif kind == "gate":
            kwargs["gates"] = (rule,)
        elif kind == "cap":
            kwargs["caps"] = (rule,)
        elif kind == "deduction":
            kwargs["deductions"] = (rule,)
        elif kind == "rounding":
            kwargs["rounding"] = rule
        else:
            raise AssertionError(f"unknown test rule kind: {kind}")
    return kwargs


@pytest.mark.parametrize(
    ("left_kind", "right_kind"),
    list(combinations(("dependency", "gate", "cap", "deduction", "rounding"), 2)),
)
def test_duplicate_rule_id_is_rejected_across_every_rule_type_pair(
    left_kind: str,
    right_kind: str,
) -> None:
    shared_id = "RULE-1"
    kwargs = _policy_kwargs_for_rules(
        (left_kind, _rule_variant(left_kind, shared_id)),
        (right_kind, _rule_variant(right_kind, shared_id)),
    )

    with pytest.raises(InvalidRuleError):
        base_policy(**kwargs)


def test_gate_and_cap_ceilings_must_be_inside_permitted_range() -> None:
    gate = GateRule("GATE-1", (condition(),), sd(-1))
    with pytest.raises(InvalidRuleError):
        base_policy(gates=(gate,))

    cap = CapRule("CAP-1", (condition(),), sd(6))
    with pytest.raises(InvalidRuleError):
        base_policy(caps=(cap,))


def test_negative_ceiling_is_valid_when_policy_range_allows_it() -> None:
    cap = CapRule("CAP-1", (condition(),), sd("-0.25"))
    policy = base_policy(minimum_score=sd(-1), maximum_score=sd(5), caps=(cap,))
    assert policy.caps == (cap,)


def test_same_rule_id_may_be_reused_in_a_different_question_policy() -> None:
    first = base_policy(caps=(CapRule("CAP-1", (condition(),), sd(4)),))
    second = QuestionScoringPolicy(
        policy_id="P2",
        version=1,
        question_id="Q2",
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=sd(0),
        maximum_score=sd(5),
        caps=(CapRule("CAP-1", (condition(),), sd(4)),),
    )

    assert first.caps[0].rule_id == second.caps[0].rule_id == "CAP-1"
