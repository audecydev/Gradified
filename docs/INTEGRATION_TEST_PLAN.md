# Integration Test Plan

This is the minimum recommended test plan for teams integrating the verified grading core.

The goal is not only to prove happy-path connectivity. The goal is to prove that wrong identities, malformed evidence, unsupported capabilities, external failures, and retries do not silently produce authoritative grades.

## Phase 0 — verify the repository before integration

From the repository root, use the qualified environment:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-test.txt
python -m pytest -q
python -m pip check
```

Expected qualified baseline from the frozen integration candidate:

```text
1499 passed
No broken requirements found.
```

Record Python, pytest, Hypothesis, commit SHA, tree SHA, and clean/dirty status with every integration run.

## Phase 1 — contract smoke tests

Before using real external systems, prove that each adapter can construct the real Gradified contracts.

Test:

- one valid ACTIVE question authority;
- one valid evidence bundle;
- one valid supported evaluator input;
- one valid grading execution context;
- one valid candidate grading execution.

Then deliberately break one identifier at a time and confirm failure.

## Phase 2 — OCR adapter tests

Use real OCR payloads.

Required cases:

- correct question mapping;
- duplicate block ID;
- missing question mapping;
- confidence present;
- confidence unavailable;
- crossed-out block;
- uncertain block;
- location present/partial/unavailable;
- page/reading order preserved;
- unsupported modality preserved rather than silently converted.

Expected result: bad OCR structure/mapping fails before it can silently change academic meaning.

## Phase 3 — backend authority tests

Required cases:

- exact ACTIVE spec/question resolves;
- wrong spec version returned;
- wrong question returned;
- old immutable version still resolves historically;
- backend source exception;
- submission/spec binding mismatch;
- duplicate or missing question execution input.

Expected result: the core never silently substitutes another spec/question.

## Phase 4 — deterministic evaluator tests

### CHOICE

Test valid match, valid mismatch, malformed/unknown selection, and authority mismatch.

### NUMERIC

Test exact match, tolerance boundary, outside tolerance, canonical finite-decimal forms, malformed syntax, wrong evidence binding, and unsupported forms.

Do not expand the current NUMERIC scope by preprocessing unsupported units/scientific notation/fractions into accepted text.

## Phase 5 — semantic-provider tests

Required cases:

- valid DIRECT response;
- malformed JSON;
- duplicate JSON key;
- unknown criterion;
- unknown level;
- missing evidence reference;
- cross-question evidence reference;
- oversized provider response;
- provider timeout/error;
- provider returns data in different order;
- uncertainty metadata preserved.

Expected result: provider failure or malformed provider output never becomes an authoritative total.

## Phase 6 — reference integration tests

Required cases:

- correct spec/question/policy binding;
- wrong spec;
- wrong question;
- wrong context policy;
- zero chunks;
- chunk count limit;
- chunk content limit;
- total content limit;
- provenance-field limit;
- source exception;
- `DIRECT` prevents source call;
- tenant-isolation test at the real backend/reference layer.

Expected result: no unrelated fallback material and no cross-tenant leakage.

## Phase 7 — retry / idempotency tests

The core alone does not provide database exactly-once semantics.

The integrated system must test:

- same grading job delivered twice;
- provider timeout then retry;
- backend commit succeeds but worker acknowledgment fails;
- duplicate evaluator attempt;
- duplicate result commit;
- regrade creates a new linked result instead of overwriting history.

Expected result: no duplicate authoritative publication and preserved audit trail.

## Phase 8 — real-paper end-to-end tests

Run at least:

1. one real subjective/text question path;
2. one real numeric/math question path.

The flow should be:

```text
real paper / ACTIVE spec
→ real answer sheet
→ real OCR adapter
→ normalized evidence
→ supported evaluator
→ evidence verification
→ deterministic scoring
→ persisted candidate result
→ review/regrade decision where applicable
```

No manual JSON editing should be required between stages.

## Phase 9 — release validation

Before a production Release 1 claim, add:

- held-out teacher-marked benchmark data;
- criterion agreement and score-error measurements;
- review-coverage measurements;
- latency and cost measurements;
- provider outage/failure tests;
- adversarial/security integration tests;
- load/backpressure/retry evidence;
- audit-log completeness.

## Stop conditions

Stop integration and investigate if any of the following occurs:

- score changes without an authorized rubric/policy/spec change;
- unsupported data is silently coerced into a supported capability;
- a model/provider can set the numerical total directly;
- cross-question or cross-spec evidence is accepted;
- cross-tenant reference material is accessible;
- retries create multiple authoritative results;
- malformed external data becomes an academic zero/incorrect judgment;
- a frozen scoring test regresses.
