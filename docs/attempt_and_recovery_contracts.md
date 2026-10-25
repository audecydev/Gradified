# Attempt identity and recovery

Every effectful grading operation must remain tied to its original request. This prevents a retry from being mistaken for an entirely new examination and helps reconcile a provider or database action whose acknowledgment was lost.

## Attempt reservation and lineage

`integration/attempt_authority.py` defines `ClaimedAttemptAllocator`, fixed reservation requests and recovery facts. `integration/attempt_lineage.py` maintains legal transition observations and audit receipt checks. `integration/attempt_history.py` and `integration/whole_paper_attempt_custody.py` preserve the original decision and paper attempt association.

The backend must supply immutable original-request identity and a durable authoritative record. The engine must not infer a new original from OCR text, provider output or the browser's local retry.

## Conditional scoring and reconciliation

`integration/whole_paper_cas.py` owns conditional scored-result state and read-only recovery, while `integration/joint_effect_authority.py` joins claim and commit currentness under installed qualified ports. Before a second physical contact, the application must determine whether the original effect already happened and whether a new operation is specifically authorized.

## Negative scenarios

Test identical request retried by two workers, changed paper revision after reservation, provider call billed but timed out, database commit succeeded but acknowledgment was lost, conflicting recovered receipt and restart with no in-memory state. A normal in-memory duplicate check is not enough. The durable storage owner must show exact original-keyed behavior.

Relevant source regressions include `tests/integration/test_joint_retry_connected_execution.py`, `test_prepared_release_resolution.py` and `test_paper_cas_durable_recovery_type_contract.py`.
