# Current Release 1 Integration Scope

This document gives a short, public, plain-language snapshot of what the repository can and cannot currently claim.

## Ready for integration testing

The following internal slices are implemented, verified, and frozen unless a verified defect or authority contradiction requires reopening them:

- deterministic scoring kernel;
- rubric authoring safety and compilation;
- rubric-generation safety boundaries/replay support;
- evidence verification;
- synthetic execution composition through deterministic scoring;
- risk-observation extraction for the supported profile;
- single-select CHOICE evaluator;
- ACTIVE question-authority boundary;
- DIRECT text semantic evaluator slice;
- bounded unitless NUMERIC N1–N4 path;
- exact versioned evaluator-capability record resolution;
- reference-context materialization/provenance boundary.

## Qualified verification baseline

The verified internal candidate used for this publication passed:

- complete qualified regression: **1499 / 1499 passed**;
- Windows x64 / CPython 3.11.9;
- pytest 9.1.1;
- Hypothesis 6.167.1;
- `pip check` clean;
- clean working tree at verification.


## Not yet production-complete

The repository does not yet establish complete production behavior for:

- automatic/exact evaluator selection from question classification;
- evaluator-execution provenance across the full workflow;
- real OCR adapter behavior;
- backend persistence/idempotency/publication;
- real reference retrieval and tenant isolation;
- production semantic-provider benchmarking and telemetry;
- complete recommendation/review/regrade policy;
- UNIT parsing/evaluation;
- broader math-expression/derivation/composite evaluation;
- complete risk/release policy;
- real-school-paper end-to-end validation;
- held-out calibration and production reliability evidence.

## Correct claim

A correct statement is:

> The repository contains a verified grading-core foundation and completed evaluator/integration slices that are ready for integration testing against real OCR, backend, reference, and provider systems.

An incorrect statement is:

> The complete Gradified Release 1 production grading platform is finished.
