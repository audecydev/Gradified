from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import inspect
import json

import pytest

from grading import semantic_evaluator as se
from grading.active_question_authority import ContextPolicy
from grading.contracts.evaluation import EvaluatorMetadata
from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlockState,
    EvidenceBlockType,
    QuestionEvidence,
)
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.execution import GradingExecutionContext
from tests.integration.test_direct_text_semantic_evaluator_red import (
    _MaterializedModelAnswer,
    _evidence,
    _provider_response,
    _resolved_question_authority,
)


DEFAULT_LIMITS = se.DirectTextSemanticLimits(
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
DEFAULT_METADATA = EvaluatorMetadata(
    evaluator_id="direct-text-semantic",
    version="1",
)
_UNSET = object()

DEFAULT_MODEL_ANSWER = (
    "Shorter visible wavelengths are scattered more strongly by the atmosphere, "
    "so scattered daylight appears blue."
)


class _ModelAnswerSource:
    def __init__(
        self,
        answer: object | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_model_answer(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        self.calls.append((grading_spec_ref, question_id))
        if self.error is not None:
            raise self.error
        return self.answer


class _Provider:
    def __init__(
        self,
        raw_response: object = _UNSET,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.raw_response = _provider_response() if raw_response is _UNSET else raw_response
        self.error = error
        self.requests: list[object] = []

    def evaluate(self, *, request: object) -> object:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.raw_response


def _context(
    *,
    authority=None,
    evidence=None,
    grading_spec_ref: GradingSpecRef | None = None,
    submission_ref: str | None = None,
) -> GradingExecutionContext:
    authority = authority or _resolved_question_authority()
    evidence = evidence or _evidence()
    return GradingExecutionContext(
        grading_run_id="RUN-DIRECT-TEXT-HOSTILE",
        submission_ref=submission_ref or evidence.submission_ref,
        exam_ref="EXAM-DIRECT-TEXT-HOSTILE",
        grading_spec_ref=grading_spec_ref or authority.grading_spec_ref,
    )


def _answer(
    *,
    authority=None,
    grading_spec_ref: GradingSpecRef | None = None,
    question_id: str | None = None,
    content: object = DEFAULT_MODEL_ANSWER,
) -> _MaterializedModelAnswer:
    authority = authority or _resolved_question_authority()
    return _MaterializedModelAnswer(
        grading_spec_ref=grading_spec_ref or authority.grading_spec_ref,
        question_id=question_id or authority.question_id,
        content=content,  # type: ignore[arg-type]
    )


def _evaluator(
    *,
    authority=None,
    source: _ModelAnswerSource | None = None,
    provider: _Provider | None = None,
    limits: se.DirectTextSemanticLimits = DEFAULT_LIMITS,
    metadata: EvaluatorMetadata = DEFAULT_METADATA,
):
    authority = authority or _resolved_question_authority()
    source = source or _ModelAnswerSource(_answer(authority=authority))
    provider = provider or _Provider()
    return (
        se.DirectTextSemanticEvaluator(
            model_answer_source=source,
            provider=provider,
            limits=limits,
            evaluator_metadata=metadata,
        ),
        source,
        provider,
    )


def _evaluate(
    *,
    authority=None,
    evidence=None,
    context=None,
    source=None,
    provider=None,
    limits=DEFAULT_LIMITS,
    metadata=DEFAULT_METADATA,
    attempt_id: object = "ATTEMPT-DIRECT-TEXT-HOSTILE",
):
    authority = authority or _resolved_question_authority()
    evidence = evidence or _evidence()
    context = context or _context(authority=authority, evidence=evidence)
    evaluator, source, provider = _evaluator(
        authority=authority,
        source=source,
        provider=provider,
        limits=limits,
        metadata=metadata,
    )
    result = evaluator.evaluate(
        authority=authority,
        evidence=evidence,
        execution_context=context,
        evaluation_attempt_id=attempt_id,  # type: ignore[arg-type]
    )
    return result, evaluator, source, provider


def _base_block():
    return _evidence().questions[0].blocks[0]


def _question(*, question_id="Q1", blocks=None, answer_scope_ref=None):
    base = _evidence().questions[0]
    return replace(
        base,
        question_id=question_id,
        answer_scope_ref=answer_scope_ref or f"{question_id}_SCOPE",
        blocks=tuple(blocks if blocks is not None else base.blocks),
    )


def _bundle(*, questions=None, submission_ref="SUB-DIRECT-TEXT-1") -> AnswerEvidenceBundle:
    base = _evidence()
    return replace(
        base,
        submission_ref=submission_ref,
        questions=tuple(questions if questions is not None else base.questions),
    )


def _judgment(
    criterion_id: object,
    selected_level: object = "FULL",
    evidence_refs: object = None,
    rationale: object = None,
    uncertainties: object = None,
    **extra,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "criterion_id": criterion_id,
        "selected_level": selected_level,
        "evidence_refs": ["Q1_B1"] if evidence_refs is None else evidence_refs,
        "concise_rationale": (
            f"rationale:{criterion_id}" if rationale is None else rationale
        ),
        "uncertainties": [] if uncertainties is None else uncertainties,
    }
    payload.update(extra)
    return payload


def _raw_response(
    *,
    judgments: object = _UNSET,
    schema_version: object = "1",
    extra_top: dict[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "judgments": (
            [_judgment("C1"), _judgment("C2")]
            if judgments is _UNSET
            else judgments
        ),
    }
    if extra_top:
        payload.update(extra_top)
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _assert_no_external_calls(source: _ModelAnswerSource, provider: _Provider) -> None:
    assert source.calls == []
    assert provider.requests == []


def test_h01_evaluate_has_no_per_call_dependency_override_parameters() -> None:
    parameters = tuple(inspect.signature(se.DirectTextSemanticEvaluator.evaluate).parameters)
    assert parameters == (
        "self",
        "authority",
        "evidence",
        "execution_context",
        "evaluation_attempt_id",
    )


def test_h02_evaluator_configuration_is_immutable() -> None:
    evaluator, _, _ = _evaluator()
    with pytest.raises(FrozenInstanceError):
        evaluator._provider = _Provider()  # type: ignore[misc]


@pytest.mark.parametrize(
    "policy",
    [
        ContextPolicy.DIRECT_PLUS_REFERENCE,
        ContextPolicy.HYBRID_RETRIEVAL,
        ContextPolicy.REFERENCE_ONLY,
    ],
)
def test_h03_non_direct_policies_fail_before_external_calls(policy: ContextPolicy) -> None:
    authority = replace(_resolved_question_authority(), context_policy=policy)
    source = _ModelAnswerSource(_answer(authority=authority))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H03",
        )
    _assert_no_external_calls(source, provider)


def test_h04_wrong_execution_spec_fails_before_external_calls() -> None:
    authority = _resolved_question_authority()
    evidence = _evidence()
    source = _ModelAnswerSource(_answer(authority=authority))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    wrong = GradingSpecRef(id="SPEC-OTHER", version=1)
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=authority,
            evidence=evidence,
            execution_context=_context(
                authority=authority,
                evidence=evidence,
                grading_spec_ref=wrong,
            ),
            evaluation_attempt_id="ATTEMPT-H04",
        )
    _assert_no_external_calls(source, provider)


def test_h05_wrong_submission_fails_before_external_calls() -> None:
    authority = _resolved_question_authority()
    evidence = _evidence()
    source = _ModelAnswerSource(_answer(authority=authority))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=authority,
            evidence=evidence,
            execution_context=_context(
                authority=authority,
                evidence=evidence,
                submission_ref="SUB-OTHER",
            ),
            evaluation_attempt_id="ATTEMPT-H05",
        )
    _assert_no_external_calls(source, provider)


@pytest.mark.parametrize("attempt_id", [None, "", " ATTEMPT", "ATTEMPT ", 7])
def test_h06_invalid_attempt_id_fails_before_external_calls(attempt_id: object) -> None:
    authority = _resolved_question_authority()
    source = _ModelAnswerSource(_answer(authority=authority))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id=attempt_id,  # type: ignore[arg-type]
        )
    _assert_no_external_calls(source, provider)


def test_h07_blank_question_text_is_unsupported_before_external_calls() -> None:
    authority = replace(_resolved_question_authority(), question_text=" \t\n")
    source = _ModelAnswerSource(_answer(authority=authority))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H07",
        )
    _assert_no_external_calls(source, provider)


