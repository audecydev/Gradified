from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from grading.contracts.numeric_evidence import NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION
from grading.contracts.paper_aggregation import GradingSpecRef, _validate_grading_spec_ref


NUMERIC_DETERMINISTIC_EVALUATION_RESULT_SCHEMA_VERSION = "1"
DETERMINISTIC_NUMERIC_EVALUATOR_ID = "gradified-deterministic-numeric"
DETERMINISTIC_NUMERIC_EVALUATOR_VERSION = "1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class InvalidNumericEvaluationResultError(ValueError):
    """Raised when a deterministic NUMERIC N3 result is malformed."""


class NumericConditionOutcome(str, Enum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"


def _required_field(value: object, field_name: str) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise InvalidNumericEvaluationResultError(
            f"NumericEvaluationResult.{field_name} is missing."
        ) from exc


def _require_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidNumericEvaluationResultError(
            f"NumericEvaluationResult.{field_name} must be a non-empty exact string "
            "without surrounding whitespace."
        )
    return value


@dataclass(frozen=True, slots=True)
class NumericEvaluationResult:
    """N3 deterministic comparison outcome with authority/evidence provenance only.

    The result deliberately carries no criterion levels, marks, score, review state,
    or publication authority. `NOT_SATISFIED` is emitted only after successful
    validation and deterministic comparison; technical/binding failures are errors.
    """

    schema_version: str
    grading_spec_ref: GradingSpecRef
    authority_fingerprint: str
    question_id: str
    submission_ref: str
    ocr_provenance: str
    answer_scope_ref: str
    evidence_ref: str
    admission_profile_version: str
    outcome: NumericConditionOutcome

    def __post_init__(self) -> None:
        _validate_numeric_evaluation_result(self)


def _validate_numeric_evaluation_result(value: object) -> NumericEvaluationResult:
    if type(value) is not NumericEvaluationResult:
        raise InvalidNumericEvaluationResultError(
            "value must be an exact NumericEvaluationResult."
        )

    schema_version = _required_field(value, "schema_version")
    if (
        type(schema_version) is not str
        or schema_version != NUMERIC_DETERMINISTIC_EVALUATION_RESULT_SCHEMA_VERSION
    ):
        raise InvalidNumericEvaluationResultError(
            "NumericEvaluationResult.schema_version must equal the supported N3 result schema."
        )

    spec_ref = _required_field(value, "grading_spec_ref")
    _validate_grading_spec_ref(
        spec_ref,
        field_name="NumericEvaluationResult.grading_spec_ref",
        error_type=InvalidNumericEvaluationResultError,
    )

    authority_fingerprint = _required_field(value, "authority_fingerprint")
    if type(authority_fingerprint) is not str or _SHA256_RE.fullmatch(authority_fingerprint) is None:
        raise InvalidNumericEvaluationResultError(
            "NumericEvaluationResult.authority_fingerprint must be canonical lowercase SHA-256 hex."
        )

    for field_name in (
        "question_id",
        "submission_ref",
        "ocr_provenance",
        "answer_scope_ref",
        "evidence_ref",
    ):
        _require_identifier(_required_field(value, field_name), field_name)

    admission_profile_version = _required_field(value, "admission_profile_version")
    if (
        type(admission_profile_version) is not str
        or admission_profile_version != NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION
    ):
        raise InvalidNumericEvaluationResultError(
            "NumericEvaluationResult.admission_profile_version must equal the supported "
            "NUMERIC evidence-admission profile."
        )

    outcome = _required_field(value, "outcome")
    if type(outcome) is not NumericConditionOutcome:
        raise InvalidNumericEvaluationResultError(
            "NumericEvaluationResult.outcome must be an exact NumericConditionOutcome."
        )

    return value


def validate_numeric_evaluation_result(value: object) -> NumericEvaluationResult:
    """Revalidate a current N3 result; construction history is not trusted."""

    return _validate_numeric_evaluation_result(value)
