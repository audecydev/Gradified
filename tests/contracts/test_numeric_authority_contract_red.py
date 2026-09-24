from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from importlib import import_module

import pytest

from grading.contracts.paper_aggregation import GradingSpecRef


_VALID_HASH = "a" * 64


class _StringSubclass(str):
    pass


class _TupleSubclass(tuple):
    pass


def _contract():
    # Deliberately imported lazily so the first causal RED can prove the
    # existing repository is healthy before it reaches the missing N1 boundary.
    return import_module("grading.contracts.numeric_authority")


def _projection(criterion_id: object = "C1", selected_level: object = "FULL"):
    c = _contract()
    return c.NumericCriterionProjection(criterion_id, selected_level)


def _exact(expected_value: object = "5"):
    c = _contract()
    return c.NumericExactCondition(expected_value)


def _tolerance(expected_value: object = "5", tolerance: object = "0.2"):
    c = _contract()
    return c.NumericAbsoluteToleranceCondition(expected_value, tolerance)


def _authority(**overrides: object):
    c = _contract()
    values: dict[str, object] = {
        "evaluation_authority_profile_version": c.NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
        "grading_spec_ref": GradingSpecRef("SPEC-1", 1),
        "question_id": "Q1",
        "rubric_id": "R-Q1",
        "rubric_version": 1,
        "finalized_question_hash": "b" * 64,
        "source_content_hash": "c" * 64,
        "compiled_authority_hash": "d" * 64,
        "conditions": (_exact("5"), _tolerance("10", "0.2")),
        "satisfied_projection": (
            _projection("C1", "FULL"),
            _projection("C2", "FULL"),
        ),
        "not_satisfied_projection": (
            _projection("C1", "NOT_MET"),
            _projection("C2", "NOT_MET"),
        ),
    }
    values.update(overrides)
    return c.NumericEvaluationAuthority(**values)


def test_red1_existing_spec_ref_fixture_is_valid_before_missing_n1_import() -> None:
    spec = GradingSpecRef("SPEC-1", 1)
    assert spec.id == "SPEC-1"
    assert spec.version == 1

    # Causal RED: N1 is BUILD-authorized but this production contract does not
    # yet exist on the qualified prerequisite baseline.
    c = _contract()
    assert c.NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION == "1"


def test_profile_and_schema_literals_are_domain_separated_from_scoring_numeric_profile() -> None:
    c = _contract()
    assert c.NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION == "1"
    assert c.NUMERIC_EVALUATION_AUTHORITY_SCHEMA == "gradified-numeric-evaluation-authority-v1"


def test_n1_error_taxonomy_has_distinct_local_contract_categories() -> None:
    c = _contract()
    categories = (
        c.InvalidNumericEvaluationAuthorityError,
        c.InvalidNumericExpectedBindingError,
        c.InvalidNumericAuthorityApprovalError,
        c.UnsupportedNumericAuthorityProfileError,
    )
    assert all(issubclass(category, c.NumericAuthorityError) for category in categories)
    assert len(set(categories)) == len(categories)


def test_authority_contract_surface_contains_no_score_student_evidence_or_self_fingerprint() -> None:
    c = _contract()
    assert {field.name for field in fields(c.NumericCriterionProjection)} == {
        "criterion_id",
        "selected_level",
    }
    assert {field.name for field in fields(c.NumericExactCondition)} == {"expected_value"}
    assert {field.name for field in fields(c.NumericAbsoluteToleranceCondition)} == {
        "expected_value",
        "tolerance",
    }
    assert {field.name for field in fields(c.NumericEvaluationAuthority)} == {
        "evaluation_authority_profile_version",
        "grading_spec_ref",
        "question_id",
        "rubric_id",
        "rubric_version",
        "finalized_question_hash",
        "source_content_hash",
        "compiled_authority_hash",
        "conditions",
        "satisfied_projection",
        "not_satisfied_projection",
    }
    forbidden = {
        "score",
        "marks",
        "awarded_marks",
        "student_value",
        "student_evidence",
        "evidence_refs",
        "authority_fingerprint",
    }
    assert not ({field.name for field in fields(c.NumericEvaluationAuthority)} & forbidden)


