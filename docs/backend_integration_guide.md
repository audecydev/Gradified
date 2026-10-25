# Backend integration

The backend owns school accounts, permissions, active exam content, database transactions and result publication. The grading engine consumes trusted, versioned observations from that backend and produces candidate outcomes.

## Build in this order

1. Create authenticated actor and tenant scopes. The actor's identity must come from a trusted session, not an OCR field or frontend request body.
2. Resolve the current paper, selected questions, rubric and approved policies with exact version and issuer evidence. Paper approval and answer readiness must be checked again when effects occur.
3. Provide the exact sources required by `ProductionPaperAdmissionComposer` in `src/grading/integration/paper_readiness_admission.py`.
4. Implement durable original-keyed attempt reservation, provider-effect reconciliation and scored-result conditional commit. Concurrency across **multiple workers** and process restarts must be tested against the real database.
5. Build the supported operation root `ProductionPaperOperations` with the same qualified attempt, executor and conditional storage owners. Installation intentionally rejects inconsistent owner assemblies.
6. Persist every candidate with its source paper, submission, rubric, attempt and criterion references. A candidate is not an official mark.
7. Connect teacher review to an authenticated append-only decision journal. A corrected official grade needs a separately approved result-version transaction; the review journal alone does not provide one.
8. Connect the conditional release writer, original write-ahead intent store, current authority and recipient checks. Publication must not occur merely because a grading call returned successfully.

## Interfaces to implement

| Need | Source declaration / call |
|---|---|
| Actor identity | `IdentityAuthority.current_actor()` in `integration/authorized_preparation.py` |
| Approved paper | `PaperSelectionAuthority.authorize_paper(...)` in `integration/paper_readiness_admission.py` |
| Paper readiness | `PaperAnswerAuthority.resolve_paper_readiness(...)` in the same module |
| Revision confirmation | `PaperRevisionAuthority.confirm_paper_revision(...)` in the same module |
| Attempt and scored effect | `QualifiedJointEffectOwner` in `integration/joint_effect_authority.py` |
| Scored CAS and read-only recovery | `AtomicWholePaperResultStateAuditStore` in `integration/whole_paper_cas.py` |
| Official conditional release | `QualifiedConditionalResultRelease` in `integration/official_result_release.py` |

Read exact dataclass fields and exception/disposition semantics in those modules. No public REST URLs, JSON response names or database schema are defined by this Python repository. The required fields, ownership, example payload shapes and approval record are in [Application API handoff](application_api_handoff.md).

## Backend/frontend acceptance contract

Before UI integration, publish a shared API artifact covering: authenticated actor; school/exam/paper/submission IDs; original operation and attempt ID; grading status; candidate and approved result versions; per-question authorized evidence/marks; review/regrade commands; release approval/recipient scope; error and UNKNOWN recovery lookup. Define error status mapping, privacy masking and idempotency keys. Do not invent those endpoint names solely from grading class names. Use [Application API handoff](application_api_handoff.md) to agree the owned API contract before frontend work.

## Negative tests

Reject foreign school, stale rubric, revoked teacher, missing currentness, duplicate concurrent attempt, crash after real provider contact, and lost database acknowledgment. Prove the original result and billing history survive. See [Paper execution](paper_execution_and_persistence.md) and [Official release](official_release.md).
