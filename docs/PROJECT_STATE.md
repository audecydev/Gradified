# Project State

Status date: 2026-09-25

## Current milestone

**Synthetic E2E S1, S2a, and S2b-1 remain closed/frozen. Deterministic single-select CHOICE v1 remains closed/frozen at its historical **853/853** post-commit baseline. Release-1 EXACT remains closed at `DEFER_EXACT`. The evaluator-facing ACTIVE question-authority boundary and DIRECT-text semantic slice remain frozen; the verified ACTIVE-exposure integrity defect remains repaired/frozen at commit `ba951af9081a5459464f4985074f5f113e62ad6b`. NUMERIC N1 academic authority remains CLOSED/FROZEN at commit `f28d11d1a20a25944f0d3dcc9320ea0149fbe46f` / tree `d5410673f76b321e19ae97cc75b5aa538e11e135`. NUMERIC N2 student evidence admission is now CLOSED/FROZEN at commit `455d7cf1b20c2479fd9d702cb2f4a9c140672559` / tree `bf529655c7527a12e1f005486f49f1db81448fa6`, with **95/95** targeted hostile qualification and **1242/1242** complete qualified pre/post-commit regression. A bounded N3 deterministic unitless scalar comparison primitive now earns `BUILD`; N4 composition, UNIT support, production NUMERIC quality and auto-release remain unauthorized.**

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

The earlier S2b-2 implementation-eligibility inspection is complete, but S2b-2 remains incomplete as an executable Release-1 capability: Gradified still needs an explicit versioned platform/default policy decision and the current S2b-1 observation profile is intentionally narrower than the complete risk/impact input space described by the Engineering Source of Truth. No recommendation behavior is frozen. Release-1 EXACT remains closed with `DEFER_EXACT`. NUMERIC N1 remains frozen and supplies the approved unitless scalar academic-authority side. N2 is now frozen and supplies one conservative admitted unitless finite-decimal student observation with evidence provenance. N3 now earns `BUILD` for deterministic execution of only the already-approved N1 `EXACT` and inclusive `ABSOLUTE_TOLERANCE` conditions against the already-admitted N2 scalar. N4, UNIT semantics and production-readiness claims remain gated. Representative workload evidence remains required for parser/evaluator breadth, benchmark coverage and production-quality claims. Frozen CHOICE, S1, B2/B3, DIRECT, G1 and scoring Numeric Profile v1 remain unchanged. No frozen source or accepted-test change is authorized without a verified defect, authority contradiction, or changed requirement.

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

### ACTIVE Grading Authority / Evaluator Authority — COMPLETE / FROZEN

Original prerequisite decision: `BUILD` — fulfilled.

Status: **IMPLEMENTED / CLOSED / FROZEN**.

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

Original authorized authority scope, preserved as frozen boundary constraints:

- implement only the smallest immutable, read-only evaluator-facing ACTIVE question-authority boundary required by the accepted architecture;
- the boundary must resolve legitimately admitted question/spec context together with the existing teacher-approved ACTIVE rubric and preserve exact binding among grading-spec identity, question identity, rubric authority and the existing reducer-facing scoring authority;
- the evaluator-facing boundary is a projection/view only and must have no independent authoring, approval, activation, retirement or mutation lifecycle; the accepted architecture assigns the authoritative GradingSpec lifecycle to the trusted workflow/spec boundary; this batch does not implement or duplicate that lifecycle;
- academic/question-context inputs used by grading must be contained in, or immutably version-bound to, the exact ACTIVE GradingSpec authority; evaluator/provider/runtime configuration remains separate from academic authority and must later be recorded against evaluation-attempt provenance where applicable; provenance does not itself guarantee deterministic replay;
- approved reference material may establish academic validity only where the ACTIVE context policy permits its use; reference material does not independently create criteria, marks, levels, caps, deductions or other scoring consequences;
- missing required authority must fail safely; no implicit `latest`, stale, inferred, or unbound context fallback is authorized.

Original authority-only `BUILD` exclusions, preserved as historical scope constraints:

- a second GradingSpec or rubric lifecycle;
- capability-registry status or routing decisions inside academic authority;
- evaluator implementation, semantic/math composition, provider/runtime implementation, student-evidence changes, risk/review state, or scoring-result changes;
- EXACT normalization, NUMERIC tolerance/unit/conversion rules, mathematical-equivalence semantics, or any other academic semantics not already authorized;
- changes to frozen S1, B2/B3, CHOICE, Numeric Profile v1, or their accepted behavior/tests merely to make this boundary easier to implement.

