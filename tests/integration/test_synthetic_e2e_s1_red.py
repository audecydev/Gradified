from __future__ import annotations

from dataclasses import fields, is_dataclass
import importlib
import importlib.util
import inspect

import pytest

from grading.contracts.judgment import CriterionJudgment
from grading.contracts.result import QuestionScoreResult
from grading.rubric.lifecycle import (
    activate_version,
    approve_version,
    create_initial_version,
    get_active_scoring_authority,
    validate_version,
)
from grading.scoring.reducer import reduce_question
from tests.support.rubric_authoring import authoring_test_limits, simple_basis, simple_content


EVIDENCE_MODULE = "grading.contracts.evidence"
EVALUATION_MODULE = "grading.contracts.evaluation"
VERIFIER_MODULE = "grading.verification.evidence"


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def _require_modules():
    missing = [
        name
        for name in (EVIDENCE_MODULE, EVALUATION_MODULE, VERIFIER_MODULE)
        if not _module_exists(name)
    ]
    if missing:
        pytest.skip("Synthetic vertical prerequisite modules are missing: " + ", ".join(missing))
    return (
        importlib.import_module(EVIDENCE_MODULE),
        importlib.import_module(EVALUATION_MODULE),
        importlib.import_module(VERIFIER_MODULE),
    )


def _active_authority():
    basis = simple_basis(max_marks=5)
    content = simple_content()
    limits = authoring_test_limits()
    draft = create_initial_version(basis, content)
    validated = validate_version(draft, limits=limits)
    approved = approve_version(validated, teacher_ref="teacher:synthetic")
    active = activate_version(approved, limits=limits)
    return get_active_scoring_authority(active)


def _synthetic_evidence(evidence_module, *, crossed_out: bool = False, question_id: str = "Q1"):
    location = evidence_module.EvidenceLocation(
        status=evidence_module.EvidenceLocationStatus.UNAVAILABLE,
        bbox=None,
    )
    block_state = (
        evidence_module.EvidenceBlockState.CROSSED_OUT
        if crossed_out
        else evidence_module.EvidenceBlockState.ACTIVE
    )
    blocks = (
        evidence_module.EvidenceBlock(
            block_id=f"{question_id}_B1",
            type=evidence_module.EvidenceBlockType.TEXT,
            content="Criterion C1 is fully satisfied.",
            language="en",
            confidence=None,
            confidence_status=evidence_module.EvidenceConfidenceStatus.UNAVAILABLE,
            state=block_state,
            page=1,
            location=location,
            reading_order=1,
            asset_ref=None,
        ),
        evidence_module.EvidenceBlock(
            block_id=f"{question_id}_B2",
            type=evidence_module.EvidenceBlockType.TEXT,
            content="Criterion C2 is fully satisfied.",
            language="en",
            confidence=None,
            confidence_status=evidence_module.EvidenceConfidenceStatus.UNAVAILABLE,
            state=evidence_module.EvidenceBlockState.ACTIVE,
            page=1,
            location=location,
            reading_order=2,
            asset_ref=None,
        ),
    )
    question = evidence_module.QuestionEvidence(
        question_id=question_id,
        answer_scope_ref=f"{question_id}_SCOPE",
        blocks=blocks,
        warnings=(),
    )
    return evidence_module.AnswerEvidenceBundle(
        schema_version="1",
        submission_ref="submission-synthetic-1",
        ocr_provenance="synthetic-ocr:v1",
        questions=(question,),
    )


def _evaluated_judgments(
    evaluation_module,
    *,
    first_ref: str = "Q1_B1",
    second_ref: str = "Q1_B2",
):
    metadata = evaluation_module.EvaluatorMetadata(
        evaluator_id="fake-evaluator",
        version="1",
    )
    return (
        evaluation_module.EvaluatedCriterionJudgment(
            criterion_id="C1",
            selected_level="FULL",
            evidence_refs=(first_ref,),
            reason_codes=(),
            concise_rationale="Synthetic fixture supports C1.",
            uncertainties=(),
            evaluator_metadata=metadata,
        ),
        evaluation_module.EvaluatedCriterionJudgment(
            criterion_id="C2",
            selected_level="FULL",
            evidence_refs=(second_ref,),
            reason_codes=(),
            concise_rationale="Synthetic fixture supports C2.",
            uncertainties=(),
            evaluator_metadata=metadata,
        ),
    )


def test_evidence_contract_module_exists_for_synthetic_grading_vertical() -> None:
    assert _module_exists(EVIDENCE_MODULE)


