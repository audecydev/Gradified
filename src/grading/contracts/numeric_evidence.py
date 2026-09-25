from __future__ import annotations

import re
from dataclasses import dataclass


NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION = "1"
MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS = 128

_CANONICAL_DECIMAL_RE = re.compile(
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$"
)


class InvalidAdmittedNumericScalarError(ValueError):
    """Raised when an admitted NUMERIC scalar observation is malformed."""


def _required_field(value: object, field_name: str) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise InvalidAdmittedNumericScalarError(
            f"AdmittedNumericScalar.{field_name} is missing."
        ) from exc


def _require_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidAdmittedNumericScalarError(
            f"AdmittedNumericScalar.{field_name} must be a non-empty exact string "
            "without surrounding whitespace."
        )
    return value


def _require_profile(value: object) -> str:
    if (
        type(value) is not str
        or value != NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION
    ):
        raise InvalidAdmittedNumericScalarError(
            "AdmittedNumericScalar.admission_profile_version must equal the "
            f"supported NUMERIC evidence-admission profile "
            f"{NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION!r}."
        )
    return value


def _require_canonical_value(value: object) -> str:
    if type(value) is not str:
        raise InvalidAdmittedNumericScalarError(
            "AdmittedNumericScalar.canonical_value must be an exact string."
        )
    if len(value) > MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS:
        raise InvalidAdmittedNumericScalarError(
            "AdmittedNumericScalar.canonical_value exceeds the profile-v1 "
            f"{MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS}-character limit."
        )
    if _CANONICAL_DECIMAL_RE.fullmatch(value) is None or value == "-0":
        raise InvalidAdmittedNumericScalarError(
            "AdmittedNumericScalar.canonical_value must be canonical finite-decimal text."
        )
    return value


@dataclass(frozen=True, slots=True)
class AdmittedNumericScalar:
    """One bounded scalar observation admitted from normalized answer evidence.

    This value records parser output and traceability only. It carries no claim
    that the scalar is academically correct and it confers no scoring authority.
    """

    admission_profile_version: str
    submission_ref: str
    ocr_provenance: str
    question_id: str
    answer_scope_ref: str
    evidence_ref: str
    canonical_value: str

    def __post_init__(self) -> None:
        _validate_admitted_numeric_scalar(self)


def _validate_admitted_numeric_scalar(value: object) -> AdmittedNumericScalar:
    if type(value) is not AdmittedNumericScalar:
        raise InvalidAdmittedNumericScalarError(
            "value must be an exact AdmittedNumericScalar."
        )
    _require_profile(_required_field(value, "admission_profile_version"))
    for field_name in (
        "submission_ref",
        "ocr_provenance",
        "question_id",
        "answer_scope_ref",
        "evidence_ref",
    ):
        _require_identifier(_required_field(value, field_name), field_name)
    _require_canonical_value(_required_field(value, "canonical_value"))
    return value


def validate_admitted_numeric_scalar(value: object) -> AdmittedNumericScalar:
    """Revalidate a current observation; construction history is not trusted."""

    return _validate_admitted_numeric_scalar(value)
