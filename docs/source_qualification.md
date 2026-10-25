# Source qualification and publication

## Published baseline (historical qualification)

The published baseline on `feature/Scoring-Algo-Engine` is commit `41fd7756a37e446a79051f349629f1fc514f2991`, with **468 project files** and Git tree `9fbcdb3fa2b93b20658edc331ce254e0b79a5dfa`. Pinned CPython 3.11.9 native Windows qualification passed 5,242 tests including 26 property tests, with cache-isolated execution and unchanged source identity. This does not prove real-system or academic acceptance; see [Testing](testing.md) and [Acceptance checks](acceptance_checks.md).

## Future grading-breadth changes

1. Base new public-bound work on the **current published public branch**, never import unpublished local private-development commits as parent ancestry.
2. Review actual source, tests and affected docs; do not silently alter frozen scoring, persisted names, original-operation custody, tenant authority or result publication policy.
3. Run capability-focused tests throughout implementation. On final release candidate, independently hash the exact Git tree and execute pinned Windows/Linux/property/adverse and academic/integration conformance tests appropriate to supported scope.
4. On Windows, verify case-sensitive and case-only paths explicitly before committing; ordinary `git add -A` under `core.ignorecase=true` can miss a case-only rename. Confirm the **actual proposed commit tree**, complete staged-path inventory, parent ancestry and commit metadata.
5. Preserve private artifacts, credentials, backups, student records and qualification logs outside the Git source. Only the reviewed code, tests, schemas and current engineering docs belong in the source commit.
6. Verify the published remote HEAD, parent and tree **after** any separately approved push. Never use force, mirror or push-all merely to bypass source or history checks.

Source-test evidence is **source behavior**. Authenticated school authority, live OCR, provider, database, student disclosure and teacher-labelled academic measurements require their own **integration/academic evidence**. The published baseline does not automatically qualify future feature additions.
