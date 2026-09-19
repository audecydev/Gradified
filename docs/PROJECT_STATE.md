# Project State

Last meaningful update: 2026-09-19

## Current milestone

The deterministic scoring kernel is complete, technically accepted, and frozen at its declared boundary.

**Rubric Authoring Safety & Compilation** has passed its qualified verification, adversarial/mutation verification, fresh independent source/contract review, and exact staging/source audit on branch `rubric-authoring-safety`.

The reviewed source/test set is approved for the acceptance commit/freeze at this deterministic authoring/compilation boundary. The acceptance commit freezes this boundary; Git history is the authoritative commit identity.

`RubricGenerator` is the next implementation capability and is not yet implemented.

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

### Rubric Authoring Safety & Compilation accepted freeze set

Implemented in the isolated capability worktree:

- generated/teacher-edited rubric content cannot establish trusted `question_id`, `max_marks`, or scoring-semantics identity;
- trusted finalized question identity/maximum are supplied separately through an immutable scoring basis;
- duplicate rubric/criterion/level IDs and unknown references are rejected;
- dependency references/cycles and gate/cap/deduction/rounding structures are validated;
- complete marks reconciliation is checked against the frozen scoring semantics;
- immutable explicit `RubricCompilationLimits` cover criteria, levels, accepted equivalents, rules, rule conditions, allowed level IDs, text length, serialized authority size, and reconciliation state space;
- no production resource-limit defaults are invented;
- pathological reconciliation state spaces are rejected before Cartesian enumeration begins;
- compiled candidates do not publicly expose reducer `authority`, `rubric`, or `policy` shortcuts;
- the supported reducer-authority path requires an ACTIVE version;
- lifecycle is immutable and follows DRAFT -> VALIDATED -> APPROVED -> ACTIVE -> RETIRED;
- Release 1 approval is bound to exact rubric/version, finalized-question hash, authoring-content hash, compiled-authority hash, and compiler-profile identity;
- activation revalidates against the current explicit resource policy;
- compiler/resource/authority fingerprints are deterministic across fresh process hash seeds;
- known invalid rounding is a domain lint failure, while unexpected `ValueError` from projection remains a transparent technical failure.

## Verification and reproducibility

Authoritative verification runtime:

- Windows x64;
- CPython 3.11.9;
- exact version-pinned verification dependency closure declared in `requirements-test.txt`.

Committed deterministic-kernel acceptance remains:

- 519/519 full tests passed;
- 0 failures;
- 0 errors;
- 0 skips.

Final Rubric Authoring acceptance verification:

- targeted Rubric Authoring suite: **78/78 passed**;
- independently rerun frozen-kernel regression: **519/519 passed**;
- complete current suite: **597/597 passed**;
- selected mutation-scope baseline: **52/52 passed**;
- selected adversarial mutations M01-M08: **8/8 genuine kills** after inspection of mutation logs/JUnit evidence;
- M06 specifically proves reconciliation enumeration does not start before state-space resource admission;
- frozen `src/grading/contracts` and `src/grading/scoring` remain unchanged.

The selected mutation result is evidence for those eight attacked invariants only; it is not a universal mutation-resistance claim.

Latest qualified selected-mutation evidence ZIP SHA-256:

`81b51b1b8ac55ff0d0d13ad3bc7880dd7240e4cbfdad2b38286504894fa59446`

## Current implementation identity

Frozen closure / capability branch base:

`178668b9b735ef369825c86d16db7999b8d3c784`

Tree:

`d95ced020330925f8d966aa418350805b55b0fab`

Capability branch:

`rubric-authoring-safety`

Capability worktree:

`F:\Gradified_Work\10_Active\Rubric_Authoring_Safety\repository`

Accepted freeze-set state:

- fresh independent source/contract review passed with non-blocking follow-ups and no confirmed source defect;
- exact staging/source audit reproduced prospective tree `5df9545815f01109bd6c4d932ac0a4212b3e3341` before the final documentation-only acceptance update;
- reviewed Rubric Authoring source/tests are byte-identical in semantic text to the mutation-verified source, modulo Git/Windows line-ending normalization;
- protected closure working copy remains separate;
- frozen scoring/contracts source remains unchanged;
- final acceptance commit identity is supplied by Git history rather than self-recorded in this file.

## Important non-claims and deferred boundaries

The current Rubric Authoring candidate does **not** establish:

