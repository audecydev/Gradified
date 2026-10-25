# Project state

Gradified's grading-engine source is installed in the linked local worktree `grading-engine-integration` on branch `integration/release1-grading-engine`. This worktree and the protected `repository` checkout share the **same Git repository and commit history**. They are not two independent projects. The protected checkout remains on the original development branch at commit `99df7eea272e861467135fc014ab1e3f392fed1a` according to the latest Windows verification supplied by the developer.

The integration worktree contains the current source and documentation as **uncommitted changes**. Nothing in the installation or editorial update stages, commits, publishes, or pushes those changes.

## What is included

The integrated grading engine provides approved rubric and evidence checks, supported CHOICE, DIRECT and bounded unitless NUMERIC evaluation, deterministic question/paper scoring, supported paper execution, attempt continuity, regrade/retry controls, review-decision custody, and guarded release interfaces. Refer to [Capabilities and limitations](capabilities_and_limitations.md) for supported combinations and academic limits.

The documentation includes a complete source declaration map, runnable OCR and synthetic paper examples, backend/OCR/frontend/provider integration responsibilities, scoring contracts and integration tests.

## Source naming and compatibility

The integration work included professional source filenames, test filenames and a subsequent rename of 40 Python declarations. Imports, affected tests and source references were updated together. Code using the previous Python names must update its imports. No external backend consumer of those older names has been independently qualified.

The repository-language correction updates comments, docstrings, user-facing error messages, test assertions that match those messages, and verification metadata. Exact scoring-traceability test identifiers are retained. The change preserves persisted operation names, enum values, request IDs, exception classes and grading rules. Error-message text is diagnostic, not a stable application protocol; connected clients should use typed outcomes and error classes.

The exact source identity is recorded in the external installation manifest and postcheck receipt. The complete current Git tree is not embedded in this tracked file because recording that hash here would change the tree itself.

## Test evidence

The renamed and API-adjusted earlier source snapshots passed full Linux non-property regression campaigns of 5,216 tests; a prior engine snapshot passed 5,242 Windows tests with property cases. These are separate snapshots. The exact current candidate still requires native Windows/property qualification and real connected-service acceptance. See [Testing](testing.md).

## Work that the connected teams must qualify

- Authentic OCR mapping from submitted pages to individual questions, with uncertainty and source provenance.
- Current school, actor, paper, rubric, capability and policy authorization at each effect boundary.
- Provider identity, actual physical attempt accounting, usage receipts and recovery after lost acknowledgments.
- Durable storage and conditional score commits under concurrent workers, retries and restart.
- Genuine teacher decision flow, report publication authorization and student-visible disclosure.
- Held-out academic evaluation for supported written and numerical papers. General mathematical derivations, units, diagram grading and arbitrary all-family papers are **not established as supported** by this source.

The grading engine is ready for controlled integration work within its verified capabilities. It is **not** a certified complete school examination product. See [Integration test plan](integration_test_plan.md) and [Acceptance checks](acceptance_checks.md) for the remaining evidence.
