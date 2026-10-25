from __future__ import annotations

from dataclasses import dataclass

from grading.active_question_authority import ContextPolicy
from grading.contracts.capability import (
    EvaluatorCapabilityRef,
    InvalidEvaluatorCapabilityRefError,
    validate_evaluator_capability_ref,
)
from grading.contracts.paper_aggregation import GradingSpecRef, _validate_grading_spec_ref


QUESTION_EVALUATION_CLASSIFICATION_SCHEMA_VERSION = "1"
EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION = "1"


class QuestionEvaluationClassificationContractError(ValueError):
    """Expected failure for malformed evaluator selection question classification values."""


class EvaluatorSelectionPolicyContractError(ValueError):
    """Expected failure for malformed evaluator selection evaluator-selection policy values."""


def _required_field(
    value: object,
    field_name: str,
    *,
    owner_name: str,
    error_type: type[ValueError],
) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise error_type(f"{owner_name}.{field_name} is missing.") from exc


def _require_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[ValueError],
) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise error_type(
            f"{field_name} must be a non-empty exact string without surrounding whitespace."
        )
    return value


@dataclass(frozen=True, slots=True)
class QuestionEvaluationClassification:
    schema_version: str
    grading_spec_ref: GradingSpecRef
    question_id: str
    answer_type: str
    language: str

    def __post_init__(self) -> None:
        validate_question_evaluation_classification(self)


@dataclass(frozen=True, slots=True)
class EvaluatorSelectionPolicyRef:
    policy_id: str
    version: int

    def __post_init__(self) -> None:
        _validate_policy_ref(self)


@dataclass(frozen=True, slots=True)
class EvaluatorSelectionRule:
    answer_type: str
    language: str
    context_policy: ContextPolicy
    capability_ref: EvaluatorCapabilityRef

    def __post_init__(self) -> None:
        _validate_rule(self)


@dataclass(frozen=True, slots=True)
class EvaluatorSelectionPolicy:
    schema_version: str
    policy_ref: EvaluatorSelectionPolicyRef
    rules: tuple[EvaluatorSelectionRule, ...]

    def __post_init__(self) -> None:
        validate_evaluator_selection_policy(self)


def validate_question_evaluation_classification(
    value: object,
) -> QuestionEvaluationClassification:
    """Validate complete current state for one exact classification projection."""

    if type(value) is not QuestionEvaluationClassification:
        raise QuestionEvaluationClassificationContractError(
            "classification must be an exact QuestionEvaluationClassification."
        )

    schema_version = _required_field(
        value,
        "schema_version",
        owner_name="QuestionEvaluationClassification",
        error_type=QuestionEvaluationClassificationContractError,
    )
    if (
        type(schema_version) is not str
        or schema_version != QUESTION_EVALUATION_CLASSIFICATION_SCHEMA_VERSION
    ):
        raise QuestionEvaluationClassificationContractError(
            "QuestionEvaluationClassification.schema_version must equal supported version '1'."
        )

    grading_spec_ref = _required_field(
        value,
        "grading_spec_ref",
        owner_name="QuestionEvaluationClassification",
        error_type=QuestionEvaluationClassificationContractError,
    )
    _validate_grading_spec_ref(
        grading_spec_ref,
        field_name="QuestionEvaluationClassification.grading_spec_ref",
        error_type=QuestionEvaluationClassificationContractError,
    )

    for field_name in ("question_id", "answer_type", "language"):
        _require_identifier(
            _required_field(
                value,
                field_name,
                owner_name="QuestionEvaluationClassification",
                error_type=QuestionEvaluationClassificationContractError,
            ),
            field_name=f"QuestionEvaluationClassification.{field_name}",
            error_type=QuestionEvaluationClassificationContractError,
        )

    return value