def test_evaluation_contract_module_exists_without_reopening_frozen_scoring_judgment() -> None:
    assert _module_exists(EVALUATION_MODULE)
    assert {field.name for field in fields(CriterionJudgment)} == {
        "criterion_id",
        "selected_level",
    }


def test_evidence_verifier_module_exists_for_synthetic_grading_vertical() -> None:
    assert _module_exists(VERIFIER_MODULE)


def test_answer_evidence_bundle_rejects_duplicate_block_ids_across_questions() -> None:
    if not _module_exists(EVIDENCE_MODULE):
        pytest.skip("Evidence contract prerequisite module is missing: " + EVIDENCE_MODULE)

    evidence = importlib.import_module(EVIDENCE_MODULE)
    location = evidence.EvidenceLocation(
        status=evidence.EvidenceLocationStatus.UNAVAILABLE,
        bbox=None,
    )

    def _shared_block(*, content: str, reading_order: int):
        return evidence.EvidenceBlock(
            block_id="SHARED_B1",
            type=evidence.EvidenceBlockType.TEXT,
            content=content,
            language="en",
            confidence=None,
            confidence_status=evidence.EvidenceConfidenceStatus.UNAVAILABLE,
            state=evidence.EvidenceBlockState.ACTIVE,
            page=1,
            location=location,
            reading_order=reading_order,
            asset_ref=None,
        )

    q1 = evidence.QuestionEvidence(
        question_id="Q1",
        answer_scope_ref="Q1_SCOPE",
        blocks=(_shared_block(content="Evidence owned by Q1.", reading_order=1),),
        warnings=(),
    )
    q2 = evidence.QuestionEvidence(
        question_id="Q2",
        answer_scope_ref="Q2_SCOPE",
        blocks=(_shared_block(content="Different evidence owned by Q2.", reading_order=2),),
        warnings=(),
    )

    with pytest.raises(ValueError):
        evidence.AnswerEvidenceBundle(
            schema_version="1",
            submission_ref="submission-duplicate-evidence-id",
            ocr_provenance="synthetic-ocr:v1",
            questions=(q1, q2),
        )


def test_normalized_evidence_contract_has_required_release1_surface() -> None:
    evidence, _, _ = _require_modules()

    for name in (
        "EvidenceBlockType",
        "EvidenceConfidenceStatus",
        "EvidenceBlockState",
        "EvidenceLocationStatus",
        "EvidenceLocation",
        "EvidenceBlock",
        "QuestionEvidence",
        "AnswerEvidenceBundle",
    ):
        assert hasattr(evidence, name), name

    assert {member.value for member in evidence.EvidenceBlockType} == {
        "TEXT", "MATH", "TABLE", "FIGURE", "CODE", "OTHER"
    }
    assert {member.value for member in evidence.EvidenceConfidenceStatus} == {
        "PRESENT", "UNAVAILABLE"
    }
    assert {member.value for member in evidence.EvidenceBlockState} == {
        "ACTIVE", "CROSSED_OUT", "UNCERTAIN"
    }
    assert {member.value for member in evidence.EvidenceLocationStatus} == {
        "PRESENT", "PARTIAL", "UNAVAILABLE"
    }

    assert {field.name for field in fields(evidence.AnswerEvidenceBundle)} == {
        "schema_version", "submission_ref", "ocr_provenance", "questions"
    }
    assert {field.name for field in fields(evidence.QuestionEvidence)} == {
        "question_id", "answer_scope_ref", "blocks", "warnings"
    }
    assert {field.name for field in fields(evidence.EvidenceBlock)} == {
        "block_id",
        "type",
        "content",
        "language",
        "confidence",
        "confidence_status",
        "state",
        "page",
        "location",
        "reading_order",
        "asset_ref",
    }


