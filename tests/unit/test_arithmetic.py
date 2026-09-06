from decimal import Decimal, Inexact, ROUND_DOWN, localcontext

import pytest

from grading.contracts.errors import InvalidScoringValueError
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import (
    exact_minimum,
    exact_subtract,
    exact_sum,
)


def scoring_decimal(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def test_exact_sum_handles_fractional_values() -> None:
    result = exact_sum(
        (
            scoring_decimal("0.1"),
            scoring_decimal("0.2"),
            scoring_decimal("0.7"),
        )
    )

    assert result.to_canonical_string() == "1"


def test_exact_sum_of_empty_collection_is_zero() -> None:
    result = exact_sum(())

    assert result.to_canonical_string() == "0"


def test_exact_subtraction_is_exact() -> None:
    result = exact_subtract(
        scoring_decimal("123456789.01"),
        scoring_decimal("0.02"),
    )

    assert result.to_canonical_string() == "123456788.99"


def test_exact_minimum_handles_negative_values() -> None:
    result = exact_minimum(
        scoring_decimal("-0.25"),
        scoring_decimal("0"),
    )

    assert result.to_canonical_string() == "-0.25"


def test_sum_is_independent_of_input_order() -> None:
    values = (
        scoring_decimal("100.01"),
        scoring_decimal("-0.01"),
        scoring_decimal("0.25"),
        scoring_decimal("0.75"),
    )

    forward = exact_sum(values)
    reversed_result = exact_sum(reversed(values))

    assert forward == reversed_result
    assert forward.to_canonical_string() == "101"


@pytest.mark.parametrize(
    "precision",
    [2, 6, 50],
)
def test_arithmetic_is_independent_of_ambient_decimal_context(
    precision: int,
) -> None:
    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True

        result = exact_sum(
            (
                scoring_decimal("123456789.01"),
                scoring_decimal("0.99"),
            )
        )

        difference = exact_subtract(
            scoring_decimal("123456789.01"),
            scoring_decimal("0.02"),
        )

    assert result.to_canonical_string() == "123456790"
    assert difference.to_canonical_string() == "123456788.99"


def test_exact_arithmetic_rejects_raw_decimal_operand() -> None:
    with pytest.raises(InvalidScoringValueError):
        exact_sum(
            (
                scoring_decimal("1"),
                Decimal("2"),  # type: ignore[arg-type]
            )
        )