from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

import grading.reference_context as reference_module
from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.contracts.reference_context import (
    MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS,
    MAX_REFERENCE_CONTEXT_CHUNKS,
    MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS,
    ReferenceContextChunk,
    ReferenceContextMaterialization,
    ReferenceContextRequest,
)
from grading.reference_context import (
    ReferenceContextBindingError,
    ReferenceContextMaterializationError,
    ReferenceContextResourceError,
    ReferenceContextSourceExecutionError,
    ReferenceContextUnsupportedPolicyError,
    resolve_reference_context,
)


def _authority(
    *,
    spec_id: str = "SPEC-REF-1",
    spec_version: int = 1,
    question_id: str = "Q1",
    policy: ContextPolicy = ContextPolicy.HYBRID_RETRIEVAL,
) -> ResolvedQuestionAuthority:
    return ResolvedQuestionAuthority(
        grading_spec_ref=GradingSpecRef(id=spec_id, version=spec_version),
        question_id=question_id,
        question_text="Question",
        context_policy=policy,
        rubric_content=cast(object, object()),  # REF-1 deliberately does not consume this field.
        scoring_authority=cast(object, object()),  # REF-1 deliberately does not consume this field.
    )


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


def _materialization(
    request: ReferenceContextRequest,
    *,
    chunks: tuple[ReferenceContextChunk, ...] = (),
) -> ReferenceContextMaterialization:
    return ReferenceContextMaterialization(
        grading_spec_ref=GradingSpecRef(
            id=request.grading_spec_ref.id,
            version=request.grading_spec_ref.version,
        ),
        question_id=request.question_id,
        context_policy=request.context_policy,
        chunks=chunks,
    )


class _Source:
    def __init__(self, factory):
        self.factory = factory
        self.calls = 0
        self.seen_request: ReferenceContextRequest | None = None

    def materialize_reference_context(self, *, request: ReferenceContextRequest):
        self.calls += 1
        self.seen_request = request
        return self.factory(request)


def test_direct_policy_rejects_before_source_invocation() -> None:
    source = _Source(lambda request: (_ for _ in ()).throw(AssertionError("source called")))
    with pytest.raises(ReferenceContextUnsupportedPolicyError):
        resolve_reference_context(
            resolved_authority=_authority(policy=ContextPolicy.DIRECT),
            source=source,
        )
    assert source.calls == 0


@pytest.mark.parametrize(
    "policy",
    [
        ContextPolicy.DIRECT_PLUS_REFERENCE,
        ContextPolicy.HYBRID_RETRIEVAL,
        ContextPolicy.REFERENCE_ONLY,
    ],
)
def test_reference_policies_materialize_exact_context(policy: ContextPolicy) -> None:
    source = _Source(lambda request: _materialization(request, chunks=(_chunk(),)))
    resolved = resolve_reference_context(
        resolved_authority=_authority(policy=policy),
        source=source,
    )
    assert source.calls == 1
    assert resolved.context_policy is policy
    assert resolved.question_id == "Q1"
    assert resolved.grading_spec_ref == GradingSpecRef(id="SPEC-REF-1", version=1)
    assert resolved.chunks == (_chunk(),)


def test_valid_empty_materialization_resolves_to_empty_context() -> None:
    source = _Source(lambda request: _materialization(request, chunks=()))
    resolved = resolve_reference_context(resolved_authority=_authority(), source=source)
    assert resolved.chunks == ()


@pytest.mark.parametrize(
    "exception",
    [TimeoutError("timeout"), RuntimeError("boom"), ValueError("source-value-failure")],
)
def test_source_exceptions_remain_source_execution_failures(exception: Exception) -> None:
    source = _Source(lambda request: (_ for _ in ()).throw(exception))
    with pytest.raises(ReferenceContextSourceExecutionError) as captured:
        resolve_reference_context(resolved_authority=_authority(), source=source)
    assert captured.value.__cause__ is exception


def test_missing_source_method_is_source_execution_failure_not_type_admission() -> None:
    with pytest.raises(ReferenceContextSourceExecutionError) as captured:
        resolve_reference_context(resolved_authority=_authority(), source=object())  # type: ignore[arg-type]
    assert isinstance(captured.value.__cause__, AttributeError)


def test_malformed_source_return_is_materialization_failure() -> None:
    source = _Source(lambda request: object())
    with pytest.raises(ReferenceContextMaterializationError):
        resolve_reference_context(resolved_authority=_authority(), source=source)


