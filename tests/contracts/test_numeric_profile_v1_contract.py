from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

import grading.contracts.errors as scoring_errors
from grading.contracts.errors import InvalidScoringValueError
from grading.contracts.numeric_profile import (
    MAX_SCORING_CANONICAL_DIGITS,
    RAW_TEXT_MAX_CHARS,
)
from grading.contracts.scoring_decimal import ScoringDecimal


N = MAX_SCORING_CANONICAL_DIGITS
RAW_MAX = RAW_TEXT_MAX_CHARS


def _envelope_error() -> type[Exception]:
    error_type = getattr(scoring_errors, "ScoringNumericEnvelopeError", None)
    assert isinstance(error_type, type), (
        "Numeric Profile v1 requires ScoringNumericEnvelopeError."
    )
    return error_type


@pytest.mark.parametrize(
    "raw",
    [
        "١٢٣",       # Arabic-Indic digits
        "१२३",       # Devanagari digits
        "１２３",     # full-width digits
        "1_000",
        " 1",
        "1 ",
        ".",
        "+.",
        "e3",
        "1e",
        "1e+",
        "1..2",
        "1.2.3",
        "NaN",
        "Infinity",
    ],
)
def test_raw_grammar_rejects_non_profile_text(raw: str) -> None:
    with pytest.raises(InvalidScoringValueError):
        ScoringDecimal.from_raw(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", "1"),
        ("1.", "1"),
        ("1.2", "1.2"),
        (".2", "0.2"),
        ("1e3", "1000"),
        ("1.e3", "1000"),
        ("1.2e3", "1200"),
        (".2e3", "200"),
        ("+0001.00", "1"),
    ],
)
def test_raw_grammar_accepts_profile_language(raw: str, expected: str) -> None:
    assert ScoringDecimal.from_raw(raw).to_canonical_string() == expected


def test_raw_length_limit_precedes_malformed_tail() -> None:
    error_type = _envelope_error()
    oversized_and_malformed = ("0" * RAW_MAX) + "!"

    with pytest.raises(error_type):
        ScoringDecimal.from_raw(oversized_and_malformed)


def test_bounded_malformed_text_precedes_lexical_resource_classification() -> None:
    malformed_with_too_many_significand_digits = ("9" * (N + 1)) + "!"
    malformed_with_too_many_exponent_digits = "1e00001!"

    assert len(malformed_with_too_many_significand_digits) <= RAW_MAX
    for raw in (
        malformed_with_too_many_significand_digits,
        malformed_with_too_many_exponent_digits,
    ):
        with pytest.raises(InvalidScoringValueError):
            ScoringDecimal.from_raw(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "0" * (N + 1),
        "1e00001",
        "1e8192",
        "1e-8191",
    ],
)
def test_well_formed_raw_resource_excess_raises_envelope_error(raw: str) -> None:
    error_type = _envelope_error()

    with pytest.raises(error_type):
        ScoringDecimal.from_raw(raw)


def test_canonical_positive_exponent_bound() -> None:
    error_type = _envelope_error()

    assert ScoringDecimal.from_raw("1e4095").to_canonical_string().startswith("1")
    with pytest.raises(error_type):
        ScoringDecimal.from_raw("1e4096")


def test_canonical_negative_exponent_bound() -> None:
    error_type = _envelope_error()

    assert ScoringDecimal.from_raw("1e-4095").to_canonical_string().endswith("1")
    with pytest.raises(error_type):
        ScoringDecimal.from_raw("1e-4096")


def test_direct_decimal_construction_cannot_bypass_envelope() -> None:
    error_type = _envelope_error()

    with pytest.raises(error_type):
        ScoringDecimal(Decimal("1E+4096"))


def test_direct_decimal_source_coefficient_is_bounded_before_normalization() -> None:
    error_type = _envelope_error()
    redundant = Decimal((0, (1,) + (0,) * N, -N))

    with pytest.raises(error_type):
        ScoringDecimal(redundant)


def test_direct_decimal_zero_has_one_internal_representation() -> None:
    value = ScoringDecimal(Decimal("-0E+999999"))

    assert value.as_decimal().as_tuple() == Decimal(0).as_tuple()
    assert value.to_canonical_string() == "0"


def test_direct_decimal_zero_and_raw_zero_have_intentional_resource_asymmetry() -> None:
    error_type = _envelope_error()
    direct = ScoringDecimal(Decimal("0E+999999"))

    assert direct.as_decimal().as_tuple() == Decimal(0).as_tuple()
    with pytest.raises(error_type):
        ScoringDecimal.from_raw("0E+999999")


