# Reference Context Integration Guide

This guide is for the engineer connecting school reference material to Gradified.

## What REF-1 already provides

The core already provides a backend-independent reference-context boundary.

The main function is:

```python
resolve_reference_context(
    resolved_authority=...,
    source=...,
)
```

The configured source implements:

```python
materialize_reference_context(
    request=ReferenceContextRequest(...)
) -> ReferenceContextMaterialization
```

The source owns real storage/search/access mechanics. The core owns binding checks, resource admission, provenance-shape validation, and immutable snapshot materialization.

## Context policies

The ACTIVE question authority can use:

- `DIRECT` — no reference materialization; REF-1 rejects the operation before the source is called.
- `DIRECT_PLUS_REFERENCE`
- `HYBRID_RETRIEVAL`
- `REFERENCE_ONLY`

REF-1 does not implement the academic semantics of the last three policies. It only materializes bounded context safely.

## What each returned chunk must contain

Each `ReferenceContextChunk` contains exactly:

```text
content
source_id
source_version
provenance_hash
```

The core preserves these fields. It does **not** assume:

- a specific hash algorithm;
- that the hash is SHA-256 of chunk text;
- version ordering;
- chunk identity;
- ranking meaning.

## REF-1 v1 resource limits

The frozen limits are:

- maximum chunks: **32**
- maximum characters in one chunk: **8192**
- maximum characters in each provenance field: **128**
- maximum total chunk-content characters: **65536**

A successful source result with `chunks == ()` is valid. Higher-level policy decides what an empty context means for grading/review.

## Source responsibilities

Before returning material, the real source/backend must enforce its trusted scope, including the appropriate tenant and approved reference/version rules.

The core does not authenticate those external facts.

The source must never respond to a missing authorized reference by searching unrelated tenants or unrelated material.

## Binding rules

The core derives a request from the already-resolved ACTIVE question authority and checks that returned materialization echoes the exact:

- grading-spec reference/version;
- question ID;
- context policy.

Returning context for another question/spec/policy fails closed.

## First reference integration test

1. Choose one ACTIVE question with a non-DIRECT context policy.
2. Resolve its `ResolvedQuestionAuthority`.
3. Configure the real source with the already-admitted tenant/reference scope.
4. Return one known chunk with source/version/provenance values.
5. Confirm `resolve_reference_context()` succeeds.
6. Return the same content with a wrong question ID; confirm it fails.
7. Return the same content with a wrong spec version; confirm it fails.
8. Return more than 32 chunks; confirm resource failure.
9. Return one oversized chunk; confirm resource failure.
10. Return zero chunks; confirm a valid empty resolved context.
11. Invoke REF-1 for `DIRECT`; confirm the source is never called.
12. At integration level, prove a tenant cannot retrieve another tenant's reference material.

## Expected outcome

The core receives bounded, provenance-preserving material for the exact ACTIVE question. Real tenant isolation and academic approval remain integration responsibilities and must be proven separately.
