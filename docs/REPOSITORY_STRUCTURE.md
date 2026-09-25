# Repository Structure

This repository is organized so a new engineer can quickly tell production code, tests, shared test helpers, and documentation apart.

```text
Gradified/
├── README.md
├── pyproject.toml
├── requirements-test.txt
├── src/
│   └── grading/
│       ├── contracts/       # immutable/domain contract types and validators
│       ├── rubric/          # rubric generation, lint, compile, fingerprint, lifecycle
│       ├── scoring/         # deterministic reducer, arithmetic, rounding, paper aggregation
│       ├── providers/       # bounded provider seams used by rubric generation
│       ├── verification/    # evidence/judgment verification
│       ├── active_question_authority.py
│       ├── choice_evaluator.py
│       ├── numeric_authority.py
│       ├── numeric_evidence.py
│       ├── numeric_evaluator.py
│       ├── numeric_judgments.py
│       ├── semantic_evaluator.py
│       ├── capability_registry.py
│       ├── reference_context.py
│       ├── execution.py
│       └── risk.py
├── tests/
│   ├── contracts/           # contract/type/binding behavior
│   ├── unit/                # focused component behavior
│   ├── integration/         # multi-component/vertical flows
│   ├── property/            # property/differential invariants
│   └── support/             # shared TEST-ONLY fixtures/helpers; not pytest test modules
└── docs/
    ├── README.md            # document map: what each document is for
    ├── ARCHITECTURE.md
    ├── INTEGRATION_START_HERE.md
    ├── INTEGRATION_REQUIREMENTS.md
    ├── INTEGRATION_TEST_PLAN.md
    ├── OCR_INTEGRATION_GUIDE.md
    ├── BACKEND_INTEGRATION_GUIDE.md
    ├── REFERENCE_INTEGRATION_GUIDE.md
    ├── SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md
    ├── RELEASE_SCOPE.md
    ├── SCORING_KERNEL_BLACK_BOX.md
    ├── PROJECT_STATE.md
    ├── TESTING.md
    └── assets/
        └── release-1-target-architecture.png
```

## Why `tests/support/` exists

`tests/support/` contains reusable **test helper modules** shared by several test categories. They are not test cases and they are not production code. Keeping them in a named support directory avoids the confusing appearance of loose Python files at the test root.

## Where should new code go?

- New public domain/value contract -> `src/grading/contracts/`
- Rubric authoring/lifecycle behavior -> `src/grading/rubric/`
- Deterministic mark calculation -> `src/grading/scoring/`
- Evidence/judgment verification -> `src/grading/verification/`
- External provider seam -> `src/grading/providers/` or a dedicated adapter module when the real contract is known
- Shared test helper -> `tests/support/`
- Contract test -> `tests/contracts/`
- Focused behavior test -> `tests/unit/`
- Cross-component flow -> `tests/integration/`
- Property/differential invariant -> `tests/property/`

## What must stay outside the public repository?

Private evidence bundles, mutation logs, local F-drive organization files, virtual environments, credentials, private learning documents, real student/school data, and private publication handoffs are not public repository content.