def test_expected_binding_and_approval_surfaces_are_minimal() -> None:
    c = _contract()
    assert {field.name for field in fields(c.NumericNotAuthorizedBinding)} == {
        "grading_spec_ref",
        "question_id",
    }
    assert {field.name for field in fields(c.NumericBoundAuthorityBinding)} == {
        "grading_spec_ref",
        "question_id",
        "evaluation_authority_profile_version",
        "authority_fingerprint",
    }
    assert {field.name for field in fields(c.NumericAuthorityApproval)} == {
        "teacher_ref",
        "numeric_authority_fingerprint",
    }


@pytest.mark.parametrize(
    "value",
    (
        "0",
        "5",
        "-5",
        "0.5",
        "-0.5",
        "12.34",
        "100.01",
        "0.0000001",
        "-999999.125",
    ),
)
def test_canonical_decimal_examples_are_admitted(value: str) -> None:
    assert _exact(value).expected_value == value


@pytest.mark.parametrize(
    "value",
    (
        "",
        "+5",
        "05",
        "00",
        "1.0",
        "1.20",
        "0.0",
        "-0",
        "-0.0",
        ".5",
        "5.",
        " 5",
        "5 ",
        "1e3",
        "1E3",
        "NaN",
        "Infinity",
        "-Infinity",
        5,
        5.0,
        _StringSubclass("5"),
    ),
)
def test_noncanonical_or_nonstring_authority_decimal_is_rejected(value: object) -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _exact(value)


def test_decimal_text_length_envelope_is_enforced_before_fingerprinting() -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _exact("1" * 129)


@pytest.mark.parametrize("bad", ("0", "-1", "-0.1", "1.0", 1, None))
def test_absolute_tolerance_requires_strictly_positive_canonical_decimal(bad: object) -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _tolerance("5", bad)


def test_condition_collection_is_exact_nonempty_bounded_tuple() -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(conditions=())
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(conditions=[_exact("5")])
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(conditions=_TupleSubclass((_exact("5"),)))
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(conditions=tuple(_exact(str(i + 1)) for i in range(33)))


def test_exact_duplicate_conditions_are_rejected_but_distinct_overlap_is_not_simplified() -> None:
    c = _contract()
    duplicate = _exact("5")
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(conditions=(duplicate, duplicate))

    # These may overlap mathematically but there is no hidden simplifier or
    # winner because every satisfied condition maps to the same projection.
    item = _authority(conditions=(_exact("5"), _tolerance("5", "0.2")))
    assert len(item.conditions) == 2


def test_projection_requires_exact_nonempty_tuple_identifiers_and_matching_sequences() -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(satisfied_projection=[])
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(satisfied_projection=_TupleSubclass((_projection("C1", "FULL"),)))
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(satisfied_projection=())
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(
            satisfied_projection=(_projection("C1", "FULL"), _projection("C1", "FULL"))
        )
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(
            satisfied_projection=(_projection("C1", "FULL"), _projection("C2", "FULL")),
            not_satisfied_projection=(_projection("C2", "NOT_MET"), _projection("C1", "NOT_MET")),
        )


def test_projection_entry_rejects_noncanonical_identifiers() -> None:
    c = _contract()
    for value in ("", " C1", "C1 ", 1, None, _StringSubclass("C1")):
        with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
            _projection(value, "FULL")
    for value in ("", " FULL", "FULL ", 1, None, _StringSubclass("FULL")):
        with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
            _projection("C1", value)


def test_projection_cardinality_and_identifier_length_resource_bounds_are_enforced() -> None:
    c = _contract()
    too_many = tuple(_projection(f"C{i}", "FULL") for i in range(513))
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(
            satisfied_projection=too_many,
            not_satisfied_projection=tuple(
                _projection(f"C{i}", "NOT_MET") for i in range(513)
            ),
        )
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _projection("C" * 513, "FULL")


@pytest.mark.parametrize(
    "field_name",
    ("finalized_question_hash", "source_content_hash", "compiled_authority_hash"),
)
@pytest.mark.parametrize("bad", ("", "a" * 63, "a" * 65, "A" * 64, "g" * 64, 1, None))
def test_authority_hash_bindings_require_canonical_lowercase_sha256(
    field_name: str,
    bad: object,
) -> None:
    c = _contract()
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(**{field_name: bad})


def test_authority_requires_exact_supported_profile_spec_ref_identifiers_and_positive_version() -> None:
    c = _contract()
    with pytest.raises(c.UnsupportedNumericAuthorityProfileError):
        _authority(evaluation_authority_profile_version="2")
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(grading_spec_ref=("SPEC-1", 1))
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(question_id=" Q1")
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(rubric_id="")
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(rubric_version=0)
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(rubric_version=True)


