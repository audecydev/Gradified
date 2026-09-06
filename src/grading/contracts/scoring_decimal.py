from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from grading.contracts.errors import InvalidScoringValueError


_DECIMAL_TEXT_RE = re.compile(
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z"
)


@dataclass(frozen=True, slots=True)
class ScoringDecimal:
    """Immutable finite decimal value permitted inside scoring authority."""

    _value: Decimal

    def __post_init__(self) -> None:
        if type(self._value) is not Decimal:
            raise InvalidScoringValueError(
                "ScoringDecimal must wrap a Decimal."
            )

        if not self._value.is_finite():
            raise InvalidScoringValueError(
                "Scoring decimals must be finite."
            )

    @classmethod
    def from_raw(cls, raw: object) -> ScoringDecimal:
        """Create a validated scoring decimal from an approved input form."""

        if isinstance(raw, bool) or isinstance(raw, float):
            raise InvalidScoringValueError(
                "Boolean and float values are not valid scoring decimals."
            )

        if type(raw) is Decimal:
            value = raw

        elif type(raw) is int:
            value = Decimal(raw)

        elif type(raw) is str:
            if _DECIMAL_TEXT_RE.fullmatch(raw) is None:
                raise InvalidScoringValueError(
                    "Scoring text must be an explicit decimal representation."
                )

            try:
                value = Decimal(raw)
            except (InvalidOperation, ValueError) as exc:
                raise InvalidScoringValueError(
                    "Invalid decimal scoring value."
                ) from exc

        else:
            raise InvalidScoringValueError(
                f"Unsupported scoring value type: {type(raw).__name__}."
            )

        return cls(value)

    def as_decimal(self) -> Decimal:
        """Return the immutable Decimal representation."""

        return self._value

    def to_canonical_string(self) -> str:
        """Serialize without exponent notation or insignificant zeros."""

        if self._value.is_zero():
            return "0"

        sign, digits, exponent = self._value.as_tuple()
        digit_text = "".join(str(digit) for digit in digits)

        if exponent >= 0:
            text = digit_text + ("0" * exponent)

        else:
            point = len(digit_text) + exponent

            if point > 0:
                text = f"{digit_text[:point]}.{digit_text[point:]}"
            else:
                text = "0." + ("0" * (-point)) + digit_text

            text = text.rstrip("0").rstrip(".")

        return f"-{text}" if sign else text

    def __str__(self) -> str:
        return self.to_canonical_string()