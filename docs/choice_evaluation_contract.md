# Single-select choice evaluation contract

Single-select CHOICE compares one already-admitted option against approved question authority and emits criterion judgments. It does not calculate marks or authenticate the school.

## 1. Required constants

```text
CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION = "1"
CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION   = "1"

DETERMINISTIC_CHOICE_EVALUATOR_ID      = "gradified-deterministic-choice"
DETERMINISTIC_CHOICE_EVALUATOR_VERSION = "1"

CHOICE_MATCH_REASON_CODE    = "DETERMINISTIC_CHOICE_MATCH"
CHOICE_MISMATCH_REASON_CODE = "DETERMINISTIC_CHOICE_MISMATCH"

CHOICE_MATCH_RATIONALE =
    "Canonical selected option matches the authoritative option."

CHOICE_MISMATCH_RATIONALE =
    "Canonical selected option does not match the authoritative option."
```

The schema-version constants and evaluator semantic version are distinct contracts even though all begin at literal `"1"`.

## 2. Error taxonomy

CHOICE failures are evaluator-domain failures, not scoring-kernel failures.

```text
ChoiceEvaluationError(ValueError)

    InvalidChoiceEvaluationAuthorityError
        malformed local CHOICE authority

    InvalidCanonicalChoiceSelectionError
        malformed local canonical selection

    UnsupportedChoiceInputError
        locally valid selection not supported by the admitted authority

    ChoiceSelectionBindingError
        selection question does not bind to CHOICE authority question

    ChoiceScoringAuthorityBindingError
        CHOICE authority does not bind to supplied scoring authority

    ChoiceProjectionScoringMismatchError
        CHOICE authority is bound to the supplied scoring authority,
        but its projection criterion universe/order or selected levels
        are incompatible with that scoring authority
```

Known-but-wrong option → mismatch projection.

Unknown option → `UnsupportedChoiceInputError`, never mismatch.

Do not reuse `ScoringError` for CHOICE admission failures. Scoring failures remain owned by the scoring layer.

## 3. `ChoiceCriterionProjection`

```text
criterion_id: str
selected_level: str
```

Both are exact non-empty strings without surrounding whitespace.

No marks or contributions are stored here.

## 4. `ChoiceEvaluationAuthority`

```text
schema_version
grading_spec_ref
question_id
compiled_authority_hash
option_ids
official_option_id
match_projection
mismatch_projection
```

Local invariants:

- schema version is exactly `CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION`;
- `grading_spec_ref` is exact `GradingSpecRef`;
- `question_id` is exact valid string;
- `compiled_authority_hash` is exactly 64 lowercase hexadecimal characters;
- `option_ids` is exact non-empty `tuple[str, ...]`;
- every option ID is non-empty, no surrounding whitespace;
- option IDs are unique;
- `official_option_id` is an exact string and a member of `option_ids`;
- match and mismatch projections are exact non-empty immutable tuples of exact `ChoiceCriterionProjection`;
- neither projection contains duplicate criterion IDs;
- match and mismatch criterion-ID sequences are exactly equal.

The authority intentionally does not duplicate the scoring rubric. Criterion-level membership against the real rubric is validated only when the evaluator binds this authority to the actual `QuestionScoringAuthority`.

`ChoiceEvaluationAuthority` is ordinary immutable data, not a trust token.

## 5. `CanonicalChoiceSelection`

```text
schema_version
submission_ref
question_id
selected_option_id
evidence_refs
```

Local invariants:

- schema version is exactly `CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION`;
- `submission_ref`, `question_id`, and `selected_option_id` are exact non-empty strings without surrounding whitespace;
- `evidence_refs` is an exact non-empty immutable tuple of exact strings;
- every evidence ref is non-empty with no surrounding whitespace;
- duplicate evidence refs are rejected.

The selection represents one already-admitted single choice. It does not prove that the referenced evidence semantically says the selected option.

## 6. Scoring-authority binding

The evaluator accepts three admitted values. Their origin remains the responsibility of the upstream source:

```text
ChoiceEvaluationAuthority
CanonicalChoiceSelection
QuestionScoringAuthority
```

Before comparison/judgment construction:

