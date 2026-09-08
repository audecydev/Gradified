from __future__ import annotations

from decimal import (
    Clamped,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_FLOOR,
    Rounded,
    Subnormal,
    Underflow,
    getcontext,
    localcontext,
)
from fractions import Fraction
from itertools import permutations

import pytest

import grading.contracts.errors as scoring_errors
from grading.contracts.errors import InvalidScoringValueError
from grading.contracts.numeric_profile import (
    MAX_ALIGNED_SUM_TERM_DIGITS,
    MAX_COEFFICIENT_PRODUCT_DIGITS,
    MAX_SCORING_CANONICAL_DIGITS,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import (
    _align_coefficient,
    _coefficient_and_exponent,
    _integer_decimal_digit_count,
    exact_compare,
    exact_minimum,
    exact_multiply_integer,
    exact_subtract,
    exact_sum,
)


N = MAX_SCORING_CANONICAL_DIGITS


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def _envelope_error() -> type[Exception]:
    error_type = getattr(scoring_errors, "ScoringNumericEnvelopeError", None)
    assert isinstance(error_type, type), (
        "Numeric Profile v1 requires ScoringNumericEnvelopeError."
    )
    return error_type


def _context_snapshot(context: Context) -> tuple[object, ...]:
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        tuple(sorted((signal.__name__, enabled) for signal, enabled in context.traps.items())),
        tuple(sorted((signal.__name__, enabled) for signal, enabled in context.flags.items())),
    )


def _hostile_context() -> Context:
    context = Context(
        prec=1,
        rounding=ROUND_FLOOR,
        Emin=-1,
        Emax=1,
        capitals=0,
        clamp=1,
    )
    for signal in (
        Clamped,
        DivisionByZero,
        Inexact,
        InvalidOperation,
        Overflow,
        Rounded,
        Subnormal,
        Underflow,
    ):
        context.traps[signal] = True
        context.flags[signal] = False
    return context


def test_exact_sum_requires_exact_tuple() -> None:
    values = (sd("1"), sd("2"))

    assert exact_sum(values).to_canonical_string() == "3"

    with pytest.raises(InvalidScoringValueError):
        exact_sum(list(values))  # type: ignore[arg-type]

    with pytest.raises(InvalidScoringValueError):
        exact_sum((value for value in values))  # type: ignore[arg-type]


class TupleSubclass(tuple):
    pass


def test_exact_sum_rejects_tuple_subclass() -> None:
    with pytest.raises(InvalidScoringValueError):
        exact_sum(TupleSubclass((sd("1"),)))  # type: ignore[arg-type]


def test_exact_sum_empty_tuple_is_canonical_zero() -> None:
    result = exact_sum(())

    assert result.as_decimal().as_tuple() == Decimal(0).as_tuple()
    assert result.to_canonical_string() == "0"


def test_cancellation_and_permutation_do_not_use_prefix_envelope() -> None:
    x = sd("9" * N)
    y = sd("1e-4095")
    negative_x = sd("-" + ("9" * N))
    expected = y

    values = (x, y, negative_x)
    for ordering in permutations(values):
        result = exact_sum(tuple(ordering))
        assert result == expected




def test_alignment_materializes_exact_frozen_boundary_not_more() -> None:
    x = sd("9" * N)
    coefficient, exponent = _coefficient_and_exponent(x)

    aligned = _align_coefficient(coefficient, exponent, 1 - N)

    assert _integer_decimal_digit_count(aligned) == MAX_ALIGNED_SUM_TERM_DIGITS


def test_extreme_subtraction_uses_profile_error_not_internal_bound_failure() -> None:
    error_type = _envelope_error()
    x = sd("9" * N)
    tiny = sd("1e-4095")

    with pytest.raises(error_type):
        exact_subtract(x, tiny)


def test_out_of_envelope_sum_has_order_independent_failure() -> None:
    error_type = _envelope_error()
    x = sd("9" * N)
    y = sd("1e-4095")

    for ordering in ((x, y), (y, x)):
        with pytest.raises(error_type):
            exact_sum(ordering)


def test_minimum_uses_numeric_comparison_for_opposite_exponent_extremes() -> None:
    tiny = sd("1e-4095")
    huge = sd("1e4095")

    assert exact_minimum(tiny, huge) is tiny
    assert exact_minimum(huge, tiny) is tiny