def test_h08_no_matching_evidence_question_is_binding_failure() -> None:
    q2_block = replace(_base_block(), block_id="Q2_B1")
    evidence = _bundle(questions=(_question(question_id="Q2", blocks=(q2_block,)),))
    evaluator, source, provider = _evaluator()
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=evidence,
            execution_context=_context(evidence=evidence),
            evaluation_attempt_id="ATTEMPT-H08",
        )
    _assert_no_external_calls(source, provider)


def test_h09_duplicate_matching_evidence_questions_are_binding_failure() -> None:
    q1a = _question()
    q1b = _question(
        blocks=(replace(_base_block(), block_id="Q1_B2", reading_order=2),),
        answer_scope_ref="Q1_SCOPE_2",
    )
    evidence = _bundle(questions=(q1a, q1b))
    evaluator, source, provider = _evaluator()
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=evidence,
            execution_context=_context(evidence=evidence),
            evaluation_attempt_id="ATTEMPT-H09",
        )
    _assert_no_external_calls(source, provider)


def test_h10_unrelated_evidence_question_is_not_exposed_to_provider() -> None:
    q1 = _question()
    q2 = _question(
        question_id="Q2",
        blocks=(replace(_base_block(), block_id="Q2_SECRET", content="unrelated secret"),),
    )
    evidence = _bundle(questions=(q2, q1))
    result, _, _, provider = _evaluate(evidence=evidence, context=_context(evidence=evidence))
    assert result.question_id == "Q1"
    request = provider.requests[0]
    assert tuple(block.block_id for block in request.evidence_blocks) == ("Q1_B1",)
    assert all("unrelated secret" not in block.content for block in request.evidence_blocks)


