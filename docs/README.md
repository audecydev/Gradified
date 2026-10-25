# Grading Engine Documentation

The grading engine converts approved marking rules and admitted student answers into candidate scores. It keeps academic decisions, student evidence, model judgments, score arithmetic, review decisions, and official release authority separate.

## Start with the working system

1. [Capabilities and limitations](capabilities_and_limitations.md) defines supported answer types and unsupported academic work.
2. [Architecture](architecture.md) explains the complete path from an approved paper to a candidate result.
3. [Integration start guide](integration_start_here.md) gives the implementation order and a verified OCR admission example.
4. [Integration ports](integration_ports.md) identifies the actual Python entry points and required host behavior.
5. [Production wiring walkthrough](deployment_wiring_walkthrough.md) runs an actual supported mixed-paper operation with synthetic host ports.
6. [Integration test plan](integration_test_plan.md) shows how the connected system must be qualified.
7. [Project state](project_state.md) separates verified local source behavior from deployment evidence still required.

## Guides by responsibility

| Responsibility | Read |
|---|---|
| School identity, paper approval, database and publication | [Backend integration](backend_integration_guide.md) |
| Handwriting capture and question-region mapping | [OCR integration](ocr_integration_guide.md) |
| Language-model grading | [Semantic provider integration](semantic_provider_integration_guide.md) |
| Trusted textbook and model-answer retrieval | [Reference integration](reference_integration_guide.md) |
| Browser screens and presentation permissions | [Frontend integration](frontend_integration_guide.md) |
| School-specific policies | [School policy setup](school_policy_setup.md) |
| Risk, review, retry and release | [Grading operations](grading_operation_flow.md) and [Failure and recovery](failure_and_recovery.md) |
| Test ownership, evidence and completion decisions | [Testing](testing.md), [Acceptance checks](acceptance_checks.md) and [SRS traceability](srs_traceability.md) |

## Engineering references

| Area | Reference |
|---|---|
| Scoring overview | [Scoring rules](scoring_rules.md) |
| Full question and paper scoring invariants | [Deterministic scoring kernel contract](scoring_kernel_contract.md) |
| Exact decimal representation, arithmetic and rounding | [Exact scoring-number contract](scoring_numeric_contract.md) |
| Single-select choice and rejection semantics | [Single-select choice evaluation contract](choice_evaluation_contract.md) |
| Rubric approval, regeneration and currentness | [Rubrics and academic authority](rubrics_and_authority.md) |
| Question type selection and model results | [Evaluation and provider contracts](evaluation_and_provider_contracts.md) |
| Answer evidence and question binding | [Evidence and question binding](evidence_and_question_binding.md) |
| Whole-paper composition, attempt identity and conditional commit | [Paper execution and persistence](paper_execution_and_persistence.md) |
| Retry and original-operation recovery | [Attempt and recovery contracts](attempt_and_recovery_contracts.md) |
| Teacher review, recommendations and feedback | [Review and feedback](review_and_feedback.md) |
| Release and publication protection | [Official release](official_release.md) |
| Physical provider activity and billing | [Provider accounting](provider_accounting.md) |
| Benchmark inputs and academic-quality claims | [Benchmark qualification](benchmark_qualification.md) |
| Trust and data isolation | [Security and trust boundaries](security_and_trust_boundaries.md) |
| Installed source and top-level declaration inventory | [Source reference](source_reference.md) |
| Exact backend/provider method and record signatures | [Host-facing port signatures](port_signatures.md) |
| Backend/frontend API ownership and acceptance | [Application API handoff](application_api_handoff.md) |
| Exact source qualification and Git checks | [Source qualification](source_qualification.md) |

The Python symbols in the reference documents are spelled exactly as they appear in `src/grading/`. Internal class names are not evidence that the corresponding external integration has been accepted.
