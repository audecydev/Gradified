from __future__ import annotations

from dataclasses import fields, replace

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlock,
    EvidenceBlockState,
    EvidenceBlockType,
    EvidenceConfidenceStatus,
    EvidenceLocation,
    EvidenceLocationStatus,
    QuestionEvidence,
)
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult,
    GradingSpecRef,
    ResolvedPaperScoringAuthority,
)
from grading.contracts.policy import QuestionScoringPolicy, SCORING_SEMANTICS_V1
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import (
    GradingExecutionContext,
    GradingExecutionResult,
    QuestionExecutionInput,
    QuestionExecutionRecord,
    execute_grading_from_evaluations,
)
from grading.verification.evidence import VerifiedCriterionJudgments
from grading.risk import (
    RISK_OBSERVATION_SCHEMA_VERSION,
    InvalidRiskObservationInputError,
    RiskObservation,
    RiskObservationCode,
    RiskObservationSet,
    extract_risk_observations,
)


def _sd(value: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def _authority(question_id: str) -> QuestionScoringAuthority:
    criterion = AtomicCriterion(
        criterion_id="C1",
        operational_description=f"Assess C1 for {question_id}.",
        performance_levels=(
            PerformanceLevel(level_id="FULL", contribution=_sd(5)),
            PerformanceLevel(level_id="NOT_MET", contribution=_sd(0)),
        ),
    )
    rubric = CompiledQuestionRubric(
        rubric_id=f"R-{question_id}",
        version=1,
        question_id=question_id,
        max_marks=_sd(5),
        criteria=(criterion,),
    )
    policy = QuestionScoringPolicy(
        policy_id=f"P-{question_id}",
        version=1,
        question_id=question_id,
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=_sd(0),
        maximum_score=_sd(5),
    )
    return QuestionScoringAuthority(rubric=rubric, policy=policy)


def _expected(authority: QuestionScoringAuthority) -> ExpectedQuestionResult:
    return ExpectedQuestionResult(
        question_id=authority.rubric.question_id,
        rubric_ref=RubricRef(
            id=authority.rubric.rubric_id,
            version=authority.rubric.version,
        ),
        scoring_policy_ref=ScoringPolicyRef(
            id=authority.policy.policy_id,
            version=authority.policy.version,
            scoring_semantics_version=authority.policy.scoring_semantics_version,
        ),
    )


def _paper(authorities: tuple[QuestionScoringAuthority, ...]) -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id="GS-S2B1", version=1),
        expected_questions=tuple(_expected(authority) for authority in authorities),
        minimum_score=_sd(0),
        maximum_score=_sd(5 * len(authorities)),
    )


def _block(
    question_id: str,
    *,
    suffix: str = "B1",
    confidence_status: EvidenceConfidenceStatus = EvidenceConfidenceStatus.PRESENT,
    confidence: int | float | None = 1.0,
) -> EvidenceBlock:
    if confidence_status is EvidenceConfidenceStatus.UNAVAILABLE:
        confidence = None
    return EvidenceBlock(
        block_id=f"{question_id}_{suffix}",
        type=EvidenceBlockType.TEXT,
        content=f"Evidence for {question_id}.",
        language="en",
        confidence=confidence,
        confidence_status=confidence_status,
        state=EvidenceBlockState.ACTIVE,
        page=1,
        location=EvidenceLocation(
            status=EvidenceLocationStatus.PRESENT,
            bbox=(0.0, 0.0, 1.0, 1.0),
        ),
        reading_order=1,
        asset_ref=None,
    )


def _question_evidence(
    question_id: str,
    *,
    block: EvidenceBlock | None = None,
    warnings: tuple[str, ...] = (),
) -> QuestionEvidence:
    return QuestionEvidence(
        question_id=question_id,
        answer_scope_ref=f"{question_id}_SCOPE",
        blocks=(block or _block(question_id),),
        warnings=warnings,
    )


def _evidence(
    questions: tuple[QuestionEvidence, ...],
    *,
    submission_ref: str = "SUB-S2B1",
) -> AnswerEvidenceBundle:
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref=submission_ref,
        ocr_provenance="synthetic-ocr:s2b1",
        questions=questions,
    )


def _judgment(
    question_id: str,
    *,
    evidence_ref: str | None = None,
    selected_level: str = "FULL",
    reason_codes: tuple[str, ...] = (),
    uncertainties: tuple[str, ...] = (),
) -> EvaluatedCriterionJudgment:
    return EvaluatedCriterionJudgment(
        criterion_id="C1",
        selected_level=selected_level,
        evidence_refs=(evidence_ref or f"{question_id}_B1",),
        reason_codes=reason_codes,
        concise_rationale=f"Rationale for {question_id}.",
        uncertainties=uncertainties,
        evaluator_metadata=EvaluatorMetadata(
            evaluator_id="synthetic-evaluator",
            version="1",
        ),
    )


