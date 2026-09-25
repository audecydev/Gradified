# Release 1 Capability Roadmap

Status date: 2026-09-25

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

## ACTIVE Grading Authority / Evaluator Authority — COMPLETE / FROZEN

Original prerequisite decision: `BUILD` — fulfilled.

Frozen implementation identity:

- commit: `82588a4df5d77f9b88dac3b19c34728dc0ad697e`;
- parent: `7ea8fbb88e2e4edd83b7ca80f14b53eddcff601f`;
- tree: `c0d68f97433cefb4f3d06fd86fb10b2db6215413`.

Qualified closure evidence:

- authority/semantic/composition targeted gate: **155/155**;
- related regression: **26/26**;
- complete pre-commit regression: **1008/1008**;
- complete post-commit regression: **1008/1008**;
- post-commit working tree: clean.

Purpose:

Implement the smallest immutable, read-only evaluator-facing ACTIVE question-authority boundary required by the accepted architecture. This is a cross-cutting authority prerequisite, not an evaluator capability and not a second lifecycle.

Frozen authority design constraints:

- consume only legitimately admitted ACTIVE question/spec context, the existing teacher-approved ACTIVE rubric authority, and the existing reducer-facing scoring authority;
- preserve exact binding among grading-spec identity, question identity, rubric authority and the existing reducer-facing scoring authority;
- expose a read-only immutable projection/view only; do not add independent authoring, approval, activation, retirement or mutation semantics;
- do not duplicate or implement a second GradingSpec/rubric lifecycle; the accepted architecture assigns the authoritative GradingSpec lifecycle to the trusted workflow/spec boundary;
- bind academic/question-context inputs to the exact ACTIVE authority by contained immutable values or explicit immutable/versioned references; never fall back to inferred, stale, `latest`, or unbound context;
- keep evaluator/provider/runtime configuration outside academic authority and record its exact identity against evaluation-attempt provenance in the later layer that owns attempts; provenance is audit evidence, not a deterministic-replay guarantee;
- allow approved reference material to establish academic validity only when the ACTIVE context policy permits it; reference material cannot independently create criteria, marks, levels, caps, deductions or other scoring consequences.

Original authority-only `BUILD` exclusions, preserved as historical scope constraints:

- no capability registry/router implementation or capability-status state in the new authority boundary;
- no evaluator implementation and no semantic/math composition framework;
- no production-provider, OCR, backend, retrieval, risk/review, `GradeResult`, persistence or publication implementation;
- no EXACT normalization/equivalence semantics;
- no NUMERIC expected-value/tolerance/unit/conversion semantics;
- no mathematical-equivalence or derivation semantics not already authorized;
- no change to S1, B2/B3, CHOICE, Numeric Profile v1, or their accepted tests/behavior merely to serve this boundary.

Closure discipline:

- **IMPLEMENTED / CLOSED / FROZEN** at the identity above;
- the original authority-only `BUILD` exclusions remain historical scope constraints for that decision;
- the later DIRECT-text semantic-evaluator slice was separately scoped, adversarially hardened and frozen in the same acceptance commit/tree; it does not retroactively broaden the original authority-only decision;
- no later capability may treat the ACTIVE-authority object itself as capability-routing, workflow, publication or provenance authority.

At this historical ACTIVE-boundary closure, EXACT remained `DEFER_EXACT` and NUMERIC remained `DEFER`; the later N1 authority decision below supersedes only the NUMERIC prerequisite status and does not broaden this historical scope.

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

### NUMERIC / UNIT — N1 + N2 + N3 FROZEN; N4 WHOLE-QUESTION COMPOSITION BUILD AUTHORIZED

N1 authority is frozen at commit `f28d11d1a20a25944f0d3dcc9320ea0149fbe46f` / tree `d5410673f76b321e19ae97cc75b5aa538e11e135`.

N2 student evidence admission is frozen at commit `455d7cf1b20c2479fd9d702cb2f4a9c140672559` / tree `bf529655c7527a12e1f005486f49f1db81448fa6` after 95/95 targeted and 1242/1242 complete qualified pre/post-commit regression.

N3 deterministic unitless comparison is frozen at commit `490c94751ea330ff31b298477f2507500d75bef8` / tree `edf2c4ee7c320b4257cd9f4187163e459a7e79f6` after 57/57 targeted and 1299/1299 complete qualified pre/post-commit regression.

N4 prerequisite decision: `BUILD` for the smallest whole-question NUMERIC judgment-composition boundary.

N4 objective:

