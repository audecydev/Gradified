# Release 1 Implementation Plan

The sequence is dependency-aware. It may move faster or slower than calendar dates. Safety tests and contract validation are not removed to protect schedule.

## Slice 0 — Foundation

### Objective
Establish a small implementation workspace, current project state, test layout, and package conventions.

### Dependencies
None.

### Acceptance
- Source-of-truth files exist.
- Local test environment can be established.
- No guessed OCR/backend implementation has been introduced.

---

## Slice 1 — Scoring Safety Kernel

### Objective
Make grading marks deterministic and structurally safe before any model integration.

### Inputs
- Compiled rubric
- Validated criterion judgments

### Output
- Deterministic question/paper score result

### Acceptance
- Unknown criteria/levels rejected.
- Duplicate judgments rejected.
- Missing required criteria cannot silently pass.
- Rubric levels are the only source of mark effects.
- Caps/dependencies/gates/deductions/rounding are deterministic.
- Allowed scoring range is enforced.
- Model-supplied numerical totals have no authority.
- Property/boundary tests cover impossible totals.

### Verification
Unit tests + property/invariant tests.

---

## Slice 2 — Rubric Safety

### Objective
Represent generated rubrics as validated deterministic scoring data.

### Components
- rubric models
- structural validator/linter
- compiler
- version/approval states

### Acceptance
- duplicate IDs rejected
- unknown levels/dependencies rejected
- marks policy reconciles to question maximum
- invalid caps/gates/deductions rejected
- teacher approval required before ACTIVE in Release 1

### Verification
Contract + linter/compiler tests.

---

## Slice 3 — Synthetic Vertical Grading Path

### Objective
Prove the grading core works end to end without external APIs.

### Flow
Synthetic evidence -> FakeProvider/evaluator -> CriterionJudgment -> verification -> reducer -> risk -> GradeResult

### Acceptance
- complete synthetic result is produced
- malformed/invalid fake output fails safely
- evidence references are validated
- no paid provider is required

---

## Slice 4 — Deterministic Evaluators

### Objective
Grade cases where deterministic software is sufficient.

### Initial scope
- MCQ/exact
- basic numeric comparison
- tolerance
- units where rules are defined

### Acceptance
No LLM call is required when deterministic evaluation fully resolves the criterion.

---

## Slice 5 — Subjective Evaluation

### Objective
Return criterion-level judgments for meaning-based answers.

### Dependencies
Rubric contract, evidence contract, provider interface.

### External validation dependency
Teacher-marked examples are required before academic quality can be claimed.

### Acceptance
- structured criterion judgments
- evidence refs
- no direct authoritative score
- alternative wording is allowed
- grammar/style is not scored unless rubric says so
- contradictory/incomplete answers represented through rubric/reason codes

---

## Slice 6 — Mathematics / Derivation Capability

### Objective
Add deterministic numeric/symbolic/unit checks where OCR representation supports them, with semantic grading for explanation/derivation.

### Dependency
Real OCR math output is important before finalizing parsers.

### Acceptance
- supported parseable subset is explicit
- parse failure is uncertainty
- correct method/wrong final answer can receive rubric-defined partial credit
- alternative valid methods can be represented

---

## Slice 7 — References

### Objective
Support SRS-required reference material without forcing retrieval for every question.

### Initial implementation
- RetrievalPort
- context policies
- source/version/hash provenance

### Final integration dependency
Backend/reference-storage reality.

---

## Slice 8 — Real Integration

### Objective
Connect the grading core to actual OCR/backend systems.

### Dependencies
- real OCR JSON
- backend repository/API/data conventions
- object/reference access patterns

### Acceptance
One real school-style paper flows through the system without manual JSON repair.

---

## Slice 9 — Reliability and Security

### Objective
Prove fail-closed behavior.

### Coverage
- idempotency
- retries
- provider failure
- tenant mismatch
- malformed output
- audit failure
- prompt-injection containment
- review/regrade preservation
- telemetry

---

## Slice 10 — Validation

### Objective
Measure academic quality, cost, risk, and review workload on the exact release candidate.

### Dependencies
- held-out teacher-marked data
- approved production provider credentials
- real OCR outputs

### Rule
Do not tune repeatedly on the held-out test set.
