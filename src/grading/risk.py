from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlockState,
    EvidenceConfidenceStatus,
    QuestionEvidence,
)
from grading.execution import (
    GradingExecutionResult,
    QuestionExecutionRecord,
)


RISK_OBSERVATION_SCHEMA_VERSION = "1"


class InvalidRiskObservationInputError(ValueError):
    """Raised when S2b-1 cannot safely bind risk-observation inputs."""


class RiskObservationCode(str, Enum):
    """Risk observations currently supported by the S2b-1 profile."""

    OCR_CONFIDENCE_UNKNOWN = "OCR_CONFIDENCE_UNKNOWN"
    EVALUATOR_UNCERTAINTY_REPORTED = "EVALUATOR_UNCERTAINTY_REPORTED"


def _require_identifier(value: object, field_name: str) -> None:
    if type(value) is not str:
        raise InvalidRiskObservationInputError(f"{field_name} must be a string.")
    if not value or value.strip() != value:
        raise InvalidRiskObservationInputError(
            f"{field_name} must be non-empty without surrounding whitespace."
        )


def _require_optional_identifier(value: object, field_name: str) -> None:
    if value is None:
        return
    _require_identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class RiskObservation:
    code: RiskObservationCode
    question_id: str
    evidence_block_id: str | None
    criterion_id: str | None

    def __post_init__(self) -> None:
        if type(self.code) is not RiskObservationCode:
            raise InvalidRiskObservationInputError(
                "RiskObservation.code must be an exact RiskObservationCode."
            )
        _require_identifier(self.question_id, "RiskObservation.question_id")
        _require_optional_identifier(
            self.evidence_block_id,
            "RiskObservation.evidence_block_id",
        )
        _require_optional_identifier(self.criterion_id, "RiskObservation.criterion_id")

        if self.code is RiskObservationCode.OCR_CONFIDENCE_UNKNOWN:
            if self.evidence_block_id is None or self.criterion_id is not None:
                raise InvalidRiskObservationInputError(
                    "OCR_CONFIDENCE_UNKNOWN requires evidence_block_id and no criterion_id."
                )
        elif self.code is RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED:
            if self.criterion_id is None or self.evidence_block_id is not None:
                raise InvalidRiskObservationInputError(
                    "EVALUATOR_UNCERTAINTY_REPORTED requires criterion_id and no "
                    "evidence_block_id."
                )


