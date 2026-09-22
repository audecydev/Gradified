# Project State

Status date: 2026-09-22

## Current milestone

**Synthetic E2E S1, S2a, and S2b-1 remain closed/frozen. Deterministic single-select CHOICE v1 is now closed/frozen: contract commit `cdc8817ed6f370c699f1c3d272f03ea8aeafc665`; evaluator commit `1fe26f959249a7f8ab9cb1acce89769996622f43`; evaluator tree `1d5239434e959fcdf51eda8304a6d9b234e6c3df`; qualified post-commit complete regression **853/853** with a clean working tree. S2b-2 recommendation behavior, final `GradeResult`, theory/semantic evaluation, numeric/math evaluation, OCR/backend integration, and production release validation remain open.**

Current immutable S1 anchor:

- commit: `456a6248e9d28ec083e7503c3a9ad9385de47c7d`
- tree: `e9898d00850890840ebd04c284993a81d9b5cc4a`
- parent: `c48c813fb0eb64013fc7265ed0d14f64dd9d3d57`
- final targeted: **11/11**
- inherited regression: **698/698**
- full pre-commit: **709/709**
- full post-commit: **709/709**
- final working tree: clean
- committed acceptance artifact SHA-256:
  `7ff52d81346094f9c361ce9625107a4dfe1330a947f18a482f4599a3d5382f32`

The earlier S2b-2 implementation-eligibility inspection is complete, but S2b-2 remains incomplete as an executable Release-1 capability: Gradified still needs an explicit versioned platform/default policy decision and the current S2b-1 observation profile is intentionally narrower than the complete risk/impact input space described by the Engineering Source of Truth. No recommendation behavior is frozen. The immediate next task is a short prerequisite inspection of the Release-1 EXACT capability, including whether it is merely canonical-token equality already covered by CHOICE semantics or instead requires a separate normalized free-text authority/normalization contract. No S1/B2/B3/S2a/S2b-1/CHOICE frozen source or accepted-test change is authorized without a verified defect, authority contradiction, or changed requirement.

## Frozen / accepted boundaries

### Deterministic scoring kernel

Frozen anchor:

`178668b9b735ef369825c86d16db7999b8d3c784`

Question scoring and paper aggregation remain the sole numerical authorities. Do not reopen without a verified defect, authority contradiction or changed requirement.

### Rubric Authoring Safety & Compilation

Commit:

`5f3ee013bc9f732f469104a5f6c6dc151cad3402`

Final qualified evidence: **78 targeted / 519 inherited / 597 full**, selected mutation campaign **8/8 genuine kills**, exception-transparency regression green, independent review/staging audit passed.

Release 1 continues to require teacher approval before ACTIVE rubric authority.

### RubricGenerator G1a

Commit:

`a6f0388f137226fb2125a07c6f01f424bafc5d58`

Qualified evidence: **27 targeted / 597 inherited / 624 full**, including targeted checks under multiple `PYTHONHASHSEED` values.

G1a composes trusted source data with admitted untrusted proposal data into an unapproved candidate only.

### RubricGenerator G1b

Commit:

`c7a3ae3592b6ad0f6120178ddf9015e5ac10bdf0`

Verified tree:

`96cc74045d85e79bd8b8724a4d1faa7428b593b9`

Full suite at closure: **676 passed**.

Important: earlier manually transcribed G1b commit/tree values were wrong. Use only the values above.

### Provider abstraction / Replay

Commit:

`c48c813fb0eb64013fc7265ed0d14f64dd9d3d57`

Tree:

`9e6012c295e2112d8baee90b0d6cef487ac650a6`

Qualified evidence: **22 targeted / 676 inherited / 698 full**.

Replay fixtures are now provenance-consistent with configured provider/model identity. This does not provide cryptographic proof of external historical origin.

### Synthetic E2E S1

Commit:

`456a6248e9d28ec083e7503c3a9ad9385de47c7d`

S1 establishes the block-grounded evidence-verification → deterministic question-score baseline.

Key properties:

- evidence block IDs unique across the submission;
- block/question ownership preserved;
- unknown/wrong-question/crossed-out references fail closed;
- empty evidence references fail before scoring projection under the current profile;
- unavailable confidence is preserved rather than synthesized;
- rich evaluator information remains separate from the narrow scoring projection;
- only `criterion_id + selected_level` enter the frozen reducer;
- no marks/totals are calculated by evidence verification.

