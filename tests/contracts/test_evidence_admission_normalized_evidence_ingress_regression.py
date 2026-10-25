from __future__ import annotations

from dataclasses import MISSING, fields
import hashlib
import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlockState,
    EvidenceBlockType,
    EvidenceConfidenceStatus,
    EvidenceLocationStatus,
)


MODULE_NAME = "grading.integration.evidence_ingress"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "gradified.normalized_answer_evidence.v1.schema.json"

_POLICY_NUMERIC_FIELDS = (
    "max_raw_bytes",
    "max_json_depth",
    "max_json_nodes",
    "max_json_number_characters",
    "max_identifier_characters",
    "max_metadata_text_characters",
    "max_block_content_characters",
    "max_total_content_characters",
    "max_questions",
    "max_blocks_per_question",
    "max_total_blocks",
    "max_warnings_per_question",
    "max_location_coordinates",
)


def _api() -> ModuleType:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME or exc.name == "grading.integration":
            pytest.fail(
                "Normalized evidence ingress contract unavailable; "
                "expected grading.integration.evidence_ingress",
                pytrace=False,
            )
        raise


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1",
        "submission_ref": "submission-1",
        "ocr_provenance": "ocr-run-1",
        "questions": [
            {
                "question_id": "Q1",
                "answer_scope_ref": "scope-Q1",
                "blocks": [
                    {
                        "block_id": "Q1-B1",
                        "type": "TEXT",
                        "content": "The answer text.",
                        "language": None,
                        "confidence": 0.95,
                        "confidence_status": "PRESENT",
                        "state": "ACTIVE",
                        "page": 1,
                        "location": {
                            "status": "PRESENT",
                            "bbox": [0, 0, 100, 20],
                        },
                        "reading_order": 1,
                        "asset_ref": None,
                    }
                ],
                "warnings": [],
            }
        ],
    }
    document.update(overrides)
    return document


def _raw(document: dict[str, object] | None = None) -> bytes:
    return json.dumps(
        _document() if document is None else document,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _policy(api: ModuleType, **overrides: object):
    values: dict[str, object] = {
        "admission_policy_identity": "p0a-test-policy-v1",
        "max_raw_bytes": 100_000,
        "max_json_depth": 32,
        "max_json_nodes": 10_000,
        "max_json_number_characters": 128,
        "max_identifier_characters": 256,
        "max_metadata_text_characters": 2_048,
        "max_block_content_characters": 8_192,
        "max_total_content_characters": 65_536,
        "max_questions": 100,
        "max_blocks_per_question": 200,
        "max_total_blocks": 5_000,
        "max_warnings_per_question": 100,
        "max_location_coordinates": 16,
    }
    values.update(overrides)
    return api.NormalizedEvidenceAdmissionPolicy(**values)


def _parse(
    api: ModuleType,
    raw_payload: bytes | object | None = None,
    *,
    policy=None,
    source_artifact_ref: str | None = None,
):
    actual_policy = _policy(api) if policy is None else policy
    actual_raw = _raw() if raw_payload is None else raw_payload
    return api.parse_normalized_evidence_payload(
        raw_payload=actual_raw,
        policy=actual_policy,
        source_artifact_ref=source_artifact_ref,
    )


def _question(document: dict[str, object], index: int = 0) -> dict[str, object]:
    return document["questions"][index]  # type: ignore[index,return-value]


def _block(document: dict[str, object], q_index: int = 0, b_index: int = 0) -> dict[str, object]:
    return _question(document, q_index)["blocks"][b_index]  # type: ignore[index,return-value]


def test_p0a_public_surface_exists_with_narrow_contract() -> None:
    api = _api()
    expected = {
        "NormalizedEvidenceAdmissionPolicy",
        "AdmittedNormalizedEvidence",
        "NormalizedEvidenceIngressError",
        "NormalizedEvidenceResourceError",
        "NormalizedEvidenceMalformedPayloadError",
        "NormalizedEvidenceSchemaError",
        "NormalizedEvidenceUnsupportedSchemaVersionError",
        "InvalidNormalizedEvidenceAdmissionPolicyError",
        "NormalizedEvidenceProvenanceError",
        "parse_normalized_evidence_payload",
    }
    assert expected.issubset(set(api.__all__))


def test_admission_policy_has_exact_no_default_effective_snapshot_surface() -> None:
    api = _api()
    policy_fields = fields(api.NormalizedEvidenceAdmissionPolicy)
    assert tuple(field.name for field in policy_fields) == (
        "admission_policy_identity",
        "max_raw_bytes",
        "max_json_depth",
        "max_json_nodes",
        "max_json_number_characters",
        "max_identifier_characters",
        "max_metadata_text_characters",
        "max_block_content_characters",
        "max_total_content_characters",
        "max_questions",
        "max_blocks_per_question",
        "max_total_blocks",
        "max_warnings_per_question",
        "max_location_coordinates",
    )
    assert all(field.default is MISSING and field.default_factory is MISSING for field in policy_fields)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("admission_policy_identity", ""),
        ("admission_policy_identity", " policy-v1"),
        ("max_raw_bytes", 0),
        ("max_json_depth", -1),
        ("max_json_nodes", True),
        ("max_json_number_characters", 0),
        ("max_identifier_characters", False),
        ("max_metadata_text_characters", 0),
        ("max_block_content_characters", -1),
        ("max_total_content_characters", 0),
        ("max_questions", 0),
        ("max_blocks_per_question", 0),
        ("max_total_blocks", 0),
        ("max_warnings_per_question", 0),
        ("max_location_coordinates", 0),
    ],
)
def test_invalid_trusted_policy_configuration_is_rejected(field: str, value: object) -> None:
    api = _api()
    with pytest.raises(api.InvalidNormalizedEvidenceAdmissionPolicyError):
        _policy(api, **{field: value})