- `RubricGenerator` or question/model-answer-to-rubric generation;
- academic rubric-generation quality;
- teacher-marked grading accuracy;
- source/model-answer contradiction resolution;
- OCR correctness or OCR schema;
- semantic evaluator academic correctness;
- authentication of `teacher_ref`, caller authorization, or tenant/backend security;
- global transactional uniqueness of an ACTIVE rubric version;
- database/persistence/publication behavior;
- real production values for `RubricCompilationLimits`;
- unrestricted external payload/job cardinality;
- provider reliability or production provider quality;
- universal OS/Python support;
- cryptographically reproducible package artifacts.

The deterministic scoring kernel receives already-admitted immutable scoring authority and does not authenticate its origin.

A private/underscore Python helper is an API-governance boundary, not a cryptographic/process-isolation security boundary.

## Integration blockers

The following real-world artifacts/policies are still required before their respective capabilities can be finalized:

- actual OCR JSON/schema and representative outputs;
- backend API/data structures and integration conventions;
- canonical authentication/tenant context;
- paper-selection/optional-question resolution rules if not supplied by the backend domain;
- production structural/job cardinality limits;
- approved production provider/runtime credentials.

## Academic-quality blockers

The following data is required before academic grading or rubric-generation quality can be claimed:

- representative finalized questions with maximum marks and school-authored model answers/marking schemes;
- an initial rubric-generation development corpus of roughly 30-50+ finalized questions across theory and mathematics;
- teacher-approved generated/edited rubrics or marking schemes for comparison;
- teacher-marked student-answer samples;
- representative reference/textbook material where applicable;
- real OCR evidence aligned with teacher-marked samples.

## Active assumptions

- External schemas adapt into grading-domain contracts through adapters.
- Missing OCR confidence means unknown/unavailable, never implicitly good.
- Math parse failure means uncertainty, not student error.
- Teacher-marked data is required for academic validation.
- `FinalizedQuestionScoringBasis` is trusted input to the compiler; authentication/provenance of that trust is upstream.
- `teacher_ref` represents an already-authenticated upstream approval assertion; this capability does not authenticate the teacher.
- Production job/resource values remain unresolved until explicitly governed and tested.
- The accepted Rubric Authoring boundary must not be reopened without a verified defect, authority contradiction, or changed requirement.

## Verification status

- Numeric scoring kernel: complete and frozen.
- Deterministic question scoring: complete and frozen.
- Deterministic paper aggregation: complete and frozen.
- Qualified committed deterministic-kernel regression: 519/519.
- Rubric Authoring Safety & Compilation: **accepted for freeze at its deterministic authoring/compilation boundary**.
- Rubric Authoring targeted verification: 78/78.
- Frozen-kernel regression under the candidate: 519/519.
- Full current regression: 597/597.
- Selected Rubric Authoring mutation campaign: 8/8 genuine kills for the selected mutations.
- Rubric Authoring exception-transparency regression: green.
- Fresh independent Rubric Authoring source/contract review: **passed with non-blocking follow-ups**; no confirmed source defect found.
- Exact staging/source audit: **passed**; only the reviewed source/tests and intentional documentation were staged, frozen scoring/contracts remained unchanged, and qualified 78/519/597 verification passed on the staged-identical working tree.
- Final pre-commit audit: **passed for the reviewed source/test boundary, subject only to removing any unrelated untracked shell debris before commit**.
- `RubricGenerator`: not yet implemented.
- OCR integration: blocked on real interface evidence.
- Backend integration: blocked on real interface evidence.
- Academic grading benchmark: blocked on teacher-marked data.
- Rubric-generation benchmark: not yet run.
- Production provider benchmark: blocked on approved provider/runtime.

## Next task

Implement **RubricGenerator** as a distinct subsequent capability on top of the frozen Rubric Authoring Safety & Compilation boundary.

The generator must consume finalized school-authorized question inputs (question identity/text, authoritative maximum marks, school-authored model answer or marking scheme, and optional approved reference context), produce candidate rubric content only, and feed that content through the existing deterministic linter/compiler and Release 1 teacher-approval boundary.

Use real finalized question/model-answer fixtures for development. A single paper is useful for integration but is insufficient to claim rubric-generation quality; representative teacher-reviewed benchmark evidence is still required.

Do not reopen the frozen Rubric Authoring boundary without a verified defect, authority contradiction, or changed requirement.
