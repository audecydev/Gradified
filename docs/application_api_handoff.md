# Application API handoff contract

The grading engine is a Python library. It does not supply HTTP routes, user sessions, database tables or a frontend service. The backend and frontend must agree on those interfaces before their implementation can be treated as connected. This document records the **required information and acceptance rules**; the JSON examples are **design examples, not an approved or implemented wire API**.

## Ownership and approval

| Decision or behavior | Owner | Required evidence |
|---|---|---|
| URL paths, HTTP methods, authentication transport and API version | Backend API owner | Reviewed API specification, integration tests |
| Teacher, student, parent and administrator permissions | School/backend identity owner | Denial and permission-revocation tests |
| Approved paper, question order, rubric, source and version | Backend school-content owner | Current revision and issuer proof |
| OCR scan, page regions and question mapping | OCR + backend | Source artifact and mapping trace |
| Candidate grading operation and scoring | Engine | Source tests, criterion and result references |
| Durable operation identity, status and replay protection | Backend | Two-worker atomicity and restart/lost-reply evidence |
| Review decisions and corrected official-result versions | Backend + academic product owner | Audit chain and signed school decision; journal alone is insufficient |
| Publication and recipient-specific result projection | Backend | Effect-time permission and visibility tests |
| Browser display and state/error wording | Frontend + backend | Approved status/error mapping and accessibility tests |

**Not an API:** Python methods such as `ProductionPaperOperations.execute` are not HTTP handlers. No URL, database schema or response field name below is authoritative until accepted by the backend owner.

## Minimum public operations to agree

The backend API owner must publish a versioned OpenAPI document (or equivalent machine-readable contract) covering the following *capabilities*. The names in this table are descriptions, not proposed URLs.

| Capability | Required request/response information | Rules |
|---|---|---|
| Read approved examination | Tenant, exam, paper/set IDs, eligible question families, approval and revision, access scope | Authenticated teacher only; do not return unpublished or foreign data |
| Submit scan / request mapping | Submission and uploaded artifact identity, OCR job ref, capture status | Backend owns identity; OCR output cannot grant paper authority |
| Read question mapping readiness | Question/region refs, source revision, mapping status (`READY`, `UNKNOWN`, `UNREADABLE`, `UNMAPPED`, `ABSENT_CONFIRMED`) | Do not grade non-ready evidence without a separate approved mechanism |
| Start grading / regrade / retry | Submission/paper identity, requested operation kind, original operation key, authorization version | Backend must resolve actor and policy; retry is never a new identity by default |
| Read operation status | Original operation key, engine/backend state, last known outcome, safe failure category, revision | Status read is effect-free; unknown must stay unknown until reconciled |
| Read candidate results | Result revision, question/criterion effects, approved rubric and source refs, review state | Teacher-only until separately authorized for recipients |
| Submit teacher review decision | Teacher identity from session, original result, criterion/question, approved action and justification | Append-only original-bound journal; does not silently mutate marks |
| Read publication | Official result version, release state, audience/school permission | Recheck at disclosure; no candidate leakage |

## Operation and state mapping

`src/grading/contracts/job_state.py` provides the engine's `GradingJobState` vocabulary:

- Progress: `QUEUED`, `VALIDATING`, `GRADING`, `VERIFYING`, `SCORING`, `RISK_EVALUATION`.
- Terminal: `COMPLETED`, `REVIEW_REQUIRED`, `UNASSESSABLE_EVIDENCE`, `UNSUPPORTED_CAPABILITY`, `FAILED_TECHNICALLY`.

The backend must **explicitly map** these to its persisted application states. `COMPLETED` is not the same as an official published result. A separate operation may be `UNKNOWN` or awaiting original-effect reconciliation even when a UI would otherwise call it failed. Release also has separate disposition and audience authority. Never map every exception to “incorrect answer.”

Required mapping rules:

1. No new grading attempt is started by a browser retry after a timeout. The browser reuses the original operation key and requests **read-only** status.
2. Mark a candidate visible only to currently authorized teachers or administrators. Mark a result *official* only after the governed release effect and current recipient permission succeed.
3. Record technical failure, unsupported capability, unassessable OCR and academic review as distinct conditions.
4. Transmit sufficient correlation IDs for support; redact private answers, provider messages, secrets and foreign-tenant records.
5. A status reply must distinguish `not started`, `in progress`, `candidate`, `awaiting review`, `blocked`, `uncertain`, and `officially released` with agreed transport representation. The precise wire tokens are a backend API design decision.

## Example payload shapes for the API design review

The following examples describe **required information**, not implemented wire field names. Synthetic values deliberately contain no real student details.

A proposed grading request envelope:

```json
{
  "tenant_ref": "school-example",
  "exam_ref": "exam-example",
  "paper_ref": "paper-example",
  "submission_ref": "submission-example",
  "original_operation_ref": "grading-request-example",
  "operation_kind": "FIRST",
  "approved_paper_revision": "approval-revision-example"
}
```

The backend must obtain the actor from the authenticated session, not from any request-body claim. It must bind the request to `PaperAdmissionRequest` using actual trusted source records; this example alone cannot become an admitted request.

A proposed **teacher-only candidate status** envelope:

```json
{
  "original_operation_ref": "grading-request-example",
  "state": "CANDIDATE_AVAILABLE",
  "state_revision": "state-revision-example",
  "candidate_result_ref": "candidate-example",
  "paper_total": "10",
  "question_marks": [
    {"question_id": "Q1", "mark": "5"},
    {"question_id": "Q2", "mark": "5"}
  ],
  "official_release": false
}
```

`CANDIDATE_AVAILABLE` and all the example JSON keys are illustrative API-design vocabulary, **not** `GradingJobState` members or existing HTTP response fields. Production decimal marks must preserve the engine's canonical serialization, not floating-point values. A student/parent-facing status must not include unreleased marks or private evidence.

## Minimum error and recovery agreement

| Backend-facing category | Engine/external source | Application response behavior |
|---|---|---|
| `INVALID_REQUEST` | Malformed submission/contract | Validation error; no grading effect |
| `NOT_AUTHORIZED` | Foreign tenant, revoked actor/paper | Deny without revealing foreign identifiers |
| `EVIDENCE_NOT_READY` | OCR readiness failure | Show scan/mapping issue; no guessed grade |
| `UNSUPPORTED_EVALUATION` | Unsupported family/operation | Show supported-scope refusal; no fallback to arbitrary AI grade |
| `ACADEMIC_REVIEW` | Review-required outcome | Teacher workflow, not technical retry |
| `EFFECT_UNCERTAIN` | Timeout/lost acknowledgment after possible effect | Read original identity and reconcile; never issue a fresh request blindly |
| `TECHNICAL_FAILURE` | Unrecoverable implementation/infrastructure error | Safe opaque message, correlated protected logs |
| `OFFICIAL_RELEASE_DENIED` | Expired/revoked approval or recipient | Keep candidate private, no publication |

These names are **proposed mapping categories**, not concrete exceptions or HTTP codes. The signed API contract must state real transport codes and fields for each category and include explicit recovery requests/responses.

## Contract approval record required before frontend connection

The receiving teams must record: (1) API owner and version, (2) schema location and change policy, (3) identity/role matrix, (4) idempotency key scope and retention, (5) exact state and exception mappings, (6) privacy and field projection for teacher versus student, (7) error/recovery behavior, (8) source/version freshness and (9) at least one contract test for each success and denial path. Backend and frontend owners must approve the same artifact. No undocumented endpoint should be inferred from a Python class.

See [Backend integration](backend_integration_guide.md), [Frontend integration](frontend_integration_guide.md), [Official release](official_release.md) and [Integration test plan](integration_test_plan.md).