@pytest.mark.parametrize("field", _POLICY_NUMERIC_FIELDS)
@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_policy_numeric_limits_require_positive_exact_ints(field: str, value: object) -> None:
    api = _api()
    with pytest.raises(api.InvalidNormalizedEvidenceAdmissionPolicyError):
        _policy(api, **{field: value})


def test_admission_policy_identity_is_bounded_by_its_effective_identifier_limit() -> None:
    api = _api()
    with pytest.raises(api.InvalidNormalizedEvidenceAdmissionPolicyError):
        _policy(api, admission_policy_identity="policy-v1", max_identifier_characters=4)


def test_parse_requires_exact_bytes() -> None:
    api = _api()
    with pytest.raises(TypeError):
        _parse(api, raw_payload=_raw().decode("utf-8"))


def test_raw_byte_limit_is_enforced_before_normalized_admission() -> None:
    api = _api()
    raw = _raw()
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=raw, policy=_policy(api, max_raw_bytes=len(raw) - 1))


def test_raw_byte_limit_allows_exact_boundary() -> None:
    api = _api()
    raw = _raw()
    admitted = _parse(api, raw_payload=raw, policy=_policy(api, max_raw_bytes=len(raw)))
    assert admitted.evidence.submission_ref == "submission-1"


def test_raw_resource_failure_precedes_utf8_decode_when_payload_is_oversized() -> None:
    api = _api()
    raw = b"\xff" * 9
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=raw, policy=_policy(api, max_raw_bytes=8))


def test_malformed_utf8_is_rejected_as_malformed_payload() -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError):
        _parse(api, raw_payload=b"\xff\xfe\xfd")


def test_malformed_utf8_translation_does_not_retain_payload_exception_context() -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError) as exc_info:
        _parse(api, raw_payload=b"\xffPRIVATE-STUDENT-BYTES")
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None


def test_preflight_malformed_translation_does_not_retain_payload_exception_context() -> None:
    api = _api()
    secret = "PRIVATE-STUDENT-PREFLIGHT-CONTENT"
    raw = (f'{{"secret":"{secret}",}}').encode("utf-8")
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError) as exc_info:
        _parse(api, raw_payload=raw)
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    assert secret not in str(exc_info.value)


def test_preflight_resource_translation_does_not_retain_payload_exception_context() -> None:
    api = _api()
    secret = "PRIVATE-STUDENT-PREFLIGHT-CONTENT"
    raw = (f'{{"secret":"{secret}"}}').encode("utf-8")
    with pytest.raises(api.NormalizedEvidenceResourceError) as exc_info:
        _parse(api, raw_payload=raw, policy=_policy(api, max_json_depth=1))
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None
    assert secret not in str(exc_info.value)


def test_valid_utf8_non_ascii_content_is_admitted_without_ascii_normalization() -> None:
    api = _api()
    doc = _document()
    _block(doc)["content"] = "ಕನ್ನಡ गणित ∑ √"
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    admitted = _parse(api, raw_payload=raw)
    assert admitted.evidence.questions[0].blocks[0].content == "ಕನ್ನಡ गणित ∑ √"


