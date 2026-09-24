from __future__ import annotations

from dataclasses import replace

import pytest

from grading import semantic_evaluator as se
from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.contracts.evidence import EvidenceBlockState
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import QuestionExecutionInput, execute_grading_from_evaluations
from grading.verification.evidence import EvidenceVerificationError
from tests.integration.test_direct_text_semantic_evaluator_hostile import (
    DEFAULT_METADATA,
    _Provider,
    _bundle,
    _context,
    _evaluator,
    _evidence,
    _judgment,
    _question,
    _raw_response,
    _resolved_question_authority,
)
from tests.integration.test_direct_text_semantic_evaluator_red import _paper_authority


def _execute_semantic_result(*, semantic_result, authority, evidence):
    return execute_grading_from_evaluations(
        context=semantic_result.execution_context,
        evidence=evidence,
        questions=(
            QuestionExecutionInput(
                question_id=semantic_result.question_id,
                judgments=semantic_result.judgments,
                authority=authority.scoring_authority,
            ),
        ),
        paper_authority=_paper_authority(),
    )


def _manual_semantic_result(*, evidence_refs: tuple[str, ...], evidence=None):
    authority = _resolved_question_authority()
    evidence = evidence or _evidence()
    context = _context(authority=authority, evidence=evidence)
    judgments = tuple(
        EvaluatedCriterionJudgment(
            criterion_id=criterion_id,
            selected_level="FULL",
            evidence_refs=evidence_refs,
            reason_codes=(),
            concise_rationale=f"manual:{criterion_id}",
            uncertainties=(),
            evaluator_metadata=DEFAULT_METADATA,
        )
        for criterion_id in ("C1", "C2")
    )
    return (
        se.SemanticEvaluationResult(
            evaluation_attempt_id="ATTEMPT-MANUAL-COMPOSITION",
            execution_context=context,
            question_id=authority.question_id,
            judgments=judgments,
        ),
        authority,
        evidence,
    )


def test_real_direct_text_semantic_result_flows_through_s1_b2_b3() -> None:
    authority = _resolved_question_authority()
    evidence = _evidence()
    context = _context(authority=authority, evidence=evidence)

    # Deliberately return provider criteria in reverse order and give them
    # different semantic payloads/levels. The semantic evaluator must canonicalize
    # by criterion ID before S1/B2, never by response position.
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment(
                    "C2",
                    selected_level="NOT_MET",
                    rationale="C2 is not satisfied.",
                    uncertainties=["C2 uncertainty is preserved as rich metadata."],
                ),
                _judgment(
                    "C1",
                    selected_level="FULL",
                    rationale="C1 is satisfied.",
                ),
            ]
        )
    )
    evaluator, _, _ = _evaluator(authority=authority, provider=provider)
    semantic_result = evaluator.evaluate(
        authority=authority,
        evidence=evidence,
        execution_context=context,
        evaluation_attempt_id="ATTEMPT-COMPOSITION-1",
    )

    assert tuple(j.criterion_id for j in semantic_result.judgments) == ("C1", "C2")
    assert tuple(j.selected_level for j in semantic_result.judgments) == (
        "FULL",
        "NOT_MET",
    )
    assert semantic_result.judgments[0].concise_rationale == "C1 is satisfied."
    assert semantic_result.judgments[1].concise_rationale == "C2 is not satisfied."
    assert semantic_result.judgments[1].uncertainties == (
        "C2 uncertainty is preserved as rich metadata.",
    )

    execution_result = _execute_semantic_result(
        semantic_result=semantic_result,
        authority=authority,
        evidence=evidence,
    )

    assert execution_result.context == context
    assert len(execution_result.questions) == 1
    record = execution_result.questions[0]
    assert record.verified.evaluated_judgments == semantic_result.judgments
    assert record.verified.scoring_judgments == (
        CriterionJudgment("C1", "FULL"),
        CriterionJudgment("C2", "NOT_MET"),
    )
    assert record.score.final_score == ScoringDecimal.from_raw("2")
    assert execution_result.paper_score.question_results == (record.score,)
    assert execution_result.paper_score.final_score == ScoringDecimal.from_raw("2")


