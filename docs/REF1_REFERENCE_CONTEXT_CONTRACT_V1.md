# REF-1 Reference Context Materialization & Provenance Boundary v1

Status: **source audit complete; BUILD authorized; causal RED authorized; GREEN not yet authorized**.

This document freezes only the authority/boundary semantics required to write a causal RED for REF-1. Exact resource-limit values and the final GREEN implementation remain subject to the post-RED implementation gate; they may not broaden the authority model below.

## 1. Purpose

REF-1 establishes a backend/search-technology-independent grading-core seam for materializing reference context with preserved provenance. It does not implement retrieval ranking, semantic grading, school/reference approval, tenant authentication, workflow decisions, or a concrete backend/search adapter.

The accepted architecture requires a RetrievalPort-style seam, approved-version retrieval, tenant/class/subject/reference filtering in the trusted upstream integration, and provenance for every returned chunk. REF-1 owns only the deterministic core boundary around those facts.

## 2. Existing authority consumed

REF-1 consumes one exact current `ResolvedQuestionAuthority` from the already-frozen ACTIVE question-authority boundary.

The public REF-1 resolver must derive its reference-context request from that authority. A caller does not separately supply `grading_spec_ref`, `question_id`, or `context_policy` to the resolver.

Only these existing authority fields are consumed by REF-1 v1:

- `grading_spec_ref`;
- `question_id`;
- `context_policy`.

REF-1 must revalidate the exact current binding fields it consumes before deriving a request. It does not need to reinterpret or recreate rubric/scoring authority.

## 3. ContextPolicy boundary

`ContextPolicy.DIRECT` means no reference materialization. REF-1 must reject the operation locally before invoking the configured source.

The following existing policies may enter REF-1:

- `DIRECT_PLUS_REFERENCE`;
- `HYBRID_RETRIEVAL`;
- `REFERENCE_ONLY`.

REF-1 does not implement the academic/workflow meaning of those policies. In particular it does not decide fallback, review, inability, semantic evaluation, or publication behavior.

## 4. Internal request custody

The resolver derives an immutable Gradified-owned request containing exactly:

- `grading_spec_ref`;
- `question_id`;
- `context_policy`.

The resolver retains one validated binding snapshot and supplies the configured source a distinct request object/snapshot. The configured source must never receive the caller's `ResolvedQuestionAuthority` object directly.

Mutation of the source-facing request must not rewrite the retained binding against which returned material is checked.

## 5. Configured source seam

The configured reference source is polymorphic. REF-1 must not exact-type-check or hard-code concrete adapter implementations.

Protocol conformance is not authentication. The composition root/backend remains responsible for configuring a source that applies trusted/admitted tenant/class/subject/reference scope and approval/version policy before returning material.

REF-1 must never derive tenant/class/subject/reference authorization from student evidence, answer text, question text, or other untrusted content.

The adapter invocation is the only broad source-execution exception boundary. Exceptions raised by the configured source are contained as source-execution failures. REF-1's own post-return validation/snapshot code must not be wrapped in a blanket `except Exception` that would disguise programming defects as hostile input.

## 6. Materialization envelope

The configured source returns one exact Gradified-owned reference-context materialization value bound to:

- `grading_spec_ref`;
- `question_id`;
- `context_policy`;
- an exact tuple of reference-context chunks.

The returned binding fields are untrusted source claims, not new authority. REF-1 cross-checks them against the independently retained request binding.

Wrong spec, wrong question, or wrong context policy is a binding failure.

## 7. Reference-context chunk v1

A REF-1 v1 chunk contains only:

- `content`;
- `source_id`;
- `source_version`;
- `provenance_hash`.

These are Gradified-owned immutable scalar fields in the resolved snapshot.

REF-1 validates only representation, presence, and resource bounds. It does **not** establish that:

