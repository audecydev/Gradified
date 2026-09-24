from __future__ import annotations

import hashlib

import pytest

from grading.contracts.numeric_authority import (
    MAX_NUMERIC_AUTHORITY_CONDITIONS,
    MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES,
    MAX_NUMERIC_DECIMAL_TEXT_CHARACTERS,
    MAX_NUMERIC_IDENTIFIER_TEXT_CHARACTERS,
    MAX_NUMERIC_PROJECTION_ENTRIES,
    InvalidNumericAuthorityApprovalError,
    InvalidNumericEvaluationAuthorityError,
    NumericAbsoluteToleranceCondition,
    NumericAuthorityApproval,
    NumericCriterionProjection,
    NumericEvaluationAuthority,
    NumericExactCondition,
    numeric_authority_canonical_bytes,
    numeric_authority_fingerprint,
)
from grading.contracts.paper_aggregation import GradingSpecRef


class _ExactSubclass(NumericExactCondition):
    pass


class _ToleranceSubclass(NumericAbsoluteToleranceCondition):
    pass


def _projection(criterion_id: str, selected_level: str) -> NumericCriterionProjection:
    return NumericCriterionProjection(criterion_id, selected_level)


def _authority(
    *,
    conditions: tuple[object, ...] | None = None,
    satisfied_projection: tuple[NumericCriterionProjection, ...] | None = None,
    not_satisfied_projection: tuple[NumericCriterionProjection, ...] | None = None,
) -> NumericEvaluationAuthority:
    if conditions is None:
        conditions = (NumericExactCondition("5"),)
    if satisfied_projection is None:
        satisfied_projection = (_projection("C1", "FULL"),)
    if not_satisfied_projection is None:
        not_satisfied_projection = (_projection("C1", "NOT_MET"),)
    return NumericEvaluationAuthority(
        evaluation_authority_profile_version="1",
        grading_spec_ref=GradingSpecRef("SPEC-1", 1),
        question_id="Q1",
        rubric_id="R-Q1",
        rubric_version=1,
        finalized_question_hash="b" * 64,
        source_content_hash="c" * 64,
        compiled_authority_hash="d" * 64,
        conditions=conditions,  # type: ignore[arg-type]
        satisfied_projection=satisfied_projection,
        not_satisfied_projection=not_satisfied_projection,
    )


def test_distinct_value_equal_conditions_are_rejected_as_exact_duplicates() -> None:
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _authority(conditions=(NumericExactCondition("5"), NumericExactCondition("5")))
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _authority(
            conditions=(
                NumericAbsoluteToleranceCondition("5", "0.2"),
                NumericAbsoluteToleranceCondition("5", "0.2"),
            )
        )


def test_profile_v1_condition_type_universe_is_exact_not_subclass_or_duck_typed() -> None:
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _ExactSubclass("5")
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _ToleranceSubclass("5", "0.2")

    class ForeignCondition:
        expected_value = "5"

    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _authority(conditions=(ForeignCondition(),))


def test_resource_boundaries_are_inclusive_at_profile_limits() -> None:
    assert MAX_NUMERIC_AUTHORITY_CONDITIONS == 32
    assert MAX_NUMERIC_DECIMAL_TEXT_CHARACTERS == 128
    assert MAX_NUMERIC_PROJECTION_ENTRIES == 512
    assert MAX_NUMERIC_IDENTIFIER_TEXT_CHARACTERS == 512

    decimal_at_limit = "1" * 128
    assert NumericExactCondition(decimal_at_limit).expected_value == decimal_at_limit
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        NumericExactCondition("1" * 129)

    conditions = tuple(NumericExactCondition(str(i + 1)) for i in range(32))
    assert len(_authority(conditions=conditions).conditions) == 32
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _authority(conditions=conditions + (NumericExactCondition("33"),))

    at_limit_id = "C" * 512
    assert NumericCriterionProjection(at_limit_id, "FULL").criterion_id == at_limit_id
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        NumericCriterionProjection("C" * 513, "FULL")

    teacher_at_limit = "t" * 512
    assert NumericAuthorityApproval(teacher_at_limit, "a" * 64).teacher_ref == teacher_at_limit
    with pytest.raises(InvalidNumericAuthorityApprovalError):
        NumericAuthorityApproval("t" * 513, "a" * 64)