@pytest.mark.parametrize(
    "block_type",
    [
        EvidenceBlockType.MATH,
        EvidenceBlockType.TABLE,
        EvidenceBlockType.FIGURE,
        EvidenceBlockType.CODE,
        EvidenceBlockType.OTHER,
    ],
)
def test_h11_active_non_text_evidence_is_unsupported_before_external_calls(
    block_type: EvidenceBlockType,
) -> None:
    block = replace(_base_block(), type=block_type)
    evidence = _bundle(questions=(_question(blocks=(block,)),))
    evaluator, source, provider = _evaluator()
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=evidence,
            execution_context=_context(evidence=evidence),
            evaluation_attempt_id="ATTEMPT-H11",
        )
    _assert_no_external_calls(source, provider)


def test_h12_uncertain_evidence_is_unsupported_before_external_calls() -> None:
    block = replace(_base_block(), state=EvidenceBlockState.UNCERTAIN)
    evidence = _bundle(questions=(_question(blocks=(block,)),))
    evaluator, source, provider = _evaluator()
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=evidence,
            execution_context=_context(evidence=evidence),
            evaluation_attempt_id="ATTEMPT-H12",
        )
    _assert_no_external_calls(source, provider)


def test_h13_whitespace_only_active_text_is_unsupported_before_external_calls() -> None:
    block = replace(_base_block(), content=" \t\n")
    evidence = _bundle(questions=(_question(blocks=(block,)),))
    evaluator, source, provider = _evaluator()
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=evidence,
            execution_context=_context(evidence=evidence),
            evaluation_attempt_id="ATTEMPT-H13",
        )
    _assert_no_external_calls(source, provider)


def test_h14_crossed_out_only_is_unsupported_but_crossed_out_plus_active_proceeds() -> None:
    crossed = replace(
        _base_block(),
        block_id="Q1_CROSS",
        content="crossed out secret",
        state=EvidenceBlockState.CROSSED_OUT,
    )
    crossed_only = _bundle(questions=(_question(blocks=(crossed,)),))
    evaluator, source, provider = _evaluator()
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=crossed_only,
            execution_context=_context(evidence=crossed_only),
            evaluation_attempt_id="ATTEMPT-H14A",
        )
    _assert_no_external_calls(source, provider)

    active = _base_block()
    mixed = _bundle(questions=(_question(blocks=(crossed, active)),))
    result, _, _, mixed_provider = _evaluate(
        evidence=mixed,
        context=_context(evidence=mixed),
        attempt_id="ATTEMPT-H14B",
    )
    assert result.question_id == "Q1"
    request = mixed_provider.requests[0]
    assert tuple(block.block_id for block in request.evidence_blocks) == ("Q1_B1",)
    assert all("crossed out secret" not in block.content for block in request.evidence_blocks)


