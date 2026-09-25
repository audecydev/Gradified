from __future__ import annotations

import pytest

from grading.contracts.numeric_authority import (
    NumericAbsoluteToleranceCondition,
    NumericAuthorityApproval,
    NumericBoundAuthorityBinding,
    NumericCriterionProjection,
    NumericEvaluationAuthority,
    numeric_authority_fingerprint,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import GradingExecutionContext, QuestionExecutionInput, execute_grading_from_evaluations
from grading.numeric_judgments import evaluate_numeric_question_to_judgments
from grading.verification.evidence import EvidenceVerificationError
from tests.unit.test_numeric_authority_resolution_red import (
    _AuthoritySource,
    _BindingSource,
    _Materialized,
    _authority,
    _paper,
    _resolved_active,
)
from tests.unit.test_numeric_evidence_admission_red import _block, _bundle, _question


def _setup(*, content: str, authority: NumericEvaluationAuthority | None = None):
    active = _resolved_active()
    authority = authority or _authority(active)
    fingerprint = numeric_authority_fingerprint(authority)
    binding = NumericBoundAuthorityBinding(active.grading_spec_ref, active.question_id, "1", fingerprint)
    approval = NumericAuthorityApproval("teacher:n4", fingerprint)
    evidence = _bundle(_question(_block(content)))
    judgments = evaluate_numeric_question_to_judgments(
        active_authority=active,
        evidence=evidence,
        binding_source=_BindingSource(binding),
        authority_source=_AuthoritySource(_Materialized(authority, approval)),
    )
    context = GradingExecutionContext(
        grading_run_id="RUN-N4-1",
        submission_ref=evidence.submission_ref,
        exam_ref="EXAM-1",
        grading_spec_ref=active.grading_spec_ref,
    )
    return active, evidence, judgments, context


def _execute(*, active, evidence, judgments, context):
    return execute_grading_from_evaluations(
        context=context,
        evidence=evidence,
        questions=(
            QuestionExecutionInput(
                question_id=active.question_id,
                judgments=judgments,
                authority=active.scoring_authority,
            ),
        ),
        paper_authority=_paper(),
    )


def test_satisfied_numeric_path_flows_through_existing_s1_b2_b3_without_new_scoring_logic() -> None:
    active, evidence, judgments, context = _setup(content="5.1")
    result = _execute(active=active, evidence=evidence, judgments=judgments, context=context)
    record = result.questions[0]
    assert record.verified.evaluated_judgments == judgments
    assert tuple((j.criterion_id, j.selected_level) for j in record.verified.scoring_judgments) == (
        ("C1", "FULL"),
        ("C2", "FULL"),
    )
    assert record.score.final_score == ScoringDecimal.from_raw("5")
    assert result.paper_score.final_score == ScoringDecimal.from_raw("5")


def test_not_satisfied_numeric_path_flows_through_existing_s1_b2_b3() -> None:
    active, evidence, judgments, context = _setup(content="6")
    result = _execute(active=active, evidence=evidence, judgments=judgments, context=context)
    assert tuple((j.criterion_id, j.selected_level) for j in result.questions[0].verified.scoring_judgments) == (
        ("C1", "NOT_MET"),
        ("C2", "NOT_MET"),
    )
    assert result.questions[0].score.final_score == ScoringDecimal.from_raw("0")


def test_n4_preserves_custom_teacher_approved_complete_projection_into_existing_reducer() -> None:
    active = _resolved_active()
    authority = _authority(
        active,
        conditions=(NumericAbsoluteToleranceCondition("5", "0.2"),),
        satisfied_projection=(
            NumericCriterionProjection("C1", "NOT_MET"),
            NumericCriterionProjection("C2", "FULL"),
        ),
    )
    active, evidence, judgments, context = _setup(content="5", authority=authority)
    result = _execute(active=active, evidence=evidence, judgments=judgments, context=context)
    assert tuple((j.criterion_id, j.selected_level) for j in result.questions[0].verified.scoring_judgments) == (
        ("C1", "NOT_MET"),
        ("C2", "FULL"),
    )
    assert result.questions[0].score.final_score == ScoringDecimal.from_raw("3")


def test_existing_s1_still_rejects_forged_evidence_reference_after_numeric_composition() -> None:
    active, evidence, judgments, context = _setup(content="5")
    forged = list(judgments)
    object.__setattr__(forged[0], "evidence_refs", ("DOES-NOT-EXIST",))
    with pytest.raises(EvidenceVerificationError):
        _execute(active=active, evidence=evidence, judgments=tuple(forged), context=context)


def test_numeric_path_includes_n2_canonicalization_before_n3_and_scoring() -> None:
    active, evidence, judgments, context = _setup(content="005.1000")
    result = _execute(active=active, evidence=evidence, judgments=judgments, context=context)
    assert result.questions[0].score.final_score == ScoringDecimal.from_raw("5")


def test_existing_b2_still_rejects_forged_numeric_selected_level() -> None:
    from grading.contracts.errors import UnknownJudgmentPerformanceLevelError

    active, evidence, judgments, context = _setup(content="5")
    forged = list(judgments)
    object.__setattr__(forged[0], "selected_level", "NOT-A-LEVEL")
    with pytest.raises(UnknownJudgmentPerformanceLevelError):
        _execute(active=active, evidence=evidence, judgments=tuple(forged), context=context)
