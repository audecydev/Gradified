from __future__ import annotations

from dataclasses import dataclass

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.errors import InvalidRubricAuthoringInputError


def _require_exact_str(value: object, field_name: str) -> None:
    if type(value) is not str:
        raise InvalidRubricAuthoringInputError(f"{field_name} must be an exact str.")


def _require_scoring_decimal(value: object, field_name: str) -> None:
    if type(value) is not ScoringDecimal:
        raise InvalidRubricAuthoringInputError(
            f"{field_name} must be a ScoringDecimal."
        )


def _require_positive_exact_int(value: object, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise InvalidRubricAuthoringInputError(
            f"{field_name} must be a positive exact int."
        )


def _require_tuple_of_exact_type(
    value: object,
    item_type: type,
    field_name: str,
) -> None:
    if type(value) is not tuple:
        raise InvalidRubricAuthoringInputError(f"{field_name} must be a tuple.")
    if any(type(item) is not item_type for item in value):
        raise InvalidRubricAuthoringInputError(
            f"{field_name} contains an invalid item."
        )


@dataclass(frozen=True, slots=True)
class FinalizedQuestionScoringBasis:
    """Trusted finalized-question scoring input supplied by an upstream boundary.

    This grading-domain object binds rubric compilation to the finalized question
    identity and maximum marks. It does not authenticate where those values came
    from; the backend/workflow adapter must supply them from trusted finalized
    assessment state rather than model-generated rubric content.
    """

    question_id: str
    max_marks: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_str(self.question_id, "finalized question_id")
        _require_scoring_decimal(self.max_marks, "finalized max_marks")


@dataclass(frozen=True, slots=True)
class RubricCompilationLimits:
    """Explicit system-owned structural/resource admission policy.

    Release 1 intentionally has no implicit production defaults. Callers must
    provide a reviewed limits object at authoring/compilation boundaries.
    """

    max_criteria: int
    max_levels_per_criterion: int
    max_accepted_equivalents_per_criterion: int
    max_rules: int
    max_conditions_per_rule: int
    max_allowed_level_ids_per_condition: int
    max_text_characters_per_field: int
    max_serialized_authority_bytes: int
    max_reconciliation_states: int

    def __post_init__(self) -> None:
        for field_name in (
            "max_criteria",
            "max_levels_per_criterion",
            "max_accepted_equivalents_per_criterion",
            "max_rules",
            "max_conditions_per_rule",
            "max_allowed_level_ids_per_condition",
            "max_text_characters_per_field",
            "max_serialized_authority_bytes",
            "max_reconciliation_states",
        ):
            _require_positive_exact_int(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class AuthoringPerformanceLevel:
    """Teacher/generator-facing semantic level before reducer projection."""

    level_id: str
    operational_description: str
    contribution: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_str(self.level_id, "level_id")
        _require_exact_str(
            self.operational_description,
            "performance level operational_description",
        )
        _require_scoring_decimal(self.contribution, "performance level contribution")


@dataclass(frozen=True, slots=True)
class AuthoringCriterion:
    """Richer authoring criterion; only its scoring projection reaches the reducer.

    `evidence_requirement` is deliberately opaque human/evaluator-facing text here.
    No OCR block grammar or evaluator schema is invented by this capability.
    """

    criterion_id: str
    operational_description: str
    evidence_requirement: str
    performance_levels: tuple[AuthoringPerformanceLevel, ...]
    accepted_equivalents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_exact_str(self.criterion_id, "criterion_id")
        _require_exact_str(
            self.operational_description,
            "criterion operational_description",
        )
        _require_exact_str(self.evidence_requirement, "evidence_requirement")
        _require_tuple_of_exact_type(
            self.performance_levels,
            AuthoringPerformanceLevel,
            "performance_levels",
        )
        if type(self.accepted_equivalents) is not tuple:
            raise InvalidRubricAuthoringInputError(
                "accepted_equivalents must be a tuple."
            )
        if any(type(value) is not str for value in self.accepted_equivalents):
            raise InvalidRubricAuthoringInputError(
                "accepted_equivalents contains an invalid item."
            )


@dataclass(frozen=True, slots=True)
class AuthoringCriterionCondition:
    criterion_id: str
    allowed_level_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_exact_str(self.criterion_id, "condition criterion_id")
        if type(self.allowed_level_ids) is not tuple:
            raise InvalidRubricAuthoringInputError(
                "allowed_level_ids must be a tuple."
            )
        if any(type(level_id) is not str for level_id in self.allowed_level_ids):
            raise InvalidRubricAuthoringInputError(
                "allowed_level_ids contains an invalid item."
            )


@dataclass(frozen=True, slots=True)
class AuthoringPositiveCreditDependencyRule:
    rule_id: str
    target_criterion_id: str
    prerequisite_conditions: tuple[AuthoringCriterionCondition, ...]

    def __post_init__(self) -> None:
        _require_exact_str(self.rule_id, "dependency rule_id")
        _require_exact_str(self.target_criterion_id, "target_criterion_id")
        _require_tuple_of_exact_type(
            self.prerequisite_conditions,
            AuthoringCriterionCondition,
            "prerequisite_conditions",
        )


@dataclass(frozen=True, slots=True)
class AuthoringGateRule:
    rule_id: str
    required_conditions: tuple[AuthoringCriterionCondition, ...]
    failure_ceiling: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_str(self.rule_id, "gate rule_id")
        _require_tuple_of_exact_type(
            self.required_conditions,
            AuthoringCriterionCondition,
            "required_conditions",
        )
        _require_scoring_decimal(self.failure_ceiling, "failure_ceiling")


@dataclass(frozen=True, slots=True)
class AuthoringCapRule:
    rule_id: str
    trigger_conditions: tuple[AuthoringCriterionCondition, ...]
    ceiling: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_str(self.rule_id, "cap rule_id")
        _require_tuple_of_exact_type(
            self.trigger_conditions,
            AuthoringCriterionCondition,
            "trigger_conditions",
        )
        _require_scoring_decimal(self.ceiling, "ceiling")


@dataclass(frozen=True, slots=True)
class AuthoringDeductionRule:
    rule_id: str
    trigger_conditions: tuple[AuthoringCriterionCondition, ...]
    amount: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_str(self.rule_id, "deduction rule_id")
        _require_tuple_of_exact_type(
            self.trigger_conditions,
            AuthoringCriterionCondition,
            "trigger_conditions",
        )
        _require_scoring_decimal(self.amount, "deduction amount")


@dataclass(frozen=True, slots=True)
class AuthoringRoundingRule:
    rule_id: str
    increment: ScoringDecimal
    mode: str

    def __post_init__(self) -> None:
        _require_exact_str(self.rule_id, "rounding rule_id")
        _require_scoring_decimal(self.increment, "rounding increment")
        _require_exact_str(self.mode, "rounding mode")


@dataclass(frozen=True, slots=True)
class QuestionRubricAuthoringContent:
    """Immutable generated/teacher-edited rubric and policy candidate content.

    Finalized question identity/maximum and scoring-semantics identity are not
    candidate-owned fields. They are supplied by trusted/system-owned inputs at
    compilation time so generated content cannot redefine assessment authority.
    """

    rubric_id: str
    policy_id: str
    minimum_score: ScoringDecimal
    criteria: tuple[AuthoringCriterion, ...]
    positive_credit_dependencies: tuple[
        AuthoringPositiveCreditDependencyRule, ...
    ] = ()
    gates: tuple[AuthoringGateRule, ...] = ()
    caps: tuple[AuthoringCapRule, ...] = ()
    deductions: tuple[AuthoringDeductionRule, ...] = ()
    rounding: AuthoringRoundingRule | None = None

    def __post_init__(self) -> None:
        _require_exact_str(self.rubric_id, "rubric_id")
        _require_exact_str(self.policy_id, "policy_id")
        _require_scoring_decimal(self.minimum_score, "minimum_score")
        _require_tuple_of_exact_type(self.criteria, AuthoringCriterion, "criteria")
        _require_tuple_of_exact_type(
            self.positive_credit_dependencies,
            AuthoringPositiveCreditDependencyRule,
            "positive_credit_dependencies",
        )
        _require_tuple_of_exact_type(self.gates, AuthoringGateRule, "gates")
        _require_tuple_of_exact_type(self.caps, AuthoringCapRule, "caps")
        _require_tuple_of_exact_type(
            self.deductions,
            AuthoringDeductionRule,
            "deductions",
        )
        if self.rounding is not None and type(self.rounding) is not AuthoringRoundingRule:
            raise InvalidRubricAuthoringInputError(
                "rounding must be an AuthoringRoundingRule or None."
            )
