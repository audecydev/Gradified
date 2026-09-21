from __future__ import annotations

from dataclasses import dataclass

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.contracts.evidence import AnswerEvidenceBundle
from grading.contracts.paper_aggregation import GradingSpecRef, ResolvedPaperScoringAuthority
from grading.contracts.result import PaperScoreResult, QuestionScoreResult
from grading.scoring.paper_aggregation import aggregate_paper
from grading.scoring.reducer import reduce_question
from grading.verification.evidence import (
    VerifiedCriterionJudgments,
    verify_evaluated_judgments,
)


class InvalidGradingExecutionError(ValueError):
    """Raised when S2 execution admission or identity binding fails."""


def _require_identifier(value: object, field_name: str) -> None:
    if type(value) is not str:
        raise InvalidGradingExecutionError(f"{field_name} must be a string.")
    if not value or value.strip() != value:
        raise InvalidGradingExecutionError(
            f"{field_name} must be non-empty without surrounding whitespace."
        )


@dataclass(frozen=True, slots=True)
class GradingExecutionContext:
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    grading_spec_ref: GradingSpecRef

    def __post_init__(self) -> None:
        _require_identifier(self.grading_run_id, "GradingExecutionContext.grading_run_id")
        _require_identifier(self.submission_ref, "GradingExecutionContext.submission_ref")
        _require_identifier(self.exam_ref, "GradingExecutionContext.exam_ref")
        if type(self.grading_spec_ref) is not GradingSpecRef:
            raise InvalidGradingExecutionError(
                "GradingExecutionContext.grading_spec_ref must be an exact GradingSpecRef."
            )


@dataclass(frozen=True, slots=True)
class QuestionExecutionInput:
    question_id: str
    judgments: tuple[EvaluatedCriterionJudgment, ...]
    authority: QuestionScoringAuthority

    def __post_init__(self) -> None:
        _require_identifier(self.question_id, "QuestionExecutionInput.question_id")
        if type(self.judgments) is not tuple or any(
            type(judgment) is not EvaluatedCriterionJudgment
            for judgment in self.judgments
        ):
            raise InvalidGradingExecutionError(
                "QuestionExecutionInput.judgments must be a tuple of exact "
                "EvaluatedCriterionJudgment values."
            )
        if type(self.authority) is not QuestionScoringAuthority:
            raise InvalidGradingExecutionError(
                "QuestionExecutionInput.authority must be an exact "
                "QuestionScoringAuthority."
            )


@dataclass(frozen=True, slots=True)
class QuestionExecutionRecord:
    verified: VerifiedCriterionJudgments
    score: QuestionScoreResult

    def __post_init__(self) -> None:
        if type(self.verified) is not VerifiedCriterionJudgments:
            raise InvalidGradingExecutionError(
                "QuestionExecutionRecord.verified must be an exact "
                "VerifiedCriterionJudgments."
            )
        if type(self.score) is not QuestionScoreResult:
            raise InvalidGradingExecutionError(
                "QuestionExecutionRecord.score must be an exact QuestionScoreResult."
            )


@dataclass(frozen=True, slots=True)
class GradingExecutionResult:
    context: GradingExecutionContext
    questions: tuple[QuestionExecutionRecord, ...]
    paper_score: PaperScoreResult

    def __post_init__(self) -> None:
        if type(self.context) is not GradingExecutionContext:
            raise InvalidGradingExecutionError(
                "GradingExecutionResult.context must be an exact GradingExecutionContext."
            )
        if type(self.questions) is not tuple or any(
            type(record) is not QuestionExecutionRecord for record in self.questions
        ):
            raise InvalidGradingExecutionError(
                "GradingExecutionResult.questions must be a tuple of exact "
                "QuestionExecutionRecord values."
            )
        if type(self.paper_score) is not PaperScoreResult:
            raise InvalidGradingExecutionError(
                "GradingExecutionResult.paper_score must be an exact PaperScoreResult."
            )


