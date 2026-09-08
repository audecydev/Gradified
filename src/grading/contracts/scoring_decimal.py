from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from grading.contracts.errors import (
    InvalidScoringValueError,
    ScoringNumericEnvelopeError,
)
from grading.contracts.numeric_profile import (
    INTEGER_MAGNITUDE_EXCLUSIVE,
    MAX_SCORING_CANONICAL_DIGITS,
    RAW_EXPONENT_MAX,
    RAW_EXPONENT_MAX_DIGITS,
    RAW_EXPONENT_MIN,
    RAW_TEXT_MAX_CHARS,
    canonical_digit_count,
)


@dataclass(frozen=True, slots=True)
class _RawDecimalScan:
    significand_digits: int
    exponent_digits: int
    exponent_value: int


def _is_ascii_digit(character: str) -> bool:
    return "0" <= character <= "9"


def _scan_raw_decimal(raw: str) -> _RawDecimalScan:
    """Validate Profile-v1 ASCII NUMBER grammar in deterministic O(n) time.

    The caller has already enforced the top-level raw-length boundary. The
    scanner deliberately completes grammar classification before reporting
    representation-resource excess so malformed bounded text remains an
    InvalidScoringValueError rather than an envelope error.
    """

    length = len(raw)
    index = 0

    if index < length and raw[index] in "+-":
        index += 1

    significand_digits = 0

    while index < length and _is_ascii_digit(raw[index]):
        significand_digits += 1
        index += 1

    if index < length and raw[index] == ".":
        index += 1
        while index < length and _is_ascii_digit(raw[index]):
            significand_digits += 1
            index += 1

    if significand_digits == 0:
        raise InvalidScoringValueError(
            "Scoring text does not match the Numeric Profile v1 decimal grammar."
        )

    exponent_digits = 0
    exponent_sign = 1
    exponent_value = 0

    if index < length and raw[index] in "eE":
        index += 1
        if index < length and raw[index] in "+-":
            if raw[index] == "-":
                exponent_sign = -1
            index += 1

        exponent_start = index
        while index < length and _is_ascii_digit(raw[index]):
            exponent_digits += 1
            if exponent_digits <= RAW_EXPONENT_MAX_DIGITS:
                exponent_value = (exponent_value * 10) + (ord(raw[index]) - 48)
            index += 1

        if index == exponent_start:
            raise InvalidScoringValueError(
                "Scoring text does not match the Numeric Profile v1 decimal grammar."
            )

    if index != length:
        raise InvalidScoringValueError(
            "Scoring text does not match the Numeric Profile v1 decimal grammar."
        )

    if significand_digits > MAX_SCORING_CANONICAL_DIGITS:
        raise ScoringNumericEnvelopeError(
            "Scoring text significand exceeds Numeric Profile v1."
        )

    if exponent_digits > RAW_EXPONENT_MAX_DIGITS:
        raise ScoringNumericEnvelopeError(
            "Scoring text exponent width exceeds Numeric Profile v1."
        )

    signed_exponent = exponent_sign * exponent_value if exponent_digits else 0
    if not RAW_EXPONENT_MIN <= signed_exponent <= RAW_EXPONENT_MAX:
        raise ScoringNumericEnvelopeError(
            "Scoring text exponent exceeds Numeric Profile v1."
        )

    return _RawDecimalScan(
        significand_digits=significand_digits,
        exponent_digits=exponent_digits,
        exponent_value=signed_exponent,
    )


def _normalize_finite_decimal(value: Decimal) -> Decimal:
    """Normalize one exact finite Decimal without Decimal arithmetic/context."""

    if value.is_zero():
        return Decimal(0)

    sign, digits, exponent = value.as_tuple()

    # Direct Decimal values are already-created objects, but Profile v1 still
    # bounds the accepted source representation before scanning redundant
    # coefficient zeros. Raw strings have their own pre-parse source limit.
    if len(digits) > MAX_SCORING_CANONICAL_DIGITS:
        raise ScoringNumericEnvelopeError(
            "Decimal coefficient representation exceeds Numeric Profile v1."
        )

    normalized_length = len(digits)
    normalized_exponent = exponent

    while normalized_length > 1 and digits[normalized_length - 1] == 0:
        normalized_length -= 1
        normalized_exponent += 1

    normalized_digits = digits[:normalized_length]
    digit_count = len(normalized_digits)

    if canonical_digit_count(digit_count, normalized_exponent) > MAX_SCORING_CANONICAL_DIGITS:
        raise ScoringNumericEnvelopeError(
            "Decimal value exceeds Numeric Profile v1 canonical envelope."
        )

    return Decimal((sign, normalized_digits, normalized_exponent))


@dataclass(frozen=True, slots=True)
class ScoringDecimal:
    """Immutable exact decimal admitted by Numeric Profile v1.

    The approved rubric/scoring policy remains the source of numerical scoring
    authority. This type only defines the exact numeric representation and
    operational capability boundary used by deterministic scoring code.
    """

    _value: Decimal

    def __post_init__(self) -> None:
        if type(self._value) is not Decimal:
            raise InvalidScoringValueError(
                "ScoringDecimal must wrap an exact Decimal."
            )

        if not self._value.is_finite():
            raise InvalidScoringValueError(
                "Scoring decimals must be finite."
            )

        normalized = _normalize_finite_decimal(self._value)
        object.__setattr__(self, "_value", normalized)

    @classmethod
    def from_raw(cls, raw: object) -> ScoringDecimal:
        """Create a scoring decimal from one explicitly approved input form."""

        if type(raw) is str:
            if len(raw) > RAW_TEXT_MAX_CHARS:
                raise ScoringNumericEnvelopeError(
                    "Scoring text exceeds Numeric Profile v1 raw length."
                )
            _scan_raw_decimal(raw)
            # The bounded scanner is the grammar/resource authority. Decimal
            # construction here is exact representation construction only.
            value = Decimal(raw)
            return cls(value)

        if type(raw) is int:
            if not -INTEGER_MAGNITUDE_EXCLUSIVE < raw < INTEGER_MAGNITUDE_EXCLUSIVE:
                raise ScoringNumericEnvelopeError(
                    "Integer scoring value exceeds Numeric Profile v1."
                )
            return cls(Decimal(raw))

        if type(raw) is Decimal:
            return cls(raw)

        raise InvalidScoringValueError(
            f"Unsupported scoring value type: {type(raw).__name__}."
        )

    def as_decimal(self) -> Decimal:
        """Return the normalized immutable Decimal representation."""

        return self._value

    def to_canonical_string(self) -> str:
        """Serialize uniquely as bounded plain ASCII decimal text."""

        if self._value.is_zero():
            return "0"

        sign, digits, exponent = self._value.as_tuple()
        digit_text = "".join(chr(48 + digit) for digit in digits)

        if exponent >= 0:
            magnitude = digit_text + ("0" * exponent)
        else:
            point = len(digit_text) + exponent
            if point > 0:
                magnitude = f"{digit_text[:point]}.{digit_text[point:]}"
            else:
                magnitude = "0." + ("0" * (-point)) + digit_text

        return f"-{magnitude}" if sign else magnitude

    def __str__(self) -> str:
        return self.to_canonical_string()
