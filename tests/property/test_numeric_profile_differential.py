from __future__ import annotations

from fractions import Fraction
from itertools import permutations
import random

from grading.contracts.policy import RoundingMode, RoundingRule
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import exact_compare, exact_sum
from grading.scoring.rounding import _round_to_increment


def _raw_from_components(sign: int, coefficient: int, exponent: int) -> str:
    prefix = "-" if sign else ""
    return f"{prefix}{coefficient}e{exponent}"


def _fraction_from_components(sign: int, coefficient: int, exponent: int) -> Fraction:
    signed = -coefficient if sign else coefficient
    if exponent >= 0:
        return Fraction(signed * (10**exponent), 1)
    return Fraction(signed, 10 ** (-exponent))


def _fraction_from_result(value: ScoringDecimal) -> Fraction:
    numerator, denominator = value.as_decimal().as_integer_ratio()
    return Fraction(numerator, denominator)


def test_deterministic_generated_values_match_independent_fraction_oracle() -> None:
    rng = random.Random(0xB1A2)

    for _ in range(500):
        sign = rng.randrange(2)
        coefficient = rng.randrange(1, 10**12)
        exponent = rng.randrange(-12, 13)
        raw = _raw_from_components(sign, coefficient, exponent)
        expected = _fraction_from_components(sign, coefficient, exponent)
        actual = ScoringDecimal.from_raw(raw)

        assert _fraction_from_result(actual) == expected
        reparsed = ScoringDecimal.from_raw(actual.to_canonical_string())
        assert reparsed == actual


def test_deterministic_generated_sums_match_independent_fraction_oracle() -> None:
    rng = random.Random(0x5A17)

    for _ in range(250):
        count = rng.randrange(0, 7)
        components: list[tuple[int, int, int]] = []
        values: list[ScoringDecimal] = []
        expected = Fraction(0)

        for _ in range(count):
            sign = rng.randrange(2)
            coefficient = rng.randrange(1, 10**8)
            exponent = rng.randrange(-8, 9)
            components.append((sign, coefficient, exponent))
            values.append(
                ScoringDecimal.from_raw(
                    _raw_from_components(sign, coefficient, exponent)
                )
            )
            expected += _fraction_from_components(sign, coefficient, exponent)

        result = exact_sum(tuple(values))
        assert _fraction_from_result(result) == expected

        if 1 < count <= 5:
            for ordering in permutations(values):
                assert exact_sum(tuple(ordering)) == result


def test_equivalent_generated_encodings_normalize_identically() -> None:
    rng = random.Random(0xCA110)

    for _ in range(300):
        sign = rng.randrange(2)
        coefficient = rng.randrange(1, 10**9)
        exponent = rng.randrange(-9, 10)
        trailing_zeros = rng.randrange(0, 6)

        raw_a = _raw_from_components(sign, coefficient, exponent)
        raw_b = _raw_from_components(
            sign,
            coefficient * (10**trailing_zeros),
            exponent - trailing_zeros,
        )

        a = ScoringDecimal.from_raw(raw_a)
        b = ScoringDecimal.from_raw(raw_b)

        assert a.as_decimal().as_tuple() == b.as_decimal().as_tuple()
        assert a.to_canonical_string() == b.to_canonical_string()



def test_deterministic_generated_comparisons_match_fraction_oracle() -> None:
    rng = random.Random(0xC0A0)

    for _ in range(500):
        left_components = (
            rng.randrange(2),
            rng.randrange(1, 10**10),
            rng.randrange(-10, 11),
        )
        right_components = (
            rng.randrange(2),
            rng.randrange(1, 10**10),
            rng.randrange(-10, 11),
        )
        left = ScoringDecimal.from_raw(_raw_from_components(*left_components))
        right = ScoringDecimal.from_raw(_raw_from_components(*right_components))
        left_fraction = _fraction_from_components(*left_components)
        right_fraction = _fraction_from_components(*right_components)
        expected = -1 if left_fraction < right_fraction else 1 if left_fraction > right_fraction else 0

        assert exact_compare(left, right) == expected


def _round_fraction(value: Fraction, increment: Fraction, mode: RoundingMode) -> Fraction:
    ratio = value / increment
    sign = -1 if ratio < 0 else 1
    absolute = abs(ratio)
    quotient, remainder = divmod(absolute.numerator, absolute.denominator)
    complement = absolute.denominator - remainder

    if remainder < complement:
        multiple = quotient
    elif remainder > complement:
        multiple = quotient + 1
    elif mode is RoundingMode.HALF_UP:
        multiple = quotient + 1
    else:
        multiple = quotient if quotient % 2 == 0 else quotient + 1

    signed_multiple = 0 if multiple == 0 else sign * multiple
    return increment * signed_multiple


def test_deterministic_generated_rounding_matches_fraction_oracle() -> None:
    rng = random.Random(0xA11CE)
    increments = ("1", "0.5", "0.25", "0.1", "0.75")

    for _ in range(500):
        components = (
            rng.randrange(2),
            rng.randrange(1, 10**8),
            rng.randrange(-6, 7),
        )
        raw_value = _raw_from_components(*components)
        value = ScoringDecimal.from_raw(raw_value)
        value_fraction = _fraction_from_components(*components)
        increment_raw = rng.choice(increments)
        increment = ScoringDecimal.from_raw(increment_raw)
        inc_num, inc_den = increment.as_decimal().as_integer_ratio()
        increment_fraction = Fraction(inc_num, inc_den)
        mode = rng.choice((RoundingMode.HALF_UP, RoundingMode.HALF_EVEN))
        rule = RoundingRule("ROUND-ORACLE", increment, mode)

        result = _round_to_increment(value, rule)
        expected = _round_fraction(value_fraction, increment_fraction, mode)

        assert _fraction_from_result(result) == expected