def test_projection_count_boundary_accepts_512_and_rejects_513_before_resolution() -> None:
    satisfied = tuple(_projection(f"C{i}", "F") for i in range(512))
    not_satisfied = tuple(_projection(f"C{i}", "N") for i in range(512))
    authority = _authority(
        satisfied_projection=satisfied,
        not_satisfied_projection=not_satisfied,
    )
    assert len(authority.satisfied_projection) == 512

    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _authority(
            satisfied_projection=satisfied + (_projection("C512", "F"),),
            not_satisfied_projection=not_satisfied + (_projection("C512", "N"),),
        )


def _payload_boundary_authority(*, plus_one_byte: bool) -> NumericEvaluationAuthority:
    # With profile-v1 canonical JSON, this exact construction serializes to
    # 65536 bytes. Adding one character to one selected_level makes 65537.
    satisfied: list[NumericCriterionProjection] = []
    not_satisfied: list[NumericCriterionProjection] = []
    for index in range(512):
        sat_extra = 159 if index == 0 and plus_one_byte else 158 if index == 0 else 0
        not_extra = 493 if index == 0 else 0
        satisfied.append(
            _projection(f"C{index}", "F" + "x" * 18 + "y" * sat_extra)
        )
        not_satisfied.append(
            _projection(f"C{index}", "N" + "x" * 18 + "y" * not_extra)
        )
    return _authority(
        satisfied_projection=tuple(satisfied),
        not_satisfied_projection=tuple(not_satisfied),
    )


def test_canonical_payload_byte_limit_accepts_65536_and_rejects_65537() -> None:
    assert MAX_NUMERIC_AUTHORITY_PAYLOAD_BYTES == 65536
    authority = _payload_boundary_authority(plus_one_byte=False)
    assert len(numeric_authority_canonical_bytes(authority)) == 65536

    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _payload_boundary_authority(plus_one_byte=True)


def test_profile_v1_golden_canonical_bytes_and_fingerprint_are_frozen() -> None:
    authority = NumericEvaluationAuthority(
        evaluation_authority_profile_version="1",
        grading_spec_ref=GradingSpecRef("SPEC-1", 1),
        question_id="Q1",
        rubric_id="R-Q1",
        rubric_version=1,
        finalized_question_hash="b" * 64,
        source_content_hash="c" * 64,
        compiled_authority_hash="d" * 64,
        conditions=(
            NumericAbsoluteToleranceCondition("10", "0.2"),
            NumericExactCondition("5"),
        ),
        satisfied_projection=(
            _projection("C1", "FULL"),
            _projection("C2", "FULL"),
        ),
        not_satisfied_projection=(
            _projection("C1", "NOT_MET"),
            _projection("C2", "NOT_MET"),
        ),
    )
    expected = (
        b'{"compiled_authority_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
        b'"conditions":[{"condition_type":"ABSOLUTE_TOLERANCE","expected_value":"10","tolerance":"0.2"},'
        b'{"condition_type":"EXACT","expected_value":"5"}],'
        b'"evaluation_authority_profile_version":"1",'
        b'"finalized_question_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
        b'"grading_spec_ref":{"id":"SPEC-1","version":1},'
        b'"not_satisfied_projection":[{"criterion_id":"C1","selected_level":"NOT_MET"},'
        b'{"criterion_id":"C2","selected_level":"NOT_MET"}],'
        b'"question_id":"Q1","rubric_id":"R-Q1","rubric_version":1,'
        b'"satisfied_projection":[{"criterion_id":"C1","selected_level":"FULL"},'
        b'{"criterion_id":"C2","selected_level":"FULL"}],'
        b'"schema":"gradified-numeric-evaluation-authority-v1",'
        b'"source_content_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}'
    )
    assert numeric_authority_canonical_bytes(authority) == expected
    assert hashlib.sha256(expected).hexdigest() == (
        "f91778a88d0b280ea18b85e78bb2375596b21fa83ca032ee704fc2b523809352"
    )
    assert numeric_authority_fingerprint(authority) == hashlib.sha256(expected).hexdigest()


def test_deleted_nested_fields_fail_as_domain_errors_not_attribute_errors() -> None:
    condition = NumericExactCondition("5")
    object.__delattr__(condition, "expected_value")
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        _authority(conditions=(condition,))

    authority = _authority()
    object.__delattr__(authority, "source_content_hash")
    with pytest.raises(InvalidNumericEvaluationAuthorityError):
        numeric_authority_fingerprint(authority)