def test_s1_still_blocks_missing_evidence_even_for_constructible_semantic_result() -> None:
    semantic_result, authority, evidence = _manual_semantic_result(
        evidence_refs=("Q1_DOES_NOT_EXIST",)
    )

    with pytest.raises(EvidenceVerificationError):
        _execute_semantic_result(
            semantic_result=semantic_result,
            authority=authority,
            evidence=evidence,
        )


def test_s1_still_blocks_wrong_question_evidence() -> None:
    base = _evidence()
    q1 = base.questions[0]
    q2_block = replace(q1.blocks[0], block_id="Q2_B1")
    q2 = _question(question_id="Q2", blocks=(q2_block,))
    evidence = _bundle(questions=(q1, q2))
    semantic_result, authority, evidence = _manual_semantic_result(
        evidence_refs=("Q2_B1",),
        evidence=evidence,
    )

    with pytest.raises(EvidenceVerificationError):
        _execute_semantic_result(
            semantic_result=semantic_result,
            authority=authority,
            evidence=evidence,
        )


def test_s1_still_blocks_crossed_out_evidence() -> None:
    base = _evidence()
    crossed_out = replace(
        base.questions[0].blocks[0],
        state=EvidenceBlockState.CROSSED_OUT,
    )
    evidence = _bundle(questions=(_question(blocks=(crossed_out,)),))
    semantic_result, authority, evidence = _manual_semantic_result(
        evidence_refs=(crossed_out.block_id,),
        evidence=evidence,
    )

    with pytest.raises(EvidenceVerificationError):
        _execute_semantic_result(
            semantic_result=semantic_result,
            authority=authority,
            evidence=evidence,
        )


def test_s1_still_blocks_empty_evidence_refs() -> None:
    semantic_result, authority, evidence = _manual_semantic_result(evidence_refs=())

    with pytest.raises(EvidenceVerificationError):
        _execute_semantic_result(
            semantic_result=semantic_result,
            authority=authority,
            evidence=evidence,
        )


def test_b2_still_rejects_unknown_level_from_constructible_semantic_result() -> None:
    authority = _resolved_question_authority()
    evidence = _evidence()
    context = _context(authority=authority, evidence=evidence)
    bad = (
        EvaluatedCriterionJudgment(
            criterion_id="C1",
            selected_level="NOT_A_LEVEL",
            evidence_refs=("Q1_B1",),
            reason_codes=(),
            concise_rationale="manual:C1",
            uncertainties=(),
            evaluator_metadata=DEFAULT_METADATA,
        ),
        EvaluatedCriterionJudgment(
            criterion_id="C2",
            selected_level="FULL",
            evidence_refs=("Q1_B1",),
            reason_codes=(),
            concise_rationale="manual:C2",
            uncertainties=(),
            evaluator_metadata=DEFAULT_METADATA,
        ),
    )
    semantic_result = se.SemanticEvaluationResult(
        evaluation_attempt_id="ATTEMPT-MANUAL-BAD-LEVEL",
        execution_context=context,
        question_id=authority.question_id,
        judgments=bad,
    )

    from grading.contracts.errors import UnknownJudgmentPerformanceLevelError

    with pytest.raises(UnknownJudgmentPerformanceLevelError):
        _execute_semantic_result(
            semantic_result=semantic_result,
            authority=authority,
            evidence=evidence,
        )


def test_b2_still_rejects_missing_criterion_from_constructible_semantic_result() -> None:
    authority = _resolved_question_authority()
    evidence = _evidence()
    context = _context(authority=authority, evidence=evidence)
    semantic_result = se.SemanticEvaluationResult(
        evaluation_attempt_id="ATTEMPT-MANUAL-MISSING-CRITERION",
        execution_context=context,
        question_id=authority.question_id,
        judgments=(
            EvaluatedCriterionJudgment(
                criterion_id="C1",
                selected_level="FULL",
                evidence_refs=("Q1_B1",),
                reason_codes=(),
                concise_rationale="manual:C1",
                uncertainties=(),
                evaluator_metadata=DEFAULT_METADATA,
            ),
        ),
    )

    from grading.contracts.errors import MissingJudgmentError

    with pytest.raises(MissingJudgmentError):
        _execute_semantic_result(
            semantic_result=semantic_result,
            authority=authority,
            evidence=evidence,
        )
