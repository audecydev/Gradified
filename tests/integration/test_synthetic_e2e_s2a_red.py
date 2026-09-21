from __future__ import annotations

from dataclasses import fields
from inspect import Parameter, signature

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import (
    InvalidPaperAggregationInputError,
    UnknownJudgmentPerformanceLevelError,
)
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
    GradingExecutionResult,
    InvalidGradingExecutionError,
    QuestionExecutionInput,
    QuestionExecutionRecord,
    execute_grading_from_evaluations,
)
from grading.scoring.paper_aggregation import aggregate_paper
from grading.scoring.reducer import reduce_question
from grading.verification.evidence import (
    EvidenceVerificationError,
    verify_evaluated_judgments,
)


def _sd(value: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def _authority(
    question_id: str,
    *,
    levels: tuple[tuple[str, object], ...] = (("FULL", 5), ("NOT_MET", 0)),
    rubric_id: str | None = None,
    policy_id: str | None = None,
) -> QuestionScoringAuthority:
    criterion = AtomicCriterion(
        criterion_id="C1",
        operational_description=f"Assess criterion C1 for {question_id}.",
        performance_levels=tuple(
            PerformanceLevel(level_id=level_id, contribution=_sd(contribution))
            for level_id, contribution in levels
        ),
    )
    rubric = CompiledQuestionRubric(
        rubric_id=rubric_id or f"R-{question_id}",
        version=1,
        question_id=question_id,
        max_marks=_sd(5),
        criteria=(criterion,),
    )
    policy = QuestionScoringPolicy(
        policy_id=policy_id or f"P-{question_id}",
        version=1,
        question_id=question_id,
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=_sd(0),
        maximum_score=_sd(5),
    )
    return QuestionScoringAuthority(rubric=rubric, policy=policy)


def _expected(
    authority: QuestionScoringAuthority,
    *,
    question_id: str | None = None,
    rubric_ref: RubricRef | None = None,
    policy_ref: ScoringPolicyRef | None = None,
) -> ExpectedQuestionResult:
    return ExpectedQuestionResult(
        question_id=question_id or authority.rubric.question_id,
        rubric_ref=rubric_ref
        or RubricRef(
            id=authority.rubric.rubric_id,
            version=authority.rubric.version,
        ),
        scoring_policy_ref=policy_ref
        or ScoringPolicyRef(
            id=authority.policy.policy_id,
            version=authority.policy.version,
            scoring_semantics_version=authority.policy.scoring_semantics_version,
        ),
    )


def _paper_authority(
    authorities: tuple[QuestionScoringAuthority, ...],
    *,
    spec_ref: GradingSpecRef | None = None,
    expected_override: tuple[ExpectedQuestionResult, ...] | None = None,
) -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=spec_ref or GradingSpecRef(id="GS-S2A", version=1),
        expected_questions=expected_override
        if expected_override is not None
        else tuple(_expected(authority) for authority in authorities),
        minimum_score=_sd(0),
        maximum_score=_sd(5 * len(authorities)),
    )


