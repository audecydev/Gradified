# Capabilities and limitations

Gradified currently evaluates a bounded set of written-exam answers. The installed production entry point can use these capabilities only when its trusted sources and effect-handling adapters have been qualified.

| Answer or operation | Current support | Important boundary |
|---|---|---|
| Single-select choice | Deterministic evaluator and a separate whole-paper path | An admitted canonical selection and approved choice authority are required. |
| Descriptive text | Structured criterion judgments through a semantic provider | Model output is checked; scoring still follows the approved rubric. |
| Numeric scalar | Exact or approved absolute-tolerance comparison | The validated profile is unitless and bounded; it is not a symbolic math solver. |
| One DIRECT/NUMERIC paper | Documented supported mixed-family execution | Do not assume arbitrary combinations with CHOICE work as one supported operation. |
| FIRST, REGRADE, RETRY | Installed guarded paper operations | Enabled only with approved sources, original-operation custody and effect owners. |
| Teacher review | Original-bound decision journal | Recording `OVERRIDE_MARK` does not itself update the official grade. |
| Result release | Conditional release, write-ahead intent and recovery mechanisms | Real teacher, school, audience, database and restart behavior require external conformance. |

The current engine does **not** establish general diagram grading, symbolic expressions, alternative mathematical derivations, unit conversions, automatic correction of official marks, or universally calibrated review confidence. Representing a `FIGURE` or `MATH` block in OCR evidence does not make it gradable.

**Practical example:** a supported Science paper with descriptive responses and bounded numerical answers may produce a candidate mark. A Class 10 paper that combines those answers with diagrams and unbounded algebra must not be silently treated as entirely supported. The application should show unsupported or uncertain work for review and must never fabricate academic judgments.

See [Release scope](release_scope.md), [SRS traceability](srs_traceability.md) and [Project state](project_state.md).
