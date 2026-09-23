# Release 1 Capability Roadmap

Status date: 2026-09-23

## Foundation — COMPLETE

Project skeleton, strict contracts, deterministic decimal/numeric profile, validation/error foundations and qualified verification environment are established.

## Deterministic Scoring Kernel — COMPLETE / FROZEN

Question scoring and paper aggregation are frozen. They remain the sole numerical authorities.

Frozen anchor:

`178668b9b735ef369825c86d16db7999b8d3c784`

Do not reopen without a verified defect, authority contradiction or changed requirement.

## Rubric Authoring Safety & Compilation — COMPLETE / FROZEN

Acceptance commit:

`5f3ee013bc9f732f469104a5f6c6dc151cad3402`

Release 1 still requires explicit teacher approval before ACTIVE authority.

## Rubric Generation Safety Boundary — COMPLETE / FROZEN BASELINE

### G1a deterministic composition

Commit:

`a6f0388f137226fb2125a07c6f01f424bafc5d58`

### G1b hostile provider ingress

Commit:

`c7a3ae3592b6ad0f6120178ddf9015e5ac10bdf0`

### Provider abstraction / Replay

Commit:

`c48c813fb0eb64013fc7265ed0d14f64dd9d3d57`

This closes the deterministic/no-network provider boundary, including replay provenance consistency. It does not establish a production network provider or academic rubric-generation quality.

## ACTIVE Grading Authority / Evaluator Authority — BUILD AUTHORIZED / NOT YET IMPLEMENTED

Decision: `BUILD`.

Purpose:

Implement the smallest immutable, read-only evaluator-facing ACTIVE question-authority boundary required by the accepted architecture. This is a cross-cutting authority prerequisite, not an evaluator capability and not a second lifecycle.

Required design constraints:

- consume only legitimately admitted ACTIVE question/spec context, the existing teacher-approved ACTIVE rubric authority, and the existing reducer-facing scoring authority;
- preserve exact binding among grading-spec identity, question identity, rubric authority and the existing reducer-facing scoring authority;
- expose a read-only immutable projection/view only; do not add independent authoring, approval, activation, retirement or mutation semantics;
- do not duplicate or implement a second GradingSpec/rubric lifecycle; the accepted architecture assigns the authoritative GradingSpec lifecycle to the trusted workflow/spec boundary;
- bind academic/question-context inputs to the exact ACTIVE authority by contained immutable values or explicit immutable/versioned references; never fall back to inferred, stale, `latest`, or unbound context;
- keep evaluator/provider/runtime configuration outside academic authority and record its exact identity against evaluation-attempt provenance in the later layer that owns attempts; provenance is audit evidence, not a deterministic-replay guarantee;
- allow approved reference material to establish academic validity only when the ACTIVE context policy permits it; reference material cannot independently create criteria, marks, levels, caps, deductions or other scoring consequences.

Explicit exclusions for this BUILD batch:

- no capability registry/router implementation or capability-status state in the new authority boundary;
- no evaluator implementation and no semantic/math composition framework;
- no production-provider, OCR, backend, retrieval, risk/review, `GradeResult`, persistence or publication implementation;
- no EXACT normalization/equivalence semantics;
- no NUMERIC expected-value/tolerance/unit/conversion semantics;
- no mathematical-equivalence or derivation semantics not already authorized;
- no change to S1, B2/B3, CHOICE, Numeric Profile v1, or their accepted tests/behavior merely to serve this boundary.

State discipline:

- **AUTHORIZED — NOT YET IMPLEMENTED**;
- governance persistence precedes behavior-defining RED;
- the first source/test batch must begin with one causal RED for the smallest missing authority-resolution/binding behavior;
- the first GREEN must implement only that behavior before hostile binding/mutation/version-mismatch cases are added separately.

EXACT remains `DEFER_EXACT`. NUMERIC remains `DEFER`. This decision does not select or authorize another evaluator capability.

## Synthetic E2E S1 — COMPLETE / FROZEN

Commit:

`456a6248e9d28ec083e7503c3a9ad9385de47c7d`

S1 proves block-grounded evidence contract/admission, evidence-reference verification, rich evaluator judgment preservation, narrow scoring projection and real deterministic question reduction.

Final complete suite: **709 passed**.

S1 is not the complete evidence subsystem.

## Synthetic E2E S2 — IN PROGRESS

