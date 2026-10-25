# Grading operation flow

The production paper entry accepts `PaperAdmissionRequest` and one enabled `PaperOperationKind`: `FIRST`, `REGRADE` or `RETRY`. The root is `ProductionPaperOperations.execute(request=..., kind=...)` in `src/grading/integration/production_paper_operations.py`.

## FIRST

The backend proves an authenticated, currently approved paper and source readiness. The admission layer fixes the question inventory and evaluator route. The installed executor claims the original-bound attempt, contacts providers where required, validates judgments, calculates marks and commits a candidate with a conditional scored-result operation.

## REGRADE

A current source must authorize a separate grading decision against the correct original paper and request history. The original result remains auditable; a regrade does not silently overwrite it. Source versions and authority are checked again before effects.

## RETRY

Retry is not a fresh exam. The engine requires a supported absence/recovery claim tied to the original operation. An unknown physical attempt must be reconciled before any new effect is allowed. A returned observation does not authorize publication.

## Teacher review and release

A teacher review decision is appended to its exact original result under current source permission. A recorded proposed mark is not an official revision. Release uses separately qualified original intent custody, conditional writer and current audience/teacher policy; recovery reads a fixed original intent rather than rerunning grading.

## State transitions to show in the application

Report request accepted, running, candidate available, review required, denied and uncertain/recovery-needed distinctly. The backend must map these to its real job-state contract; the engine's state vocabulary is defined in `src/grading/contracts/job_state.py`.

See [Paper execution](paper_execution_and_persistence.md), [Attempt recovery](attempt_and_recovery_contracts.md) and [Official release](official_release.md).
