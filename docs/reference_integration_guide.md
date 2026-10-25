# Reference integration

Reference retrieval supplies approved textbook excerpts and model-answer context. It must never create or modify a school's grading authority merely because a search result mentions an answer.

The host must authenticate the school and source revision, authorize access to the requested text, retain stable chunk IDs and versioned provenance, limit returned content, and reject cross-tenant or retired references. Use the `ReferenceContextSource` contract in `src/grading/contracts/reference_context.py` and `resolve_reference_context` in `src/grading/reference_context.py`.

A valid integration test requests an approved excerpt, verifies its exact origin/version at the evaluator, then tries a revoked source, another school's document, an unknown chunk and a response that exceeds resource limits. The latter cases must not become candidate grading context.

The engine resolves and validates context; it does not operate the production search index, document-ingestion pipeline or textbook-rights service. See [Rubrics and academic authority](rubrics_and_authority.md).
