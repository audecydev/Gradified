from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from grading.contracts.paper_aggregation import GradingSpecRef, _validate_grading_spec_ref


NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION = "1"
NUMERIC_EVALUATION_AUTHORITY_SCHEMA = "gradified-numeric-evaluation-authority-v1"

MAX_NUMERIC_AUTHORITY_CONDITIONS = 32
MAX_NUMERIC_DECIMAL_TEXT_CHARACTERS = 128
MAX_NUMERIC_PROJECTION_ENTRIES = 512
MAX_NUMERIC_IDENTIFIER_TEXT_CHARACTERS = 512
MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES = 65536

_CONDITION_EXACT = "EXACT"
_CONDITION_ABSOLUTE_TOLERANCE = "ABSOLUTE_TOLERANCE"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_DECIMAL_RE = re.compile(
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$"
)


class NumericAuthorityError(ValueError):
    """Base class for expected NUMERIC N1 authority-contract failures."""


class InvalidNumericEvaluationAuthorityError(NumericAuthorityError):
    """Raised when local NUMERIC evaluation authority is malformed."""


class InvalidNumericExpectedBindingError(NumericAuthorityError):
    """Raised when an expected NUMERIC configuration binding is malformed."""


class InvalidNumericAuthorityApprovalError(NumericAuthorityError):
    """Raised when subordinate NUMERIC approval evidence is malformed."""


class UnsupportedNumericAuthorityProfileError(NumericAuthorityError):
    """Raised when NUMERIC authority requests an unsupported profile."""


def _required_field(
    value: object,
    field_name: str,
    *,
    owner_name: str,
    error_type: type[NumericAuthorityError],
) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise error_type(f"{owner_name}.{field_name} is missing.") from exc


def _require_exact_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[NumericAuthorityError],
) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise error_type(
            f"{field_name} must be a non-empty exact string without surrounding whitespace."
        )
    if len(value) > MAX_NUMERIC_IDENTIFIER_TEXT_CHARACTERS:
        raise error_type(
            f"{field_name} exceeds the profile-v1 {MAX_NUMERIC_IDENTIFIER_TEXT_CHARACTERS}-character limit."
        )
    return value


def _require_sha256_hex(
    value: object,
    *,
    field_name: str,
    error_type: type[NumericAuthorityError],
) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise error_type(f"{field_name} must be canonical lowercase SHA-256 hex.")
    return value


def _require_positive_version(
    value: object,
    *,
    field_name: str,
    error_type: type[NumericAuthorityError],
) -> int:
    if type(value) is not int or value <= 0:
        raise error_type(f"{field_name} must be a positive exact integer.")
    return value


def _require_supported_profile(
    value: object,
    *,
    field_name: str,
) -> str:
    if type(value) is not str or value != NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION:
        raise UnsupportedNumericAuthorityProfileError(
            f"{field_name} must equal supported NUMERIC evaluation authority profile "
            f"{NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION!r}."
        )
    return value


def _require_grading_spec_ref(
    value: object,
    *,
    field_name: str,
    error_type: type[NumericAuthorityError],
) -> GradingSpecRef:
    try:
        ref = _validate_grading_spec_ref(
            value,
            field_name=field_name,
            error_type=error_type,
        )
    except error_type:
        raise
    except Exception as exc:  # defensive containment around a foreign existing contract
        raise error_type(f"{field_name} is invalid.") from exc

    # N1's own resource profile additionally bounds textual binding identifiers.
    _require_exact_identifier(
        ref.id,
        field_name=f"{field_name}.id",
        error_type=error_type,
    )
    return ref


def _require_canonical_decimal(value: object, *, field_name: str) -> str:
    if type(value) is not str:
        raise InvalidNumericEvaluationAuthorityError(
            f"{field_name} must be an exact canonical decimal string."
        )
    if len(value) > MAX_NUMERIC_DECIMAL_TEXT_CHARACTERS:
        raise InvalidNumericEvaluationAuthorityError(
            f"{field_name} exceeds the profile-v1 "
            f"{MAX_NUMERIC_DECIMAL_TEXT_CHARACTERS}-character decimal limit."
        )
    if _CANONICAL_DECIMAL_RE.fullmatch(value) is None or value == "-0":
        raise InvalidNumericEvaluationAuthorityError(
            f"{field_name} is not a canonical finite-decimal authority value."
        )
    return value


