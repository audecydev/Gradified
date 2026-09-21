# Release 1 Capability Roadmap

Status date: 2026-09-21

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

## Synthetic E2E S1 — COMPLETE / FROZEN

Commit:

`456a6248e9d28ec083e7503c3a9ad9385de47c7d`

S1 proves block-grounded evidence contract/admission, evidence-reference verification, rich evaluator judgment preservation, narrow scoring projection and real deterministic question reduction.

Final complete suite: **709 passed**.

S1 is not the complete evidence subsystem.

## Synthetic E2E S2 — IN PROGRESS

S2a is closed/frozen at commit `61ce96d62774a78f4019c4905421324f614a7422` (tree `ced53127e566902050d47fe6b0a1bac921a0c9c3`). S2b-1 risk-observation extraction is closed/frozen at implementation commit `3f789a70443c3b9810c63b15bccb8dc4f5d889e5` (tree `99758c27b9890ba7e65ad0667c71db502e6071c7`), with governance closure commit `5838eac38a7a9df256a8ed0d5880a80e76b39128`, after a **743/743** complete regression. The later S2b-2 recommendation-policy slice is blocked on missing executable policy authority; downstream capabilities require individual dependency inspection rather than a blanket S2b-2 prerequisite.

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

#### S2b-2 — recommendation/review policy — ELIGIBILITY INSPECTION COMPLETE / BLOCKED

The implementation-eligibility inspection is complete.

Routing intent is authoritative, but executable recommendation-policy authority is insufficient. S2b-2 implementation has **not started**, and behavior-defining RED is **not authorized**.

The missing prerequisite is broader than threshold values. It includes:

- admitted release-policy identity/version and binding to the grading run/spec;
- approved school/platform threshold values and default-policy semantics;
- confidence/risk derivation and aggregation;
- impact derivation;
- deterministic recommendation mapping;
- explicit `SECOND_CHECK` semantics;
- precedence/override/conflict behavior.

Do not invent school thresholds, platform defaults, qualitative risk derivation, or `AUTO_CANDIDATE | SECOND_CHECK | HUMAN_REVIEW` mapping.

Keep separate:

- numerical outcome;
- S2b-1 observations;
- future risk/review recommendation;
- grading job/result workflow status;
- official backend publication.

Do not create a partial `GradeResult` merely to bypass unresolved schema semantics.

### Decision gate before final rich GradeResult

Resolve criterion-level `awarded_marks` semantics for cases where question-level dependencies/gates/caps/deductions/rounding make the final score differ from the sum of criterion effects.

Until authority defines that mapping, preserve reducer-native criterion effects and question-level stage effects rather than inventing redistribution.

## Deterministic Evaluators — CANDIDATE AREA / PREREQUISITE INSPECTION REQUIRED

Roadmap order does not authorize deterministic-evaluator RED or implementation.

Before selecting an evaluator capability, establish whether that capability depends on blocked S2b-2 or whether frozen S2a is sufficient, and verify that the capability's own behavior is authoritative enough to define observable RED.

For evaluator candidates, use the actual frozen runtime boundary:

- S1 accepts rich `EvaluatedCriterionJudgment` values;
- runtime `CriterionJudgment` is only the narrow post-verification scoring projection;
- S1 verifies evidence relationships but does not independently establish semantic correctness of `selected_level`;
- semantic outcome-to-rich-judgment ownership must therefore be explicit in the evaluator capability or an admitted projection boundary.

Do not infer official answers, answer types, normalization, criterion-level mappings, numeric tolerances, units, or unsupported-input behavior from scoring marks or authoring-generation provenance.

If one deterministic capability passes its authority/dependency/prerequisite gate, implement only that smallest validated slice.

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