def _block(question_id: str) -> EvidenceBlock:
    return EvidenceBlock(
        block_id=f"{question_id}_B1",
        type=EvidenceBlockType.TEXT,
        content=f"Evidence for {question_id} criterion C1.",
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


def _evidence(
    question_ids: tuple[str, ...] = ("Q1", "Q2"),
    *,
    submission_ref: str = "SUB-S2A",
) -> AnswerEvidenceBundle:
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref=submission_ref,
        ocr_provenance="synthetic-ocr:s2a",
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


def _judgments(
    question_id: str,
    *,
    selected_level: str = "FULL",
    evidence_ref: str | None = None,
    rationale: str | None = None,
) -> tuple[EvaluatedCriterionJudgment, ...]:
    return (
        EvaluatedCriterionJudgment(
            criterion_id="C1",
            selected_level=selected_level,
            evidence_refs=(evidence_ref or f"{question_id}_B1",),
            reason_codes=(f"{question_id}_SUPPORTED",),
            concise_rationale=rationale or f"Rich rationale for {question_id}.",
            uncertainties=(),
            evaluator_metadata=EvaluatorMetadata(
                evaluator_id="synthetic-evaluator",
                version="1",
            ),
        ),
    )


def _context(
    *,
    submission_ref: str = "SUB-S2A",
    spec_ref: GradingSpecRef | None = None,
) -> GradingExecutionContext:
    return GradingExecutionContext(
        grading_run_id="RUN-S2A-1",
        submission_ref=submission_ref,
        exam_ref="EXAM-S2A",
        grading_spec_ref=spec_ref or GradingSpecRef(id="GS-S2A", version=1),
    )


def _work(
    question_id: str,
    authority: QuestionScoringAuthority,
    *,
    judgments: tuple[EvaluatedCriterionJudgment, ...] | None = None,
) -> QuestionExecutionInput:
    return QuestionExecutionInput(
        question_id=question_id,
        judgments=judgments or _judgments(question_id),
        authority=authority,
    )


def _capture_expected_exception(call):
    try:
        call()
    except Exception as exc:  # test helper intentionally captures the native boundary error
        return type(exc), exc.args, exc.__cause__
    pytest.fail("Fixture did not produce the expected downstream exception.")


def _assert_same_native_failure(expected, call) -> None:
    expected_type, expected_args, expected_cause = expected
    with pytest.raises(expected_type) as caught:
        call()
    assert caught.value.args == expected_args
    assert caught.value.__cause__ is expected_cause
    assert type(caught.value) is expected_type


def test_s2a_exec_01_real_vertical_uses_minimal_input_and_authoritative_order() -> None:
    assert {field.name for field in fields(QuestionExecutionInput)} == {
        "question_id",
        "judgments",
        "authority",
    }
    forbidden_input_fields = {
        "verified",
        "verified_judgments",
        "score",
        "question_score",
        "paper_score",
        "result",
    }
    assert {field.name for field in fields(QuestionExecutionInput)}.isdisjoint(
        forbidden_input_fields
    )

    parameters = signature(execute_grading_from_evaluations).parameters
    assert tuple(parameters) == ("context", "evidence", "questions", "paper_authority")
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for parameter in parameters.values())

    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    paper = _paper_authority((q1_authority, q2_authority))
    context = _context(spec_ref=paper.grading_spec_ref)
    evidence = _evidence()

    q1 = _work(
        "Q1",
        q1_authority,
        judgments=_judgments("Q1", rationale="Q1 rationale must survive verification."),
    )
    q2 = _work(
        "Q2",
        q2_authority,
        judgments=_judgments("Q2", rationale="Q2 rationale must survive verification."),
    )

    result = execute_grading_from_evaluations(
        context=context,
        evidence=evidence,
        questions=(q2, q1),
        paper_authority=paper,
    )

    assert type(result) is GradingExecutionResult
    assert result.context == context
    assert tuple(record.verified.question_id for record in result.questions) == ("Q1", "Q2")
    assert tuple(record.score.question_id for record in result.questions) == ("Q1", "Q2")
    assert tuple(item.question_id for item in result.paper_score.question_results) == ("Q1", "Q2")
    assert result.questions[0].verified.evaluated_judgments == q1.judgments
    assert result.questions[1].verified.evaluated_judgments == q2.judgments
    assert result.questions[0].verified.evaluated_judgments[0].concise_rationale == (
        "Q1 rationale must survive verification."
    )
    assert result.questions[1].verified.evaluated_judgments[0].concise_rationale == (
        "Q2 rationale must survive verification."
    )
    assert result.paper_score.final_score.as_decimal() == _sd(10).as_decimal()


@pytest.mark.parametrize(
    ("context", "evidence", "paper", "match"),
    (
        (
            _context(submission_ref="SUB-CONTEXT"),
            _evidence(submission_ref="SUB-EVIDENCE"),
            _paper_authority((_authority("Q1"), _authority("Q2"))),
            "submission_ref",
        ),
        (
            _context(spec_ref=GradingSpecRef(id="GS-CONTEXT", version=1)),
            _evidence(),
            _paper_authority(
                (_authority("Q1"), _authority("Q2")),
                spec_ref=GradingSpecRef(id="GS-PAPER", version=1),
            ),
            "grading_spec_ref",
        ),
    ),
)
def test_s2a_context_01_rejects_context_mismatch_before_question_execution(
    context: GradingExecutionContext,
    evidence: AnswerEvidenceBundle,
    paper: ResolvedPaperScoringAuthority,
    match: str,
) -> None:
    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    poisoned_q1 = _work(
        "Q1",
        q1_authority,
        judgments=_judgments("Q1", evidence_ref="DOES_NOT_EXIST"),
    )
    q2 = _work("Q2", q2_authority)

    with pytest.raises(InvalidGradingExecutionError, match=match):
        execute_grading_from_evaluations(
            context=context,
            evidence=evidence,
            questions=(poisoned_q1, q2),
            paper_authority=paper,
        )


def test_s2a_bind_01_rejects_cross_question_authority_before_b2() -> None:
    q1_expected_authority = _authority("Q1")
    q2_reducer_poison = _authority(
        "Q2",
        levels=(("Q2_ONLY", 5), ("NOT_MET", 0)),
    )
    paper = _paper_authority((q1_expected_authority,))
    context = _context(spec_ref=paper.grading_spec_ref)
    evidence = _evidence(("Q1",))

    work = _work(
        "Q1",
        q2_reducer_poison,
        judgments=_judgments("Q1", selected_level="FULL"),
    )

    verified = verify_evaluated_judgments(
        evidence=evidence,
        question_id="Q1",
        judgments=work.judgments,
    )
    with pytest.raises(UnknownJudgmentPerformanceLevelError):
        reduce_question(q2_reducer_poison, verified.scoring_judgments)

    with pytest.raises(InvalidGradingExecutionError, match="question_id"):
        execute_grading_from_evaluations(
            context=context,
            evidence=evidence,
            questions=(work,),
            paper_authority=paper,
        )