def test_admission_does_not_unicode_normalize_evidence_content() -> None:
    api = _api()
    decomposed = "e\u0301"
    doc = _document()
    _block(doc)["content"] = decomposed
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    admitted = _parse(api, raw_payload=raw)
    assert admitted.evidence.questions[0].blocks[0].content == decomposed
    assert admitted.evidence.questions[0].blocks[0].content != "é"


def test_unescaped_json_control_character_is_rejected() -> None:
    api = _api()
    raw = _raw().replace(b"The answer text.", b"bad\x01text", 1)
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError):
        _parse(api, raw_payload=raw)


def test_unpaired_unicode_surrogate_is_rejected() -> None:
    api = _api()
    raw = _raw().replace(b'"The answer text."', b'"\\ud800"', 1)
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError):
        _parse(api, raw_payload=raw)


@pytest.mark.parametrize(
    "raw_payload",
    [
        b"",
        b"   ",
        _raw() + b"{}",
        b"{} {}",
    ],
)
def test_payload_must_be_one_complete_json_document(raw_payload: bytes) -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError):
        _parse(api, raw_payload=raw_payload)


def test_over_depth_json_is_rejected_by_resource_policy() -> None:
    api = _api()
    nested = (b"[" * 40) + b"0" + (b"]" * 40)
    raw = b'{"schema_version":"1","submission_ref":"s","ocr_provenance":"o","questions":' + nested + b"}"
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=raw, policy=_policy(api, max_json_depth=8))


def test_schema_valid_v1_depth_boundary_is_exact() -> None:
    api = _api()
    admitted = _parse(api, policy=_policy(api, max_json_depth=8))
    assert admitted.evidence.submission_ref == "submission-1"
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, policy=_policy(api, max_json_depth=7))


def test_over_node_json_is_rejected_by_resource_policy() -> None:
    api = _api()
    doc = _document(questions=[{} for _ in range(20)])
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_json_nodes=10))


def test_canonical_v1_node_boundary_is_exact() -> None:
    api = _api()
    admitted = _parse(api, policy=_policy(api, max_json_nodes=28))
    assert admitted.evidence.submission_ref == "submission-1"
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, policy=_policy(api, max_json_nodes=27))


def test_duplicate_json_keys_fail_closed_including_nested_keys() -> None:
    api = _api()
    raw = (
        b'{"schema_version":"1","submission_ref":"submission-1",'
        b'"ocr_provenance":"ocr-run-1","questions":[{'
        b'"question_id":"Q1","question_id":"Q2","answer_scope_ref":"scope-Q1",'
        b'"blocks":[],"warnings":[]}]}'
    )
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=raw)


@pytest.mark.parametrize("token", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonstandard_json_numeric_constants_are_rejected(token: bytes) -> None:
    api = _api()
    raw = _raw().replace(b"0.95", token, 1)
    with pytest.raises(api.NormalizedEvidenceMalformedPayloadError):
        _parse(api, raw_payload=raw)


def test_standard_json_number_that_cannot_become_finite_confidence_is_rejected() -> None:
    api = _api()
    raw = _raw().replace(b"0.95", b"1e309", 1)
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=raw)


def test_huge_json_number_token_is_bounded_before_numeric_conversion() -> None:
    api = _api()
    huge = b"1" + (b"0" * 5000)
    raw = _raw().replace(b'"page":1', b'"page":' + huge, 1)
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(
            api,
            raw_payload=raw,
            policy=_policy(api, max_raw_bytes=len(raw) + 1, max_json_number_characters=64),
        )


def test_json_number_token_limit_exact_boundary_is_enforced() -> None:
    api = _api()
    doc = _document()
    block = _block(doc)
    block["confidence"] = 0
    block["page"] = 1234
    block["location"] = {"status": "PRESENT", "bbox": [0]}
    block["reading_order"] = 1
    admitted = _parse(
        api,
        raw_payload=_raw(doc),
        policy=_policy(api, max_json_number_characters=4),
    )
    assert admitted.evidence.questions[0].blocks[0].page == 1234
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(
            api,
            raw_payload=_raw(doc),
            policy=_policy(api, max_json_number_characters=3),
        )


def test_json_number_limit_does_not_count_digits_inside_student_strings() -> None:
    api = _api()
    doc = _document()
    block = _block(doc)
    block["content"] = "9" * 200
    block["confidence"] = 0
    block["location"] = {"status": "PRESENT", "bbox": [0]}
    admitted = _parse(
        api,
        raw_payload=_raw(doc),
        policy=_policy(
            api,
            max_json_number_characters=1,
            max_block_content_characters=256,
            max_total_content_characters=256,
        ),
    )
    assert admitted.evidence.questions[0].blocks[0].content == "9" * 200


