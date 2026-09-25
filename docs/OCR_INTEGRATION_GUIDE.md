# OCR Integration Guide

This guide is for the OCR engineer connecting real answer-sheet OCR output to the grading core.

## Goal

Convert the OCR system's real output into Gradified's normalized `AnswerEvidenceBundle` contract.

Do **not** change the grading core to depend on OCR-vendor field names.

## Core contract to produce

The main value is:

```python
AnswerEvidenceBundle(
    schema_version=...,
    submission_ref=...,
    ocr_provenance=...,
    questions=(...),
)
```

Each question is:

```python
QuestionEvidence(
    question_id=...,
    answer_scope_ref=...,
    blocks=(...),
    warnings=(...),
)
```

Each OCR block becomes:

```python
EvidenceBlock(
    block_id=...,
    type=...,
    content=...,
    language=...,
    confidence=...,
    confidence_status=...,
    state=...,
    page=...,
    location=EvidenceLocation(...),
    reading_order=...,
    asset_ref=...,
)
```

The exact definitions are in `src/grading/contracts/evidence.py`.

## Required mapping rules

### 1. Keep stable submission identity

`submission_ref` must identify the answer-sheet submission that the backend/workflow admitted.

The OCR adapter must not invent a different submission identity for convenience.

### 2. Preserve question mapping

Each `QuestionEvidence.question_id` must match the backend/admitted grading question ID.

If OCR cannot map content to a question reliably, do not guess silently. Surface the mapping problem to the integration workflow.

### 3. Give every evidence block a stable unique ID

`block_id` must be unique across the entire submission bundle, not only within one question.

Duplicate block IDs are rejected.

### 4. Use the correct evidence type

Available block types are:

- `TEXT`
- `MATH`
- `TABLE`
- `FIGURE`
- `CODE`
- `OTHER`

Do not label everything `TEXT` if the OCR system actually knows the modality.

### 5. Represent confidence truthfully

If confidence exists:

```text
confidence_status = PRESENT
confidence = finite numeric value from the OCR system
```

If confidence does not exist:

```text
confidence_status = UNAVAILABLE
confidence = None
```

Do not manufacture a confidence score merely because the field exists in the Gradified contract.

### 6. Preserve crossed-out / uncertain state when available

Supported states are:

- `ACTIVE`
- `CROSSED_OUT`
- `UNCERTAIN`

Do not convert crossed-out work back to active text.

If OCR cannot determine a state, agree the mapping with the workflow team rather than hiding uncertainty.

### 7. Preserve page/location information

`EvidenceLocation` carries a location status and optional finite bounding-box coordinates.

Use `UNAVAILABLE`/`None` when location is genuinely unavailable instead of fabricated coordinates.

### 8. Preserve OCR provenance

`ocr_provenance` must identify the OCR process/version sufficiently for later traceability. The core treats it as provenance metadata; it does not authenticate the OCR provider.

## First integration test

Use one real OCR payload and one real mapped question.

1. Read the OCR payload.
2. Construct one `AnswerEvidenceBundle`.
3. Confirm construction succeeds.
4. Confirm all block IDs are unique.
5. Confirm the exact question ID matches the ACTIVE question authority.
6. Feed the bundle into an already-supported evaluator path.
7. Confirm bad question mapping fails rather than silently grading another question.
8. Confirm a crossed-out referenced block is rejected by evidence verification.
9. Confirm missing referenced evidence is rejected.

## NUMERIC-specific note

The frozen bounded NUMERIC v1 path is deliberately narrow. Current admission supports exactly one relevant active `TEXT` or `MATH` block for one exact question and a bounded ASCII finite-decimal syntax. UNIT parsing, scientific notation, fractions, expressions, and general OCR disambiguation are not production-complete.

Do not pre-normalize unsupported forms into a value just to make the numeric path accept them.

## DIRECT-text-specific note

The frozen DIRECT text semantic path currently accepts active `TEXT` evidence and rejects uncertain/unsupported active evidence modes according to its contract.

Do not hide unsupported modalities by converting them to text without an explicit integration decision.

## Expected outcome

A correct OCR adapter should make OCR data look like Gradified evidence while preserving uncertainty and provenance. It should **not** make academic decisions, select rubric levels, calculate marks, or publish grades.