def test_h15_crossed_out_reference_is_rejected_as_not_provider_visible() -> None:
    crossed = replace(
        _base_block(),
        block_id="Q1_CROSS",
        content="crossed out secret",
        state=EvidenceBlockState.CROSSED_OUT,
    )
    evidence = _bundle(questions=(_question(blocks=(crossed, _base_block())),))
    raw = _raw_response(
        judgments=[
            _judgment("C1", evidence_refs=["Q1_CROSS"]),
            _judgment("C2"),
        ]
    )
    provider = _Provider(raw)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(
            evidence=evidence,
            context=_context(evidence=evidence),
            provider=provider,
            attempt_id="ATTEMPT-H15",
        )


def test_h16_evidence_block_count_limit_is_enforced_before_source_and_provider() -> None:
    blocks = (
        _base_block(),
        replace(_base_block(), block_id="Q1_B2", content="second", reading_order=2),
    )
    evidence = _bundle(questions=(_question(blocks=blocks),))
    limits = replace(DEFAULT_LIMITS, max_evidence_blocks=1)
    evaluator, source, provider = _evaluator(limits=limits)
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=evidence,
            execution_context=_context(evidence=evidence),
            evaluation_attempt_id="ATTEMPT-H16",
        )
    _assert_no_external_calls(source, provider)


def test_h17_evidence_character_limit_is_enforced_before_source_and_provider() -> None:
    limits = replace(DEFAULT_LIMITS, max_evidence_characters=5)
    evaluator, source, provider = _evaluator(limits=limits)
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=_evidence(),
            execution_context=_context(),
            evaluation_attempt_id="ATTEMPT-H17",
        )
    _assert_no_external_calls(source, provider)


def test_h18_pre_materialization_total_request_limit_avoids_source_and_provider() -> None:
    limits = replace(DEFAULT_LIMITS, max_total_request_characters=1)
    evaluator, source, provider = _evaluator(limits=limits)
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=_resolved_question_authority(),
            evidence=_evidence(),
            execution_context=_context(),
            evaluation_attempt_id="ATTEMPT-H18",
        )
    _assert_no_external_calls(source, provider)


@pytest.mark.parametrize(
    "content",
    ["", " \t\n"],
)
def test_h19_blank_model_answer_is_unsupported_before_provider(content: str) -> None:
    authority = _resolved_question_authority()
    source = _ModelAnswerSource(_answer(authority=authority, content=content))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H19",
        )
    assert len(source.calls) == 1
    assert provider.requests == []


def test_h20_oversized_model_answer_is_unsupported_before_provider() -> None:
    authority = _resolved_question_authority()
    limits = replace(DEFAULT_LIMITS, max_model_answer_characters=5)
    source = _ModelAnswerSource(_answer(authority=authority, content="0123456789"))
    provider = _Provider()
    evaluator, _, _ = _evaluator(
        authority=authority, source=source, provider=provider, limits=limits
    )
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H20",
        )
    assert len(source.calls) == 1
    assert provider.requests == []


def test_h21_final_total_request_limit_is_enforced_before_provider() -> None:
    authority = _resolved_question_authority()
    content = "M" * 19_000
    limits = replace(
        DEFAULT_LIMITS,
        max_model_answer_characters=19_500,
        max_total_request_characters=19_354,
    )
    source = _ModelAnswerSource(_answer(authority=authority, content=content))
    provider = _Provider()
    evaluator, _, _ = _evaluator(
        authority=authority, source=source, provider=provider, limits=limits
    )
    with pytest.raises(se.DirectTextSemanticUnsupportedInputError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H21",
        )
    assert len(source.calls) == 1
    assert provider.requests == []


def test_h22_model_answer_wrong_spec_is_binding_failure() -> None:
    authority = _resolved_question_authority()
    source = _ModelAnswerSource(
        _answer(
            authority=authority,
            grading_spec_ref=GradingSpecRef(id="SPEC-WRONG", version=1),
        )
    )
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H22",
        )
    assert len(source.calls) == 1
    assert provider.requests == []


