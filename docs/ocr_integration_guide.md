# OCR integration

The OCR team converts each real scanned answer sheet into the engine's normalized evidence JSON. The schema describes **observations**, not school approval or grading instructions.

## Supported input

The exact schema is `schemas/gradified.normalized_answer_evidence.v1.schema.json`. A complete example is supplied at [examples/ocr_evidence_sample.json](examples/ocr_evidence_sample.json), with a runnable parser check at [examples/ocr_admission_demo.py](examples/ocr_admission_demo.py).

```sh
PYTHONPATH=src:. python docs/examples/ocr_admission_demo.py
```

On Windows CMD:

```bat
set "PYTHONPATH=src;."
python docs\examples\ocr_admission_demo.py
```

The example uses invented *sample IDs* only to demonstrate parsing. They do not represent a real school, an authorized paper, a live OCR confidence calibration or grading readiness.

## Mapping rules

1. Obtain submission, paper, question and page associations from trusted capture and backend records. Do not guess a student's identity from handwriting content.
2. Preserve every block's `block_id`, `type`, `state`, `reading_order`, `page` and real location status. `CROSSED_OUT` and `UNCERTAIN` must not silently become `ACTIVE`.
3. Set `confidence_status` to `UNAVAILABLE` with `confidence: null` when the OCR process has no confidence value. Never manufacture a score.
4. Use `FIGURE` for image regions and `MATH` for observed mathematical work; neither implies those answers are eligible for automatic grading.
5. Retain actual source artifact reference and OCR run provenance. The parser records a hash of the admitted raw bytes.
6. Call `parse_normalized_evidence_payload` with **backend-owned** `NormalizedEvidenceAdmissionPolicy`. Limit raw upload size, decompression and concurrent processing upstream as well.
7. Bind admitted evidence to the real approved question through the preparation/binding path before any supported evaluator is invoked.

`AdmittedNormalizedEvidence` is constructed only through the parser; do not instantiate it in adapters. A syntactically valid payload may still be rejected because it refers to the wrong submission, paper or approved question.

## Acceptance cases

Test a genuine OCR scan, wrong submission ID, duplicated block, large content, crossed-out work, missing confidence, unknown region and swapped question. Record the actual mapping errors. A schema check alone is not a handwriting-recognition benchmark.

See [Evidence and question binding](evidence_and_question_binding.md).
