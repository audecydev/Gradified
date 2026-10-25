"""Run at repository root with PYTHONPATH=src:. python docs/examples/ocr_admission_demo.py.

Demonstrates JSON boundary parsing only; sample values are not school authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from grading.integration.evidence_ingress import (
    NormalizedEvidenceAdmissionPolicy,
    NormalizedEvidenceUnsupportedSchemaVersionError,
    parse_normalized_evidence_payload,
)


def demo() -> None:
    raw = Path(__file__).with_name("ocr_evidence_sample.json").read_bytes()
    policy = NormalizedEvidenceAdmissionPolicy(
        admission_policy_identity="example-resource-policy",  # local demo only
        max_raw_bytes=100_000,
        max_json_depth=32,
        max_json_nodes=10_000,
        max_json_number_characters=128,
        max_identifier_characters=256,
        max_metadata_text_characters=2_048,
        max_block_content_characters=8_192,
        max_total_content_characters=65_536,
        max_questions=100,
        max_blocks_per_question=200,
        max_total_blocks=5_000,
        max_warnings_per_question=100,
        max_location_coordinates=16,
    )
    evidence = parse_normalized_evidence_payload(
        raw_payload=raw,
        policy=policy,
        source_artifact_ref="example-source-ref",
    )
    print("OCR ADMISSION PASS: schema", evidence.wire_schema_version)
    print("Raw input SHA-256:", evidence.raw_payload_sha256)
    print("Question count:", len(evidence.evidence.questions))

    invalid = json.loads(raw)
    invalid["schema_version"] = "unsupported"
    try:
        parse_normalized_evidence_payload(
            raw_payload=json.dumps(invalid, separators=(",", ":")).encode("utf-8"),
            policy=policy,
        )
    except NormalizedEvidenceUnsupportedSchemaVersionError:
        print("INVALID VERSION REJECTED")
    else:
        raise AssertionError("Invalid schema version was accepted")


if __name__ == "__main__":
    demo()
