# Gradified Grading Engine

Gradified's grading engine applies **school-approved marking rules** to **admitted student answer evidence** and produces checked candidate scores. It handles supported answer evaluation, exact mark calculation, guarded paper operations and recovery. The engine is part of the Gradified examination product; it is not the full school management application.

## Start here

1. [Documentation index](docs/README.md) — all integration guides and component references.
2. [Capabilities and limitations](docs/capabilities_and_limitations.md) — what can and cannot be graded automatically.
3. [Architecture](docs/architecture.md) — how grading authority, evidence, evaluation and scoring fit together.
4. [Integration start guide](docs/integration_start_here.md) — connect an actual supported examination in the right order.
5. [Integration test plan](docs/integration_test_plan.md) — reproduce source tests and qualify the real adapters.

## What is implemented

- Versioned rubric admission, linting, compilation, approval and lifecycle checks.
- Deterministic question and paper scoring using bounded exact decimal arithmetic.
- Single-select **CHOICE**, supported **DIRECT** semantic text and bounded unitless **NUMERIC** evaluation.
- Supported DIRECT/NUMERIC paper composition and a separate CHOICE whole-paper path.
- Guarded FIRST, REGRADE and RETRY mechanisms with original attempt custody, provider accounting and conditional result persistence.
- Teacher review-decision custody, governed feedback and separately authorized result-release mechanisms.
- Normalized OCR evidence admission and question/source binding.

### How grading works

```text
Approved school paper, rubric, policy and reference sources
                            +
               Normalized OCR answer evidence
                            |
                            v
             Current authority and evidence checks
                            |
                            v
               Supported evaluator selection
                            |
                            v
             Verified criterion-level judgments
                            |
                            v
             Deterministic scores and paper total
                            |
                            v
                Candidate result and audit
                            |
                            v
             Separate school review and release
```

The language model may interpret supported descriptive answers, but does not own the final numerical scoring rules. A candidate result is **not** permission for student-visible publication.

## Limits that matter for a real examination

The verified engine scope does not establish general symbolic mathematics, alternative stepwise derivations, unit-aware grading, diagram assessment, or arbitrary combinations of CHOICE, DIRECT and NUMERIC in one paper. Calibrated automatic confidence decisions and a complete official teacher-corrected result projection also remain open. Real OCR, authenticated school approval, billing, database durability and official publication must be qualified by the connected teams.

## Repository layout

| Path | Purpose |
|---|---|
| `src/grading/` | Grading implementation, contracts, scoring, rubrics and integration boundaries |
| `tests/` | Unit, contract, integration and property tests |
| `schemas/` | Normalized answer evidence JSON Schema |
| `docs/` | Integration guides, exact source references and acceptance checks |

For strict supported paper operations, the backend installs `ProductionPaperOperations` from `src/grading/integration/production_paper_operations.py`. The backend must supply authenticated sources and durable effects; the browser does not call this Python class directly.

## Run verification

Python 3.11 is the source qualification baseline. Install pinned test dependencies:

```sh
python -m pip install -r requirements-test.txt
python -m pip check
PYTHONPATH=src:. python -m pytest -q
```

On Windows Command Prompt:

```bat
set "PYTHONPATH=src;."
python -m pytest -q
```

Runnable **OCR admission** and **synthetic supported-paper** examples are available:

```sh
PYTHONPATH=src:. python docs/examples/ocr_admission_demo.py
PYTHONPATH=src:. python docs/examples/paper_operation_demo.py
```

The paper example executes a real engine operation with repository test-fixture ports. It does not grant school authority or publish a result. Previous Linux and Windows regression runs qualified different earlier source snapshots; [Testing](docs/testing.md) explains the evidence without treating it as same-tree production certification.

## Teams and responsibilities

| Team | Guide |
|---|---|
| Backend and persistence | [Backend integration](docs/backend_integration_guide.md) |
| OCR | [OCR integration](docs/ocr_integration_guide.md) |
| Semantic provider | [Semantic provider integration](docs/semantic_provider_integration_guide.md) |
| Reference retrieval | [Reference integration](docs/reference_integration_guide.md) |
| Frontend | [Frontend integration](docs/frontend_integration_guide.md) |
| Integration and QA | [Integration test plan](docs/integration_test_plan.md) |

Never commit school-private answers, secrets or provider credentials. Never infer academic approval from OCR or model output, retry an unknown physical effect blindly, or publish an unapproved candidate result. No public REST API or project redistribution license is defined in this repository.
