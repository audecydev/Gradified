from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import importlib
import inspect
import json
import sys
from types import ModuleType

import pytest

from grading.active_question_authority import (
    ContextPolicy,
    ResolvedQuestionAuthority,
    resolve_active_question_authority,
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
from grading.integration import evaluation_binding, evidence_ingress
from grading.integration.evaluation_binding import (
    BoundQuestionEvaluationInputs,
    QuestionEvaluationBindingError,
    bind_question_evaluation_inputs,
)
from grading.integration.evidence_ingress import (
    AdmittedNormalizedEvidence,
    NormalizedEvidenceAdmissionPolicy,
    NormalizedEvidenceMalformedPayloadError,
    parse_normalized_evidence_payload,
)
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


MODULE_NAME = "grading.integration.question_evaluation_preparation"
FUNCTION_NAME = "prepare_question_evaluation_inputs"


class _UnexpectedP0aFailure(RuntimeError):
    pass


class _UnexpectedP0bFailure(RuntimeError):
    pass


def _api() -> ModuleType:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME:
            pytest.fail(
                "Normalized evidence-to-question preparation "
                "is absent; expected grading.integration.question_evaluation_preparation",
                pytrace=False,
            )
        raise


def _fresh_api() -> ModuleType:
    sys.modules.pop(MODULE_NAME, None)
    return _api()


def _policy(
    *,
    admission_policy_identity: str = "batch1-red-p0a-policy-v1",
    **overrides: int,
) -> NormalizedEvidenceAdmissionPolicy:
    values: dict[str, object] = {
        "admission_policy_identity": admission_policy_identity,
        "max_raw_bytes": 100_000,
        "max_json_depth": 32,
        "max_json_nodes": 10_000,
        "max_json_number_characters": 128,
        "max_identifier_characters": 256,
        "max_metadata_text_characters": 2_048,
        "max_block_content_characters": 8_192,
        "max_total_content_characters": 65_536,
        "max_questions": 100,
        "max_blocks_per_question": 200,
        "max_total_blocks": 5_000,
        "max_warnings_per_question": 100,
        "max_location_coordinates": 16,
    }
    values.update(overrides)
    return NormalizedEvidenceAdmissionPolicy(**values)  # type: ignore[arg-type]


def _wire_block(
    *,
    block_id: str,
    content: str = "Student answer.",
    state: str = "ACTIVE",
) -> dict[str, object]:
    return {
        "block_id": block_id,
        "type": "TEXT",
        "content": content,
        "language": "en",
        "confidence": None,
        "confidence_status": "UNAVAILABLE",
        "state": state,
        "page": 1,
        "location": {"status": "UNAVAILABLE", "bbox": None},
        "reading_order": 1,
        "asset_ref": None,
    }


def _wire_question(
    question_id: str,
    *,
    with_block: bool = True,
    content: str = "Student answer.",
    answer_scope_ref: str | None = None,
) -> dict[str, object]:
    return {
        "question_id": question_id,
        "answer_scope_ref": answer_scope_ref or f"scope-{question_id}",
        "blocks": (
            [_wire_block(block_id=f"{question_id}-B1", content=content)]
            if with_block
            else []
        ),
        "warnings": [],
    }


def _raw_payload(
    *,
    submission_ref: str = "SUB-BATCH1-1",
    questions: tuple[dict[str, object], ...] | None = None,
    ocr_provenance: str = "ocr-batch1-red-1",
) -> bytes:
    effective_questions = (
        (_wire_question("Q1"),) if questions is None else questions
    )
    return json.dumps(
        {
            "schema_version": "1",
            "submission_ref": submission_ref,
            "ocr_provenance": ocr_provenance,
            "questions": list(effective_questions),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _active_rubric(
    *,
    question_id: str = "Q1",
    rubric_id: str = "R-Q1",
    policy_id: str = "P-Q1",
) -> RubricAuthoringVersion:
    content = replace(
        simple_content(),
        rubric_id=rubric_id,
        policy_id=policy_id,
    )
    draft = create_initial_version(simple_basis(question_id=question_id), content)
    validated = validate_version(draft, limits=authoring_test_limits())
    approved = approve_version(validated, teacher_ref="teacher-batch1-red-v1")
    return activate_version(approved, limits=authoring_test_limits())


def _expected_question(
    question_id: str = "Q1",
    *,
    rubric_id: str = "R-Q1",
    policy_id: str = "P-Q1",
) -> ExpectedQuestionResult:
    return ExpectedQuestionResult(
        question_id=question_id,
        rubric_ref=RubricRef(id=rubric_id, version=1),
        scoring_policy_ref=ScoringPolicyRef(
            id=policy_id,
            version=1,
            scoring_semantics_version=SCORING_SEMANTICS_V1,
        ),
    )


def _paper_authority(
    *,
    question_id: str = "Q1",
    spec_id: str = "SPEC-BATCH1",
) -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id=spec_id, version=1),
        expected_questions=(_expected_question(question_id),),
        minimum_score=ScoringDecimal.from_raw("0"),
        maximum_score=ScoringDecimal.from_raw("5"),
    )


@dataclass(frozen=True, slots=True)
class _Selection:
    grading_spec_ref: object
    question_id: object
    question_text: object
    context_policy: object
    active_rubric: object


class _Source:
    def __init__(self, selection: _Selection) -> None:
        self._selection = selection

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        del grading_spec_ref, question_id
        return self._selection


def _question_authority(
    paper: ResolvedPaperScoringAuthority,
    *,
    question_id: str = "Q1",
    question_text: str = "Explain the result.",
) -> ResolvedQuestionAuthority:
    active = _active_rubric(question_id=question_id)
    return resolve_active_question_authority(
        paper_authority=paper,
        question_id=question_id,
        source=_Source(
            _Selection(
                grading_spec_ref=paper.grading_spec_ref,
                question_id=question_id,
                question_text=question_text,
                context_policy=ContextPolicy.DIRECT,
                active_rubric=active,
            )
        ),
    )


def _roots(
    *,
    submission_ref: str = "SUB-BATCH1-1",
    context_submission_ref: str | None = None,
    question_text: str = "Explain the result.",
) -> tuple[
    GradingExecutionContext,
    ResolvedPaperScoringAuthority,
    ResolvedQuestionAuthority,
]:
    paper = _paper_authority()
    question = _question_authority(
        paper,
        question_text=question_text,
    )
    context = GradingExecutionContext(
        grading_run_id="RUN-BATCH1-1",
        submission_ref=(
            submission_ref
            if context_submission_ref is None
            else context_submission_ref
        ),
        exam_ref="EXAM-BATCH1-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    return context, paper, question


def _prepare(
    api: ModuleType,
    *,
    raw_payload: bytes | object | None = None,
    admission_policy: NormalizedEvidenceAdmissionPolicy | None = None,
    context: GradingExecutionContext | None = None,
    paper_authority: ResolvedPaperScoringAuthority | None = None,
    question_authority: ResolvedQuestionAuthority | None = None,
    source_artifact_ref: str | None = "artifact://batch1-red/scan-1",
):
    if context is None or paper_authority is None or question_authority is None:
        default_context, default_paper, default_question = _roots()
        context = default_context if context is None else context
        paper_authority = default_paper if paper_authority is None else paper_authority
        question_authority = (
            default_question if question_authority is None else question_authority
        )
    return api.prepare_question_evaluation_inputs(
        raw_payload=_raw_payload() if raw_payload is None else raw_payload,
        admission_policy=_policy() if admission_policy is None else admission_policy,
        context=context,
        paper_authority=paper_authority,
        question_authority=question_authority,
        source_artifact_ref=source_artifact_ref,
    )


def _direct_p0a_p0b(
    *,
    raw_payload: bytes | None = None,
    source_artifact_ref: str | None = "artifact://batch1-red/scan-1",
):
    context, paper, question = _roots()
    raw = _raw_payload() if raw_payload is None else raw_payload
    policy = _policy()
    admitted = parse_normalized_evidence_payload(
        raw_payload=raw,
        policy=policy,
        source_artifact_ref=source_artifact_ref,
    )
    bound = bind_question_evaluation_inputs(
        context=context,
        admitted_evidence=admitted,
        paper_authority=paper,
        question_authority=question,
    )
    return raw, policy, context, admitted, paper, question, bound


# ---------------------------------------------------------------------------
# Frozen prerequisite witnesses. These must stay GREEN before the new seam.
# ---------------------------------------------------------------------------


def test_prerequisite_real_p0a_and_p0b_already_compose_manually() -> None:
    raw, policy, context, admitted, paper, question, bound = _direct_p0a_p0b()
    assert type(admitted) is AdmittedNormalizedEvidence
    assert type(bound) is BoundQuestionEvaluationInputs
    assert bound.context is context
    assert bound.admitted_evidence is admitted
    assert bound.paper_authority is paper
    assert bound.question_authority is question
    assert admitted.raw_payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert admitted.effective_policy_snapshot == policy


def test_prerequisite_p0a_source_artifact_ref_is_existing_opaque_provenance() -> None:
    source_ref = "artifact://batch1-red/source-17"
    _, _, _, admitted, _, _, _ = _direct_p0a_p0b(
        source_artifact_ref=source_ref
    )
    assert admitted.source_artifact_ref == source_ref
    assert not hasattr(admitted, "artifact_authenticated")
    assert not hasattr(admitted, "source_trusted")


def test_prerequisite_p0b_expected_rejection_keeps_ambient_context_private() -> None:
    raw = _raw_payload()
    policy = _policy()
    _, paper, question = _roots()
    admitted = parse_normalized_evidence_payload(
        raw_payload=raw,
        policy=policy,
    )
    bad_context = GradingExecutionContext(
        grading_run_id="RUN-BATCH1-AMBIENT",
        submission_ref="SUB-DIFFERENT",
        exam_ref="EXAM-BATCH1-1",
        grading_spec_ref=paper.grading_spec_ref,
    )

    try:
        raise RuntimeError("ambient prerequisite failure")
    except RuntimeError:
        with pytest.raises(QuestionEvaluationBindingError) as captured:
            bind_question_evaluation_inputs(
                context=bad_context,
                admitted_evidence=admitted,
                paper_authority=paper,
                question_authority=question,
            )

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


# ---------------------------------------------------------------------------
# evidence and question preparation regression. The prior implementation failed because the
# production preparation module/surface does not yet exist.
# ---------------------------------------------------------------------------


def test_red_public_surface_is_exact_and_keyword_only() -> None:
    api = _api()
    assert api.__all__ == (FUNCTION_NAME,)
    prepare = getattr(api, FUNCTION_NAME)
    assert callable(prepare)

    signature = inspect.signature(prepare)
    assert tuple(signature.parameters) == (
        "raw_payload",
        "admission_policy",
        "context",
        "paper_authority",
        "question_authority",
        "source_artifact_ref",
    )
    for name in (
        "raw_payload",
        "admission_policy",
        "context",
        "paper_authority",
        "question_authority",
        "source_artifact_ref",
    ):
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["raw_payload"].default is inspect.Parameter.empty
    assert signature.parameters["admission_policy"].default is inspect.Parameter.empty
    assert signature.parameters["context"].default is inspect.Parameter.empty
    assert signature.parameters["paper_authority"].default is inspect.Parameter.empty
    assert signature.parameters["question_authority"].default is inspect.Parameter.empty
    assert signature.parameters["source_artifact_ref"].default is None


def test_red_real_valid_wire_flows_through_real_p0a_then_real_p0b() -> None:
    api = _api()
    raw = _raw_payload()
    policy = _policy()
    context, paper, question = _roots()
    source_ref = "artifact://batch1-red/real-wire"

    bound = api.prepare_question_evaluation_inputs(
        raw_payload=raw,
        admission_policy=policy,
        context=context,
        paper_authority=paper,
        question_authority=question,
        source_artifact_ref=source_ref,
    )

    assert type(bound) is BoundQuestionEvaluationInputs
    assert bound.context is context
    assert bound.paper_authority is paper
    assert bound.question_authority is question
    assert type(bound.admitted_evidence) is AdmittedNormalizedEvidence
    assert bound.admitted_evidence.evidence.submission_ref == context.submission_ref
    assert bound.admitted_evidence.raw_payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert bound.admitted_evidence.admission_policy_identity == policy.admission_policy_identity
    assert bound.admitted_evidence.effective_policy_snapshot == policy
    assert bound.admitted_evidence.source_artifact_ref == source_ref


def test_red_bound_result_keeps_provenance_only_under_canonical_admitted_root() -> None:
    bound = _prepare(_api())
    for forbidden_peer in (
        "evidence",
        "answer_evidence_bundle",
        "raw_payload_sha256",
        "wire_schema_version",
        "admission_policy_identity",
        "effective_policy_snapshot",
        "source_artifact_ref",
    ):
        assert not hasattr(bound, forbidden_peer)
    assert bound.admitted_evidence.raw_payload_sha256


def test_red_missing_source_artifact_ref_remains_none_not_fabricated() -> None:
    bound = _prepare(_api(), source_artifact_ref=None)
    assert bound.admitted_evidence.source_artifact_ref is None


def test_red_exact_raw_bytes_are_not_coerced_before_real_p0a() -> None:
    api = _api()
    with pytest.raises(TypeError, match="raw_payload must be exact bytes"):
        _prepare(api, raw_payload=bytearray(_raw_payload()))


def test_red_exact_orchestration_order_and_root_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _raw_payload()
    policy = _policy()
    context, paper, question = _roots()
    admitted = parse_normalized_evidence_payload(
        raw_payload=raw,
        policy=policy,
        source_artifact_ref="artifact://batch1-red/spy",
    )
    returned = object()
    events: list[tuple[str, object]] = []

    def fake_parse(*, raw_payload, policy, source_artifact_ref=None):
        events.append(("p0a", raw_payload))
        assert type(raw_payload) is bytes
        assert raw_payload == raw
        assert policy is policy_object
        assert type(source_artifact_ref) is str
        assert source_artifact_ref == source_ref
        return admitted

    def fake_bind(*, context, admitted_evidence, paper_authority, question_authority):
        events.append(("p0b", admitted_evidence))
        assert context is context_object
        assert admitted_evidence is admitted
        assert paper_authority is paper_object
        assert question_authority is question_object
        return returned

    policy_object = policy
    context_object = context
    paper_object = paper
    question_object = question
    source_ref = "artifact://batch1-red/spy"

    with monkeypatch.context() as patcher:
        patcher.setattr(
            evidence_ingress,
            "parse_normalized_evidence_payload",
            fake_parse,
        )
        patcher.setattr(
            evaluation_binding,
            "bind_question_evaluation_inputs",
            fake_bind,
        )
        api = _fresh_api()
        result = api.prepare_question_evaluation_inputs(
            raw_payload=raw,
            admission_policy=policy,
            context=context,
            paper_authority=paper,
            question_authority=question,
            source_artifact_ref=source_ref,
        )

    sys.modules.pop(MODULE_NAME, None)
    assert result is returned
    assert events == [("p0a", raw), ("p0b", admitted)]


def test_red_real_expected_p0a_rejection_short_circuits_p0b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_called = False

    def forbidden_bind(**kwargs):
        del kwargs
        nonlocal bind_called
        bind_called = True
        raise AssertionError("question evidence binding must not run after normalized evidence admission rejection")

    with monkeypatch.context() as patcher:
        patcher.setattr(
            evaluation_binding,
            "bind_question_evaluation_inputs",
            forbidden_bind,
        )
        api = _fresh_api()
        with pytest.raises(NormalizedEvidenceMalformedPayloadError):
            _prepare(api, raw_payload=b"{not-json")

    sys.modules.pop(MODULE_NAME, None)
    assert bind_called is False


def test_red_unexpected_p0a_failure_is_not_translated_and_short_circuits_p0b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boom = _UnexpectedP0aFailure("unexpected p0a failure")
    bind_called = False

    def exploding_parse(**kwargs):
        del kwargs
        raise boom

    def forbidden_bind(**kwargs):
        del kwargs
        nonlocal bind_called
        bind_called = True
        raise AssertionError("question evidence binding must not run after unexpected normalized evidence admission failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(
            evidence_ingress,
            "parse_normalized_evidence_payload",
            exploding_parse,
        )
        patcher.setattr(
            evaluation_binding,
            "bind_question_evaluation_inputs",
            forbidden_bind,
        )
        api = _fresh_api()
        with pytest.raises(_UnexpectedP0aFailure) as captured:
            _prepare(api)

    sys.modules.pop(MODULE_NAME, None)
    assert captured.value is boom
    assert bind_called is False


def test_red_real_expected_p0b_rejection_propagates_without_new_translation() -> None:
    api = _api()
    bad_context, paper, question = _roots(
        context_submission_ref="SUB-DIFFERENT"
    )
    with pytest.raises(QuestionEvaluationBindingError) as captured:
        _prepare(
            api,
            context=bad_context,
            paper_authority=paper,
            question_authority=question,
        )
    assert type(captured.value) is QuestionEvaluationBindingError
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_red_unexpected_p0b_failure_is_not_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = parse_normalized_evidence_payload(
        raw_payload=_raw_payload(),
        policy=_policy(),
    )
    boom = _UnexpectedP0bFailure("unexpected p0b failure")

    def fake_parse(**kwargs):
        del kwargs
        return admitted

    def exploding_bind(**kwargs):
        del kwargs
        raise boom

    with monkeypatch.context() as patcher:
        patcher.setattr(
            evidence_ingress,
            "parse_normalized_evidence_payload",
            fake_parse,
        )
        patcher.setattr(
            evaluation_binding,
            "bind_question_evaluation_inputs",
            exploding_bind,
        )
        api = _fresh_api()
        with pytest.raises(_UnexpectedP0bFailure) as captured:
            _prepare(api)

    sys.modules.pop(MODULE_NAME, None)
    assert captured.value is boom


def test_red_ambient_exception_does_not_reintroduce_p0b_exception_context() -> None:
    api = _api()
    bad_context, paper, question = _roots(
        context_submission_ref="SUB-DIFFERENT"
    )

    try:
        raise RuntimeError("synthetic ambient failure")
    except RuntimeError:
        with pytest.raises(QuestionEvaluationBindingError) as captured:
            _prepare(
                api,
                context=bad_context,
                paper_authority=paper,
                question_authority=question,
            )

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_red_unrelated_questions_and_zero_blocks_remain_p0b_semantics() -> None:
    api = _api()
    raw = _raw_payload(
        questions=(
            _wire_question("Q1", with_block=False),
            _wire_question("Q-UNRELATED", content="Other answer."),
        )
    )
    bound = _prepare(api, raw_payload=raw)
    assert tuple(
        question.question_id for question in bound.admitted_evidence.evidence.questions
    ) == ("Q1", "Q-UNRELATED")
    assert bound.admitted_evidence.evidence.questions[0].blocks == ()


def test_red_student_content_formatting_survives_without_batch1_normalization() -> None:
    api = _api()
    exact_content = "  student answer\nwith spacing  "
    raw = _raw_payload(
        questions=(_wire_question("Q1", content=exact_content),)
    )
    bound = _prepare(api, raw_payload=raw)
    assert bound.admitted_evidence.evidence.questions[0].blocks[0].content == exact_content


def test_red_question_text_root_is_forwarded_without_batch1_normalization() -> None:
    api = _api()
    exact_question_text = "  Explain the result.\n  "
    context, paper, question = _roots(question_text=exact_question_text)
    bound = _prepare(
        api,
        context=context,
        paper_authority=paper,
        question_authority=question,
    )
    assert bound.question_authority is question
    assert bound.question_authority.question_text == exact_question_text


def test_red_missing_bound_question_still_rejects_through_real_p0b() -> None:
    api = _api()
    raw = _raw_payload(questions=(_wire_question("Q2"),))
    with pytest.raises(QuestionEvaluationBindingError):
        _prepare(api, raw_payload=raw)


def test_red_repeat_preparation_creates_no_peer_identity_or_semantic_alias() -> None:
    api = _api()
    raw = _raw_payload()
    policy = _policy()
    context, paper, question = _roots()
    first = api.prepare_question_evaluation_inputs(
        raw_payload=raw,
        admission_policy=policy,
        context=context,
        paper_authority=paper,
        question_authority=question,
    )
    second = api.prepare_question_evaluation_inputs(
        raw_payload=raw,
        admission_policy=policy,
        context=context,
        paper_authority=paper,
        question_authority=question,
    )

    assert first.context is second.context is context
    assert first.paper_authority is second.paper_authority is paper
    assert first.question_authority is second.question_authority is question
    assert first.admitted_evidence is not second.admitted_evidence
    assert first.admitted_evidence.raw_payload_sha256 == second.admitted_evidence.raw_payload_sha256
    assert first.admitted_evidence.evidence == second.admitted_evidence.evidence
    assert not hasattr(first, "evaluation_attempt_id")
    assert not hasattr(first, "candidate_grade_result")
