# Gradified Grading Core

Gradified's grading core converts **school-approved grading rules** and **student answer evidence** into **checked, deterministic candidate scores**.

This repository contains the completed grading-core work for the current Release 1 integration scope. It is ready for integration testing with OCR, backend/workflow, reference-retrieval, and semantic-model systems.

This is **not the complete Gradified production platform**. Authentication, production persistence, official result publication, and the real OCR, model-provider, and reference-retrieval adapters belong to the surrounding platform and integration work.

## Start here

If you are joining the project for the first time, read these documents in this order:

1. [`docs/README.md`](docs/README.md) — explains what every document is for.
2. [`docs/INTEGRATION_START_HERE.md`](docs/INTEGRATION_START_HERE.md) — simple overview of the system and integration order.
3. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Release 1 target architecture, current implemented path, and open boundaries.
4. [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md) — explains where source code, tests, contracts, and support files live.
5. [`docs/INTEGRATION_REQUIREMENTS.md`](docs/INTEGRATION_REQUIREMENTS.md) — requirements each external integration must satisfy.
6. [`docs/INTEGRATION_TEST_PLAN.md`](docs/INTEGRATION_TEST_PLAN.md) — step-by-step integration tests and expected results.
7. Read the guide for the system being integrated:
   - [`docs/OCR_INTEGRATION_GUIDE.md`](docs/OCR_INTEGRATION_GUIDE.md)
   - [`docs/BACKEND_INTEGRATION_GUIDE.md`](docs/BACKEND_INTEGRATION_GUIDE.md)
   - [`docs/REFERENCE_INTEGRATION_GUIDE.md`](docs/REFERENCE_INTEGRATION_GUIDE.md)
   - [`docs/SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md`](docs/SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md)
8. [`docs/SCORING_KERNEL_BLACK_BOX.md`](docs/SCORING_KERNEL_BLACK_BOX.md) — scoring-kernel rules and invariants.
9. [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — what exists now.
10. [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — remaining Release 1 work.
11. [`docs/TESTING.md`](docs/TESTING.md) — verification scope, test history, and what the tests do not prove.

## What is implemented

The current repository includes:

- deterministic question scoring and paper aggregation;
- exact decimal score handling and controlled rounding;
- rubric generation boundaries, linting, deterministic compilation, fingerprinting, versioning, teacher approval, and ACTIVE lifecycle controls;
- ACTIVE question-authority resolution;
- evidence contracts and evidence-to-judgment verification;
- deterministic risk-observation extraction for the implemented observation profile;
- single-select CHOICE evaluation;
- DIRECT text semantic evaluation through a bounded provider interface;
- bounded unitless NUMERIC authority, evidence admission, deterministic comparison, and judgment composition;
- exact versioned evaluator-capability-record resolution;
- bounded reference-context materialization with provenance preservation.

The grading core is designed so that external systems provide trusted inputs through explicit boundaries. External systems do not become scoring authority simply because they connect to the core.

## Main grading flow

```text
school-approved grading authority
        +
student answer evidence
        ↓
pre-evaluation validation
        ↓
supported evaluator path
        ↓
criterion judgments
        ↓
evidence and judgment verification
        ↓
deterministic question scoring
        ↓
deterministic paper aggregation
        ↓
candidate result
        ↓
backend review / publication workflow
```

The model may interpret content, but it does not own the final numerical score.

The backend may publish an official result, but the grading core only produces a candidate result.

## Current supported evaluator paths

### CHOICE

Single-select choice answers are evaluated deterministically against the approved authority.

### DIRECT semantic text

Supported text criteria can be evaluated through the semantic-provider boundary. Provider output is admitted into structured criterion judgments and still passes through verification and deterministic scoring.

### NUMERIC

The implemented numeric path supports a deliberately bounded unitless numeric profile:

```text
approved numeric authority
        ↓
student numeric evidence admission
        ↓
deterministic exact / absolute-tolerance comparison
        ↓
approved criterion projection
        ↓
criterion judgment
        ↓
verification and deterministic scoring
```

Unsupported numeric formats or semantics do not silently become academic judgments.

## Reference context

The repository includes a reference-context boundary that preserves source identity, source version, and provenance information.

It does **not** implement the production retrieval system itself.

A real reference integration must still prove tenant/version isolation, approved-source access, and correct provenance behavior.

## Architecture rule

The following responsibilities stay separate:

- **School / teacher authority** defines the approved grading content.
- **OCR** provides student evidence.
- **Evaluators** interpret supported answer types.
- **Verification** checks evidence and judgment relationships.
- **Deterministic scoring code** calculates marks.
- **Backend / institution policy** controls official publication.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full target architecture and the narrower path implemented today.

## What is still open

The main Release 1 gaps are:

- versioned evaluator-selection/routing policy;
- evaluator-execution and attempt provenance through the complete workflow;
- real OCR adapter against the OCR team's production payload;
- real backend/workflow adapter, persistence, idempotency, and transaction behavior;
- real reference-retrieval adapter with tenant/version isolation;
- production semantic-provider adapter, telemetry, and benchmark evidence;
- recommendation, review, regrade, and publication workflow completion;
- units and broader mathematical / derivation / composite evaluator support;
- real subjective-paper and numeric/math-paper end-to-end runs;
- held-out academic-quality validation and production reliability evidence.

A green core test suite proves the tested grading-core behavior. It does not prove that an external OCR, backend, model provider, or retrieval system is correct.

## Testing

The qualified environment is:

- CPython 3.11.9
- pytest 9.1.1
- Hypothesis 6.167.1

The complete integration baseline contains **1499 tests**.

Before a publication or integration candidate is accepted, the exact candidate must pass the full suite:

```bat
python -m pip check
python -m pytest -q
```

Expected result:

```text
1499 passed
```

See [`docs/TESTING.md`](docs/TESTING.md) for the detailed test history and limits of the evidence.

## Repository layout

```text
src/grading/        grading-core source
tests/contracts/    contract tests
tests/unit/         focused unit tests
tests/integration/  cross-component tests
tests/property/     property-based invariant tests
tests/support/      shared test-only helpers
docs/               engineering, architecture, integration, and verification documentation
```

The Python modules directly under `src/grading/` are top-level grading capabilities and orchestration modules. Cohesive subsystems such as contracts, rubric logic, scoring, providers, and verification have their own subpackages.

See [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md) for the full explanation.

## Integration safety rules

- Do not place secrets, API keys, private student data, or school-private reference material in this repository.
- Do not derive tenant authority from student content or model output.
- Do not allow OCR or model output to publish grades directly.
- Do not convert technical failures into student mistakes.
- Do not change frozen scoring behavior merely to make an external integration easier.
- Adapt external systems at the documented integration boundaries.
- Stop safely when required authority, evidence, capability, or provenance is missing or invalid.

## License

No project license has been established in this repository. Consult the repository owner before reuse or redistribution outside the Gradified project.
