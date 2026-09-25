from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from grading.active_question_authority import ContextPolicy
from grading.contracts.paper_aggregation import (
    GradingSpecRef,
    _validate_grading_spec_ref,
    _validate_identifier,
)


REFERENCE_CONTEXT_SCHEMA_VERSION = "1"
MAX_REFERENCE_CONTEXT_CHUNKS = 32
MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS = 8192
MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS = 128
MAX_REFERENCE_CONTEXT_TOTAL_CONTENT_CHARACTERS = 65536


_ErrorT = TypeVar("_ErrorT", bound=Exception)


class ReferenceContextContractError(ValueError):
    """Base class for malformed REF-1 domain values."""


class ReferenceContextContractResourceError(ReferenceContextContractError):
    """Raised when a REF-1 domain value exceeds v1 resource limits."""


def _raise(error_type: type[_ErrorT], message: str, cause: BaseException | None = None) -> None:
    if cause is None:
        raise error_type(message)
    raise error_type(message) from cause


def _required_field(
    value: object,
    field_name: str,
    *,
    owner_name: str,
    error_type: type[_ErrorT],
) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        _raise(error_type, f"{owner_name}.{field_name} is missing.", exc)


def _require_context_policy(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
) -> ContextPolicy:
    if type(value) is not ContextPolicy or not any(value is member for member in ContextPolicy):
        _raise(error_type, f"{field_name} must be a canonical ContextPolicy member.")
    return value


def _require_bounded_text(
    value: object,
    *,
    field_name: str,
    maximum_characters: int,
    error_type: type[_ErrorT],
    resource_error_type: type[_ErrorT],
    strip_sensitive: bool,
) -> str:
    if type(value) is not str or not value:
        _raise(error_type, f"{field_name} must be a non-empty exact string.")
    if strip_sensitive and value.strip() != value:
        _raise(error_type, f"{field_name} must not contain surrounding whitespace.")
    if len(value) > maximum_characters:
        _raise(
            resource_error_type,
            f"{field_name} exceeds the REF-1-v1 {maximum_characters}-character limit.",
        )
    return value


@dataclass(frozen=True, slots=True)
class ReferenceContextRequest:
    """Gradified-owned request derived from one resolved ACTIVE question."""

    grading_spec_ref: GradingSpecRef
    question_id: str
    context_policy: ContextPolicy

    def __post_init__(self) -> None:
        _validate_request_current(
            self,
            error_type=ReferenceContextContractError,
        )


@dataclass(frozen=True, slots=True)
class ReferenceContextChunk:
    """One materialized reference excerpt with opaque source provenance."""

    content: str
    source_id: str
    source_version: str
    provenance_hash: str

    def __post_init__(self) -> None:
        _validate_chunk_current(
            self,
            error_type=ReferenceContextContractError,
            resource_error_type=ReferenceContextContractResourceError,
        )


@dataclass(frozen=True, slots=True)
class ReferenceContextMaterialization:
    """Untrusted source result to be rebound against the retained request."""

    grading_spec_ref: GradingSpecRef
    question_id: str
    context_policy: ContextPolicy
    chunks: tuple[ReferenceContextChunk, ...]

    def __post_init__(self) -> None:
        _validate_materialization_current(
            self,
            error_type=ReferenceContextContractError,
            resource_error_type=ReferenceContextContractResourceError,
        )


@dataclass(frozen=True, slots=True)
class ResolvedReferenceContext:
    """Independent evaluator-facing REF-1 snapshot."""

    grading_spec_ref: GradingSpecRef
    question_id: str
    context_policy: ContextPolicy
    chunks: tuple[ReferenceContextChunk, ...]

    def __post_init__(self) -> None:
        _validate_materialization_fields(
            self,
            owner_name="ResolvedReferenceContext",
            error_type=ReferenceContextContractError,
            resource_error_type=ReferenceContextContractResourceError,
        )


class ReferenceContextSource(Protocol):
    """Configured integration seam for already-admitted reference scope.

    Protocol conformance does not authenticate tenant/class/subject/reference
    scope or prove school/reference approval. The composition root/backend owns
    those external trust decisions. REF-1 only validates the deterministic
    binding and provenance shape of the returned Gradified-owned value.
    """

    def materialize_reference_context(
        self,
        *,
        request: ReferenceContextRequest,
    ) -> ReferenceContextMaterialization:
        ...


def _validate_request_current(
    value: object,
    *,
    error_type: type[_ErrorT],
) -> tuple[GradingSpecRef, str, ContextPolicy]:
    if type(value) is not ReferenceContextRequest:
        _raise(error_type, "reference request must be an exact ReferenceContextRequest.")

    grading_spec_ref = _required_field(
        value,
        "grading_spec_ref",
        owner_name="ReferenceContextRequest",
        error_type=error_type,
    )
    question_id = _required_field(
        value,
        "question_id",
        owner_name="ReferenceContextRequest",
        error_type=error_type,
    )
    context_policy = _required_field(
        value,
        "context_policy",
        owner_name="ReferenceContextRequest",
        error_type=error_type,
    )

    _validate_grading_spec_ref(
        grading_spec_ref,
        field_name="ReferenceContextRequest.grading_spec_ref",
        error_type=error_type,
    )
    validated_question_id = _validate_identifier(
        question_id,
        field_name="ReferenceContextRequest.question_id",
        error_type=error_type,
    )
    validated_policy = _require_context_policy(
        context_policy,
        field_name="ReferenceContextRequest.context_policy",
        error_type=error_type,
    )
    return grading_spec_ref, validated_question_id, validated_policy


