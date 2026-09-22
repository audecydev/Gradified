from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

from grading.choice_evaluator import evaluate_single_select_choice
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.choice import (
    CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
    CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
    CHOICE_MATCH_RATIONALE,
    CHOICE_MATCH_REASON_CODE,
    CHOICE_MISMATCH_RATIONALE,
    CHOICE_MISMATCH_REASON_CODE,
    DETERMINISTIC_CHOICE_EVALUATOR_ID,
    DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    CanonicalChoiceSelection,
    ChoiceCriterionProjection,
    ChoiceEvaluationAuthority,
    InvalidCanonicalChoiceSelectionError,
    InvalidChoiceEvaluationAuthorityError,
    ChoiceProjectionScoringMismatchError,
    ChoiceScoringAuthorityBindingError,
    ChoiceSelectionBindingError,
    UnsupportedChoiceInputError,
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
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.rubric.fingerprint import compiled_authority_fingerprint
from grading.rubric.lifecycle import (
    activate_version,
    approve_version,
    create_initial_version,
    get_active_scoring_authority,
    validate_version,
)
from grading.scoring.reducer import reduce_question
from grading.verification.evidence import EvidenceVerificationError, verify_evaluated_judgments
from tests._rubric_authoring_support import authoring_test_limits, simple_basis, simple_content


def _active_authority() -> QuestionScoringAuthority:
    basis = simple_basis(max_marks=5)
    content = simple_content()
    limits = authoring_test_limits()
    draft = create_initial_version(basis, content)
    validated = validate_version(draft, limits=limits)
    approved = approve_version(validated, teacher_ref="teacher:choice-red")
    active = activate_version(approved, limits=limits)
    return get_active_scoring_authority(active)


def _authority(
    scoring_authority: QuestionScoringAuthority,
    *,
    question_id: str = "Q1",
    compiled_hash: str | None = None,
    match_projection: tuple[ChoiceCriterionProjection, ...] | None = None,
    mismatch_projection: tuple[ChoiceCriterionProjection, ...] | None = None,
) -> ChoiceEvaluationAuthority:
    return ChoiceEvaluationAuthority(
        schema_version=CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
        grading_spec_ref=GradingSpecRef(id="SPEC-1", version=1),
        question_id=question_id,
        compiled_authority_hash=(
            compiled_hash
            if compiled_hash is not None
            else compiled_authority_fingerprint(scoring_authority)
        ),
        option_ids=("OPT-A", "OPT-B", "OPT-C"),
        official_option_id="OPT-B",
        match_projection=(
            match_projection
            if match_projection is not None
            else (
                ChoiceCriterionProjection("C1", "FULL"),
                ChoiceCriterionProjection("C2", "FULL"),
            )
        ),
        mismatch_projection=(
            mismatch_projection
            if mismatch_projection is not None
            else (
                ChoiceCriterionProjection("C1", "NOT_MET"),
                ChoiceCriterionProjection("C2", "NOT_MET"),
            )
        ),
    )


def _selection(
    *,
    selected_option_id: str = "OPT-B",
    question_id: str = "Q1",
    evidence_refs: tuple[str, ...] = ("Q1_B1",),
) -> CanonicalChoiceSelection:
    return CanonicalChoiceSelection(
        schema_version=CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
        submission_ref="submission-choice-1",
        question_id=question_id,
        selected_option_id=selected_option_id,
        evidence_refs=evidence_refs,
    )


def _evidence(*, block_id: str = "Q1_B1", crossed_out: bool = False) -> AnswerEvidenceBundle:
    block = EvidenceBlock(
        block_id=block_id,
        type=EvidenceBlockType.TEXT,
        content="Canonical selection OPT-B",
        language="en",
        confidence=None,
        confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
        state=(EvidenceBlockState.CROSSED_OUT if crossed_out else EvidenceBlockState.ACTIVE),
        page=1,
        location=EvidenceLocation(status=EvidenceLocationStatus.UNAVAILABLE, bbox=None),
        reading_order=1,
        asset_ref=None,
    )
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref="submission-choice-1",
        ocr_provenance="synthetic-choice-red:v1",
        questions=(
            QuestionEvidence(
                question_id="Q1",
                answer_scope_ref="Q1_SCOPE",
                blocks=(block,),
                warnings=(),
            ),
        ),
    )


