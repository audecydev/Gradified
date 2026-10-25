# Failure and recovery

A technical failure is not an incorrect student answer. A timeout after a remote provider or database operation may mean the operation happened but its acknowledgment was lost.

| Observed situation | Required treatment |
|---|---|
| Invalid paper, rubric, tenant or evidence identity | Reject before grading or publication effect. |
| Unsupported evaluator family or missing approved policy | Do not route to a convenient alternative evaluator. |
| Invalid model judgment or unknown criterion | Reject the judgment; never trust provider-supplied totals. |
| Provider timeout after dispatch | Preserve original attempt identity and physical accounting uncertainty. Reconcile before new contact. |
| Concurrent or conflicting scored commit | Use authoritative conditional storage; do not replace an original candidate blindly. |
| Lost scoring acknowledgment | Read fixed-original status from durable storage; avoid replaying an effect without proof. |
| Teacher decision write acknowledgment lost | Reconcile original decision journal using its exact decision identity. |
| Release prepared before crash | Resolve the persisted original intent using the separate prepared-release path; do not republish by regrading. |
| Source revoked before effect | Deny under the backend's effect-time authority. |

The engine includes in-memory and synthetic connected recovery tests. These do not establish atomicity across real backend workers or across a network partition. The backend must demonstrate durability and idempotency using its real persistence and provider adapters.

See [Attempt and recovery contracts](attempt_and_recovery_contracts.md) and [Integration test plan](integration_test_plan.md).