def test_source_side_contract_resource_failure_is_preserved_as_resource_failure() -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        return _materialization(
            request,
            chunks=(_chunk(content="x" * (MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS + 1)),),
        )

    with pytest.raises(ReferenceContextResourceError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


def test_source_side_contract_shape_failure_is_preserved_as_materialization_failure() -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        return ReferenceContextMaterialization(
            grading_spec_ref=request.grading_spec_ref,
            question_id=request.question_id,
            context_policy=request.context_policy,
            chunks=[_chunk()],  # type: ignore[arg-type]
        )

    with pytest.raises(ReferenceContextMaterializationError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


@pytest.mark.parametrize("field", ["grading_spec_ref", "question_id", "context_policy"])
def test_wrong_returned_binding_fails_closed(field: str) -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        result = _materialization(request, chunks=(_chunk(),))
        if field == "grading_spec_ref":
            object.__setattr__(result, field, GradingSpecRef(id="OTHER", version=1))
        elif field == "question_id":
            object.__setattr__(result, field, "Q2")
        else:
            object.__setattr__(result, field, ContextPolicy.REFERENCE_ONLY)
        return result

    with pytest.raises(ReferenceContextBindingError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


def test_foreign_materialization_is_rejected_before_field_dispatch() -> None:
    class ForeignMaterialization:
        @property
        def grading_spec_ref(self):
            raise AssertionError("foreign materialization field accessed")

    source = _Source(lambda request: ForeignMaterialization())
    with pytest.raises(ReferenceContextMaterializationError):
        resolve_reference_context(resolved_authority=_authority(), source=source)


def test_foreign_chunk_is_rejected_before_nested_field_dispatch() -> None:
    class ForeignChunk:
        @property
        def content(self):
            raise AssertionError("foreign chunk field accessed")

    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        result = _materialization(request, chunks=(_chunk(),))
        object.__setattr__(result, "chunks", (ForeignChunk(),))
        return result

    with pytest.raises(ReferenceContextMaterializationError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


def test_source_receives_request_not_authority_object() -> None:
    authority = _authority()
    source = _Source(lambda request: _materialization(request))
    resolve_reference_context(resolved_authority=authority, source=source)
    assert source.seen_request is not authority
    assert type(source.seen_request) is ReferenceContextRequest


def test_source_request_and_retained_binding_do_not_share_grading_spec_ref() -> None:
    original = _authority()

    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        object.__setattr__(request.grading_spec_ref, "id", "MUTATED-BY-SOURCE")
        # A malicious source may mutate its own request; it still returns the
        # originally requested binding. The resolver's retained binding must win.
        return ReferenceContextMaterialization(
            grading_spec_ref=GradingSpecRef(id="SPEC-REF-1", version=1),
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=(),
        )

    resolved = resolve_reference_context(resolved_authority=original, source=_Source(factory))
    assert resolved.grading_spec_ref.id == "SPEC-REF-1"
    assert original.grading_spec_ref.id == "SPEC-REF-1"


def test_source_request_mutation_cannot_rewrite_retained_question_or_policy() -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        object.__setattr__(request, "question_id", "Q999")
        object.__setattr__(request, "context_policy", ContextPolicy.REFERENCE_ONLY)
        return ReferenceContextMaterialization(
            grading_spec_ref=GradingSpecRef(id="SPEC-REF-1", version=1),
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=(),
        )

    resolved = resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))
    assert resolved.question_id == "Q1"
    assert resolved.context_policy is ContextPolicy.HYBRID_RETRIEVAL


def test_authority_binding_is_snapshotted_before_source_execution() -> None:
    authority = _authority()

    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        object.__setattr__(authority, "question_id", "Q999")
        object.__setattr__(authority.grading_spec_ref, "id", "MUTATED-AUTHORITY")
        return ReferenceContextMaterialization(
            grading_spec_ref=GradingSpecRef(id="SPEC-REF-1", version=1),
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=(),
        )

    resolved = resolve_reference_context(resolved_authority=authority, source=_Source(factory))
    assert resolved.grading_spec_ref.id == "SPEC-REF-1"
    assert resolved.question_id == "Q1"


def test_malformed_authority_binding_is_rejected_before_source_call() -> None:
    authority = _authority()
    object.__setattr__(authority, "question_id", " Q1")
    source = _Source(lambda request: _materialization(request))
    with pytest.raises(ReferenceContextBindingError):
        resolve_reference_context(resolved_authority=authority, source=source)
    assert source.calls == 0


def test_foreign_authority_is_rejected_before_source_call() -> None:
    class ForeignAuthority:
        @property
        def grading_spec_ref(self):
            raise AssertionError("foreign authority field accessed")

    source = _Source(lambda request: _materialization(request))
    with pytest.raises(TypeError):
        resolve_reference_context(resolved_authority=ForeignAuthority(), source=source)  # type: ignore[arg-type]
    assert source.calls == 0


def test_source_owned_chunk_mutation_after_resolution_does_not_change_snapshot() -> None:
    source_chunk = _chunk(content="before")
    source_materialization: ReferenceContextMaterialization | None = None

    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        nonlocal source_materialization
        source_materialization = _materialization(request, chunks=(source_chunk,))
        return source_materialization

    resolved = resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))
    object.__setattr__(source_chunk, "content", "after")
    assert source_materialization is not None
    object.__setattr__(source_materialization, "question_id", "Q999")

    assert resolved.question_id == "Q1"
    assert resolved.chunks[0].content == "before"
    assert resolved.chunks[0] is not source_chunk


