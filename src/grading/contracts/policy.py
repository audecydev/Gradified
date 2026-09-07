from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from grading.contracts.errors import (
    InvalidRuleError,
    InvalidScoringAuthorityError,
    UnsupportedScoringSemanticsError,
)
from grading.contracts.scoring_decimal import ScoringDecimal


SCORING_SEMANTICS_V1 = "1"


def _validate_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidScoringAuthorityError(
            f"{field_name} must be a non-empty string without surrounding whitespace."
        )
    return value


def _validate_rule_identifier(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidRuleError(
            "rule_id must be a non-empty string without surrounding whitespace."
        )
    return value


def _validate_version(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise InvalidScoringAuthorityError(
            f"{field_name} must be a positive integer."
        )
    return value


def _require_conditions(
    conditions: object,
    *,
    field_name: str,
) -> tuple[CriterionCondition, ...]:
    if type(conditions) is not tuple or not conditions:
        raise InvalidRuleError(f"{field_name} must be a non-empty tuple.")
    if any(type(condition) is not CriterionCondition for condition in conditions):
        raise InvalidRuleError(f"{field_name} contains an invalid condition.")

    # Scoring Semantics v1 uses one normal-form condition per criterion. OR
    # belongs inside allowed_level_ids; duplicate criterion conditions would be
    # redundant, contradictory, or reducible to one explicit condition.
    criterion_ids = tuple(condition.criterion_id for condition in conditions)
    if len(criterion_ids) != len(set(criterion_ids)):
        raise InvalidRuleError(
            f"{field_name} cannot contain multiple conditions for the same criterion."
        )
    return conditions


def _decimal_less(left: ScoringDecimal, right: ScoringDecimal) -> bool:
    return left.as_decimal() < right.as_decimal()


def _decimal_greater(left: ScoringDecimal, right: ScoringDecimal) -> bool:
    return left.as_decimal() > right.as_decimal()


@dataclass(frozen=True, slots=True)
class CriterionCondition:
    """Immutable predicate over an original criterion judgment."""

    criterion_id: str
    allowed_level_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.criterion_id) is not str
            or not self.criterion_id
            or self.criterion_id.strip() != self.criterion_id
        ):
            raise InvalidRuleError(
                "CriterionCondition.criterion_id must be a non-empty string "
                "without surrounding whitespace."
            )
        if type(self.allowed_level_ids) is not tuple or not self.allowed_level_ids:
            raise InvalidRuleError(
                "CriterionCondition.allowed_level_ids must be a non-empty tuple."
            )
        for level_id in self.allowed_level_ids:
            if type(level_id) is not str or not level_id or level_id.strip() != level_id:
                raise InvalidRuleError(
                    "CriterionCondition.allowed_level_ids contains an invalid level ID."
                )
        if len(self.allowed_level_ids) != len(set(self.allowed_level_ids)):
            raise InvalidRuleError(
                "CriterionCondition.allowed_level_ids cannot contain duplicates."
            )


@dataclass(frozen=True, slots=True)
class PositiveCreditDependencyRule:
    """Positive credit for a target criterion requires all prerequisites."""

    rule_id: str
    target_criterion_id: str
    prerequisite_conditions: tuple[CriterionCondition, ...]

    def __post_init__(self) -> None:
        _validate_rule_identifier(self.rule_id)
        if (
            type(self.target_criterion_id) is not str
            or not self.target_criterion_id
            or self.target_criterion_id.strip() != self.target_criterion_id
        ):
            raise InvalidRuleError(
                "target_criterion_id must be a non-empty string without surrounding whitespace."
            )
        _require_conditions(
            self.prerequisite_conditions,
            field_name="dependency prerequisite_conditions",
        )


@dataclass(frozen=True, slots=True)
class GateRule:
    """Essential requirement whose failure imposes a question-level ceiling."""

    rule_id: str
    required_conditions: tuple[CriterionCondition, ...]
    failure_ceiling: ScoringDecimal

    def __post_init__(self) -> None:
        _validate_rule_identifier(self.rule_id)
        _require_conditions(self.required_conditions, field_name="gate required_conditions")
        if type(self.failure_ceiling) is not ScoringDecimal:
            raise InvalidRuleError("GateRule.failure_ceiling must be a ScoringDecimal.")


@dataclass(frozen=True, slots=True)
class CapRule:
    """Conditional question-level maximum."""

    rule_id: str
    trigger_conditions: tuple[CriterionCondition, ...]
    ceiling: ScoringDecimal

    def __post_init__(self) -> None:
        _validate_rule_identifier(self.rule_id)
        _require_conditions(self.trigger_conditions, field_name="cap trigger_conditions")
        if type(self.ceiling) is not ScoringDecimal:
            raise InvalidRuleError("CapRule.ceiling must be a ScoringDecimal.")


