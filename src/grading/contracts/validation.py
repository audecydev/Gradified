from __future__ import annotations

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import (
    DuplicateJudgmentError,
    InvalidCriterionJudgmentError,
    InvalidScoringAuthorityError,
    MissingJudgmentError,
    UnknownJudgmentCriterionError,
    UnknownJudgmentPerformanceLevelError,
)
from grading.contracts.judgment import CriterionJudgment


def validate_criterion_judgments(
    authority: QuestionScoringAuthority,
    judgments: tuple[CriterionJudgment, ...],
) -> tuple[CriterionJudgment, ...]:
    """Validate one judgment per atomic criterion and return rubric-order form."""

    if type(authority) is not QuestionScoringAuthority:
        raise InvalidScoringAuthorityError(
            "authority must be a QuestionScoringAuthority."
        )
    if type(judgments) is not tuple:
        raise InvalidCriterionJudgmentError(
            "judgments must be an immutable tuple."
        )
    if any(type(judgment) is not CriterionJudgment for judgment in judgments):
        raise InvalidCriterionJudgmentError(
            "judgments contains an invalid item."
        )

    criteria_by_id = authority.rubric.criteria_by_id()
    judgments_by_id: dict[str, CriterionJudgment] = {}

    for judgment in judgments:
        criterion = criteria_by_id.get(judgment.criterion_id)
        if criterion is None:
            raise UnknownJudgmentCriterionError(
                f"Judgment references unknown criterion {judgment.criterion_id!r}."
            )
        if judgment.criterion_id in judgments_by_id:
            raise DuplicateJudgmentError(
                f"Duplicate judgment for criterion {judgment.criterion_id!r}."
            )
        if judgment.selected_level not in criterion.level_ids():
            raise UnknownJudgmentPerformanceLevelError(
                f"Unknown level {judgment.selected_level!r} for criterion "
                f"{judgment.criterion_id!r}."
            )
        judgments_by_id[judgment.criterion_id] = judgment

    missing = [
        criterion.criterion_id
        for criterion in authority.rubric.criteria
        if criterion.criterion_id not in judgments_by_id
    ]
    if missing:
        raise MissingJudgmentError(
            "Missing judgments for criteria: " + ", ".join(missing)
        )

    return tuple(
        judgments_by_id[criterion.criterion_id]
        for criterion in authority.rubric.criteria
    )