S2a is closed/frozen at commit `61ce96d62774a78f4019c4905421324f614a7422` (tree `ced53127e566902050d47fe6b0a1bac921a0c9c3`). S2b-1 risk-observation extraction is closed/frozen at implementation commit `3f789a70443c3b9810c63b15bccb8dc4f5d889e5` (tree `99758c27b9890ba7e65ad0667c71db502e6071c7`), with governance closure commit `5838eac38a7a9df256a8ed0d5880a80e76b39128`, after a **743/743** complete regression. S2b-2 recommendation behavior is not implemented; remaining work is a Gradified-owned versioned platform/default policy decision plus broader risk/impact input coverage. Downstream evaluator capabilities are not globally blocked by S2b-2.

### S2a — execution integrity and context continuity

Objective:

Prove that one coherent grading execution invokes the real S1 verifier, real frozen question reducer and real frozen paper aggregator, while preserving workflow/audit identity outside the numerical kernel.

Required high-level flow:

```text
GradingExecutionContext
+ AnswerEvidenceBundle
+ per-question EvaluatedCriterionJudgments
+ already-admitted QuestionScoringAuthorities
+ already-admitted ResolvedPaperScoringAuthority
        ↓
verify_evaluated_judgments()
        ↓
reduce_question()
        ↓
QuestionScoreResult
        ↓
aggregate_paper()
        ↓
PaperScoreResult
+ preserved rich per-question audit/context
```

Implemented S2a invariants:

- the public execution path accepts pre-execution inputs rather than caller-supplied `VerifiedCriterionJudgments`, `QuestionScoreResult`, or `PaperScoreResult`;
- S2 owns the real verifier/reducer/aggregator calls;
- context `submission_ref` binds to the evidence bundle;
- context `grading_spec_ref` binds to the resolved paper authority;
- raw work is rejected for duplicate/missing/unexpected question IDs before execution;
- execution order is canonicalized from authoritative paper composition;
- work `question_id` binds to rubric/policy question identity before S1/B2;
- rich verified judgments and B2 numerical results remain parallel rather than being positionally merged or reconstructed;
- no S2 arithmetic duplicates reducer or paper aggregation behavior;
- B3 retains rubric/policy/result admission and paper arithmetic;
- native S1/B2/B3 failures propagate unchanged.

Qualified final evidence:

- inherited S1 regression: **709/709**;
- original S2a contract: **10/10**;
- acceptance-hardening: **8/8**;
- all S2a tests: **18/18**;
- complete suite before final staging: **727/727**;
- final governance-inclusive staged suite: **727/727**;
- implementation commit: `61ce96d62774a78f4019c4905421324f614a7422`;
- parent / frozen S1 base: `456a6248e9d28ec083e7503c3a9ad9385de47c7d`;
- committed tree: `ced53127e566902050d47fe6b0a1bac921a0c9c3`;
- final staged acceptance patch SHA-256: `0015fdb2b26ec2667d94cdce00f6104750d497cc42f467221161f112bf41c56a`;
- post-commit complete suite: **727/727**;
- post-commit working tree: clean.

Historical code/test-only forensic identities remain `804a28a1041b264ad150638a3267d6cf69802354` and patch SHA-256 `1bbf993078166ee4b07e627cbaf30927bd559b527ee5b5a91806e0ab5d5e19eb`.

S2a non-claims:

- `GradingExecutionContext` is a data container, not a trust token;
- `grading_run_id` and `exam_ref` are preserved/validated but not authenticated by S2a;
- supplied scoring authorities are already-admitted trusted upstream domain inputs; S2a does not authenticate their backend/lifecycle origin;
- supplied `EvaluatedCriterionJudgment` values are not proven to have been created for this exact run/spec; evaluator-attempt provenance is deferred;
- `GradingExecutionResult` object/class identity is not proof that the public execution path ran;
- S2a does not provide persistence, rollback, exactly-once execution, publication authority, or transaction semantics.

S2a freeze rule:

S2a is closed. Do not change `src/grading/execution.py` or its accepted S2a tests unless a verified defect, authority contradiction, or changed requirement requires the milestone to be explicitly reopened.

### S2b — risk/review around the frozen execution result

#### S2b-1 — deterministic risk observations — COMPLETE / FROZEN

Implementation commit:

`3f789a70443c3b9810c63b15bccb8dc4f5d889e5`