def _expected_judgments(*, matched: bool, evidence_refs: tuple[str, ...] = ("Q1_B1",)):
    level = "FULL" if matched else "NOT_MET"
    code = CHOICE_MATCH_REASON_CODE if matched else CHOICE_MISMATCH_REASON_CODE
    rationale = CHOICE_MATCH_RATIONALE if matched else CHOICE_MISMATCH_RATIONALE
    metadata = EvaluatorMetadata(
        evaluator_id=DETERMINISTIC_CHOICE_EVALUATOR_ID,
        version=DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    )
    return (
        EvaluatedCriterionJudgment(
            criterion_id="C1",
            selected_level=level,
            evidence_refs=evidence_refs,
            reason_codes=(code,),
            concise_rationale=rationale,
            uncertainties=(),
            evaluator_metadata=metadata,
        ),
        EvaluatedCriterionJudgment(
            criterion_id="C2",
            selected_level=level,
            evidence_refs=evidence_refs,
            reason_codes=(code,),
            concise_rationale=rationale,
            uncertainties=(),
            evaluator_metadata=metadata,
        ),
    )


def test_choice_evaluator_public_boundary_is_keyword_only_and_narrow() -> None:
    signature = inspect.signature(evaluate_single_select_choice)
    assert tuple(signature.parameters) == ("authority", "selection", "scoring_authority")
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )


def test_known_correct_selection_emits_exact_match_projection_as_rich_judgments() -> None:
    scoring = _active_authority()
    result = evaluate_single_select_choice(
        authority=_authority(scoring),
        selection=_selection(selected_option_id="OPT-B"),
        scoring_authority=scoring,
    )
    assert result == _expected_judgments(matched=True)
    assert all(type(item) is EvaluatedCriterionJudgment for item in result)


def test_known_wrong_admitted_selection_emits_exact_mismatch_projection() -> None:
    scoring = _active_authority()
    result = evaluate_single_select_choice(
        authority=_authority(scoring),
        selection=_selection(selected_option_id="OPT-A"),
        scoring_authority=scoring,
    )
    assert result == _expected_judgments(matched=False)


def test_known_wrong_and_unknown_option_have_distinct_observable_outcomes() -> None:
    scoring = _active_authority()
    authority = _authority(scoring)

    wrong = evaluate_single_select_choice(
        authority=authority,
        selection=_selection(selected_option_id="OPT-A"),
        scoring_authority=scoring,
    )
    assert wrong == _expected_judgments(matched=False)

    with pytest.raises(UnsupportedChoiceInputError):
        evaluate_single_select_choice(
            authority=authority,
            selection=_selection(selected_option_id="OPT-UNKNOWN"),
            scoring_authority=scoring,
        )


def test_selection_question_mismatch_raises_binding_error_before_option_support_check() -> None:
    scoring = _active_authority()
    with pytest.raises(ChoiceSelectionBindingError):
        evaluate_single_select_choice(
            authority=_authority(scoring),
            selection=_selection(question_id="Q2", selected_option_id="OPT-UNKNOWN"),
            scoring_authority=scoring,
        )


def test_scoring_authority_question_mismatch_raises_binding_error() -> None:
    scoring = _active_authority()
    scoring_q2 = QuestionScoringAuthority(
        rubric=replace(scoring.rubric, question_id="Q2"),
        policy=replace(scoring.policy, question_id="Q2"),
    )
    with pytest.raises(ChoiceScoringAuthorityBindingError):
        evaluate_single_select_choice(
            authority=_authority(scoring),
            selection=_selection(),
            scoring_authority=scoring_q2,
        )


def test_compiled_authority_hash_mismatch_raises_scoring_binding_error() -> None:
    scoring = _active_authority()
    with pytest.raises(ChoiceScoringAuthorityBindingError):
        evaluate_single_select_choice(
            authority=_authority(scoring, compiled_hash="0" * 64),
            selection=_selection(),
            scoring_authority=scoring,
        )


def test_projection_criterion_universe_or_order_mismatch_raises_projection_error() -> None:
    scoring = _active_authority()
    projection = (
        ChoiceCriterionProjection("C2", "FULL"),
        ChoiceCriterionProjection("C1", "FULL"),
    )
    mismatch = (
        ChoiceCriterionProjection("C2", "NOT_MET"),
        ChoiceCriterionProjection("C1", "NOT_MET"),
    )
    with pytest.raises(ChoiceProjectionScoringMismatchError):
        evaluate_single_select_choice(
            authority=_authority(
                scoring,
                match_projection=projection,
                mismatch_projection=mismatch,
            ),
            selection=_selection(),
            scoring_authority=scoring,
        )


