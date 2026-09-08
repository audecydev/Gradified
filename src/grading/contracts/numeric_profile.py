from __future__ import annotations


NUMERIC_PROFILE_VERSION = "1"
MAX_SCORING_CANONICAL_DIGITS = 4096

# All profile limits below are derived from the one authoritative N value.
RAW_EXPONENT_MIN = 2 - (2 * MAX_SCORING_CANONICAL_DIGITS)
RAW_EXPONENT_MAX = (2 * MAX_SCORING_CANONICAL_DIGITS) - 1
INTEGER_MAGNITUDE_EXCLUSIVE = 10**MAX_SCORING_CANONICAL_DIGITS
MAX_ALIGNED_SUM_TERM_DIGITS = (2 * MAX_SCORING_CANONICAL_DIGITS) - 1
MAX_ROUNDING_CROSS_PRODUCT_DIGITS = 2 * MAX_SCORING_CANONICAL_DIGITS
MAX_INTEGER_MULTIPLIER_DIGITS = (2 * MAX_SCORING_CANONICAL_DIGITS) - 1
MAX_COEFFICIENT_PRODUCT_DIGITS = (3 * MAX_SCORING_CANONICAL_DIGITS) - 1
MAX_INTEGER_MULTIPLIER_EXCLUSIVE = 10**MAX_INTEGER_MULTIPLIER_DIGITS


def decimal_digit_count_positive(value: int) -> int:
    """Return the base-10 digit count of a strictly positive exact integer.

    This helper intentionally avoids decimal integer-to-string conversion so
    Numeric Profile v1 is independent of CPython's PYTHONINTMAXSTRDIGITS.
    """

    if type(value) is not int or value <= 0:
        raise ValueError("decimal_digit_count_positive requires a positive int.")

    count = 0
    remaining = value
    while remaining:
        remaining //= 10
        count += 1
    return count


def clog10_int(value: int) -> int:
    """Return the exact integer ceiling of log10(value) for value >= 1.

    Defined without floating point:
        clog10_int(1) = 0
        clog10_int(m) = digits(m - 1), for m >= 2
    """

    if type(value) is not int or value < 1:
        raise ValueError("clog10_int requires an int >= 1.")
    if value == 1:
        return 0
    return decimal_digit_count_positive(value - 1)


RAW_EXPONENT_MAX_DIGITS = decimal_digit_count_positive(
    max(abs(RAW_EXPONENT_MIN), abs(RAW_EXPONENT_MAX))
)
RAW_TEXT_MAX_CHARS = (
    MAX_SCORING_CANONICAL_DIGITS
    + 4  # value sign, decimal point, exponent marker, exponent sign
    + RAW_EXPONENT_MAX_DIGITS
)


def canonical_digit_count(coefficient_digits: int, exponent: int) -> int:
    """Return Profile-v1 canonical plain-decimal digit count for non-zero data."""

    if type(coefficient_digits) is not int or coefficient_digits < 1:
        raise ValueError("coefficient_digits must be a positive int.")
    if type(exponent) is not int:
        raise ValueError("exponent must be an int.")

    if exponent >= 0:
        return coefficient_digits + exponent
    if coefficient_digits + exponent > 0:
        return coefficient_digits
    return 1 - exponent
