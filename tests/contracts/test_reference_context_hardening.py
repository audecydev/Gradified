from __future__ import annotations

import inspect

import pytest

from grading.active_question_authority import ContextPolicy
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.contracts.reference_context import (
    MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS,
    MAX_REFERENCE_CONTEXT_CHUNKS,
    MAX_REFERENCE_CONTEXT_TOTAL_CONTENT_CHARACTERS,
    MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS,
    REFERENCE_CONTEXT_SCHEMA_VERSION,
    ReferenceContextChunk,
    ReferenceContextContractError,
    ReferenceContextContractResourceError,
    ReferenceContextMaterialization,
    ReferenceContextRequest,
    ReferenceContextSource,
    ResolvedReferenceContext,
)


def _spec(version: int = 1) -> GradingSpecRef:
    return GradingSpecRef(id="SPEC-REF-1", version=version)


def _chunk(
    *,
    content: str = "Reference excerpt.",
    source_id: str = "TEXTBOOK-A",
    source_version: str = "edition-2026",
    provenance_hash: str = "opaque-hash-token",
) -> ReferenceContextChunk:
    return ReferenceContextChunk(
        content=content,
        source_id=source_id,
        source_version=source_version,
        provenance_hash=provenance_hash,
    )


def test_ref1_schema_and_resource_limits_are_frozen() -> None:
    assert REFERENCE_CONTEXT_SCHEMA_VERSION == "1"
    assert MAX_REFERENCE_CONTEXT_CHUNKS == 32
    assert MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS == 8192
    assert MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS == 128
    assert MAX_REFERENCE_CONTEXT_TOTAL_CONTENT_CHARACTERS == 65536


@pytest.mark.parametrize(
    "policy",
    [
        ContextPolicy.DIRECT,
        ContextPolicy.DIRECT_PLUS_REFERENCE,
        ContextPolicy.HYBRID_RETRIEVAL,
        ContextPolicy.REFERENCE_ONLY,
    ],
)
def test_request_accepts_exact_context_policy_members(policy: ContextPolicy) -> None:
    request = ReferenceContextRequest(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=policy,
    )
    assert request.context_policy is policy


def test_request_rejects_foreign_grading_spec_ref() -> None:
    with pytest.raises(ReferenceContextContractError):
        ReferenceContextRequest(
            grading_spec_ref=object(),  # type: ignore[arg-type]
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
        )


@pytest.mark.parametrize("question_id", ["", " Q1", "Q1 ", 1, True, None])
def test_request_rejects_invalid_question_identity(question_id: object) -> None:
    with pytest.raises(ReferenceContextContractError):
        ReferenceContextRequest(
            grading_spec_ref=_spec(),
            question_id=question_id,  # type: ignore[arg-type]
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
        )


