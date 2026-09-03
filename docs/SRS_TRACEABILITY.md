# Grading SRS Traceability

This file does not copy the SRS. The official SRS remains authoritative. This maps grading-related requirements to implementation areas and verification evidence.

| SRS area | Grading responsibility | Planned component | Required proof |
|---|---|---|---|
| §11 Reference material | Consume approved, tenant-scoped references; optional for grading when policy allows | RetrievalPort / context builder | tenant/version/provenance tests |
| §12 Model answer & rubric generation | Generate rubric from school inputs; validate/version it; Release 1 teacher approval before ACTIVE | rubric generator/linter/compiler | structural tests + rubric benchmark |
| §14 Answer-sheet validation | Consume validated OCR evidence; preserve source/provenance/uncertainty | OCRAdapter / AnswerEvidenceBundle | OCR contract tests |
| §15 AI evaluation engine | Criterion-level evaluation, alternative methods, error classification, deterministic marks | evaluators + verification + reducer | evaluator/reducer tests + teacher benchmark |
| §16 Confidence scoring | Preserve OCR confidence; derive rubric/evaluation readiness from observable signals | risk/readiness | risk tests + calibration later |
| §17 Human review | Return review reasons/evidence; support override/regrade input | GradeResult/risk/backend adapter | review/regrade integration tests |
| §18 Grievance | Support new regrade/review run linked to prior result | service/result contracts | version/history tests |
| §19 Result publishing | Return candidate result only; backend controls publish | GradeResult/backend boundary | integration policy test |
| §20 Analytics | Emit structured criterion/error/risk/cost/provenance fields | GradeResult/telemetry | schema tests |
| §21 Lifecycle | Rubric prepared before exam; grading job has explicit states | rubric/service/job contract | lifecycle tests |
| §22 History/reuse | Immutable versions and new regrade runs | contracts/backend boundary | versioning tests |
| §25 Security/privacy/reliability | tenant safety, fail-closed, auditability, cost/latency visibility | adapters/risk/telemetry | security/failure tests |
| §26 Responsibility boundary | school authors exam content; grading owns evaluation logic; backend owns technical workflow/publish | architecture boundaries | architecture/integration review |
| §27 Product definition | safe automated grading with selective review and controlled improvement | whole system | held-out validation |

## Important interpretation

The SRS uses “confidence score” language. Release 1 will not use raw LLM self-confidence as release authority. OCR confidence is preserved when supplied with defined meaning; rubric/evaluation readiness is backed by measurable signals until calibration supports a numeric probability.
