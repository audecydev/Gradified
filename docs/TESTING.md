# Testing Strategy

Passing ordinary unit tests does not prove that a grading system is academically accurate. Different test layers prove different things.

## 1. Unit tests

Prove local deterministic behavior.

Examples:
- cap application
- dependency rule
- deduction rule
- rounding
- numeric tolerance
- risk-rule mapping

## 2. Contract/schema tests

Prove data entering/leaving a component has valid structure and values.

Examples:
- unknown criterion ID rejected
- unknown performance level rejected
- malformed GradeResult rejected
- missing confidence represented explicitly

## 3. Property/invariant tests

Prove safety properties over many generated inputs.

Examples:
- awarded score never leaves the active policy's permitted range
- question total cannot exceed question maximum
- duplicate judgments cannot create duplicate marks
- evaluator/model-provided free-form total is never authoritative

These are especially important for the reducer.

## 4. Integration tests

Prove components work together.

Examples:
- OCRAdapter -> AnswerEvidenceBundle
- BackendAdapter -> grading job/result
- reference lookup -> approved tenant source
- retry -> only one authoritative result

Real integration tests wait for real external interfaces.

## 5. Regression tests

Every meaningful discovered defect becomes a permanent test before the fix is considered complete.

A regression test should reproduce the actual failure mechanism, not merely test nearby behavior.

## 6. Adversarial/failure tests

Try to make the engine fail unsafely.

Examples:
- malformed model output
- hallucinated criterion/evidence refs
- bad OCR
- wrong question mapping
- prompt injection
- provider timeout
- duplicate retry
- tenant mismatch
- audit failure

Expected result: safe stop/review/technical failure, never a fabricated academic result.

## 7. Academic grading benchmark

This is different from software tests.

Required data:
- question
- maximum marks
- teacher/model answer or marking scheme
- student answer
- teacher-awarded marks
- criterion-level labels where available
- original scan/OCR where possible

Track:
- MAE
- exact agreement
- +/-1 mark agreement
- criterion agreement
- material-error rate
- over/under-grading
- review coverage
- alternative-method performance
- OCR-corruption performance
- presentation invariance

Teacher-marked data is required before claiming academic grading quality.

## 8. Rubric-generation benchmark

Measure the rubric generator separately from the grader.

Track:
- structural validity
- marks reconciliation
- criterion coverage
- teacher acceptance/edit rate
- ambiguity/missing criteria
- alternative-method coverage

A bad rubric can cause bad grading even when the evaluator follows it perfectly.

## 9. Cost/performance tests

Track:
- provider/model
- calls
- input/output tokens
- retries
- estimated cost per question/paper
- p50/p95 latency
- teacher review minutes

Quality gates come before cost optimization.

## Current status

No implementation tests have been run yet. This document defines the planned proof categories only.
