from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from grading.semantic_evaluator import DirectTextSemanticRequest


__all__ = [
    "DirectTextSemanticProviderProvenance",
    "DirectTextSemanticReplayFixture",
    "ReplayDirectTextSemanticProvider",
    "DirectTextSemanticProviderReplayError",
    "DirectTextSemanticProviderReplayMissError",
    "direct_text_semantic_request_fingerprint",
]

_REQUEST_FINGERPRINT_SCHEMA = "gradified-direct-text-semantic-provider-request-v1"


class DirectTextSemanticProviderReplayError(RuntimeError):
    """Base class for deterministic DIRECT semantic replay failures."""


class DirectTextSemanticProviderReplayMissError(DirectTextSemanticProviderReplayError):
    """No replay fixture matches the exact DIRECT semantic request."""


def _require_exact_nonempty_identifier(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact str.")
    if value == "" or value.strip() != value:
        raise ValueError(
            f"{field_name} must be non-empty and contain no surrounding whitespace."
        )
    return value


def _require_lowercase_sha256(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact str.")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be lowercase SHA-256 hex.")
    return value


@dataclass(frozen=True, slots=True)
class DirectTextSemanticProviderProvenance:
    provider_id: str
    model_id: str

    def __post_init__(self) -> None:
        _require_exact_nonempty_identifier(self.provider_id, "provider_id")
        _require_exact_nonempty_identifier(self.model_id, "model_id")


def _direct_text_semantic_request_bytes(request: DirectTextSemanticRequest) -> bytes:
    """Canonical replay request bytes; not vendor wire or execution proof."""

    if type(request) is not DirectTextSemanticRequest:
        raise TypeError("request must be an exact DirectTextSemanticRequest.")

    payload = {
        "schema": _REQUEST_FINGERPRINT_SCHEMA,
        "question_id": request.question_id,
        "question_text": request.question_text,
        "model_answer_text": request.model_answer_text,
        "criteria": [
            {
                "criterion_id": criterion.criterion_id,
                "operational_description": criterion.operational_description,
                "evidence_requirement": criterion.evidence_requirement,
                "performance_levels": [
                    {
                        "level_id": level.level_id,
                        "operational_description": level.operational_description,
                    }
                    for level in criterion.performance_levels
                ],
                "accepted_equivalents": list(criterion.accepted_equivalents),
            }
            for criterion in request.criteria
        ],
        "evidence_blocks": [
            {
                "block_id": block.block_id,
                "content": block.content,
            }
            for block in request.evidence_blocks
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return encoded


def direct_text_semantic_request_fingerprint(request: DirectTextSemanticRequest) -> str:
    """Deterministic replay identity, not execution or source authentication."""
    return hashlib.sha256(_direct_text_semantic_request_bytes(request)).hexdigest()


@dataclass(frozen=True, slots=True)
class DirectTextSemanticReplayFixture:
    request_fingerprint: str
    provenance: DirectTextSemanticProviderProvenance
    raw_payload: bytes

    def __post_init__(self) -> None:
        _require_lowercase_sha256(self.request_fingerprint, "request_fingerprint")
        if type(self.provenance) is not DirectTextSemanticProviderProvenance:
            raise TypeError(
                "fixture.provenance must be an exact "
                "DirectTextSemanticProviderProvenance."
            )
        if type(self.raw_payload) is not bytes:
            raise TypeError("raw_payload must be exact bytes.")


@dataclass(frozen=True, slots=True)
class ReplayDirectTextSemanticProvider:
    """Deterministic no-network provider backed by exact request fixtures."""

    provenance: DirectTextSemanticProviderProvenance
    fixtures: tuple[DirectTextSemanticReplayFixture, ...]

    def __post_init__(self) -> None:
        if type(self.provenance) is not DirectTextSemanticProviderProvenance:
            raise TypeError(
                "provenance must be an exact DirectTextSemanticProviderProvenance."
            )
        if type(self.fixtures) is not tuple:
            raise TypeError("fixtures must be a tuple.")
        if any(type(fixture) is not DirectTextSemanticReplayFixture for fixture in self.fixtures):
            raise TypeError("fixtures contains an invalid item.")

        for fixture in self.fixtures:
            if fixture.provenance != self.provenance:
                raise ValueError(
                    "Replay fixture provenance does not match provider provenance."
                )

        fingerprints = [fixture.request_fingerprint for fixture in self.fixtures]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("Replay fixtures contain duplicate request_fingerprint values.")

    def evaluate(self, *, request: DirectTextSemanticRequest) -> bytes:
        request_fingerprint = direct_text_semantic_request_fingerprint(request)
        for fixture in self.fixtures:
            if fixture.request_fingerprint == request_fingerprint:
                return fixture.raw_payload
        raise DirectTextSemanticProviderReplayMissError(
            "No replay fixture matches the exact DIRECT semantic request."
        )