`VerifiedCriterionJudgments` is a non-authoritative result container; later orchestration must not trust its class identity as proof that verification ran.

### Synthetic E2E S2a — closed/frozen

Branch:

`synthetic-e2e-s2`

Implementation commit:

`61ce96d62774a78f4019c4905421324f614a7422`

Tree:

`ced53127e566902050d47fe6b0a1bac921a0c9c3`

Parent / frozen S1 base:

`456a6248e9d28ec083e7503c3a9ad9385de47c7d`

S2a implements a narrow in-memory orchestration boundary:

- `execute_grading_from_evaluations(...)` accepts pre-execution context, evidence, per-question `EvaluatedCriterionJudgment` tuples, admitted question-scoring authorities, and one resolved paper-scoring authority;
- caller-supplied `VerifiedCriterionJudgments`, `QuestionScoreResult`, and `PaperScoreResult` are not accepted as execution credentials;
- context `submission_ref` is bound to the evidence bundle;
- context `grading_spec_ref` is bound to the resolved paper authority;
- raw execution work is checked for duplicate, missing, and unexpected question IDs before question execution;
- execution is canonicalized to authoritative paper-question order;
- work question identity is bound to the question authority's rubric/policy question identity before S1/B2 execution;
- the real frozen `verify_evaluated_judgments()`, `reduce_question()`, and `aggregate_paper()` functions are called;
- rich verified judgments and numerical question results are preserved in parallel;
- S2a contains no authoritative score arithmetic and does not reimplement B3 rubric/policy/result admission;
- downstream S1/B2/B3 failures remain native rather than being wrapped as S2 admission failures;
- a successful `execute_grading_from_evaluations(...)` return occurs only after every expected question has completed S1+B2 and B3 aggregation has succeeded.

Final qualified evidence:

- inherited S1 regression: **709/709**;
- original S2a contract: **10/10**;
- acceptance-hardening batch: **8/8**;
- all S2a tests: **18/18**;
- complete suite: **727/727**;
- post-code/test-staging complete suite: **727/727**;
- final governance-inclusive staged suite: **727/727**;
- final staged tree / committed tree: `ced53127e566902050d47fe6b0a1bac921a0c9c3`;
- final staged acceptance patch SHA-256: `0015fdb2b26ec2667d94cdce00f6104750d497cc42f467221161f112bf41c56a`;
- implementation commit: `61ce96d62774a78f4019c4905421324f614a7422`;
- implementation parent: `456a6248e9d28ec083e7503c3a9ad9385de47c7d`;
- post-commit complete suite: **727/727**;
- post-commit working tree: clean;
- historical code/test-only candidate tree: `804a28a1041b264ad150638a3267d6cf69802354`;
- historical code/test-only staged patch SHA-256: `1bbf993078166ee4b07e627cbaf30927bd559b527ee5b5a91806e0ab5d5e19eb`;
- `src/grading/execution.py` blob: `d6d8ef44b8b9df49fee9f9d9fd6a3396aaea1711`;
- acceptance-test blob: `4fd1091d3c89a5fb42dec770e21b7f077e4f652c`;
- S2a contract-test blob: `fd96c6c7ba6e26f1482f89d2aea14a10ffe9329e`;
- frozen S1/B2/B3/rubric tracked source remained unchanged during the S2a source/test candidate audit.

The code/test-only tree/hash above are retained as intermediate forensic history. The authoritative frozen S2a implementation identity is commit `61ce96d62774a78f4019c4905421324f614a7422`, tree `ced53127e566902050d47fe6b0a1bac921a0c9c3`.


### Synthetic E2E S2b-1 — risk observations closed/frozen

Branch:

`synthetic-e2e-s2b`

Implementation commit:

`3f789a70443c3b9810c63b15bccb8dc4f5d889e5`

Governance closure commit:

`5838eac38a7a9df256a8ed0d5880a80e76b39128`

Tree:

`99758c27b9890ba7e65ad0667c71db502e6071c7`

Parent / frozen S2a governance anchor:

`ca2c27b7d2958eb8f9e170120ad2f758e0f5bc61`

S2b-1 implements deterministic extraction of a deliberately narrow, versioned risk-observation profile from supplied internal execution/evidence data without making a review recommendation.

Supported observation codes in profile v1:

