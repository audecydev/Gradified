# Gradified Grading Engine Architecture

This document describes the **final Release 1 target architecture** and clearly separates it from what is already implemented in this repository.

The canonical diagram is:

![Gradified Release 1 target architecture](assets/release-1-target-architecture.png)

A scalable SVG copy is also available at [`assets/release-1-target-architecture.svg`](assets/release-1-target-architecture.svg).

## What changed from the earlier draft diagram

The corrected architecture makes several important boundaries explicit:

1. **Reference context is not student evidence.** `AnswerEvidenceBundle` contains OCR/student evidence only. Approved reference context is materialized separately and is supplied to rubric authoring or evaluation only when policy requires it.
2. **Capability registry and evaluator routing are separate.** The registry resolves an exact versioned capability record. A separate versioned selection policy chooses the exact evaluator capability for a question/criterion.
3. **Evaluator execution has its own provenance boundary.** The target architecture records an `evaluation_attempt_id`, selected capability identity/version, and execution provenance before judgments are accepted.
4. **Backend technology is not hard-coded.** The architecture uses a generic backend/API/workflow boundary rather than assuming Django/DRF.
5. **Regrade does not bypass grading.** A regrade creates a new run. A rubric correction creates a new rubric/spec version and then a new run. Historical results are not silently mutated.
6. **Technical failures do not become student errors.** Pre-evaluation, provider, execution, and verification failures fail closed into controlled workflow states.
7. **The backend publishes.** The grading core produces candidate results; institution/backend policy controls official publication.

## Final Release 1 target flow

```text
verified identity
    -> TrustedTenantContext
    -> authorization / authorized store access
    -> admitted async grading job

school-authorized question/model answer/references
    -> rubric generation
    -> deterministic lint + compile
    -> teacher approval
    -> immutable ACTIVE GradingSpec

real OCR payload
    -> OCRAdapter
    -> AnswerEvidenceBundle

ACTIVE authority + evidence + job context
    -> pre-evaluation safety gate
    -> versioned evaluator selection policy
    -> exact capability registry resolution
    -> evaluator execution boundary / evaluation_attempt_id
    -> deterministic / semantic / domain evaluation
    -> CriterionJudgment(s)
    -> evidence + domain verification
    -> frozen deterministic scoring kernel
    -> candidate score
    -> risk/impact decision
    -> candidate GradeResult
    -> backend persistence / review / publication policy
```

## Reference path

Reference material follows a separate path:

```text
authorized tenant/reference scope
    -> retrieval/backend reference adapter
    -> reference-context materialization + provenance boundary
    -> rubric generation and/or evaluator context when policy requires it
```

It does **not** enter `AnswerEvidenceBundle` and it does not become student evidence.

## Capability selection and registry

These two responsibilities must never be conflated:

- **Selection policy:** chooses the exact evaluator capability for an authoritative question/criterion classification.
- **Capability registry:** resolves and validates the exact versioned capability record that was selected.

The current repository has the capability registry. The generic selection/routing policy remains open Release 1 work.

## Evaluator execution provenance

The final architecture includes an explicit execution boundary between selection and evaluator output. Its purpose is to make this statement provable:

> These judgments came from this exact evaluator capability/version during this exact evaluation attempt.

The target boundary records the attempt identity and prevents retry behavior from silently creating multiple authoritative judgment/result paths.

## Current implemented core

The repository currently implements and verifies this narrower path:

```text
school-authorized / ACTIVE grading authority
        +
AnswerEvidenceBundle
        ↓
implemented evaluator path:
    CHOICE
    DIRECT semantic text
    bounded unitless NUMERIC N1-N4
        ↓
CriterionJudgment
        ↓
evidence / judgment verification
        ↓
frozen deterministic question scoring
        ↓
frozen deterministic paper aggregation
        ↓
candidate grading result for backend/workflow handling
```

Additional implemented integration foundations:

- **IF1 capability registry:** exact versioned capability-record resolution; it does not choose the evaluator.
- **REF-1 reference-context boundary:** bounded, provenance-preserving materialization from a configured source; it does not implement real tenant authentication or retrieval infrastructure.

## Release 1 target components still open or requiring real integration evidence

- generic versioned evaluator selection/routing policy;
- evaluator-attempt -> judgment provenance binding;
- real OCR adapter against the OCR team's actual payload;
- trusted backend/auth/tenant integration;
- real reference retrieval with tenant/version isolation;
- production semantic-provider adapter, telemetry and benchmark evidence;
- units, broader symbolic math, derivation and composite evaluator breadth;
- durable idempotency/persistence semantics;
- complete risk/review/regrade/publication workflow;
- real subjective and numeric/math school-paper end-to-end runs;
- held-out academic validation and production reliability evidence.

## Main invariants

- The school owns assessment content and final approved grading authority.
- OCR is evidence, not unquestioned truth.
- Models interpret; they do not own the authoritative numerical score.
- Deterministic scoring code alone maps approved rubric authority to marks.
- Technical/parser/provider failures are not student mistakes.
- Tenant authority comes only from trusted backend/workflow context.
- Reference context is provenance-bearing support context, not student evidence.
- Candidate results are not official published grades.
- Regrade/correction creates new linked/versioned state rather than silently rewriting history.
- Capability promotion requires benchmark/validation evidence rather than runtime self-assertion.

## Integration rule

External systems should adapt **to these boundaries**. Do not change frozen scoring semantics merely because an OCR, backend, provider, or retrieval implementation exposes a different payload shape.
