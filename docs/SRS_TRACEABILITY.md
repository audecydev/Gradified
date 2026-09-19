# Grading SRS Traceability

This file does not copy the SRS. The official SRS remains authoritative. It maps grading requirements to implementation responsibility, current status, and required proof.

| SRS area | Grading responsibility | Current implementation area | Status / required proof |
|---|---|---|---|
| §11 Reference material | Consume approved, tenant-scoped references; optional where policy allows | RetrievalPort / context builder | Planned; tenant/version/provenance tests required |
| §12 Model answer & rubric generation | Generate rubric from school inputs; validate/version it; Release 1 teacher approval before ACTIVE | Rubric authoring safety & compilation | Next capability; structural/compiler tests and rubric benchmark required |
| §14 Answer-sheet validation | Consume validated OCR evidence; preserve source/provenance/uncertainty | OCR adapter / evidence contracts | Blocked on real OCR interface evidence |
| §15.2 Contextual understanding | Interpret extracted text for the specific question | Semantic evaluator | Planned; teacher-marked validation required |
| §15.3 LLM-based evaluation | Compare response to question/rubric at criterion level | Semantic evaluator/provider boundary | Planned; model must return semantic judgments, not authoritative numerical total |
| §15.4 Step-wise logic | Support rubric-defined intermediate credit and subject-appropriate logic | Rubric + evaluator + deterministic question scoring | Numerical execution implemented; evaluator/rubric authoring still pending |
| §15.5 Error classification | Represent conceptual/calculation/formula/incomplete-solution classifications | Evaluator/result contracts | Planned |
| §15.6 Marks allocation | Allocate marks from rubric step weighting; total per answer; aggregate per answer sheet | Deterministic scoring kernel | **Implemented and technically accepted** |
| §15.7 Evaluation pipeline | OCR -> interpretation -> evaluation -> scoring -> result | Grading service composition | Scoring segment implemented; full vertical path pending |
| §16 Confidence scoring | Preserve OCR confidence; derive measurable readiness/risk signals | Risk/readiness | Planned/calibration dependent |
| §17 Human review | Return review reasons/evidence; support override/regrade input | Candidate result/risk/backend boundary | Planned integration |
| §18 Grievance | Support a new linked regrade/review run | Service/result/backend contracts | Planned |
| §19 Result publishing | Return candidate result only; backend controls publish | Candidate result/backend boundary | Planned integration |
| §20 Analytics | Emit criterion/error/risk/cost/provenance data | Result/telemetry | Later capability; paper score aggregation is not analytics aggregation |
| §21 Lifecycle | Rubric prepared before exam; explicit grading states | Rubric/service/job contracts | Rubric lifecycle next; workflow integration later |
| §22 History/reuse | Immutable versions and new regrade runs | Contracts/backend boundary | Numerical identities versioned; workflow history later |
| §25 Security/privacy/reliability | Tenant safety, fail-closed behavior, auditability, operational limits | Adapters/risk/telemetry/job boundaries | Numerical fail-closed behavior implemented; tenant/operational controls later |
| §26 Responsibility boundary | School authors examination content; grading owns evaluation logic; backend owns technical workflow/publish | Architecture boundaries | Preserved by current scoring kernel |
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
