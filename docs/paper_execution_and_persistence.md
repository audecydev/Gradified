# Paper execution and persistence

The strict paper entry, `ProductionPaperOperations`, is the integration root for supported FIRST, REGRADE and RETRY operations. It is not the school database, not a REST endpoint and not a publication service.

## Installation requirements

The `ProductionPaperOperations` constructor validates exact component types, enabled operation kinds, matching identifier/question limits and shared attempt/CAS/executor ownership. FIRST or REGRADE requires `ProductionPaperLifecycle`; RETRY requires `ProductionGradedPaperRetry`. Both paths require a compatible `ProductionPaperPromotion` and `ProductionPaperAdmissionComposer`.

The class also checks for strict original-bound claim and purpose-aware scored-CAS configuration. A DIRECT paper needs an installed `ProductionDirectProviderRoute` and the required physical usage/completeness observations. An object with an identically named method is not automatically an authorized source.

## Per-operation flow

1. Re-read current paper readiness from backend-authorized sources.
2. Verify question identity, routing eligibility and supported family.
3. Establish original/purpose-scoped attempt claim and effect authorization.
4. Invoke the approved evaluator and any physical provider call.
5. Verify judgments, calculate exact scores and aggregate the full expected paper.
6. Commit the candidate and audit lineage through the qualified conditional scored-result owner.
7. Return a nonpublishing observation. Review and publication are separate decisions.

The root uses a non-blocking lock against simultaneous calls **to one Python instance**. This is not database transaction isolation: the receiving backend must prove uniqueness across workers and restarts.

## Source owners

- `integration/paper_readiness_admission.py` — current official paper scope.
- `integration/paper_lifecycle.py`, `integration/paper_retry_grading.py` — operation-specific sequencing.
- `integration/whole_paper_attempt_custody.py` — original attempt and provider observation custody.
- `integration/whole_paper_cas.py` — scored-result commit and read-only reconciliation.
- `integration/scored_paper_promotion.py` — governed output promotion and accounting checks.

Primary regression: `tests/integration/test_production_paper_operations.py`. See [Attempt and recovery contracts](attempt_and_recovery_contracts.md) for uncertain effects.
