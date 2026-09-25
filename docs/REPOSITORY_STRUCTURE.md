# Repository Structure

This repository is intentionally small. Most files are either production grading-core code, tests, or engineering contracts.

```text
.
├── README.md
├── pyproject.toml
├── requirements-test.txt
├── src/
│   └── grading/
│       ├── contracts/              immutable public/internal value contracts
│       ├── scoring/                deterministic numerical scoring kernel
│       ├── verification/           evidence-to-judgment verification
│       ├── rubric/                 rubric authoring/lint/compile/lifecycle code
│       ├── providers/              rubric provider boundaries/replay support
│       ├── active_question_authority.py
│       ├── execution.py
│       ├── choice_evaluator.py
│       ├── semantic_evaluator.py
│       ├── numeric_authority.py
│       ├── numeric_evidence.py
│       ├── numeric_evaluator.py
│       ├── numeric_judgments.py
│       ├── capability_registry.py
│       ├── reference_context.py
│       └── risk.py
├── tests/
│   ├── contracts/                  contract and hostile-boundary tests
│   ├── unit/                       unit and adversarial tests
│   ├── integration/                multi-component composition tests
│   └── property/                   Hypothesis/property tests
└── docs/
    ├── ARCHITECTURE.md
    ├── PROJECT_STATE.md
    ├── IMPLEMENTATION_PLAN.md
    ├── TESTING.md
    ├── SCORING_KERNEL_BLACK_BOX.md
    ├── NUMERIC_PROFILE_V1.md
    ├── SRS_TRACEABILITY.md
    ├── DETERMINISTIC_SCORING_KERNEL_AUDIT.md
    ├── CHOICE_EVALUATION_CONTRACT_V1.md
    ├── IF1_EVALUATOR_CAPABILITY_REGISTRY_CONTRACT_V1.md
    ├── REF1_REFERENCE_CONTEXT_CONTRACT_V1.md
    └── integration guides added for this handoff
```

## Production-code ownership by concern

### Deterministic marks

`src/grading/scoring/`

This is the numerical scoring authority. External systems must not duplicate or bypass it.

### Contract values

`src/grading/contracts/`

These are the strict value boundaries used between grading-core components and integrations.

### Rubrics and ACTIVE lifecycle

`src/grading/rubric/`

This area validates and compiles rubric authoring data and preserves the ACTIVE lifecycle used by grading authority.

### Student evidence

`src/grading/contracts/evidence.py`

OCR adapters should map vendor-specific data here. Grading-core code should never depend directly on OCR vendor JSON field names.

### ACTIVE question authority

`src/grading/active_question_authority.py`

Backend integration supplies an admitted source. The core cross-checks deterministic relationships and returns an evaluator-facing authority projection.

### Evaluators

- CHOICE: `src/grading/choice_evaluator.py`
- DIRECT semantic text: `src/grading/semantic_evaluator.py`
- bounded NUMERIC: `src/grading/numeric_*.py`

### Execution composition

`src/grading/execution.py`

This composes verified evaluator judgments through the real evidence verifier, question reducer, and paper aggregator. It is not a persistence or publication workflow.

### Capability metadata

`src/grading/capability_registry.py`

This resolves an exact versioned capability record. It does not decide which capability a question should use.

### Reference context

`src/grading/reference_context.py`

This validates and snapshots material from a configured source. The source itself owns real access/retrieval mechanics and tenant/reference authorization.

## Private material that should not be added

Do not commit:

- local virtual environments;
- `.env` files, keys, tokens, credentials, or secret stores;
- private student answer sheets or student PII;
- school-private reference material;
- internal mutation/evidence ZIPs;
- private handoff documents;
- local F-drive workspace manifests;
- caches, build output, or test artifacts.
