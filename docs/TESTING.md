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
- canonical ordering;
- rubric authoring/lifecycle transitions.

## Contract/schema tests

Prove data entering or leaving a component has valid structure and values.

Examples:
- unknown criterion ID rejected;
- unknown performance level rejected;
- duplicate/missing judgments rejected;
- closed exact runtime types;
- malformed scoring authority rejected;
- unsupported numeric profile rejected;
- immutable result contracts;
- trusted finalized-question scoring basis kept separate from generated/edited rubric content;
- compiled candidates cannot expose supported pre-ACTIVE reducer-authority shortcuts.

## Property/invariant tests

Prove safety properties over many generated inputs.

Examples:
- successful scores remain inside the configured range;
- score calculation is independent of caller ordering;
- duplicate judgments/results cannot create duplicate marks;
- evaluator/model free-form totals are never authoritative;
- exact arithmetic is invariant to hostile Decimal context;
- paper aggregate equals the exact sum of admitted question final scores;
- complete rubric marks reconciliation respects the frozen scoring semantics.

## Mutation testing

Mutation testing is used to determine whether tests distinguish meaningful incorrect implementations.

Mutation percentage is **not** treated as a quality score.

The completed deterministic scoring boundaries were subjected to targeted mutation analysis. Contract-distinguishing mutations were required to be observable to the relevant verification gates; behaviorally equivalent or domain-implied mutations were classified rather than artificially forced to fail.

The current Rubric Authoring review candidate has also completed a selected eight-mutation adversarial campaign. The campaign is intentionally narrow and proves only the attacked invariants.

Selected Rubric Authoring mutations verified:

- public projection-builder authority shortcut restored;
- APPROVED state allowed to obtain reducer authority;
- approval/compiled-authority hash binding removed;
- approval/finalized-question hash binding removed;
- `max_rules` resource enforcement removed;
- reconciliation state-space guard removed;
- compiled-authority serialized-size checks removed;
- finalized-question ID text limit removed.

Qualified result: **8/8 selected mutations killed** after individual log/JUnit inspection.

M06 specifically uses a deterministic sentinel to prove that Cartesian reconciliation enumeration must not begin before resource admission rejects an over-limit candidate. Timeout-based mutation classification is not accepted as a semantic kill.

## Integration tests

Prove components work together across a meaningful workflow boundary.

External OCR/backend integration tests wait for real interfaces.

The current deterministic kernel shares exact runtime contracts between question scoring and paper aggregation. The final independent closure audit also executed a direct reducer-to-paper composition probe. A permanent vertical integration test belongs in the synthetic end-to-end grading path where evaluator/evidence/scoring composition is exercised as one workflow.

Rubric generation is a separate upcoming capability. Real finalized question/model-answer fixtures should be used as development integration cases once `RubricGenerator` exists.

## Regression tests

Every meaningful discovered defect becomes a permanent test before the fix is considered complete.

A regression test should reproduce the actual failure mechanism rather than merely testing nearby behavior.

Current Rubric Authoring regressions include:

- over-limit reconciliation must reject before Cartesian enumeration;
- compiled-authority serialized-size enforcement must be independently observable;
- approval must bind exact compiled-authority and finalized-question identity hashes;
- unexpected projection `ValueError` must remain a transparent technical failure rather than being converted into ordinary rubric lint rejection.

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

Covered Rubric Authoring attacks include:
- generated content attempting to own trusted question identity/max;
- pre-ACTIVE reducer-authority access;
- forged approval/provenance bindings;
- structural/resource-limit removal;
- pathological reconciliation workload;
- public authority-construction shortcut exposure;
- compiled-authority size-limit removal;
- exception swallowing/disguised technical failure.

Expected result: typed domain failure or transparent technical failure, never a fabricated academic result.

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

Required development/benchmark inputs should include representative finalized questions, authoritative maximum marks, school-authored model answers/marking schemes, and teacher-reviewed expected rubric structure where available.

Track:
- structural validity;
- marks reconciliation;
- criterion coverage;
- teacher acceptance/edit rate;
- ambiguity/missing criteria;
- alternative-method coverage.

A single question paper/model answer is useful for development and integration, but it is insufficient to claim rubric-generation quality.

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

Final committed deterministic-kernel acceptance:

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

Current final deterministic-kernel acceptance evidence SHA-256:

`3E0FA92B7BC6744423CD1E942CE61E16F5C6913BA364730AA1FE92391FBF6A76`

## Final Rubric Authoring acceptance verification

Accepted boundary status:

- capability branch: `rubric-authoring-safety`;
- base HEAD: `178668b9b735ef369825c86d16db7999b8d3c784`;
- fresh independent source/contract review passed with non-blocking follow-ups and no confirmed source defect;
- exact staging/source audit passed;
- qualified 78/519/597 verification passed on the staged-identical working tree;
- frozen scoring/contracts source remained unchanged;
- the acceptance commit freezes the deterministic Rubric Authoring Safety & Compilation boundary.

Qualified Windows / CPython 3.11.9 results:

- targeted Rubric Authoring suite: **78 passed**;
- frozen deterministic-kernel regression: **519 passed**;
- complete current suite: **597 passed**;
- selected mutation-scope baseline: **52 passed**;
- selected adversarial mutations: **8/8 genuine kills**;
- exception-transparency regression: passed;
- fresh independent source/contract review: **PASS WITH NON-BLOCKING FOLLOW-UPS**; no confirmed source defect found;
- the independent reviewer did not independently rerun the qualified suite, so 78/519/597 remain qualified-environment execution evidence rather than independently reproduced execution evidence.

Latest qualified selected-mutation evidence ZIP SHA-256:

`81b51b1b8ac55ff0d0d13ad3bc7880dd7240e4cbfdad2b38286504894fa59446`

This evidence, together with the independent source review and exact staging/source audit, is the technical acceptance evidence for the Rubric Authoring Safety & Compilation freeze boundary. Git history provides the final acceptance-commit identity.

## What this verification does not prove

The deterministic-kernel and Rubric Authoring suites do not prove:
- OCR correctness;
- semantic evaluator academic correctness;
- correctness of school-authored content;
- rubric-generation quality;
- academic adequacy of generated criteria;
- authority authentication;
- tenant/backend security;
- real production resource-limit values;
- unrestricted external job-size safety;
- persistence/publication correctness;
- production provider reliability;
- universal platform support;
- academic agreement with teachers.

Those require their own later evidence.
