from __future__ import annotations

from dataclasses import dataclass
import json

from grading.active_question_authority import (
    ContextPolicy,
    ResolvedQuestionAuthority,
    resolve_active_question_authority,
)
from grading.contracts.evaluation import EvaluatorMetadata
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
from grading.contracts.policy import SCORING_SEMANTICS_V1
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import GradingExecutionContext
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    activate_version,
    approve_version,
    create_initial_version,
    validate_version,
)
from tests.support.rubric_authoring import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


@dataclass(frozen=True, slots=True)
class _SelectedActiveQuestion:
    grading_spec_ref: GradingSpecRef
    question_id: str
    question_text: str
    context_policy: ContextPolicy
    active_rubric: RubricAuthoringVersion


class _ActiveSpecSourceDouble:
    """Test-local stand-in for an already-admitted ACTIVE-spec source."""

    def __init__(self, selected: _SelectedActiveQuestion) -> None:
        self._selected = selected

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> _SelectedActiveQuestion:
        return self._selected


@dataclass(frozen=True, slots=True)
class _MaterializedModelAnswer:
    """Structural test value; construction does not itself establish authority."""

    grading_spec_ref: GradingSpecRef
    question_id: str
    content: str


class _ModelAnswerSourceDouble:
    """Controlled test representation of an upstream-admitted materialization source."""

    def __init__(self, answer: _MaterializedModelAnswer) -> None:
        self._answer = answer
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_model_answer(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> _MaterializedModelAnswer:
        self.calls.append((grading_spec_ref, question_id))
        return self._answer


class _SemanticProviderDouble:
    """Deterministic provider double; it performs no grading logic."""

    def __init__(self, raw_response: bytes) -> None:
        self._raw_response = raw_response
        self.requests: list[object] = []

    def evaluate(self, *, request: object) -> bytes:
        self.requests.append(request)
        return self._raw_response


def _active_rubric() -> RubricAuthoringVersion:
    limits = authoring_test_limits()
    draft = create_initial_version(simple_basis(), simple_content())
    validated = validate_version(draft, limits=limits)
    approved = approve_version(validated, teacher_ref="teacher:direct-text-red")
    return activate_version(approved, limits=limits)


def _paper_authority() -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id="SPEC-DIRECT-TEXT", version=1),
        expected_questions=(
            ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=RubricRef(id="R-Q1", version=1),
                scoring_policy_ref=ScoringPolicyRef(
                    id="P-Q1",
                    version=1,
                    scoring_semantics_version=SCORING_SEMANTICS_V1,
                ),
            ),
        ),
        minimum_score=ScoringDecimal.from_raw("0"),
        maximum_score=ScoringDecimal.from_raw("5"),
    )


def _resolved_question_authority() -> ResolvedQuestionAuthority:
    paper = _paper_authority()
    selected = _SelectedActiveQuestion(
        grading_spec_ref=paper.grading_spec_ref,
        question_id="Q1",
        question_text="Explain why the sky appears blue during the day.",
        context_policy=ContextPolicy.DIRECT,
        active_rubric=_active_rubric(),
    )
    return resolve_active_question_authority(
        paper_authority=paper,
        question_id="Q1",
        source=_ActiveSpecSourceDouble(selected),
    )


def _evidence() -> AnswerEvidenceBundle:
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref="SUB-DIRECT-TEXT-1",
        ocr_provenance="synthetic-ocr:direct-text-red",
        questions=(
            QuestionEvidence(
                question_id="Q1",
                answer_scope_ref="Q1_SCOPE",
                blocks=(
                    EvidenceBlock(
                        block_id="Q1_B1",
                        type=EvidenceBlockType.TEXT,
                        content=(
                            "Blue light is scattered more strongly by the atmosphere "
                            "than longer wavelengths."
                        ),
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
                    ),
                ),
                warnings=(),
            ),
        ),
    )