@dataclass(frozen=True, slots=True)
class DeductionRule:
    """Conditional positive amount subtracted at question scope."""

    rule_id: str
    trigger_conditions: tuple[CriterionCondition, ...]
    amount: ScoringDecimal

    def __post_init__(self) -> None:
        _validate_rule_identifier(self.rule_id)
        _require_conditions(
            self.trigger_conditions,
            field_name="deduction trigger_conditions",
        )
        if type(self.amount) is not ScoringDecimal:
            raise InvalidRuleError("DeductionRule.amount must be a ScoringDecimal.")
        if self.amount.as_decimal() <= 0:
            raise InvalidRuleError("DeductionRule.amount must be strictly greater than zero.")


class RoundingMode(str, Enum):
    HALF_UP = "HALF_UP"
    HALF_EVEN = "HALF_EVEN"


@dataclass(frozen=True, slots=True)
class RoundingRule:
    """Explicit question-boundary rounding configuration."""

    rule_id: str
    increment: ScoringDecimal
    mode: RoundingMode

    def __post_init__(self) -> None:
        _validate_rule_identifier(self.rule_id)
        if type(self.increment) is not ScoringDecimal:
            raise InvalidRuleError("RoundingRule.increment must be a ScoringDecimal.")
        if self.increment.as_decimal() <= 0:
            raise InvalidRuleError("RoundingRule.increment must be strictly greater than zero.")
        if type(self.mode) is not RoundingMode:
            raise InvalidRuleError("RoundingRule.mode must be a supported RoundingMode.")


@dataclass(frozen=True, slots=True)
class QuestionScoringPolicy:
    """Versioned deterministic scoring rules and permitted question range.

    External JSON/list shapes must be normalized by an adapter/compiler before
    this immutable domain boundary; collection fields intentionally require
    tuples here.
    """

    policy_id: str
    version: int
    question_id: str
    scoring_semantics_version: str
    minimum_score: ScoringDecimal
    maximum_score: ScoringDecimal
    positive_credit_dependencies: tuple[PositiveCreditDependencyRule, ...] = ()
    gates: tuple[GateRule, ...] = ()
    caps: tuple[CapRule, ...] = ()
    deductions: tuple[DeductionRule, ...] = ()
    rounding: RoundingRule | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.policy_id, "policy_id")
        _validate_version(self.version, "policy version")
        _validate_identifier(self.question_id, "question_id")

        if (
            type(self.scoring_semantics_version) is not str
            or self.scoring_semantics_version != SCORING_SEMANTICS_V1
        ):
            raise UnsupportedScoringSemanticsError(
                f"Unsupported scoring semantics version: {self.scoring_semantics_version!r}."
            )

        if (
            type(self.minimum_score) is not ScoringDecimal
            or type(self.maximum_score) is not ScoringDecimal
        ):
            raise InvalidScoringAuthorityError(
                "QuestionScoringPolicy bounds must be ScoringDecimal values."
            )
        if _decimal_greater(self.minimum_score, self.maximum_score):
            raise InvalidScoringAuthorityError(
                "QuestionScoringPolicy minimum_score cannot exceed maximum_score."
            )

        self._validate_rule_tuple(
            self.positive_credit_dependencies,
            PositiveCreditDependencyRule,
            "positive_credit_dependencies",
        )
        self._validate_rule_tuple(self.gates, GateRule, "gates")
        self._validate_rule_tuple(self.caps, CapRule, "caps")
        self._validate_rule_tuple(self.deductions, DeductionRule, "deductions")
        if self.rounding is not None and type(self.rounding) is not RoundingRule:
            raise InvalidScoringAuthorityError(
                "QuestionScoringPolicy.rounding must be a RoundingRule or None."
            )

        all_rules = (
            *self.positive_credit_dependencies,
            *self.gates,
            *self.caps,
            *self.deductions,
        )
        rule_ids = [rule.rule_id for rule in all_rules]
        if self.rounding is not None:
            rule_ids.append(self.rounding.rule_id)
        if len(rule_ids) != len(set(rule_ids)):
            raise InvalidRuleError(
                "rule_id values must be unique within one question scoring authority."
            )

        for gate in self.gates:
            self._validate_ceiling(gate.failure_ceiling, gate.rule_id)
        for cap in self.caps:
            self._validate_ceiling(cap.ceiling, cap.rule_id)

    @staticmethod
    def _validate_rule_tuple(values: object, item_type: type, field_name: str) -> None:
        if type(values) is not tuple:
            raise InvalidScoringAuthorityError(
                f"QuestionScoringPolicy.{field_name} must be a tuple."
            )
        if any(type(value) is not item_type for value in values):
            raise InvalidScoringAuthorityError(
                f"QuestionScoringPolicy.{field_name} contains an invalid rule."
            )

    def _validate_ceiling(self, ceiling: ScoringDecimal, rule_id: str) -> None:
        if _decimal_less(ceiling, self.minimum_score) or _decimal_greater(
            ceiling,
            self.maximum_score,
        ):
            raise InvalidRuleError(
                f"Rule {rule_id!r} ceiling must lie within the permitted question range."
            )
