from __future__ import annotations

from grading.contracts.errors import InvalidScoringValueError
from grading.contracts.numeric_profile import MAX_ROUNDING_CROSS_PRODUCT_DIGITS
from grading.contracts.policy import RoundingMode, RoundingRule
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import (
    _bounded_integer_product,
    _require_internal_digit_bound,
    exact_multiply_integer,
)


def _round_to_increment(
    value: ScoringDecimal,
    rule: RoundingRule,
) -> ScoringDecimal:
    """Round exactly to the nearest configured increment.

    The rounding decision uses exact integer ratios and Python integer
    quotient/remainder arithmetic. Decimal context precision, rounding, exponent
    limits, traps, and flags therefore have no scoring authority here.
    """

    if type(value) is not ScoringDecimal:
        raise InvalidScoringValueError(
            "Rounding accepts a ScoringDecimal value only."
        )
    if type(rule) is not RoundingRule:
        raise InvalidScoringValueError(
            "Rounding accepts a validated RoundingRule only."
        )

    value_numerator, value_denominator = value.as_decimal().as_integer_ratio()
    increment_numerator, increment_denominator = (
        rule.increment.as_decimal().as_integer_ratio()
    )

    # RoundingRule validation guarantees a strictly positive finite increment.
    numerator = _bounded_integer_product(
        value_numerator,
        increment_denominator,
        MAX_ROUNDING_CROSS_PRODUCT_DIGITS,
        "rounding-numerator-cross-product",
    )
    denominator = _bounded_integer_product(
        value_denominator,
        increment_numerator,
        MAX_ROUNDING_CROSS_PRODUCT_DIGITS,
        "rounding-denominator-cross-product",
    )
    # Reassert the exact operation-specific theorem at the consuming boundary.
    # These RuntimeError checks classify implementation drift as a programming
    # defect rather than misreporting it as a scoring-domain envelope failure.
    _require_internal_digit_bound(
        numerator,
        MAX_ROUNDING_CROSS_PRODUCT_DIGITS,
        "rounding-numerator-cross-product",
    )
    _require_internal_digit_bound(
        denominator,
        MAX_ROUNDING_CROSS_PRODUCT_DIGITS,
        "rounding-denominator-cross-product",
    )

    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(numerator), denominator)
    # Compare the remainder to its complement rather than multiplying it by
    # two. This keeps tie classification inside the proven ratio-product bound.
    complement = denominator - remainder

    if remainder < complement:
        rounded_multiple = quotient
    elif remainder > complement:
        rounded_multiple = quotient + 1
    elif rule.mode is RoundingMode.HALF_UP:
        rounded_multiple = quotient + 1
    elif rule.mode is RoundingMode.HALF_EVEN:
        rounded_multiple = quotient if quotient % 2 == 0 else quotient + 1
    else:  # Defensive: policy validation should make this unreachable.
        raise RuntimeError("Unsupported rounding mode reached exact rounding.")

    signed_multiple = 0 if rounded_multiple == 0 else sign * rounded_multiple
    return exact_multiply_integer(rule.increment, signed_multiple)
