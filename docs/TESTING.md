# Testing Strategy and Verification Status

Status date: 2026-09-24

## Verification principle

Tests are evidence, not authority. Green tests do not override the SRS/accepted architecture, and a passing suite does not prevent a hostile source audit from finding a real fail-open path.

For non-trivial capability work use:

```text
contract
→ RED
→ verify causal failure
→ minimal GREEN
→ targeted/inherited/full regression
→ hostile source audit
→ exact staging/tree/blob identity
→ post-commit regression
→ freeze evidence
```

## Frozen deterministic scoring kernel

Frozen anchor:

`178668b9b735ef369825c86d16db7999b8d3c784`

Qualified regression baseline inherited by Rubric Authoring: **519 tests**.

The kernel includes deterministic question scoring and paper aggregation and remains frozen.

## Rubric Authoring Safety & Compilation

Acceptance commit:

`5f3ee013bc9f732f469104a5f6c6dc151cad3402`

Qualified final evidence:

- targeted: 78/78
- inherited deterministic kernel: 519/519
- full: 597/597
- selected mutation campaign: 8/8 genuine kills
- exception-transparency regression: passed
- independent source/contract review: passed
- exact staging/source audit: passed

Committed acceptance patch SHA-256:

`b39c08e49590f1b651ab542abbf0172e381c7e7a457bb0cf3a0fa795f43ed604`

## RubricGenerator G1a

Commit:

`a6f0388f137226fb2125a07c6f01f424bafc5d58`

Qualified evidence:

- targeted: 27/27
- inherited: 597/597
- full: 624/624
- targeted under `PYTHONHASHSEED=1`: 27/27
- targeted under `PYTHONHASHSEED=777`: 27/27
- targeted under `PYTHONHASHSEED=123456`: 27/27

Committed acceptance patch SHA-256:

`5baa4e0856d46b58250e3c7b9a8bae2e365d4d7f9d815da975c9f98c4c148a95`

## RubricGenerator G1b hostile ingress

Commit:

`c7a3ae3592b6ad0f6120178ddf9015e5ac10bdf0`

Full suite at closure: **676 passed**.

Verified behaviors include strict bounded raw-byte/schema admission, authority-field rejection, exact admitted type construction, subclass/replace smuggling resistance, deterministic behavior and exception transparency.

Use the verified G1b commit/tree values; earlier manually transcribed values were wrong.

## Provider abstraction / Replay

Commit:

`c48c813fb0eb64013fc7265ed0d14f64dd9d3d57`

Qualified final evidence:

- provider contract: 22/22
- inherited: 676/676
- full: 698/698
- post-commit full regression: 698
- final status: clean

The replay-provenance hostile RED found a real defect: fixture bytes could otherwise be cross-attributed to a different configured provider/model. The GREEN binds every fixture's provenance to provider provenance.

This establishes internal provenance consistency, not external cryptographic authenticity.

## Synthetic E2E S1

Commit:

`456a6248e9d28ec083e7503c3a9ad9385de47c7d`

Tree:

`e9898d00850890840ebd04c284993a81d9b5cc4a`

Committed acceptance patch SHA-256:

`7ff52d81346094f9c361ce9625107a4dfe1330a947f18a482f4599a3d5382f32`

Final qualified evidence:

- targeted S1: 11/11
- inherited: 698/698
- full before commit: 709/709
- full after commit: 709/709
- staged tree == committed tree
- final status: clean

The S1 sequence is important:

1. initial RED: missing evidence/evaluation/verifier surfaces;
2. submission-wide duplicate evidence-ID hostile strengthening;
3. initial GREEN reached 708/708;
4. hostile source audit found a real fail-open path: localized criterion judgment with empty `evidence_refs` could reach scoring projection;
5. surgical RED reproduced `1 failed / 10 passed` with 698 inherited green;
6. verifier-only GREEN closed the path;
7. final 11/698/709 and post-commit 709 passed.

This is a standing example of why complete-suite green is not sufficient without hostile source review.

## S1 accepted contract coverage

Current S1 tests cover:

- evidence/evaluation/verifier public contract existence;
- immutable evidence/evaluation value surfaces;
- submission-wide duplicate `block_id` rejection;
- positive block-grounded verification;
- missing evidence reference rejection;
- wrong-question reference rejection;
- CROSSED_OUT evidence rejection under current profile;
- empty evidence references rejection before projection;
- rich-to-narrow projection;
- real frozen reducer composition;
- authority isolation.

S1 does not prove:

