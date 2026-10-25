# Testing

The repository contains unit, contract, integration and property-based tests. These tests exercise the grading rules and expected failure behavior. They do not prove school authorization, real OCR accuracy, model grading quality, actual provider billing, or database atomicity across machines.

## Run the tests

Use **CPython 3.11.9** and the pinned test dependencies to reproduce the published Windows qualification environment.

On Windows Command Prompt, from the repository root:

```bat
python -m pip install -r requirements-test.txt
python -m pip check
set "PYTHONPATH=src;."
python -m pytest -q
```

On Linux or macOS, from the repository root:

```sh
python -m pip install -r requirements-test.txt
python -m pip check
PYTHONPATH=src:. python -m pytest -q
```

Run the supported OCR and paper examples using the same `PYTHONPATH` setting:

```bat
python docs\examples\ocr_admission_demo.py
python docs\examples\paper_operation_demo.py
```

The paper example uses synthetic providers and storage ports. It does not verify a deployed OCR service, real billing, institutional permissions, or student-visible publication.

## Published baseline verification and version scope

- Published baseline: `feature/Scoring-Algo-Engine`, commit `41fd7756a37e446a79051f349629f1fc514f2991`, Git tree `9fbcdb3fa2b93b20658edc331ce254e0b79a5dfa` (468 files).
- **Native Windows CPython 3.11.9:** pinned dependencies and `pip check` passed; cache-isolated execution passed 26 explicit property tests and the **full 5,242-test suite** (the 26 property tests are included in 5,242), with source/hash and protected Git custody intact before and after. OCR and paper examples passed.
- Linux non-property campaigns established regression evidence for earlier candidates. Do **not** claim a complete native Linux test of this final published tree unless such evidence is separately produced.
- These results establish source behavior for the stated supported subset. They do **not** establish real-school identity, OCR quality, model grading accuracy, provider billing, multiworker durability or official result publishing.

The next breadth work changes the Git tree and requires fresh targeted unit/contract/integration/adverse tests as each capability closes. Run the complete pinned regression, property suite, source-integrity checks and genuine academic/integration acceptance on the **future exact release tree** before another publication. Never add overlapping test counts together or silently reuse older-tree qualification.

## What to record when a test fails

Record the exact command, Python and dependency versions, source snapshot, failing test name, traceback, sanitized input shape, expected behavior, actual behavior and responsible integration boundary. Preserve the underlying failure. Do not relax a scoring check, suppress an error, or replace a real authority decision with a fabricated test value simply to obtain a passing result.

## Release evidence

For handoff, record the exact Git content tree or file manifest **outside the tracked source being hashed**, along with the native Windows/property and Linux results, dependency versions, the runnable paper example, and the receiving teams' real adapter conformance results. The final source tree is not certified by tests run only on an older tree.