1. `selection.question_id == choice_authority.question_id`, else `ChoiceSelectionBindingError`.
2. `choice_authority.question_id == scoring_authority.rubric.question_id == scoring_authority.policy.question_id`, else `ChoiceScoringAuthorityBindingError`.
3. `compiled_authority_fingerprint(scoring_authority) == choice_authority.compiled_authority_hash`, else `ChoiceScoringAuthorityBindingError`.
4. match/mismatch projection criterion-ID sequence equals the complete scoring-rubric criterion-ID sequence, else `ChoiceProjectionScoringMismatchError`.
5. every projected level is admitted by its scoring criterion, else `ChoiceProjectionScoringMismatchError`.

The evaluator validates these bindings before emitting criterion judgments.

## 7. Evidence applicability assertion

Pure CHOICE single-select is supported only when the selected-option outcome legitimately resolves **every** scoring criterion.

By issuing/admitting a `ChoiceEvaluationAuthority`, the domain authority explicitly asserts both:

1. selected-option match/mismatch determines the level of every projected criterion; and
2. the canonical selected-option evidence is semantically applicable support for every projected criterion.

The core evaluator cannot independently prove pedagogical evidence applicability.

If either assertion cannot truthfully be made, the question is outside pure CHOICE single-select and must use a later composite/other evaluator capability.

No extra boolean or duplicated criterion list is added solely to restate this invariant; it is part of the semantic meaning of the single-select authority type itself.

## 8. Outer run/evidence binding

`submission_ref` and `grading_spec_ref` are contextual bindings, not authentication.

Before vertical grading execution, an owning outer boundary MUST establish:

```text
selection.submission_ref == evidence.submission_ref

choice_authority.grading_spec_ref
    == grading run / execution context grading_spec_ref
```

The CHOICE evaluator itself does not authenticate these relationships because evidence-bundle binding and current grading-spec resolution belong to the outer workflow.

The current `QuestionScoringAuthority` does not carry `grading_spec_ref`, so CHOICE single-select also does not independently prove that the supplied scoring authority originated from the claimed grading-spec version.

The outer active-spec/resolution boundary must ultimately establish:

```text
grading run/spec version
        ↕
ChoiceEvaluationAuthority
        ↕
admitted QuestionScoringAuthority
```

The evaluator must not fabricate that provenance from equal IDs.

## 9. Core comparison

After all local/binding admission:

```text
selected_option_id == official_option_id
    → match_projection

selected_option_id != official_option_id
    → mismatch_projection
```

Before comparison, `selected_option_id` must belong to `option_ids`.

If it does not, raise `UnsupportedChoiceInputError`.

The evaluator performs no OCR parsing, fuzzy matching, mark arithmetic, negative marking, or risk/review routing.

## 10. Rich output

For each scoring criterion in exact scoring-rubric order emit one exact `EvaluatedCriterionJudgment`.

Fields:

```text
criterion_id
    from selected projection

selected_level
    from selected projection

evidence_refs
    exactly CanonicalChoiceSelection.evidence_refs

reason_codes
    match    → (CHOICE_MATCH_REASON_CODE,)
    mismatch → (CHOICE_MISMATCH_REASON_CODE,)

concise_rationale
    exact frozen match/mismatch rationale literal

uncertainties
    ()

evaluator_metadata
    EvaluatorMetadata(
        evaluator_id=DETERMINISTIC_CHOICE_EVALUATOR_ID,
        version=DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    )
```

The authority does not supply or override evaluator implementation identity/version.

Downstream evidence verification remains responsible for evidence existence, question ownership and crossed-out rejection.

## 11. Upstream unsupported states

`CanonicalChoiceSelection` represents exactly one admitted selection.

Upstream selection admission must reject rather than encode:

- blank/no selection;
- ambiguous extraction;
- multiple conflicting selections;
- multi-select;
- ranking;
- free-text EXACT.

These states are never converted to academic mismatch.

## 12. Verification

Production implementations: `src/grading/contracts/choice.py`,
`src/grading/choice_evaluator.py`, `src/grading/integration/choice_authority_admission.py`
and `src/grading/integration/whole_paper_choice_execution.py`.

Run:

```sh
python -m pytest -q tests/contracts/test_choice_evaluation_contract_regression.py tests/integration/test_choice_evaluator_behavior_regression.py tests/integration/test_whole_paper_choice_execution.py
```

The tests are executable against the current source. The tests must distinguish a known wrong option
(which yields a mismatch judgment) from an unknown option (which is rejected).

See [Deterministic scoring kernel](scoring_kernel_contract.md) for applying
marks to verified criterion judgments. See [Evidence and question binding](evidence_and_question_binding.md) for the separate submission and OCR checks.