def _validate_execution_inputs(
    *,
    context: object,
    evidence: object,
    questions: object,
    paper_authority: object,
) -> tuple[QuestionExecutionInput, ...]:
    if type(context) is not GradingExecutionContext:
        raise InvalidGradingExecutionError(
            "context must be an exact GradingExecutionContext."
        )
    if type(evidence) is not AnswerEvidenceBundle:
        raise InvalidGradingExecutionError(
            "evidence must be an exact AnswerEvidenceBundle."
        )
    if type(questions) is not tuple or any(
        type(question) is not QuestionExecutionInput for question in questions
    ):
        raise InvalidGradingExecutionError(
            "questions must be a tuple of exact QuestionExecutionInput values."
        )
    if type(paper_authority) is not ResolvedPaperScoringAuthority:
        raise InvalidGradingExecutionError(
            "paper_authority must be an exact ResolvedPaperScoringAuthority."
        )

    if context.submission_ref != evidence.submission_ref:
        raise InvalidGradingExecutionError(
            "context.submission_ref must match evidence.submission_ref."
        )
    if context.grading_spec_ref != paper_authority.grading_spec_ref:
        raise InvalidGradingExecutionError(
            "context.grading_spec_ref must match paper_authority.grading_spec_ref."
        )

    seen_question_ids: set[str] = set()
    for question in questions:
        if question.question_id in seen_question_ids:
            raise InvalidGradingExecutionError(
                f"questions contains duplicate question_id {question.question_id!r}."
            )
        seen_question_ids.add(question.question_id)

    expected_question_ids = tuple(
        expected.question_id for expected in paper_authority.expected_questions
    )
    expected_question_id_set = set(expected_question_ids)

    missing_question_ids = tuple(
        question_id
        for question_id in expected_question_ids
        if question_id not in seen_question_ids
    )
    unexpected_question_ids = tuple(
        question.question_id
        for question in questions
        if question.question_id not in expected_question_id_set
    )

    if missing_question_ids:
        raise InvalidGradingExecutionError(
            f"questions is missing expected question IDs: {missing_question_ids!r}."
        )
    if unexpected_question_ids:
        raise InvalidGradingExecutionError(
            f"questions contains unexpected question IDs: {unexpected_question_ids!r}."
        )

    questions_by_id = {question.question_id: question for question in questions}
    canonical_questions = tuple(
        questions_by_id[question_id] for question_id in expected_question_ids
    )

    for question in canonical_questions:
        rubric_question_id = question.authority.rubric.question_id
        policy_question_id = question.authority.policy.question_id
        if (
            question.question_id != rubric_question_id
            or question.question_id != policy_question_id
        ):
            raise InvalidGradingExecutionError(
                "QuestionExecutionInput.question_id must match authority rubric and "
                "policy question_id."
            )

    return canonical_questions


def execute_grading_from_evaluations(
    *,
    context: GradingExecutionContext,
    evidence: AnswerEvidenceBundle,
    questions: tuple[QuestionExecutionInput, ...],
    paper_authority: ResolvedPaperScoringAuthority,
) -> GradingExecutionResult:
    """Execute the S2a grading vertical from supplied evaluator judgments."""

    canonical_questions = _validate_execution_inputs(
        context=context,
        evidence=evidence,
        questions=questions,
        paper_authority=paper_authority,
    )

    records: list[QuestionExecutionRecord] = []
    scores: list[QuestionScoreResult] = []
    for question in canonical_questions:
        verified = verify_evaluated_judgments(
            evidence=evidence,
            question_id=question.question_id,
            judgments=question.judgments,
        )
        score = reduce_question(question.authority, verified.scoring_judgments)
        records.append(QuestionExecutionRecord(verified=verified, score=score))
        scores.append(score)

    paper_score = aggregate_paper(paper_authority, tuple(scores))
    return GradingExecutionResult(
        context=context,
        questions=tuple(records),
        paper_score=paper_score,
    )
