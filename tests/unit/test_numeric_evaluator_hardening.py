from __future__ import annotations

import pytest

from grading.contracts.numeric_authority import (
    NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
    NumericAbsoluteToleranceCondition,
    NumericCriterionProjection,
    NumericEvaluationAuthority,
    NumericExactCondition,
    numeric_authority_fingerprint,
)
from grading.contracts.numeric_evaluation import NumericConditionOutcome
from grading.contracts.numeric_evidence import (
    NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
    AdmittedNumericScalar,
)
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.numeric_authority import ResolvedNumericAuthority
from grading.numeric_evaluator import (
    NumericEvaluationAuthorityBindingError,
    NumericEvaluationEvidenceBindingError,
    evaluate_numeric_scalar,
)


def _authority(*conditions: object) -> NumericEvaluationAuthority:
    return NumericEvaluationAuthority(
        evaluation_authority_profile_version=NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
        grading_spec_ref=GradingSpecRef("SPEC-1", 1),
        question_id="Q1",
        rubric_id="R-Q1",
        rubric_version=1,
        finalized_question_hash="b" * 64,
        source_content_hash="c" * 64,
        compiled_authority_hash="d" * 64,
        conditions=conditions or (NumericExactCondition("5"),),  # type: ignore[arg-type]
        satisfied_projection=(NumericCriterionProjection("C1", "FULL"),),
        not_satisfied_projection=(NumericCriterionProjection("C1", "NOT_MET"),),
    )


def _resolved(*conditions: object) -> ResolvedNumericAuthority:
    authority = _authority(*conditions)
    return ResolvedNumericAuthority(
        authority.grading_spec_ref,
        authority.question_id,
        numeric_authority_fingerprint(authority),
        authority,
    )


def _observation(value: str) -> AdmittedNumericScalar:
    return AdmittedNumericScalar(
        NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
        "submission-1",
        "ocr-run-1",
        "Q1",
        "scope-Q1",
        "Q1-B1",
        value,
    )


def _evaluate(value: str, *conditions: object) -> NumericConditionOutcome:
    return evaluate_numeric_scalar(
        resolved_authority=_resolved(*conditions),
        observation=_observation(value),
    ).outcome


def test_maximum_length_integer_values_compare_exactly_without_float() -> None:
    value = "9" * 128
    assert _evaluate(value, NumericExactCondition(value)) is NumericConditionOutcome.SATISFIED


def test_maximum_length_fractional_value_compares_exactly() -> None:
    value = "0." + ("0" * 125) + "1"
    assert len(value) == 128
    assert _evaluate(value, NumericExactCondition(value)) is NumericConditionOutcome.SATISFIED


def test_large_integer_one_unit_difference_is_not_equal() -> None:
    expected = "9" * 128
    observed = ("9" * 127) + "8"
    assert _evaluate(observed, NumericExactCondition(expected)) is NumericConditionOutcome.NOT_SATISFIED


def test_absolute_tolerance_handles_very_different_scales_exactly() -> None:
    expected = "9999999999999999999999999999999999999999"
    tolerance = "0." + ("0" * 60) + "1"
    observed = expected + "." + ("0" * 60) + "1"
    assert _evaluate(
        observed,
        NumericAbsoluteToleranceCondition(expected, tolerance),
    ) is NumericConditionOutcome.SATISFIED


def test_all_32_authorized_conditions_can_be_evaluated_and_last_can_match() -> None:
    conditions = tuple(NumericExactCondition(str(index)) for index in range(32))
    assert _evaluate("31", *conditions) is NumericConditionOutcome.SATISFIED


def test_all_32_authorized_conditions_can_fail_without_becoming_technical_error() -> None:
    conditions = tuple(NumericExactCondition(str(index)) for index in range(32))
    assert _evaluate("100", *conditions) is NumericConditionOutcome.NOT_SATISFIED


class _ExplodingForeignAuthority:
    @property
    def conditions(self):
        raise AssertionError("foreign authority must never be traversed")


def test_foreign_nested_authority_is_type_rejected_before_condition_dispatch() -> None:
    resolved = _resolved()
    object.__setattr__(resolved, "authority", _ExplodingForeignAuthority())
    with pytest.raises(NumericEvaluationAuthorityBindingError) as exc_info:
        evaluate_numeric_scalar(resolved_authority=resolved, observation=_observation("5"))
    assert not isinstance(exc_info.value.__cause__, AssertionError)


class _ExplodingForeignObservation:
    @property
    def canonical_value(self):
        raise AssertionError("foreign observation must never be traversed")


def test_foreign_observation_is_type_rejected_before_value_dispatch() -> None:
    with pytest.raises(NumericEvaluationEvidenceBindingError) as exc_info:
        evaluate_numeric_scalar(
            resolved_authority=_resolved(),
            observation=_ExplodingForeignObservation(),  # type: ignore[arg-type]
        )
    assert not isinstance(exc_info.value.__cause__, AssertionError)


def test_post_construction_forged_grading_spec_ref_is_revalidated() -> None:
    resolved = _resolved()
    object.__setattr__(resolved.grading_spec_ref, "version", 0)
    with pytest.raises(NumericEvaluationAuthorityBindingError):
        evaluate_numeric_scalar(resolved_authority=resolved, observation=_observation("5"))


def test_technical_integer_conversion_is_never_used_for_unbounded_input() -> None:
    # N1/N2 cap canonical decimal text at 128 characters. This proves the N3
    # arithmetic path remains far below CPython's decimal integer conversion limit.
    value = "1" + ("0" * 127)
    assert len(value) == 128
    assert _evaluate(value, NumericExactCondition(value)) is NumericConditionOutcome.SATISFIED


def test_exact_comparison_matches_independent_fraction_oracle_on_representative_grid() -> None:
    from fractions import Fraction

    values = ("-10", "-1.25", "-0.03", "0", "0.02", "1.2", "5", "10.125")
    for observed in values:
        for expected in values:
            actual = _evaluate(observed, NumericExactCondition(expected))
            oracle = Fraction(observed) == Fraction(expected)
            assert (actual is NumericConditionOutcome.SATISFIED) is oracle


def test_absolute_tolerance_matches_independent_fraction_oracle_on_representative_grid() -> None:
    from fractions import Fraction

    values = ("-10", "-1.25", "-0.03", "0", "0.02", "1.2", "5", "10.125")
    tolerances = ("0.001", "0.05", "0.2", "1")
    for observed in values:
        for expected in values:
            for tolerance in tolerances:
                actual = _evaluate(
                    observed,
                    NumericAbsoluteToleranceCondition(expected, tolerance),
                )
                oracle = abs(Fraction(observed) - Fraction(expected)) <= Fraction(tolerance)
                assert (actual is NumericConditionOutcome.SATISFIED) is oracle
