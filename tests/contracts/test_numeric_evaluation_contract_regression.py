from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from importlib import import_module

import pytest

from grading.contracts.numeric_evidence import NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION
from grading.contracts.paper_aggregation import GradingSpecRef


_HASH = "a" * 64


def _contract():
    return import_module("grading.contracts.numeric_evaluation")


def _result(**overrides: object):
    c = _contract()
    values: dict[str, object] = {
        "schema_version": c.NUMERIC_DETERMINISTIC_EVALUATION_RESULT_SCHEMA_VERSION,
        "grading_spec_ref": GradingSpecRef("SPEC-1", 1),
        "authority_fingerprint": _HASH,
        "question_id": "Q1",
        "submission_ref": "submission-1",
        "ocr_provenance": "ocr-run-1",
        "answer_scope_ref": "scope-Q1",
        "evidence_ref": "Q1-B1",
        "admission_profile_version": NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
        "outcome": c.NumericConditionOutcome.SATISFIED,
    }
    values.update(overrides)
    return c.NumericEvaluationResult(**values)


def test_red1_existing_spec_ref_is_valid_before_missing_n3_contract_import() -> None:
    spec = GradingSpecRef("SPEC-1", 1)
    assert spec.id == "SPEC-1"
    assert _contract().NUMERIC_DETERMINISTIC_EVALUATION_RESULT_SCHEMA_VERSION == "1"


def test_result_surface_contains_only_outcome_and_provenance_not_projection_or_marks() -> None:
    c = _contract()
    assert {field.name for field in fields(c.NumericEvaluationResult)} == {
        "schema_version",
        "grading_spec_ref",
        "authority_fingerprint",
        "question_id",
        "submission_ref",
        "ocr_provenance",
        "answer_scope_ref",
        "evidence_ref",
        "admission_profile_version",
        "outcome",
    }
    forbidden = {
        "criterion_id",
        "selected_level",
        "projection",
        "marks",
        "awarded_marks",
        "score",
        "review",
        "published",
        "matched_condition_index",
    }
    assert not ({field.name for field in fields(c.NumericEvaluationResult)} & forbidden)


def test_outcome_universe_is_exactly_satisfied_or_not_satisfied() -> None:
    c = _contract()
    assert tuple(c.NumericConditionOutcome) == (
        c.NumericConditionOutcome.SATISFIED,
        c.NumericConditionOutcome.NOT_SATISFIED,
    )


def test_evaluator_identity_is_domain_specific_and_versioned() -> None:
    c = _contract()
    assert c.DETERMINISTIC_NUMERIC_EVALUATOR_ID == "gradified-deterministic-numeric"
    assert c.DETERMINISTIC_NUMERIC_EVALUATOR_VERSION == "1"


def test_result_is_frozen() -> None:
    result = _result()
    with pytest.raises(FrozenInstanceError):
        result.question_id = "Q2"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "bad"),
    [
        ("schema_version", "2"),
        ("grading_spec_ref", object()),
        ("authority_fingerprint", "A" * 64),
        ("authority_fingerprint", "a" * 63),
        ("question_id", " Q1"),
        ("submission_ref", ""),
        ("ocr_provenance", "ocr "),
        ("answer_scope_ref", 5),
        ("evidence_ref", ""),
        ("admission_profile_version", "2"),
        ("outcome", "SATISFIED"),
        ("outcome", True),
    ],
)
def test_result_rejects_malformed_fields(field_name: str, bad: object) -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationResultError):
        _result(**{field_name: bad})


def test_result_validator_revalidates_post_construction_forgery() -> None:
    c = _contract()
    result = _result()
    object.__setattr__(result, "authority_fingerprint", "b" * 63)
    with pytest.raises(c.InvalidNumericEvaluationResultError):
        c.validate_numeric_evaluation_result(result)


def test_result_validator_rejects_foreign_type() -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationResultError):
        c.validate_numeric_evaluation_result(object())


def test_result_validator_revalidates_forged_nested_grading_spec_ref() -> None:
    c = _contract()
    result = _result()
    object.__setattr__(result.grading_spec_ref, "version", 0)
    with pytest.raises(c.InvalidNumericEvaluationResultError):
        c.validate_numeric_evaluation_result(result)


def test_result_validator_revalidates_forged_outcome() -> None:
    c = _contract()
    result = _result()
    object.__setattr__(result, "outcome", "SATISFIED")
    with pytest.raises(c.InvalidNumericEvaluationResultError):
        c.validate_numeric_evaluation_result(result)
