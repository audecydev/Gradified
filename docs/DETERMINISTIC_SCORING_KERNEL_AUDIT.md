# Deterministic Scoring Kernel — Closure Audit

Date: 2026-09-18
Status: technically accepted and frozen within the declared boundary.

## Scope

This audit covers the deterministic numerical scoring capability:

- Numeric Profile v1;
- deterministic question scoring;
- deterministic paper aggregation;
- verification environment and committed implementation identity.

It does not certify the complete grading product.

## Authority basis

The audit was checked against:

- Gradified Software Requirements Specification v1.0;
- Verification-First Adaptive Grading Engine Version 2 — SRS-Aligned Engineering Source of Truth;
- Authoritative Scoring Numeric Profile v1;
- the committed scoring source and tests;
- qualified Windows acceptance evidence.

Prior audit conclusions were treated as evidence, not product authority.

## Implementation identities

Numeric/scoring foundation:

`322807de9ec89c03fc074af9104e26a84f224751`

Deterministic question scoring:

`3065d1428fca948d0eb3f84efbcb865f90ded682`

Qualified verification environment declaration:

`d7f12bb10825f80faf7e0cb188c3bc949585e5c4`

Deterministic paper aggregation:

`e6c7cb71b33120b6cdeeb2b4176a3f33a8580869`

Paper-aggregation tree:

`0fc3601fbf0bfacaacfc378aa0ce9313ffa45313`

Parent-to-paper-aggregation patch SHA-256:

`CDC9D97DCCD46B90E9C11215C0B5CCD525BB98BE30BF7770DE551C9D01D8BE89`

## Final qualified acceptance

Evidence ZIP SHA-256:

`3E0FA92B7BC6744423CD1E942CE61E16F5C6913BA364730AA1FE92391FBF6A76`

Qualified runtime:

- Windows x64;
- CPython 3.11.9;
- exact version-pinned dependency closure from `requirements-test.txt`;
- `pip check` clean.

Execution:

```text
traceability: 1 passed
baseline:     430 passed
paper:         88 passed
full:         519 passed

failures: 0
errors:   0
skips:    0
```

The testcase identity sets were independently reconciled:

```text
430 + 88 + 1 = 519
```

with no overlap and no testcase missing from or added to the full run.

The repository remained clean and the committed HEAD/tree remained unchanged during acceptance.

## Whole-kernel source verdict

### Numeric semantics

PASS.

The implementation uses one frozen exact numeric profile:
- exact finite decimals;
- canonical representation;
- exact integer/rational arithmetic;
- deterministic error separation;
- no float scoring path;
- no ambient Decimal arithmetic authority.

### Question numerical authority

PASS.

Criterion numerical effects originate from the compiled rubric.

Scoring policy owns:
- dependencies;
- gates;
- caps;
- deductions;
- question rounding;
- question minimum/maximum.

The evaluator supplies semantic level selections, not an authoritative total.

### Question execution order

PASS.

The source enforces:

`validated judgments -> dependency-adjusted contributions -> exact subtotal -> gates -> caps -> deductions -> one question-boundary rounding -> final range validation -> result`

No early clamp or zero substitution exists.

### Paper numerical authority

PASS.

Paper aggregation:
- consumes an already-resolved question composition;
- validates exact question/rubric/policy identities;
- canonicalizes provenance to authority order;
- sums only admitted question `final_score`;
- consumes upstream paper bounds;
- performs no second rounding;
- rejects out-of-range totals.

### Provenance and immutability

PASS.

Question results preserve rubric/policy/semantics/profile/rule/stage provenance.

Paper results preserve:
- grading-specification reference;
- profile version;
- canonical immutable question-result tuple;
- final score;
- admitted paper bounds.

### Failure behavior

PASS.

Known malformed inputs fail with typed scoring-domain errors.

Unexpected technical failures are not broadly swallowed or converted into academic scores.

No partial successful result is constructed before all required checks succeed.

### External state

PASS.

No filesystem, database, network, time, randomness, or provider state has numerical authority inside deterministic scoring.

## Mutation assurance

Targeted mutation analysis was performed against the deterministic question-scoring and paper-aggregation boundaries.

Contract-distinguishing mutations were required to be observable to verification. Behaviorally equivalent or domain-implied mutations were classified rather than artificially forced to fail.

No unresolved contract-distinguishing mutation remained at technical acceptance.

## Composition check

Question scoring returns the exact `QuestionScoreResult` contract consumed by paper aggregation.

The closure audit performed a direct composition probe:
- real question reducer outputs were used as paper-aggregation inputs;
- caller order was reversed;
- exact rubric/policy identities were pinned in paper authority;
- paper aggregation succeeded;
- exact total was produced;
- output question provenance returned to authority order;
- the same immutable question-result objects were preserved.

A permanent full vertical test belongs in the synthetic end-to-end grading capability, where evidence/evaluator/scoring integration is tested together.

## Reproducibility boundary

The qualified environment pins dependency **versions**, not cryptographic wheel/package artifact hashes.

Therefore the evidence supports:

> qualified Windows x64 / CPython 3.11.9 verification reproducibility using the frozen version-pinned dependency closure.

It does not claim cryptographic software-supply-chain reproduction.

## Non-claims

This closure does not prove:
- authority authentication;
- caller authorization;
- OCR correctness;
- semantic evaluator correctness;
- rubric authoring quality;
- teacher/model-answer academic correctness;
- optional-question/section resolution;
- tenant/backend security;
- persistence/publication;
- unrestricted external job/cardinality safety;
- provider reliability;
- academic agreement with teacher-marked answers;
- universal platform support.

## Resource-safety boundary

Numeric Profile v1 bounds numeric representation/arithmetic, not arbitrary structural cardinality.

Unrestricted external production ingestion remains blocked until applicable exam/job/payload/result limits are explicitly defined and tested at their named upstream enforcement points.

## Final verdict

The deterministic scoring kernel is technically accepted and frozen **within its declared admitted-input boundary and qualified verification runtime**.

The next engineering work is rubric authoring safety/compilation and later integration/validation capabilities. No numerical scoring component should be reopened without a verified defect, authority contradiction, or changed requirement.
