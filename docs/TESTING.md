# Testing Strategy and Verification Status

Passing ordinary unit tests does not prove that a grading system is academically accurate. Different verification layers prove different things.

## Unit tests

Prove local deterministic behavior.

Examples:
- exact arithmetic;
- dependency suppression;
- gate/cap behavior;
- deduction behavior;
- question-boundary rounding;
- paper-bound enforcement;
- canonical ordering.

## Contract/schema tests

Prove data entering or leaving a component has valid structure and values.

Examples:
- unknown criterion ID rejected;
- unknown performance level rejected;
- duplicate/missing judgments rejected;
- closed exact runtime types;
- malformed scoring authority rejected;
- unsupported numeric profile rejected;
- immutable result contracts.

## Property/invariant tests

Prove safety properties over many generated inputs.

Examples:
- successful scores remain inside the configured range;
- score calculation is independent of caller ordering;
- duplicate judgments/results cannot create duplicate marks;
- evaluator/model free-form totals are never authoritative;
- exact arithmetic is invariant to hostile Decimal context;
- paper aggregate equals the exact sum of admitted question final scores.

## Mutation testing

Mutation testing is used to determine whether tests distinguish meaningful incorrect implementations.

Mutation percentage is **not** treated as a quality score.

The completed deterministic scoring boundaries were subjected to targeted mutation analysis. Contract-distinguishing mutations were required to be observable to the relevant verification gates; behaviorally equivalent or domain-implied mutations were classified rather than artificially forced to fail.

No unresolved contract-distinguishing mutation remained at technical acceptance.

## Integration tests

Prove components work together across a meaningful workflow boundary.

External OCR/backend integration tests wait for real interfaces.

The current deterministic kernel shares exact runtime contracts between question scoring and paper aggregation. The final independent closure audit also executed a direct reducer-to-paper composition probe. A permanent vertical integration test belongs in the synthetic end-to-end grading path where evaluator/evidence/scoring composition is exercised as one workflow.

## Regression tests

Every meaningful discovered defect becomes a permanent test before the fix is considered complete.

A regression test should reproduce the actual failure mechanism rather than merely testing nearby behavior.

## Adversarial/failure tests

Try to make the engine fail unsafely.

Covered deterministic-kernel attacks include:
- malformed authority;
- forged exact-class objects;
- subclass smuggling;
- missing internal slots;
- noncanonical finite scoring values;
- unknown/mismatched identity references;
- duplicate/missing/unexpected results;
- unsupported profile provenance;
- range overflow/underflow;
- premature result construction;
- exception swallowing;
- external-state dependency;
- caller-order dependence.

Expected result: typed failure or transparent technical failure, never a fabricated academic result.

## Academic grading benchmark

This is different from software verification.

Required data:
- question;
- maximum marks;
- teacher/model answer or marking scheme;
- student answer;
- teacher-awarded marks;
- criterion-level labels where available;
- original scan/OCR where possible.

Track:
- MAE;
- exact agreement;
- +/-1 mark agreement;
- criterion agreement;
- material-error rate;
- over/under-grading;
- review coverage;
- alternative-method performance;
- OCR-corruption performance;
- presentation invariance.

Teacher-marked data is required before claiming academic grading quality.

## Rubric-generation benchmark

Measure rubric generation separately from grading execution.

Track:
- structural validity;
- marks reconciliation;
- criterion coverage;
- teacher acceptance/edit rate;
- ambiguity/missing criteria;
- alternative-method coverage.

A bad rubric can cause bad grading even when deterministic scoring executes it perfectly.

## Cost/performance tests

Track:
- provider/model;
- calls;
- input/output tokens;
- retries;
- estimated cost per question/paper;
- p50/p95 latency;
- teacher review minutes.

Quality gates come before cost optimization.

## Qualified deterministic-kernel verification

Authoritative verification runtime:

- Windows x64;
- CPython 3.11.9;
- dependencies pinned by version in `requirements-test.txt`.

This is a qualified runtime reproducibility declaration. It is **not** a cryptographic software-supply-chain reproduction guarantee because dependency artifact hashes/wheels are not pinned.

Final committed acceptance:

- traceability: 1 passed;
- pre-paper-aggregation baseline: 430 passed;
- paper aggregation: 88 passed;
- full suite: 519 passed;
- failures: 0;
- errors: 0;
- skips: 0;
- exact testcase identity union: 430 + 88 + 1 = 519;
- fresh-process contract import/type-hint gate: passed;
- working tree clean before and after.

Current final acceptance evidence SHA-256:

`3E0FA92B7BC6744423CD1E942CE61E16F5C6913BA364730AA1FE92391FBF6A76`

## What this verification does not prove

The deterministic-kernel suite does not prove:
- OCR correctness;
- semantic evaluator academic correctness;
- correctness of school-authored content;
- rubric-generation quality;
- authority authentication;
- tenant/backend security;
- unrestricted external job-size safety;
- persistence/publication correctness;
- production provider reliability;
- universal platform support;
- academic agreement with teachers.

Those require their own later evidence.
