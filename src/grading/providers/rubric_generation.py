from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from grading.providers.rubric_ingress import (
    AdmittedRubricProviderProposal,
    RubricProviderIngressLimits,
    RubricProviderProvenance,
    parse_rubric_provider_payload,
)
from grading.rubric.generator import (
    GeneratedRubricCandidate,
    RubricGenerationInput,
    generate_rubric_candidate,
)


__all__ = [
    "RubricGenerationProvider",
    "RubricProviderReplayFixture",
    "ReplayRubricProvider",
    "ProviderGeneratedRubricCandidate",
    "RubricProviderError",
    "RubricProviderTimeoutError",
    "RubricProviderUnavailableError",
    "RubricProviderReplayMissError",
    "rubric_provider_request_fingerprint",
    "generate_rubric_with_provider",
]

_PROVIDER_PROFILE_VERSION = "1"
_REQUEST_FINGERPRINT_SCHEMA = "gradified-rubric-provider-request-v1"


class RubricProviderError(RuntimeError):
    """Base class for expected provider-execution failures."""


class RubricProviderTimeoutError(RubricProviderError):
    """Provider execution exceeded its configured deadline."""


class RubricProviderUnavailableError(RubricProviderError):
    """Provider execution is unavailable before a response is admitted."""


class RubricProviderReplayMissError(RubricProviderError):
    """No deterministic replay fixture matches the exact generation request."""


def _require_exact_source(source: object) -> RubricGenerationInput:
    if type(source) is not RubricGenerationInput:
        raise TypeError("source must be an exact RubricGenerationInput.")
    return source


def _require_exact_provenance(provenance: object) -> RubricProviderProvenance:
    if type(provenance) is not RubricProviderProvenance:
        raise TypeError("provider.provenance must be an exact RubricProviderProvenance.")
    return provenance


def _require_lowercase_sha256(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact str.")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be lowercase SHA-256 hex.")
    return value


def _rounding_payload(source: RubricGenerationInput) -> dict[str, str] | None:
    rounding = source.rounding
    if rounding is None:
        return None
    return {
        "rule_id": rounding.rule_id,
        "increment": rounding.increment.to_canonical_string(),
        "mode": rounding.mode,
    }