def _validate_policy_ref(value: object) -> EvaluatorSelectionPolicyRef:
    if type(value) is not EvaluatorSelectionPolicyRef:
        raise EvaluatorSelectionPolicyContractError(
            "policy_ref must be an exact EvaluatorSelectionPolicyRef."
        )

    _require_identifier(
        _required_field(
            value,
            "policy_id",
            owner_name="EvaluatorSelectionPolicyRef",
            error_type=EvaluatorSelectionPolicyContractError,
        ),
        field_name="EvaluatorSelectionPolicyRef.policy_id",
        error_type=EvaluatorSelectionPolicyContractError,
    )

    version = _required_field(
        value,
        "version",
        owner_name="EvaluatorSelectionPolicyRef",
        error_type=EvaluatorSelectionPolicyContractError,
    )
    if type(version) is not int or version <= 0:
        raise EvaluatorSelectionPolicyContractError(
            "EvaluatorSelectionPolicyRef.version must be a positive exact integer."
        )

    return value


def _validate_rule(value: object) -> EvaluatorSelectionRule:
    if type(value) is not EvaluatorSelectionRule:
        raise EvaluatorSelectionPolicyContractError(
            "rule must be an exact EvaluatorSelectionRule."
        )

    for field_name in ("answer_type", "language"):
        _require_identifier(
            _required_field(
                value,
                field_name,
                owner_name="EvaluatorSelectionRule",
                error_type=EvaluatorSelectionPolicyContractError,
            ),
            field_name=f"EvaluatorSelectionRule.{field_name}",
            error_type=EvaluatorSelectionPolicyContractError,
        )

    context_policy = _required_field(
        value,
        "context_policy",
        owner_name="EvaluatorSelectionRule",
        error_type=EvaluatorSelectionPolicyContractError,
    )
    if type(context_policy) is not ContextPolicy or not any(
        context_policy is member for member in ContextPolicy
    ):
        raise EvaluatorSelectionPolicyContractError(
            "EvaluatorSelectionRule.context_policy must be a canonical ContextPolicy member."
        )

    capability_ref = _required_field(
        value,
        "capability_ref",
        owner_name="EvaluatorSelectionRule",
        error_type=EvaluatorSelectionPolicyContractError,
    )
    try:
        validate_evaluator_capability_ref(capability_ref)
    except InvalidEvaluatorCapabilityRefError as exc:
        raise EvaluatorSelectionPolicyContractError(
            "EvaluatorSelectionRule.capability_ref is invalid."
        ) from exc

    return value


def validate_evaluator_selection_policy(value: object) -> EvaluatorSelectionPolicy:
    """Validate complete current state for one exact selection policy."""

    if type(value) is not EvaluatorSelectionPolicy:
        raise EvaluatorSelectionPolicyContractError(
            "policy must be an exact EvaluatorSelectionPolicy."
        )

    schema_version = _required_field(
        value,
        "schema_version",
        owner_name="EvaluatorSelectionPolicy",
        error_type=EvaluatorSelectionPolicyContractError,
    )
    if (
        type(schema_version) is not str
        or schema_version != EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION
    ):
        raise EvaluatorSelectionPolicyContractError(
            "EvaluatorSelectionPolicy.schema_version must equal supported version '1'."
        )

    _validate_policy_ref(
        _required_field(
            value,
            "policy_ref",
            owner_name="EvaluatorSelectionPolicy",
            error_type=EvaluatorSelectionPolicyContractError,
        )
    )

    rules = _required_field(
        value,
        "rules",
        owner_name="EvaluatorSelectionPolicy",
        error_type=EvaluatorSelectionPolicyContractError,
    )
    if type(rules) is not tuple:
        raise EvaluatorSelectionPolicyContractError(
            "EvaluatorSelectionPolicy.rules must be an exact tuple."
        )

    seen: set[tuple[str, str, ContextPolicy]] = set()
    for rule in rules:
        _validate_rule(rule)
        key = (
            object.__getattribute__(rule, "answer_type"),
            object.__getattribute__(rule, "language"),
            object.__getattribute__(rule, "context_policy"),
        )
        if key in seen:
            raise EvaluatorSelectionPolicyContractError(
                "EvaluatorSelectionPolicy.rules must not contain duplicate exact selection keys."
            )
        seen.add(key)

    return value
