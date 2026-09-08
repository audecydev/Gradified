from __future__ import annotations

from decimal import Decimal

from grading.contracts.errors import (
    InvalidScoringValueError,
    ScoringNumericEnvelopeError,
)
from grading.contracts.numeric_profile import (
    INTEGER_MAGNITUDE_EXCLUSIVE,
    MAX_ALIGNED_SUM_TERM_DIGITS,
    MAX_COEFFICIENT_PRODUCT_DIGITS,
    MAX_INTEGER_MULTIPLIER_EXCLUSIVE,
    MAX_SCORING_CANONICAL_DIGITS,
    canonical_digit_count,
    clog10_int,
)
from grading.contracts.scoring_decimal import ScoringDecimal


def _coefficient_and_exponent(
    value: ScoringDecimal,
) -> tuple[int, int]:
    sign, digits, exponent = value.as_decimal().as_tuple()

    coefficient = 0
    for digit in digits:
        coefficient = (coefficient * 10) + digit
    if sign:
        coefficient = -coefficient

    return coefficient, exponent


def _normalized_coefficient_and_exponent(
    coefficient: int,
    exponent: int,
) -> tuple[int, int]:
    if coefficient == 0:
        return 0, 0

    normalized_coefficient = coefficient
    normalized_exponent = exponent
    while normalized_coefficient % 10 == 0:
        normalized_coefficient //= 10
        normalized_exponent += 1

    return normalized_coefficient, normalized_exponent


def _integer_decimal_digit_count(value: int) -> int:
    """Return exact base-10 digits without int-to-string conversion.

    Callers use this only for already-proven bounded integer intermediates.
    Decimal(int) is exact representation construction and does not use the
    process-global integer-to-decimal-string limit.
    """

    if type(value) is not int:
        raise RuntimeError("Internal arithmetic digit count received a non-int.")
    if value == 0:
        return 1
    return len(Decimal(abs(value)).as_tuple().digits)


def _require_internal_digit_bound(
    value: int,
    maximum_digits: int,
    operation: str,
) -> None:
    """Enforce a reviewed implementation-intermediate theorem.

    This is deliberately a RuntimeError, not a ScoringError. With validated
    Profile-v1 inputs, exceeding an operation-specific proof bound indicates a
    programming/invariant defect rather than an unsupported student score.
    """

    if _integer_decimal_digit_count(value) > maximum_digits:
        raise RuntimeError(
            f"Numeric Profile v1 internal {operation} bound was violated."
        )


def _align_coefficient(
    coefficient: int,
    exponent: int,
    common_exponent: int,
) -> int:
    """Align one normalized coefficient within the frozen 2N-1 theorem."""

    shift = exponent - common_exponent
    if shift < 0:
        raise RuntimeError(
            "Numeric Profile v1 internal alignment exponent invariant was violated."
        )

    if coefficient == 0:
        return 0

    coefficient_digits = _integer_decimal_digit_count(coefficient)
    aligned_digits = coefficient_digits + shift
    if aligned_digits > MAX_ALIGNED_SUM_TERM_DIGITS:
        raise RuntimeError(
            "Numeric Profile v1 internal aligned-term bound was violated."
        )

    aligned = coefficient * (10**shift)
    _require_internal_digit_bound(
        aligned,
        MAX_ALIGNED_SUM_TERM_DIGITS,
        "aligned-term",
    )
    return aligned


def _bounded_integer_product(
    left: int,
    right: int,
    maximum_digits: int,
    operation: str,
) -> int:
    """Multiply two proven bounded integers under an operation-specific bound."""

    if type(left) is not int or type(right) is not int:
        raise RuntimeError("Internal bounded multiplication received a non-int.")

    if left == 0 or right == 0:
        return 0

    left_digits = _integer_decimal_digit_count(left)
    right_digits = _integer_decimal_digit_count(right)

    # At all reviewed call sites the mathematical proof guarantees that the sum
    # of operand digit counts is already no larger than the frozen product bound.
    # If that precondition is ever false, fail before materializing the product.
    if left_digits + right_digits > maximum_digits:
        raise RuntimeError(
            f"Numeric Profile v1 internal {operation} pre-admission bound was violated."
        )

    product = left * right
    _require_internal_digit_bound(product, maximum_digits, operation)
    return product


def _decimal_digits_from_bounded_integer(value: int) -> tuple[int, ...]:
    """Return exact decimal digits without using int-to-string conversion.

    The caller proves |value| < 10^N first, so Decimal(int) cannot introduce an
    unbounded materialized scoring representation here.
    """

    return Decimal(abs(value)).as_tuple().digits


def _from_coefficient_and_exponent(
    coefficient: int,
    exponent: int,
) -> ScoringDecimal:
    normalized_coefficient, normalized_exponent = (
        _normalized_coefficient_and_exponent(coefficient, exponent)
    )

    if normalized_coefficient == 0:
        return ScoringDecimal(Decimal(0))

    absolute = abs(normalized_coefficient)
    # A normalized coefficient with N+1 digits can never produce an in-profile
    # ScoringDecimal, regardless of exponent. Reject before Decimal materialization.
    if absolute >= INTEGER_MAGNITUDE_EXCLUSIVE:
        raise ScoringNumericEnvelopeError(
            "Arithmetic result exceeds Numeric Profile v1 coefficient envelope."
        )

    digits = _decimal_digits_from_bounded_integer(normalized_coefficient)
    if canonical_digit_count(len(digits), normalized_exponent) > MAX_SCORING_CANONICAL_DIGITS:
        raise ScoringNumericEnvelopeError(
            "Arithmetic result exceeds Numeric Profile v1 canonical envelope."
        )

    sign = 1 if normalized_coefficient < 0 else 0
    return ScoringDecimal(Decimal((sign, digits, normalized_exponent)))


