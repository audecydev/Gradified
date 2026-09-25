from __future__ import annotations

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.contracts.paper_aggregation import (
    GradingSpecRef,
    _validate_grading_spec_ref,
    _validate_identifier,
)
from grading.contracts.reference_context import (
    ReferenceContextChunk,
    ReferenceContextContractError,
    ReferenceContextContractResourceError,
    ReferenceContextMaterialization,
    ReferenceContextRequest,
    ReferenceContextSource,
    ResolvedReferenceContext,
    _validate_materialization_current,
)


class ReferenceContextError(Exception):
    """Base class for expected REF-1 resolution failures."""


class ReferenceContextUnsupportedPolicyError(ReferenceContextError):
    """REF-1 was invoked for a context policy that does not permit references."""


class ReferenceContextSourceExecutionError(ReferenceContextError):
    """Configured reference source failed while materializing context."""


class ReferenceContextMaterializationError(ReferenceContextError):
    """Configured source returned a malformed REF-1 materialization."""


class ReferenceContextBindingError(ReferenceContextError):
    """Returned reference context is bound to the wrong ACTIVE question context."""


class ReferenceContextResourceError(ReferenceContextError):
    """Returned reference context exceeds REF-1-v1 resource limits."""


def _snapshot_spec_ref(spec_ref: GradingSpecRef) -> GradingSpecRef:
    return GradingSpecRef(
        id=object.__getattribute__(spec_ref, "id"),
        version=object.__getattribute__(spec_ref, "version"),
    )


def _authority_binding_snapshot(
    resolved_authority: object,
) -> tuple[GradingSpecRef, str, ContextPolicy]:
    if type(resolved_authority) is not ResolvedQuestionAuthority:
        raise TypeError(
            "resolved_authority must be an exact ResolvedQuestionAuthority."
        )

    try:
        grading_spec_ref = object.__getattribute__(resolved_authority, "grading_spec_ref")
        question_id = object.__getattribute__(resolved_authority, "question_id")
        context_policy = object.__getattribute__(resolved_authority, "context_policy")
    except AttributeError as exc:
        raise ReferenceContextBindingError(
            "resolved ACTIVE question authority is missing a REF-1 binding field."
        ) from exc

    validated_spec_ref = _validate_grading_spec_ref(
        grading_spec_ref,
        field_name="resolved_authority.grading_spec_ref",
        error_type=ReferenceContextBindingError,
    )
    validated_question_id = _validate_identifier(
        question_id,
        field_name="resolved_authority.question_id",
        error_type=ReferenceContextBindingError,
    )
    if type(context_policy) is not ContextPolicy or not any(
        context_policy is member for member in ContextPolicy
    ):
        raise ReferenceContextBindingError(
            "resolved_authority.context_policy must be a canonical ContextPolicy member."
        )

    return _snapshot_spec_ref(validated_spec_ref), validated_question_id, context_policy


def resolve_reference_context(
    *,
    resolved_authority: ResolvedQuestionAuthority,
    source: ReferenceContextSource,
) -> ResolvedReferenceContext:
    """Materialize reference context without creating retrieval or academic authority.

    The configured source owns access/retrieval mechanics and its already-admitted
    tenant/class/subject/reference scope. REF-1 derives the request only from the
    current ACTIVE question authority, verifies the returned binding/provenance
    shape, applies bounded resource admission, and returns an independent snapshot.
    """

    retained_spec_ref, retained_question_id, retained_policy = _authority_binding_snapshot(
        resolved_authority
    )

    if retained_policy is ContextPolicy.DIRECT:
        raise ReferenceContextUnsupportedPolicyError(
            "REF-1 must not materialize reference context for ContextPolicy.DIRECT."
        )

    retained_request = ReferenceContextRequest(
        grading_spec_ref=_snapshot_spec_ref(retained_spec_ref),
        question_id=retained_question_id,
        context_policy=retained_policy,
    )
    source_request = ReferenceContextRequest(
        grading_spec_ref=_snapshot_spec_ref(retained_spec_ref),
        question_id=retained_question_id,
        context_policy=retained_policy,
    )

    try:
        candidate = source.materialize_reference_context(request=source_request)
    except ReferenceContextContractResourceError as exc:
        raise ReferenceContextResourceError(
            "configured source attempted to materialize reference context beyond REF-1-v1 resource limits."
        ) from exc
    except ReferenceContextContractError as exc:
        raise ReferenceContextMaterializationError(
            "configured source failed while constructing a REF-1 domain result."
        ) from exc
    except Exception as exc:
        raise ReferenceContextSourceExecutionError(
            "configured reference source failed during context materialization."
        ) from exc

    # Do not broad-catch anything below this point: unexpected REF-1 programming
    # failures must remain technical failures rather than being reclassified as
    # hostile source data.
    (
        returned_spec_ref,
        returned_question_id,
        returned_policy,
        validated_chunks,
    ) = _validate_materialization_current(
        candidate,
        error_type=ReferenceContextMaterializationError,
        resource_error_type=ReferenceContextResourceError,
    )

    if returned_spec_ref != retained_request.grading_spec_ref:
        raise ReferenceContextBindingError(
            "source materialization grading_spec_ref does not match the retained ACTIVE binding."
        )
    if returned_question_id != retained_request.question_id:
        raise ReferenceContextBindingError(
            "source materialization question_id does not match the retained ACTIVE binding."
        )
    if returned_policy is not retained_request.context_policy:
        raise ReferenceContextBindingError(
            "source materialization context_policy does not match the retained ACTIVE binding."
        )

    resolved_chunks = tuple(
        ReferenceContextChunk(
            content=content,
            source_id=source_id,
            source_version=source_version,
            provenance_hash=provenance_hash,
        )
        for content, source_id, source_version, provenance_hash in validated_chunks
    )

    return ResolvedReferenceContext(
        grading_spec_ref=_snapshot_spec_ref(retained_request.grading_spec_ref),
        question_id=retained_request.question_id,
        context_policy=retained_request.context_policy,
        chunks=resolved_chunks,
    )
