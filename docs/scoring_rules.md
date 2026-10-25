# Scoring rules and numeric answers

The scoring layer accepts **approved** rubrics and verified criterion judgments. It never treats a model's suggested total as the authoritative mark.

For exact contract rules and failure behavior, use [Deterministic scoring kernel contract](scoring_kernel_contract.md) and [Exact scoring-number contract](scoring_numeric_contract.md). The current page is a short overview.

## Question scoring

`grading.scoring.reducer.reduce_question(...)` applies the compiled question policy: positive criterion credit, declared dependencies, gates, caps, deductions and the configured rounding rule. Unknown criteria, invalid rules, missing required evidence and out-of-range scores are rejected instead of silently adjusted.

`grading.contracts.scoring_decimal.ScoringDecimal` provides bounded exact decimal handling. The reducer and its arithmetic helpers avoid ordinary binary floating-point mark drift. `grading.scoring.paper_aggregation.aggregate_paper(...)` then checks the expected question inventory and combines compatible question scores; a missing, duplicate or foreign question cannot be silently added to the total.

## Numeric answers

The numeric evaluator is deliberately narrower than a general mathematics engine. The approved authority defines which scalar is expected and whether an exact or absolute-tolerance comparison applies. `resolve_numeric_authority(...)`, `admit_numeric_scalar(...)`, `evaluate_numeric_scalar(...)` and `evaluate_numeric_question_to_judgments(...)` handle the respective authority, evidence, comparison and criterion-projection steps.

For example, an admitted scalar answer of `8` can satisfy an approved exact answer of `8` for `48 ÷ 6`. This example does not establish that handwritten algebraic working, units or diagram measurements are automatically supported. A missing unit may be an academic error for some questions, but this unitless evaluator cannot safely invent a unit criterion.

## Test map

- `tests/unit/test_reducer_scoring_stages.py` covers the reduction stages.
- `tests/unit/test_arithmetic.py`, `test_rounding.py` and `tests/property/test_numeric_profile_hypothesis.py` check numerical invariants.
- `tests/integration/test_numeric_to_scoring_composition.py` covers numeric judgment-to-score flow.
- `tests/unit/test_paper_aggregation_provenance_regression.py` checks whole-paper identity and source consistency.

Exact numeric envelope and serialization fields are defined in `src/grading/contracts/scoring_decimal.py`, `src/grading/contracts/numeric_authority.py` and `src/grading/contracts/policy.py`.
