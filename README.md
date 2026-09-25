# Gradified Grading Core

Gradified's grading core turns **school-authorized grading rules** and **admitted student evidence** into **deterministic, auditable candidate scores**.

This repository contains the verified internal grading core for the currently completed Release 1 scope. It is ready for **integration testing** with OCR, backend/workflow, reference-retrieval, and semantic-provider systems.

It is **not** the complete production Gradified platform. In particular, this repository does not by itself provide authentication, database persistence, official-result publication, a production OCR adapter, a production model-provider adapter, or a production reference-retrieval adapter.

## Start here

If you are new to the project, read these documents in this order:

1. [`docs/README.md`](docs/README.md) — documentation map: what every document is for and who should read it.
2. [`docs/INTEGRATION_START_HERE.md`](docs/INTEGRATION_START_HERE.md) — plain-language system overview and integration order.
3. [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md) — where code, contracts, tests, and engineering documents live.
4. [`docs/INTEGRATION_TEST_PLAN.md`](docs/INTEGRATION_TEST_PLAN.md) — step-by-step tests the integration team should run.
5. Your integration-specific guide:
   - [`docs/OCR_INTEGRATION_GUIDE.md`](docs/OCR_INTEGRATION_GUIDE.md)
   - [`docs/BACKEND_INTEGRATION_GUIDE.md`](docs/BACKEND_INTEGRATION_GUIDE.md)
   - [`docs/REFERENCE_INTEGRATION_GUIDE.md`](docs/REFERENCE_INTEGRATION_GUIDE.md)
   - [`docs/SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md`](docs/SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md)
6. [`docs/SCORING_KERNEL_BLACK_BOX.md`](docs/SCORING_KERNEL_BLACK_BOX.md) — deterministic scoring boundary and invariants.
7. [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) and [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — exact engineering state and remaining Release 1 work.
8. [`docs/TESTING.md`](docs/TESTING.md) — detailed verification history and non-claims.

## What is implemented and frozen

The completed scope includes:

- deterministic question scoring and paper aggregation;
- exact decimal scoring profile and controlled rounding;
- rubric authoring safety, linting, compilation, fingerprinting, versioning, and ACTIVE lifecycle controls;
- ACTIVE question-authority resolution;
- evidence contracts and evidence-to-judgment verification;
- synthetic execution composition through verification, deterministic question scoring, and deterministic paper aggregation;
- deterministic risk-observation extraction for the currently supported observation profile;
- single-select CHOICE evaluation;
- DIRECT text semantic evaluation through a provider boundary with strict response admission;
- bounded unitless NUMERIC authority, evidence admission, deterministic comparison, and judgment composition;
- exact evaluator-capability-record resolution;
- reference-context materialization and provenance preservation through a backend-independent source boundary.

The verified Release 1 integration baseline before the public documentation/privacy-normalization step is:

- qualified environment: Windows x64, CPython 3.11.9
- pytest: 9.1.1
- Hypothesis: 6.167.1
- complete qualified regression: **1499 / 1499 passed**
- dependency check: clean
- working tree at verification: clean

Exact private forensic commit identities are retained in the private delivery/evidence package rather than used as public-history authority.

This publication branch does not modify production grading source or scoring behavior. It adds public integration documentation and performs one test-only repository-structure cleanup: shared pytest helper modules live under `tests/support/` instead of loose at the `tests/` root. The helper move does not change grading semantics and must still pass the complete qualified regression before push.

## Important architectural rule

A model, OCR system, backend, or retrieval system does **not** become scoring authority merely because it integrates with this core.

The intended flow is:

```text
trusted workflow / school authority
        ↓
ACTIVE grading authority
        ↓
admitted student evidence
        ↓
bounded evaluator capability
        ↓
criterion judgments
        ↓
evidence verification
        ↓
deterministic scoring reducer
        ↓
deterministic paper aggregation
        ↓
candidate result
        ↓
backend review / publication workflow
```

The numerical scoring reducer remains the only authority that calculates authoritative marks inside the grading core.

## What is still open

The major Release 1 gaps are intentionally visible:

- exact question-classification → evaluator-capability routing policy;
- evaluator-execution / attempt provenance through the complete workflow;
- real OCR adapter against real OCR payloads;
- real backend/workflow adapter, persistence, idempotency, and transaction behavior;
- real reference-retrieval adapter with tenant/version isolation and provenance conformance;
- production semantic-provider adapter, cost/latency telemetry, and benchmark evidence;
- recommendation/review/regrade/publication workflow completion;
- UNIT support and broader math/derivation/composite capabilities;
- real subjective-paper and numeric/math-paper end-to-end runs;
- held-out academic-quality validation and production reliability evidence.

Do not interpret a green core regression as proof that those external systems are correct.

## Run the verified test suite

From the repository root on Windows:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-test.txt
python -m pytest -q
```

The qualified baseline uses **CPython 3.11.9** and the exact package versions in `requirements-test.txt`.

For the integration handoff baseline, the expected complete result is:

```text
1499 passed
```

A different Python/dependency environment is useful for extra compatibility testing, but it is not the qualified baseline unless separately verified.

## Repository usage notes

- The project is currently a Python grading-core library plus tests and engineering contracts, not a deployable HTTP service.
- Run tests from the repository root; pytest adds `src` to the Python path through `pyproject.toml`.
- Do not place secrets, private student data, school-private reference material, `.env` files, or production credentials in this repository.
- Do not change frozen scoring behavior merely to make an external integration easier. Adapt external systems at their explicit integration boundaries.

## License

No project license has been established in this repository. Consult the repository owner before reuse or redistribution outside the Gradified project.
