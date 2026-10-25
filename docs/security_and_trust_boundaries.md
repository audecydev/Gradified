# Security and trust boundaries

School decisions require authenticated, current authority from the backend. OCR text, model output, browser requests and generated references cannot grant school approval.

## Boundary rules

- Scope every read and conditional write to the exact school, exam, paper, submission, original operation and approved revision.
- Store secrets and private student material outside Git and test fixtures intended for publication.
- Validate the backend actor and policy again before durable effects; never assume a previous read proves current authorization.
- Keep result candidate and official publication permissions separate. Student visibility belongs to the authenticated release/read layer.
- Use bounded request sizes, explicit provider deadlines and reconciliation. Do not expose provider traces or full answers in browser error messages.
- Use real database uniqueness and atomic conditional operations across processes. A Python lock protects one instance only.
- Reject an invalid or contradictory receipt; do not upgrade `UNKNOWN` to success or simply retry a physical effect.

Threat tests must cover forged issuer, wrong tenant, source mutation between admission and commit, replayed provider receipts, duplicated release, malformed evidence and crash after a durable effect.

See [Backend integration](backend_integration_guide.md), [Provider accounting](provider_accounting.md) and [Official release](official_release.md).