EXACT remains `DEFER_EXACT`. The authority boundary exists and remains frozen. The verified post-construction ACTIVE-exposure integrity defect was later repaired at commit `ba951af9081a5459464f4985074f5f113e62ad6b` without broadening the original authority-only scope. The repair re-establishes current authority-bearing lifecycle/approval integrity before scoring-authority exposure; it does not claim cryptographic authentication or historical backend immutability. NUMERIC N1 and N2 now have separately authorized bounded contracts; N3 deterministic comparison is the currently authorized BUILD candidate, while N4/UNIT remain gated.

#### ACTIVE exposure integrity repair — CLOSED / FROZEN

- commit: `ba951af9081a5459464f4985074f5f113e62ad6b`;
- parent: `f8efd180611246d3a2c847b26316e5dadbabee1a`;
- tree: `687e4049630135bd3fd0d06db1218169df06a550`;
- candidate/committed patch SHA-256: `f9489d737593679e0accb7cc2e2b11d4500e53c7ff9292ebbb91434658ffe414`;
- qualified environment: Windows x64 / CPython 3.11.9, pytest 9.1.1, hypothesis 6.167.1, clean `pip check`;
- targeted integrity/hardening campaign: **99/99**;
- qualified complete pre-commit regression: **1037/1037**;
- qualified complete post-commit regression: **1037/1037**;
- post-commit working tree: clean.

The repair is intentionally limited to current authority-bearing ACTIVE lifecycle/approval integrity. Compilation-time diagnostic/resource provenance that does not participate in the exposed scoring authority is not reauthenticated at grading-time exposure.

### DIRECT-text semantic evaluator — COMPLETE / FROZEN SLICE

Frozen in the same acceptance commit/tree above.

Frozen scope:

- `ContextPolicy.DIRECT` only;
- composition-owned model-answer source, semantic provider, limits and evaluator identity;
- exact grading-spec/submission/question binding before provider execution;
- ACTIVE TEXT evidence projection with crossed-out isolation and fail-closed rejection of unsupported/uncertain evidence for this v1 slice;
- structured semantic request containing academic context but no score/mark arithmetic authority;
- strict bounded raw-byte/UTF-8/JSON/schema ingress for provider output;
- frozen criterion-universe validation plus criterion-ID-based rich-field reassociation;
- system-owned `EvaluatedCriterionJudgment` metadata and attempt-bound `SemanticEvaluationResult`;
- real DIRECT semantic → S1 evidence verification → frozen B2 question scoring → frozen B3 paper aggregation composition.

Frozen-slice non-claims:

- no production-provider academic-quality claim or production network-adapter closure;
- no semantic benchmark or real subjective school-paper E2E claim;
- no capability-registry/routing completion or answer-type/language validation claim;
- no `DIRECT_PLUS_REFERENCE`, `HYBRID_RETRIEVAL`, or `REFERENCE_ONLY` support;
- no OCR/backend integration, retry/idempotency/exactly-once guarantee, risk/review recommendation, workflow transition or publication authority;
- no claim that broader Release-1 semantic/theory grading is complete.

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

### Release-1 EXACT — prerequisite inspection closed / deferred

Decision: `DEFER_EXACT`.

The accepted Release-1 architecture includes EXACT within deterministic evaluation scope but does not establish that EXACT requires a distinct evaluator. Current authority does not provide sufficient executable semantics to implement a distinct EXACT capability without invention.

Hard semantic-contract blocker:

- the admitted student-side EXACT representation is not defined;
- the deterministic authoritative-answer runtime representation and binding are not defined;
- applicable normalization/equivalence semantics, if any, are not defined;
- participation of alternative accepted answers/equivalents, if any, is not defined;
- criterion-projection authority is not defined for a distinct EXACT path;
- blank/ambiguous/malformed/unsupported behavior is not sufficiently defined.

Separate BUILD-value evidence gap:

- approved/anonymized workload evidence has not yet established the amount and nature of distinct EXACT demand sufficient to justify a separate capability; this is not evidence that demand is low.

Freeze consequences:

