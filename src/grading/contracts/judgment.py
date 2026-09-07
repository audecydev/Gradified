from __future__ import annotations

from dataclasses import dataclass

from grading.contracts.errors import InvalidCriterionJudgmentError


def _validate_judgment_identifier(value: object, field_name: str) -> None:
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidCriterionJudgmentError(
            f"{field_name} must be a non-empty string without surrounding whitespace."
        )


@dataclass(frozen=True, slots=True)
class CriterionJudgment:
    """Evaluator-selected semantic state with no numerical scoring authority.

    External structured-output adapters must reject unexpected fields before
    constructing this object; this domain type itself intentionally contains no
    score-like field.
    """

    criterion_id: str
    selected_level: str

    def __post_init__(self) -> None:
        _validate_judgment_identifier(self.criterion_id, "criterion_id")
        _validate_judgment_identifier(self.selected_level, "selected_level")
