# Repository structure

| Path | What belongs there |
|---|---|
| `src/grading/contracts/` | Immutable contracts for inputs, rubrics, evidence, policy, scores and errors. |
| `src/grading/scoring/` | Decimal arithmetic, deterministic question reducer and paper aggregation. |
| `src/grading/rubric/` | Rubric generation, validation, compilation, approval and regeneration custody. |
| `src/grading/integration/` | Trusted input admission, evaluator selection, paper operations, review and recovery. |
| `src/grading/providers/` | Controlled provider calls, canonical transport and physical-accounting observations. |
| `src/grading/benchmark/` | Bounded offline comparison and teacher-label evidence; not a live grading endpoint. |
| `src/grading/verification/` | Checks that evaluated criterion judgments match student evidence and approved context. |
| `tests/contracts/` | Contract and invalid-input checks. |
| `tests/unit/` | Scoring and component behavior. |
| `tests/integration/` | Cross-component and adversarial operation tests. |
| `tests/property/` | Generated invariant checks (requires Hypothesis). |
| `schemas/` | JSON Schema for normalized answer evidence. |
| `docs/` | Installation, responsibility, test and component reference material. |

The root `README.md` is the entry point. `docs/README.md` is the documentation index. Public Python names and serialization identifiers must be preserved for compatibility; file names have been normalized without changing frozen protocol values.
