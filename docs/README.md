# Documentation Guide

This page explains **what every document is for** and the order in which a new engineer should read them.

If you are joining the project for the first time, you should not need to guess which file matters.

## Read these first

| Document | Who should read it | Why it exists |
|---|---|---|
| [`../README.md`](../README.md) | Everyone | One-page entry point: what this repository is, what is implemented, what is still open, and how to run tests. |
| [`INTEGRATION_START_HERE.md`](INTEGRATION_START_HERE.md) | OCR, backend, provider, reference, QA engineers | Plain-language integration flow and the safest order to connect systems. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Everyone integrating or changing the system | Explains the authority/data flow, the **currently implemented core**, and the **target Release 1 architecture**. |
| [`REPOSITORY_STRUCTURE.md`](REPOSITORY_STRUCTURE.md) | Developers | Tells you where code, contracts, tests, and documents live. |
| [`INTEGRATION_REQUIREMENTS.md`](INTEGRATION_REQUIREMENTS.md) | Integration leads and QA | Checklist of what each external system must supply and what success/failure should look like. |
| [`INTEGRATION_TEST_PLAN.md`](INTEGRATION_TEST_PLAN.md) | QA and integration engineers | Step-by-step integration tests and expected outcomes. |
| [`RELEASE_SCOPE.md`](RELEASE_SCOPE.md) | Managers and engineers | Simple statement of what is finished versus what is not yet production-complete. |

## Integration-specific guides

| Document | Audience | Purpose |
|---|---|---|
| [`OCR_INTEGRATION_GUIDE.md`](OCR_INTEGRATION_GUIDE.md) | OCR engineer | Map real OCR output into `AnswerEvidenceBundle` without changing grading semantics. |
| [`BACKEND_INTEGRATION_GUIDE.md`](BACKEND_INTEGRATION_GUIDE.md) | Backend/workflow engineer | Supply trusted authority, run/submission identity, persistence, retries, review and publication workflow. |
| [`REFERENCE_INTEGRATION_GUIDE.md`](REFERENCE_INTEGRATION_GUIDE.md) | Reference/retrieval engineer | Connect tenant/version-scoped reference access to the frozen REF-1 boundary. |
| [`SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md`](SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md) | Model/provider engineer | Connect a production semantic provider only through the bounded DIRECT provider interface. |

## Frozen contracts and scoring references

These are more detailed. Read them when you are changing or debugging the corresponding subsystem.

| Document | Purpose |
|---|---|
| [`SCORING_KERNEL_BLACK_BOX.md`](SCORING_KERNEL_BLACK_BOX.md) | The public black-box contract for deterministic marks. External systems must not bypass it. |
| [`NUMERIC_PROFILE_V1.md`](NUMERIC_PROFILE_V1.md) | Exact decimal representation and bounded arithmetic used by scoring. |
| [`CHOICE_EVALUATION_CONTRACT_V1.md`](CHOICE_EVALUATION_CONTRACT_V1.md) | Frozen single-select CHOICE evaluator contract. |
| [`IF1_EVALUATOR_CAPABILITY_REGISTRY_CONTRACT_V1.md`](IF1_EVALUATOR_CAPABILITY_REGISTRY_CONTRACT_V1.md) | Exact versioned capability-record resolution; **not** automatic routing. |
| [`REF1_REFERENCE_CONTEXT_CONTRACT_V1.md`](REF1_REFERENCE_CONTEXT_CONTRACT_V1.md) | Reference-context materialization/provenance boundary and resource limits. |
| [`DETERMINISTIC_SCORING_KERNEL_AUDIT.md`](DETERMINISTIC_SCORING_KERNEL_AUDIT.md) | Closure/audit summary for the deterministic scoring foundation. |

## Engineering state and evidence

| Document | Purpose |
|---|---|
| [`PROJECT_STATE.md`](PROJECT_STATE.md) | Detailed operational record of what has been frozen and what remains open. |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Dependency-aware roadmap. It is not permission to skip authority gates. |
| [`TESTING.md`](TESTING.md) | Detailed verification history, test counts, and explicit non-claims. |
| [`SRS_TRACEABILITY.md`](SRS_TRACEABILITY.md) | Shows how grading requirements map to the implemented core and deferred boundaries. |

## Architecture diagram

The canonical Release 1 architecture is rendered directly from Mermaid source inside [`ARCHITECTURE.md`](ARCHITECTURE.md). This keeps every arrow reviewable in Git history and avoids preserving an ambiguous raster diagram.

`ARCHITECTURE.md` clearly separates the **target Release 1 architecture** from the **currently implemented core**. [`RELEASE_SCOPE.md`](RELEASE_SCOPE.md) gives the corresponding implementation-status summary.

## Why many filenames use CAPITAL LETTERS

This repository inherited an engineering convention where durable control documents and frozen contracts use uppercase names, for example `PROJECT_STATE.md`, `TESTING.md`, and `SCORING_KERNEL_BLACK_BOX.md`.

There is no technical requirement for uppercase filenames. Established names are retained because other documents and engineering evidence already reference them. Renaming them only for appearance would create broken links and unnecessary churn.

`README.md` is also conventionally uppercase on GitHub because GitHub renders it automatically.

## Documentation format

Repository engineering documentation is kept in **Markdown (`.md`)** because it renders directly on GitHub, produces readable diffs, and is easy to search and link.

## Test support helpers

Shared pytest helper modules live under [`../tests/support/`](../tests/support/) rather than loose at the `tests/` root. They are fixtures/builders used by multiple test categories and are not production modules.
