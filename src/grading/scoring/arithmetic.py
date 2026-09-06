from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from grading.contracts.errors import InvalidScoringValueError
from grading.contracts.scoring_decimal import ScoringDecimal


def _coefficient_and_exponent(
    value: ScoringDecimal,
) -> tuple[int, int]:
    sign, digits, exponent = value.as_decimal().as_tuple()

    coefficient = 0

    for digit in digits:
        coefficient = coefficient * 10 + digit

    if sign:
        coefficient = -coefficient

    return coefficient, exponent


def _from_coefficient_and_exponent(
    coefficient: int,
    exponent: int,
) -> ScoringDecimal:
    if coefficient == 0:
        return ScoringDecimal(Decimal(0))

    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1

    sign = 1 if coefficient < 0 else 0
    digits = tuple(
        int(character)
        for character in str(abs(coefficient))
    )

    return ScoringDecimal(
        Decimal((sign, digits, exponent))
    )


def _require_scoring_decimal(
    value: object,
) -> ScoringDecimal:
    if type(value) is not ScoringDecimal:
        raise InvalidScoringValueError(
            "Exact arithmetic accepts ScoringDecimal operands only."
        )

    return value


def exact_sum(
    values: Iterable[ScoringDecimal],
) -> ScoringDecimal:
    """Add scoring decimals without consulting Decimal arithmetic context."""

    parts: list[tuple[int, int]] = []

    for value in values:
        validated = _require_scoring_decimal(value)
        parts.append(
            _coefficient_and_exponent(validated)
        )

    if not parts:
        return ScoringDecimal.from_raw(0)

    common_exponent = min(
        exponent
        for _, exponent in parts
    )

    total_coefficient = sum(
        coefficient
        * (10 ** (exponent - common_exponent))
        for coefficient, exponent in parts
    )

    return _from_coefficient_and_exponent(
        total_coefficient,
        common_exponent,
    )


def exact_subtract(
    left: ScoringDecimal,
    right: ScoringDecimal,
) -> ScoringDecimal:
    """Subtract scoring decimals exactly and context-independently."""

    validated_left = _require_scoring_decimal(left)
    validated_right = _require_scoring_decimal(right)

    right_coefficient, right_exponent = (
        _coefficient_and_exponent(validated_right)
    )

    negated_right = _from_coefficient_and_exponent(
        -right_coefficient,
        right_exponent,
    )

    return exact_sum(
        (validated_left, negated_right)
    )


def exact_minimum(
    left: ScoringDecimal,
    right: ScoringDecimal,
) -> ScoringDecimal:
    """Return the mathematical minimum without Decimal-context arithmetic."""

    validated_left = _require_scoring_decimal(left)
    validated_right = _require_scoring_decimal(right)

    left_coefficient, left_exponent = (
        _coefficient_and_exponent(validated_left)
    )
    right_coefficient, right_exponent = (
        _coefficient_and_exponent(validated_right)
    )

    common_exponent = min(
        left_exponent,
        right_exponent,
    )

    scaled_left = (
        left_coefficient
        * (10 ** (left_exponent - common_exponent))
    )
    scaled_right = (
        right_coefficient
        * (10 ** (right_exponent - common_exponent))
    )

    if scaled_left <= scaled_right:
        return validated_left

    return validated_right