def _require_scoring_decimal(value: object) -> ScoringDecimal:
    if type(value) is not ScoringDecimal:
        raise InvalidScoringValueError(
            "Exact arithmetic accepts ScoringDecimal operands only."
        )
    return value


def exact_sum(values: tuple[ScoringDecimal, ...]) -> ScoringDecimal:
    """Add a finite materialized tuple exactly and order-independently.

    Structural cardinality admission belongs to the caller/authority boundary.
    Numeric Profile v1 proves the arithmetic intermediate bound as a function
    of N and m; this primitive does not invent a product cardinality limit.
    """

    if type(values) is not tuple:
        raise InvalidScoringValueError(
            "exact_sum requires an exact tuple of ScoringDecimal values."
        )

    if not values:
        return ScoringDecimal(Decimal(0))

    parts: list[tuple[int, int]] = []
    for value in values:
        validated = _require_scoring_decimal(value)
        parts.append(_coefficient_and_exponent(validated))

    common_exponent = min(exponent for _, exponent in parts)
    accumulator_digit_bound = MAX_ALIGNED_SUM_TERM_DIGITS + clog10_int(len(parts))

    total_coefficient = 0
    for coefficient, exponent in parts:
        aligned = _align_coefficient(coefficient, exponent, common_exponent)
        total_coefficient += aligned
        # This is not a scoring-envelope check. It is an implementation theorem
        # check against the order-independent full-operation bound for m terms.
        _require_internal_digit_bound(
            total_coefficient,
            accumulator_digit_bound,
            "sum-accumulator",
        )

    # Do not materialize or envelope-check prefixes as ScoringDecimal values.
    # Cancellation is part of the exact operation; only the final mathematical
    # result re-enters the scoring-value envelope.
    return _from_coefficient_and_exponent(total_coefficient, common_exponent)


def exact_subtract(
    left: ScoringDecimal,
    right: ScoringDecimal,
) -> ScoringDecimal:
    """Subtract scoring decimals exactly without Decimal arithmetic context."""

    validated_left = _require_scoring_decimal(left)
    validated_right = _require_scoring_decimal(right)
    left_coefficient, left_exponent = _coefficient_and_exponent(validated_left)
    right_coefficient, right_exponent = _coefficient_and_exponent(validated_right)

    common_exponent = min(left_exponent, right_exponent)
    aligned_left = _align_coefficient(
        left_coefficient,
        left_exponent,
        common_exponent,
    )
    aligned_right = _align_coefficient(
        right_coefficient,
        right_exponent,
        common_exponent,
    )
    total_coefficient = aligned_left - aligned_right
    _require_internal_digit_bound(
        total_coefficient,
        MAX_ALIGNED_SUM_TERM_DIGITS + clog10_int(2),
        "subtraction-accumulator",
    )
    return _from_coefficient_and_exponent(total_coefficient, common_exponent)


def exact_compare(
    left: ScoringDecimal,
    right: ScoringDecimal,
) -> int:
    """Compare validated finite scoring decimals without alignment arithmetic."""

    validated_left = _require_scoring_decimal(left)
    validated_right = _require_scoring_decimal(right)
    left_decimal = validated_left.as_decimal()
    right_decimal = validated_right.as_decimal()

    if left_decimal < right_decimal:
        return -1
    if left_decimal > right_decimal:
        return 1
    return 0


def exact_minimum(
    left: ScoringDecimal,
    right: ScoringDecimal,
) -> ScoringDecimal:
    """Return the mathematical minimum of two validated scoring decimals."""

    validated_left = _require_scoring_decimal(left)
    validated_right = _require_scoring_decimal(right)

    if exact_compare(validated_left, validated_right) <= 0:
        return validated_left
    return validated_right


def exact_multiply_integer(
    value: ScoringDecimal,
    multiplier: int,
) -> ScoringDecimal:
    """Multiply by an exact integer within Profile-v1 proven work bounds."""

    validated_value = _require_scoring_decimal(value)
    if type(multiplier) is not int:
        raise InvalidScoringValueError(
            "Exact integer multiplication requires an exact int multiplier."
        )

    if multiplier == 0 or validated_value.as_decimal().is_zero():
        return ScoringDecimal(Decimal(0))

    if abs(multiplier) >= MAX_INTEGER_MULTIPLIER_EXCLUSIVE:
        raise ScoringNumericEnvelopeError(
            "Integer multiplier exceeds Numeric Profile v1 operation bound."
        )

    coefficient, exponent = _coefficient_and_exponent(validated_value)
    product = _bounded_integer_product(
        coefficient,
        multiplier,
        MAX_COEFFICIENT_PRODUCT_DIGITS,
        "coefficient-product",
    )
    _require_internal_digit_bound(
        product,
        MAX_COEFFICIENT_PRODUCT_DIGITS,
        "coefficient-product",
    )
    return _from_coefficient_and_exponent(product, exponent)