- `OCR_CONFIDENCE_UNKNOWN`, emitted only from active evidence blocks whose semantic `confidence_status` is `UNAVAILABLE`;
- `EVALUATOR_UNCERTAINTY_REPORTED`, emitted only when the matched rich evaluated criterion judgment has a non-empty `uncertainties` tuple.

S2b-1 admission/continuity guarantees include:

- execution `submission_ref` binds to the supplied evidence bundle;
- each rich verified record's `submission_ref` binds to execution context;
- rich verified question identity binds to the numerical question result;
- execution question/result order and numerical question results bind exactly to `PaperScoreResult.question_results`;
- duplicate execution questions are rejected;
- scoring-judgment and numerical criterion-effect universes are exact, duplicate-free, and agree on `selected_level` by `criterion_id`;
- every executed question has exactly one matching `QuestionEvidence`;
- unrelated evidence questions are ignored;
- crossed-out evidence remains inactive under the current profile;
- observation ordering is deterministic: execution-question order, then evidence-block order for OCR observations, then numerical criterion-effect order for evaluator observations.

Final qualified evidence on Windows / CPython 3.11.9:

- S2b-1 targeted/acceptance: **16/16**;
- inherited frozen suite: **727/727**;
- complete suite: **743/743**;
- frozen S2a diff check: clean before commit;
- implementation commit: `3f789a70443c3b9810c63b15bccb8dc4f5d889e5`;
- implementation parent: `ca2c27b7d2958eb8f9e170120ad2f758e0f5bc61`;
- implementation tree: `99758c27b9890ba7e65ad0667c71db502e6071c7`;
- pre-test post-commit working tree: clean.

S2b-1 non-claims:

- no numeric risk score, qualitative risk tier, review recommendation, workflow state, second-evaluator action, publication decision, or `GradeResult` is produced;
- numeric OCR confidence is not thresholded locally, and no school/platform threshold is invented;
- free-form evidence warnings, evaluator `reason_codes`, and uncertainty text are not interpreted as policy/recommendation authority;
- `grading_run_id`, `submission_ref`, question IDs, criterion IDs, and evidence-block IDs provide correlation/contextual traceability, not authentication credentials;
- S2b-1 cannot prove that the separately supplied `AnswerEvidenceBundle` is byte-for-byte or semantically the exact immutable artifact consumed by the earlier S2a execution; stronger cross-stage artifact identity requires an upstream workflow/artifact identity contract;
- S2b-1 consumes internal domain values and does not treat Python object/class identity as proof of execution provenance;
- criterion-level `awarded_marks` remains unresolved and untouched.

## Current architecture boundary

Frozen numerical path:

```text
QuestionScoringAuthority + CriterionJudgment[]
        ↓
reduce_question()
        ↓
QuestionScoreResult

ResolvedPaperScoringAuthority + QuestionScoreResult[]
        ↓
aggregate_paper()
        ↓
PaperScoreResult
```

B2/B3 answer:

> What deterministic numerical result follows from these supplied scoring inputs?

S2 must answer:

> Did this S2 execution path coherently bind the execution inputs it can verify, invoke the real S1 verifier and frozen B2/B3 numerical path, and preserve the resulting rich/numerical records without granting workflow/publication authority to the numerical kernel?

Workflow identity stays outside the frozen B2/B3 numerical contracts.

### Deterministic single-select CHOICE v1 — closed/frozen

Branch:

`deterministic-choice-v1`

Contract commit:

`cdc8817ed6f370c699f1c3d272f03ea8aeafc665`

Contract tree:

`736c4edee091d797a2faa971bb29c6ddff140644`

Evaluator commit:

`1fe26f959249a7f8ab9cb1acce89769996622f43`

Evaluator tree:

`1d5239434e959fcdf51eda8304a6d9b234e6c3df`

Evaluator parent / frozen contract anchor:

`cdc8817ed6f370c699f1c3d272f03ea8aeafc665`

CHOICE v1 implements deterministic semantic evaluation for one deliberately narrow capability:

- single-select only;
- canonical opaque option IDs;
- exact option-ID equality only;
- admitted `ChoiceEvaluationAuthority` bound by the existing compiled scoring-authority fingerprint;
- complete match/mismatch projections across the full scoring criterion universe;
- rich `EvaluatedCriterionJudgment` output in scoring-rubric order;
- canonical evidence references are carried through for later S1 verification;
- known-but-wrong admitted option and unsupported/unknown option remain distinct outcomes;
- malformed public top-level inputs fail through explicit CHOICE-domain errors rather than leaking `AttributeError`.

