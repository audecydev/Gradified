# Testing Strategy and Verification Status

Status date: 2026-09-21

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

## Synthetic E2E S2a acceptance candidate

Branch:

`synthetic-e2e-s2`

Base S1 commit:

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
- complete suite after code/test staging: **727/727**.

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

The final S2a tree/patch identities must be captured again after governance documents are staged.

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
