# Exact scoring-number contract

## Purpose

The grading numeric profile defines the exact scoring-number representation and arithmetic capability used by deterministic grading.

It prevents scoring behavior from depending on floating point, ambient Decimal context, huge unbounded numeric representations, or noncanonical values.

`numeric_profile_version="1"` is system execution provenance. It is not school-authored scoring authority and it is not a complete forensic build identity.

## Authoritative constant

```text
N = 4096 canonical digits
```

Derived limits include:

```text
normalized exponent min = -4095
normalized exponent max = +4095
raw exponent min        = -8190
raw exponent max        = +8191
raw text max            = 4104 characters
aligned sum term max    = 8191 digits
rounding cross product  = 8192 digits
coefficient product max = 12287 digits
```

These values are derived from the single profile constant rather than independently configured limits.

## Admitted raw input forms

`ScoringDecimal.from_raw()` admits only exact runtime types:

- `str`;
- `int`;
- `Decimal`.

It rejects:
- `float`;
- `bool`;
- subclasses used as alternate input channels;
- arbitrary coercion protocols;
- NaN;
- infinity.

### String path

Accepted text uses a bounded ASCII decimal grammar.

Profile checks include:
- total raw length;
- significand digit count;
- exponent digit width;
- raw exponent range;
- grammar validity.

No whitespace, underscores, Unicode digit families, NaN/Infinity spellings, or non-decimal syntax is scoring input.

### Integer path

Only exact integers within the profile magnitude are admitted.

Python's process-global integer-to-decimal-string setting is not allowed to become scoring authority.

### Decimal path

Direct Decimal input must be:
- exact runtime type `Decimal`;
- finite;
- inside the source/canonical representation envelope.

## Canonical representation

Every successful nonzero value is normalized manually to one coefficient/exponent representation without `Decimal.normalize()`.

Zero has exactly one internal representation:

```text
Decimal(0)
```

Canonical serialization:
- plain ASCII decimal;
- no exponent notation;
- no leading `+`;
- no `-0`;
- leading zero before fractions;
- exact round trip;
- context independent.

Observable canonical representation is part of the versioned profile behavior.

## Authorized Decimal use

Allowed:
- construction after path-specific validation;
- `as_tuple()`;
- `as_integer_ratio()` for validated finite values;
- `is_finite()` / `is_zero()`;
- direct comparison of admitted finite scoring decimals.

Not authoritative scoring arithmetic:
- Decimal `+`, `-`, `*`, `/`, `%`;
- `normalize()`;
- `quantize()`;
- `round()`;
- context-created scoring values;
- ambient-context arithmetic.

## Exact arithmetic

The scoring arithmetic layer uses exact integer/rational mechanics.

### `exact_sum`

Requirements:
- exact tuple of `ScoringDecimal`;
- empty tuple returns canonical zero;
- all operands are admitted before arithmetic;
- operation is order-independent within the separately admitted structural cardinality;
- prefixes are not envelope-checked as scoring values because exact cancellation is permitted;
- final mathematical result re-enters the same `ScoringDecimal` envelope.

### Subtraction

Values are aligned exactly by coefficient/exponent and the final result re-enters the scoring envelope.

### Comparison

Comparison operates on admitted finite scoring decimals without alignment arithmetic and without changing Decimal context.

### Integer multiplication

Used by exact rounding mechanics under operation-specific proven bounds.

## Rounding

The supported question-boundary rounding modes are:

- `HALF_UP`;
- `HALF_EVEN`.

Rounding uses exact integer ratios, quotient/remainder logic, and bounded integer products.

Ambient Decimal context does not control the result.

There is no paper-level rounding in the deterministic scoring kernel.

## Error separation

### `InvalidScoringValueError`

Malformed or unauthorized input type/value.

### `ScoringNumericEnvelopeError`

A valid numeric concept/representation exceeds the numeric profile's supported numeric envelope.

### `ScoreOutOfRangeError`

An admitted computed academic score lies outside configured policy bounds.

### Unexpected technical failure

Programming/runtime/infrastructure failures remain technical failures. They must not be converted into normal scoring-domain rejection or a numeric score.

## Version governance

Observable profile behavior includes:
- accepted/rejected inputs;
- normalization;
- canonical serialized bytes;
- deterministic error classification/precedence;
- numerical execution semantics.

An intentional change to observable profile behavior requires a numeric-profile version change.

The profile identifier alone is not a complete forensic build identity. Historical replay also requires an implementation conforming to the recorded profile and the relevant source/build identity.

## Structural cardinality boundary

Numeric Profile v1 does **not** authorize arbitrary structural cardinality.

It assumes structural/job admission has already bounded:
- exam/paper question counts;
- criteria/rule counts;
- result/provenance amplification;
- payload structure;
- runtime work/concurrency.

Therefore:

> Passing Numeric Profile v1 does not by itself authorize unrestricted external production ingestion.

Explicit limits must be defined and tested at the appropriate ingress/job/compiler/result boundaries before unrestricted production traffic is admitted.

## Source and verification

The numeric profile constants are in `src/grading/contracts/numeric_profile.py`,
its input representation is in `src/grading/contracts/scoring_decimal.py`,
and exact arithmetic and rounding are in `src/grading/scoring/arithmetic.py`
and `src/grading/scoring/rounding.py`.

Run:

```sh
python -m pytest -q tests/unit/test_arithmetic.py tests/unit/test_rounding.py tests/property/test_numeric_profile_hypothesis.py
```

A score representation is not a substitute for academic rules. Those live in
[Deterministic scoring kernel contract](scoring_kernel_contract.md).
