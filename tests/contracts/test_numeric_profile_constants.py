from __future__ import annotations

import pytest

from grading.contracts.numeric_profile import (
    MAX_ALIGNED_SUM_TERM_DIGITS,
    MAX_COEFFICIENT_PRODUCT_DIGITS,
    MAX_INTEGER_MULTIPLIER_DIGITS,
    MAX_ROUNDING_CROSS_PRODUCT_DIGITS,
    MAX_SCORING_CANONICAL_DIGITS,
    NUMERIC_PROFILE_VERSION,
    RAW_EXPONENT_MAX,
    RAW_EXPONENT_MAX_DIGITS,
    RAW_EXPONENT_MIN,
    RAW_TEXT_MAX_CHARS,
    canonical_digit_count,
    clog10_int,
    decimal_digit_count_positive,
)


def test_numeric_profile_v1_constants_are_derived_from_one_n() -> None:
    n = MAX_SCORING_CANONICAL_DIGITS

    assert NUMERIC_PROFILE_VERSION == "1"
    assert n == 4096
    assert RAW_TEXT_MAX_CHARS == n + 8 == 4104
    assert RAW_EXPONENT_MIN == 2 - (2 * n) == -8190
    assert RAW_EXPONENT_MAX == (2 * n) - 1 == 8191
    assert RAW_EXPONENT_MAX_DIGITS == 4
    assert MAX_ALIGNED_SUM_TERM_DIGITS == (2 * n) - 1 == 8191
    assert MAX_ROUNDING_CROSS_PRODUCT_DIGITS == 2 * n == 8192
    assert MAX_INTEGER_MULTIPLIER_DIGITS == (2 * n) - 1 == 8191
    assert MAX_COEFFICIENT_PRODUCT_DIGITS == (3 * n) - 1 == 12287


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 1), (9, 1), (10, 2), (99, 2), (100, 3), (10**50, 51)],
)
def test_decimal_digit_count_positive_is_integer_only(value: int, expected: int) -> None:
    assert decimal_digit_count_positive(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 0), (2, 1), (9, 1), (10, 1), (11, 2), (100, 2), (101, 3)],
)
def test_clog10_int_matches_frozen_definition(value: int, expected: int) -> None:
    assert clog10_int(value) == expected


@pytest.mark.parametrize("value", [0, -1, True, 1.0])
def test_integer_profile_helpers_reject_invalid_inputs(value: object) -> None:
    with pytest.raises(ValueError):
        decimal_digit_count_positive(value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        clog10_int(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("digits", "exponent", "expected"),
    [
        (1, 0, 1),
        (4, 0, 4),
        (1, 3, 4),
        (3, -1, 3),
        (3, -3, 4),
        (1, -4095, 4096),
        (1, 4095, 4096),
    ],
)
def test_canonical_digit_count_matches_profile_formula(
    digits: int,
    exponent: int,
    expected: int,
) -> None:
    assert canonical_digit_count(digits, exponent) == expected