- frozen CHOICE remains unchanged;
- CHOICE's proven authority-binding/projection design may inform a future capability, but no CHOICE semantic extension, refactor, or generic abstraction extraction is authorized merely for EXACT;
- no EXACT RED, implementation, or normalization framework is authorized;
- reopen EXACT only when new authoritative, approved-workload, or verified-integration evidence materially changes a recorded `DEFER_EXACT` basis.


### Release-1 NUMERIC / UNIT — N1 + N2 frozen; N3 deterministic comparison BUILD authorized

N1 authority decision: `CLOSED / FROZEN`.

Frozen N1 identity and qualification:

- implementation commit: `f28d11d1a20a25944f0d3dcc9320ea0149fbe46f`;
- committed tree: `d5410673f76b321e19ae97cc75b5aa538e11e135`;
- targeted N1 authority + hostile qualification: **110/110**;
- complete qualified pre/post-commit regression: **1147/1147**.

N2 student evidence-admission decision: `CLOSED / FROZEN`.

Frozen N2 identity and qualification:

- implementation commit: `455d7cf1b20c2479fd9d702cb2f4a9c140672559`;
- parent governance checkpoint: `7a6bdaef828b80b58fc77b454f72ed20d3a98ea0`;
- committed tree: `bf529655c7527a12e1f005486f49f1db81448fa6`;
- qualified environment: Windows x64 / CPython **3.11.9**, pytest **9.1.1**, Hypothesis **6.167.1**, `pip check` clean;
- targeted N2 admission + hostile hardening: **95/95**;
- complete qualified pre-commit regression: **1242/1242**;
- complete qualified post-commit regression: **1242/1242**;
- post-commit working tree: clean.

N2 remains evidence-admission only. It admits one bounded unitless finite-decimal scalar from an already-normalized exact `AnswerEvidenceBundle`, preserves submission/OCR/question/answer-scope/evidence references, and fails without converting parser/resource/binding problems into academic correctness. It does not authenticate OCR/backend provenance or perform academic comparison.

N3 prerequisite decision: `BUILD` for **narrow deterministic unitless scalar comparison only**. N4 and UNIT remain unauthorized.

Why N3 now earns BUILD:

- N1 freezes the complete approved academic comparison universe for v1: finite `EXACT` conditions and inclusive positive `ABSOLUTE_TOLERANCE` conditions, all mapping to one complete satisfied projection and one complete not-satisfied projection;
- N2 supplies one already-admitted canonical unitless finite-decimal observation with evidence provenance;
- those two frozen inputs are sufficient to define exact deterministic comparison without inventing normalization, units, scoring, partial-credit composition, review policy or academic semantics;
- condition ordering is non-authoritative and all alternatives share the same satisfied projection, so N3 needs only determine whether at least one already-approved condition is satisfied; it must not choose a winning condition or assign marks.

Closed N3 v1 scope for the next implementation batch:

- consume one exact current `ResolvedNumericAuthority` and one exact current `AdmittedNumericScalar`;
- revalidate both current object graphs and exact authority fingerprint/binding before comparison;
- require exact question binding between authority and admitted evidence;
- evaluate canonical finite-decimal values with exact deterministic arithmetic independent of binary float and ambient decimal context;
- `EXACT`: numerical equality of the admitted scalar and approved expected value;
- `ABSOLUTE_TOLERANCE`: inclusive `abs(observed - expected) <= tolerance` using the approved strictly-positive tolerance;
- alternatives are OR semantics only; zero matches => `NOT_SATISFIED`, one or more matches => `SATISFIED`;
- produce a bounded immutable N3 result carrying authority/evidence provenance and only `SATISFIED | NOT_SATISFIED`, not criterion levels, marks, score or publication/review state;
- malformed/forged/binding/technical failures remain errors and must never be converted into `NOT_SATISFIED`.

N3 does **not** establish:

- criterion-judgment composition or scoring integration (N4);
- UNIT parsing/conversion or quantity algebra;
- scientific notation, fractions, symbolic expressions or relative tolerance;
- OCR/backend trust, whole-answer scope verification or evaluator-attempt provenance;
- benchmark/calibration breadth, production NUMERIC quality or auto-release eligibility.

Representative approved/anonymized workload and numeric benchmark evidence remain required before broadening NUMERIC scope or claiming production auto-release quality. The deterministic N3 mechanism may be built now without making those claims.

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

