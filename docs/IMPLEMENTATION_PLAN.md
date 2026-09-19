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

## Rubric Authoring Safety & Compilation — NEXT

### Objective

Represent generated/edited rubrics as validated deterministic scoring authority.

### Components

- rubric authoring models;
- structural validator/linter;
- deterministic compiler to reducer-facing contracts;
- version and approval states.

### Acceptance

- duplicate IDs rejected;
- unknown level/dependency references rejected;
- marks/scoring policy reconcile to question maximum;
- invalid caps/gates/deductions/rounding rejected;
- positive-credit dependency graph validated;
- teacher approval required before ACTIVE in Release 1;
- meaningful change produces a new immutable version;
- compiled output is consumable by the scoring kernel without ad-hoc transformation.

### Verification

Contract tests, linter/compiler tests, adversarial authority cases, and marks-reconciliation properties.

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
