# Rubrics and academic authority

A rubric describes how many marks a question can earn and what evidence supports those marks. The model may propose a rubric, but a model proposal is not school approval.

## Lifecycle

`grading.rubric.generator` produces candidates; `grading.rubric.linter` checks content; `grading.rubric.compiler` compiles deterministic scoring authority. `grading.rubric.lifecycle` handles versioned drafts, explicit teacher approval, ACTIVE use and retirement. An ACTIVE rubric is the scoring authority only when the backend independently confirms its exact source identity and revision.

The engine keeps content hashes and revision references so a paper cannot quietly use a different marking scheme. Changes after grading require new authorized versions and, where applicable, a separately approved REGRADE. A teacher's corrected score does not itself rewrite the original rubric.

## Regeneration

`grading.rubric.regeneration` compares candidate changes with existing authored content. `grading.rubric.regeneration_custody` requires an authorized read and a conditional draft write. Concurrent or conflicting edits must not be merged blindly or promoted to ACTIVE without approval.

## Integration evidence

The backend must record who approved the rubric, which paper/question it covers, the exact version, currentness at use and the stored content fingerprint. The reference service must bind approved textbook/model-answer sources to their versions. A passing in-memory lifecycle test does not authenticate a real teacher.

See [School policy setup](school_policy_setup.md) and [Reference integration](reference_integration_guide.md). Source tests include `tests/unit/test_rubric_lifecycle.py` and `tests/integration/test_rubric_regeneration_custody.py`.
