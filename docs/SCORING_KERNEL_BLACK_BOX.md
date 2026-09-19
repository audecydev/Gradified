# Deterministic Scoring Kernel — Black-Box Contract

## Purpose

The deterministic scoring kernel is the numerical authority boundary of the grading core.

It converts already-admitted scoring authority and semantic judgments/results into exact question and paper scores. It deliberately does **not** interpret OCR, judge answer meaning, authenticate backend authority, or publish results.

## Authority chain

At question scope:

`CompiledQuestionRubric + QuestionScoringPolicy + CriterionJudgment tuple -> QuestionScoreResult`

At paper scope:

`ResolvedPaperScoringAuthority + QuestionScoreResult tuple -> PaperScoreResult`

A probabilistic evaluator may select an approved rubric level. It has no authoritative numerical-total input path.

## Numeric authority

All authoritative scoring values use `ScoringDecimal` under Numeric Profile v1.

Important properties:

- exact finite decimal values only;
- canonical internal representation;
- canonical plain-decimal serialization;
- no float scoring inputs;
- authoritative arithmetic independent of ambient Decimal context;
- numeric-envelope failure is distinct from academic score-range failure.

See `NUMERIC_PROFILE_V1.md`.

## Question scoring public boundary

Primary operation:

```python
reduce_question(
    authority: QuestionScoringAuthority,
    judgments: tuple[CriterionJudgment, ...],
) -> QuestionScoreResult
```

### Required admitted authority

`QuestionScoringAuthority` pairs:

- one `CompiledQuestionRubric`;
- one `QuestionScoringPolicy`.

The authority validates:
- exact contract types;
- matching question identity;
- rubric maximum equal to policy maximum;
- rule references;
- performance-level references;
- acyclic positive-credit dependencies.

Full authoring-time rubric reconciliation belongs to the rubric compiler/activation boundary, not this reducer.

### Judgment admission

Exactly one `CriterionJudgment` is required per atomic criterion.

Rejected:
- unknown criterion;
- unknown level;
- duplicate criterion judgment;
- missing criterion judgment;
- wrong collection/item runtime types.

Judgments are canonicalized to rubric criterion order.

### Question scoring order

1. map each selected level to its rubric-authorized contribution;
2. evaluate positive-credit dependencies against original judgments;
3. suppress unauthorized positive target contribution while preserving zero/negative configured contribution;
4. exact-sum effective criterion contributions;
5. apply triggered gates;
6. apply triggered caps;
7. exact-sum and subtract triggered deductions once each;
8. apply exactly one configured question-boundary rounding transformation, if present;
9. validate final score against policy minimum/maximum;
10. construct one immutable result.

No earlier stage may clamp or silently convert an invalid score to zero.

### Question result provenance

A successful `QuestionScoreResult` records:

- question identity;
- rubric identity/version;
- scoring-policy identity/version/scoring-semantics version;
- numeric-profile version;
- criterion base/effective contributions;
- dependency blockers;
- one decision per configured conditional rule;
- deterministic stage before/after provenance;
- base subtotal;
- score before rounding;
- final score;
- question minimum/maximum.

## Paper aggregation public boundary

Primary operation:

```python
aggregate_paper(
    authority: ResolvedPaperScoringAuthority,
    question_results: tuple[QuestionScoreResult, ...],
) -> PaperScoreResult
```

### Required admitted authority

`ResolvedPaperScoringAuthority` contains:

- `grading_spec_ref`;
- ordered non-empty tuple of expected question-result identities;
- authoritative paper minimum;
- authoritative paper maximum.

The exact countable question composition must already have been resolved upstream. The aggregator never selects, remaps, substitutes, or infers which questions count.

### Paper admission order

1. defensively re-admit authority structure;
2. require an exact result tuple;
3. validate result question IDs;
4. reject duplicate supplied IDs;
5. require exact expected/supplied question-set equality;
6. verify question/rubric/policy/scoring-semantics identity in authority order;
7. require supported numeric-profile provenance;
8. re-admit and check consumed question min/final/max values;
9. rebuild the result tuple in authority order using the same immutable result objects;
10. exact-sum `final_score` values only;
11. enforce authoritative paper range;
12. construct one immutable paper result.

### Paper numerical authority

Contributes to the paper total:

- `QuestionScoreResult.final_score`, and nothing else.

Does **not** contribute:

- question minimum;
- question maximum;
- criterion effects;
- stage effects;
- model/evaluator totals;
- OCR totals;
- student-written totals;
- textual numbering.

Paper bounds are supplied by `ResolvedPaperScoringAuthority`. They are not derived from the sum of question bounds.

### Ordering

Caller input order has no scoring authority.

Authority order controls canonical output/provenance order only. It is not weighting, priority, or sequence-dependent scoring.

### No paper rounding

Paper aggregation performs no rounding. Question scores are already final at the question boundary.

## Failure semantics

Expected scoring-domain failures include:

- invalid numeric value;
- numeric-profile envelope violation;
- invalid scoring authority;
- invalid criterion judgment;
- unknown criterion/level;
- duplicate/missing judgment;
- invalid paper aggregation input;
- final score outside configured academic range.

Known malformed input fails with the appropriate typed domain error.

Unexpected programming/runtime defects must remain technical failures. Broad catch-all conversion into a scoring result is forbidden.

Failure never means:
- clamp to min/max;
- substitute zero;
- return a partial successful result;
- silently skip a question;
- fabricate provenance.

## Immutability

Safety-critical contracts are frozen/slotted and collection fields use immutable tuples.

The paper result intentionally retains the same admitted immutable `QuestionScoreResult` objects in canonical authority order rather than rebuilding or normalizing them.

## What the kernel does not prove

A successful result does not prove:
- the authority came from an authenticated backend;
- the school configuration is academically correct;
- OCR read the answer correctly;
- the evaluator selected the correct semantic level;
- optional-question resolution was correct;
- external job size is safe;
- the result was persisted or published correctly.

Those are separate system boundaries.

## Resource/cardinality boundary

Numeric Profile v1 bounds numerical representation and arithmetic work. It does not define arbitrary structural/job cardinality.

Unrestricted production ingestion must remain blocked until the relevant upstream exam/job boundaries define and test explicit limits.

## Verification baseline

Qualified runtime:
- Windows x64;
- CPython 3.11.9;
- version-pinned dependency closure in `requirements-test.txt`.

Final committed acceptance:
- 519/519 tests passed;
- 0 failures/errors/skips;
- exact testcase identity union;
- targeted mutation analysis with no unresolved contract-distinguishing mutation;
- final whole-kernel source/authority audit passed.