def _execute(
    *,
    question_ids: tuple[str, ...],
    evidence: AnswerEvidenceBundle,
    judgments_by_question: dict[str, tuple[EvaluatedCriterionJudgment, ...]] | None = None,
) -> GradingExecutionResult:
    authorities = tuple(_authority(question_id) for question_id in question_ids)
    paper = _paper(authorities)
    context = GradingExecutionContext(
        grading_run_id="RUN-S2B1-1",
        submission_ref=evidence.submission_ref,
        exam_ref="EXAM-S2B1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    questions = tuple(
        QuestionExecutionInput(
            question_id=question_id,
            judgments=(judgments_by_question or {}).get(
                question_id,
                (_judgment(question_id),),
            ),
            authority=authority,
        )
        for question_id, authority in zip(question_ids, authorities)
    )
    return execute_grading_from_evaluations(
        context=context,
        evidence=evidence,
        questions=questions,
        paper_authority=paper,
    )


def test_s2b1_obs_01_extracts_only_supported_observations_with_contextual_traceability() -> None:
    evidence = _evidence(
        (
            _question_evidence("Q2"),
            _question_evidence(
                "Q1",
                block=_block(
                    "Q1",
                    confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
                ),
            ),
        )
    )
    execution = _execute(
        question_ids=("Q1", "Q2"),
        evidence=evidence,
        judgments_by_question={
            "Q1": (_judgment("Q1"),),
            "Q2": (
                _judgment(
                    "Q2",
                    uncertainties=("Evaluator reports unresolved ambiguity.",),
                ),
            ),
        },
    )
    before_question_scores = tuple(
        result.final_score for result in execution.paper_score.question_results
    )
    before_paper_score = execution.paper_score.final_score

    observed = extract_risk_observations(execution=execution, evidence=evidence)

    assert observed.schema_version == RISK_OBSERVATION_SCHEMA_VERSION == "1"
    assert observed.grading_run_id == execution.context.grading_run_id
    assert observed.submission_ref == execution.context.submission_ref
    assert observed.observations == (
        RiskObservation(
            code=RiskObservationCode.OCR_CONFIDENCE_UNKNOWN,
            question_id="Q1",
            evidence_block_id="Q1_B1",
            criterion_id=None,
        ),
        RiskObservation(
            code=RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED,
            question_id="Q2",
            evidence_block_id=None,
            criterion_id="C1",
        ),
    )

    assert tuple(
        result.final_score for result in execution.paper_score.question_results
    ) == before_question_scores
    assert execution.paper_score.final_score == before_paper_score


def test_s2b1_bind_01_submission_mismatch_is_rejected() -> None:
    valid_evidence = _evidence((_question_evidence("Q1"),))
    execution = _execute(question_ids=("Q1",), evidence=valid_evidence)
    wrong_evidence = _evidence(
        (_question_evidence("Q1"),),
        submission_ref="SUB-OTHER",
    )

    with pytest.raises(InvalidRiskObservationInputError):
        extract_risk_observations(execution=execution, evidence=wrong_evidence)


def test_s2b1_continuity_01_verified_and_numeric_question_identity_must_agree() -> None:
    q1_evidence = _evidence((_question_evidence("Q1"),))
    q2_evidence = _evidence(
        (_question_evidence("Q2"),),
        submission_ref=q1_evidence.submission_ref,
    )
    q1_execution = _execute(question_ids=("Q1",), evidence=q1_evidence)
    q2_execution = _execute(question_ids=("Q2",), evidence=q2_evidence)

    inconsistent = GradingExecutionResult(
        context=q1_execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=q1_execution.questions[0].verified,
                score=q2_execution.questions[0].score,
            ),
        ),
        paper_score=q1_execution.paper_score,
    )

    with pytest.raises(InvalidRiskObservationInputError):
        extract_risk_observations(execution=inconsistent, evidence=q1_evidence)


