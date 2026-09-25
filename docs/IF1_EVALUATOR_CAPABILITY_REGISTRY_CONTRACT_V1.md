# IF1 Evaluator Capability Registry Contract v1

Status: BUILD AUTHORIZED FOR CAUSAL RED

## 1. Purpose

IF1 adds the smallest internal capability-registry boundary needed to describe and
resolve one explicitly selected evaluator capability without creating automatic
question routing, execution authorization, or a second academic authority.

The caller supplies the exact evaluator identity and exact capability-record
version. IF1 validates and resolves exactly that record from a configured source.

## 2. Reused existing contracts

IF1 MUST reuse `grading.contracts.evaluation.EvaluatorMetadata` as the evaluator
implementation identity pair:

- `evaluator_id`
- `version`

IF1 MUST NOT define a second evaluator ID/version vocabulary.

Current CHOICE and NUMERIC deterministic evaluators already emit fixed
`EvaluatorMetadata`. DIRECT-text evaluation already emits composition-owned
`EvaluatorMetadata` and an `evaluation_attempt_id`. IF1 does not reinterpret
those objects as cryptographic or execution-authentication tokens.

## 3. Capability reference

A capability reference contains:

- exact `EvaluatorMetadata`;
- positive exact integer `record_version`.

There is no omitted-version form. There is no `latest`, `highest`, `newest`,
`default`, or first-row selection.

## 4. Capability record

The record schema version is v1.

One immutable record contains:

- record schema version;
- exact capability reference;
- status: `VALIDATED | PILOT | DISABLED`;
- supported answer types;
- supported languages;
- supported modalities;
- tested grade range, if established;
- domain scope, if established;
- verification mechanisms;
- benchmark version, if established;
- known failure modes;
- cost profile, if established;
- latency profile, if established.

The contract is code-defined and versioned. The production inventory is NOT
code-defined.

Empty scope tuples or absent optional fields mean "no claim is established".
They never mean "all", wildcard support, or automatic compatibility.

Status is source-supplied capability metadata. IF1 does not infer `VALIDATED`
from passing repository tests, and it does not interpret any status as job,
auto-release, publication, or backend authorization.


### 4.1 Exact v1 field types

`EvaluatorCapabilityRef`:

- `evaluator_metadata`: exact `EvaluatorMetadata`;
- `record_version`: positive exact `int` (`bool` is invalid).

`EvaluatorCapabilityRecord`:

- `schema_version`: exact string equal to `"1"`;
- `capability_ref`: exact `EvaluatorCapabilityRef`;
- `status`: exact `EvaluatorCapabilityStatus`;
- `supported_answer_types`: exact `tuple[str, ...]`;
- `supported_languages`: exact `tuple[str, ...]`;
- `supported_modalities`: exact `tuple[str, ...]`;
- `tested_grade_range`: exact `str | None`;
- `domain_scope`: exact `str | None`;
- `verification_mechanisms`: exact `tuple[str, ...]`;
- `benchmark_version`: exact `str | None`;
- `known_failure_modes`: exact `tuple[str, ...]`;
- `cost_profile`: exact `str | None`;
- `latency_profile`: exact `str | None`.

Tuple entries are exact strings, contain no surrounding whitespace, and are
duplicate-free. Optional strings, when present, are non-empty and contain no
surrounding whitespace. Empty tuples and `None` are valid "no claim established"
representations and are never wildcard values.

IF1 v1 uses bounded metadata only:

- evaluator/scope identifier text: at most 128 characters per value;
- tuple fields: at most 32 entries each;
- descriptive optional text / failure-mode text: at most 512 characters per value.

These are Gradified-owned resource bounds, not academic semantics.

### 4.2 Exact v1 public contract surface

The contract module provides:

- `EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION`;
- `EvaluatorCapabilityStatus`;
- `EvaluatorCapabilityRef`;
- `EvaluatorCapabilityRecord`;
- explicit current-state validation functions for references and records.

The runtime registry module provides:

- `EvaluatorCapabilitySource.find_exact_capabilities(*, capability_ref=...)`;
- `ResolvedEvaluatorCapability`;
- `resolve_evaluator_capability(*, capability_ref, source)`.

`ResolvedEvaluatorCapability` is a domain result container. Its class identity is
not proof that the resolver ran and is not execution authorization.

## 5. Exact source resolution

A configured capability source receives the exact capability reference and
returns all records matching that exact reference.

The resolver MUST:

1. revalidate the current reference;
2. call only exact-reference lookup;
3. require an exact tuple result;
4. treat zero matches as missing;
5. treat more than one match as ambiguous;
6. require the one materialized value to be an exact capability-record type
   before invoking record validation;
7. revalidate the record's complete current state;
8. require the returned record reference to equal the requested exact reference;
9. return a read-only resolved record.

Source execution failure is distinct from missing capability.

The resolver cannot prove that an arbitrary backend source has never rewritten
historical data. Same-record-version replacement remains a later persistence /
integration invariant.

## 6. Registry versus routing

IF1 MUST NOT perform or infer:

- subject -> evaluator routing;
- question-text -> evaluator routing;
- evidence-shape -> evaluator routing;
- successful-parse -> evaluator routing;
- answer-type/language/modality matching for selection;
- try-A-then-B fallback;
- disabled/unavailable automatic substitution;
- implicit newest/latest evaluator or record version;
- `VALIDATED` -> automatically selected;
- capability status -> publication or auto-release permission.

A future authoritative selector may explicitly choose another exact capability;
that is not IF1 fallback.

## 7. Execution binding non-claim

The audited repository already emits `EvaluatorMetadata`, but arbitrary domain
objects are constructible and S2a accepts supplied judgments. IF1 v1 does not
claim that record resolution proves a particular evaluator implementation ran.

Future integration must bind:

explicit selected capability record
-> actual evaluator execution
-> attempt/run provenance
-> result provenance

without treating object identity or metadata equality alone as execution proof.

IF1 v1 does not modify frozen S2a, CHOICE, NUMERIC, DIRECT, S1, B2 or B3 merely
to fabricate that proof.

## 8. External integration non-claims

IF1 does not implement:

- real OCR adapter;
- backend auth/tenant adapter;
- reference retrieval adapter;
- production provider transport;
- provider health/cost/latency telemetry;
- UNIT semantics;
- mixed evaluator composition.

Those remain separate prerequisite/integration gates.

## 9. Hostile requirements for GREEN

The IF1 implementation must later prove at least:

- exact identity + record-version success;
- missing exact record fails;
- duplicate exact records fail as ambiguity;
- wrong returned identity fails;
- unknown schema/status fails;
- malformed/foreign source result fails safely;
- foreign record objects are rejected before attribute/method dispatch;
- post-construction record/ref mutation is detected by current revalidation;
- bool is not accepted as an integer record version;
- duplicate scope/evidence metadata entries are rejected;
- source exceptions remain source-execution failures rather than "missing";
- no automatic fallback or implicit version selection exists;
- no production evaluator inventory is hard-coded into the registry modules;
- empty/absent descriptive scope cannot become wildcard support.

## 10. Causal RED

RED-1 first establishes that the existing `EvaluatorMetadata` prerequisite is
valid, then fails only because `grading.contracts.capability` does not exist.

RED-2 establishes an exact evaluator identity prerequisite and then fails only
because `grading.capability_registry` does not exist.

Behavior-defining GREEN starts only after those failures are confirmed on the
exact frozen N4 baseline.