Tree:

`99758c27b9890ba7e65ad0667c71db502e6071c7`

S2b-1 consumes internal `GradingExecutionResult` + `AnswerEvidenceBundle` data and emits a versioned immutable `RiskObservationSet` only.

Profile-v1 observations are intentionally narrow:

- `OCR_CONFIDENCE_UNKNOWN` from active blocks with semantic confidence status `UNAVAILABLE`;
- `EVALUATOR_UNCERTAINTY_REPORTED` from matched rich evaluated criteria with non-empty `uncertainties`.

The extractor validates only the associations needed for safe observation attribution: submission binding, question/result continuity, exact paper-result continuity, duplicate-question rejection, rich/numerical criterion continuity, exact evidence-question coverage, unrelated-evidence isolation and deterministic ordering.

It does not:

- apply numeric OCR thresholds;
- derive risk tiers or calibrated probabilities;
- interpret arbitrary warning/reason/uncertainty strings as policy;
- emit `AUTO_CANDIDATE`, `SECOND_CHECK`, or `HUMAN_REVIEW`;
- mutate question/paper numerical results;
- execute a second evaluator;
- create workflow/job state or publication decisions;
- construct `GradeResult`.

Qualified evidence: **16/16 S2b-1 / 727/727 inherited / 743/743 full**.

#### S2b-2 — recommendation/review policy — PRODUCT-POLICY / SIGNAL-BREADTH GATE

Plan update 2026-09-22: the earlier inspection correctly rejected inventing school-specific recommendation policy in evaluator code. The higher-authority SRS assigns Gradified responsibility for confidence/routing and requires a configurable sensible platform default.

Remaining work before complete Release-1 recommendation behavior:

- define a versioned Gradified platform/default policy mechanism and explicit default behavior;
- preserve school-specific thresholds/overrides as configuration rather than hidden constants;
- expand supported risk/impact inputs beyond the deliberately narrow S2b-1 observation profile where required by the Engineering Source of Truth;
- keep any numeric threshold or auto-release setting separate from claims of calibration until held-out evidence exists;
- keep recommendation separate from workflow state and official publication.

S2b-2 implementation has not started. Do not retrofit recommendation logic into S2b-1.

### Decision gate before final rich GradeResult

Resolve criterion-level `awarded_marks` semantics for cases where question-level dependencies/gates/caps/deductions/rounding make the final score differ from the sum of criterion effects.

Until authority defines that mapping, preserve reducer-native criterion effects and question-level stage effects rather than inventing redistribution.

## Deterministic Evaluators — IN PROGRESS

### Single-select CHOICE v1 — COMPLETE / FROZEN

Contract commit:

`cdc8817ed6f370c699f1c3d272f03ea8aeafc665`

Evaluator commit:

`1fe26f959249a7f8ab9cb1acce89769996622f43`

Evaluator tree:

`1d5239434e959fcdf51eda8304a6d9b234e6c3df`

Qualified evidence:

- contract tests: **94/94**;
- pre-evaluator complete baseline: **837/837**;
- evaluator/hardening tests: **16/16**;
- post-commit complete suite: **853/853**.

Frozen scope:

- single-select only;
- canonical option IDs and exact equality;
- explicit match/mismatch criterion projections bound to the compiled scoring-authority fingerprint;
- rich `EvaluatedCriterionJudgment` output only;
- no OCR parsing, score arithmetic, risk/review logic, `GradeResult`, workflow, or publication authority.

Do not modify the frozen CHOICE contract/evaluator unless a verified defect, authority contradiction, or changed requirement requires explicit reopening.

### EXACT — DEFERRED / PREREQUISITE INSPECTION CLOSED

Decision: `DEFER_EXACT`.

The accepted Release-1 architecture includes EXACT within deterministic evaluation scope but does not establish that EXACT requires a distinct evaluator. Current authority does not provide sufficient executable semantics to implement a distinct EXACT capability without invention.

Hard semantic-contract blocker:

- admitted student-side EXACT representation is undefined;
- deterministic authoritative-answer runtime representation/binding is undefined;
- normalization/equivalence semantics, if any, are undefined;
- participation of accepted alternatives/equivalents, if any, is undefined;
- criterion-projection authority and blank/ambiguous/malformed/unsupported behavior are not sufficiently defined.

Separate BUILD-value evidence gap:

