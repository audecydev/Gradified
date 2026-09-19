# Project State

Last meaningful update: 2026-09-18

## Current milestone

The deterministic scoring kernel is complete, technically accepted, and frozen at its declared boundary.

The next implementation capability is **Rubric Authoring Safety & Compilation**.

## Verified completed

### Exact numeric scoring

- Numeric Profile v1 is implemented.
- Scoring values are exact finite decimals with one canonical internal representation.
- Authoritative arithmetic is independent of ambient Decimal precision, rounding, exponent limits, traps, and flags.
- Numeric-envelope failure is distinct from malformed input and academic score-range failure.
- `numeric_profile_version="1"` is system execution provenance.
- Observable profile changes require a profile-version change.

### Deterministic question scoring

- Unknown criterion IDs are rejected.
- Unknown performance levels are rejected.
- Duplicate criterion judgments are rejected.
- Missing criterion judgments are rejected.
- Rubric performance levels are the sole source of criterion numerical contribution.
- Failed positive-credit dependencies suppress only positive contribution; zero and negative configured contributions are preserved.
- Gates and caps apply the most restrictive triggered ceiling.
- Each configured deduction is applied at most once when triggered.
- Rule predicates inspect original semantic judgments.
- Question scoring order is fixed:
  - dependency-adjusted criterion contributions;
  - exact subtotal;
  - gates;
  - caps;
  - deductions;
  - exactly one question-boundary rounding stage;
  - final academic range validation.
- Final out-of-range scores fail; they are never clamped.
- Question results preserve rubric, scoring-policy, scoring-semantics, numeric-profile, rule, stage, and criterion provenance.
- The evaluator/model has no authoritative numerical-total input path.

### Deterministic paper aggregation

- Paper aggregation consumes an upstream-resolved exact question composition.
- Missing, duplicate, and unexpected question results are rejected.
- Question/rubric/policy/scoring-semantics identities are checked.
- Unsupported or malformed numeric-profile provenance is rejected.
- Consumed question min/final/max values are defensively re-admitted and checked for self-consistency.
- Caller order cannot determine canonical paper provenance.
- Only admitted `QuestionScoreResult.final_score` values contribute to the paper total.
- Paper minimum and maximum are consumed from upstream authority and are not reconstructed from question-result bounds.
- There is no paper-level rounding stage.
- Out-of-range paper totals fail; they are never clamped.
- Successful paper results preserve the admitted grading-specification reference and canonical question-result tuple.

### Verification and reproducibility

Qualified verification runtime:

- Windows x64;
- CPython 3.11.9;
- exact version-pinned verification dependency closure declared in `requirements-test.txt`.

Final committed acceptance:

- 1 traceability test passed;
- 430 pre-paper-aggregation tests passed;
- 88 paper-aggregation semantic tests passed;
- 519/519 full tests passed;
- 0 failures;
- 0 errors;
- 0 skips;
- testcase identity union verified exactly;
- fresh-process contract import/type-hint isolation passed;
- repository was clean before and after.

Targeted mutation analysis found no unresolved contract-distinguishing mutation in the completed paper-aggregation boundary.

## Current implementation identity

Deterministic paper-aggregation commit:

`e6c7cb71b33120b6cdeeb2b4176a3f33a8580869`

Tree:

`0fc3601fbf0bfacaacfc378aa0ce9313ffa45313`

Final committed parent-to-HEAD patch SHA-256:

`CDC9D97DCCD46B90E9C11215C0B5CCD525BB98BE30BF7770DE551C9D01D8BE89`

Final qualified acceptance evidence SHA-256:

`3E0FA92B7BC6744423CD1E942CE61E16F5C6913BA364730AA1FE92391FBF6A76`

## Important non-claims and deferred boundaries

The completed kernel does not establish:

- rubric generation quality;
- authoring-time marks reconciliation for a complete rubric;
- teacher approval workflow;
- which optional/alternate questions count for a specific paper;
- the persisted upstream schema that projects paper-level scoring bounds;
- OCR correctness or OCR schema;
- semantic evaluator academic correctness;
- authority authentication or caller authorization;
- tenant/backend security;
- database/persistence/publication behavior;
- unlimited external payload/job cardinality;
- provider reliability;
- universal OS/Python support;
- cryptographically reproducible package artifacts;
- academic grading accuracy on teacher-marked data.

Numeric Profile v1 explicitly does not authorize arbitrary structural cardinality. Production ingress/job limits must be defined and tested at the appropriate upstream boundaries before unrestricted external ingestion.

## Integration blockers

The following real-world artifacts are still required before their respective capabilities can be finalized:

- actual OCR JSON/schema and representative outputs;
- backend API/data structures and integration conventions;
- canonical authentication/tenant context;
- paper-selection/optional-question resolution rules if not already supplied by the backend domain;
- production structural/job cardinality limits;
- approved production provider/runtime credentials.

## Academic-quality blockers

The following data is still required before academic grading quality can be claimed:

- teacher-marked sample papers/answer instances;
- teacher-approved marking schemes/reference answers for benchmark cases;
- representative reference/textbook material;
- real OCR evidence aligned with teacher-marked samples.

## Active assumptions

- External schemas adapt into grading-domain contracts through adapters.
- Missing OCR confidence means unknown/unavailable, never implicitly good.
- Math parse failure means uncertainty, not student error.
- Teacher-marked data is required for academic validation.
- The deterministic scoring kernel receives already-admitted immutable scoring authority and semantic judgments/results; it does not authenticate their origin.
- Production job/resource limits remain upstream until explicitly defined and tested.

## Verification status

- Numeric scoring kernel: complete and frozen.
- Deterministic question scoring: complete and frozen.
- Deterministic paper aggregation: complete and frozen.
- Qualified committed regression: complete, 519/519.
- Whole-kernel source/authority audit: complete.
- Rubric authoring safety and compilation: next.
- OCR integration: blocked on real interface evidence.
- Backend integration: blocked on real interface evidence.
- Academic benchmark: blocked on teacher-marked data.
- Production provider benchmark: blocked on approved provider/runtime.

## Next task

Implement **Rubric Authoring Safety & Compilation**.

Acceptance must include:

- duplicate rubric/criterion/level IDs rejected;
- unknown level/dependency references rejected;
- maximum possible scoring contributions and scoring policy reconciled to the question maximum;
- invalid dependencies, cycles, caps, gates, deductions, and rounding rejected;
- immutable version/activation contracts;
- teacher approval required before ACTIVE for Release 1;
- compiled output is directly consumable by the deterministic scoring kernel without guessed remapping.
