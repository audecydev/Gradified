from __future__ import annotations

from dataclasses import dataclass

from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlock,
    EvidenceBlockState,
)
from grading.contracts.judgment import CriterionJudgment


class EvidenceVerificationError(ValueError):
    """Raised when evaluator evidence references fail deterministic verification."""


@dataclass(frozen=True, slots=True)
class VerifiedCriterionJudgments:
    """Non-authoritative result of evidence-reference verification."""

    submission_ref: str
    question_id: str
    evaluated_judgments: tuple[EvaluatedCriterionJudgment, ...]
    scoring_judgments: tuple[CriterionJudgment, ...]

    def __post_init__(self) -> None:
        if type(self.submission_ref) is not str:
            raise TypeError(
                "VerifiedCriterionJudgments.submission_ref must be a string."
            )
        if not self.submission_ref or self.submission_ref.strip() != self.submission_ref:
            raise ValueError(
                "VerifiedCriterionJudgments.submission_ref must be non-empty "
                "without surrounding whitespace."
            )
        if type(self.question_id) is not str:
            raise TypeError("VerifiedCriterionJudgments.question_id must be a string.")
        if not self.question_id or self.question_id.strip() != self.question_id:
            raise ValueError(
                "VerifiedCriterionJudgments.question_id must be non-empty "
                "without surrounding whitespace."
            )
        if type(self.evaluated_judgments) is not tuple or any(
            type(value) is not EvaluatedCriterionJudgment
            for value in self.evaluated_judgments
        ):
            raise TypeError(
                "VerifiedCriterionJudgments.evaluated_judgments must be a tuple "
                "of exact EvaluatedCriterionJudgment values."
            )
        if type(self.scoring_judgments) is not tuple or any(
            type(value) is not CriterionJudgment for value in self.scoring_judgments
        ):
            raise TypeError(
                "VerifiedCriterionJudgments.scoring_judgments must be a tuple "
                "of exact CriterionJudgment values."
            )
        if len(self.evaluated_judgments) != len(self.scoring_judgments):
            raise ValueError(
                "VerifiedCriterionJudgments must preserve one scoring projection "
                "per evaluated judgment."
            )
        for evaluated, scoring in zip(
            self.evaluated_judgments,
            self.scoring_judgments,
        ):
            if (
                scoring.criterion_id != evaluated.criterion_id
                or scoring.selected_level != evaluated.selected_level
            ):
                raise ValueError(
                    "VerifiedCriterionJudgments scoring projection must exactly "
                    "preserve criterion_id and selected_level."
                )


def _require_question_id(question_id: object) -> str:
    if type(question_id) is not str:
        raise TypeError("question_id must be a string.")
    if not question_id or question_id.strip() != question_id:
        raise ValueError(
            "question_id must be non-empty without surrounding whitespace."
        )
    return question_id


def verify_evaluated_judgments(
    *,
    evidence: AnswerEvidenceBundle,
    question_id: str,
    judgments: tuple[EvaluatedCriterionJudgment, ...],
) -> VerifiedCriterionJudgments:
    """Verify evidence references and project semantic judgments for scoring.

    This function validates evidence relationships only. It does not calculate
    marks, infer scoring policy, or confer scoring authority.
    """

    if type(evidence) is not AnswerEvidenceBundle:
        raise TypeError("evidence must be an exact AnswerEvidenceBundle.")
    canonical_question_id = _require_question_id(question_id)
    if type(judgments) is not tuple or any(
        type(judgment) is not EvaluatedCriterionJudgment for judgment in judgments
    ):
        raise TypeError(
            "judgments must be a tuple of exact EvaluatedCriterionJudgment values."
        )

    matching_questions = tuple(
        question
        for question in evidence.questions
        if question.question_id == canonical_question_id
    )
    if len(matching_questions) != 1:
        raise EvidenceVerificationError(
            "Evidence bundle must contain exactly one matching question for verification."
        )

    block_owners: dict[str, tuple[str, EvidenceBlock]] = {}
    for question in evidence.questions:
        for block in question.blocks:
            # AnswerEvidenceBundle admission guarantees uniqueness. Keep this
            # defensive check fail-closed without silently overwriting evidence.
            if block.block_id in block_owners:
                raise EvidenceVerificationError(
                    "Evidence bundle contains an ambiguous duplicate block identifier."
                )
            block_owners[block.block_id] = (question.question_id, block)

    for judgment in judgments:
        if not judgment.evidence_refs:
            raise EvidenceVerificationError(
                "Current verification profile requires at least one evidence reference "
                "per evaluated judgment."
            )
        for evidence_ref in judgment.evidence_refs:
            owner_and_block = block_owners.get(evidence_ref)
            if owner_and_block is None:
                raise EvidenceVerificationError(
                    f"Evidence reference does not exist in the submission: {evidence_ref!r}."
                )

            owner_question_id, block = owner_and_block
            if owner_question_id != canonical_question_id:
                raise EvidenceVerificationError(
                    f"Evidence reference belongs to a different question: {evidence_ref!r}."
                )
            if block.state is EvidenceBlockState.CROSSED_OUT:
                raise EvidenceVerificationError(
                    "Crossed-out evidence cannot support scoring in the current "
                    f"verification profile: {evidence_ref!r}."
                )

    scoring_judgments = tuple(
        CriterionJudgment(
            criterion_id=judgment.criterion_id,
            selected_level=judgment.selected_level,
        )
        for judgment in judgments
    )

    return VerifiedCriterionJudgments(
        submission_ref=evidence.submission_ref,
        question_id=canonical_question_id,
        evaluated_judgments=judgments,
        scoring_judgments=scoring_judgments,
    )
