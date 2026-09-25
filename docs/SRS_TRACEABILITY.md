# Grading SRS Traceability

This file does not copy the SRS. The official SRS remains authoritative. It maps grading requirements to implementation responsibility, current status, and required proof.

| SRS area | Grading responsibility | Current implementation area | Status / required proof |
|---|---|---|---|
| §11 Reference material | Consume approved, tenant-scoped references; optional where policy allows | REF-1 reference-context boundary / RetrievalPort integration | REF-1 materialization/provenance boundary implemented and frozen; real tenant/version-scoped retrieval adapter and integration conformance still required |
| §12 Model answer & rubric generation | Generate rubric from school inputs; validate/version it; Release 1 teacher approval before ACTIVE | RubricGenerator + rubric authoring safety/compiler/lifecycle | Generator, lint/compiler and approval/ACTIVE lifecycle implemented; production provider/reference integration and representative rubric benchmark evidence still required |
| §14 Answer-sheet validation | Consume validated OCR evidence; preserve source/provenance/uncertainty | OCR adapter / evidence contracts | Blocked on real OCR interface evidence |
| §15.2 Contextual understanding | Interpret extracted text for the specific question | DIRECT semantic evaluator | DIRECT text slice implemented and frozen; broader context policies and teacher-marked academic validation remain open |
| §15.3 LLM-based evaluation | Compare response to question/rubric at criterion level | DIRECT semantic evaluator/provider boundary | Bounded provider-response admission and criterion judgments implemented for DIRECT text; production provider integration/telemetry/benchmarking remain open; model output never owns the authoritative numerical total |
| §15.4 Step-wise logic | Support rubric-defined intermediate credit and subject-appropriate logic | Rubric lifecycle + evaluator paths + deterministic question scoring | Rubric authority and deterministic scoring implemented; CHOICE, DIRECT text and bounded NUMERIC paths exist; broader derivation/composite evaluator breadth remains open |
| §15.5 Error classification | Represent conceptual/calculation/formula/incomplete-solution classifications | Evaluator/result contracts | Structured reason/error fields exist in current evaluator contracts; complete Release 1 classification coverage remains to be validated across broader evaluator types |
| §15.6 Marks allocation | Allocate marks from rubric step weighting; total per answer; aggregate per answer sheet | Deterministic scoring kernel | **Implemented and technically accepted** |
| §15.7 Evaluation pipeline | OCR -> interpretation -> evaluation -> scoring -> result | Execution/evaluator/verification/scoring composition | Internal CHOICE, DIRECT text and bounded NUMERIC vertical paths are implemented; real OCR/backend/provider integration and complete production E2E remain open |
| §16 Confidence scoring | Preserve OCR confidence; derive measurable readiness/risk signals | S2b-1 risk observations / future recommendation policy | Narrow deterministic risk-observation profile implemented; calibrated recommendation/release policy and broader signal coverage remain open |
| §17 Human review | Return review reasons/evidence; support override/regrade input | Risk/backend boundary | Core reason/evidence structures exist; executable recommendation policy and backend review workflow remain integration work |
| §18 Grievance | Support a new linked regrade/review run | Backend/regrade boundary | Required architecture is defined; durable backend workflow and linked regrade persistence remain open |
| §19 Result publishing | Return candidate result only; backend controls publish | Candidate result/backend boundary | Core preserves candidate-vs-published authority separation; backend publication workflow remains open |
| §20 Analytics | Emit criterion/error/risk/cost/provenance data | Result/telemetry | Later capability; paper score aggregation is not analytics aggregation |
| §21 Lifecycle | Rubric prepared before exam; explicit grading states | Rubric lifecycle + service/job contracts | Rubric draft/compile/approval/ACTIVE lifecycle implemented; production async job-state integration remains open |
| §22 History/reuse | Immutable versions and new regrade runs | Versioned core contracts/backend boundary | Core authorities/capabilities are version-bound and immutable by contract; durable historical persistence and linked regrade workflow remain backend integration work |
| §25 Security/privacy/reliability | Tenant safety, fail-closed behavior, auditability, operational limits | Contracts, REF-1, verification, adapters/risk/telemetry/job boundaries | Internal fail-closed/resource-bound behavior is implemented for completed slices; real tenant/auth isolation, telemetry and reliability integration remain open |
| §26 Responsibility boundary | School authors examination content; grading owns evaluation logic; backend owns technical workflow/publish | Architecture boundaries | Preserved across ACTIVE authority, evaluator, scoring, reference and backend integration boundaries |
| §27 Product definition | Safe automated grading with selective review and controlled improvement | Whole system | Requires full integration and held-out academic validation |

## Implemented deterministic marks path

The implemented marks path is:

`approved scoring authority + semantic criterion judgments -> deterministic question score -> upstream-resolved paper composition + admitted question results -> deterministic paper score`

Numerical authority rules:

- the model/evaluator cannot directly set the authoritative numerical total;
- rubric performance levels define criterion mark effects;
- scoring policy defines dependencies, gates, caps, deductions, rounding, and question range;
- exactly one question-boundary rounding stage exists;
- paper aggregation has no second rounding stage;
- paper total consumes question `final_score` only;
- paper bounds are supplied by upstream scoring authority and are not inferred from question bounds;
- out-of-range results fail rather than clamp.

## Important interpretation

The SRS uses confidence-score language. Release 1 must not use an uncalibrated raw model self-confidence value as scoring or publication authority. OCR confidence may be preserved when its meaning is defined; other readiness/risk signals require measurable evidence and calibration.

## Deferred boundaries retained explicitly

The completed scoring kernel does not define:

- how optional questions/alternate sections are resolved into the exact countable paper composition;
- the persisted schema that projects paper-level minimum/maximum authority;
- authority authentication;
- tenant/backend identity enforcement;
- OCR schema or correction;
- semantic evaluator correctness;
- production structural/job cardinality limits;
- persistence/publication workflow;
- academic-quality claims.

These remain requirements for their named future capabilities rather than hidden behavior inside deterministic scoring.
