# School policy setup

Each school may supply approved grading rules and review settings through its authenticated administrative backend. Configuration is versioned and must be bound to the correct school, paper, rubric and operation.

## Backend-owned inputs

Record school/tenant identity, authorized issuer, current approved policy revision, applicable subjects and questions, admitted evaluator families, model and reference selection, numeric rules where supported, attempt/regrade permissions, review decisions and release audience requirements.

The engine checks exact policy and capability identity at the relevant boundaries. Missing, revoked, conflicting or unsupported settings are not defaults to permissive behavior. In particular, a school administrator cannot enable unimplemented symbolic mathematics, diagram grading or statistical confidence calibration through a policy flag.

## Update behavior

When a school policy changes, issue a new approved revision and recheck effect-time currentness. Do not mutate an earlier result's frozen academic context. A legitimate regrade is a separate authorized operation with preserved original history.

See [Evaluation and provider contracts](evaluation_and_provider_contracts.md), [Security and trust boundaries](security_and_trust_boundaries.md) and [Backend integration](backend_integration_guide.md).