Qualified Windows / CPython 3.11.9 evidence:

- contract tests: **94/94**;
- pre-evaluator complete baseline: **837/837**;
- evaluator/hardening tests: **16/16**;
- complete post-commit suite: **853/853**;
- evaluator staged tree == committed tree: `1d5239434e959fcdf51eda8304a6d9b234e6c3df`;
- post-commit working tree: clean.

CHOICE v1 non-claims:

- consumes already-admitted canonical selection data; it does not parse OCR or perform fuzzy text normalization;
- carries evidence references but does not verify evidence relationships; existing S1 owns that verification;
- produces semantic criterion judgments only; B2 remains the sole question-level numerical scoring authority;
- performs no mark arithmetic, negative-marking logic, risk/review recommendation, workflow transition, publication decision, or `GradeResult` construction;
- does not authenticate ACTIVE grading-spec provenance, scoring-authority lifecycle origin, or evaluator-attempt/run provenance;
- does not implement blank/no-selection, ambiguous extraction, multi-select, ranking, free-text EXACT, numeric/unit, semantic/theory, or mathematical-derivation evaluation.


## Current blockers / open decisions

### S2 execution integrity

S2a is closed/frozen. Its functional/adversarial acceptance, final staged-tree audit, commit identity, clean post-commit state, and 727/727 post-commit regression are complete. S2b-1 is also closed/frozen. S2b-2 recommendation implementation has not started; remaining work includes an explicit Gradified-owned versioned policy/default decision plus the broader risk/impact signal coverage required by the Engineering Source of Truth.

S2a establishes only the relationships supported by current authority:

- `submission_ref` is semantically bound to `AnswerEvidenceBundle.submission_ref`;
- `grading_spec_ref` is semantically bound to `ResolvedPaperScoringAuthority.grading_spec_ref`;
- execution-work `question_id` is bound to the question authority's rubric/policy question identity;
- `grading_run_id` and `exam_ref` are validated/preserved context values but are not authenticated against an upstream workflow authority;
- expected execution work comes from the resolved paper composition;
- rich and numerical outputs remain parallel and are not positionally merged.

### S2b-2 recommendation/review policy — product-policy / signal-breadth gate

The earlier eligibility inspection correctly rejected inventing school-specific thresholds or recommendation mappings inside implementation code. The higher-authority SRS also assigns Gradified responsibility for confidence/routing behavior and requires a sensible configurable platform default.

Current state:

- S2b-2 implementation has **not started** and no recommendation behavior is frozen;
- a versioned Gradified platform/default policy decision is still required;
- school-specific overrides remain configuration, not hidden code constants;
- the current S2b-1 observation profile is intentionally narrow and does not yet cover the full risk/impact input space described by the Engineering Source of Truth;
- numeric thresholds or auto-release settings must not be presented as calibrated quality claims without held-out evidence.

Keep separate:

- numerical outcome;
- S2b-1 observations;
- future risk/review recommendation;
- grading job/result workflow status;
- official backend publication.

Downstream Release-1 capabilities are not globally blocked by S2b-2.

### Criterion-level `awarded_marks`

The final rich `GradeResult` expects criterion-level awarded marks, but question-level gates/caps/deductions/rounding can make `final_score` differ from the sum of criterion effects.

No authoritative redistribution rule has yet been verified. Do not invent one. Preserve reducer-native effects and final score until this is resolved through an explicit design/ADR decision.

## Important non-claims

The current project does not yet establish:

- executable S2b-2 recommendation policy or calibrated recommendation mapping;
- final candidate `GradeResult`;
- deterministic risk/review recommendation engine (S2b-1 observations exist, but recommendation policy is not yet implemented);
- whole-answer `answer_scope_ref` verification;
- evidence-type compatibility;
- real OCR/backend integration;
- approved reference retrieval;
- one production live-provider adapter with transport-level bounding;
- production evaluator quality beyond the frozen narrow CHOICE v1 capability; theory/semantic and numeric/math evaluator quality remain unestablished;
- supported math/derivation evaluator benchmark;
- review/regrade persistence and official publication;
- evaluator-attempt provenance binding supplied judgments to a specific run/spec at judgment-creation time;
- authentication or semantic-origin proof for supplied `QuestionScoringAuthority` / `ResolvedPaperScoringAuthority`; S2a treats them as already-admitted trusted upstream domain inputs;
- global uniqueness/authentication of `grading_run_id` or semantic ownership of `exam_ref`;
- transactional rollback, exactly-once execution, persistence atomicity, or publication;
- `GradingExecutionResult` class/object identity as proof that `execute_grading_from_evaluations(...)` ran;
- representative teacher-reviewed rubric-generation quality;
- real subjective and numerical/math school-paper Release-1 E2E acceptance.