def _validate_chunk_current(
    value: object,
    *,
    error_type: type[_ErrorT],
    resource_error_type: type[_ErrorT],
) -> tuple[str, str, str, str]:
    if type(value) is not ReferenceContextChunk:
        _raise(error_type, "reference chunk must be an exact ReferenceContextChunk.")

    content = _required_field(
        value,
        "content",
        owner_name="ReferenceContextChunk",
        error_type=error_type,
    )
    source_id = _required_field(
        value,
        "source_id",
        owner_name="ReferenceContextChunk",
        error_type=error_type,
    )
    source_version = _required_field(
        value,
        "source_version",
        owner_name="ReferenceContextChunk",
        error_type=error_type,
    )
    provenance_hash = _required_field(
        value,
        "provenance_hash",
        owner_name="ReferenceContextChunk",
        error_type=error_type,
    )

    validated_content = _require_bounded_text(
        content,
        field_name="ReferenceContextChunk.content",
        maximum_characters=MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS,
        error_type=error_type,
        resource_error_type=resource_error_type,
        strip_sensitive=False,
    )
    validated_source_id = _require_bounded_text(
        source_id,
        field_name="ReferenceContextChunk.source_id",
        maximum_characters=MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS,
        error_type=error_type,
        resource_error_type=resource_error_type,
        strip_sensitive=True,
    )
    validated_source_version = _require_bounded_text(
        source_version,
        field_name="ReferenceContextChunk.source_version",
        maximum_characters=MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS,
        error_type=error_type,
        resource_error_type=resource_error_type,
        strip_sensitive=True,
    )
    validated_hash = _require_bounded_text(
        provenance_hash,
        field_name="ReferenceContextChunk.provenance_hash",
        maximum_characters=MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS,
        error_type=error_type,
        resource_error_type=resource_error_type,
        strip_sensitive=True,
    )
    return (
        validated_content,
        validated_source_id,
        validated_source_version,
        validated_hash,
    )


def _validate_materialization_fields(
    value: object,
    *,
    owner_name: str,
    error_type: type[_ErrorT],
    resource_error_type: type[_ErrorT],
) -> tuple[GradingSpecRef, str, ContextPolicy, tuple[tuple[str, str, str, str], ...]]:
    grading_spec_ref = _required_field(
        value,
        "grading_spec_ref",
        owner_name=owner_name,
        error_type=error_type,
    )
    question_id = _required_field(
        value,
        "question_id",
        owner_name=owner_name,
        error_type=error_type,
    )
    context_policy = _required_field(
        value,
        "context_policy",
        owner_name=owner_name,
        error_type=error_type,
    )
    chunks = _required_field(
        value,
        "chunks",
        owner_name=owner_name,
        error_type=error_type,
    )

    _validate_grading_spec_ref(
        grading_spec_ref,
        field_name=f"{owner_name}.grading_spec_ref",
        error_type=error_type,
    )
    validated_question_id = _validate_identifier(
        question_id,
        field_name=f"{owner_name}.question_id",
        error_type=error_type,
    )
    validated_policy = _require_context_policy(
        context_policy,
        field_name=f"{owner_name}.context_policy",
        error_type=error_type,
    )

    if type(chunks) is not tuple:
        _raise(error_type, f"{owner_name}.chunks must be an exact tuple.")
    if len(chunks) > MAX_REFERENCE_CONTEXT_CHUNKS:
        _raise(
            resource_error_type,
            f"{owner_name}.chunks exceeds the REF-1-v1 {MAX_REFERENCE_CONTEXT_CHUNKS}-chunk limit.",
        )

    # Prove the entire element-type universe before dispatching into any chunk.
    if any(type(chunk) is not ReferenceContextChunk for chunk in chunks):
        _raise(
            error_type,
            f"{owner_name}.chunks must contain only exact ReferenceContextChunk values.",
        )

    validated_chunks: list[tuple[str, str, str, str]] = []
    total_content_characters = 0
    for chunk in chunks:
        fields = _validate_chunk_current(
            chunk,
            error_type=error_type,
            resource_error_type=resource_error_type,
        )
        total_content_characters += len(fields[0])
        if total_content_characters > MAX_REFERENCE_CONTEXT_TOTAL_CONTENT_CHARACTERS:
            _raise(
                resource_error_type,
                f"{owner_name}.chunks exceed the REF-1-v1 "
                f"{MAX_REFERENCE_CONTEXT_TOTAL_CONTENT_CHARACTERS}-character total-content limit.",
            )
        validated_chunks.append(fields)

    return grading_spec_ref, validated_question_id, validated_policy, tuple(validated_chunks)


def _validate_materialization_current(
    value: object,
    *,
    error_type: type[_ErrorT],
    resource_error_type: type[_ErrorT],
) -> tuple[GradingSpecRef, str, ContextPolicy, tuple[tuple[str, str, str, str], ...]]:
    if type(value) is not ReferenceContextMaterialization:
        _raise(
            error_type,
            "source result must be an exact ReferenceContextMaterialization.",
        )
    return _validate_materialization_fields(
        value,
        owner_name="ReferenceContextMaterialization",
        error_type=error_type,
        resource_error_type=resource_error_type,
    )
