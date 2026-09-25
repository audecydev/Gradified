# Release 1 Capability Roadmap


Status date: 2026-09-25

## Foundation — COMPLETE

Project skeleton, strict contracts, deterministic decimal/numeric profile, validation/error foundations and qualified verification environment are established.

## Deterministic Scoring Kernel — COMPLETE / FROZEN

Question scoring and paper aggregation are frozen. They remain the sole numerical authorities.

Frozen anchor:

`5c32de738978739af04fa3b38f1c051cc40ba0b5`

Do not reopen without a verified defect, authority contradiction or changed requirement.

## Rubric Authoring Safety & Compilation — COMPLETE / FROZEN

Acceptance commit:

`bbaa7c528b9c1310452cba7e75b38acec51da3ed`

Release 1 still requires explicit teacher approval before ACTIVE authority.

## Rubric Generation Safety Boundary — COMPLETE / FROZEN BASELINE

### G1a deterministic composition

Commit:

`de8a0af6c637cd24179d1fdcf5c4837c514a8896`

### G1b hostile provider ingress

Commit:

`ead80e5ff85b68dfd7310e6251e4a5ad65b1aff1`

### Provider abstraction / Replay

Commit:

`1b823ae441bfba01436085cc266b578c2d7c17af`

This closes the deterministic/no-network provider boundary, including replay provenance consistency. It does not establish a production network provider or academic rubric-generation quality.

## ACTIVE Grading Authority / Evaluator Authority — COMPLETE / FROZEN

Original prerequisite decision: `BUILD` — fulfilled.

Frozen implementation identity:

- commit: `19ebbb3365af4de5fcf135bb019c05eafb03ddf1`;
- parent: `3775d5771c2fe1c5dc75538b01a068b6418e7b6b`;
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

`a831b1145f13e3eaeef29f9a0c1530da57ecbedc`

S1 proves block-grounded evidence contract/admission, evidence-reference verification, rich evaluator judgment preservation, narrow scoring projection and real deterministic question reduction.

Final complete suite: **709 passed**.

S1 is not the complete evidence subsystem.

## Synthetic E2E S2 — IN PROGRESS

S2a is closed/frozen at commit `a3577f92c6ff151a129ca96f6dea578c15cefea3` (tree `ced53127e566902050d47fe6b0a1bac921a0c9c3`). S2b-1 risk-observation extraction is closed/frozen at implementation commit `3d21e23df3e9ba8f007938dcae8c0d067b8cd47c` (tree `99758c27b9890ba7e65ad0667c71db502e6071c7`), with governance closure commit `efc22ef7120a30a2d3dd2fbcbe21ce0b543640d9`, after a **743/743** complete regression. S2b-2 recommendation behavior is not implemented; remaining work is a Gradified-owned versioned platform/default policy decision plus broader risk/impact input coverage. Downstream evaluator capabilities are not globally blocked by S2b-2.

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
- implementation commit: `a3577f92c6ff151a129ca96f6dea578c15cefea3`;
- parent / frozen S1 base: `a831b1145f13e3eaeef29f9a0c1530da57ecbedc`;
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

`3d21e23df3e9ba8f007938dcae8c0d067b8cd47c`

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

Policy boundary: school-specific recommendation policy must not be invented inside evaluator code. The SRS assigns Gradified responsibility for confidence/routing behavior and requires a configurable platform default.

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

`18f80eee43372b65f84336a2d9d0e84a13705203`

Evaluator commit:

`3f516b574378dfd99b99c3c0991278dfdfb1eaa4`

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

### NUMERIC / UNIT — N1 + N2 + N3 + N4 FROZEN

N1 authority is frozen at commit `05809a4f33f343b06ed4e77eca6ffde58fc8344b` / tree `d5410673f76b321e19ae97cc75b5aa538e11e135`.

N2 student evidence admission is frozen at commit `8c966ef4b3d93fe3c1d22ed4ff2b3f4762a2c023` / tree `bf529655c7527a12e1f005486f49f1db81448fa6` after 95/95 targeted and 1242/1242 complete qualified pre/post-commit regression.

N3 deterministic unitless comparison is frozen at commit `df89dd05a86093ded7c06565eba7456b6bdd96cc` / tree `edf2c4ee7c320b4257cd9f4187163e459a7e79f6` after 57/57 targeted and 1299/1299 complete qualified pre/post-commit regression.

N4 whole-question judgment composition is frozen at commit `56a5c2a1081e20bd8a65f9d4cf84516ce7bc7f1a` / tree `5afa6521f1a0ccea6ac3d613bce18109983f8724` after 18/18 targeted qualification and 1317/1317 complete qualified pre/post-commit regression.

N4 runs the actual N1 -> N2 -> N3 path and maps only the actual deterministic outcome to the corresponding already-approved whole-question N1 projection before unchanged S1/B2/B3 processing. It does not add score arithmetic, accept a caller-supplied N3 result as execution proof, implement UNIT semantics or create a generic merger.

