# Integration test plan

The integration team must run the same supported examination through real OCR, backend authority, evaluator, candidate persistence, teacher review and release components. Synthetic source tests remain valuable regression evidence but cannot certify external services.

## 1. Source qualification

```sh
python -m pip install -r requirements-test.txt
python -m pip check
PYTHONPATH=src:. python -m pytest -q
```

For Windows Command Prompt:

```bat
set "PYTHONPATH=src;."
python -m pip check
python -m pytest -q
```

Record the exact Git tree, Python, pytest and Hypothesis versions, test counts and any skips. Do not add historic test counts together or claim the renamed source's Linux run proves a newer Windows run.

## 2. OCR admission demonstration

```sh
PYTHONPATH=src:. python docs/examples/ocr_admission_demo.py
```

Expected: a valid sample is admitted, its schema version and original raw-body SHA-256 are reported, and a deliberately malformed schema version is rejected. This is a parser test, **not** an end-to-end grade and not evidence of real handwriting quality.

## 3. Reproducible synthetic supported paper

```sh
PYTHONPATH=src:. python docs/examples/paper_operation_demo.py
```

Expected: Q1=5, Q2=5, paper candidate=10, two synthetic physical attempts, one synthetic conditional commit and publication authorization `False`. This is source behavior, not real service conformance. See [Production paper wiring](deployment_wiring_walkthrough.md).

## 4. Authentic paper campaign

Use a school-approved CHOICE-only paper or a supported DIRECT/NUMERIC paper with real scanned responses. Record the approved version, canonical question inventory, observed OCR mapping, model/provider version, original attempt, physical-accounting receipt, candidate criterion scores and teacher-labelled expectation. Prove that the candidate is private until separately released.

## 5. Adverse cases

| Test | Expected result | Owner |
|---|---|---|
| Foreign tenant or revoked paper approval | No grading or release effect | Backend + engine |
| Swapped question region or missing OCR mapping | Rejected or mapped to review; no guessed answer | OCR + backend |
| Unsupported diagram or symbolic derivation | No false claim of validated automatic grading | Engine + product |
| Wrong model criterion or malformed provider response | Judgment denied; no invented numeric mark | Provider + engine |
| Provider timeout after remote contact | Preserve physical uncertainty; reconcile original | Provider + backend |
| Two workers race attempt reservation or scored commit | At most one authoritative conditional effect | Backend database |
| Lost acknowledgment after write | Recover original durable status without blind repeat | Backend database |
| Unapproved teacher correction | No official mark mutation | Backend review |
| Released audience revoked just before publication | Deny effect under current issuer/policy | Backend release |
| Cross-tenant or unreleased candidate requested by student | Deny disclosure | Backend + frontend |

## 6. Evidence package

Keep redacted real database receipts and event histories, provider request/usage receipts, captured source versions, original operation IDs, review approval, restart logs, returned candidate and final student-facing result. All private student records remain in secure team storage, not Git.

The [Acceptance checks](acceptance_checks.md) define the gate record. Passing only the Python tests is not enough for a production claim.
