from __future__ import annotations

from decimal import (
    Clamped,
    Context,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_FLOOR,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)

import pytest

from grading.contracts.errors import ScoringNumericEnvelopeError
from grading.contracts.numeric_profile import MAX_SCORING_CANONICAL_DIGITS
from grading.contracts.policy import RoundingMode, RoundingRule
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.rounding import _round_to_increment


N = MAX_SCORING_CANONICAL_DIGITS


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def rule(increment: object, mode: RoundingMode) -> RoundingRule:
    return RoundingRule("ROUND-1", sd(increment), mode)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", "0"),
        ("0.124", "0"),
        ("0.125", "0.25"),
        ("0.126", "0.25"),
        ("0.374", "0.25"),
        ("0.375", "0.5"),
        ("-0.124", "0"),
        ("-0.125", "-0.25"),
        ("-0.126", "-0.25"),
        ("-0.375", "-0.5"),
    ],
)
def test_half_up_rounds_to_quarter_multiples(raw: str, expected: str) -> None:
    result = _round_to_increment(sd(raw), rule("0.25", RoundingMode.HALF_UP))

    assert result.to_canonical_string() == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.125", "0"),
        ("0.375", "0.5"),
        ("0.625", "0.5"),
        ("0.875", "1"),
        ("-0.125", "0"),
        ("-0.375", "-0.5"),
        ("-0.625", "-0.5"),
        ("-0.875", "-1"),
    ],
)
def test_half_even_uses_even_multiple_on_ties(raw: str, expected: str) -> None:
    result = _round_to_increment(sd(raw), rule("0.25", RoundingMode.HALF_EVEN))

    assert result.to_canonical_string() == expected


def test_rounding_canonicalizes_negative_zero() -> None:
    result = _round_to_increment(sd("-0.00"), rule("0.25", RoundingMode.HALF_UP))

    assert result.to_canonical_string() == "0"
    assert result.as_decimal().as_tuple() == sd(0).as_decimal().as_tuple()


def test_rounding_can_use_greater_than_4300_digit_internal_multiple() -> None:
    value = sd("9" * N)
    increment = sd("1e-4095")

    result = _round_to_increment(
        value,
        RoundingRule("ROUND-1", increment, RoundingMode.HALF_UP),
    )

    assert result == value


def test_rounding_rejects_positive_result_outside_numeric_envelope() -> None:
    value = sd("9" * N)

    with pytest.raises(ScoringNumericEnvelopeError):
        _round_to_increment(value, rule(2, RoundingMode.HALF_UP))


def test_rounding_rejects_negative_result_outside_numeric_envelope() -> None:
    value = sd("-" + ("9" * N))

    with pytest.raises(ScoringNumericEnvelopeError):
        _round_to_increment(value, rule(2, RoundingMode.HALF_UP))


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


def _snapshot(context: Context) -> tuple[object, ...]:
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


def test_rounding_does_not_consult_or_mutate_hostile_decimal_context() -> None:
    hostile = _hostile_context()

    with localcontext(hostile) as context:
        before = _snapshot(context)
        result = _round_to_increment(
            sd("123456789.125"),
            rule("0.25", RoundingMode.HALF_EVEN),
        )
        after = _snapshot(context)

    assert result.to_canonical_string() == "123456789"
    assert after == before
