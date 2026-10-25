# Semantic provider integration

DIRECT text evaluation uses an external model to interpret supported answers. The model returns **structured criterion evidence**; it is not allowed to choose an unchecked numeric paper score.

## Host responsibilities

1. Resolve an approved evaluator capability and runtime for the exact school, question, rubric and operation.
2. Use the approved reference and model-answer source, preserving versions and origin. An answer's own content cannot become an approved rubric.
3. Send bounded, canonical requests through the installed transport. The production DIRECT operation checks for an installed `ProductionDirectProviderRoute` before claim/contact.
4. Validate provider output against expected criterion IDs, evidence blocks, response shape, model identity and resource limits. Reject fabricated or foreign identifiers.
5. Preserve the physical attempt record, actual usage observation and signed/qualified receipt from the provider boundary. Distinguish an observed failure from a call whose effect is unknown.
6. Reconcile an uncertain call using its fixed original identity; never silently bill or dispatch again on a new identity.

## Source entries

- `grading.semantic_evaluator` — model-answer and criterion-response boundary.
- `grading.integration.direct_provider_route` — installed DIRECT call route.
- `grading.providers.canonical_transport` — canonical byte send and structured response.
- `grading.providers.attempt_accounting` — original-bound provider activity and accounting.
- `grading.providers.accounting_recovery` — read-only effect recovery.

The existing replay provider in tests is not a production API credential or a proof of model grading accuracy. Compare real returned judgments with held-out teacher-labeled answers before academic sign-off. See [Evaluation and provider contracts](evaluation_and_provider_contracts.md) and [Provider accounting](provider_accounting.md).