def test_s2b1_continuity_01_verified_submission_must_match_execution_context() -> None:
    q1_evidence = _evidence((_question_evidence("Q1"),))
    other_submission_evidence = _evidence(
        (_question_evidence("Q1"),),
        submission_ref="SUB-OTHER",
    )
    q1_execution = _execute(question_ids=("Q1",), evidence=q1_evidence)
    other_submission_execution = _execute(
        question_ids=("Q1",),
        evidence=other_submission_evidence,
    )

    inconsistent = GradingExecutionResult(
        context=q1_execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=other_submission_execution.questions[0].verified,
                score=q1_execution.questions[0].score,
            ),
        ),
        paper_score=q1_execution.paper_score,
    )

    with pytest.raises(InvalidRiskObservationInputError):
        extract_risk_observations(execution=inconsistent, evidence=q1_evidence)


def test_s2b1_continuity_01_execution_records_must_match_paper_question_results() -> None:
    evidence = _evidence(
        (
            _question_evidence("Q1"),
            _question_evidence("Q2"),
        )
    )
    canonical_execution = _execute(
        question_ids=("Q1", "Q2"),
        evidence=evidence,
    )
    reversed_execution = _execute(
        question_ids=("Q2", "Q1"),
        evidence=evidence,
    )

    reversed_paper = GradingExecutionResult(
        context=canonical_execution.context,
        questions=canonical_execution.questions,
        paper_score=reversed_execution.paper_score,
    )

    q1_evidence = _evidence((_question_evidence("Q1"),))
    q1_full = _execute(question_ids=("Q1",), evidence=q1_evidence)
    q1_not_met = _execute(
        question_ids=("Q1",),
        evidence=q1_evidence,
        judgments_by_question={
            "Q1": (
                _judgment(
                    "Q1",
                    selected_level="NOT_MET",
                ),
            )
        },
    )
    same_question_different_score = GradingExecutionResult(
        context=q1_full.context,
        questions=q1_full.questions,
        paper_score=q1_not_met.paper_score,
    )

    duplicated_score = q1_full.questions[0].score
    duplicate_question_execution = GradingExecutionResult(
        context=q1_full.context,
        questions=(q1_full.questions[0], q1_full.questions[0]),
        paper_score=replace(
            q1_full.paper_score,
            question_results=(duplicated_score, duplicated_score),
        ),
    )

    for inconsistent, bound_evidence in (
        (reversed_paper, evidence),
        (same_question_different_score, q1_evidence),
        (duplicate_question_execution, q1_evidence),
    ):
        with pytest.raises(InvalidRiskObservationInputError):
            extract_risk_observations(
                execution=inconsistent,
                evidence=bound_evidence,
            )


def test_s2b1_continuity_01_rich_criterion_projection_must_match_numeric_effects() -> None:
    evidence = _evidence((_question_evidence("Q1"),))
    execution = _execute(question_ids=("Q1",), evidence=evidence)
    original_record = execution.questions[0]
    original_verified = original_record.verified
    original_evaluated = original_verified.evaluated_judgments[0]
    original_scoring = original_verified.scoring_judgments[0]
    original_effect = original_record.score.criterion_effects[0]

    duplicate_verified = VerifiedCriterionJudgments(
        submission_ref=original_verified.submission_ref,
        question_id=original_verified.question_id,
        evaluated_judgments=(original_evaluated, original_evaluated),
        scoring_judgments=(original_scoring, original_scoring),
    )
    duplicate_execution = GradingExecutionResult(
        context=execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=duplicate_verified,
                score=original_record.score,
            ),
        ),
        paper_score=execution.paper_score,
    )

    mismatched_evaluated = EvaluatedCriterionJudgment(
        criterion_id=original_evaluated.criterion_id,
        selected_level="NOT_MET",
        evidence_refs=original_evaluated.evidence_refs,
        reason_codes=original_evaluated.reason_codes,
        concise_rationale=original_evaluated.concise_rationale,
        uncertainties=("Still uncertain.",),
        evaluator_metadata=original_evaluated.evaluator_metadata,
    )
    mismatched_verified = VerifiedCriterionJudgments(
        submission_ref=original_verified.submission_ref,
        question_id=original_verified.question_id,
        evaluated_judgments=(mismatched_evaluated,),
        scoring_judgments=(
            CriterionJudgment(
                criterion_id=mismatched_evaluated.criterion_id,
                selected_level=mismatched_evaluated.selected_level,
            ),
        ),
    )
    mismatched_execution = GradingExecutionResult(
        context=execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=mismatched_verified,
                score=original_record.score,
            ),
        ),
        paper_score=execution.paper_score,
    )

    extra_evaluated = EvaluatedCriterionJudgment(
        criterion_id="C2",
        selected_level="FULL",
        evidence_refs=original_evaluated.evidence_refs,
        reason_codes=(),
        concise_rationale="Additional forged rich criterion.",
        uncertainties=(),
        evaluator_metadata=original_evaluated.evaluator_metadata,
    )
    rich_extra_verified = VerifiedCriterionJudgments(
        submission_ref=original_verified.submission_ref,
        question_id=original_verified.question_id,
        evaluated_judgments=(original_evaluated, extra_evaluated),
        scoring_judgments=(
            original_scoring,
            CriterionJudgment(
                criterion_id="C2",
                selected_level="FULL",
            ),
        ),
    )
    rich_extra_execution = GradingExecutionResult(
        context=execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=rich_extra_verified,
                score=original_record.score,
            ),
        ),
        paper_score=execution.paper_score,
    )

    extra_effect = replace(original_effect, criterion_id="C2")
    numeric_extra_score = replace(
        original_record.score,
        criterion_effects=(original_effect, extra_effect),
    )
    numeric_extra_execution = GradingExecutionResult(
        context=execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=original_verified,
                score=numeric_extra_score,
            ),
        ),
        paper_score=replace(
            execution.paper_score,
            question_results=(numeric_extra_score,),
        ),
    )

    numeric_duplicate_score = replace(
        original_record.score,
        criterion_effects=(original_effect, original_effect),
    )
    numeric_duplicate_execution = GradingExecutionResult(
        context=execution.context,
        questions=(
            QuestionExecutionRecord(
                verified=original_verified,
                score=numeric_duplicate_score,
            ),
        ),
        paper_score=replace(
            execution.paper_score,
            question_results=(numeric_duplicate_score,),
        ),
    )

    for inconsistent in (
        duplicate_execution,
        mismatched_execution,
        rich_extra_execution,
        numeric_extra_execution,
        numeric_duplicate_execution,
    ):
        with pytest.raises(InvalidRiskObservationInputError):
            extract_risk_observations(execution=inconsistent, evidence=evidence)