@pytest.mark.parametrize(
    "field",
    ["schema_version", "submission_ref", "ocr_provenance", "questions"],
)
def test_root_required_fields_cannot_be_missing(field: str) -> None:
    api = _api()
    doc = _document()
    del doc[field]
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("questions", {}),
        ("questions", "not-an-array"),
        ("blocks", {}),
        ("warnings", {}),
        ("location", []),
        ("bbox", {}),
    ],
)
def test_major_container_types_are_explicit(path: str, value: object) -> None:
    api = _api()
    doc = _document()
    if path == "questions":
        doc["questions"] = value
    elif path == "blocks":
        _question(doc)["blocks"] = value
    elif path == "warnings":
        _question(doc)["warnings"] = value
    elif path == "location":
        _block(doc)["location"] = value
    else:
        _block(doc)["location"]["bbox"] = value
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("score", 10),
        ("tenant_ref", "school-B"),
        ("evaluator_id", "preferred-evaluator"),
        ("admission_policy_identity", "attacker-policy"),
        ("source_artifact_ref", "attacker-artifact"),
        ("authenticated", True),
        ("evaluation_attempt_id", "attempt-attacker"),
    ],
)
def test_wire_cannot_smuggle_authority_or_security_configuration(field: str, value: object) -> None:
    api = _api()
    doc = _document(**{field: value})
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_unsupported_wire_schema_version_has_specific_failure() -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceUnsupportedSchemaVersionError):
        _parse(api, raw_payload=_raw(_document(schema_version="2")))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("submission_ref", ""),
        ("submission_ref", " submission-1"),
        ("ocr_provenance", ""),
    ],
)
def test_top_level_identity_fields_keep_existing_exact_identifier_semantics(
    field: str,
    value: object,
) -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(_document(**{field: value})))


@pytest.mark.parametrize("value", ["\u0085submission", "\u001csubmission"])
def test_identifier_rejects_unicode_boundary_whitespace_not_portably_covered_by_ecma_regex(
    value: str,
) -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(_document(submission_ref=value)))


@pytest.mark.parametrize("field", ["question_id", "answer_scope_ref", "blocks", "warnings"])
def test_question_wire_surface_requires_all_explicit_fields(field: str) -> None:
    api = _api()
    doc = _document()
    del _question(doc)[field]
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_question_wire_surface_rejects_unknown_fields() -> None:
    api = _api()
    doc = _document()
    _question(doc)["score"] = 10
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_duplicate_question_ids_are_rejected_as_ambiguous_normalized_evidence() -> None:
    api = _api()
    q = _question(_document()).copy()
    q2 = json.loads(json.dumps(q))
    raw = _raw(_document(questions=[q, q2]))
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=raw)


def test_duplicate_block_ids_are_rejected_across_questions() -> None:
    api = _api()
    doc = _document()
    q1 = json.loads(json.dumps(_question(doc)))
    q2 = json.loads(json.dumps(_question(doc)))
    q2["question_id"] = "Q2"
    q2["answer_scope_ref"] = "scope-Q2"
    # block_id intentionally remains Q1-numeric scoring profile
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(_document(questions=[q1, q2])))


@pytest.mark.parametrize(
    "missing_field",
    [
        "block_id",
        "type",
        "content",
        "language",
        "confidence",
        "confidence_status",
        "state",
        "page",
        "location",
        "reading_order",
        "asset_ref",
    ],
)
def test_block_wire_surface_is_closed_and_all_state_keys_are_explicit(missing_field: str) -> None:
    api = _api()
    doc = _document()
    del _block(doc)[missing_field]
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_block_wire_surface_rejects_unknown_fields() -> None:
    api = _api()
    doc = _document()
    _block(doc)["score"] = 10
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema_version", 1),
        ("submission_ref", 123),
        ("ocr_provenance", False),
        ("question_id", 7),
        ("answer_scope_ref", 8),
        ("block_id", 9),
        ("type", 1),
        ("content", 2),
        ("language", 3),
        ("confidence", "0.95"),
        ("confidence", True),
        ("confidence_status", 4),
        ("state", 5),
        ("page", 1.0),
        ("reading_order", "1"),
        ("asset_ref", 6),
        ("location.status", 7),
        ("bbox_item", "0"),
    ],
)
def test_scalar_wire_types_are_exact(path: str, value: object) -> None:
    api = _api()
    doc = _document()
    if path in {"schema_version", "submission_ref", "ocr_provenance"}:
        doc[path] = value
    elif path in {"question_id", "answer_scope_ref"}:
        _question(doc)[path] = value
    elif path == "location.status":
        _block(doc)["location"]["status"] = value
    elif path == "bbox_item":
        _block(doc)["location"]["bbox"] = [0, value, 1, 1]
    else:
        _block(doc)[path] = value
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize(
    ("status", "confidence", "valid"),
    [
        ("UNAVAILABLE", None, True),
        ("UNAVAILABLE", 0, False),
        ("PRESENT", None, False),
        ("PRESENT", 0, True),
        ("PRESENT", -0.25, True),
    ],
)
def test_confidence_null_and_zero_semantics_are_explicit(
    status: str,
    confidence: object,
    valid: bool,
) -> None:
    api = _api()
    doc = _document()
    block = _block(doc)
    block["confidence_status"] = status
    block["confidence"] = confidence
    if valid:
        admitted = _parse(api, raw_payload=_raw(doc))
        assert admitted.evidence.questions[0].blocks[0].confidence == confidence
    else:
        with pytest.raises(api.NormalizedEvidenceSchemaError):
            _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize("field", ["page", "reading_order"])
