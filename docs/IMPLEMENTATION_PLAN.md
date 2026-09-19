# Release 1 Capability Roadmap

The sequence is dependency-aware. It may move faster or slower than calendar dates. Safety tests and contract validation are not removed to protect schedule.

## Foundation — COMPLETE

### Objective

Establish the implementation workspace, persistent project state, test layout, package conventions, and source-of-truth discipline.

### Completed

- project/source-of-truth structure established;
- local and qualified Windows verification environments established;
- no guessed OCR/backend implementation introduced.

---

## Deterministic Scoring Kernel — COMPLETE / FROZEN

### Objective

Make numerical grading deterministic and structurally safe before model and external-system integration.

### Implemented inputs

- compiled question rubric;
- immutable question scoring policy;
- validated semantic criterion judgments;
- upstream-resolved paper scoring authority;
- admitted deterministic question results.

### Implemented outputs

- immutable deterministic question score result;
- immutable deterministic paper score result;
- exact provenance for authority identity, scoring rules, scoring stages, profile, and included question results.

### Verified behavior

- unknown criteria and levels rejected;
- duplicate and missing judgments rejected;
- rubric levels are the only source of criterion numerical effects;
- dependencies, gates, caps, deductions, and rounding are deterministic;
- one exact numeric profile governs authoritative scoring values;
- question and paper score ranges fail closed rather than clamp;
- model/evaluator free-form numerical totals have no authority;
- paper total uses question final scores only;
- paper bounds are consumed rather than inferred;
- caller ordering does not change numerical results;
- immutable result/provenance contracts;
- qualified 519-test committed acceptance;
- targeted mutation and source-audit closure.

### Important boundary

This capability assumes admitted immutable authority/results. It does not authenticate upstream origin, choose optional questions, define unrestricted job cardinality, or establish academic evaluator quality.

---

## Rubric Authoring Safety & Compilation — COMPLETE / ACCEPTED / FREEZE BOUNDARY

### Objective

Represent generated/edited rubrics as validated deterministic scoring authority without allowing generated content to establish trusted question identity/maximum or bypass the Release 1 approval boundary.

### Implemented components

- rubric authoring models;
- trusted finalized-question scoring basis;
- structural/resource validator/linter;
- deterministic compiler to reducer semantics;
- deterministic fingerprints/provenance;
- immutable version and approval lifecycle;
- ACTIVE-only supported reducer-authority acquisition.

### Implemented safety behavior

- duplicate IDs rejected;
- unknown level/dependency references rejected;
- marks/scoring policy reconcile to the trusted question maximum;
- invalid caps/gates/deductions/rounding rejected;
- positive-credit dependency graph validated;
- authoring content cannot establish trusted `question_id`, `max_marks`, or scoring-semantics identity;
- no hidden/default production compilation limits;
- configured structural/resource limits fail closed;
- pathological reconciliation state spaces are rejected before enumeration;
- teacher approval required before ACTIVE in Release 1;
- meaningful change produces a new immutable version;
- approval is bound to exact question/content/compiled-authority/compiler-profile identity;
- unexpected technical `ValueError` from projection remains a technical failure rather than being disguised as a lint error;
- reducer-facing authority is obtained only through the supported ACTIVE lifecycle path.

### Current verification

Qualified Windows / CPython 3.11.9 evidence:

- Rubric Authoring target: **78/78 passed**;
- frozen scoring regression: **519/519 passed**;
- full suite: **597/597 passed**;
- selected mutation baseline: **52/52 passed**;
- selected adversarial mutations M01-M08: **8/8 genuine kills** after JUnit/log inspection;
- frozen `contracts` and `scoring` source unchanged.

### Acceptance closure

- fresh independent source/contract review: **PASS WITH NON-BLOCKING FOLLOW-UPS**; no confirmed source defect found;
- exact staging/source audit: **PASS**;
- staged source/test identity was tied to the reviewed and mutation-verified candidate;
- qualified 78/519/597 verification passed on the staged-identical working tree;
- frozen `contracts` and `scoring` source remained unchanged.

This boundary is accepted for the freeze commit. Later provider/generator work must consume it rather than silently redefining its authority semantics.

### Important boundary

This capability validates and compiles candidate rubric content. It does **not** generate academic rubric content, authenticate teachers, provide global persistence/concurrency guarantees, or establish academic rubric quality.

---

## Rubric Generation — NEXT

### Objective

Generate a candidate rubric from finalized school-authorized assessment inputs while preserving the distinction between probabilistic candidate interpretation and deterministic scoring authority.

