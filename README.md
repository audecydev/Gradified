# Gradified Grading Core

The Gradified grading core converts school-authorized scoring rules and admitted semantic judgments into deterministic, auditable candidate scores.

The implemented numerical kernel is intentionally isolated from OCR vendors, backend persistence, model-provider SDKs, authentication systems, and publication workflow. Those systems integrate through explicit boundaries rather than becoming scoring authority.

## Current implemented capability

The deterministic scoring kernel is complete and technically accepted.

It includes:

- **Numeric Profile v1** for exact finite decimal scoring values;
- deterministic question scoring from an immutable compiled rubric, scoring policy, and one semantic judgment per atomic criterion;
- positive-credit dependencies, gates, caps, deductions, and exactly one question-boundary rounding stage;
- deterministic paper aggregation from an upstream-resolved exact question composition;
- typed failure rather than clamping, fabricated zero scores, or partial successful results;
- immutable result/provenance contracts;
- exact runtime-type boundaries at safety-critical contract edges;
- a qualified reproducible verification environment.

The numerical kernel does **not** decide which questions belong to a paper, authenticate upstream authority, interpret OCR, judge answer meaning, publish results, or define unlimited production job sizes.

## Verified implementation identity

Current deterministic paper-aggregation commit:

`e6c7cb71b33120b6cdeeb2b4176a3f33a8580869`

Current tree:

`0fc3601fbf0bfacaacfc378aa0ce9313ffa45313`

Qualified final verification:

- Windows x64;
- CPython 3.11.9;
- version-pinned eight-package verification dependency closure;
- 519/519 tests passed;
- 0 failures;
- 0 errors;
- 0 skips;
- exact testcase identity reconciliation;
- clean repository before and after verification.

See `docs/DETERMINISTIC_SCORING_KERNEL_AUDIT.md` for the evidence summary and non-claims.

## Authority model

Numerical scoring authority flows from approved scoring data, never from a model-produced total.

At question scope:

`CompiledQuestionRubric + QuestionScoringPolicy + CriterionJudgment tuple -> deterministic question score`

At paper scope:

`ResolvedPaperScoringAuthority + QuestionScoreResult tuple -> deterministic paper score`

The semantic evaluator may select an approved rubric level. It cannot directly set the authoritative numerical total.

## Primary sources

1. Gradified Software Requirements Specification v1.0, 31 August 2026.
2. Verification-First Adaptive Grading Engine Version 2 — SRS-Aligned Engineering Source of Truth.
3. Authoritative Scoring Numeric Profile v1.

## Engineering documentation

- `docs/PROJECT_STATE.md` — current verified implementation state and next work.
- `docs/ARCHITECTURE.md` — cross-system grading boundaries and invariants.
- `docs/IMPLEMENTATION_PLAN.md` — dependency-aware Release 1 capability roadmap.
- `docs/SRS_TRACEABILITY.md` — requirements mapped to implementation and verification.
- `docs/TESTING.md` — verification strategy and executed evidence.
- `docs/SCORING_KERNEL_BLACK_BOX.md` — future-engineer interface, authority, failure, and non-claim reference.
- `docs/NUMERIC_PROFILE_V1.md` — concise normative numeric-profile reference.
- `docs/DETERMINISTIC_SCORING_KERNEL_AUDIT.md` — final kernel evidence and closure audit.

## Next implementation capability

The next dependency-aware capability is **Rubric Authoring Safety & Compilation**:

- immutable rubric authoring models;
- deterministic structural validation/linting;
- marks reconciliation to question maximum;
- dependency/cap/gate/deduction validation;
- version and activation state;
- teacher approval before ACTIVE for Release 1.

No OCR schema, backend table, provider API, authentication rule, or production resource limit should be invented in advance of real integration evidence.