def test_h23_model_answer_wrong_question_is_binding_failure() -> None:
    authority = _resolved_question_authority()
    source = _ModelAnswerSource(_answer(authority=authority, question_id="Q2"))
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticBindingError):
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H23",
        )
    assert len(source.calls) == 1
    assert provider.requests == []


@pytest.mark.parametrize("failure", [TimeoutError("down"), RuntimeError("boom")])
def test_h24_model_answer_source_failures_do_not_escape_raw_dependency_exceptions(
    failure: BaseException,
) -> None:
    authority = _resolved_question_authority()
    source = _ModelAnswerSource(error=failure)
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    with pytest.raises(se.DirectTextSemanticError) as excinfo:
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-H24",
        )
    assert not isinstance(excinfo.value, se.DirectTextSemanticBindingError)
    assert not isinstance(excinfo.value, se.DirectTextSemanticProviderExecutionError)
    assert not isinstance(excinfo.value, se.DirectTextSemanticProviderResponseError)
    assert type(excinfo.value).__name__ == "DirectTextSemanticModelAnswerSourceExecutionError"
    assert excinfo.value.__cause__ is failure
    assert provider.requests == []


def test_h25_provider_execution_failure_is_normalized_and_chained() -> None:
    failure = RuntimeError("provider bug/outage")
    provider = _Provider(error=failure)
    with pytest.raises(se.DirectTextSemanticProviderExecutionError) as excinfo:
        _evaluate(provider=provider, attempt_id="ATTEMPT-H25")
    assert excinfo.value.__cause__ is failure


@pytest.mark.parametrize("raw", ["{}", bytearray(b"{}"), memoryview(b"{}"), None])
def test_h26_provider_must_return_exact_bytes(raw: object) -> None:
    provider = _Provider(raw)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H26")


def test_h27_raw_response_byte_limit_precedes_json_parsing() -> None:
    provider = _Provider(b"{" + b"x" * 100 + b"}")
    limits = replace(DEFAULT_LIMITS, max_raw_response_bytes=50)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, limits=limits, attempt_id="ATTEMPT-H27")


def test_h28_invalid_utf8_is_rejected() -> None:
    provider = _Provider(b"\xff")
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H28")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"1","schema_version":"1","judgments":[]}',
        b'{"schema_version":"1","judgments":[]}{"x":1}',
        b'{"schema_version":"1","judgments":NaN}',
        b'{"schema_version":"1","judgments":Infinity}',
        b'{"schema_version":"1","judgments":-Infinity}',
    ],
)
def test_h29_strict_json_rejects_duplicate_trailing_and_nonstandard_values(raw: bytes) -> None:
    provider = _Provider(raw)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H29")


def test_h30_huge_json_integer_cannot_escape_as_raw_valueerror() -> None:
    raw = (
        b'{"schema_version":"1","judgments":'
        + (b"9" * 5_000)
        + b"}"
    )
    provider = _Provider(raw)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H30")


def test_h31_json_depth_limit_is_enforced() -> None:
    provider = _Provider(_provider_response())
    limits = replace(DEFAULT_LIMITS, max_json_depth=2)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, limits=limits, attempt_id="ATTEMPT-H31")


def test_h32_json_node_limit_is_enforced() -> None:
    provider = _Provider(_provider_response())
    limits = replace(DEFAULT_LIMITS, max_json_nodes=5)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, limits=limits, attempt_id="ATTEMPT-H32")


@pytest.mark.parametrize("raw", [b"[]", b'"x"', b"1", b"true", b"null"])
def test_h33_top_level_response_must_be_object(raw: bytes) -> None:
    provider = _Provider(raw)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H33")


@pytest.mark.parametrize(
    "raw",
    [
        _raw_response(schema_version="2"),
        _raw_response(schema_version="01"),
        _raw_response(schema_version=1),
        json.dumps({"judgments": []}).encode("utf-8"),
    ],
)
def test_h34_response_schema_version_is_exact_and_mandatory(raw: bytes) -> None:
    provider = _Provider(raw)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H34")


def test_h35_top_level_schema_is_closed() -> None:
    provider = _Provider(_raw_response(extra_top={"provider_metadata": {}}))
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H35")


@pytest.mark.parametrize("judgments", [{}, "x", 1, None, True])
def test_h36_judgments_must_be_json_array(judgments: object) -> None:
    provider = _Provider(_raw_response(judgments=judgments))
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H36")


