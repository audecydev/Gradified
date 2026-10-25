from __future__ import annotations

from importlib import import_module

import pytest

from grading.contracts.numeric_authority import (
    NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
    NumericAbsoluteToleranceCondition,
    NumericCriterionProjection,
    NumericEvaluationAuthority,
    NumericExactCondition,
    numeric_authority_fingerprint,
)
from grading.contracts.numeric_evidence import (
    NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
    AdmittedNumericScalar,
)
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.numeric_authority import ResolvedNumericAuthority


_HASH_B = "b" * 64
_HASH_C = "c" * 64
_HASH_D = "d" * 64


def _module():
    return import_module("grading.numeric_evaluator")


def _authority(*conditions: object) -> NumericEvaluationAuthority:
    if not conditions:
        conditions = (NumericExactCondition("5"),)
    return NumericEvaluationAuthority(
        evaluation_authority_profile_version=NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
        grading_spec_ref=GradingSpecRef("SPEC-1", 1),
        question_id="Q1",
        rubric_id="R-Q1",
        rubric_version=1,
        finalized_question_hash=_HASH_B,
        source_content_hash=_HASH_C,
        compiled_authority_hash=_HASH_D,
        conditions=conditions,  # type: ignore[arg-type]
        satisfied_projection=(NumericCriterionProjection("C1", "FULL"),),
        not_satisfied_projection=(NumericCriterionProjection("C1", "NOT_MET"),),
    )


def _resolved(*conditions: object) -> ResolvedNumericAuthority:
    authority = _authority(*conditions)
    return ResolvedNumericAuthority(
        grading_spec_ref=authority.grading_spec_ref,
        question_id=authority.question_id,
        authority_fingerprint=numeric_authority_fingerprint(authority),
        authority=authority,
    )


def _observation(value: str = "5", **overrides: object) -> AdmittedNumericScalar:
    values: dict[str, object] = {
        "admission_profile_version": NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
        "submission_ref": "submission-1",
        "ocr_provenance": "ocr-run-1",
        "question_id": "Q1",
        "answer_scope_ref": "scope-Q1",
        "evidence_ref": "Q1-B1",
        "canonical_value": value,
    }
    values.update(overrides)
    return AdmittedNumericScalar(**values)  # type: ignore[arg-type]


def _outcome(value: str, *conditions: object):
    n = _module()
    return n.evaluate_numeric_scalar(
        resolved_authority=_resolved(*conditions),
        observation=_observation(value),
    ).outcome


def test_red1_existing_n1_n2_inputs_are_valid_before_missing_n3_import() -> None:
    resolved = _resolved(NumericExactCondition("5"))
    observation = _observation("5")
    assert resolved.question_id == observation.question_id == "Q1"
    assert callable(_module().evaluate_numeric_scalar)


def test_exact_condition_satisfied() -> None:
    c = import_module("grading.contracts.numeric_evaluation")
    assert _outcome("5", NumericExactCondition("5")) is c.NumericConditionOutcome.SATISFIED


def test_exact_condition_not_satisfied() -> None:
    c = import_module("grading.contracts.numeric_evaluation")
    assert _outcome("5.01", NumericExactCondition("5")) is c.NumericConditionOutcome.NOT_SATISFIED


@pytest.mark.parametrize(
    ("observed", "expected", "tolerance", "satisfied"),
    [
        ("5.2", "5", "0.2", True),
        ("4.8", "5", "0.2", True),
        ("5.2001", "5", "0.2", False),
        ("4.7999", "5", "0.2", False),
        ("-1.25", "-1.2", "0.05", True),
        ("-1.26", "-1.2", "0.05", False),
        ("-0.03", "0.02", "0.05", True),
        ("-0.031", "0.02", "0.05", False),
        ("0", "0", "0.0001", True),
        ("999999.999", "1000000", "0.001", True),
    ],
)
def test_absolute_tolerance_is_inclusive_and_exact(
    observed: str,
    expected: str,
    tolerance: str,
    satisfied: bool,
) -> None:
    c = import_module("grading.contracts.numeric_evaluation")
    result = _outcome(
        observed,
        NumericAbsoluteToleranceCondition(expected, tolerance),
    )
    expected_outcome = (
        c.NumericConditionOutcome.SATISFIED
        if satisfied
        else c.NumericConditionOutcome.NOT_SATISFIED
    )
    assert result is expected_outcome


