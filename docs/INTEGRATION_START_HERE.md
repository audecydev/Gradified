# Integration Start Here

This page explains the grading core in simple terms and tells each integration engineer what to do first.

## 1. What this repository is

This repository is the **internal grading engine** for the completed Release 1 scope.

It accepts trusted grading authority and normalized student evidence, produces evaluator judgments through supported evaluator paths, verifies those judgments against evidence, and calculates deterministic candidate scores.

It deliberately does **not** own every concern in the Gradified product.

The external systems still own important responsibilities:

- **Backend/workflow:** tenant identity, authentication, authorization, ACTIVE spec storage, job state, persistence, review, regrade, and official publication.
- **OCR:** reading answer sheets and converting OCR-specific output into Gradified's evidence contract.
- **Semantic provider:** returning bounded structured semantic-evaluation data through the provider boundary.
- **Reference system:** tenant/version-scoped access and retrieval of approved reference material.

## 2. The safest mental model

Think of the core as a strict machine in the middle:

```text
External systems provide trusted facts
        ↓
Gradified validates exact relationships it owns
        ↓
Supported evaluator creates criterion judgments
        ↓
Evidence verifier checks grounding
        ↓
Deterministic reducer calculates marks
        ↓
Paper aggregator calculates candidate total
        ↓
External workflow decides review/publication
```

The core fails closed when required authority, evidence, or supported capability is missing or malformed.

## 3. What integration testing should prove

Integration testing should answer four questions:

1. **Can the external system create the exact Gradified contract values required by the core?**
2. **Are identifiers and versions preserved end to end without guessing or silent substitution?**
3. **Do malformed, missing, duplicated, cross-question, cross-spec, and unsupported inputs fail safely?**
4. **Does the final candidate score come only from the deterministic scoring path?**

## 4. Recommended integration order

Do not connect every external system at once. Use this order:

### Step A — verify the frozen repository

Run the complete test suite. Expected qualified baseline: **1499 passed**.

### Step B — backend authority integration

Make the backend supply exact grading-spec/question authority and stable run/submission identifiers.

Read [`BACKEND_INTEGRATION_GUIDE.md`](BACKEND_INTEGRATION_GUIDE.md).

### Step C — OCR integration

Map one real OCR payload into `AnswerEvidenceBundle` without leaking OCR-vendor field names into grading-core code.

Read [`OCR_INTEGRATION_GUIDE.md`](OCR_INTEGRATION_GUIDE.md).

### Step D — run deterministic evaluator paths

Start with CHOICE and bounded unitless NUMERIC examples because they do not require a semantic model provider.

### Step E — semantic-provider integration

Connect a real provider only through the existing DIRECT semantic provider interface and strict response admission.

Read [`SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md`](SEMANTIC_PROVIDER_INTEGRATION_GUIDE.md).

### Step F — reference integration

Implement the configured reference-context source. Prove tenant/version isolation outside the core and exact provenance/binding inside the core.

Read [`REFERENCE_INTEGRATION_GUIDE.md`](REFERENCE_INTEGRATION_GUIDE.md).

### Step G — full integration tests

Run one real paper through the exact authority/evidence/evaluator/scoring flow with no manual JSON repair between stages.

Read [`INTEGRATION_TEST_PLAN.md`](INTEGRATION_TEST_PLAN.md).

## 5. What not to do

Do not:

- let OCR totals or model totals become authoritative scores;
- infer tenant identity from student content;
- choose an evaluator by subject name or by "whichever parser works";
- silently select the newest capability version;
- silently fall back to unrelated reference material;
- change frozen scoring rules to accommodate an adapter;
- treat a Python object type as proof that a trusted workflow step actually ran;
- call a candidate result an official published grade.

## 6. Where to look when something fails

- Contract/type/binding failures: start in `src/grading/contracts/` and the matching `tests/contracts/` tests.
- Evidence grounding failures: `src/grading/verification/evidence.py`.
- Deterministic score failures: `src/grading/scoring/` and `docs/SCORING_KERNEL_BLACK_BOX.md`.
- ACTIVE authority problems: `src/grading/active_question_authority.py`.
- DIRECT semantic problems: `src/grading/semantic_evaluator.py`.
- NUMERIC problems: `src/grading/numeric_authority.py`, `numeric_evidence.py`, `numeric_evaluator.py`, and `numeric_judgments.py`.
- Reference-context problems: `src/grading/reference_context.py`.
- Capability-record resolution: `src/grading/capability_registry.py`.
- Overall exact state: `docs/PROJECT_STATE.md` and `docs/TESTING.md`.