def test_h37_empty_and_missing_criterion_sets_are_rejected() -> None:
    for judgments in ([], [_judgment("C1")]):
        provider = _Provider(_raw_response(judgments=judgments))
        with pytest.raises(se.DirectTextSemanticProviderResponseError):
            _evaluate(provider=provider, attempt_id="ATTEMPT-H37")


def test_h38_unknown_criterion_is_rejected() -> None:
    provider = _Provider(
        _raw_response(judgments=[_judgment("C1"), _judgment("C-UNKNOWN")])
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H38")


def test_h39_duplicate_criterion_is_rejected_before_mapping() -> None:
    provider = _Provider(
        _raw_response(judgments=[_judgment("C1"), _judgment("C1")])
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H39")


def test_h40_shuffled_criteria_preserve_rich_fields_by_criterion_id() -> None:
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment(
                    "C2",
                    rationale="R-C2",
                    uncertainties=["U-C2"],
                ),
                _judgment(
                    "C1",
                    rationale="R-C1",
                    uncertainties=["U-C1"],
                ),
            ]
        )
    )
    result, _, _, _ = _evaluate(provider=provider, attempt_id="ATTEMPT-H40")
    assert tuple(j.criterion_id for j in result.judgments) == ("C1", "C2")
    assert tuple(j.concise_rationale for j in result.judgments) == ("R-C1", "R-C2")
    assert tuple(j.uncertainties for j in result.judgments) == (("U-C1",), ("U-C2",))


def test_h41_unknown_performance_level_is_rejected() -> None:
    provider = _Provider(
        _raw_response(judgments=[_judgment("C1", "BOGUS"), _judgment("C2")])
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H41")


@pytest.mark.parametrize(
    "refs",
    [[], ["Q1_B1", "Q1_B1"], ["Q1_UNKNOWN"], ["Q2_B1"], "Q1_B1", [7]],
)
def test_h42_evidence_refs_must_be_nonempty_unique_visible_string_array(refs: object) -> None:
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1", evidence_refs=refs),
                _judgment("C2"),
            ]
        )
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H42")


def test_h43_evidence_ref_count_limit_is_enforced() -> None:
    second = replace(_base_block(), block_id="Q1_B2", content="second", reading_order=2)
    evidence = _bundle(questions=(_question(blocks=(_base_block(), second)),))
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1", evidence_refs=["Q1_B1", "Q1_B2"]),
                _judgment("C2"),
            ]
        )
    )
    limits = replace(DEFAULT_LIMITS, max_evidence_refs_per_judgment=1)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(
            evidence=evidence,
            context=_context(evidence=evidence),
            provider=provider,
            limits=limits,
            attempt_id="ATTEMPT-H43",
        )


@pytest.mark.parametrize(
    "extra_field",
    [
        "score",
        "marks",
        "total",
        "confidence",
        "evaluator_metadata",
        "evaluation_attempt_id",
        "rubric_text",
        "scoring_policy",
    ],
)
def test_h44_judgment_schema_rejects_scoring_provenance_and_unknown_fields(
    extra_field: str,
) -> None:
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1", **{extra_field: "attacker"}),
                _judgment("C2"),
            ]
        )
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H44")


def test_h45_missing_required_judgment_field_is_rejected() -> None:
    item = _judgment("C1")
    del item["uncertainties"]
    provider = _Provider(_raw_response(judgments=[item, _judgment("C2")]))
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H45")


@pytest.mark.parametrize(
    "field,value",
    [
        ("criterion_id", 1),
        ("selected_level", 1),
        ("concise_rationale", 1),
        ("uncertainties", "none"),
    ],
)
def test_h46_wrong_judgment_field_types_are_rejected(field: str, value: object) -> None:
    item = _judgment("C1")
    item[field] = value
    provider = _Provider(_raw_response(judgments=[item, _judgment("C2")]))
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H46")


def test_h47_rationale_limit_is_enforced() -> None:
    limits = replace(DEFAULT_LIMITS, max_rationale_characters=3)
    provider = _Provider(
        _raw_response(
            judgments=[_judgment("C1", rationale="1234"), _judgment("C2")]
        )
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, limits=limits, attempt_id="ATTEMPT-H47")