def test_resolved_grading_spec_ref_does_not_alias_source_returned_ref() -> None:
    returned_ref: GradingSpecRef | None = None

    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        nonlocal returned_ref
        returned_ref = GradingSpecRef(id="SPEC-REF-1", version=1)
        return ReferenceContextMaterialization(
            grading_spec_ref=returned_ref,
            question_id="Q1",
            context_policy=ContextPolicy.HYBRID_RETRIEVAL,
            chunks=(),
        )

    resolved = resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))
    assert returned_ref is not None
    object.__setattr__(returned_ref, "id", "MUTATED")
    assert resolved.grading_spec_ref.id == "SPEC-REF-1"


def test_source_order_is_preserved_without_deduplication_or_sorting() -> None:
    chunks = (
        _chunk(content="B", source_id="S2"),
        _chunk(content="A", source_id="S1"),
        _chunk(content="B", source_id="S2"),
    )
    source = _Source(lambda request: _materialization(request, chunks=chunks))
    resolved = resolve_reference_context(resolved_authority=_authority(), source=source)
    assert tuple(chunk.content for chunk in resolved.chunks) == ("B", "A", "B")
    assert len(resolved.chunks) == 3


def test_opaque_hash_is_preserved_not_recomputed() -> None:
    chunk = _chunk(content="abc", provenance_hash="definitely-not-sha256")
    source = _Source(lambda request: _materialization(request, chunks=(chunk,)))
    resolved = resolve_reference_context(resolved_authority=_authority(), source=source)
    assert resolved.chunks[0].provenance_hash == "definitely-not-sha256"


def test_source_version_is_preserved_not_ordered_or_normalized() -> None:
    chunk = _chunk(source_version="v-final-school-edition")
    source = _Source(lambda request: _materialization(request, chunks=(chunk,)))
    resolved = resolve_reference_context(resolved_authority=_authority(), source=source)
    assert resolved.chunks[0].source_version == "v-final-school-edition"


def test_chunk_count_resource_failure_is_distinct() -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        valid = _materialization(request)
        object.__setattr__(valid, "chunks", tuple(_chunk(content="x") for _ in range(MAX_REFERENCE_CONTEXT_CHUNKS + 1)))
        return valid

    with pytest.raises(ReferenceContextResourceError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


@pytest.mark.parametrize("field", ["source_id", "source_version", "provenance_hash"])
def test_provenance_resource_failure_is_distinct(field: str) -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        chunk = _chunk()
        result = _materialization(request, chunks=(chunk,))
        object.__setattr__(chunk, field, "x" * (MAX_REFERENCE_PROVENANCE_FIELD_CHARACTERS + 1))
        return result

    with pytest.raises(ReferenceContextResourceError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


def test_content_resource_failure_is_distinct() -> None:
    def factory(request: ReferenceContextRequest) -> ReferenceContextMaterialization:
        chunk = _chunk()
        result = _materialization(request, chunks=(chunk,))
        object.__setattr__(chunk, "content", "x" * (MAX_REFERENCE_CHUNK_CONTENT_CHARACTERS + 1))
        return result

    with pytest.raises(ReferenceContextResourceError):
        resolve_reference_context(resolved_authority=_authority(), source=_Source(factory))


def test_internal_programming_failure_is_not_reclassified_as_source_or_materialization_failure(monkeypatch) -> None:
    source = _Source(lambda request: _materialization(request))

    def explode(*args, **kwargs):
        raise AssertionError("internal bug")

    monkeypatch.setattr(reference_module, "_validate_materialization_current", explode)
    with pytest.raises(AssertionError, match="internal bug"):
        resolve_reference_context(resolved_authority=_authority(), source=source)


def test_public_resolver_does_not_accept_caller_binding_overrides() -> None:
    import inspect

    signature = inspect.signature(resolve_reference_context)
    assert tuple(signature.parameters) == ("resolved_authority", "source")