@pytest.mark.parametrize("case", ("missing", "duplicate", "unexpected"))
def test_s2a_set_01_rejects_invalid_raw_work_universe_before_execution(case: str) -> None:
    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    q3_authority = _authority("Q3")
    paper = _paper_authority((q1_authority, q2_authority))
    context = _context(spec_ref=paper.grading_spec_ref)
    evidence = _evidence()

    poisoned_q1 = _work(
        "Q1",
        q1_authority,
        judgments=_judgments("Q1", evidence_ref="DOES_NOT_EXIST"),
    )
    valid_q1 = _work("Q1", q1_authority)
    valid_q2 = _work("Q2", q2_authority)
    unexpected_q3 = _work("Q3", q3_authority)

    if case == "missing":
        questions = (poisoned_q1,)
    elif case == "duplicate":
        # The first duplicate is intentionally poisoned and the second valid.
        # Converting to a dict before duplicate admission can erase the evidence.
        questions = (poisoned_q1, valid_q1, valid_q2)
    else:
        questions = (poisoned_q1, valid_q2, unexpected_q3)

    with pytest.raises(InvalidGradingExecutionError, match="question"):
        execute_grading_from_evaluations(
            context=context,
            evidence=evidence,
            questions=questions,
            paper_authority=paper,
        )


def test_s2a_error_01_s1_verification_failure_propagates_unchanged() -> None:
    authority = _authority("Q1")
    paper = _paper_authority((authority,))
    context = _context(spec_ref=paper.grading_spec_ref)
    evidence = _evidence(("Q1",))
    work = _work(
        "Q1",
        authority,
        judgments=_judgments("Q1", evidence_ref="DOES_NOT_EXIST"),
    )

    expected = _capture_expected_exception(
        lambda: verify_evaluated_judgments(
            evidence=evidence,
            question_id="Q1",
            judgments=work.judgments,
        )
    )
    assert expected[0] is EvidenceVerificationError

    _assert_same_native_failure(
        expected,
        lambda: execute_grading_from_evaluations(
            context=context,
            evidence=evidence,
            questions=(work,),
            paper_authority=paper,
        ),
    )


def test_s2a_error_01_b2_failure_propagates_unchanged() -> None:
    authority = _authority("Q1")
    paper = _paper_authority((authority,))
    context = _context(spec_ref=paper.grading_spec_ref)
    evidence = _evidence(("Q1",))
    work = _work(
        "Q1",
        authority,
        judgments=_judgments("Q1", selected_level="UNKNOWN_LEVEL"),
    )

    verified = verify_evaluated_judgments(
        evidence=evidence,
        question_id="Q1",
        judgments=work.judgments,
    )
    expected = _capture_expected_exception(
        lambda: reduce_question(authority, verified.scoring_judgments)
    )
    assert expected[0] is UnknownJudgmentPerformanceLevelError

    _assert_same_native_failure(
        expected,
        lambda: execute_grading_from_evaluations(
            context=context,
            evidence=evidence,
            questions=(work,),
            paper_authority=paper,
        ),
    )


def test_s2a_error_01_b3_failure_propagates_unchanged() -> None:
    q1_authority = _authority("Q1")
    q2_authority = _authority("Q2")
    wrong_q2_expected = _expected(
        q2_authority,
        rubric_ref=RubricRef(id="R-Q2-WRONG", version=1),
    )
    paper = _paper_authority(
        (q1_authority, q2_authority),
        expected_override=(_expected(q1_authority), wrong_q2_expected),
    )
    context = _context(spec_ref=paper.grading_spec_ref)
    evidence = _evidence()
    q1 = _work("Q1", q1_authority)
    q2 = _work("Q2", q2_authority)

    verified_q1 = verify_evaluated_judgments(
        evidence=evidence,
        question_id="Q1",
        judgments=q1.judgments,
    )
    verified_q2 = verify_evaluated_judgments(
        evidence=evidence,
        question_id="Q2",
        judgments=q2.judgments,
    )
    q1_score = reduce_question(q1_authority, verified_q1.scoring_judgments)
    q2_score = reduce_question(q2_authority, verified_q2.scoring_judgments)
    expected = _capture_expected_exception(
        lambda: aggregate_paper(paper, (q1_score, q2_score))
    )
    assert expected[0] is InvalidPaperAggregationInputError

    _assert_same_native_failure(
        expected,
        lambda: execute_grading_from_evaluations(
            context=context,
            evidence=evidence,
            questions=(q2, q1),
            paper_authority=paper,
        ),
    )