After N4 freeze, the dependency/value gate selected IF1 over UNIT expansion.

### IF1 — VERSIONED EVALUATOR CAPABILITY RECORD + EXACT RESOLUTION FROZEN

IF1 is CLOSED/FROZEN at commit `54f4e43a0a9e7f3fe50a3bf7527761acb421657d` / tree `db932cc7c1f444bd4fdaf171718256da6e126161`. Qualified evidence is 87/87 targeted plus 1404/1404 complete pre/post-commit regression with a clean final tree.

The frozen scope is versioned capability-record validation and exact caller-selected record resolution only. IF1 is not question routing, execution authorization, benchmark truth, evaluator-execution proof or publication authority.

### IF2 — EXACT QUESTION-CLASSIFICATION -> CAPABILITY SELECTION DEFERRED

Decision: `DEFER` implementation because the Gradified-owned deterministic/versioned mapping from authoritative question classification to exact evaluator capability identity has not yet been specified. This is an internal routing-policy authority gap, not a reason to wait for an external backend. No caller-supplied evaluator identity, capability status, answer-shape inference or implicit default may become selection authority. No behavior-defining IF2 RED is authorized yet.

### REF-1 — REFERENCE CONTEXT MATERIALIZATION + PROVENANCE FROZEN

REF-1 is CLOSED/FROZEN at commit `409f9215d218f76a39514c43afa8a1e4858b4a92` / tree `fa2c047e5891e9930512c245ba7e8231532e21bd`. Qualified evidence is **95/95** targeted plus **1499/1499** complete pre/post-commit regression with a clean final working tree.

The frozen v1 boundary derives an exact request from `ResolvedQuestionAuthority`, rejects `ContextPolicy.DIRECT` before source invocation, invokes a configured polymorphic source for reference-aware policies, cross-checks returned spec/question/policy binding, preserves per-chunk `content + source_id + source_version + opaque provenance_hash`, enforces versioned resource bounds, and returns an independent immutable snapshot. A successful empty chunk tuple is a valid factual context result.

Configured-source exception semantics preserve Gradified-owned REF-1 contract/resource categories raised during REF-1 value construction; other adapter exceptions remain source-execution failures. Post-return validation is not blanket-wrapped.

Still open after REF-1:

- concrete database/vector/search/backend adapters and real tenant/version/provenance conformance;
- tenant/class/subject authentication/authorization implementation;
- reference approval lifecycle/authentication;
- hash-algorithm/content-hash inference or version ordering/latest selection;
- chunk identity/deduplication/ranking/search scores;
- automatic DIRECT fallback or review/publication decisions;
- reference-aware semantic evaluator execution;
- evaluator routing and execution-attempt provenance.

### CROSS-CUTTING AUTHORITY PREREQUISITE — COMPLETE / FROZEN

The evaluator-facing ACTIVE question-authority prerequisite remains implemented/frozen. A verified post-construction exposure-integrity defect was repaired/frozen at commit `d934010b3acea1bbc566d4cb7522f34a96fc3728` (parent `25a5ccdecc0f9af877c492c67db70735b369c0d0`, tree `687e4049630135bd3fd0d06db1218169df06a550`) after 99/99 targeted checks and 1037/1037 qualified complete pre/post-commit regression.

The repair closes only current authority-bearing lifecycle/approval integrity; it does not create cryptographic source authentication or historical persistence guarantees. This historical prerequisite remains frozen. Current downstream authorization is tracked in the NUMERIC section above; it does not by itself authorize any new evaluator behavior.

## Semantic Evaluation — PARTIALLY IMPLEMENTED / BROADER RELEASE-1 OPEN

### DIRECT-text semantic evaluator — COMPLETE / FROZEN SLICE

Frozen identity:

- commit: `19ebbb3365af4de5fcf135bb019c05eafb03ddf1`;
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

### NEXT MILESTONE — PRODUCTION INTEGRATION / RELEASE-GAP CLOSURE

Integrate external systems against the exact frozen capabilities and close release gaps in dependency order. Record which adapters and release evidence remain open, preserve qualified regression and Git custody, and keep reproducible verification evidence.

Each further implementation slice requires its own authority/dependency gate.

## Mathematical / Derivation Evaluation — OPEN

Implement only the capability subset supported by explicit contracts and benchmark data. Unsupported patterns must fail/review safely.

## Reference Context Materialization / Provenance — REF-1 COMPLETE / FROZEN

The backend-independent REF-1 boundary is frozen at commit `409f9215d218f76a39514c43afa8a1e4858b4a92` / tree `fa2c047e5891e9930512c245ba7e8231532e21bd`. Concrete retrieval/search/backend adapters remain open and must later prove tenant/version scope and real provenance against actual integration contracts.

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
