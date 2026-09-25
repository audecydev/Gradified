# Backend / Workflow Integration Guide

This guide is for the backend engineer connecting Gradified's grading core to real workflow, storage, authentication, and persistence.

## Backend responsibilities

The backend owns facts that the grading core deliberately does not authenticate:

- tenant identity and tenant isolation;
- user identity, roles, and authorization;
- ACTIVE grading-spec selection;
- question/model-answer/reference access;
- object/file storage;
- grading-job lifecycle;
- durable run/attempt identifiers;
- idempotency/retry policy;
- result persistence;
- review/regrade workflow;
- official publication.

The grading core validates deterministic relationships between already-admitted values. It does not replace the backend trust model.

## 1. ACTIVE question authority

The backend should implement the `ActiveGradingSpecSource` protocol from:

`src/grading/active_question_authority.py`

The method is conceptually:

```python
resolve_active_question(
    grading_spec_ref=...,
    question_id=...,
) -> ActiveQuestionSelection
```

The returned selection must carry the exact requested:

- grading spec reference/version;
- question ID;
- question text;
- context policy;
- ACTIVE rubric authoring version.

The core cross-checks those values against admitted paper authority and derives evaluator-facing scoring authority from the existing ACTIVE rubric lifecycle.

### Backend test cases

Test at least:

- correct spec + correct question;
- wrong spec returned;
- wrong question returned;
- non-ACTIVE rubric returned;
- malformed context policy;
- source/backend exception;
- historical spec version requested after a newer version exists.

A request for an old immutable version must still resolve that old version, not silently return the newest one.

## 2. Execution context

The core uses:

```python
GradingExecutionContext(
    grading_run_id=...,
    submission_ref=...,
    exam_ref=...,
    grading_spec_ref=...,
)
```

The backend is responsible for making those IDs real and durable.

The core checks relationships such as submission/spec matching, but the object itself is not an authentication credential.

## 3. Scoring execution

The composition function is:

```python
execute_grading_from_evaluations(
    context=...,
    evidence=...,
    questions=...,
    paper_authority=...,
)
```

It runs the real evidence verifier, deterministic question reducer, and paper aggregator.

It returns a `GradingExecutionResult` containing verified question records and a deterministic `PaperScoreResult`.

This result is still a **candidate grading result**, not an official published grade.

## 4. Do not duplicate scoring in the backend

The backend should store and transport score outputs, but it should not independently recalculate the rubric logic, caps, gates, deductions, rounding, or paper total.

If the backend needs a display total, use the result produced by the grading core.

## 5. Idempotency and persistence are still open integration work

The frozen core does not itself prove:

- exactly-once database commit;
- transaction rollback;
- duplicate-job suppression;
- retry-safe provider calls;
- unique authoritative result creation;
- official publication state.

These must be tested at the backend/workflow layer.

A good production design should preserve one stable grading run ID and explicit evaluator-attempt IDs, and must prevent a retry from creating a second authoritative result accidentally.

## 6. Reference access

For reference context, the backend/reference service must apply trusted tenant/class/subject/reference scope before returning material.

Read [`REFERENCE_INTEGRATION_GUIDE.md`](REFERENCE_INTEGRATION_GUIDE.md).

## 7. First backend integration test

Use one deterministic question first.

1. Create/fetch an immutable ACTIVE grading spec version.
2. Fetch the exact question and ACTIVE rubric.
3. Resolve paper authority for that same spec version.
4. Map one submission to a stable `submission_ref`.
5. Supply normalized evidence.
6. Run a supported evaluator.
7. Execute verification/scoring.
8. Persist the candidate result with run/spec/submission identity.
9. Retry the same job deliberately.
10. Prove the backend does not silently create a second authoritative result.

## Expected outcome

A correct backend integration provides trustworthy workflow facts and stores results without becoming a second scoring engine.
