from __future__ import annotations

import pytest
from dataclasses import fields

from grading.contracts.numeric_evidence import (
    MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS,
    NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
    AdmittedNumericScalar,
    InvalidAdmittedNumericScalarError,
    validate_admitted_numeric_scalar,
)


def _valid(**overrides: object) -> AdmittedNumericScalar:
    values: dict[str, object] = {
        "admission_profile_version": NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
        "submission_ref": "submission-1",
        "ocr_provenance": "ocr-run-1",
        "question_id": "Q1",
        "answer_scope_ref": "scope-Q1",
        "evidence_ref": "Q1-B1",
        "canonical_value": "12.5",
    }
    values.update(overrides)
    return AdmittedNumericScalar(**values)  # type: ignore[arg-type]


def test_admitted_numeric_scalar_contract_has_exact_authority_free_field_surface() -> None:
    assert tuple(field.name for field in fields(AdmittedNumericScalar)) == (
        "admission_profile_version",
        "submission_ref",
        "ocr_provenance",
        "question_id",
        "answer_scope_ref",
        "evidence_ref",
        "canonical_value",
    )


def test_admitted_numeric_scalar_contract_accepts_exact_profile_value() -> None:
    value = _valid()
    assert value.admission_profile_version == "1"
    assert value.canonical_value == "12.5"
    assert validate_admitted_numeric_scalar(value) is value


@pytest.mark.parametrize(
    "field,value",
    [
        ("admission_profile_version", "2"),
        ("admission_profile_version", 1),
        ("submission_ref", ""),
        ("submission_ref", " submission-1"),
        ("ocr_provenance", ""),
        ("question_id", "Q1 "),
        ("answer_scope_ref", ""),
        ("evidence_ref", " Q1-B1"),
    ],
)
def test_admitted_numeric_scalar_rejects_invalid_identity_or_profile(
    field: str,
    value: object,
) -> None:
    with pytest.raises(InvalidAdmittedNumericScalarError):
        _valid(**{field: value})


@pytest.mark.parametrize(
    "value",
    [
        "-0",
        "+1",
        "01",
        "1.0",
        ".5",
        "1.",
        "1e2",
        "1E2",
        "1_000",
        "1,000",
        "NaN",
        "Infinity",
        " 1",
        "1 ",
        "١",
        "１２",
        "",
    ],
)
def test_admitted_numeric_scalar_requires_canonical_output_value(value: str) -> None:
    with pytest.raises(InvalidAdmittedNumericScalarError):
        _valid(canonical_value=value)


def test_admitted_numeric_scalar_accepts_profile_boundary_length() -> None:
    value = "9" * MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS
    assert _valid(canonical_value=value).canonical_value == value


def test_admitted_numeric_scalar_rejects_over_profile_boundary_length() -> None:
    with pytest.raises(InvalidAdmittedNumericScalarError):
        _valid(canonical_value="9" * (MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS + 1))


def test_validator_rejects_post_construction_forgery() -> None:
    value = _valid()
    object.__setattr__(value, "canonical_value", "1.0")
    with pytest.raises(InvalidAdmittedNumericScalarError):
        validate_admitted_numeric_scalar(value)


def test_validator_rejects_foreign_objects() -> None:
    with pytest.raises(InvalidAdmittedNumericScalarError):
        validate_admitted_numeric_scalar(object())