def test_numeric_primitives_do_not_mutate_hostile_decimal_context() -> None:
    hostile = _hostile_context()

    with localcontext(hostile) as context:
        before = _context_snapshot(context)

        total = exact_sum((sd("123456789.01"), sd("0.99")))
        difference = exact_subtract(sd("123456789.01"), sd("0.02"))
        minimum = exact_minimum(sd("-0.25"), sd("0"))

        after = _context_snapshot(context)

    assert total.to_canonical_string() == "123456790"
    assert difference.to_canonical_string() == "123456788.99"
    assert minimum.to_canonical_string() == "-0.25"
    assert after == before


def test_boundary_numeric_paths_do_not_mutate_hostile_decimal_context() -> None:
    hostile = _hostile_context()

    with localcontext(hostile) as context:
        before = _context_snapshot(context)
        x = sd("9" * N)
        y = sd("1e-4095")
        negative_x = sd("-" + ("9" * N))
        result = exact_sum((x, y, negative_x))
        comparison = exact_compare(y, x)
        canonical = result.to_canonical_string()
        after = _context_snapshot(context)

    assert result == y
    assert comparison == -1
    assert canonical == y.to_canonical_string()
    assert after == before


def test_expected_numeric_failure_does_not_mutate_hostile_context() -> None:
    error_type = _envelope_error()
    hostile = _hostile_context()
    x = sd("9" * N)
    y = sd("1e-4095")

    with localcontext(hostile) as context:
        before = _context_snapshot(context)
        with pytest.raises(error_type):
            exact_sum((x, y))
        after = _context_snapshot(context)

    assert after == before


def _fraction_from_scoring_decimal(value: ScoringDecimal) -> Fraction:
    sign, digits, exponent = value.as_decimal().as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = (coefficient * 10) + digit
    if sign:
        coefficient = -coefficient
    if exponent >= 0:
        return Fraction(coefficient * (10**exponent), 1)
    return Fraction(coefficient, 10 ** (-exponent))


@pytest.mark.parametrize(
    "values",
    [
        ("0.1", "0.2", "0.7"),
        ("1000", "-999.999", "0.001"),
        ("-0.25", "0.125", "0.125"),
        ("1e-20", "1e20", "-1e20"),
        ("123456789.01", "-0.01", "-123456789"),
    ],
)
def test_exact_sum_matches_independent_fraction_oracle(values: tuple[str, ...]) -> None:
    scoring_values = tuple(sd(value) for value in values)
    expected = sum((_fraction_from_scoring_decimal(value) for value in scoring_values), Fraction(0))
    result = exact_sum(scoring_values)

    assert _fraction_from_scoring_decimal(result) == expected


def test_module_level_decimal_context_is_not_changed() -> None:
    context = getcontext()
    before = _context_snapshot(context)

    exact_sum((sd("1"), sd("2")))
    exact_subtract(sd("2"), sd("1"))
    exact_minimum(sd("1"), sd("2"))

    assert _context_snapshot(context) == before



def test_exact_compare_rejects_raw_decimal_operand() -> None:
    with pytest.raises(InvalidScoringValueError):
        exact_compare(sd("1"), Decimal("2"))  # type: ignore[arg-type]


def test_exact_integer_multiplication_is_exact() -> None:
    result = exact_multiply_integer(sd("123456789.125"), -2)

    assert result.to_canonical_string() == "-246913578.25"


def test_exact_integer_multiplication_rejects_non_exact_int() -> None:
    class IntSubclass(int):
        pass

    for multiplier in (True, 2.0, IntSubclass(2)):
        with pytest.raises(InvalidScoringValueError):
            exact_multiply_integer(sd("1"), multiplier)  # type: ignore[arg-type]


def test_zero_multiplication_short_circuits_huge_integer_multiplier() -> None:
    huge_multiplier = 10 ** ((2 * N) + 100)

    result = exact_multiply_integer(sd("0"), huge_multiplier)

    assert result.to_canonical_string() == "0"


def test_nonzero_multiplication_rejects_multiplier_outside_operation_bound() -> None:
    error_type = _envelope_error()
    huge_multiplier = 10 ** ((2 * N) - 1)

    with pytest.raises(error_type):
        exact_multiply_integer(sd("1"), huge_multiplier)


def test_coefficient_product_boundary_is_proven_before_final_envelope_failure() -> None:
    error_type = _envelope_error()
    value = sd(("9" * N) + "e-4095")
    multiplier = (10 ** ((2 * N) - 1)) - 1

    with pytest.raises(error_type):
        exact_multiply_integer(value, multiplier)

    # The reviewed operation-specific product theorem remains 3N-1 digits.
    assert MAX_COEFFICIENT_PRODUCT_DIGITS == (3 * N) - 1
