# Integration requirements

The grading engine assumes the host application supplies independently trustworthy facts and durable effects. Connecting a class with the right method names is insufficient.

| Area | Required evidence from the receiving team |
|---|---|
| Backend | Tenant-aware authenticated actor; approved paper/rubric/current policy; original request IDs; durable atomic and unique conditional writes. |
| OCR | Source artifact identity, real page/question mapping, block state, coordinates when known, measured or unavailable confidence, bounded normalized JSON. |
| Provider | Approved model/runtime identity, canonical request/response, structured criterion judgments, physical attempt accounting and uncertain-call reconciliation. |
| References | Authorized school source, exact reference version, bounded excerpts and provenance for every admitted chunk. |
| Frontend | Only authenticated backend API access; candidate and published result segregation; review and unknown states displayed truthfully. |
| Operations | No retry of unknown physical effects without original-keyed read-only reconciliation; no score publication without current issuer/audience approval. |

See [Integration ports](integration_ports.md) for exact declarations, [Security](security_and_trust_boundaries.md) for trust boundaries and [Acceptance checks](acceptance_checks.md) for tests that must pass.
