from __future__ import annotations

import inspect

import pytest

from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.contracts.numeric_authority import (
    NumericAuthorityApproval,
    NumericBoundAuthorityBinding,
    NumericCriterionProjection,
    NumericNotAuthorizedBinding,
    numeric_authority_fingerprint,
)
from grading.contracts.numeric_evaluation import DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION
from grading.numeric_authority import NumericAuthoritySourceExecutionError
from grading.numeric_evidence import UnsupportedNumericEvidenceError
from grading.numeric_judgments import (
    NUMERIC_CONDITION_NOT_SATISFIED_RATIONALE,
    NUMERIC_CONDITION_NOT_SATISFIED_REASON_CODE,
    NUMERIC_CONDITION_SATISFIED_RATIONALE,
    NUMERIC_CONDITION_SATISFIED_REASON_CODE,
    NumericNotAuthorizedForQuestionError,
    evaluate_numeric_question_to_judgments,
)
from tests.unit.test_numeric_authority_resolution_regression import (
    _AuthoritySource,
    _BindingSource,
    _ExplodingAuthoritySource,
    _Materialized,
    _authority,
    _bound_setup,
    _resolved_active,
)
from tests.unit.test_numeric_evidence_admission_regression import _block, _bundle, _question


def _evaluate(content: str):
    active, authority, _, binding, approval = _bound_setup()
    judgments = evaluate_numeric_question_to_judgments(
        active_authority=active,
        evidence=_bundle(_question(_block(content))),
        binding_source=_BindingSource(binding),
        authority_source=_AuthoritySource(_Materialized(authority, approval)),
    )
    return active, judgments


def test_public_signature_does_not_accept_caller_supplied_n3_result_or_projection() -> None:
    assert tuple(inspect.signature(evaluate_numeric_question_to_judgments).parameters) == (
        "active_authority",
        "evidence",
        "binding_source",
        "authority_source",
    )


def test_satisfied_outcome_uses_exact_approved_projection() -> None:
    _, judgments = _evaluate("5.1")
    assert all(type(judgment) is EvaluatedCriterionJudgment for judgment in judgments)
    assert tuple((j.criterion_id, j.selected_level) for j in judgments) == (
        ("C1", "FULL"),
        ("C2", "FULL"),
    )
    assert all(j.evidence_refs == ("Q1-B1",) for j in judgments)
    assert all(j.reason_codes == (NUMERIC_CONDITION_SATISFIED_REASON_CODE,) for j in judgments)
    assert all(j.concise_rationale == NUMERIC_CONDITION_SATISFIED_RATIONALE for j in judgments)
    assert all(j.uncertainties == () for j in judgments)
    assert all(j.evaluator_metadata.evaluator_id == DETERMINISTIC_NUMERIC_EVALUATOR_ID for j in judgments)
    assert all(j.evaluator_metadata.version == DETERMINISTIC_NUMERIC_EVALUATOR_VERSION for j in judgments)


def test_not_satisfied_outcome_uses_exact_approved_projection() -> None:
    _, judgments = _evaluate("5.3")
    assert tuple((j.criterion_id, j.selected_level) for j in judgments) == (
        ("C1", "NOT_MET"),
        ("C2", "NOT_MET"),
    )
    assert all(j.reason_codes == (NUMERIC_CONDITION_NOT_SATISFIED_REASON_CODE,) for j in judgments)
    assert all(j.concise_rationale == NUMERIC_CONDITION_NOT_SATISFIED_RATIONALE for j in judgments)


def test_explicit_not_authorized_never_becomes_not_satisfied_projection() -> None:
    active = _resolved_active()
    binding_source = _BindingSource(
        NumericNotAuthorizedBinding(active.grading_spec_ref, active.question_id)
    )
    source = _AuthoritySource(object())
    with pytest.raises(NumericNotAuthorizedForQuestionError):
        evaluate_numeric_question_to_judgments(
            active_authority=active,
            evidence=object(),  # type: ignore[arg-type]
            binding_source=binding_source,
            authority_source=source,
        )
    assert source.calls == []


