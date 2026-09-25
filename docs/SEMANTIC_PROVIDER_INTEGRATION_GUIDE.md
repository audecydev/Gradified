# Semantic Provider Integration Guide

This guide is for the engineer connecting a real model/provider to the currently frozen DIRECT text semantic evaluator.

## Supported semantic slice

The current frozen semantic path is deliberately narrow:

- context policy: `DIRECT` only;
- active evidence: text only for the supported path;
- provider receives a narrow request projection;
- provider returns untrusted raw bytes;
- the core strictly parses and validates the response;
- the provider does not return the authoritative numerical total.

Broader reference-aware semantic evaluation is still open Release 1 work.

## Provider protocol

Implement:

```python
class DirectTextSemanticProvider:
    def evaluate(self, *, request: DirectTextSemanticRequest) -> bytes:
        ...
```

The response is intentionally raw bytes so the core can perform strict admission instead of trusting a provider SDK object.

## Model-answer source

The evaluator also uses a `DirectTextModelAnswerSource` that materializes the already-authorized model answer for the exact grading spec/question.

The returned material must bind to the requested spec and question.

## Resource limits are explicit

`DirectTextSemanticLimits` contains explicit limits for:

- model-answer characters;
- evidence block count;
- evidence characters;
- total request characters;
- raw response bytes;
- JSON depth/node count;
- evidence references per judgment;
- rationale size;
- uncertainty count/size.

There are no implicit provider defaults in the core. The composition root must configure the limits deliberately.

## Provider result expectations

The provider output is admitted into `EvaluatedCriterionJudgment` values with:

- criterion ID;
- selected approved rubric level;
- evidence references;
- reason codes;
- concise rationale;
- uncertainty metadata;
- system-owned evaluator metadata.

The provider is not allowed to invent a final numerical score.

## First provider integration test

1. Select one ACTIVE DIRECT text question.
2. Supply one valid model answer and one valid text evidence block.
3. Build explicit semantic limits.
4. Call the real provider through `DirectTextSemanticProvider`.
5. Confirm the response passes strict admission.
6. Feed admitted judgments through evidence verification and deterministic scoring.
7. Return an unknown criterion; confirm rejection.
8. Return a valid criterion with an unknown level; confirm rejection downstream.
9. Return an evidence reference to another question; confirm evidence verification rejects it.
10. Return malformed JSON / duplicate keys / oversized response; confirm provider-response failure.
11. Trigger timeout/provider failure; confirm it does not become an academic score.
12. Record model/provider/version, cost, latency, retry count, and evaluator-attempt identity in the integration workflow.

## Production evidence still required

Before calling a semantic provider production-ready, the project still needs representative held-out teacher-marked benchmarking, cost/latency measurements, provider-failure testing, and real-paper end-to-end evidence.