## Verification status

Frozen S1 baseline: **709 passed** at commit `456a624...`.

S2a qualified evidence on Windows / CPython 3.11.9:

- clean S2 baseline from exact S1 anchor: **709/709**;
- causal GREEN1: **4 passed / 6 failed** with the six failures exposing the intended missing context/work/binding admission boundaries;
- GREEN2 inherited regression: **709/709**;
- GREEN2 original S2a contract: **10/10**;
- GREEN2 complete suite before acceptance hardening: **719/719**;
- acceptance-hardening: **8/8**;
- all S2a tests: **18/18**;
- complete suite: **727/727**;
- post-code/test-staging complete suite: **727/727**;
- final governance-inclusive staged suite: **727/727**;
- implementation commit: `61ce96d62774a78f4019c4905421324f614a7422`;
- implementation tree: `ced53127e566902050d47fe6b0a1bac921a0c9c3`;
- final staged acceptance patch SHA-256: `0015fdb2b26ec2667d94cdce00f6104750d497cc42f467221161f112bf41c56a`;
- post-commit complete suite: **727/727**;
- post-commit working tree: clean;
- final code/test source audit found no numerical-authority duplication, no exception wrapping, no new dependency framework, and no frozen-source modification.


Deterministic CHOICE v1 qualified evidence on Windows / CPython 3.11.9:

- semantic/executable contract commit: `cdc8817ed6f370c699f1c3d272f03ea8aeafc665`;
- contract tree: `736c4edee091d797a2faa971bb29c6ddff140644`;
- contract tests: **94/94**;
- pre-evaluator complete baseline: **837/837**;
- evaluator causal RED: **12 failed / 1 passed** at the intentional behavior stub;
- initial evaluator GREEN: **13/13**;
- hostile public-boundary hardening RED: **3 failed / 13 passed**;
- hardened evaluator targeted: **16/16**;
- evaluator implementation commit: `1fe26f959249a7f8ab9cb1acce89769996622f43`;
- evaluator tree: `1d5239434e959fcdf51eda8304a6d9b234e6c3df`;
- post-commit complete suite: **853/853**;
- post-commit working tree: clean.

S1's earlier empty-evidence defect remains the standing example that full-suite green does not replace hostile source review.

## Next task

Perform a short authority/dependency/prerequisite inspection of **Release-1 EXACT evaluation**.

The inspection must first determine whether authoritative Release-1 EXACT means:

1. canonical token/string equality that can reuse the frozen CHOICE comparison/binding pattern without duplicating evaluator code; or
2. normalized free-text exact-answer evaluation that requires a separate accepted-answer and normalization/equivalence contract.

Before behavior-defining RED, establish:

- the exact admitted student value;
- the exact authoritative answer value(s);
- normalization/equivalence semantics, if any;
- outcome-to-rich-judgment projection ownership;
- scoring-authority binding;
- unsupported/invalid behavior;
- real composition through the frozen S1 → B2 runtime.

Do not implement EXACT merely because it appears next in the roadmap. If the semantics are not sufficiently specified, record the blocker promptly and inspect the next candidate rather than inventing normalization rules.

Do not modify S1, B2, B3, frozen S2a/S2b-1, or frozen CHOICE merely to make EXACT easier to implement.

## Documentation rule

Update `PROJECT_STATE.md` at subsystem milestone closure, material blocker/assumption change, and before implementation-chat handoff. Do not use it as a turn-by-turn diary.

`IMPLEMENTATION_PLAN.md` records the frozen S2/CHOICE milestones and the next candidate-capability sequence.

`TESTING.md` records the qualified S2 and deterministic CHOICE verification/freeze evidence.

Do not alter the SRS/Engineering Source of Truth merely to report implementation progress.
