from __future__ import annotations

import pytest

from grading.contracts.capability import (
    EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION,
    MAX_CAPABILITY_DESCRIPTION_CHARACTERS,
    MAX_CAPABILITY_IDENTIFIER_CHARACTERS,
    MAX_CAPABILITY_TUPLE_ENTRIES,
    EvaluatorCapabilityRecord,
    EvaluatorCapabilityRef,
    EvaluatorCapabilityStatus,
    InvalidEvaluatorCapabilityRecordError,
    InvalidEvaluatorCapabilityRefError,
    UnsupportedEvaluatorCapabilityRecordSchemaError,
    validate_evaluator_capability_record,
    validate_evaluator_capability_ref,
)
from grading.contracts.evaluation import EvaluatorMetadata


def _ref(
    *,
    evaluator_id: str = "gradified-deterministic-numeric",
    evaluator_version: str = "1",
    record_version: int = 1,
) -> EvaluatorCapabilityRef:
    return EvaluatorCapabilityRef(
        evaluator_metadata=EvaluatorMetadata(
            evaluator_id=evaluator_id,
            version=evaluator_version,
        ),
        record_version=record_version,
    )


def _record(**overrides: object) -> EvaluatorCapabilityRecord:
    values: dict[str, object] = {
        "schema_version": "1",
        "capability_ref": _ref(),
        "status": EvaluatorCapabilityStatus.PILOT,
        "supported_answer_types": ("NUMERIC",),
        "supported_languages": ("en",),
        "supported_modalities": ("TEXT",),
        "tested_grade_range": "grades-6-12",
        "domain_scope": "bounded-unitless-numeric",
        "verification_mechanisms": ("deterministic-comparison",),
        "benchmark_version": "bench-v1",
        "known_failure_modes": ("units-unsupported",),
        "cost_profile": "deterministic-no-provider-call",
        "latency_profile": "bounded-local-compute",
    }
    values.update(overrides)
    return EvaluatorCapabilityRecord(**values)  # type: ignore[arg-type]


def _mutate(value: object, field_name: str, replacement: object) -> object:
    object.__setattr__(value, field_name, replacement)
    return value


def test_schema_and_resource_constants_are_frozen_v1() -> None:
    assert EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION == "1"
    assert MAX_CAPABILITY_IDENTIFIER_CHARACTERS == 128
    assert MAX_CAPABILITY_TUPLE_ENTRIES == 32
    assert MAX_CAPABILITY_DESCRIPTION_CHARACTERS == 512


@pytest.mark.parametrize(
    "status",
    [
        EvaluatorCapabilityStatus.VALIDATED,
        EvaluatorCapabilityStatus.PILOT,
        EvaluatorCapabilityStatus.DISABLED,
    ],
)
def test_all_authoritative_status_values_are_valid_metadata(status: EvaluatorCapabilityStatus) -> None:
    record = _record(status=status)
    assert validate_evaluator_capability_record(record) is record


def test_empty_scope_and_absent_optional_fields_mean_no_claim_and_are_valid() -> None:
    record = _record(
        supported_answer_types=(),
        supported_languages=(),
        supported_modalities=(),
        tested_grade_range=None,
        domain_scope=None,
        verification_mechanisms=(),
        benchmark_version=None,
        known_failure_modes=(),
        cost_profile=None,
        latency_profile=None,
    )
    assert validate_evaluator_capability_record(record) is record


def test_reference_reuses_existing_evaluator_metadata_identity() -> None:
    metadata = EvaluatorMetadata("evaluator-x", "version-x")
    ref = EvaluatorCapabilityRef(metadata, 7)
    assert ref.evaluator_metadata is metadata
    assert validate_evaluator_capability_ref(ref) is ref


@pytest.mark.parametrize("record_version", [True, False, 0, -1])
def test_reference_requires_positive_exact_integer_record_version(record_version: object) -> None:
    with pytest.raises(InvalidEvaluatorCapabilityRefError):
        EvaluatorCapabilityRef(
            evaluator_metadata=EvaluatorMetadata("evaluator-x", "1"),
            record_version=record_version,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("evaluator_id", ""),
        ("evaluator_id", " padded"),
        ("evaluator_id", "padded "),
        ("version", ""),
        ("version", " v1"),
        ("version", "v1 "),
    ],
)
def test_reference_revalidates_nested_evaluator_metadata_current_state(
    field_name: str,
    bad_value: object,
) -> None:
    ref = _ref()
    _mutate(ref.evaluator_metadata, field_name, bad_value)
    with pytest.raises(InvalidEvaluatorCapabilityRefError):
        validate_evaluator_capability_ref(ref)


@pytest.mark.parametrize("field_name", ["evaluator_id", "version"])
def test_reference_bounds_nested_evaluator_identity_text(field_name: str) -> None:
    ref = _ref()
    _mutate(ref.evaluator_metadata, field_name, "x" * (MAX_CAPABILITY_IDENTIFIER_CHARACTERS + 1))
    with pytest.raises(InvalidEvaluatorCapabilityRefError):
        validate_evaluator_capability_ref(ref)


def test_reference_rejects_foreign_nested_metadata_before_attribute_dispatch() -> None:
    class ForeignMetadata:
        @property
        def evaluator_id(self) -> str:
            raise AssertionError("foreign evaluator_id accessed")

    ref = _ref()
    _mutate(ref, "evaluator_metadata", ForeignMetadata())
    with pytest.raises(InvalidEvaluatorCapabilityRefError):
        validate_evaluator_capability_ref(ref)