- the source belongs to the correct school;
- a teacher/school approved the source;
- a tenant claim is historically true;
- a version is newest or ordered relative to another version;
- the provenance hash is SHA-256 or any other specific algorithm;
- the provenance hash is a hash of returned chunk content;
- the configured source actually enforced tenant/class/subject filters;
- the returned material is academically relevant.

`source_version` and `provenance_hash` are opaque provenance values. REF-1 must not sort versions, recompute hashes, or use provenance canonicalization as hidden retrieval/approval semantics.

REF-1 v1 does not invent a separate chunk ID or nested provenance object.

## 8. Empty context and ordering

An exact materialization with `chunks == ()` is valid and resolves to an empty `ResolvedReferenceContext`.

Empty context is not malformed input, not source execution failure, not an academic judgment, and not by itself a workflow/review/publication decision.

REF-1 preserves source-returned chunk order. It must not sort, rank, deduplicate, merge, or select chunks, and it makes no claim that preserved order has academic meaning.

## 9. Snapshot/custody invariant

Caller authority, source-facing request, source-returned materialization/chunks, and resolved context are distinct custody surfaces.

After exact-type admission, current-state validation and binding/resource checks, REF-1 copies validated scalar/tuple values into an independent resolved snapshot. Later source-side mutation must not rewrite the already-resolved context.

Foreign materialization/chunk values are rejected before nested property or method dispatch.

## 10. Failure separation

REF-1 v1 must preserve at least these distinct categories:

- unsupported policy/use of REF-1 under `DIRECT`;
- configured source execution failure;
- malformed source result/domain-contract failure;
- source-result binding mismatch;
- resource-limit failure.

A separate `UNAVAILABLE` exception/state is **not** authorized by REF-1 v1 merely because reference material is absent. Successful absence is represented by a valid empty chunk tuple. A future integration contract may add an explicit unavailable state only if authoritative semantics require one.

No REF-1 failure or empty result may become a criterion judgment, score, correctness decision, review decision, or publication decision.

## 11. Resource safety

GREEN must enforce deterministic versioned bounds for at least:

- maximum number of chunks;
- maximum individual chunk-content characters;
- maximum provenance-field characters;
- maximum total materialized chunk-content characters.

Those limits are Gradified resource-safety policy, not academic semantics. REF-1 v1 freezes these resource-safety limits before GREEN implementation:

- maximum chunks: `32`;
- maximum individual chunk content: `8192` characters;
- maximum each provenance field (`source_id`, `source_version`, `provenance_hash`): `128` characters;
- maximum total materialized chunk content: `65536` characters.

These values are Gradified-owned resource-safety policy, not academic semantics, and GREEN must test each at the boundary and boundary + 1.

Cheap cardinality/field-size checks must precede expensive copying/materialization where practical.

## 12. Explicit exclusions

REF-1 v1 does not implement or authorize:

- concrete PostgreSQL/pgvector/vector-search/object-store/backend APIs;
- tenant authentication or tenant/class/subject authorization logic;
- reference approval lifecycle or approval authentication;
- reference version ordering/latest selection;
- a hash algorithm or content-hash verification rule;
- chunk identity, uniqueness, deduplication, ranking or search scoring;
- embeddings, search queries, index IDs or database IDs;
- automatic DIRECT fallback;
- `DIRECT_PLUS_REFERENCE`, `HYBRID_RETRIEVAL`, or `REFERENCE_ONLY` semantic evaluation;
- evaluator routing/selection;
- academic judgments, scoring, review or publication decisions;
- persistence-history/temporal immutability guarantees.

## 13. Causal RED authorization

The first causal RED may prove existing `ContextPolicy`/ACTIVE-question prerequisites are valid before failing only at the missing REF-1 Gradified-owned domain contract.

The second causal RED may prove existing grading-spec/context-policy prerequisites are valid before failing only at the missing REF-1 materialization/resolution module.

RED must not introduce production behavior merely to make the tests compile. GREEN remains separately gated after the causal baseline is established.
