# Official result release

A scored candidate is not automatically official. The release layer requires separately sourced current school policy, teacher/review authority, original scored result, audience permission and durable original intent.

## Installed boundary

`ProductionGovernedResultRelease` in `src/grading/integration/official_result_release.py` handles conditional release. The integrated source also includes read-only original reconciliation and separately approved prepared-intent recovery. These operations are not grading retries.

Before a release writer can be contacted, `QualifiedReleaseIntentCustody.establish_original_intent(...)` must admit the exact original intent. The backend is responsible for genuine write-ahead durability and transactional uniqueness, not merely returning a success-shaped Python object.

## Crash and recovery example

1. A teacher approves the correct original candidate under current policy.
2. The backend persists the release intent and contacts the conditional publication writer.
3. The process crashes after publication but before receiving an acknowledgment.
4. Recovery reads the **fixed original intent**, checks the authoritative release history and resolves that intent without rerunning paper scoring or blindly publishing again.

A real test must prove one authorized audience-visible result under two workers, restart, revoked permission, malformed reply and conflicting intent. The local regression tests exercise engine mechanics with synthetic ports; they do not prove production publication.

Source tests include `tests/integration/test_official_result_release.py`, `test_release_write_ahead_custody.py` and `test_prepared_release_resolution.py`.