def test_request_rejects_foreign_context_policy() -> None:
    with pytest.raises(ReferenceContextContractError):
        ReferenceContextRequest(
            grading_spec_ref=_spec(),
            question_id="Q1",
            context_policy="HYBRID_RETRIEVAL",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field_name", ["source_id", "source_version", "provenance_hash"])
def test_chunk_accepts_provenance_field_limit(field_name: str) -> None:
    kwargs = {field_name: "x" * MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS}
    chunk = _chunk(**kwargs)
    assert getattr(chunk, field_name) == "x" * MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS


@pytest.mark.parametrize("field_name", ["source_id", "source_version", "provenance_hash"])
def test_chunk_rejects_provenance_field_limit_plus_one(field_name: str) -> None:
    kwargs = {field_name: "x" * (MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS + 1)}
    with pytest.raises(ReferenceContextContractResourceError):
        _chunk(**kwargs)


@pytest.mark.parametrize("field_name", ["source_id", "source_version", "provenance_hash"])
@pytest.mark.parametrize("value", ["", " value", "value ", 1, True, None])
def test_chunk_rejects_malformed_provenance_fields(field_name: str, value: object) -> None:
    kwargs = {field_name: value}
    with pytest.raises(ReferenceContextContractError):
        _chunk(**kwargs)


def test_chunk_accepts_content_at_limit() -> None:
    chunk = _chunk(content="x" * MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS)
    assert len(chunk.content) == MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS


def test_chunk_rejects_content_limit_plus_one() -> None:
    with pytest.raises(ReferenceContextContractResourceError):
        _chunk(content="x" * (MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS + 1))


@pytest.mark.parametrize("content", ["", 1, True, None])
def test_chunk_rejects_invalid_content(content: object) -> None:
    with pytest.raises(ReferenceContextContractError):
        _chunk(content=content)  # type: ignore[arg-type]


def test_chunk_preserves_content_whitespace_without_normalization() -> None:
    chunk = _chunk(content="  exact excerpt\n")
    assert chunk.content == "  exact excerpt\n"


def test_chunk_treats_hash_as_opaque_and_does_not_require_sha_shape() -> None:
    chunk = _chunk(content="abc", provenance_hash="not-a-sha")
    assert chunk.provenance_hash == "not-a-sha"


def test_chunk_treats_source_version_as_opaque_and_does_not_require_numeric_ordering() -> None:
    chunk = _chunk(source_version="teacher-edition-final")
    assert chunk.source_version == "teacher-edition-final"


def test_materialization_accepts_empty_tuple() -> None:
    materialization = ReferenceContextMaterialization(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=ContextPolicy.REFERENCE_ONLY,
        chunks=(),
    )
    assert materialization.chunks == ()


def test_materialization_accepts_chunk_count_at_limit() -> None:
    chunks = tuple(_chunk(content="x") for _ in range(MAX_REFERENCE_CONTEXT_CHUNKS))
    materialization = ReferenceContextMaterialization(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=ContextPolicy.HYBRID_RETRIEVAL,
        chunks=chunks,
    )
    assert len(materialization.chunks) == MAX_REFERENCE_CONTEXT_CHUNKS


def test_materialization_rejects_chunk_count_limit_plus_one() -> None:
    chunks = tuple(_chunk(content="x") for _ in range(MAX_REFERENCE_CONTEXT_CHUNKS + 1))
    with pytest.raises(ReferenceContextContractResourceError):
        ReferenceContextMaterialization(
            grading_spec_ref=_spec(),
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=chunks,
        )


def test_materialization_accepts_total_content_at_limit() -> None:
    chunks = tuple(_chunk(content="x" * 8192) for _ in range(8))
    materialization = ReferenceContextMaterialization(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=ContextPolicy.HYBRID_RETRIEVAL,
        chunks=chunks,
    )
    assert sum(len(chunk.content) for chunk in materialization.chunks) == 65536


def test_materialization_rejects_total_content_limit_plus_one() -> None:
    chunks = tuple(_chunk(content="x" * 8192) for _ in range(8)) + (_chunk(content="x"),)
    with pytest.raises(ReferenceContextContractResourceError):
        ReferenceContextMaterialization(
            grading_spec_ref=_spec(),
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=chunks,
        )


def test_materialization_rejects_non_tuple_chunks() -> None:
    with pytest.raises(ReferenceContextContractError):
        ReferenceContextMaterialization(
            grading_spec_ref=_spec(),
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=[_chunk()],  # type: ignore[arg-type]
        )


def test_materialization_rejects_foreign_chunk_before_nested_dispatch() -> None:
    class ForeignChunk:
        @property
        def content(self) -> str:
            raise AssertionError("foreign chunk field was accessed")

    valid = ReferenceContextMaterialization(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=ContextPolicy.HYBRID_RETRIEVAL,
        chunks=(_chunk(),),
    )
    object.__setattr__(valid, "chunks", (ForeignChunk(),))

    with pytest.raises(ReferenceContextContractError):
        valid.__post_init__()


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("grading_spec_ref", object()),
        ("question_id", " Q1"),
        ("context_policy", "HYBRID_RETRIEVAL"),
    ],
)
def test_materialization_revalidates_mutated_binding(field_name: str, value: object) -> None:
    materialization = ReferenceContextMaterialization(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=ContextPolicy.HYBRID_RETRIEVAL,
        chunks=(),
    )
    object.__setattr__(materialization, field_name, value)
    with pytest.raises(ReferenceContextContractError):
        materialization.__post_init__()


def test_resolved_context_contract_is_immutable_value_shape() -> None:
    resolved = ResolvedReferenceContext(
        grading_spec_ref=_spec(),
        question_id="Q1",
        context_policy=ContextPolicy.DIRECT_PLUS_REFERENCE,
        chunks=(_chunk(),),
    )
    with pytest.raises(AttributeError):
        resolved.question_id = "Q2"  # type: ignore[misc]


def test_source_protocol_exposes_only_materialization_call_contract() -> None:
    signature = inspect.signature(ReferenceContextSource.materialize_reference_context)
    assert tuple(signature.parameters) == ("self", "request")
