# Grading Core Architecture

## Purpose

The grading subsystem converts school-authorized assessment rules and student evidence into an auditable candidate grade.

The system is designed to fail safely. Unsupported capability, unusable evidence, review-required cases, and technical failure are valid outcomes. Inventing a grade is not.

## Authority chain

`School-authorized inputs -> generated/validated rubric -> OCR evidence -> capability-selected evaluator -> verification -> deterministic reducer -> candidate score -> risk/impact -> review or candidate result`

## Six responsibilities

1. **Assessment authority**  
   The school provides the question, maximum marks, model answer, and approved references. The engine may generate a rubric from these inputs, but Release 1 requires teacher approval before the rubric becomes ACTIVE.

2. **Evidence**  
   OCR provides evidence about what the student submitted. OCR output carries source/provenance and uncertainty. It is not treated as unquestioned truth.

3. **Interpretation**  
   A validated evaluator decides which teacher-approved rubric level best matches the evidence.

4. **Verification**  
   Deterministic/domain checks verify what can be checked independently: evidence references, numeric values, units, parseable mathematics, approved references, and other supported checks.

5. **Scoring**  
   Only deterministic code maps rubric levels to marks and applies caps, dependencies, gates, deductions, rounding, and score bounds.

6. **Release safety**  
   Pre-evaluation gates stop invalid inputs early. After deterministic scoring, risk and impact decide whether the result is an AUTO_CANDIDATE, needs another check, or requires human review. Backend/institution policy controls official publication.

## Dependency boundaries

The grading core must not directly depend on:
- backend ORM/database tables
- OCR vendor-specific field names
- frontend objects
- OpenAI/Gemini SDK response types
- arbitrary vector-database APIs

Use adapters/ports at those boundaries.

## Final architectural invariants

- The evaluator/model cannot create the authoritative numerical total.
- Active rubric/spec versions are immutable.
- Missing OCR confidence is explicit uncertainty.
- Math/parser failure is not automatically a student error.
- Evidence references must resolve to the correct submission/question.
- Tenant authority comes only from trusted backend context.
- Retrieval is tenant/version scoped.
- Unsupported capability must not be forced through a generic grader.
- Safety-critical failure blocks automatic progression.
- Candidate grade is separate from published grade.
- Teacher corrections do not directly retrain the live model.
- Quality must pass validation before cost optimization determines provider/model choice.

## Release 1 deployment style

Use one logically modular grading application. Do not split logical components into microservices unless real scale or ownership later requires it.
