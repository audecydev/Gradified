# Integration start guide

Start with one **supported** school paper. Do not begin by connecting the browser directly to grading functions or by treating a synthetic test issuer as real school authority.

## Integration order

1. From the source checkout, install only the pinned **test dependencies** and run the source tests (see [Testing](testing.md)). This repository does not define an installable Python distribution; use `PYTHONPATH=src:.` on Linux/macOS and `set "PYTHONPATH=src;."` in Windows CMD.
2. Agree the backend's tenant, actor, paper, submission, rubric and operation identity model. Establish authenticated, revisioned sources before any attempt reservation.
3. Connect OCR to the normalized evidence format and run the [OCR example](examples/ocr_admission_demo.py). Verify mapping against real scanned pages.
4. Configure school-approved rubrics, evaluator capability records, route selection and eligibility. Unsupported question modalities must fail before grading effects.
5. Install conditional attempt, provider, accounting and scored-result adapters. Use the strict `ProductionPaperOperations` root, not individual internal owners as public endpoints.
6. Execute one supported FIRST operation, compare question/criterion marks with an approved teacher-marked sample and read the candidate from the real database.
7. Exercise REGRADE and RETRY using the same original request lineage; verify crash and lost-acknowledgment behavior.
8. Connect teacher review and conditional official release separately. Expose only backend-authorized status and result views to the frontend.

## Required observable outcomes

An admitted OCR document produces a bounded, immutable evidence object, **not** an official grade. A successful FIRST produces a guarded candidate result. A timeout after a provider/storage effect produces an uncertain/reconcilable result rather than permission to rerun. A school-approved release is a separate effect with its own durable intent and currentness checks.

The examples in this repository use **demonstration identities only**. No example grants school authority or supplies production credentials. For an executable supported mixed-paper demonstration using synthetic ports, run [Production paper wiring](deployment_wiring_walkthrough.md). It does not qualify real school adapters.

See [Backend integration](backend_integration_guide.md), [Operation flow](grading_operation_flow.md) and [Integration testing](integration_test_plan.md).
