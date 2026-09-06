from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from grading.contracts.errors import InvalidScoringValueError
from grading.contracts.scoring_decimal import ScoringDecimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", "0"),
        ("0.500", "0.5"),
        ("-0.000", "0"),
        ("1E+3", "1000"),
        (".25", "0.25"),
        ("1.", "1"),
        ("0.0100", "0.01"),
        ("-1E-7", "-0.0000001"),
        (7, "7"),
        (Decimal("2.7500"), "2.75"),
    ],
)
def test_valid_values_have_canonical_serialization(
    raw: object,
    expected: str,
) -> None:
    value = ScoringDecimal.from_raw(raw)

    assert value.to_canonical_string() == expected


@pytest.mark.parametrize(
    "raw",
    [
        0.5,
        True,
        False,
        "",
        " 1",
        "1 ",
        "1_000",
        "NaN",
        "Infinity",
        "-Infinity",
        "abc",
        object(),
    ],
)
def test_invalid_input_forms_are_rejected(
    raw: object,
) -> None:
    with pytest.raises(InvalidScoringValueError):
        ScoringDecimal.from_raw(raw)


@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_direct_construction_rejects_non_finite_decimals(
    value: Decimal,
) -> None:
    with pytest.raises(InvalidScoringValueError):
        ScoringDecimal(value)


def test_direct_construction_rejects_non_decimal_values() -> None:
    with pytest.raises(InvalidScoringValueError):
        ScoringDecimal("1")  # type: ignore[arg-type]


def test_scoring_decimal_is_immutable() -> None:
    value = ScoringDecimal.from_raw("1.25")

    with pytest.raises(FrozenInstanceError):
        value._value = Decimal("2")  # type: ignore[misc]