# Provider accounting

DIRECT evaluation may contact a paid remote model. The engine records the relationship between an original grading attempt and its physical provider activity so a timeout cannot be treated as an unbilled, safe-to-repeat request.

## Boundaries

- `providers/canonical_transport.py` fixes the outbound request form used by the approved sender.
- `providers/attempt_accounting.py` records one-shot physical observations and original attempt identity.
- `providers/accounting_recovery.py` supplies read-only reconciliation after uncertain outcomes.
- `providers/operational_policy.py` limits approved retry/backoff behavior.
- `integration/paper_provider_inventory.py` and `integration/paper_accounting.py` join paper-level provider activity with scored outcomes.

A provider callback must preserve its actual request identity, runtime version, transport result, usage measurement and receipt. Estimated token counts or a synthetic counter must not be represented as confirmed vendor charges. If the response is unknown, preserve that uncertainty.

Test request/receipt mismatch, duplicate callback, physical usage omitted from a paper, a provider call that completed after timeout and a second worker trying to replay the same attempt. Real vendor receipts and billing records are required for external acceptance.
