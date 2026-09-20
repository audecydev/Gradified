from __future__ import annotations

from dataclasses import dataclass


def _require_identifier(value: object, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string.")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be non-empty without surrounding whitespace."
        )


def _require_tuple_of_strings(values: object, field_name: str) -> None:
    if type(values) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if any(type(value) is not str for value in values):
        raise TypeError(f"{field_name} must contain only strings.")


@dataclass(frozen=True, slots=True)
class EvaluatorMetadata:
    evaluator_id: str
    version: str

    def __post_init__(self) -> None:
        _require_identifier(self.evaluator_id, "EvaluatorMetadata.evaluator_id")
        _require_identifier(self.version, "EvaluatorMetadata.version")


@dataclass(frozen=True, slots=True)
class EvaluatedCriterionJudgment:
    criterion_id: str
    selected_level: str
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    concise_rationale: str
    uncertainties: tuple[str, ...]
    evaluator_metadata: EvaluatorMetadata

    def __post_init__(self) -> None:
        _require_identifier(self.criterion_id, "EvaluatedCriterionJudgment.criterion_id")
        _require_identifier(
            self.selected_level,
            "EvaluatedCriterionJudgment.selected_level",
        )
        _require_tuple_of_strings(
            self.evidence_refs,
            "EvaluatedCriterionJudgment.evidence_refs",
        )
        _require_tuple_of_strings(
            self.reason_codes,
            "EvaluatedCriterionJudgment.reason_codes",
        )
        if type(self.concise_rationale) is not str:
            raise TypeError("EvaluatedCriterionJudgment.concise_rationale must be a string.")
        _require_tuple_of_strings(
            self.uncertainties,
            "EvaluatedCriterionJudgment.uncertainties",
        )
        if type(self.evaluator_metadata) is not EvaluatorMetadata:
            raise TypeError(
                "EvaluatedCriterionJudgment.evaluator_metadata must be an exact EvaluatorMetadata."
            )