- approved/anonymized evidence has not yet established the amount and nature of distinct EXACT workload demand sufficient to justify a separate capability; this is not evidence that demand is low.

Frozen consequences:

- do not modify or reopen CHOICE merely to serve EXACT;
- CHOICE's proven binding/projection design may inform later work, but no generic abstraction extraction is authorized merely by this deferred candidate;
- do not create EXACT RED, implementation, or normalization infrastructure;
- reopen EXACT only if new authoritative, approved-workload, or verified-integration evidence materially changes a recorded defer basis.

### NUMERIC / UNIT — DEFERRED / PREREQUISITE INSPECTION CLOSED

Decision: `DEFER`.

Release-1 NUMERIC remains architecturally authorized. However, in the inspected integrated runtime state, the executable contracts and retained rubric-authoring data do not provide sufficient structured answer-domain authority to implement deterministic NUMERIC evaluation without inventing academic semantics.

Recorded `DEFER` bases:

- the inspected runtime does not currently establish a sufficiently defined admitted numeric/quantity input;
- structured expected-value/tolerance/unit/conversion authority and binding are not established for deterministic NUMERIC evaluation;
- criterion-level NUMERIC authority is not established;
- no already-authorized composition boundary was found in the inspected evaluator → S1 → B2 runtime contracts/path that would allow partial NUMERIC judgments to be combined into the complete required criterion universe for a supported question;
- approved/anonymized workload evidence has not yet bounded the minimum representative NUMERIC scope for a first implementation; this is not evidence that NUMERIC lacks Release-1 product value.

Consequences:

- do not create NUMERIC behavior-defining RED or implementation under the current executable authority;
- Numeric Profile v1 remains the frozen scoring-number/execution boundary and must not be treated as academic-answer semantics;
- do not modify frozen CHOICE, S1, B2/B3, or their accepted tests merely to make NUMERIC easier to implement;
- do not invent a generic evaluator/composition framework merely to work around the current contract-state gap;
- reopen NUMERIC only if new authoritative, runtime-contract, approved-workload, or verified-integration evidence materially changes a recorded `DEFER` basis.

### CROSS-CUTTING AUTHORITY PREREQUISITE — SELECTED

The deliberate-selection step is closed for the current batch. The selected cross-cutting prerequisite is the evaluator-facing ACTIVE question-authority boundary documented above, and it earned `BUILD`.

This does not select or authorize CHOICE expansion, EXACT, NUMERIC, semantic, math/derivation, or any other evaluator capability. Do not start another evaluator implementation merely because the shared authority boundary earned `BUILD`.

## Semantic Evaluation — OPEN

Requires provider boundary, compiled rubric, evidence contract, capability routing and representative benchmark evidence.

## Mathematical / Derivation Evaluation — OPEN

Implement only the capability subset supported by explicit contracts and benchmark data. Unsupported patterns must fail/review safely.

## Approved Reference Context — OPEN

Reference retrieval must be tenant/version scoped and record exact source provenance. Do not invent retrieval infrastructure before real backend/reference contracts are available.

## Production Provider Adapter — OPEN

Release 1 needs one real production provider adapter.

Mandatory later requirements include:

- transport-level response bounding before full body materialization;
- timeout/failure behavior;
- configured provider/model provenance and usage telemetry;
- authenticated/traceable acquisition evidence appropriate to the provider;
- no provider output becomes scoring authority directly.

## OCR & Backend Integration — OPEN

Wait for real schemas/auth/tenant behavior. Do not invent them.

## Risk / Review / Regrade / Publication — OPEN

Implement in the layer that owns workflow state and persistence. Regrade creates a new linked run/result and does not silently overwrite history.

## Reliability & Security — ONGOING / RELEASE GATE OPEN

Continue fail-closed contract/adversarial testing per capability. Do not weaken frozen boundaries to meet schedule.

## Release Validation & Calibration — OPEN

Before Release 1 production claim:

- representative rubric-generation teacher review;
- evaluator benchmark;
- real subjective school paper E2E;
- real numerical/math school paper E2E;
- cost/provider/model/latency/retry/evaluator telemetry;
- risk threshold calibration from held-out data;
- regression/adversarial release-candidate gate;
- future-engineer documentation.

## Scheduling rule

Move forward as soon as a gate closes. If time is tight, defer unsupported breadth; do not remove safety tests, identity checks, or contract verification.