def test_conditions_are_or_alternatives_and_first_nonmatch_does_not_block_later_match() -> None:
    c = import_module("grading.contracts.numeric_evaluation")
    result = _outcome(
        "10",
        NumericExactCondition("5"),
        NumericAbsoluteToleranceCondition("10.1", "0.1"),
    )
    assert result is c.NumericConditionOutcome.SATISFIED


def test_multiple_matching_conditions_still_produce_only_satisfied_not_a_winner() -> None:
    c = import_module("grading.contracts.numeric_evaluation")
    result = _module().evaluate_numeric_scalar(
        resolved_authority=_resolved(
            NumericExactCondition("5"),
            NumericAbsoluteToleranceCondition("5", "0.1"),
        ),
        observation=_observation("5"),
    )
    assert result.outcome is c.NumericConditionOutcome.SATISFIED
    assert not hasattr(result, "matched_condition_index")


def test_condition_order_does_not_change_result() -> None:
    first = (
        NumericExactCondition("5"),
        NumericAbsoluteToleranceCondition("10", "0.2"),
    )
    second = tuple(reversed(first))
    assert _outcome("10.1", *first) == _outcome("10.1", *second)


def test_result_preserves_exact_authority_and_evidence_provenance() -> None:
    resolved = _resolved(NumericExactCondition("5"))
    observation = _observation("5")
    result = _module().evaluate_numeric_scalar(
        resolved_authority=resolved,
        observation=observation,
    )
    assert result.grading_spec_ref == resolved.grading_spec_ref
    assert result.authority_fingerprint == resolved.authority_fingerprint
    assert result.question_id == "Q1"
    assert result.submission_ref == observation.submission_ref
    assert result.ocr_provenance == observation.ocr_provenance
    assert result.answer_scope_ref == observation.answer_scope_ref
    assert result.evidence_ref == observation.evidence_ref
    assert result.admission_profile_version == observation.admission_profile_version


def test_question_mismatch_is_binding_error_not_not_satisfied() -> None:
    n = _module()
    with pytest.raises(n.NumericEvaluationEvidenceBindingError):
        n.evaluate_numeric_scalar(
            resolved_authority=_resolved(NumericExactCondition("5")),
            observation=_observation("5", question_id="Q2"),
        )


def test_foreign_top_level_inputs_are_rejected() -> None:
    n = _module()
    with pytest.raises(n.NumericEvaluationAuthorityBindingError):
        n.evaluate_numeric_scalar(resolved_authority=object(), observation=_observation("5"))  # type: ignore[arg-type]
    with pytest.raises(n.NumericEvaluationEvidenceBindingError):
        n.evaluate_numeric_scalar(resolved_authority=_resolved(), observation=object())  # type: ignore[arg-type]


def test_forged_resolved_authority_fingerprint_is_rejected() -> None:
    n = _module()
    resolved = _resolved()
    object.__setattr__(resolved, "authority_fingerprint", "e" * 64)
    with pytest.raises(n.NumericEvaluationAuthorityBindingError):
        n.evaluate_numeric_scalar(resolved_authority=resolved, observation=_observation())


def test_forged_resolved_identity_is_rejected_even_with_well_formed_values() -> None:
    n = _module()
    resolved = _resolved()
    object.__setattr__(resolved, "question_id", "Q2")
    with pytest.raises(n.NumericEvaluationAuthorityBindingError):
        n.evaluate_numeric_scalar(resolved_authority=resolved, observation=_observation())


def test_forged_authority_payload_is_rejected_before_comparison() -> None:
    n = _module()
    resolved = _resolved()
    object.__setattr__(resolved.authority.conditions[0], "expected_value", "+5")
    with pytest.raises(n.NumericEvaluationAuthorityBindingError):
        n.evaluate_numeric_scalar(resolved_authority=resolved, observation=_observation())


def test_forged_observation_is_rejected_before_comparison() -> None:
    n = _module()
    observation = _observation()
    object.__setattr__(observation, "canonical_value", "+5")
    with pytest.raises(n.NumericEvaluationEvidenceBindingError):
        n.evaluate_numeric_scalar(resolved_authority=_resolved(), observation=observation)


def test_n3_result_contains_no_projection_marks_or_score() -> None:
    result = _module().evaluate_numeric_scalar(
        resolved_authority=_resolved(),
        observation=_observation(),
    )
    for name in ("projection", "criterion_id", "selected_level", "marks", "score", "awarded_marks"):
        assert not hasattr(result, name)