@dataclass(frozen=True, slots=True)
class RiskObservationSet:
    schema_version: str
    grading_run_id: str
    submission_ref: str
    observations: tuple[RiskObservation, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RISK_OBSERVATION_SCHEMA_VERSION:
            raise InvalidRiskObservationInputError(
                "RiskObservationSet.schema_version must be the supported profile."
            )
        _require_identifier(self.grading_run_id, "RiskObservationSet.grading_run_id")
        _require_identifier(self.submission_ref, "RiskObservationSet.submission_ref")
        if type(self.observations) is not tuple or any(
            type(observation) is not RiskObservation for observation in self.observations
        ):
            raise InvalidRiskObservationInputError(
                "RiskObservationSet.observations must be a tuple of exact RiskObservation values."
            )


def _validate_and_bind_inputs(
    *,
    execution: object,
    evidence: object,
) -> tuple[tuple[QuestionExecutionRecord, QuestionEvidence], ...]:
    if type(execution) is not GradingExecutionResult:
        raise InvalidRiskObservationInputError(
            "execution must be an exact GradingExecutionResult."
        )
    if type(evidence) is not AnswerEvidenceBundle:
        raise InvalidRiskObservationInputError(
            "evidence must be an exact AnswerEvidenceBundle."
        )

    if execution.context.submission_ref != evidence.submission_ref:
        raise InvalidRiskObservationInputError(
            "execution.context.submission_ref must match evidence.submission_ref."
        )

    records = execution.questions
    if type(records) is not tuple or any(
        type(record) is not QuestionExecutionRecord for record in records
    ):
        raise InvalidRiskObservationInputError(
            "execution.questions must be a tuple of exact QuestionExecutionRecord values."
        )

    seen_question_ids: set[str] = set()
    record_scores = []
    for record in records:
        verified = record.verified
        score = record.score

        if verified.submission_ref != execution.context.submission_ref:
            raise InvalidRiskObservationInputError(
                "verified submission_ref must match execution context submission_ref."
            )
        if verified.question_id != score.question_id:
            raise InvalidRiskObservationInputError(
                "verified question_id must match numerical score question_id."
            )
        if score.question_id in seen_question_ids:
            raise InvalidRiskObservationInputError(
                f"execution contains duplicate question_id {score.question_id!r}."
            )
        seen_question_ids.add(score.question_id)
        record_scores.append(score)

        evaluated = verified.evaluated_judgments
        scoring = verified.scoring_judgments
        effects = score.criterion_effects

        evaluated_ids = tuple(item.criterion_id for item in evaluated)
        scoring_ids = tuple(item.criterion_id for item in scoring)
        effect_ids = tuple(item.criterion_id for item in effects)

        if len(set(evaluated_ids)) != len(evaluated_ids):
            raise InvalidRiskObservationInputError(
                "verified evaluated judgments contain duplicate criterion_id values."
            )
        if len(set(scoring_ids)) != len(scoring_ids):
            raise InvalidRiskObservationInputError(
                "verified scoring judgments contain duplicate criterion_id values."
            )
        if len(set(effect_ids)) != len(effect_ids):
            raise InvalidRiskObservationInputError(
                "numerical criterion effects contain duplicate criterion_id values."
            )

        if set(scoring_ids) != set(effect_ids):
            raise InvalidRiskObservationInputError(
                "verified scoring judgments and numerical criterion effects must "
                "cover the same criterion_id universe."
            )

        scoring_by_id = {item.criterion_id: item for item in scoring}
        for effect in effects:
            scoring_judgment = scoring_by_id[effect.criterion_id]
            if scoring_judgment.selected_level != effect.selected_level:
                raise InvalidRiskObservationInputError(
                    "verified scoring selected_level must match numerical "
                    "criterion effect selected_level."
                )

    if tuple(record_scores) != execution.paper_score.question_results:
        raise InvalidRiskObservationInputError(
            "execution question scores must exactly match paper_score.question_results "
            "in authoritative order."
        )

    bound_questions: list[tuple[QuestionExecutionRecord, QuestionEvidence]] = []
    for record in records:
        question_id = record.score.question_id
        matches = tuple(
            question for question in evidence.questions if question.question_id == question_id
        )
        if len(matches) != 1:
            raise InvalidRiskObservationInputError(
                "evidence must contain exactly one matching QuestionEvidence for "
                f"executed question_id {question_id!r}."
            )
        bound_questions.append((record, matches[0]))

    return tuple(bound_questions)


def extract_risk_observations(
    *,
    execution: GradingExecutionResult,
    evidence: AnswerEvidenceBundle,
) -> RiskObservationSet:
    """Extract supported S2b-1 risk observations without making review policy."""

    bound_questions = _validate_and_bind_inputs(
        execution=execution,
        evidence=evidence,
    )

    observations: list[RiskObservation] = []
    for record, question_evidence in bound_questions:
        question_id = record.score.question_id

        for block in question_evidence.blocks:
            if block.state is EvidenceBlockState.CROSSED_OUT:
                continue
            if block.confidence_status is EvidenceConfidenceStatus.UNAVAILABLE:
                observations.append(
                    RiskObservation(
                        code=RiskObservationCode.OCR_CONFIDENCE_UNKNOWN,
                        question_id=question_id,
                        evidence_block_id=block.block_id,
                        criterion_id=None,
                    )
                )

        evaluated_by_id = {
            judgment.criterion_id: judgment
            for judgment in record.verified.evaluated_judgments
        }
        for effect in record.score.criterion_effects:
            evaluated = evaluated_by_id[effect.criterion_id]
            if evaluated.uncertainties:
                observations.append(
                    RiskObservation(
                        code=RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED,
                        question_id=question_id,
                        evidence_block_id=None,
                        criterion_id=effect.criterion_id,
                    )
                )

    return RiskObservationSet(
        schema_version=RISK_OBSERVATION_SCHEMA_VERSION,
        grading_run_id=execution.context.grading_run_id,
        submission_ref=execution.context.submission_ref,
        observations=tuple(observations),
    )