- production integration and broader capability work beyond the now-frozen evaluator-facing ACTIVE question-authority projection;
- executable S2b-2 recommendation policy or calibrated recommendation mapping;
- final candidate `GradeResult`;
- deterministic risk/review recommendation engine (S2b-1 observations exist, but recommendation policy is not yet implemented);
- whole-answer `answer_scope_ref` verification;
- evidence-type compatibility;
- real OCR/backend integration;
- approved reference retrieval;
- one production live-provider adapter with transport-level bounding;
- production evaluator quality beyond the frozen DIRECT-text semantic plumbing slice; semantic academic benchmark quality and numeric/math evaluator quality remain unestablished;
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

ACTIVE authority + DIRECT-text semantic slice qualified evidence on Windows / CPython 3.11.9:

- implementation commit: `82588a4df5d77f9b88dac3b19c34728dc0ad697e`;
- parent: `7ea8fbb88e2e4edd83b7ca80f14b53eddcff601f`;
- committed tree: `c0d68f97433cefb4f3d06fd86fb10b2db6215413`;
- authority/semantic/composition targeted gate: **155/155**;
- related rubric-lifecycle/paper-aggregation regression: **26/26**;
- complete pre-commit regression: **1008/1008**;
- exact 13-path staged custody audit: passed;
- final staged tree matched the committed tree;
- complete post-commit regression: **1008/1008**;
- post-commit working tree: clean.

ACTIVE exposure integrity repair qualified evidence on Windows / CPython 3.11.9:

- repair commit: `ba951af9081a5459464f4985074f5f113e62ad6b`;
- parent: `f8efd180611246d3a2c847b26316e5dadbabee1a`;
- committed tree: `687e4049630135bd3fd0d06db1218169df06a550`;
- candidate/committed patch SHA-256: `f9489d737593679e0accb7cc2e2b11d4500e53c7ff9292ebbb91434658ffe414`;
- targeted lifecycle/ACTIVE hostile campaign: **99/99**;
- complete qualified pre-commit regression: **1037/1037**;
- complete qualified post-commit regression: **1037/1037**;
- post-commit working tree: clean.

NUMERIC N1 authority qualified evidence on Windows / CPython 3.11.9:

- implementation commit: `f28d11d1a20a25944f0d3dcc9320ea0149fbe46f`;
- parent: `328f131281c554f798e944c27a5177a43900f3bd`;
- committed tree: `d5410673f76b321e19ae97cc75b5aa538e11e135`;
- reviewed candidate patch SHA-256: `da7dc648ee8673e9e6ece5d3d188bf2dccfd9c9d5ccc867d23ee1eeb27128c8c`;
- targeted N1 + hostile qualification: **110/110**;
- exact related selector: **515/515 selected**, **606 deselected**;
- complete qualified pre-commit regression: **1147/1147**;
- complete qualified post-commit regression: **1147/1147**;
- post-commit working tree: clean.

S1's earlier empty-evidence defect remains the standing example that full-suite green does not replace hostile source review.

## Next task

Begin the **N2 NUMERIC student-evidence admission causal RED batch** from the exact frozen N1 baseline `f28d11d1a20a25944f0d3dcc9320ea0149fbe46f` / tree `d5410673f76b321e19ae97cc75b5aa538e11e135`.

The RED batch must establish the bounded v1 admission contract above before production implementation. The first RED must fail causally at the missing N2 production boundary after existing `AnswerEvidenceBundle` fixtures construct successfully.

Do not start N3 comparison, N4 composition, UNIT support, capability routing, OCR/backend adapters or generic numeric frameworks in this batch. Unsupported/malformed/unassessable evidence must remain non-academic failure, never an implicit incorrect-answer projection.

## Documentation rule

Update `PROJECT_STATE.md` at subsystem milestone closure, material blocker/assumption change, and before implementation-chat handoff. Do not use it as a turn-by-turn diary.

`IMPLEMENTATION_PLAN.md` records the frozen S2/CHOICE/ACTIVE-DIRECT milestones, prerequisite-gate decisions, and the currently authorized implementation sequence.

`TESTING.md` records the qualified S2, deterministic CHOICE, ACTIVE/DIRECT semantic, and ACTIVE-exposure repair verification/freeze evidence.

Do not alter the SRS/Engineering Source of Truth merely to report implementation progress.