def test_bool_never_satisfies_exact_integer_fields(field: str) -> None:
    api = _api()
    doc = _document()
    _block(doc)[field] = True
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("type", "text"),
        ("state", "active"),
        ("confidence_status", "present"),
    ],
)
def test_block_enum_values_are_exact_and_case_sensitive(field: str, value: str) -> None:
    api = _api()
    doc = _document()
    _block(doc)[field] = value
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize("field", ["status", "bbox"])
def test_location_wire_surface_requires_explicit_fields(field: str) -> None:
    api = _api()
    doc = _document()
    del _block(doc)["location"][field]
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_location_wire_surface_rejects_unknown_fields() -> None:
    api = _api()
    doc = _document()
    _block(doc)["location"]["units"] = "pixels"
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize("field", ["language", "asset_ref"])
def test_optional_string_fields_require_explicit_key_but_allow_null(field: str) -> None:
    api = _api()
    doc = _document()
    _block(doc)[field] = None
    admitted = _parse(api, raw_payload=_raw(doc))
    assert getattr(admitted.evidence.questions[0].blocks[0], field) is None


@pytest.mark.parametrize("field", ["language", "asset_ref"])
def test_present_optional_string_fields_reject_empty_string(field: str) -> None:
    api = _api()
    doc = _document()
    _block(doc)[field] = ""
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


@pytest.mark.parametrize("field", ["language", "asset_ref"])
def test_optional_metadata_strings_are_bounded_when_present(field: str) -> None:
    api = _api()
    doc = _document()
    _block(doc)[field] = "X" * 9
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_metadata_text_characters=8))


def test_empty_block_content_is_structurally_admissible_without_academic_interpretation() -> None:
    api = _api()
    doc = _document()
    _block(doc)["content"] = ""
    admitted = _parse(api, raw_payload=_raw(doc))
    assert admitted.evidence.questions[0].blocks[0].content == ""


def test_empty_question_blocks_are_structurally_admissible_without_becoming_incorrect_answer() -> None:
    api = _api()
    doc = _document()
    _question(doc)["blocks"] = []
    admitted = _parse(api, raw_payload=_raw(doc))
    assert admitted.evidence.questions[0].blocks == ()


def test_empty_questions_array_is_structurally_admissible_pending_later_paper_binding() -> None:
    api = _api()
    admitted = _parse(api, raw_payload=_raw(_document(questions=[])))
    assert admitted.evidence.questions == ()


def test_page_and_reading_order_allow_zero_without_inventing_zero_or_one_based_indexing() -> None:
    api = _api()
    doc = _document()
    block = _block(doc)
    block["page"] = 0
    block["reading_order"] = 0
    admitted = _parse(api, raw_payload=_raw(doc))
    result_block = admitted.evidence.questions[0].blocks[0]
    assert result_block.page == 0
    assert result_block.reading_order == 0


@pytest.mark.parametrize("field", ["page", "reading_order"])
def test_page_and_reading_order_do_not_invent_sign_or_sentinel_semantics(field: str) -> None:
    api = _api()
    doc = _document()
    _block(doc)[field] = -1
    admitted = _parse(api, raw_payload=_raw(doc))
    result = admitted.evidence.questions[0].blocks[0]
    assert getattr(result, field) == -1


