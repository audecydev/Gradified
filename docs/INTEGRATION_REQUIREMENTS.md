# Integration Requirements

This is the shortest requirements checklist for teams connecting real systems to the verified grading core.

The rule is simple: **external systems provide trusted facts; the grading core validates the relationships it owns; deterministic code calculates marks.**

## Common requirements for every integration

Every adapter/integration must:

1. preserve exact IDs and versions; do not silently choose “latest”;
2. preserve uncertainty instead of inventing certainty;
3. fail safely on malformed, missing, unsupported, or mismatched data;
4. never write a numerical score directly into the grading core as authority;
5. never derive tenant or authorization authority from student content;
6. keep secrets, private student data, and school-private references out of logs and source control;
7. keep retries/idempotency explicit so one grading job cannot silently become two authoritative results;
8. record enough provenance to debug and audit the integrated run.

## Backend / workflow must provide

- authenticated/authorized tenant and actor context outside the grading core;
- exact ACTIVE grading-spec version and question identity;
- exact school-authorized rubric/model-answer/reference access;
- stable `grading_run_id` and `submission_ref` values;
- durable persistence and retry/idempotency behavior;
- review/regrade workflow and official publication policy.

Expected outcome: the backend supplies trustworthy workflow facts and stores candidate results without becoming a second scoring engine.

Read: [`BACKEND_INTEGRATION_GUIDE.md`](BACKEND_INTEGRATION_GUIDE.md).

## OCR must provide

- a stable submission identity;
- reliable question mapping or an explicit mapping failure;
- unique evidence block IDs;
- content/modality type;
- OCR confidence when available, or explicit `UNAVAILABLE` when not available;
- crossed-out/uncertain state when available;
- page/location/asset references when available;
- OCR provenance/version.

Expected outcome: real OCR data is converted into `AnswerEvidenceBundle` without vendor-specific fields leaking into grading-core logic.

Read: [`OCR_INTEGRATION_GUIDE.md`](OCR_INTEGRATION_GUIDE.md).

## Reference/retrieval system must provide

- trusted tenant/class/subject/reference filtering before retrieval;
- only admitted/approved reference versions from the workflow boundary;
- source ID, source version and opaque provenance hash on every returned context chunk;
- exact request binding to grading spec, question and context policy;
- no unrelated fallback material.

Expected outcome: the grading core receives bounded, provenance-preserving context and rejects binding/resource/shape violations. REF-1 alone does not prove tenant isolation; the real integration must.

Read: [`REFERENCE_INTEGRATION_GUIDE.md`](REFERENCE_INTEGRATION_GUIDE.md).

## Semantic model/provider must provide

- structured output through the existing provider protocol;
- only known criterion IDs and approved rubric levels;
- bounded response size;
- explicit errors/timeouts rather than fabricated judgments;
- provider/model/version, latency/cost and attempt telemetry at the integrated workflow layer.

Expected outcome: semantic interpretation can propose criterion-level judgments, but it cannot directly set the authoritative numerical total.

Read: [`SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md`](SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md).

## Acceptance before a production Release 1 claim

Integration is not complete until the combined system proves at least:

- one real subjective/text paper path end to end without manual JSON repair;
- one real numeric/math paper path end to end without manual JSON repair;
- tenant/reference isolation with real backend/reference infrastructure;
- duplicate/retry safety and linked regrade behavior;
- provider failure and malformed external input fail closed;
- held-out teacher-marked benchmark/calibration evidence;
- latency/cost/retry/audit telemetry;
- complete regression/adversarial tests remain green.

See [`INTEGRATION_TEST_PLAN.md`](INTEGRATION_TEST_PLAN.md) for the detailed sequence.
