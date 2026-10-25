from __future__ import annotations

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import UnknownJudgmentPerformanceLevelError
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
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
    InvalidGradingExecutionError,
    QuestionExecutionInput,
    execute_grading_from_evaluations,
)
from grading.verification.evidence import (
    EvidenceVerificationError,
    verify_evaluated_judgments,
)


def _sd(value: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def _criterion(criterion_id: str, full_marks: object) -> AtomicCriterion:
    return AtomicCriterion(
        criterion_id=criterion_id,
        operational_description=f"Assess {criterion_id}.",
        performance_levels=(
            PerformanceLevel(level_id="FULL", contribution=_sd(full_marks)),
            PerformanceLevel(level_id="NOT_MET", contribution=_sd(0)),
        ),
    )


def _authority(
    question_id: str,
    *,
    criteria: tuple[AtomicCriterion, ...] | None = None,
    maximum: object = 5,
) -> QuestionScoringAuthority:
    rubric = CompiledQuestionRubric(
        rubric_id=f"R-{question_id}",
        version=1,
        question_id=question_id,
        max_marks=_sd(maximum),
        criteria=criteria or (_criterion("C1", maximum),),
    )
    policy = QuestionScoringPolicy(
        policy_id=f"P-{question_id}",
        version=1,
        question_id=question_id,
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=_sd(0),
        maximum_score=_sd(maximum),
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


def _paper(
    authorities: tuple[QuestionScoringAuthority, ...],
    *,
    maximum: object | None = None,
) -> ResolvedPaperScoringAuthority:
    if maximum is None:
        maximum = 5 * len(authorities)
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id="GS-S2A-ACC", version=1),
        expected_questions=tuple(_expected(authority) for authority in authorities),
        minimum_score=_sd(0),
        maximum_score=_sd(maximum),
    )


def _block(question_id: str) -> EvidenceBlock:
    return EvidenceBlock(
        block_id=f"{question_id}_B1",
        type=EvidenceBlockType.TEXT,
        content=f"Evidence for {question_id}.",
        language="en",
        confidence=None,
        confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
        state=EvidenceBlockState.ACTIVE,
        page=1,
        location=EvidenceLocation(
            status=EvidenceLocationStatus.UNAVAILABLE,
            bbox=None,
        ),
        reading_order=1,
        asset_ref=None,
    )


def _evidence(question_ids: tuple[str, ...] = ("Q1", "Q2")) -> AnswerEvidenceBundle:
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref="SUB-S2A-ACC",
        ocr_provenance="synthetic-ocr:s2a-acceptance",
        questions=tuple(
            QuestionEvidence(
                question_id=question_id,
                answer_scope_ref=f"{question_id}_SCOPE",
                blocks=(_block(question_id),),
                warnings=(),
            )
            for question_id in question_ids
        ),
    )


def _judgment(
    criterion_id: str,
    question_id: str,
    *,
    selected_level: str = "FULL",
    evidence_ref: str | None = None,
) -> EvaluatedCriterionJudgment:
    return EvaluatedCriterionJudgment(
        criterion_id=criterion_id,
        selected_level=selected_level,
        evidence_refs=(evidence_ref or f"{question_id}_B1",),
        reason_codes=(f"{criterion_id}_SUPPORTED",),
        concise_rationale=f"Rationale for {question_id}/{criterion_id}.",
        uncertainties=(),
        evaluator_metadata=EvaluatorMetadata(
            evaluator_id="synthetic-evaluator",
            version="1",
        ),
    )


def _work(
    question_id: str,
    authority: QuestionScoringAuthority,
    *,
    judgments: tuple[EvaluatedCriterionJudgment, ...] | None = None,
) -> QuestionExecutionInput:
    return QuestionExecutionInput(
        question_id=question_id,
        judgments=judgments or (_judgment("C1", question_id),),
        authority=authority,
    )


def _context(paper: ResolvedPaperScoringAuthority) -> GradingExecutionContext:
    return GradingExecutionContext(
        grading_run_id="RUN-S2A-ACC",
        submission_ref="SUB-S2A-ACC",
        exam_ref="EXAM-S2A-ACC",
        grading_spec_ref=paper.grading_spec_ref,
    )


def _valid_fixture():
    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    paper = _paper((q1_authority, q2_authority))
    return {
        "context": _context(paper),
        "evidence": _evidence(),
        "questions": (_work("Q1", q1_authority), _work("Q2", q2_authority)),
        "paper_authority": paper,
    }