def test_location_coordinates_are_finite_structural_numbers_without_geometry_normalization() -> None:
    api = _api()
    doc = _document()
    _block(doc)["location"] = {"status": "PARTIAL", "bbox": [-10, 0.5, 9999, -3.25]}
    admitted = _parse(api, raw_payload=_raw(doc))
    assert admitted.evidence.questions[0].blocks[0].location.bbox == (-10, 0.5, 9999, -3.25)


@pytest.mark.parametrize("value", [True, False])
def test_bool_never_satisfies_location_numeric_coordinates(value: bool) -> None:
    api = _api()
    doc = _document()
    _block(doc)["location"] = {"status": "PRESENT", "bbox": [0, value, 1, 1]}
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_location_coordinate_count_is_bounded_without_assuming_bbox_shape() -> None:
    api = _api()
    doc = _document()
    _block(doc)["location"] = {"status": "PARTIAL", "bbox": list(range(5))}
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_location_coordinates=4))


def test_identifier_limit_is_enforced() -> None:
    api = _api()
    doc = _document(submission_ref="S" * 9, ocr_provenance="ocr-v1")
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(
            api,
            raw_payload=_raw(doc),
            policy=_policy(
                api, admission_policy_identity="p0a-v1", max_identifier_characters=8
            ),
        )


def test_identifier_limit_allows_exact_boundary() -> None:
    api = _api()
    value = "S" * 8
    admitted = _parse(
        api,
        raw_payload=_raw(_document(submission_ref=value, ocr_provenance="ocr-v1")),
        policy=_policy(api, admission_policy_identity="p0a-v1", max_identifier_characters=8),
    )
    assert admitted.evidence.submission_ref == value


def test_block_content_per_field_limit_is_enforced() -> None:
    api = _api()
    doc = _document()
    _block(doc)["content"] = "X" * 9
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_block_content_characters=8))


def test_block_content_limit_allows_exact_boundary() -> None:
    api = _api()
    doc = _document()
    _block(doc)["content"] = "abcdefgh"
    admitted = _parse(
        api,
        raw_payload=_raw(doc),
        policy=_policy(api, max_block_content_characters=8),
    )
    assert admitted.evidence.questions[0].blocks[0].content == "abcdefgh"


def test_aggregate_content_limit_is_enforced_across_multiple_blocks() -> None:
    api = _api()
    doc = _document()
    b1 = json.loads(json.dumps(_block(doc)))
    b2 = json.loads(json.dumps(b1))
    b1["content"] = "abcde"
    b2["block_id"] = "Q1-B2"
    b2["content"] = "fghij"
    _question(doc)["blocks"] = [b1, b2]
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(
            api,
            raw_payload=_raw(doc),
            policy=_policy(
                api,
                max_block_content_characters=8,
                max_total_content_characters=8,
            ),
        )


def test_question_count_is_bounded() -> None:
    api = _api()
    doc = _document(questions=[])
    q = json.loads(json.dumps(_question(_document())))
    q2 = json.loads(json.dumps(q))
    q2["question_id"] = "Q2"
    q2["answer_scope_ref"] = "scope-Q2"
    q2["blocks"][0]["block_id"] = "Q2-B1"
    doc["questions"] = [q, q2]
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_questions=1))


def test_blocks_per_question_and_total_blocks_are_separately_bounded() -> None:
    api = _api()
    doc = _document()
    b1 = json.loads(json.dumps(_block(doc)))
    b2 = json.loads(json.dumps(b1))
    b2["block_id"] = "Q1-B2"
    _question(doc)["blocks"] = [b1, b2]
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_blocks_per_question=1))
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_total_blocks=1))


def test_warning_count_and_text_size_are_bounded_but_warnings_have_no_academic_authority() -> None:
    api = _api()
    doc = _document()
    _question(doc)["warnings"] = ["ONE", "TWO"]
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_warnings_per_question=1))

    doc = _document()
    _question(doc)["warnings"] = ["TOO-LONG"]
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(api, raw_payload=_raw(doc), policy=_policy(api, max_metadata_text_characters=3))


def test_empty_warning_string_is_rejected_in_normalized_wire() -> None:
    api = _api()
    doc = _document()
    _question(doc)["warnings"] = [""]
    with pytest.raises(api.NormalizedEvidenceSchemaError):
        _parse(api, raw_payload=_raw(doc))