- whole-answer `answer_scope_ref` grounding;
- evidence-type compatibility;
- real OCR adapter behavior;
- final S2 workflow identity;
- risk/review/candidate result;
- real evaluator/provider quality.

## Synthetic E2E S2a — frozen

Branch:

`synthetic-e2e-s2`

Implementation commit:

`61ce96d62774a78f4019c4905421324f614a7422`

Tree:

`ced53127e566902050d47fe6b0a1bac921a0c9c3`

Parent / frozen S1 base:

`456a6248e9d28ec083e7503c3a9ad9385de47c7d`

Qualified Windows / CPython 3.11.9 sequence:

- fresh exact-S1 S2 baseline: **709/709**;
- initial S2a contract scaffold: **10 failing nodes**, all at the intentional unimplemented entry point;
- causal GREEN1: **4 passed / 6 failed**;
  - happy path and native S1/B2/B3 exception-transparency cases passed;
  - context mismatch reached S1 and failed with `EvidenceVerificationError`;
  - cross-question authority mismatch reached B2 and failed with `UnknownJudgmentPerformanceLevelError`;
  - missing work produced `KeyError('Q2')`;
  - duplicate/unexpected work reached poisoned S1 evidence;
- GREEN2 added only S2-owned pre-execution admission;
- GREEN2 inherited regression: **709/709**;
- original S2a contract: **10/10**;
- GREEN2 complete suite: **719/719**;
- acceptance-hardening: **8/8**;
- all S2a contract + acceptance tests: **18/18**;
- complete suite after acceptance: **727/727**;
- complete suite after code/test staging: **727/727**;
- final governance-inclusive staged suite: **727/727**;
- post-commit complete suite: **727/727**;
- post-commit working tree: clean.

Acceptance-hardening covers:

- ordinary malformed top-level public inputs;
- complete work/authority admission before the first question executes;
- authoritative question execution order rather than caller order;
- distinct rich-vs-numerical criterion ordering and identity continuity;
- later-question native B2 failure without a successful S2 execution result.

The S2a test boundary intentionally does **not** treat Python dataclass unforgeability or `object.__new__` constructor bypass as an authentication requirement. S2a is an internal trusted-domain boundary, not an arbitrary in-process hostile-object sandbox.

S2a tests and source audit establish:

- public execution consumes inputs needed to perform grading rather than precomputed verification/scoring result credentials;
- S2 invokes the real S1 verifier, real frozen B2 reducer, and real frozen B3 aggregator;
- submission/spec/work-question relationships owned by S2 are admitted before question execution;
- expected execution work and order come from paper authority;
- rich and numerical tracks remain parallel; continuity is compared by semantic identity rather than positional `zip()`;
- S2 performs no score arithmetic and does not duplicate B3 rubric/policy/result admission;
- native S1/B2/B3 failure type/arguments remain transparent;
- successful return occurs only after all question S1+B2 work and B3 aggregation succeed.

Important non-claims:

- supplied scoring authorities are already-admitted upstream domain inputs; S2a does not authenticate their backend/lifecycle origin or semantic authenticity;
- `grading_run_id` and `exam_ref` are preserved/validated but not semantically authenticated here;
- evaluator-attempt provenance tying supplied judgments to this exact run/spec is deferred;
- `GradingExecutionResult` class/object identity is not proof that the execution function ran;
- S2a provides no persistence rollback, exactly-once guarantee, database transaction, review decision, or publication authority.

Code/test staging evidence before governance update:

- code/test candidate tree: `804a28a1041b264ad150638a3267d6cf69802354`;
- code/test staged patch SHA-256: `1bbf993078166ee4b07e627cbaf30927bd559b527ee5b5a91806e0ab5d5e19eb`;
- `src/grading/execution.py` blob: `d6d8ef44b8b9df49fee9f9d9fd6a3396aaea1711`;
- acceptance-test blob: `4fd1091d3c89a5fb42dec770e21b7f077e4f652c`;
- original S2a contract-test blob: `fd96c6c7ba6e26f1482f89d2aea14a10ffe9329e`.

The frozen S2a implementation identity is commit `61ce96d62774a78f4019c4905421324f614a7422`, tree `ced53127e566902050d47fe6b0a1bac921a0c9c3`, with final staged acceptance patch SHA-256 `0015fdb2b26ec2667d94cdce00f6104750d497cc42f467221161f112bf41c56a`.


## Synthetic E2E S2b-1 — risk observations frozen

Branch:

`synthetic-e2e-s2b`

Implementation commit:

`3f789a70443c3b9810c63b15bccb8dc4f5d889e5`

Tree:

