# Source qualification and publication

The corrected documentation is tied to the installed Python source and tracked-file inventory. The source is not automatically production-certified merely because the documentation is consistent.

Before any Git stage or commit, independently record the resulting working-tree content tree, run the full tests on the target operating systems, and verify all intended paths are the only staged changes.

**Windows Git case-folding warning:** this integration contains document paths renamed from uppercase to lowercase. The original repository records `core.ignorecase` behavior, and a normal `git add -A` in a Git worktree configured as case-insensitive may fail to stage some case-only name changes. A disposable alternate-index rehearsal with `core.ignorecase=false` staged the intended paths and produced the expected tree. Do not change the protected index during documentation installation; at the later approved staging step, inspect the complete staged path inventory and verify its Git tree before committing. Reconcile the branch against the original published GitHub branch without publishing unpublished internal commits accidentally.

Evidence from in-memory tests must be labelled **source behavior**. Evidence from genuine authenticated school services, the OCR vendor, the provider, the database and student-facing publication must be labelled **integration behavior** and retained in the receiving team's controlled evidence storage.

Source history, working packages and verification logs belong in the project's `artifacts` location, not in the Git source tree. Only review-approved source, tests, schemas and current engineering documents should be committed. See [Acceptance checks](acceptance_checks.md).