@pytest.mark.parametrize(
    "raw",
    ["1", "1.0", "1.00", "10E-1", "100E-2", "0001", "+1"],
)
def test_equivalent_values_have_identical_internal_representation(raw: str) -> None:
    value = ScoringDecimal.from_raw(raw)

    assert value.as_decimal().as_tuple() == Decimal(1).as_tuple()
    assert value.to_canonical_string() == "1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("000.00100", "0.001"),
        ("000100.000", "100"),
        ("000100E-3", "0.1"),
        ("+000100.000E-3", "0.1"),
        ("-000.000", "0"),
        ("1000E-3", "1"),
        ("100.00E-2", "1"),
    ],
)
def test_manual_normalization_handles_zero_and_trailing_zeros(
    raw: str,
    expected: str,
) -> None:
    value = ScoringDecimal.from_raw(raw)
    reparsed = ScoringDecimal(value.as_decimal())

    assert value.to_canonical_string() == expected
    assert reparsed.as_decimal().as_tuple() == value.as_decimal().as_tuple()


@pytest.mark.parametrize(
    "raw",
    [0.1, True, False],
)
def test_float_and_bool_are_rejected(raw: object) -> None:
    with pytest.raises(InvalidScoringValueError):
        ScoringDecimal.from_raw(raw)


def test_numeric_subclasses_are_rejected() -> None:
    class IntSubclass(int):
        pass

    class StrSubclass(str):
        pass

    class DecimalSubclass(Decimal):
        pass

    for raw in (IntSubclass(1), StrSubclass("1"), DecimalSubclass("1")):
        with pytest.raises(InvalidScoringValueError):
            ScoringDecimal.from_raw(raw)


def test_integer_envelope_is_exact_and_does_not_accept_boundary() -> None:
    error_type = _envelope_error()
    limit = 10**N

    assert ScoringDecimal.from_raw(limit - 1).as_decimal() == Decimal(limit - 1)
    assert ScoringDecimal.from_raw(-(limit - 1)).as_decimal() == Decimal(-(limit - 1))

    with pytest.raises(error_type):
        ScoringDecimal.from_raw(limit)
    with pytest.raises(error_type):
        ScoringDecimal.from_raw(-limit)


def test_canonical_round_trip_is_idempotent() -> None:
    cases = (
        "0",
        "-0.000",
        "0.1250",
        "-0.1250",
        "1e4095",
        "1e-4095",
        "1000E-3",
    )

    for raw in cases:
        value = ScoringDecimal.from_raw(raw)
        canonical = value.to_canonical_string()
        reparsed = ScoringDecimal.from_raw(canonical)

        assert reparsed == value
        assert reparsed.to_canonical_string() == canonical


def test_scoring_decimal_remains_immutable_after_normalization() -> None:
    value = ScoringDecimal.from_raw("1.5000")

    with pytest.raises(FrozenInstanceError):
        value._value = Decimal("2")  # type: ignore[misc]


def test_raw_maximum_4104_character_boundary_is_accepted_when_semantically_valid() -> None:
    raw = "+." + ("0" * (N - 1)) + "1e+8191"

    assert len(raw) == RAW_MAX
    value = ScoringDecimal.from_raw(raw)
    assert value.as_decimal().as_tuple() == Decimal("1e4095").as_tuple()


def test_raw_negative_exponent_boundary_can_produce_minimum_nonzero_value() -> None:
    raw = ("1" + ("0" * (N - 1))) + "e-8190"

    value = ScoringDecimal.from_raw(raw)
    assert value.as_decimal().as_tuple() == Decimal("1e-4095").as_tuple()


def test_envelope_errors_never_echo_explosive_numeric_payload() -> None:
    error_type = _envelope_error()
    raw = "9" * (N + 1)

    with pytest.raises(error_type) as exc_info:
        ScoringDecimal.from_raw(raw)

    message = str(exc_info.value)
    assert len(message) < 256
    assert raw[:100] not in message


def test_canonical_serialization_length_bound_for_boundary_values() -> None:
    positive_integer = ScoringDecimal.from_raw("9" * N).to_canonical_string()
    negative_integer = ScoringDecimal.from_raw("-" + ("9" * N)).to_canonical_string()
    positive_fraction = ScoringDecimal.from_raw("1e-4095").to_canonical_string()
    negative_fraction = ScoringDecimal.from_raw("-1e-4095").to_canonical_string()

    assert len(positive_integer) == N
    assert len(negative_integer) == N + 1
    assert len(positive_fraction) == N + 1
    assert len(negative_fraction) == N + 2