def test_s2b1_scope_01_unrelated_evidence_question_cannot_emit_observations() -> None:
    evidence = _evidence(
        (
            _question_evidence(
                "Q9",
                block=_block(
                    "Q9",
                    confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
                ),
            ),
            _question_evidence("Q1"),
        )
    )
    execution = _execute(question_ids=("Q1",), evidence=evidence)

    observed = extract_risk_observations(execution=execution, evidence=evidence)

    assert observed.observations == ()


def test_s2b1_scope_01_requires_exactly_one_evidence_question_per_execution_question() -> None:
    valid_evidence = _evidence((_question_evidence("Q1"),))
    execution = _execute(question_ids=("Q1",), evidence=valid_evidence)
    duplicate_question_evidence = _evidence(
        (
            _question_evidence("Q1", block=_block("Q1", suffix="B1")),
            _question_evidence("Q1", block=_block("Q1", suffix="B2")),
        )
    )

    with pytest.raises(InvalidRiskObservationInputError):
        extract_risk_observations(
            execution=execution,
            evidence=duplicate_question_evidence,
        )


def test_s2b1_scope_01_requires_matching_evidence_for_every_execution_question() -> None:
    complete_evidence = _evidence(
        (
            _question_evidence("Q1"),
            _question_evidence("Q2"),
        )
    )
    execution = _execute(
        question_ids=("Q1", "Q2"),
        evidence=complete_evidence,
    )
    incomplete_evidence = _evidence((_question_evidence("Q1"),))

    with pytest.raises(InvalidRiskObservationInputError):
        extract_risk_observations(
            execution=execution,
            evidence=incomplete_evidence,
        )


def test_s2b1_obs_01_emits_one_ocr_observation_per_affected_block_in_stable_order() -> None:
    question = QuestionEvidence(
        question_id="Q1",
        answer_scope_ref="Q1_SCOPE",
        blocks=(
            _block(
                "Q1",
                suffix="B1",
                confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
            ),
            _block(
                "Q1",
                suffix="B2",
                confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
            ),
        ),
        warnings=(),
    )
    evidence = _evidence((question,))
    execution = _execute(
        question_ids=("Q1",),
        evidence=evidence,
        judgments_by_question={
            "Q1": (
                _judgment(
                    "Q1",
                    evidence_ref="Q1_B1",
                    uncertainties=("Evaluator reports unresolved ambiguity.",),
                ),
            )
        },
    )

    observed = extract_risk_observations(execution=execution, evidence=evidence)

    assert observed.observations == (
        RiskObservation(
            code=RiskObservationCode.OCR_CONFIDENCE_UNKNOWN,
            question_id="Q1",
            evidence_block_id="Q1_B1",
            criterion_id=None,
        ),
        RiskObservation(
            code=RiskObservationCode.OCR_CONFIDENCE_UNKNOWN,
            question_id="Q1",
            evidence_block_id="Q1_B2",
            criterion_id=None,
        ),
        RiskObservation(
            code=RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED,
            question_id="Q1",
            evidence_block_id=None,
            criterion_id="C1",
        ),
    )