def _provider_response() -> bytes:
    # The provider double returns controlled structured output; it does not infer
    # these judgments from the student answer. Semantic quality is out of scope
    # for this causal plumbing RED.
    payload = {
        "schema_version": "1",
        "judgments": [
            {
                "criterion_id": "C1",
                "selected_level": "FULL",
                "evidence_refs": ["Q1_B1"],
                "concise_rationale": "The response provides evidence relevant to C1.",
                "uncertainties": [],
            },
            {
                "criterion_id": "C2",
                "selected_level": "FULL",
                "evidence_refs": ["Q1_B1"],
                "concise_rationale": "The response provides evidence relevant to C2.",
                "uncertainties": [],
            },
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_direct_text_red_missing_semantic_evaluator_boundary() -> None:
    """Causal RED for the first DIRECT text semantic-evaluation boundary.

    All currently-authorized upstream fixtures are constructed before importing
    the missing production semantic-evaluator module. The intended RED is the
    absence of that production boundary, not a broken authority/evidence fixture.
    """

    authority = _resolved_question_authority()
    evidence = _evidence()
    context = GradingExecutionContext(
        grading_run_id="RUN-DIRECT-TEXT-1",
        submission_ref=evidence.submission_ref,
        exam_ref="EXAM-DIRECT-TEXT-1",
        grading_spec_ref=authority.grading_spec_ref,
    )
    model_answer = _MaterializedModelAnswer(
        grading_spec_ref=authority.grading_spec_ref,
        question_id=authority.question_id,
        content=(
            "Shorter visible wavelengths are scattered more strongly by the "
            "atmosphere, so scattered daylight appears blue."
        ),
    )
    model_answer_source = _ModelAnswerSourceDouble(model_answer)
    provider = _SemanticProviderDouble(_provider_response())

    # Prove the real pre-existing fixtures are coherent before crossing the new
    # boundary. These are deliberately not claims of backend authentication.
    assert authority.context_policy is ContextPolicy.DIRECT
    assert authority.question_id == "Q1"
    assert tuple(
        criterion.criterion_id
        for criterion in authority.scoring_authority.rubric.criteria
    ) == ("C1", "C2")
    assert context.grading_spec_ref == authority.grading_spec_ref
    assert context.submission_ref == evidence.submission_ref
    assert evidence.questions[0].blocks[0].state is EvidenceBlockState.ACTIVE
    assert evidence.questions[0].blocks[0].type is EvidenceBlockType.TEXT

    # Import inside the test so RED is one failed test node, not collection
    # failure. The current repository should fail here specifically because the
    # production semantic-evaluator boundary does not yet exist.
    from grading import semantic_evaluator

    limits = semantic_evaluator.DirectTextSemanticLimits(
        max_model_answer_characters=2_000,
        max_evidence_blocks=10,
        max_evidence_characters=10_000,
        max_total_request_characters=20_000,
        max_raw_response_bytes=20_000,
        max_json_depth=10,
        max_json_nodes=500,
        max_evidence_refs_per_judgment=10,
        max_rationale_characters=1_000,
        max_uncertainties_per_judgment=10,
        max_uncertainty_characters=1_000,
    )
    evaluator_metadata = EvaluatorMetadata(
        evaluator_id="direct-text-semantic",
        version="1",
    )
    evaluator = semantic_evaluator.DirectTextSemanticEvaluator(
        model_answer_source=model_answer_source,
        provider=provider,
        limits=limits,
        evaluator_metadata=evaluator_metadata,
    )

    result = evaluator.evaluate(
        authority=authority,
        evidence=evidence,
        execution_context=context,
        evaluation_attempt_id="ATTEMPT-DIRECT-TEXT-1",
    )

    assert result.evaluation_attempt_id == "ATTEMPT-DIRECT-TEXT-1"
    assert result.execution_context == context
    assert result.question_id == authority.question_id
    assert tuple(judgment.criterion_id for judgment in result.judgments) == (
        "C1",
        "C2",
    )
    assert tuple(judgment.selected_level for judgment in result.judgments) == (
        "FULL",
        "FULL",
    )
    assert all(judgment.evidence_refs == ("Q1_B1",) for judgment in result.judgments)
    assert all(judgment.reason_codes == () for judgment in result.judgments)
    assert all(
        judgment.evaluator_metadata == evaluator_metadata
        for judgment in result.judgments
    )
    assert model_answer_source.calls == [
        (authority.grading_spec_ref, authority.question_id)
    ]