`99758c27b9890ba7e65ad0667c71db502e6071c7`

Parent / S2a governance anchor:

`ca2c27b7d2958eb8f9e170120ad2f758e0f5bc61`

Qualified Windows / CPython 3.11.9 evidence:

- S2b-1 targeted/acceptance: **16/16**;
- inherited frozen regression: **727/727**;
- full suite: **743/743**;
- frozen S2a diff check before commit: clean;
- post-commit HEAD: `3f789a70443c3b9810c63b15bccb8dc4f5d889e5`;
- post-commit tree: `99758c27b9890ba7e65ad0667c71db502e6071c7`;
- parent: `ca2c27b7d2958eb8f9e170120ad2f758e0f5bc61`;
- working tree was clean immediately before the post-commit 743/743 regression.

S2b-1 contract coverage includes:

- execution/evidence submission binding;
- rich verified submission/question continuity with numerical question results;
- exact execution-score tuple continuity with `PaperScoreResult.question_results` in authoritative order;
- duplicate execution-question rejection;
- duplicate scoring/numerical criterion rejection;
- exact scoring-judgment/numerical-effect criterion universe equality and selected-level agreement;
- exactly one matching evidence question per executed question;
- unrelated evidence-question isolation;
- crossed-out evidence inactivity under the current profile;
- `OCR_CONFIDENCE_UNKNOWN` only from semantic confidence status `UNAVAILABLE`, one observation per affected active evidence block;
- `EVALUATOR_UNCERTAINTY_REPORTED` only from non-empty rich evaluator `uncertainties` for the canonically matched criterion;
- deterministic observation order;
- arbitrary numeric confidence is not thresholded into `OCR_LOW_CONFIDENCE`;
- free-form warnings/reason strings do not become normalized policy observations;
- ordinary malformed top-level inputs fail through the S2b-owned admission error;
- repeated extraction is deterministic and does not mutate the supplied execution/evidence values.

Source audit establishes no risk arithmetic, no recommendation/risk-tier mapping, no score mutation, no `GradeResult`, no `awarded_marks` logic, no S1/S2a/scoring calls, and no modification to frozen S2a source/tests.

Important non-claims:

- S2b-1 is an observation extractor, not a recommendation engine;
- numeric OCR thresholds, school/platform defaults, calibrated risk tiers and recommendation mappings remain unimplemented pending authority;
- `grading_run_id`, `submission_ref`, question/criterion/block IDs are correlation/contextual traceability, not authentication credentials;
- supplied `AnswerEvidenceBundle` identity is not cryptographically bound to the exact artifact used by S2a; stronger cross-stage artifact identity is a future workflow/artifact contract;
- Python object identity does not prove S2a/S2b execution provenance;
- no review/job-state/publication semantics are established.

## Deterministic single-select CHOICE v1 — frozen

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

Qualified Windows / CPython 3.11.9 evidence:

- contract RED: **87 failed / 7 passed**, with failures caused by missing local admission validation rather than collection/import/setup errors;
- contract GREEN: **94/94**;
- inherited pre-evaluator complete baseline: **837/837**;
- evaluator behavior RED: **12 failed / 1 passed** at the intentional evaluator stub;
- initial evaluator GREEN: **13/13**;
- hostile public-boundary hardening RED: **3 failed / 13 passed**, exposing uncontrolled `AttributeError` on malformed top-level inputs;
- hardened evaluator targeted: **16/16**;
- complete pre-commit suite: **853/853**;
- staged evaluator tree: `1d5239434e959fcdf51eda8304a6d9b234e6c3df`;
- committed evaluator tree: `1d5239434e959fcdf51eda8304a6d9b234e6c3df`;
- post-commit complete suite: **853/853**;
- post-commit working tree: clean.

Accepted behavior includes:

- exact public top-level type admission with CHOICE-domain failures;
- known correct canonical option → exact match projection;
- known wrong but admitted option → exact mismatch projection;
- unknown option → `UnsupportedChoiceInputError`;
- selection/question and scoring-authority/fingerprint binding;
- both match and mismatch projections validated against the complete scoring criterion universe and admitted levels;
- deterministic rich `EvaluatedCriterionJudgment` output in scoring-rubric order;
- canonical evidence refs carried unchanged for later S1 verification;
- real CHOICE → S1 → B2 composition for the supported fixture;
- hallucinated/invalid evidence remains S1-owned and fails there rather than being reverified by CHOICE;
- no score arithmetic, OCR parsing, provider calls, risk/recommendation logic, mutation, or generic evaluator framework.

Important non-claims:

