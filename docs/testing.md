# Testing

The repository contains unit, contract, integration and property-based tests. These tests exercise the grading rules and expected failure behavior. They do not prove school authorization, real OCR accuracy, model grading quality, actual provider billing, or database atomicity across machines.

## Run the tests

Use Python 3.11 and the pinned test dependencies when reproducing the original Windows qualification environment.

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

## Verification evidence and version scope

- An earlier scoring-engine snapshot passed 5,242 Windows tests including Hypothesis property tests.
- The integrated source after file and module renaming passed 5,216 Linux non-property tests. Subsequent API declaration renaming also passed 5,216 Linux non-property tests, with focused regression campaigns.
- The API naming update renamed 40 Python declarations and updated dependent imports, tests, and documentation. This was a **source change**, even though scoring arithmetic and persisted protocol values were intentionally preserved.
- The repository-language corrections update comments, descriptive class strings, developer-facing diagnostics and stale test messages. An earlier correction also restored exact frozen scoring-traceability identifiers accidentally changed during editing. Frozen enum/wire values and test traceability identifiers remain unchanged; diagnostic message text is not a protocol. Schema validation constraints and dependency pins are unchanged. Every source revision requires its own exact-tree test evidence rather than inheriting certification from an earlier candidate.

Test counts from different snapshots or overlapping runs must not be added together. A passing synthetic test also does not replace real-school or real-provider acceptance evidence.

## What to record when a test fails

Record the exact command, Python and dependency versions, source snapshot, failing test name, traceback, sanitized input shape, expected behavior, actual behavior and responsible integration boundary. Preserve the underlying failure. Do not relax a scoring check, suppress an error, or replace a real authority decision with a fabricated test value simply to obtain a passing result.

## Release evidence

For handoff, record the exact Git content tree or file manifest **outside the tracked source being hashed**, along with the native Windows/property and Linux results, dependency versions, the runnable paper example, and the receiving teams' real adapter conformance results. The final source tree is not certified by tests run only on an older tree.