@pytest.mark.parametrize(
    "uncertainties",
    [[""], [" \t"], [1]],
)
def test_h48_malformed_uncertainties_are_rejected(uncertainties: object) -> None:
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1", uncertainties=uncertainties),
                _judgment("C2"),
            ]
        )
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H48")


def test_h49_uncertainty_count_and_length_limits_are_enforced() -> None:
    count_limits = replace(DEFAULT_LIMITS, max_uncertainties_per_judgment=1)
    count_provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1", uncertainties=["u1", "u2"]),
                _judgment("C2"),
            ]
        )
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(
            provider=count_provider,
            limits=count_limits,
            attempt_id="ATTEMPT-H49A",
        )

    length_limits = replace(DEFAULT_LIMITS, max_uncertainty_characters=2)
    length_provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1", uncertainties=["long"]),
                _judgment("C2"),
            ]
        )
    )
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(
            provider=length_provider,
            limits=length_limits,
            attempt_id="ATTEMPT-H49B",
        )


@pytest.mark.parametrize("field", ["concise_rationale", "uncertainty"])
def test_h50_decoded_lone_unicode_surrogates_are_rejected(field: str) -> None:
    if field == "concise_rationale":
        item = _judgment("C1", rationale="\ud800")
    else:
        item = _judgment("C1", uncertainties=["\ud800"])
    provider = _Provider(_raw_response(judgments=[item, _judgment("C2")]))
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H50")


def test_h51_request_projection_is_narrow_immutable_and_preserves_evidence_order() -> None:
    b1 = replace(_base_block(), block_id="Q1_B1", content="first", reading_order=20)
    b2 = replace(_base_block(), block_id="Q1_B2", content="second", reading_order=1)
    evidence = _bundle(questions=(_question(blocks=(b1, b2)),))
    raw = _raw_response(
        judgments=[
            _judgment("C1", evidence_refs=["Q1_B1"]),
            _judgment("C2", evidence_refs=["Q1_B2"]),
        ]
    )
    provider = _Provider(raw)
    result, evaluator, source, provider = _evaluate(
        evidence=evidence,
        context=_context(evidence=evidence),
        provider=provider,
        attempt_id="ATTEMPT-H51",
    )
    assert result.question_id == "Q1"
    assert source.calls == [
        (_resolved_question_authority().grading_spec_ref, "Q1")
    ]
    request = provider.requests[0]
    assert tuple(field.name for field in fields(request)) == (
        "question_id",
        "question_text",
        "model_answer_text",
        "criteria",
        "evidence_blocks",
    )
    assert tuple(block.block_id for block in request.evidence_blocks) == ("Q1_B1", "Q1_B2")
    assert tuple(block.content for block in request.evidence_blocks) == ("first", "second")
    assert all(not hasattr(criterion, "contribution") for criterion in request.criteria)
    assert all(
        not hasattr(level, "contribution")
        for criterion in request.criteria
        for level in criterion.performance_levels
    )
    with pytest.raises(FrozenInstanceError):
        request.question_id = "Q2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        evaluator._limits = DEFAULT_LIMITS  # type: ignore[misc]


def test_h52_system_owned_metadata_attempt_and_reason_codes_cannot_be_provider_overridden() -> None:
    provider = _Provider(_provider_response())
    result, _, _, _ = _evaluate(provider=provider, attempt_id="ATTEMPT-SYSTEM-OWNED")
    assert result.evaluation_attempt_id == "ATTEMPT-SYSTEM-OWNED"
    assert all(j.evaluator_metadata == DEFAULT_METADATA for j in result.judgments)
    assert all(j.reason_codes == () for j in result.judgments)


def test_h53_partial_valid_plus_malicious_response_constructs_zero_trusted_judgments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider(
        _raw_response(
            judgments=[
                _judgment("C1"),
                _judgment("C2", evidence_refs=["Q1_UNKNOWN"]),
            ]
        )
    )
    constructed = 0
    original = se.EvaluatedCriterionJudgment

    def spy(*args, **kwargs):
        nonlocal constructed
        constructed += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(se, "EvaluatedCriterionJudgment", spy)
    with pytest.raises(se.DirectTextSemanticProviderResponseError):
        _evaluate(provider=provider, attempt_id="ATTEMPT-H53")
    assert constructed == 0