### Required inputs

- finalized question identity/text;
- authoritative maximum marks;
- school-authored model answer or marking scheme;
- optional approved reference context when available.

Do not invent OCR/backend/provider persistence schemas to implement this capability.

### Initial implementation direction

- provider-neutral `RubricGenerator` contract;
- strict structured candidate output mapped into the existing authoring models;
- Fake/ReplayProvider path before paid/production provider use;
- explicit generator/provider/model provenance;
- deterministic linter/compiler immediately downstream;
- teacher review/edit and Release 1 approval before ACTIVE.

### Acceptance

- model output remains candidate content and never directly becomes scoring authority;
- generated criteria/levels/rules are structurally valid after deterministic validation;
- generated marks reconcile to the trusted finalized-question maximum;
- invalid/ambiguous/malformed provider output fails safely;
- alternative valid methods can be represented where assessment authority permits;
- meaningful generated/teacher-edited changes produce a new immutable version;
- no provider-generated free-form score becomes authoritative.

### Development verification

Use real finalized question/model-answer fixtures as development cases.

A single paper is useful for integration but is not enough to establish rubric-generation quality.

### Academic-quality verification

Build an initial teacher-reviewed development/benchmark corpus of roughly 30-50+ finalized questions across theory and mathematics.

Track:

- structural validity;
- marks reconciliation;
- criterion coverage;
- teacher acceptance/edit rate;
- ambiguity/missing criteria;
- alternative-method coverage.

Do not claim academic rubric-generation quality before representative teacher-reviewed evidence exists.

---

## Synthetic End-to-End Grading Path

### Objective

Prove the grading core works end to end without external APIs.

### Flow

Synthetic evidence -> FakeProvider/evaluator -> criterion judgments -> verification -> deterministic scoring -> risk -> candidate result.

### Acceptance

- complete synthetic result is produced;
- malformed/invalid fake output fails safely;
- evidence references are validated;
- real question-scoring output flows into paper aggregation;
- no paid provider is required.

---

## Deterministic Evaluators

### Objective

Resolve cases where deterministic software is sufficient without an LLM call.

### Initial scope

- MCQ/exact;
- basic numeric comparison;
- tolerance;
- units where rules are defined.

### Acceptance

No model call is required when deterministic evaluation fully resolves the criterion.

---

## Semantic Evaluation

### Objective

Return criterion-level semantic judgments for meaning-based answers.

### Dependencies

Compiled rubric contract, evidence contract, provider interface.

### External validation dependency

Teacher-marked examples are required before academic quality can be claimed.

### Acceptance

- structured criterion judgments;
- evidence references;
- no direct authoritative score;
- alternative valid wording supported;
- grammar/style not scored unless the rubric says so;
- contradictory/incomplete answers represented through rubric levels/reason codes.

---

## Mathematical / Derivation Evaluation

### Objective

Add deterministic numeric/symbolic/unit checks where OCR representation supports them, with semantic grading for explanation and derivation.

### Dependency

Real OCR mathematical output is important before finalizing parsers.

### Acceptance

- supported parseable subset is explicit;
- parse failure means uncertainty;
- correct method/wrong final answer can receive rubric-defined partial credit;
- alternative valid methods can be represented.

---

## Approved Reference Context

### Objective

Support approved reference material without forcing retrieval for every question.

### Initial implementation

- RetrievalPort;
- context policies;
- source/version/hash provenance.

### Integration dependency

Backend/reference-storage reality.

---

## OCR & Backend Integration

### Objective

Connect the grading core to actual OCR and backend systems through adapters.

### Dependencies

- real OCR JSON/schema;
- backend repository/API/data conventions;
- canonical object/reference access patterns;
- authentication/tenant context.

### Acceptance

One real school-style paper flows through the system without manual JSON repair.

---

## Reliability & Security

### Objective

Prove fail-closed behavior under operational failure and hostile conditions.

### Coverage

- idempotency;
- retries;
- provider failure;
- tenant mismatch;
- malformed output;
- audit failure;
- prompt-injection containment;
- review/regrade preservation;
- telemetry;
- structural/job cardinality limits;
- resource/backpressure controls.

---

## Release Validation & Calibration

### Objective

Measure academic quality, cost, risk, and review workload on the exact release candidate.

### Dependencies

- held-out teacher-marked data;
- approved production provider/runtime;
- real OCR outputs.

### Rule

Do not repeatedly tune on the held-out evaluation set.