def test_reference_rejects_post_construction_bool_mutation() -> None:
    ref = _ref()
    _mutate(ref, "record_version", True)
    with pytest.raises(InvalidEvaluatorCapabilityRefError):
        validate_evaluator_capability_ref(ref)


def test_record_rejects_unknown_schema() -> None:
    with pytest.raises(UnsupportedEvaluatorCapabilityRecordSchemaError):
        _record(schema_version="2")


def test_record_rejects_string_status_even_when_text_matches_enum_member() -> None:
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        _record(status="PILOT")


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_answer_types",
        "supported_languages",
        "supported_modalities",
        "verification_mechanisms",
        "known_failure_modes",
    ],
)
def test_tuple_metadata_requires_exact_tuple(field_name: str) -> None:
    record = _record()
    _mutate(record, field_name, ["x"])
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_answer_types",
        "supported_languages",
        "supported_modalities",
        "verification_mechanisms",
        "known_failure_modes",
    ],
)
def test_tuple_metadata_rejects_duplicates(field_name: str) -> None:
    record = _record()
    _mutate(record, field_name, ("duplicate", "duplicate"))
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_answer_types",
        "supported_languages",
        "supported_modalities",
        "verification_mechanisms",
        "known_failure_modes",
    ],
)
def test_tuple_metadata_rejects_more_than_32_entries(field_name: str) -> None:
    record = _record()
    _mutate(record, field_name, tuple(f"v{i}" for i in range(MAX_CAPABILITY_TUPLE_ENTRIES + 1)))
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


@pytest.mark.parametrize(
    ("field_name", "bad_entry"),
    [
        ("supported_answer_types", ""),
        ("supported_languages", " padded"),
        ("supported_modalities", "padded "),
        ("verification_mechanisms", 7),
        ("known_failure_modes", None),
    ],
)
def test_tuple_metadata_rejects_invalid_entries(field_name: str, bad_entry: object) -> None:
    record = _record()
    _mutate(record, field_name, (bad_entry,))
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_answer_types",
        "supported_languages",
        "supported_modalities",
        "verification_mechanisms",
    ],
)
def test_identifier_tuple_entries_are_bounded_to_128(field_name: str) -> None:
    record = _record()
    _mutate(record, field_name, ("x" * (MAX_CAPABILITY_IDENTIFIER_CHARACTERS + 1),))
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


def test_failure_mode_text_is_bounded_to_512() -> None:
    record = _record()
    _mutate(record, "known_failure_modes", ("x" * (MAX_CAPABILITY_DESCRIPTION_CHARACTERS + 1),))
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


@pytest.mark.parametrize(
    "field_name",
    ["tested_grade_range", "domain_scope", "cost_profile", "latency_profile"],
)
def test_optional_descriptions_reject_empty_whitespace_and_oversize(field_name: str) -> None:
    for bad in ("", " padded", "padded ", "x" * (MAX_CAPABILITY_DESCRIPTION_CHARACTERS + 1)):
        record = _record()
        _mutate(record, field_name, bad)
        with pytest.raises(InvalidEvaluatorCapabilityRecordError):
            validate_evaluator_capability_record(record)


def test_benchmark_version_is_identifier_bounded_not_free_form_description() -> None:
    for bad in ("", " v1", "v1 ", "x" * (MAX_CAPABILITY_IDENTIFIER_CHARACTERS + 1)):
        record = _record()
        _mutate(record, "benchmark_version", bad)
        with pytest.raises(InvalidEvaluatorCapabilityRecordError):
            validate_evaluator_capability_record(record)


def test_record_detects_nested_reference_mutation() -> None:
    record = _record()
    _mutate(record.capability_ref, "record_version", 0)
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


def test_record_rejects_foreign_reference_before_nested_dispatch() -> None:
    class ForeignRef:
        @property
        def evaluator_metadata(self) -> object:
            raise AssertionError("foreign capability ref accessed")

    record = _record()
    _mutate(record, "capability_ref", ForeignRef())
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


def test_record_detects_post_construction_status_mutation() -> None:
    record = _record()
    _mutate(record, "status", "VALIDATED")
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        validate_evaluator_capability_record(record)


def test_identifier_text_accepts_exact_128_character_boundary() -> None:
    ref = _ref(evaluator_id="x" * MAX_CAPABILITY_IDENTIFIER_CHARACTERS)
    assert validate_evaluator_capability_ref(ref) is ref


@pytest.mark.parametrize(
    "field_name",
    [
        "supported_answer_types",
        "supported_languages",
        "supported_modalities",
        "verification_mechanisms",
        "known_failure_modes",
    ],
)
def test_tuple_metadata_accepts_exact_32_entry_boundary(field_name: str) -> None:
    record = _record()
    object.__setattr__(
        record,
        field_name,
        tuple(f"v{i}" for i in range(MAX_CAPABILITY_TUPLE_ENTRIES)),
    )
    assert validate_evaluator_capability_record(record) is record


def test_description_text_accepts_exact_512_character_boundary() -> None:
    record = _record(domain_scope="x" * MAX_CAPABILITY_DESCRIPTION_CHARACTERS)
    assert validate_evaluator_capability_record(record) is record


def test_failure_mode_accepts_exact_512_character_boundary() -> None:
    record = _record(known_failure_modes=("x" * MAX_CAPABILITY_DESCRIPTION_CHARACTERS,))
    assert validate_evaluator_capability_record(record) is record