- CHOICE v1 is single-select only and does not implement blank/no-selection, ambiguous extraction, multi-select, ranking, free-text EXACT, numeric/unit, semantic/theory, or mathematical-derivation evaluation;
- CHOICE does not authenticate ACTIVE grading-spec provenance, scoring-authority lifecycle origin, evidence semantic origin, or evaluator-attempt/run provenance;
- CHOICE does not establish production grading quality beyond its frozen deterministic contract/behavior scope.

Historical complete regression baseline at CHOICE evaluator freeze: **853/853**.

## ACTIVE authority + DIRECT-text semantic evaluator — frozen slice

Branch:

`active-grading-authority-boundary`

Implementation commit:

`82588a4df5d77f9b88dac3b19c34728dc0ad697e`

Parent:

`7ea8fbb88e2e4edd83b7ca80f14b53eddcff601f`

Committed tree:

`c0d68f97433cefb4f3d06fd86fb10b2db6215413`

Qualified Windows / CPython 3.11.9 evidence:

- initial DIRECT semantic causal RED: **1 failed** at the missing `grading.semantic_evaluator` module, followed by the intended happy-path GREEN;
- concentrated semantic hostile campaign: **101/101** after hardening malformed UTF-8/JSON/schema/resource, criterion-order/duplication, evidence-visibility and output-smuggling cases;
- model-answer materialization hardening regression plus real semantic → S1 → B2/B3 composition: **8/8**;
- ACTIVE-authority hardening file after source-execution/materialization containment: **18/18**;
- authority/semantic/composition accumulated gate: **155/155**;
- related rubric-lifecycle/paper-aggregation regression: **26/26**;
- complete pre-commit repository regression: **1008/1008**;
- exact 13-path staging/blob/tree custody audit: passed;
- committed tree matched the staged tree above;
- complete post-commit repository regression: **1008/1008**;
- post-commit working tree: clean.

Accepted frozen behavior includes:

- immutable evaluator-facing ACTIVE question authority bound to grading-spec/question/context-policy/teacher-approved rubric/scoring authority;
- source execution/materialization failures contained without changing existing rubric-lifecycle failure semantics;
- `ContextPolicy.DIRECT` text-only semantic evaluation with explicit unsupported evidence/policy rejection;
- strict bounded provider-response admission before trusted judgment construction;
- duplicate criterion rejection before mapping and criterion-ID-based rich-field reassociation;
- system-owned evaluator metadata and attempt correlation outside provider control;
- evidence references preserved for independent S1 verification;
- real semantic → S1 → frozen B2/B3 composition with no semantic-provider numerical authority.

Important non-claims:

- this does not establish production-provider academic quality, provider network-adapter completion, semantic benchmark quality, or real subjective school-paper E2E;
- it does not implement `DIRECT_PLUS_REFERENCE`, `HYBRID_RETRIEVAL`, `REFERENCE_ONLY`, general capability routing, OCR/backend integration, retry/idempotency/exactly-once behavior, risk/review recommendation, workflow state, publication, numeric/unit evaluation, or mathematical/derivation evaluation;
- `SemanticEvaluationResult` and ACTIVE-authority object identity are not authentication or execution-provenance tokens;
- broader Release-1 semantic/theory capability remains open.

Current complete regression baseline after ACTIVE/DIRECT semantic freeze: **1008/1008**.


## S2 test-design rules

Do not test implementation trivia such as whether a dataclass is artificially “unforgeable.”

For S2b and later integration work, preserve the established boundaries:

- tests must distinguish execution data from execution provenance;
- risk/review cannot mutate frozen numerical results;
- candidate status is not publication authority;
- no later orchestration may infer criterion `awarded_marks` redistribution that is not defined by authority.

## Mutation/adversarial policy

Use mutation testing selectively for safety-critical decision logic where it provides new evidence.

Do not run generic mutation campaigns after every small slice.

A kill is genuine only when the mutated source actually ran and a semantically relevant test failed—not because of setup errors, collection errors, timeout, or infrastructure failure.

## Release-level testing still required

Release 1 still requires:

- representative teacher-reviewed rubric-generation quality data;
- deterministic evaluator capability tests;
- semantic evaluator benchmark;
- supported math/derivation benchmark;
- reference isolation/provenance tests;
- real OCR contract/integration tests;
- risk/review/regrade workflow tests;
- provider/model/cost/latency/retry telemetry checks;
- real subjective school-paper E2E without manual repair;
- real numerical/math school-paper E2E without manual repair;
- final release-candidate regression/adversarial suite;
- calibration on held-out data where thresholds are used.