def test_evaluator_judgment_envelope_is_non_numeric_and_projects_to_frozen_judgment() -> None:
    _, evaluation, verifier = _require_modules()

    assert hasattr(evaluation, "EvaluatorMetadata")
    assert hasattr(evaluation, "EvaluatedCriterionJudgment")
    assert hasattr(verifier, "EvidenceVerificationError")
    assert hasattr(verifier, "VerifiedCriterionJudgments")
    assert hasattr(verifier, "verify_evaluated_judgments")
    assert is_dataclass(verifier.VerifiedCriterionJudgments)
    assert is_dataclass(evaluation.EvaluatorMetadata)
    assert is_dataclass(evaluation.EvaluatedCriterionJudgment)
    assert {field.name for field in fields(evaluation.EvaluatorMetadata)} == {
        "evaluator_id", "version"
    }
    judgment_fields = {field.name for field in fields(evaluation.EvaluatedCriterionJudgment)}
    assert judgment_fields == {
        "criterion_id",
        "selected_level",
        "evidence_refs",
        "reason_codes",
        "concise_rationale",
        "uncertainties",
        "evaluator_metadata",
    }
    forbidden_score_fields = {
        "score", "marks", "awarded_marks", "total", "final_score", "maximum_score"
    }
    assert judgment_fields.isdisjoint(forbidden_score_fields)

    assert {field.name for field in fields(verifier.VerifiedCriterionJudgments)} == {
        "submission_ref",
        "question_id",
        "evaluated_judgments",
        "scoring_judgments",
    }

    signature = inspect.signature(verifier.verify_evaluated_judgments)
    assert set(signature.parameters) == {"evidence", "question_id", "judgments"}
    for parameter in signature.parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_synthetic_evidence_to_verified_judgment_to_reducer_vertical_produces_real_score() -> None:
    evidence, evaluation, verifier = _require_modules()
    authority = _active_authority()
    bundle = _synthetic_evidence(evidence)
    evaluated = _evaluated_judgments(evaluation)

    verified = verifier.verify_evaluated_judgments(
        evidence=bundle,
        question_id="Q1",
        judgments=evaluated,
    )

    assert type(verified) is verifier.VerifiedCriterionJudgments
    assert verified.submission_ref == bundle.submission_ref
    assert verified.question_id == "Q1"
    assert verified.evaluated_judgments == evaluated
    assert type(verified.scoring_judgments) is tuple
    assert all(type(item) is CriterionJudgment for item in verified.scoring_judgments)
    assert verified.scoring_judgments == (
        CriterionJudgment("C1", "FULL"),
        CriterionJudgment("C2", "FULL"),
    )

    result = reduce_question(authority, verified.scoring_judgments)
    assert type(result) is QuestionScoreResult
    assert result.question_id == "Q1"
    assert result.final_score.to_canonical_string() == "5"
    assert result.maximum_score.to_canonical_string() == "5"


def test_hallucinated_evidence_reference_fails_before_reducer_projection() -> None:
    evidence, evaluation, verifier = _require_modules()
    bundle = _synthetic_evidence(evidence)
    evaluated = _evaluated_judgments(evaluation, first_ref="Q1_DOES_NOT_EXIST")

    with pytest.raises(verifier.EvidenceVerificationError):
        verifier.verify_evaluated_judgments(
            evidence=bundle,
            question_id="Q1",
            judgments=evaluated,
        )


def test_crossed_out_evidence_cannot_support_active_criterion_judgment() -> None:
    evidence, evaluation, verifier = _require_modules()
    bundle = _synthetic_evidence(evidence, crossed_out=True)
    evaluated = _evaluated_judgments(evaluation)

    with pytest.raises(verifier.EvidenceVerificationError):
        verifier.verify_evaluated_judgments(
            evidence=bundle,
            question_id="Q1",
            judgments=evaluated,
        )


def test_wrong_question_evidence_mapping_fails_closed() -> None:
    evidence, evaluation, verifier = _require_modules()
    bundle = _synthetic_evidence(evidence, question_id="Q2")
    evaluated = _evaluated_judgments(
        evaluation,
        first_ref="Q2_B1",
        second_ref="Q2_B2",
    )

    with pytest.raises(verifier.EvidenceVerificationError):
        verifier.verify_evaluated_judgments(
            evidence=bundle,
            question_id="Q1",
            judgments=evaluated,
        )

def test_localizable_judgment_without_evidence_refs_fails_before_projection() -> None:
    evidence, evaluation, verifier = _require_modules()
    bundle = _synthetic_evidence(evidence)
    metadata = evaluation.EvaluatorMetadata(
        evaluator_id="fake-evaluator",
        version="1",
    )
    evaluated = (
        evaluation.EvaluatedCriterionJudgment(
            criterion_id="C1",
            selected_level="FULL",
            evidence_refs=(),
            reason_codes=(),
            concise_rationale="The localized synthetic evidence supports C1.",
            uncertainties=(),
            evaluator_metadata=metadata,
        ),
    )

    with pytest.raises(verifier.EvidenceVerificationError):
        verifier.verify_evaluated_judgments(
            evidence=bundle,
            question_id="Q1",
            judgments=evaluated,
        )
