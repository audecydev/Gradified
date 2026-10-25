# Frontend integration

The frontend presents school examinations, candidate marks, review decisions and published results. It communicates only with the authenticated backend API. Direct access to grading Python objects is not an accepted browser architecture.

## Required screens and states

| Screen | Information | Safety requirement |
|---|---|---|
| Exam setup | Approved paper, rubric revisions, supported answer families | Do not allow unsupported grading settings to be silently enabled. |
| Scan intake | Capture status, question mapping, uncertain or missing OCR regions | Show unresolved mapping; do not invent answers. |
| Grading | Operation ID, pending, candidate, denied, uncertain or review-needed outcome | A browser timeout is not a permission to resubmit a new operation. |
| Teacher review | Source answer/evidence, criterion marks, review reason, authorized decision | Distinguish journaled mark proposal from an official corrected result. |
| Result publication | Authorized released version and audience | Never display a candidate result to students as official. |
| Operations/support | Correlation ID and safe failure text | No secrets, full private provider traces or other tenants' answers in logs. |

## Coordinate the API with backend

The team must agree method, route, request/response schema, role checks, privacy filtering, original operation/idempotency key, error semantics, status polling and version fields. This repository **does not provide a public HTTP API**. Python class names are not HTTP route definitions. The backend/frontend acceptance fields and example non-authoritative payloads are in [Application API handoff](application_api_handoff.md).

## Demonstrate the failure path

A grading request times out after a provider call. The frontend keeps the original operation ID and asks the backend for a read-only status. It must not generate a new request identifier or silently rerun the grade. The backend must reconcile from durable history before allowing another effect.

See [Backend integration](backend_integration_guide.md) and [Failure and recovery](failure_and_recovery.md).