def test_successful_projection_is_exact_existing_answer_evidence_bundle() -> None:
    api = _api()
    admitted = _parse(api)
    assert type(admitted.evidence) is AnswerEvidenceBundle
    bundle = admitted.evidence
    assert bundle.schema_version == "1"
    assert bundle.submission_ref == "submission-1"
    assert bundle.ocr_provenance == "ocr-run-1"
    assert bundle.questions[0].question_id == "Q1"
    block = bundle.questions[0].blocks[0]
    assert block.type is EvidenceBlockType.TEXT
    assert block.confidence_status is EvidenceConfidenceStatus.PRESENT
    assert block.state is EvidenceBlockState.ACTIVE
    assert block.location.status is EvidenceLocationStatus.PRESENT


def test_exact_raw_bytes_are_fingerprinted_and_not_retained() -> None:
    api = _api()
    raw = _raw()
    admitted = _parse(api, raw_payload=raw)
    assert admitted.raw_payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert admitted.wire_schema_version == "1"
    assert not hasattr(admitted, "raw_payload")
    assert not hasattr(admitted, "raw_json")


def test_one_byte_change_changes_raw_artifact_digest() -> None:
    api = _api()
    first = _raw()
    second = first.replace(b"The answer text.", b"The answer text!", 1)
    assert _parse(api, raw_payload=first).raw_payload_sha256 != _parse(
        api, raw_payload=second
    ).raw_payload_sha256


def test_admitted_result_records_exact_trusted_policy_snapshot() -> None:
    api = _api()
    policy = _policy(api, max_questions=17)
    admitted = _parse(api, policy=policy)
    assert admitted.admission_policy_identity == "p0a-test-policy-v1"
    assert admitted.effective_policy_snapshot == policy
    assert admitted.effective_policy_snapshot.max_questions == 17


def test_effective_policy_snapshot_is_independent_of_later_caller_mutation() -> None:
    api = _api()
    policy = _policy(api, max_questions=17)
    admitted = _parse(api, policy=policy)
    object.__setattr__(policy, "max_questions", 999)
    assert admitted.effective_policy_snapshot.max_questions == 17
    assert admitted.admission_policy_identity == "p0a-test-policy-v1"


def test_effective_policy_snapshot_preserves_large_exact_integers() -> None:
    api = _api()
    large_exact_value = (2 ** 53) + 1
    policy = _policy(api, max_json_nodes=large_exact_value)
    admitted = _parse(api, policy=policy)
    assert policy.max_json_nodes == large_exact_value
    assert admitted.effective_policy_snapshot.max_json_nodes == large_exact_value
    assert type(admitted.effective_policy_snapshot.max_json_nodes) is int


def test_policy_snapshot_is_provenance_not_authentication() -> None:
    api = _api()
    admitted = _parse(api)
    forbidden_names = {
        "authenticated",
        "authorized",
        "tenant_authorized",
        "trust_proof",
        "authentication_proof",
    }
    assert forbidden_names.isdisjoint({field.name for field in fields(type(admitted))})


def test_separately_supplied_source_artifact_ref_is_preserved_but_not_authenticated() -> None:
    api = _api()
    admitted = _parse(api, source_artifact_ref="object-store://answer-sheets/submission-1/ocr-v7")
    assert admitted.source_artifact_ref == "object-store://answer-sheets/submission-1/ocr-v7"
    assert not hasattr(admitted, "artifact_authenticated")
    assert not hasattr(admitted, "source_trusted")


def test_missing_source_artifact_ref_is_explicitly_none_not_fabricated() -> None:
    api = _api()
    admitted = _parse(api, source_artifact_ref=None)
    assert admitted.source_artifact_ref is None


@pytest.mark.parametrize("source_artifact_ref", ["", " source", "source "])
def test_source_artifact_ref_if_present_uses_exact_identifier_semantics(
    source_artifact_ref: str,
) -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceProvenanceError):
        _parse(api, source_artifact_ref=source_artifact_ref)


def test_source_artifact_ref_is_bounded_by_trusted_policy() -> None:
    api = _api()
    with pytest.raises(api.NormalizedEvidenceResourceError):
        _parse(
            api,
            raw_payload=_raw(_document(ocr_provenance="ocr-v1")),
            policy=_policy(
                api, admission_policy_identity="p0a-v1", max_identifier_characters=8
            ),
            source_artifact_ref="artifact-123",
        )


def test_post_construction_policy_forgery_is_revalidated_before_use() -> None:
    api = _api()
    policy = _policy(api)
    object.__setattr__(policy, "max_raw_bytes", True)
    with pytest.raises(api.InvalidNormalizedEvidenceAdmissionPolicyError):
        _parse(api, policy=policy)