Run the actual frozen N1 resolver, N2 scalar admission and N3 deterministic evaluator, then map the resulting `SATISFIED | NOT_SATISFIED` state to the corresponding already-approved complete N1 criterion projection and emit existing `EvaluatedCriterionJudgment` values for unchanged S1/B2/B3 processing.

N4 required v1 behavior:

- no caller-supplied N3 result input; the trusted N1 -> N2 -> N3 chain executes inside the N4 boundary;
- exact `NOT_AUTHORIZED` remains non-academic and cannot become a not-satisfied projection;
- exact projection selection only: satisfied -> `satisfied_projection`, not-satisfied -> `not_satisfied_projection`;
- exact approved criterion order and level IDs are inherited from the N1 resolver's current ACTIVE/scoring cross-check;
- every emitted judgment references the exact admitted N2 evidence block;
- deterministic evaluator metadata/reason codes contain no score or hidden academic rule;
- technical/source/admission/binding failures propagate as failures rather than becoming judgments;
- integration tests must prove the resulting judgments pass the existing S1 evidence verifier and existing B2/B3 scoring path without modifying frozen scoring code.

N4 exclusions:

- no generic partial-judgment merger;
- no mixed NUMERIC + method/semantic composition;
- no UNIT/conversion or broader numeric grammar;
- no scoring arithmetic, marks, review/release policy or publication;
- no capability registry/routing framework;
- no claim of benchmark/calibration or production auto-release quality.

N4 sequence:

contract closure + governance checkpoint
→ causal RED after valid N1/N2/N3 prerequisites
→ minimal GREEN
→ hostile provenance/not-authorized/failure hardening
→ real N4 -> S1 -> B2/B3 integration tests
→ complete regression
→ exact source/staging/tree custody
→ commit + post-commit complete regression
→ freeze N4

After N4 freezes, perform a fresh dependency/value gate. Do not automatically broaden to UNIT or mixed composition. Production integration slices may have higher immediate delivery value.

### CROSS-CUTTING AUTHORITY PREREQUISITE — COMPLETE / FROZEN

The evaluator-facing ACTIVE question-authority prerequisite remains implemented/frozen. A verified post-construction exposure-integrity defect was repaired/frozen at commit `ba951af9081a5459464f4985074f5f113e62ad6b` (parent `f8efd180611246d3a2c847b26316e5dadbabee1a`, tree `687e4049630135bd3fd0d06db1218169df06a550`) after 99/99 targeted checks and 1037/1037 qualified complete pre/post-commit regression.

The repair closes only current authority-bearing lifecycle/approval integrity; it does not create cryptographic source authentication or historical persistence guarantees. This historical prerequisite remains frozen. Current downstream authorization is tracked in the NUMERIC section above; it does not by itself authorize any new evaluator behavior.

## Semantic Evaluation — PARTIALLY IMPLEMENTED / BROADER RELEASE-1 OPEN

### DIRECT-text semantic evaluator — COMPLETE / FROZEN SLICE

Frozen identity:

- commit: `82588a4df5d77f9b88dac3b19c34728dc0ad697e`;
- tree: `c0d68f97433cefb4f3d06fd86fb10b2db6215413`.

Qualified evidence:

- authority/semantic/composition targeted gate: **155/155**;
- related regression: **26/26**;
- complete pre-commit regression: **1008/1008**;
- complete post-commit regression: **1008/1008**;
- post-commit working tree: clean.

Frozen scope:

- `ContextPolicy.DIRECT` only;
- ACTIVE authority + model-answer + text-evidence semantic request construction;
- strict bounded provider-response ingress and frozen criterion validation;
- criterion-ID-based rich-field reassociation;
- system-owned evaluator metadata;
- real semantic → S1 → B2/B3 composition with no model-owned numerical marks.

Broader semantic Release-1 work remains open and still requires production provider integration, capability routing/validation, representative semantic benchmark evidence, supported non-DIRECT context policies where authorized, and real subjective school-paper E2E.

Do not interpret this slice as academic-quality validation, production-provider closure, retry/idempotency closure, OCR/backend integration, or review/publication authority.

### NEXT CANDIDATE — N4 WHOLE-QUESTION NUMERIC COMPOSITION RED AUTHORIZED

N4 is the selected next capability gate on top of frozen N1/N2/N3. Begin causal RED for the bounded judgment-composition contract above.

Do not start UNIT, mixed partial composition, generic routing or broader integration work inside the N4 batch. If the frozen prerequisites expose a concrete contradiction, stop on that contradiction rather than weakening fail-closed behavior.

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
