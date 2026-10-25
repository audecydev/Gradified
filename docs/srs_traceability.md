# SRS traceability

The software requirements describe the Gradified examination product. This repository supplies the grading-engine component, not the entire school web application. The table separates implemented local mechanisms from responsibilities that need real external systems or further academic development.

| Requirement area | Engine implementation | Remaining boundary |
|---|---|---|
| Paper and rubric preparation | Versioned rubric generation, linting, compilation and ACTIVE approval rules | Real school issuer, teacher workflow and approved source revisions |
| Student answer ingestion | Strict normalized OCR parser and question binding | Handwriting recognition, scan provenance and actual region mapping |
| Choice grading | Deterministic single-select evaluator; separate supported paper path | Real canonical selection and academic approval |
| Descriptive grading | DIRECT semantic boundary, judgment verification and deterministic scoring | Real model/provider plus held-out academic evaluation |
| Numerical grading | Bounded unitless exact/tolerance profile | Unit-aware, symbolic and stepwise derivations not established |
| Mixed examinations | Supported DIRECT/NUMERIC paper composition | Arbitrary CHOICE/DIRECT/NUMERIC/diagram combination not established |
| Attempt and regrade | Original-bound FIRST, REGRADE, RETRY, scoring CAS and recovery | Durable multiworker store and genuine source currentness |
| Risk and review | Deterministic observations and approved policy recommendations | Three calibrated confidence domains and automatic routing unproven |
| Teacher moderation | Original-bound decision journal including proposed override | Official corrected-result projection and complete moderation workflow |
| Feedback and grievance | Constrained feedback candidates and linked original operations | Full school grievance UI, policy and authentic source confirmations |
| Publication | Conditional release, write-ahead intent and prepared recovery | Real audience approval, atomic publication and student-facing service |
| Analytics, notifications, archival | Original result and audit metadata available | Product reporting, retention policy, message delivery and secure backup |
| Security and reliability | Fail-closed validations, bounded schemas, original-keyed recovery semantics | Authentication, production infrastructure, monitoring and operational conformance |

The grading engine meets only the source-tested subset shown here. It cannot be described as meeting every SRS academic capability until the missing evaluators and real school acceptance evidence are delivered. See [Release scope](release_scope.md) and [Acceptance checks](acceptance_checks.md).
