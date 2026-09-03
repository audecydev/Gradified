# Gradified Grading Core

This workspace is the temporary implementation foundation for the Gradified grading subsystem.

It exists so the grading-core contracts, deterministic scoring rules, tests, and other implementation work can begin without guessing the current OCR or backend interfaces.

## Current rule

Build only work that is independent of unknown external systems.

Do not invent:
- OCR field names
- backend database tables
- authentication behavior
- queue behavior
- production API endpoints
- model-provider credentials
- calibrated risk thresholds

When the official repository and real integration artifacts arrive, inspect them first and reconcile this work into the existing project structure.

## Primary sources

1. Gradified Software Requirements Specification v1.0, 31 August 2026.
2. Verification-First Adaptive Grading Engine Version 2 — SRS-Aligned Engineering Source of Truth.

## Working documents

- `docs/PROJECT_STATE.md` — where implementation stands now.
- `docs/ARCHITECTURE.md` — concise grading-core boundaries and invariants.
- `docs/IMPLEMENTATION_PLAN.md` — dependency-aware Release 1 slices.
- `docs/SRS_TRACEABILITY.md` — grading-related SRS requirements and planned verification.
- `docs/TESTING.md` — what each kind of test proves.

## First implementation milestone

Scoring Safety Kernel:

`CompiledRubric + CriterionJudgment[] -> validation -> deterministic reducer -> score/result fragment`

No model API, OCR integration, backend integration, or database is required for this milestone.
