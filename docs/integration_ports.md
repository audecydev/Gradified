# Integration ports and installation

A port is a Python interface implemented by a trusted host service. The engine can check its data shape and installation compatibility. It cannot infer that the implementation authenticates teachers, uses atomic transactions or returns genuine vendor receipts.

## Mandatory starting points

| Purpose | Source | Actual entry |
|---|---|---|
| Normalize OCR evidence | `src/grading/integration/evidence_ingress.py` | `parse_normalized_evidence_payload(...)` |
| Bind question evidence | `src/grading/integration/evaluation_binding.py` | `bind_question_evaluation_inputs(...)` |
| Admit a current whole paper | `src/grading/integration/paper_readiness_admission.py` | `ProductionPaperAdmissionComposer.admit(...)` |
| Grade an admitted paper | `src/grading/integration/production_paper_operations.py` | `ProductionPaperOperations.execute(...)` |
| Conditionally release result | `src/grading/integration/official_result_release.py` | `ProductionGovernedResultRelease` |

## Core backend ports

| Host responsibility | Installed source interface |
|---|---|
| Authenticated actor | `IdentityAuthority.current_actor()` |
| Authorized paper selection | `PaperSelectionAuthority.authorize_paper(...)` |
| Current paper answer readiness | `PaperAnswerAuthority.resolve_paper_readiness(...)` |
| Paper revision check | `PaperRevisionAuthority.confirm_paper_revision(...)` |
| Conditional original attempt + scored effect | `QualifiedJointEffectOwner` |
| Durable scored write and recovery | `AtomicWholePaperResultStateAuditStore` |
| Original release intent | `QualifiedReleaseIntentCustody` |
| Conditional release effect | `QualifiedConditionalResultRelease` |

The first four interfaces are declared in `integration/authorized_preparation.py` and `integration/paper_readiness_admission.py`; the latter four are declared in `integration/joint_effect_authority.py`, `integration/whole_paper_cas.py` and `integration/official_result_release.py`.

## Constructor compatibility

`ProductionPaperOperations.__init__` requires an **exact** `ProductionPaperAdmissionComposer`, `ProductionPaperPromotion`, enabled `PaperOperationKind` tuple, numeric limits, and an installed lifecycle or retry owner depending on the enabled operation. The constructor checks shared underlying attempt/CAS/executor owners and real DIRECT route dependencies. It does not accept an arbitrary mock shape as proof of production suitability.

Exact selected constructor, method and record signatures are reproduced from source in [Host-facing port signatures](port_signatures.md); the full source inventory is in [Source reference](source_reference.md). Read their field contracts directly before wiring an adapter. There is deliberately no generic sample constructor using fabricated school-authorization values: the required qualified sources must be supplied by the receiving backend.

## External acceptance

Each port needs a real conformance test using its true store/issuer/provider. Capture evidence of authenticated currentness, revocation, exact source revision, multiworker atomicity, physical activity, lost-acknowledgment recovery and authorized audience disclosure. A matching Python Protocol alone is not enough.