def test_direct_construction_does_not_create_a_supported_admitted_instance() -> None:
    api = _api()
    with pytest.raises(TypeError):
        api.AdmittedNormalizedEvidence(
            evidence=object(),
            raw_payload_sha256="0" * 64,
            wire_schema_version="1",
            admission_policy_identity="p0a-test-policy-v1",
            effective_policy_snapshot=_policy(api),
            source_artifact_ref=None,
        )


def test_error_text_does_not_echo_student_answer_content() -> None:
    api = _api()
    secret_answer = "PRIVATE-STUDENT-ANSWER-DO-NOT-ECHO"
    doc = _document()
    _block(doc)["content"] = secret_answer
    doc["unexpected"] = "force closed schema error"
    with pytest.raises(api.NormalizedEvidenceSchemaError) as exc_info:
        _parse(api, raw_payload=_raw(doc))
    assert secret_answer not in str(exc_info.value)


def test_admitted_wrapper_repr_does_not_echo_student_answer_content() -> None:
    api = _api()
    secret_answer = "PRIVATE-STUDENT-ANSWER-DO-NOT-ECHO"
    doc = _document()
    _block(doc)["content"] = secret_answer
    admitted = _parse(api, raw_payload=_raw(doc))
    assert secret_answer not in repr(admitted)
    assert secret_answer not in str(admitted)


def _object_schemas(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if type(value) is dict:
        if value.get("type") == "object":
            found.append(value)
        for child in value.values():
            found.extend(_object_schemas(child))
    elif type(value) is list:
        for child in value:
            found.extend(_object_schemas(child))
    return found


def test_schema_artifact_exists_and_declares_closed_normalized_wire_surface() -> None:
    _api()  # admission requires the executable implementation and published contract to agree
    assert SCHEMA_PATH.is_file()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"schema_version", "submission_ref", "ocr_provenance", "questions"}
    assert set(schema["properties"]) == {"schema_version", "submission_ref", "ocr_provenance", "questions"}
    assert schema["properties"]["schema_version"].get("const") == "1"

    object_schemas = _object_schemas(schema)
    assert len(object_schemas) >= 4
    assert all(item.get("additionalProperties") is False for item in object_schemas)

    property_sets = {frozenset(item.get("properties", {})) for item in object_schemas}
    assert frozenset({"question_id", "answer_scope_ref", "blocks", "warnings"}) in property_sets
    assert frozenset(
        {
            "block_id",
            "type",
            "content",
            "language",
            "confidence",
            "confidence_status",
            "state",
            "page",
            "location",
            "reading_order",
            "asset_ref",
        }
    ) in property_sets
    assert frozenset({"status", "bbox"}) in property_sets


def test_schema_overlap_matches_executable_enums_and_required_nested_fields() -> None:
    _api()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    block = schema["$defs"]["block"]
    location = schema["$defs"]["location"]
    question = schema["$defs"]["question"]

    assert set(question["required"]) == {"question_id", "answer_scope_ref", "blocks", "warnings"}
    assert set(block["required"]) == {
        "block_id",
        "type",
        "content",
        "language",
        "confidence",
        "confidence_status",
        "state",
        "page",
        "location",
        "reading_order",
        "asset_ref",
    }
    assert set(location["required"]) == {"status", "bbox"}
    assert set(block["properties"]["type"]["enum"]) == {member.value for member in EvidenceBlockType}
    assert set(block["properties"]["confidence_status"]["enum"]) == {
        member.value for member in EvidenceConfidenceStatus
    }
    assert set(block["properties"]["state"]["enum"]) == {member.value for member in EvidenceBlockState}
    assert set(location["properties"]["status"]["enum"]) == {
        member.value for member in EvidenceLocationStatus
    }
    assert block["properties"]["page"] == {"type": "integer"}
    assert block["properties"]["reading_order"] == {"type": "integer"}


def test_schema_identifier_surface_avoids_nonportable_whitespace_regex_claim() -> None:
    _api()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    identifier = schema["$defs"]["identifier"]
    assert identifier["type"] == "string"
    assert identifier["minLength"] == 1
    assert "pattern" not in identifier
    assert schema["properties"]["submission_ref"] == {"$ref": "#/$defs/identifier"}
    assert schema["properties"]["ocr_provenance"] == {"$ref": "#/$defs/identifier"}


def test_schema_cannot_claim_request_controlled_admission_or_authority_fields() -> None:
    _api()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "admission_policy_identity",
        "effective_policy_snapshot",
        "tenant_ref",
        "authenticated",
        "authorized",
        "evaluator_id",
        "evaluation_attempt_id",
        "source_artifact_ref",
        "score",
    }
    assert forbidden.isdisjoint(set(schema["properties"]))