@pytest.mark.parametrize("field", ("context", "evidence", "questions", "paper_authority"))
def test_s2a_acc_01_malformed_top_level_inputs_fail_at_s2_admission(field: str) -> None:
    kwargs = _valid_fixture()
    kwargs[field] = [] if field == "questions" else object()

    with pytest.raises(InvalidGradingExecutionError):
        execute_grading_from_evaluations(**kwargs)


def test_s2a_acc_02_all_question_authority_bindings_are_checked_before_execution() -> None:
    q1_authority = _authority("Q1")
    q2_expected_authority = _authority("Q2")
    q3_wrong_authority = _authority("Q3")
    paper = _paper((q1_authority, q2_expected_authority))

    poisoned_q1 = _work(
        "Q1",
        q1_authority,
        judgments=(
            _judgment("C1", "Q1", evidence_ref="DOES_NOT_EXIST"),
        ),
    )
    mismatched_q2 = _work("Q2", q3_wrong_authority)

    with pytest.raises(InvalidGradingExecutionError):
        execute_grading_from_evaluations(
            context=_context(paper),
            evidence=_evidence(),
            questions=(poisoned_q1, mismatched_q2),
            paper_authority=paper,
        )


def test_s2a_acc_03_execution_follows_authoritative_question_order_not_caller_order() -> None:
    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    paper = _paper((q1_authority, q2_authority))
    evidence = _evidence()

    q1 = _work(
        "Q1",
        q1_authority,
        judgments=(
            _judgment("C1", "Q1", evidence_ref="DOES_NOT_EXIST"),
        ),
    )
    q2 = _work(
        "Q2",
        q2_authority,
        judgments=(
            _judgment("C1", "Q2", selected_level="UNKNOWN_LEVEL"),
        ),
    )

    try:
        verify_evaluated_judgments(
            evidence=evidence,
            question_id="Q1",
            judgments=q1.judgments,
        )
    except EvidenceVerificationError as expected:
        expected_args = expected.args
    else:
        pytest.fail("Q1 poison did not produce the expected verifier failure.")

    with pytest.raises(EvidenceVerificationError) as caught:
        execute_grading_from_evaluations(
            context=_context(paper),
            evidence=evidence,
            questions=(q2, q1),
            paper_authority=paper,
        )

    assert caught.value.args == expected_args


def test_s2a_acc_04_rich_and_numeric_tracks_preserve_distinct_criterion_ordering() -> None:
    authority = _authority(
        "Q1",
        criteria=(_criterion("C1", 3), _criterion("C2", 2)),
        maximum=5,
    )
    paper = _paper((authority,), maximum=5)
    evidence = _evidence(("Q1",))
    judgments = (
        _judgment("C2", "Q1", selected_level="FULL"),
        _judgment("C1", "Q1", selected_level="FULL"),
    )

    result = execute_grading_from_evaluations(
        context=_context(paper),
        evidence=evidence,
        questions=(_work("Q1", authority, judgments=judgments),),
        paper_authority=paper,
    )

    record = result.questions[0]
    assert record.verified.submission_ref == result.context.submission_ref
    assert record.verified.evaluated_judgments == judgments
    assert tuple(j.criterion_id for j in record.verified.evaluated_judgments) == ("C2", "C1")
    assert tuple(effect.criterion_id for effect in record.score.criterion_effects) == ("C1", "C2")

    rich_levels = {
        judgment.criterion_id: judgment.selected_level
        for judgment in record.verified.evaluated_judgments
    }
    numeric_levels = {
        effect.criterion_id: effect.selected_level
        for effect in record.score.criterion_effects
    }
    assert numeric_levels == rich_levels
    assert result.paper_score.grading_spec_ref == result.context.grading_spec_ref
    assert result.paper_score.question_results == (record.score,)


def test_s2a_acc_05_later_question_b2_failure_never_returns_successful_execution_result() -> None:
    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    paper = _paper((q1_authority, q2_authority))
    evidence = _evidence()

    q1 = _work("Q1", q1_authority)
    q2 = _work(
        "Q2",
        q2_authority,
        judgments=(
            _judgment("C1", "Q2", selected_level="UNKNOWN_LEVEL"),
        ),
    )

    with pytest.raises(UnknownJudgmentPerformanceLevelError):
        execute_grading_from_evaluations(
            context=_context(paper),
            evidence=evidence,
            questions=(q1, q2),
            paper_authority=paper,
        )
