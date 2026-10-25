# Evidence and question binding

OCR returns observations about a scan; the backend supplies authoritative paper and question identity. Both are required before a supported evaluator may see a student's answer.

## Admission

`parse_normalized_evidence_payload(...)` in `integration/evidence_ingress.py` validates strict UTF-8 JSON, resource limits, supported wire shape, unique question/block relationships and source metadata. The resulting `AdmittedNormalizedEvidence` carries the original raw payload hash and a snapshot of the trusted resource policy.

The parser does not determine whether a submission is the correct student's paper or whether the question rubric is still ACTIVE. Those checks happen when normalized evidence is bound to an independently resolved paper/question through the preparation and binding components.

## Binding and verification

- `integration/question_evaluation_preparation.py` prepares question-level source and evidence context.
- `integration/evaluation_binding.py` joins the admitted answer with the exact question and execution context.
- `integration/paper_readiness_admission.py` resolves current official paper scope before an effectful paper operation.
- `verification/evidence.py` rejects criterion judgments that do not match the admitted evidence context.

A payload with a valid `Q1` text block must not be graded against `Q2` or a different rubric version. Missing or ambiguous mapping should become a review/mapping problem, not a fabricated student error.

A schema-valid example and runnable admission check appear in the [OCR guide](ocr_integration_guide.md). Source tests include `tests/contracts/test_evidence_admission_normalized_evidence_ingress_regression.py` and `tests/integration/test_question_evaluation_binding_regression.py`.