def test_s2b1_obs_01_crossed_out_unknown_confidence_is_not_active_risk_evidence() -> None:
    active_block = _block("Q1", suffix="B1")
    crossed_out_unknown = replace(
        _block(
            "Q1",
            suffix="B2",
            confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
        ),
        state=EvidenceBlockState.CROSSED_OUT,
    )
    question = QuestionEvidence(
        question_id="Q1",
        answer_scope_ref="Q1_SCOPE",
        blocks=(active_block, crossed_out_unknown),
        warnings=(),
    )
    evidence = _evidence((question,))
    execution = _execute(question_ids=("Q1",), evidence=evidence)

    observed = extract_risk_observations(execution=execution, evidence=evidence)

    assert observed.observations == ()

def test_s2b1_nonpolicy_01_does_not_threshold_numeric_confidence() -> None:
    evidence = _evidence(
        (
            _question_evidence(
                "Q1",
                block=_block(
                    "Q1",
                    confidence_status=EvidenceConfidenceStatus.PRESENT,
                    confidence=0.0,
                ),
            ),
        )
    )
    execution = _execute(question_ids=("Q1",), evidence=evidence)

    observed = extract_risk_observations(execution=execution, evidence=evidence)

    assert observed.observations == ()
    assert {code.value for code in RiskObservationCode} == {
        "OCR_CONFIDENCE_UNKNOWN",
        "EVALUATOR_UNCERTAINTY_REPORTED",
    }


def test_s2b1_nonpolicy_01_does_not_interpret_freeform_strings_or_expose_policy() -> None:
    evidence = _evidence(
        (
            _question_evidence(
                "Q1",
                warnings=("PROMPT_INJECTION_SIGNAL", "OCR_LOW_CONFIDENCE"),
            ),
        )
    )
    execution = _execute(
        question_ids=("Q1",),
        evidence=evidence,
        judgments_by_question={
            "Q1": (
                _judgment(
                    "Q1",
                    reason_codes=("OUT_OF_DISTRIBUTION", "POLICY_REQUIRES_HUMAN"),
                    uncertainties=(),
                ),
            )
        },
    )

    observed = extract_risk_observations(execution=execution, evidence=evidence)

    assert observed.observations == ()
    assert {field.name for field in fields(RiskObservationSet)} == {
        "schema_version",
        "grading_run_id",
        "submission_ref",
        "observations",
    }
    assert {field.name for field in fields(RiskObservation)} == {
        "code",
        "question_id",
        "evidence_block_id",
        "criterion_id",
    }
    forbidden_policy_fields = {
        "recommendation",
        "review_action",
        "risk_level",
        "risk_score",
        "risk_tier",
        "impact_tier",
        "workflow_state",
        "publication_state",
    }
    assert {field.name for field in fields(RiskObservationSet)}.isdisjoint(
        forbidden_policy_fields
    )

@pytest.mark.parametrize(
    ("execution_value", "evidence_value"),
    (
        ([], _evidence((_question_evidence("Q1"),))),
        (_execute(question_ids=("Q1",), evidence=_evidence((_question_evidence("Q1"),))), None),
    ),
)
def test_s2b1_acceptance_ordinary_malformed_top_level_inputs_are_controlled(
    execution_value,
    evidence_value,
) -> None:
    with pytest.raises(InvalidRiskObservationInputError):
        extract_risk_observations(
            execution=execution_value,
            evidence=evidence_value,
        )


def test_s2b1_acceptance_repeated_extraction_is_deterministic_and_non_mutating() -> None:
    evidence = _evidence(
        (
            _question_evidence(
                "Q1",
                block=_block(
                    "Q1",
                    confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
                ),
            ),
            _question_evidence("Q2"),
        )
    )
    execution = _execute(
        question_ids=("Q1", "Q2"),
        evidence=evidence,
        judgments_by_question={
            "Q1": (_judgment("Q1"),),
            "Q2": (_judgment("Q2", uncertainties=("reported",)),),
        },
    )
    execution_before = repr(execution)
    evidence_before = repr(evidence)

    first = extract_risk_observations(execution=execution, evidence=evidence)
    second = extract_risk_observations(execution=execution, evidence=evidence)

    assert first == second
    assert repr(execution) == execution_before
    assert repr(evidence) == evidence_before