def test_projection_unknown_level_raises_projection_error() -> None:
    scoring = _active_authority()
    match = (
        ChoiceCriterionProjection("C1", "DOES_NOT_EXIST"),
        ChoiceCriterionProjection("C2", "FULL"),
    )
    mismatch = (
        ChoiceCriterionProjection("C1", "NOT_MET"),
        ChoiceCriterionProjection("C2", "NOT_MET"),
    )
    with pytest.raises(ChoiceProjectionScoringMismatchError):
        evaluate_single_select_choice(
            authority=_authority(
                scoring,
                match_projection=match,
                mismatch_projection=mismatch,
            ),
            selection=_selection(),
            scoring_authority=scoring,
        )


def test_scoring_binding_failure_precedes_projection_compatibility_failure() -> None:
    scoring = _active_authority()
    scoring_q2 = QuestionScoringAuthority(
        rubric=replace(scoring.rubric, question_id="Q2"),
        policy=replace(scoring.policy, question_id="Q2"),
    )
    bad_projection = (
        ChoiceCriterionProjection("C2", "FULL"),
        ChoiceCriterionProjection("C1", "FULL"),
    )
    bad_mismatch = (
        ChoiceCriterionProjection("C2", "NOT_MET"),
        ChoiceCriterionProjection("C1", "NOT_MET"),
    )
    with pytest.raises(ChoiceScoringAuthorityBindingError):
        evaluate_single_select_choice(
            authority=_authority(
                scoring,
                match_projection=bad_projection,
                mismatch_projection=bad_mismatch,
            ),
            selection=_selection(),
            scoring_authority=scoring_q2,
        )


def test_output_is_deterministic_and_inputs_remain_unchanged() -> None:
    scoring = _active_authority()
    authority = _authority(scoring)
    selection = _selection(evidence_refs=("Q1_B1", "Q1_B2"))
    authority_before = authority
    selection_before = selection
    scoring_before = scoring

    first = evaluate_single_select_choice(
        authority=authority,
        selection=selection,
        scoring_authority=scoring,
    )
    second = evaluate_single_select_choice(
        authority=authority,
        selection=selection,
        scoring_authority=scoring,
    )

    assert first == second
    assert authority == authority_before
    assert selection == selection_before
    assert scoring == scoring_before
    assert first == _expected_judgments(matched=True, evidence_refs=("Q1_B1", "Q1_B2"))


def test_real_s1_then_b2_vertical_accepts_choice_judgments_and_scores() -> None:
    scoring = _active_authority()
    judgments = evaluate_single_select_choice(
        authority=_authority(scoring),
        selection=_selection(),
        scoring_authority=scoring,
    )

    verified = verify_evaluated_judgments(
        evidence=_evidence(),
        question_id="Q1",
        judgments=judgments,
    )
    result = reduce_question(scoring, verified.scoring_judgments)

    assert result.question_id == "Q1"
    assert result.final_score.to_canonical_string() == "5"
    assert result.maximum_score.to_canonical_string() == "5"


def test_choice_does_not_preverify_hallucinated_evidence_refs_but_real_s1_rejects_them() -> None:
    scoring = _active_authority()
    judgments = evaluate_single_select_choice(
        authority=_authority(scoring),
        selection=_selection(evidence_refs=("Q1_DOES_NOT_EXIST",)),
        scoring_authority=scoring,
    )

    with pytest.raises(EvidenceVerificationError):
        verify_evaluated_judgments(
            evidence=_evidence(),
            question_id="Q1",
            judgments=judgments,
        )



def test_wrong_authority_type_is_rejected_as_choice_authority_failure() -> None:
    scoring = _active_authority()
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        evaluate_single_select_choice(
            authority=object(),  # type: ignore[arg-type]
            selection=_selection(),
            scoring_authority=scoring,
        )


def test_wrong_selection_type_is_rejected_as_canonical_selection_failure() -> None:
    scoring = _active_authority()
    with pytest.raises(InvalidCanonicalChoiceSelectionError):
        evaluate_single_select_choice(
            authority=_authority(scoring),
            selection=object(),  # type: ignore[arg-type]
            scoring_authority=scoring,
        )


def test_wrong_scoring_authority_type_is_rejected_as_scoring_binding_failure() -> None:
    scoring = _active_authority()
    with pytest.raises(ChoiceScoringAuthorityBindingError):
        evaluate_single_select_choice(
            authority=_authority(scoring),
            selection=_selection(),
            scoring_authority=object(),  # type: ignore[arg-type]
        )
