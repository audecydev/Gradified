from __future__ import annotations

from dataclasses import dataclass

from grading.contracts.errors import InvalidScoringAuthorityError
from grading.contracts.scoring_decimal import ScoringDecimal


def _validate_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidScoringAuthorityError(
            f"{field_name} must be a non-empty string without surrounding whitespace."
        )
    return value


def _validate_operational_description(value: object) -> str:
    # Human-authored prose is not an identifier. The scoring contract only
    # requires meaningful text; any canonical whitespace normalization belongs
    # to the upstream rubric compiler, not to the numerical scoring kernel.
    if type(value) is not str or not value.strip():
        raise InvalidScoringAuthorityError(
            "operational_description must contain non-whitespace text."
        )
    return value


def _validate_version(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise InvalidScoringAuthorityError(
            f"{field_name} must be a positive integer."
        )
    return value


@dataclass(frozen=True, slots=True)
class PerformanceLevel:
    """One approved semantic level and its rubric-authorized contribution."""

    level_id: str
    contribution: ScoringDecimal

    def __post_init__(self) -> None:
        _validate_identifier(self.level_id, "level_id")
        if type(self.contribution) is not ScoringDecimal:
            raise InvalidScoringAuthorityError(
                "PerformanceLevel.contribution must be a ScoringDecimal."
            )


@dataclass(frozen=True, slots=True)
class AtomicCriterion:
    """Independently assessable scoring unit in Scoring Semantics v1."""

    criterion_id: str
    operational_description: str
    performance_levels: tuple[PerformanceLevel, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.criterion_id, "criterion_id")
        _validate_operational_description(self.operational_description)
        if type(self.performance_levels) is not tuple or not self.performance_levels:
            raise InvalidScoringAuthorityError(
                "AtomicCriterion.performance_levels must be a non-empty tuple."
            )
        if any(type(level) is not PerformanceLevel for level in self.performance_levels):
            raise InvalidScoringAuthorityError(
                "AtomicCriterion.performance_levels contains an invalid item."
            )

        level_ids = tuple(level.level_id for level in self.performance_levels)
        if len(level_ids) != len(set(level_ids)):
            raise InvalidScoringAuthorityError(
                f"Criterion {self.criterion_id!r} contains duplicate performance level IDs."
            )

    def level_ids(self) -> frozenset[str]:
        return frozenset(level.level_id for level in self.performance_levels)


@dataclass(frozen=True, slots=True)
class CompiledQuestionRubric:
    """Immutable reducer-facing scoring projection of a compiled rubric.

    Scoring Semantics v1 intentionally carries only data required for numerical
    reduction. Richer authoring/evaluation metadata remains a rubric authoring compiler
    concern. This contract validates scoring shape and local identity
    constraints; full marks reconciliation and authoring-time semantic linting
    must pass before a rubric can become ACTIVE.
    """

    rubric_id: str
    version: int
    question_id: str
    max_marks: ScoringDecimal
    criteria: tuple[AtomicCriterion, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.rubric_id, "rubric_id")
        _validate_version(self.version, "rubric version")
        _validate_identifier(self.question_id, "question_id")
        if type(self.max_marks) is not ScoringDecimal:
            raise InvalidScoringAuthorityError(
                "CompiledQuestionRubric.max_marks must be a ScoringDecimal."
            )
        if type(self.criteria) is not tuple or not self.criteria:
            raise InvalidScoringAuthorityError(
                "CompiledQuestionRubric.criteria must be a non-empty tuple."
            )
        if any(type(criterion) is not AtomicCriterion for criterion in self.criteria):
            raise InvalidScoringAuthorityError(
                "CompiledQuestionRubric.criteria contains an invalid item."
            )

        criterion_ids = tuple(criterion.criterion_id for criterion in self.criteria)
        if len(criterion_ids) != len(set(criterion_ids)):
            raise InvalidScoringAuthorityError(
                "CompiledQuestionRubric contains duplicate criterion IDs."
            )

    def criteria_by_id(self) -> dict[str, AtomicCriterion]:
        return {criterion.criterion_id: criterion for criterion in self.criteria}