def _encode_payload(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class NumericCriterionProjection:
    criterion_id: str
    selected_level: str

    def __post_init__(self) -> None:
        _validate_projection(self)


@dataclass(frozen=True, slots=True)
class NumericExactCondition:
    expected_value: str

    def __post_init__(self) -> None:
        _validate_exact_condition(self)


@dataclass(frozen=True, slots=True)
class NumericAbsoluteToleranceCondition:
    expected_value: str
    tolerance: str

    def __post_init__(self) -> None:
        _validate_tolerance_condition(self)


NumericAuthorityCondition = NumericExactCondition | NumericAbsoluteToleranceCondition


@dataclass(frozen=True, slots=True)
class NumericEvaluationAuthority:
    evaluation_authority_profile_version: str
    grading_spec_ref: GradingSpecRef
    question_id: str
    rubric_id: str
    rubric_version: int
    finalized_question_hash: str
    source_content_hash: str
    compiled_authority_hash: str
    conditions: tuple[NumericAuthorityCondition, ...]
    satisfied_projection: tuple[NumericCriterionProjection, ...]
    not_satisfied_projection: tuple[NumericCriterionProjection, ...]

    def __post_init__(self) -> None:
        _validate_numeric_evaluation_authority(self, enforce_payload_limit=True)


@dataclass(frozen=True, slots=True)
class NumericNotAuthorizedBinding:
    grading_spec_ref: GradingSpecRef
    question_id: str

    def __post_init__(self) -> None:
        _validate_not_authorized_binding(self)


@dataclass(frozen=True, slots=True)
class NumericBoundAuthorityBinding:
    grading_spec_ref: GradingSpecRef
    question_id: str
    evaluation_authority_profile_version: str
    authority_fingerprint: str

    def __post_init__(self) -> None:
        _validate_bound_authority_binding(self)


NumericExpectedBinding = NumericNotAuthorizedBinding | NumericBoundAuthorityBinding


@dataclass(frozen=True, slots=True)
class NumericAuthorityApproval:
    teacher_ref: str
    numeric_authority_fingerprint: str

    def __post_init__(self) -> None:
        _validate_numeric_authority_approval(self)


def _validate_projection(value: object) -> NumericCriterionProjection:
    if type(value) is not NumericCriterionProjection:
        raise InvalidNumericEvaluationAuthorityError(
            "projection entry must be an exact NumericCriterionProjection."
        )
    criterion_id = _required_field(
        value, "criterion_id", owner_name="NumericCriterionProjection",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    selected_level = _required_field(
        value, "selected_level", owner_name="NumericCriterionProjection",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    _require_exact_identifier(
        criterion_id,
        field_name="NumericCriterionProjection.criterion_id",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    _require_exact_identifier(
        selected_level,
        field_name="NumericCriterionProjection.selected_level",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    return value


def _validate_exact_condition(value: object) -> NumericExactCondition:
    if type(value) is not NumericExactCondition:
        raise InvalidNumericEvaluationAuthorityError(
            "condition must be an exact NumericExactCondition."
        )
    expected_value = _required_field(
        value, "expected_value", owner_name="NumericExactCondition",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    _require_canonical_decimal(
        expected_value,
        field_name="NumericExactCondition.expected_value",
    )
    return value


def _validate_tolerance_condition(
    value: object,
) -> NumericAbsoluteToleranceCondition:
    if type(value) is not NumericAbsoluteToleranceCondition:
        raise InvalidNumericEvaluationAuthorityError(
            "condition must be an exact NumericAbsoluteToleranceCondition."
        )
    expected_value = _required_field(
        value, "expected_value", owner_name="NumericAbsoluteToleranceCondition",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    tolerance_value = _required_field(
        value, "tolerance", owner_name="NumericAbsoluteToleranceCondition",
        error_type=InvalidNumericEvaluationAuthorityError,
    )
    _require_canonical_decimal(
        expected_value,
        field_name="NumericAbsoluteToleranceCondition.expected_value",
    )
    tolerance = _require_canonical_decimal(
        tolerance_value,
        field_name="NumericAbsoluteToleranceCondition.tolerance",
    )
    if tolerance == "0" or tolerance.startswith("-"):
        raise InvalidNumericEvaluationAuthorityError(
            "NumericAbsoluteToleranceCondition.tolerance must be strictly positive."
        )
    return value


def _condition_payload(condition: NumericAuthorityCondition) -> dict[str, str]:
    if type(condition) is NumericExactCondition:
        return {
            "condition_type": _CONDITION_EXACT,
            "expected_value": condition.expected_value,
        }
    if type(condition) is NumericAbsoluteToleranceCondition:
        return {
            "condition_type": _CONDITION_ABSOLUTE_TOLERANCE,
            "expected_value": condition.expected_value,
            "tolerance": condition.tolerance,
        }
    raise InvalidNumericEvaluationAuthorityError(
        "conditions contains an unsupported NUMERIC authority condition type."
    )


def _condition_identity(condition: NumericAuthorityCondition) -> tuple[str, ...]:
    if type(condition) is NumericExactCondition:
        return (_CONDITION_EXACT, condition.expected_value)
    if type(condition) is NumericAbsoluteToleranceCondition:
        return (
            _CONDITION_ABSOLUTE_TOLERANCE,
            condition.expected_value,
            condition.tolerance,
        )
    raise InvalidNumericEvaluationAuthorityError(
        "conditions contains an unsupported NUMERIC authority condition type."
    )


def _validate_condition(value: object) -> NumericAuthorityCondition:
    if type(value) is NumericExactCondition:
        return _validate_exact_condition(value)
    if type(value) is NumericAbsoluteToleranceCondition:
        return _validate_tolerance_condition(value)
    raise InvalidNumericEvaluationAuthorityError(
        "conditions contains an unsupported NUMERIC authority condition type."
    )


def _validate_projection_tuple(
    value: object,
    *,
    field_name: str,
) -> tuple[NumericCriterionProjection, ...]:
    if type(value) is not tuple or not value:
        raise InvalidNumericEvaluationAuthorityError(
            f"{field_name} must be a non-empty exact tuple."
        )
    if len(value) > MAX_NUMERIC_PROJECTION_ENTRIES:
        raise InvalidNumericEvaluationAuthorityError(
            f"{field_name} exceeds the profile-v1 {MAX_NUMERIC_PROJECTION_ENTRIES}-entry limit."
        )

    criterion_ids: list[str] = []
    for index, item in enumerate(value):
        try:
            projection = _validate_projection(item)
        except InvalidNumericEvaluationAuthorityError as exc:
            raise InvalidNumericEvaluationAuthorityError(
                f"{field_name}[{index}] is invalid."
            ) from exc
        criterion_ids.append(projection.criterion_id)

    if len(criterion_ids) != len(set(criterion_ids)):
        raise InvalidNumericEvaluationAuthorityError(
            f"{field_name} contains duplicate criterion_id values."
        )
    return value  # type: ignore[return-value]


def _validate_numeric_evaluation_authority(
    value: object,
    *,
    enforce_payload_limit: bool,
) -> NumericEvaluationAuthority:
    if type(value) is not NumericEvaluationAuthority:
        raise InvalidNumericEvaluationAuthorityError(
            "authority must be an exact NumericEvaluationAuthority."
        )

    owner = "NumericEvaluationAuthority"
    profile = _required_field(value, "evaluation_authority_profile_version", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    grading_spec_ref = _required_field(value, "grading_spec_ref", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    question_id = _required_field(value, "question_id", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    rubric_id = _required_field(value, "rubric_id", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    rubric_version = _required_field(value, "rubric_version", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)

    _require_supported_profile(profile, field_name=f"{owner}.evaluation_authority_profile_version")
    _require_grading_spec_ref(grading_spec_ref, field_name=f"{owner}.grading_spec_ref", error_type=InvalidNumericEvaluationAuthorityError)
    _require_exact_identifier(question_id, field_name=f"{owner}.question_id", error_type=InvalidNumericEvaluationAuthorityError)
    _require_exact_identifier(rubric_id, field_name=f"{owner}.rubric_id", error_type=InvalidNumericEvaluationAuthorityError)
    _require_positive_version(rubric_version, field_name=f"{owner}.rubric_version", error_type=InvalidNumericEvaluationAuthorityError)
    for field_name in ("finalized_question_hash", "source_content_hash", "compiled_authority_hash"):
        field_value = _required_field(value, field_name, owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
        _require_sha256_hex(field_value, field_name=f"{owner}.{field_name}", error_type=InvalidNumericEvaluationAuthorityError)

    conditions = _required_field(value, "conditions", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    if type(conditions) is not tuple or not conditions:
        raise InvalidNumericEvaluationAuthorityError(
            "NumericEvaluationAuthority.conditions must be a non-empty exact tuple."
        )
    if len(conditions) > MAX_NUMERIC_AUTHORITY_CONDITIONS:
        raise InvalidNumericEvaluationAuthorityError(
            "NumericEvaluationAuthority.conditions exceeds the profile-v1 "
            f"{MAX_NUMERIC_AUTHORITY_CONDITIONS}-condition limit."
        )
    identities: list[tuple[str, ...]] = []
    for index, condition in enumerate(conditions):
        try:
            validated = _validate_condition(condition)
        except InvalidNumericEvaluationAuthorityError as exc:
            raise InvalidNumericEvaluationAuthorityError(
                f"NumericEvaluationAuthority.conditions[{index}] is invalid."
            ) from exc
        identities.append(_condition_identity(validated))
    if len(identities) != len(set(identities)):
        raise InvalidNumericEvaluationAuthorityError(
            "NumericEvaluationAuthority.conditions contains exact duplicate conditions."
        )

    satisfied_value = _required_field(value, "satisfied_projection", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    not_satisfied_value = _required_field(value, "not_satisfied_projection", owner_name=owner, error_type=InvalidNumericEvaluationAuthorityError)
    satisfied = _validate_projection_tuple(
        satisfied_value,
        field_name="NumericEvaluationAuthority.satisfied_projection",
    )
    not_satisfied = _validate_projection_tuple(
        not_satisfied_value,
        field_name="NumericEvaluationAuthority.not_satisfied_projection",
    )
    if tuple(item.criterion_id for item in satisfied) != tuple(
        item.criterion_id for item in not_satisfied
    ):
        raise InvalidNumericEvaluationAuthorityError(
            "NUMERIC satisfied/not-satisfied projections must have identical criterion-ID sequences."
        )

    if enforce_payload_limit:
        payload_bytes = _canonical_authority_bytes_from_validated(value)
        if len(payload_bytes) > MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES:
            raise InvalidNumericEvaluationAuthorityError(
                "NumericEvaluationAuthority canonical payload exceeds the profile-v1 "
                f"{MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES}-byte limit."
            )
    return value


def _projection_payload(
    projection: tuple[NumericCriterionProjection, ...],
) -> list[dict[str, str]]:
    return [
        {
            "criterion_id": item.criterion_id,
            "selected_level": item.selected_level,
        }
        for item in projection
    ]


def _authority_payload(authority: NumericEvaluationAuthority) -> dict[str, Any]:
    condition_payloads = [_condition_payload(condition) for condition in authority.conditions]
    condition_payloads.sort(key=_encode_payload)
    return {
        "schema": NUMERIC_EVALUATION_AUTHORITY_SCHEMA,
        "evaluation_authority_profile_version": authority.evaluation_authority_profile_version,
        "grading_spec_ref": {
            "id": authority.grading_spec_ref.id,
            "version": authority.grading_spec_ref.version,
        },
        "question_id": authority.question_id,
        "rubric_id": authority.rubric_id,
        "rubric_version": authority.rubric_version,
        "finalized_question_hash": authority.finalized_question_hash,
        "source_content_hash": authority.source_content_hash,
        "compiled_authority_hash": authority.compiled_authority_hash,
        "conditions": condition_payloads,
        "satisfied_projection": _projection_payload(authority.satisfied_projection),
        "not_satisfied_projection": _projection_payload(authority.not_satisfied_projection),
    }


def _canonical_authority_bytes_from_validated(
    authority: NumericEvaluationAuthority,
) -> bytes:
    return _encode_payload(_authority_payload(authority))


def numeric_authority_canonical_bytes(authority: NumericEvaluationAuthority) -> bytes:
    """Return profile-v1 canonical bytes after revalidating the current payload.

    This is deliberately a current-state operation: construction history and any
    caller-supplied digest are not trusted. The exact JSON mapping is part of
    NUMERIC evaluation authority profile v1 and is protected by golden vectors.
    """

    _validate_numeric_evaluation_authority(authority, enforce_payload_limit=False)
    payload_bytes = _canonical_authority_bytes_from_validated(authority)
    if len(payload_bytes) > MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES:
        raise InvalidNumericEvaluationAuthorityError(
            "NumericEvaluationAuthority canonical payload exceeds the profile-v1 "
            f"{MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES}-byte limit."
        )
    return payload_bytes


def numeric_authority_fingerprint(authority: NumericEvaluationAuthority) -> str:
    """Hash the exact current validated profile-v1 authority payload."""

    return hashlib.sha256(numeric_authority_canonical_bytes(authority)).hexdigest()


def _validate_not_authorized_binding(
    value: object,
) -> NumericNotAuthorizedBinding:
    if type(value) is not NumericNotAuthorizedBinding:
        raise InvalidNumericExpectedBindingError(
            "binding must be an exact NumericNotAuthorizedBinding."
        )
    spec_ref = _required_field(value, "grading_spec_ref", owner_name="NumericNotAuthorizedBinding", error_type=InvalidNumericExpectedBindingError)
    question_id = _required_field(value, "question_id", owner_name="NumericNotAuthorizedBinding", error_type=InvalidNumericExpectedBindingError)
    _require_grading_spec_ref(spec_ref, field_name="NumericNotAuthorizedBinding.grading_spec_ref", error_type=InvalidNumericExpectedBindingError)
    _require_exact_identifier(question_id, field_name="NumericNotAuthorizedBinding.question_id", error_type=InvalidNumericExpectedBindingError)
    return value


def _validate_bound_authority_binding(
    value: object,
) -> NumericBoundAuthorityBinding:
    if type(value) is not NumericBoundAuthorityBinding:
        raise InvalidNumericExpectedBindingError(
            "binding must be an exact NumericBoundAuthorityBinding."
        )
    owner = "NumericBoundAuthorityBinding"
    spec_ref = _required_field(value, "grading_spec_ref", owner_name=owner, error_type=InvalidNumericExpectedBindingError)
    question_id = _required_field(value, "question_id", owner_name=owner, error_type=InvalidNumericExpectedBindingError)
    profile = _required_field(value, "evaluation_authority_profile_version", owner_name=owner, error_type=InvalidNumericExpectedBindingError)
    authority_fingerprint = _required_field(value, "authority_fingerprint", owner_name=owner, error_type=InvalidNumericExpectedBindingError)
    _require_grading_spec_ref(spec_ref, field_name=f"{owner}.grading_spec_ref", error_type=InvalidNumericExpectedBindingError)
    _require_exact_identifier(question_id, field_name=f"{owner}.question_id", error_type=InvalidNumericExpectedBindingError)
    _require_supported_profile(profile, field_name=f"{owner}.evaluation_authority_profile_version")
    _require_sha256_hex(authority_fingerprint, field_name=f"{owner}.authority_fingerprint", error_type=InvalidNumericExpectedBindingError)
    return value


def validate_numeric_expected_binding(value: object) -> NumericExpectedBinding:
    """Revalidate a possibly forged current expected-binding value."""

    if type(value) is NumericNotAuthorizedBinding:
        return _validate_not_authorized_binding(value)
    if type(value) is NumericBoundAuthorityBinding:
        return _validate_bound_authority_binding(value)
    raise InvalidNumericExpectedBindingError(
        "expected binding must be an exact NUMERIC expected-binding state."
    )


def _validate_numeric_authority_approval(value: object) -> NumericAuthorityApproval:
    if type(value) is not NumericAuthorityApproval:
        raise InvalidNumericAuthorityApprovalError(
            "approval must be an exact NumericAuthorityApproval."
        )
    owner = "NumericAuthorityApproval"
    teacher_ref = _required_field(value, "teacher_ref", owner_name=owner, error_type=InvalidNumericAuthorityApprovalError)
    authority_fingerprint = _required_field(value, "numeric_authority_fingerprint", owner_name=owner, error_type=InvalidNumericAuthorityApprovalError)
    _require_exact_identifier(teacher_ref, field_name=f"{owner}.teacher_ref", error_type=InvalidNumericAuthorityApprovalError)
    _require_sha256_hex(authority_fingerprint, field_name=f"{owner}.numeric_authority_fingerprint", error_type=InvalidNumericAuthorityApprovalError)
    return value


def validate_numeric_authority_approval(value: object) -> NumericAuthorityApproval:
    """Revalidate current subordinate approval evidence without authenticating it."""

    return _validate_numeric_authority_approval(value)
