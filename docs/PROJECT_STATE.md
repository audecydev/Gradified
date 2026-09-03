# Project State

Last meaningful update: 2026-09-02

## Current milestone

Implementation foundation and Scoring Safety Kernel preparation.

## Verified completed

- Official SRS is available.
- Version 2 SRS-aligned grading architecture is approved as the implementation baseline.
- Release 1 uses a verification-first grading flow.
- Release 1 generated rubrics require teacher approval before becoming ACTIVE.
- The grading model/evaluator does not own authoritative numerical marks.
- The deterministic reducer owns marks and score-rule enforcement.
- Candidate grades are separate from officially published grades.
- OCR is treated as evidence, not unquestioned truth.
- OCR and backend integration are isolated through adapters.
- Routing is capability-based rather than subject-name hardcoding.
- Reference retrieval is selective and hidden behind a RetrievalPort.
- Risk uses observable signals; raw model self-confidence is not release authority.
- Pre-evaluation safety gates and post-score risk/impact are separate.
- Active grading specifications and rubrics are immutable versions.
- Regrading creates a new run/result rather than overwriting history.
- Modular-monolith implementation is the Release 1 default.

## Not yet implemented

No production grading code or automated tests have been verified yet.

## Current blockers

### Integration blockers
- Official project Git repository access has not been received.
- Actual OCR JSON/schema and sample outputs have not been received.
- Backend API/data structures and integration conventions have not been received.
- Previous grading implementation has not been inspected.

### Quality-validation blockers
- Teacher-marked sample papers/answer instances have not been received.
- Teacher-approved marking schemes/reference answers for benchmark cases have not been received.
- Reference/textbook samples have not been received.
- Approved production model/provider credentials have not been received.

## Active assumptions

- Internal grading contracts are canonical in meaning but may need field-level reconciliation after real OCR/backend inspection.
- External schemas adapt to the grading domain through adapters. Internal contracts change only when real integration evidence exposes a missing domain concept.
- Missing OCR confidence means UNKNOWN/UNAVAILABLE, never “good”.
- Math parse failure is uncertainty, not evidence that a student is wrong.
- Production risk thresholds will not be invented before calibration data exists.
- Teacher-marked data is required to establish academic grading quality.
- The first core implementation can use synthetic fixtures and FakeProvider without paid model calls.
- No production provider, retrieval database, backend storage model, or final API route shape has been selected.

## Verification status

- Architecture review: complete.
- Production code tests: not started.
- OCR integration tests: blocked.
- Backend integration tests: blocked.
- Academic grading benchmark: blocked.
- Production provider benchmark: blocked.

## Next task

Implement Slice 1 — Scoring Safety Kernel.

### Acceptance criteria

- Core rubric and criterion-judgment types are executable.
- Unknown criterion IDs are rejected.
- Unknown performance levels are rejected.
- Duplicate criterion judgments are rejected.
- Required criterion omissions cannot silently become a valid score.
- Marks come only from the active rubric/policy.
- Caps, dependencies, gates, deductions, and rounding can be enforced deterministically.
- Question and paper scores cannot leave the scoring range permitted by the active policy.
- A free-form evaluator/model total cannot become authoritative.
- Tests cover full, partial, zero, configured negative marking, illegal totals, unknown levels, duplicate judgments, missing criteria, caps, dependencies, gates, deductions, rounding, and maximum-score protection.