def test_expected_binding_requires_explicit_exact_state_and_never_models_missing_as_not_authorized() -> None:
    c = _contract()
    not_authorized = c.NumericNotAuthorizedBinding(GradingSpecRef("SPEC-1", 1), "Q1")
    bound = c.NumericBoundAuthorityBinding(
        GradingSpecRef("SPEC-1", 1),
        "Q1",
        c.NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
        _VALID_HASH,
    )
    assert type(not_authorized) is c.NumericNotAuthorizedBinding
    assert type(bound) is c.NumericBoundAuthorityBinding

    with pytest.raises(c.InvalidNumericExpectedBindingError):
        c.NumericNotAuthorizedBinding(("SPEC-1", 1), "Q1")
    with pytest.raises(c.UnsupportedNumericAuthorityProfileError):
        c.NumericBoundAuthorityBinding(GradingSpecRef("SPEC-1", 1), "Q1", "2", _VALID_HASH)
    with pytest.raises(c.InvalidNumericExpectedBindingError):
        c.NumericBoundAuthorityBinding(GradingSpecRef("SPEC-1", 1), "Q1", "1", "A" * 64)


def test_subordinate_approval_binds_exact_fingerprint_but_does_not_authenticate_teacher() -> None:
    c = _contract()
    item = c.NumericAuthorityApproval("teacher:42", _VALID_HASH)
    assert item.teacher_ref == "teacher:42"
    assert item.numeric_authority_fingerprint == _VALID_HASH
    for bad_teacher in ("", " teacher:42", "teacher:42 ", 1, None):
        with pytest.raises(c.InvalidNumericAuthorityApprovalError):
            c.NumericAuthorityApproval(bad_teacher, _VALID_HASH)
    with pytest.raises(c.InvalidNumericAuthorityApprovalError):
        c.NumericAuthorityApproval("teacher:42", "A" * 64)


def test_contract_objects_are_frozen() -> None:
    c = _contract()
    authority = _authority()
    approval = c.NumericAuthorityApproval("teacher:42", _VALID_HASH)
    binding = c.NumericBoundAuthorityBinding(
        GradingSpecRef("SPEC-1", 1), "Q1", "1", _VALID_HASH
    )
    with pytest.raises(FrozenInstanceError):
        authority.question_id = "Q2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        approval.teacher_ref = "teacher:other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        binding.authority_fingerprint = "b" * 64  # type: ignore[misc]


def test_condition_order_is_non_authoritative_for_fingerprinting() -> None:
    c = _contract()
    a = _authority(conditions=(_exact("4.8"), _tolerance("5", "0.2")))
    b = _authority(conditions=(_tolerance("5", "0.2"), _exact("4.8")))
    assert c.numeric_authority_fingerprint(a) == c.numeric_authority_fingerprint(b)


def test_projection_order_is_authoritative_for_fingerprinting() -> None:
    c = _contract()
    a = _authority()
    b = _authority(
        satisfied_projection=(_projection("C2", "FULL"), _projection("C1", "FULL")),
        not_satisfied_projection=(_projection("C2", "NOT_MET"), _projection("C1", "NOT_MET")),
    )
    assert c.numeric_authority_fingerprint(a) != c.numeric_authority_fingerprint(b)


def test_fingerprint_external_form_is_canonical_lowercase_sha256() -> None:
    c = _contract()
    fingerprint = c.numeric_authority_fingerprint(_authority())
    assert type(fingerprint) is str
    assert len(fingerprint) == 64
    assert fingerprint == fingerprint.lower()
    assert all(ch in "0123456789abcdef" for ch in fingerprint)


def test_fingerprint_boundary_revalidates_current_payload_instead_of_trusting_construction_history() -> None:
    c = _contract()
    authority = _authority()
    object.__setattr__(authority, "source_content_hash", "A" * 64)
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        c.numeric_authority_fingerprint(authority)


def test_canonical_payload_resource_limit_is_enforced_before_digest() -> None:
    c = _contract()
    # Stay inside projection cardinality and per-field length while deliberately
    # making the canonical authority payload exceed the 65536-byte profile cap.
    satisfied = tuple(_projection(f"C{i:03d}-" + "x" * 500, "FULL") for i in range(80))
    not_satisfied = tuple(
        _projection(f"C{i:03d}-" + "x" * 500, "NOT_MET") for i in range(80)
    )
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        _authority(
            satisfied_projection=satisfied,
            not_satisfied_projection=not_satisfied,
        )
