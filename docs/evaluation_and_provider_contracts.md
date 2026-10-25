# Evaluation and provider contracts

A question is evaluated only when an admitted classification, school-approved selection policy, exact capability record and qualified runtime permit that route.

## Method selection

`grading.evaluator_selection.resolve_question_evaluator_selection(...)` resolves a bounded approved choice. `integration/selector_admission.py`, `integration/execution_eligibility.py` and `integration/evaluator_execution_binding.py` guard the selected capability and runtime against foreign identity and unsupported modality.

A convenient model cannot silently replace a missing approved evaluator. Where policy, capability, modality or currentness is unresolved, execution must fail safely.

See [Single-select choice evaluation contract](choice_evaluation_contract.md) for exact option admission, evidence binding, judgment fields and rejection semantics.

## Supported paths

| Family | Implementation | Output boundary |
|---|---|---|
| CHOICE | `grading.choice_evaluator.evaluate_single_select_choice` | Judgments based on admitted canonical selection and approved authority. |
| DIRECT | `grading.semantic_evaluator` with `integration/direct_provider_route.py` | Model response admitted and verified against criteria/evidence. |
| NUMERIC | `grading.numeric_evaluator` and `grading.numeric_judgments` | Bounded exact/tolerance scalar outcome projected to criteria. |

`integration/paper_family_evaluation.py` composes documented DIRECT/NUMERIC question families; `integration/whole_paper_choice_execution.py` owns the separate CHOICE paper route. Do not infer general diagram or symbolic math grading from the presence of a modality token.

## Provider failure handling

A malformed response cannot create marks; provider timeout after a physical dispatch cannot be treated as proof of no dispatch. The installed physical-accounting and original-operation recovery contracts determine whether another effect is permissible. See [Provider accounting](provider_accounting.md).