def rubric_provider_request_fingerprint(source: RubricGenerationInput) -> str:
    """Fingerprint the exact trusted generation request used for provider replay.

    This is a deterministic request identity, not an authentication credential.
    """

    source = _require_exact_source(source)
    payload = {
        "schema": _REQUEST_FINGERPRINT_SCHEMA,
        "finalized_question": {
            "question_id": source.finalized_question.question_id,
            "max_marks": source.finalized_question.max_marks.to_canonical_string(),
        },
        "question_text": source.question_text,
        "model_answer_text": source.model_answer_text,
        "rubric_id": source.rubric_id,
        "policy_id": source.policy_id,
        "minimum_score": source.minimum_score.to_canonical_string(),
        "rounding": _rounding_payload(source),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RubricGenerationProvider(Protocol):
    """Provider-neutral generation boundary returning exact raw response bytes."""

    @property
    def provenance(self) -> RubricProviderProvenance:
        ...

    def generate(self, *, source: RubricGenerationInput) -> bytes:
        ...


@dataclass(frozen=True, slots=True)
class RubricProviderReplayFixture:
    request_fingerprint: str
    provenance: RubricProviderProvenance
    raw_payload: bytes

    def __post_init__(self) -> None:
        _require_lowercase_sha256(self.request_fingerprint, "request_fingerprint")
        if type(self.provenance) is not RubricProviderProvenance:
            raise TypeError(
                "fixture.provenance must be an exact RubricProviderProvenance."
            )
        if type(self.raw_payload) is not bytes:
            raise TypeError("raw_payload must be exact bytes.")


@dataclass(frozen=True, slots=True)
class ReplayRubricProvider:
    """Deterministic no-network provider backed by exact request-bound fixtures."""

    provenance: RubricProviderProvenance
    fixtures: tuple[RubricProviderReplayFixture, ...]

    def __post_init__(self) -> None:
        _require_exact_provenance(self.provenance)
        if type(self.fixtures) is not tuple:
            raise TypeError("fixtures must be a tuple.")
        if any(type(fixture) is not RubricProviderReplayFixture for fixture in self.fixtures):
            raise TypeError("fixtures contains an invalid item.")

        for fixture in self.fixtures:
            if fixture.provenance != self.provenance:
                raise ValueError(
                    "Replay fixture provenance does not match provider provenance."
                )

        fingerprints = [fixture.request_fingerprint for fixture in self.fixtures]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("Replay fixtures contain duplicate request_fingerprint values.")

    def generate(self, *, source: RubricGenerationInput) -> bytes:
        request_fingerprint = rubric_provider_request_fingerprint(source)
        for fixture in self.fixtures:
            if fixture.request_fingerprint == request_fingerprint:
                return fixture.raw_payload
        raise RubricProviderReplayMissError(
            "No replay fixture matches the exact rubric-generation request."
        )


@dataclass(frozen=True, slots=True)
class ProviderGeneratedRubricCandidate:
    """Provider provenance plus the still-unapproved deterministic G1a candidate."""

    request_fingerprint: str
    provider_profile_version: str
    admitted_proposal: AdmittedRubricProviderProposal
    candidate: GeneratedRubricCandidate

    def __post_init__(self) -> None:
        _require_lowercase_sha256(self.request_fingerprint, "request_fingerprint")
        if type(self.provider_profile_version) is not str:
            raise TypeError("provider_profile_version must be an exact str.")
        if self.provider_profile_version != _PROVIDER_PROFILE_VERSION:
            raise ValueError("Unsupported provider_profile_version.")
        if type(self.admitted_proposal) is not AdmittedRubricProviderProposal:
            raise TypeError(
                "admitted_proposal must be an exact AdmittedRubricProviderProposal."
            )
        if type(self.candidate) is not GeneratedRubricCandidate:
            raise TypeError("candidate must be an exact GeneratedRubricCandidate.")
        if self.candidate.proposal != self.admitted_proposal.proposal:
            raise ValueError("candidate proposal does not match admitted provider proposal.")
        expected_request_fingerprint = rubric_provider_request_fingerprint(
            self.candidate.source
        )
        if self.request_fingerprint != expected_request_fingerprint:
            raise ValueError("request_fingerprint does not match candidate source.")


def generate_rubric_with_provider(
    *,
    source: RubricGenerationInput,
    provider: RubricGenerationProvider,
    ingress_limits: RubricProviderIngressLimits,
) -> ProviderGeneratedRubricCandidate:
    """Generate one unapproved candidate through frozen G1b then frozen G1a.

    Provider bytes remain untrusted until admitted by G1b. This function performs
    no compilation, approval, activation, or reducer-authority construction.
    """

    source = _require_exact_source(source)
    if type(ingress_limits) is not RubricProviderIngressLimits:
        raise TypeError("ingress_limits must be an exact RubricProviderIngressLimits.")

    provenance = _require_exact_provenance(provider.provenance)
    raw_payload = provider.generate(source=source)
    if type(raw_payload) is not bytes:
        raise TypeError("provider.generate() must return exact bytes.")

    admitted_proposal = parse_rubric_provider_payload(
        raw_payload=raw_payload,
        limits=ingress_limits,
        provenance=provenance,
    )
    candidate = generate_rubric_candidate(
        source=source,
        proposal=admitted_proposal.proposal,
    )
    return ProviderGeneratedRubricCandidate(
        request_fingerprint=rubric_provider_request_fingerprint(source),
        provider_profile_version=_PROVIDER_PROFILE_VERSION,
        admitted_proposal=admitted_proposal,
        candidate=candidate,
    )
