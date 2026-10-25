# Architecture

The engine separates academic authority from observed student work. This prevents OCR, a language model or the browser from approving its own grading rules or publishing results.

```text
Authenticated school/backend source            OCR / capture source
 approved paper, rubric, policy                  normalized evidence
                |                                        |
                v                                        v
   current authority and eligibility          strict admission + question binding
                |                                        |
                +----------------------+-----------------+
                                       |
                                       v
                           supported evaluator route
                         CHOICE / DIRECT / NUMERIC
                                       |
                                       v
                     evidence-checked criterion judgments
                                       |
                                       v
                       deterministic question scoring
                                       |
                                       v
                           exact paper aggregation
                                       |
                                       v
                         candidate result + audit identity
                                       |
                         independent review / release checks
                                       |
                                       v
                     backend-authorized official publication
```

## Important separations

- The **school backend** authenticates people, resolves approved paper and rubric versions, and provides durable transaction services.
- The **OCR adapter** maps scanned pages to real submission, question and evidence identities. Recognition confidence is evidence, not grading authority.
- The **evaluation layer** applies a selected supported method. Direct text requires a separately qualified provider route.
- The **scoring layer** applies the compiled rubric using exact numeric rules. A model cannot directly set an unchecked paper total.
- The **paper-operation layer** binds FIRST, REGRADE and RETRY to the original request and effect history, then calls qualified conditional storage.
- The **review/release layer** has its own authority checks. A scored candidate is never an automatic publication grant.

The main host entry is `ProductionPaperOperations.execute(...)` in `src/grading/integration/production_paper_operations.py`. The actual constructor rejects inconsistent executor, attempt, storage and accounting owners. It does not prove that backend callbacks use a real database or authenticate their issuers.

Follow [Paper execution and persistence](paper_execution_and_persistence.md) for the detailed boundaries.
