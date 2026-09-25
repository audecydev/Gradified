# Gradified Grading Engine Architecture

This document is the canonical **Release 1 target architecture** for the grading engine and also records the narrower path that is already implemented in this repository.

The diagram below is kept as Mermaid source inside Markdown so every arrow is reviewable in Git history.

```mermaid
flowchart TB
  subgraph A["A. Platform Trust / Authorization / Job Boundary"]
    FE[Frontend / LMS / Internal Service] --> API[Backend API boundary]
    API --> ID[Authentication / Service Identity]
    ID --> TENANT[TrustedTenantContext]
    TENANT --> RBAC[Authorization / RBAC]
    RBAC --> STORE[Authoritative-store isolation / authorized asset access]
    STORE --> INGRESS[Ingress + Job Admission Gate]
    INGRESS --> JOB[Async Job / Reliability Control<br/>queue · retries · evaluation_attempt_id · timeout · idempotency]
  end

  subgraph B["B. Assessment Authority / Rubric Authoring"]
    SCHOOL[School-authorized inputs<br/>question · max marks · model answer · optional approved references]
      --> RGEN[Rubric Generator]
    RGEN --> RCOMP[Rubric Linter + Deterministic Compiler]
    RCOMP --> APPROVAL[Teacher Approval]
    APPROVAL --> ACTIVE[ACTIVE GradingSpec<br/>immutable versioned grading authority]
  end

  subgraph C["C. Student Evidence Boundary"]
    OCR[OCR output<br/>external OCR schema] --> OCRA[OCR Adapter<br/>normalizes external format]
    OCRA --> EVIDENCE[AnswerEvidenceBundle<br/>evidence IDs · content/type · confidence/UNKNOWN · page/location · asset refs · OCR provenance]
  end

  subgraph D["D. Verification-First Grading Core"]
    PRE[Pre-Evaluation Safety Gate<br/>trusted context · ACTIVE authority · question mapping · evidence usability · resource limits]
    SELECT[Versioned Evaluator Selection Policy<br/>choose exact capability from authoritative question/criterion classification]
    REG[Capability Registry<br/>resolve exact versioned capability record]
    ATTEMPT[Evaluator Execution Boundary<br/>evaluation_attempt_id + exact evaluator/capability identity]
    DET[Deterministic Evaluators<br/>CHOICE / exact / bounded numeric and other validated deterministic checks]
    SEM[Semantic Evaluator<br/>structured criterion-level judgments only]
    DOMAIN[Math / Domain Checks<br/>independent unit / symbolic / reference / domain verification]
    J[CriterionJudgment array<br/>criterion · approved level · evidence refs · reason codes · uncertainty]
    VERIFY[Judgment + Evidence / Domain Verification<br/>exact criterion correspondence · evidence ownership/existence · independent checks]
    KERNEL[Frozen Deterministic Scoring Kernel<br/>rubric authority -> marks · caps · dependencies · gates · deductions · rounding · bounds]
    SCORE[Candidate Score]
    RISK[Risk + Impact Decision]
    RESULT[Candidate GradeResult<br/>AUTO_CANDIDATE / REVIEW_REQUIRED / UNSUPPORTED / UNASSESSABLE / FAILED_TECHNICALLY]

    PRE --> SELECT --> REG --> ATTEMPT
    ATTEMPT --> DET --> J
    ATTEMPT --> SEM --> J
    ATTEMPT --> DOMAIN
    DOMAIN -. independent verification evidence .-> VERIFY
    J --> VERIFY --> KERNEL --> SCORE --> RISK --> RESULT
  end

  subgraph E["E. Supporting / Cross-Cutting Controls"]
    SECRET[Secret Infrastructure<br/>provider credentials by reference only]
    PROVIDER[Model Provider Adapter<br/>validated structured output · health · cost/usage metadata]
    RETRIEVAL[RetrievalPort<br/>approved tenant/version-filtered context; index is not authoritative storage]
    REFCTX[Reference Context Materialization + Provenance<br/>source identity · version · opaque provenance hash]
    AUDIT[Audit / Provenance / Telemetry<br/>spec/evaluator/provider versions · evidence/source refs · retries · latency · tokens · cost]
    RUNTIME[Runtime / Structural Resource Controls]
    ISOLATION[Tenant / Data Isolation]
    UNTRUSTED[Untrusted Content / Prompt-Injection Boundary]
    FAIL[Fail-Closed + Selective Review]
    BENCH[Offline Calibration / Benchmark]
    PROMOTE[Validated Configuration / Policy Promotion]

    SECRET --> PROVIDER
    RETRIEVAL --> REFCTX
    BENCH --> PROMOTE
  end

  subgraph F["F. Backend / Institutional Outcome Boundary"]
    BADAPTER[Backend Adapter / Integration]
    PERSIST[Authoritative tenant-isolated persistence]
    REVIEW[Conditional review / regrade workflow]
    NEWRUN[New grading run / linked result<br/>never mutate historical result in place]
    PUB[Institution publication policy gate]

    BADAPTER --> PERSIST --> PUB
    PERSIST --> REVIEW
    REVIEW -. accepted/allowed override outcome .-> PUB
    REVIEW -. correction or regrade requested .-> NEWRUN
    NEWRUN --> JOB
  end

  %% Main authority/data flow into the core
  JOB --> PRE
  ACTIVE --> PRE
  EVIDENCE --> PRE
  TENANT -. trusted tenant context .-> PRE

  %% Provider paths: rubric/semantic components invoke a configured provider; provider output never scores directly
  RGEN -. provider request .-> PROVIDER
  PROVIDER -. structured rubric proposal .-> RGEN
  SEM -. provider request .-> PROVIDER
  PROVIDER -. structured semantic output .-> SEM

  %% Reference context is separate from student evidence
  RGEN -. authoring reference request .-> RETRIEVAL
  PRE -. grading-policy reference request .-> RETRIEVAL
  REFCTX -. when authoring policy requires reference context .-> RGEN
  REFCTX -. when grading policy requires reference context .-> PRE

  %% Cross-cutting controls
  ISOLATION -. constrains .-> RETRIEVAL
  ISOLATION -. constrains .-> PROVIDER
  ISOLATION -. constrains .-> PRE
  UNTRUSTED -. constrains .-> SEM
  UNTRUSTED -. constrains .-> RGEN
  RUNTIME -. bounds .-> PRE
  RUNTIME -. bounds .-> ATTEMPT
  FAIL -. fail-closed policy .-> PRE
  FAIL -. fail-closed policy .-> VERIFY
  FAIL -. review/release policy .-> RISK
  PROMOTE -. validated selector/policy configuration .-> SELECT
  PROMOTE -. validated capability status/configuration .-> REG

  PRE -. audit events .-> AUDIT
  ATTEMPT -. audit events .-> AUDIT
  VERIFY -. audit events .-> AUDIT
  RISK -. audit events .-> AUDIT

  %% Candidate result returns to backend; backend alone publishes
  RESULT --> BADAPTER
```

## Why this diagram is canonical

 In particular:

1. **Reference context is not student evidence.** `RetrievalPort` / reference context must never feed `AnswerEvidenceBundle`. Student/OCR evidence and reference context remain separate inputs.
2. **Selection, registry resolution, and evaluator execution are distinct.** The target architecture now shows `Selection Policy -> Capability Registry -> Evaluator Execution Boundary` explicitly. The current repository implements the registry, not the generic selector.
3. **Independent math/domain checks verify rather than silently author semantic judgments.** Their results feed the verification stage. A deterministic evaluator may itself use domain logic when that behavior is the selected capability, but independent checks do not bypass criterion-judgment verification.
4. **Model/provider output never bypasses verification or deterministic scoring.** The provider may propose rubric structure or semantic judgments only through bounded interfaces.
5. **A regrade creates a new grading run/result.** Historical results are never silently mutated in place.
6. **Backend publication authority stays outside the grading core.** A candidate result is not an official published grade.

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

## Target components still open or requiring real integration evidence

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