def test_n1_source_failure_propagates_as_n1_failure_not_academic_projection() -> None:
    active, _, _, binding, _ = _bound_setup()
    with pytest.raises(NumericAuthoritySourceExecutionError):
        evaluate_numeric_question_to_judgments(
            active_authority=active,
            evidence=_bundle(_question(_block("5"))),
            binding_source=_BindingSource(binding),
            authority_source=_ExplodingAuthoritySource(),
        )


def test_n2_unsupported_syntax_propagates_without_academic_projection() -> None:
    active, authority, _, binding, approval = _bound_setup()
    with pytest.raises(UnsupportedNumericEvidenceError):
        evaluate_numeric_question_to_judgments(
            active_authority=active,
            evidence=_bundle(_question(_block("5 m"))),
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_projection_is_authority_owned_not_hard_coded_by_n4() -> None:
    c1 = _resolved_active()
    authority = _authority(
        c1,
        satisfied_projection=(
            NumericCriterionProjection("C1", "NOT_MET"),
            NumericCriterionProjection("C2", "FULL"),
        ),
    )
    fingerprint = numeric_authority_fingerprint(authority)
    binding = NumericBoundAuthorityBinding(c1.grading_spec_ref, c1.question_id, "1", fingerprint)
    approval = NumericAuthorityApproval("teacher:n4", fingerprint)
    judgments = evaluate_numeric_question_to_judgments(
        active_authority=c1,
        evidence=_bundle(_question(_block("5"))),
        binding_source=_BindingSource(binding),
        authority_source=_AuthoritySource(_Materialized(authority, approval)),
    )
    assert tuple((j.criterion_id, j.selected_level) for j in judgments) == (
        ("C1", "NOT_MET"),
        ("C2", "FULL"),
    )


def test_n4_does_not_expose_marks_scores_review_or_publication_fields() -> None:
    _, judgments = _evaluate("5")
    for judgment in judgments:
        assert not hasattr(judgment, "marks")
        assert not hasattr(judgment, "awarded_marks")
        assert not hasattr(judgment, "score")
        assert not hasattr(judgment, "review")
        assert not hasattr(judgment, "published")


def test_n4_rejects_n3_provenance_mismatch_even_if_result_shape_is_valid(monkeypatch) -> None:
    import grading.numeric_judgments as nj
    from grading.numeric_evaluator import evaluate_numeric_scalar as real_evaluate

    def forged(*, resolved_authority, observation):
        result = real_evaluate(
            resolved_authority=resolved_authority,
            observation=observation,
        )
        object.__setattr__(result, "evidence_ref", "OTHER-BLOCK")
        return result

    monkeypatch.setattr(nj, "evaluate_numeric_scalar", forged)
    active, authority, _, binding, approval = _bound_setup()
    with pytest.raises(nj.NumericCompositionInvariantError):
        nj.evaluate_numeric_question_to_judgments(
            active_authority=active,
            evidence=_bundle(_question(_block("5"))),
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_n4_rejects_n3_authority_identity_mismatch(monkeypatch) -> None:
    import grading.numeric_judgments as nj
    from grading.numeric_evaluator import evaluate_numeric_scalar as real_evaluate

    def forged(*, resolved_authority, observation):
        result = real_evaluate(
            resolved_authority=resolved_authority,
            observation=observation,
        )
        object.__setattr__(result, "authority_fingerprint", "0" * 64)
        return result

    monkeypatch.setattr(nj, "evaluate_numeric_scalar", forged)
    active, authority, _, binding, approval = _bound_setup()
    with pytest.raises(nj.NumericCompositionInvariantError):
        nj.evaluate_numeric_question_to_judgments(
            active_authority=active,
            evidence=_bundle(_question(_block("5"))),
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_n4_rationale_and_reason_codes_do_not_leak_expected_values_or_tolerances() -> None:
    _, judgments = _evaluate("5.1")
    rendered = " ".join(
        [
            *(code for judgment in judgments for code in judgment.reason_codes),
            *(judgment.concise_rationale for judgment in judgments),
        ]
    )
    assert "5" not in rendered
    assert "0.2" not in rendered
