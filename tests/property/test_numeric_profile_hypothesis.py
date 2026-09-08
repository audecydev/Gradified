from __future__ import annotations

from fractions import Fraction

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st

from grading.contracts.numeric_profile import MAX_SCORING_CANONICAL_DIGITS
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import exact_sum


@st.composite
def decimal_components(draw):
    sign = draw(st.integers(min_value=0, max_value=1))
    coefficient = draw(st.integers(min_value=1, max_value=10**20))
    exponent = draw(st.integers(min_value=-20, max_value=20))
    return sign, coefficient, exponent


def _raw(components: tuple[int, int, int]) -> str:
    sign, coefficient, exponent = components
    prefix = "-" if sign else ""
    return f"{prefix}{coefficient}e{exponent}"


def _fraction(components: tuple[int, int, int]) -> Fraction:
    sign, coefficient, exponent = components
    signed = -coefficient if sign else coefficient
    if exponent >= 0:
        return Fraction(signed * (10**exponent), 1)
    return Fraction(signed, 10 ** (-exponent))


def _result_fraction(value: ScoringDecimal) -> Fraction:
    numerator, denominator = value.as_decimal().as_integer_ratio()
    return Fraction(numerator, denominator)


@given(decimal_components())
@settings(max_examples=150, deadline=None)
def test_hypothesis_parse_and_serialize_match_fraction(components) -> None:
    value = ScoringDecimal.from_raw(_raw(components))

    assert _result_fraction(value) == _fraction(components)
    assert ScoringDecimal.from_raw(value.to_canonical_string()) == value


@given(st.lists(decimal_components(), min_size=0, max_size=8))
@settings(max_examples=150, deadline=None)
def test_hypothesis_exact_sum_matches_fraction(components_list) -> None:
    values = tuple(ScoringDecimal.from_raw(_raw(item)) for item in components_list)
    expected = sum((_fraction(item) for item in components_list), Fraction(0))
    result = exact_sum(values)

    assert _result_fraction(result) == expected


N = MAX_SCORING_CANONICAL_DIGITS


@st.composite
def boundary_profile_raw(draw):
    category = draw(
        st.sampled_from(
            (
                "max_integer",
                "near_max_integer",
                "min_fraction",
                "near_min_fraction",
                "max_positive_exponent",
                "dense_fraction",
            )
        )
    )
    negative = draw(st.booleans())
    prefix = "-" if negative else ""

    if category == "max_integer":
        magnitude = "9" * N
    elif category == "near_max_integer":
        magnitude = "1" + ("0" * (N - 1))
    elif category == "min_fraction":
        magnitude = "1e-4095"
    elif category == "near_min_fraction":
        magnitude = "9e-4095"
    elif category == "max_positive_exponent":
        magnitude = "1e4095"
    else:
        magnitude = ("9" * N) + "e-4095"

    return prefix + magnitude


@given(boundary_profile_raw())
@settings(max_examples=40, deadline=None)
def test_hypothesis_boundary_values_round_trip_canonically(raw: str) -> None:
    value = ScoringDecimal.from_raw(raw)
    canonical = value.to_canonical_string()

    assert ScoringDecimal.from_raw(canonical) == value
    assert ScoringDecimal.from_raw(canonical).to_canonical_string() == canonical


@given(
    x_raw=st.sampled_from(
        (
            "9" * N,
            "1e4095",
            ("9" * N) + "e-4095",
        )
    ),
    y_raw=st.sampled_from(("1e-4095", "0.25", "1")),
    ordering=st.permutations((0, 1, 2)),
)
@settings(max_examples=60, deadline=None)
def test_hypothesis_boundary_cancellation_is_permutation_invariant(
    x_raw: str,
    y_raw: str,
    ordering: list[int],
) -> None:
    x = ScoringDecimal.from_raw(x_raw)
    negative_x = ScoringDecimal.from_raw("-" + x_raw)
    y = ScoringDecimal.from_raw(y_raw)
    values = (x, y, negative_x)

    result = exact_sum(tuple(values[index] for index in ordering))

    assert result == y
