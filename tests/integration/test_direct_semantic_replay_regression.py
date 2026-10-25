from __future__ import annotations

from dataclasses import fields
import importlib
import inspect
import re

import pytest

from grading.semantic_evaluator import (
    DirectTextSemanticCriterion,
    DirectTextSemanticEvidenceBlock,
    DirectTextSemanticLevel,
    DirectTextSemanticRequest,
)


MODULE_NAME = "grading.providers.semantic_replay"
EXPECTED_PUBLIC = {
    "DirectTextSemanticProviderProvenance",
    "DirectTextSemanticReplayFixture",
    "ReplayDirectTextSemanticProvider",
    "DirectTextSemanticProviderReplayError",
    "DirectTextSemanticProviderReplayMissError",
    "direct_text_semantic_request_fingerprint",
}
MISSING_MESSAGE = (
    "Deterministic DIRECT semantic replay provider is absent; "
    "expected grading.providers.semantic_replay"
)


def _require_module():
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME:
            pytest.fail(MISSING_MESSAGE)
        raise


def _request(
    *,
    question_id: str = "Q1",
    question_text: str = "Explain why the result follows.",
    model_answer_text: str = "Because the stated condition implies the result.",
    criteria: tuple[DirectTextSemanticCriterion, ...] | None = None,
    evidence_blocks: tuple[DirectTextSemanticEvidenceBlock, ...] | None = None,
) -> DirectTextSemanticRequest:
    if criteria is None:
        criteria = (
            DirectTextSemanticCriterion(
                criterion_id="C1",
                operational_description="States the required implication.",
                evidence_requirement="LOCAL",
                performance_levels=(
                    DirectTextSemanticLevel(
                        level_id="FULL",
                        operational_description="Correct implication.",
                    ),
                    DirectTextSemanticLevel(
                        level_id="NONE",
                        operational_description="Implication absent or wrong.",
                    ),
                ),
                accepted_equivalents=("equivalent wording",),
            ),
        )
    if evidence_blocks is None:
        evidence_blocks = (
            DirectTextSemanticEvidenceBlock(block_id="B1", content="Student answer."),
        )
    return DirectTextSemanticRequest(
        question_id=question_id,
        question_text=question_text,
        model_answer_text=model_answer_text,
        criteria=criteria,
        evidence_blocks=evidence_blocks,
    )


def _provenance(module, provider_id: str = "provider-x", model_id: str = "model-y"):
    return module.DirectTextSemanticProviderProvenance(
        provider_id=provider_id,
        model_id=model_id,
    )


def _fixture(module, request: DirectTextSemanticRequest, raw: bytes = b'{"ok":true}'):
    provenance = _provenance(module)
    return module.DirectTextSemanticReplayFixture(
        request_fingerprint=module.direct_text_semantic_request_fingerprint(request),
        provenance=provenance,
        raw_payload=raw,
    )


def test_prerequisite_direct_text_request_contract_exists() -> None:
    request = _request()
    assert type(request) is DirectTextSemanticRequest
    assert request.question_id == "Q1"
    assert request.criteria[0].criterion_id == "C1"
    assert request.evidence_blocks[0].block_id == "B1"


def test_prerequisite_direct_provider_protocol_remains_raw_bytes_boundary() -> None:
    import grading.semantic_evaluator as semantic

    signature = inspect.signature(semantic.DirectTextSemanticProvider.evaluate)
    assert tuple(signature.parameters) == ("self", "request")
    assert signature.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.return_annotation in (bytes, "bytes")


def test_red_public_surface_is_exact() -> None:
    module = _require_module()
    assert set(module.__all__) == EXPECTED_PUBLIC
    for name in EXPECTED_PUBLIC:
        assert hasattr(module, name)


def test_red_error_hierarchy_is_narrow() -> None:
    module = _require_module()
    assert issubclass(module.DirectTextSemanticProviderReplayError, RuntimeError)
    assert issubclass(
        module.DirectTextSemanticProviderReplayMissError,
        module.DirectTextSemanticProviderReplayError,
    )


def test_red_provenance_shape_and_identity_validation() -> None:
    module = _require_module()
    cls = module.DirectTextSemanticProviderProvenance
    assert tuple(field.name for field in fields(cls)) == ("provider_id", "model_id")
    value = cls(provider_id="provider-x", model_id="model-y")
    assert value.provider_id == "provider-x"
    assert value.model_id == "model-y"
    for kwargs in (
        {"provider_id": "", "model_id": "model-y"},
        {"provider_id": " provider-x", "model_id": "model-y"},
        {"provider_id": "provider-x", "model_id": "model-y "},
        {"provider_id": 1, "model_id": "model-y"},
        {"provider_id": "provider-x", "model_id": None},
    ):
        with pytest.raises((TypeError, ValueError)):
            cls(**kwargs)


def test_red_request_fingerprint_is_lowercase_sha256_deterministic_and_canonical() -> None:
    module = _require_module()
    signature = inspect.signature(module.direct_text_semantic_request_fingerprint)
    assert tuple(signature.parameters) == ("request",)
    request = _request()
    first = module.direct_text_semantic_request_fingerprint(request)
    second = module.direct_text_semantic_request_fingerprint(request)
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert first == "e15d5cd709caa0fc82e837bc188e4eb3ad5c61697b4053d0f502d4d526a7dcb5"


def test_red_request_fingerprint_requires_exact_request_type() -> None:
    module = _require_module()

    class SubRequest(DirectTextSemanticRequest):
        pass

    base = _request()
    sub = SubRequest(
        question_id=base.question_id,
        question_text=base.question_text,
        model_answer_text=base.model_answer_text,
        criteria=base.criteria,
        evidence_blocks=base.evidence_blocks,
    )
    with pytest.raises(TypeError):
        module.direct_text_semantic_request_fingerprint(sub)
    with pytest.raises(TypeError):
        module.direct_text_semantic_request_fingerprint(object())


@pytest.mark.parametrize(
    "mutation",
    [
        "question_id",
        "question_text",
        "model_answer_text",
        "criterion_id",
        "criterion_description",
        "evidence_requirement",
        "level_id",
        "level_description",
        "accepted_equivalents",
        "evidence_block_id",
        "evidence_block_content",
    ],
)
def test_red_every_provider_visible_field_participates_in_fingerprint(mutation: str) -> None:
    module = _require_module()
    base = _request()
    criterion = base.criteria[0]
    levels = criterion.performance_levels
    kwargs = {
        "question_id": base.question_id,
        "question_text": base.question_text,
        "model_answer_text": base.model_answer_text,
        "criteria": base.criteria,
        "evidence_blocks": base.evidence_blocks,
    }

    if mutation == "question_id":
        kwargs["question_id"] = "Q2"
    elif mutation == "question_text":
        kwargs["question_text"] = base.question_text + "!"
    elif mutation == "model_answer_text":
        kwargs["model_answer_text"] = base.model_answer_text + "!"
    elif mutation in {
        "criterion_id",
        "criterion_description",
        "evidence_requirement",
        "accepted_equivalents",
        "level_id",
        "level_description",
    }:
        new_levels = levels
        if mutation == "level_id":
            new_levels = (
                DirectTextSemanticLevel("ALT", levels[0].operational_description),
                levels[1],
            )
        elif mutation == "level_description":
            new_levels = (
                DirectTextSemanticLevel(levels[0].level_id, levels[0].operational_description + "!"),
                levels[1],
            )
        new_criterion = DirectTextSemanticCriterion(
            criterion_id="C2" if mutation == "criterion_id" else criterion.criterion_id,
            operational_description=(
                criterion.operational_description + "!"
                if mutation == "criterion_description"
                else criterion.operational_description
            ),
            evidence_requirement=(
                "MULTI" if mutation == "evidence_requirement" else criterion.evidence_requirement
            ),
            performance_levels=new_levels,
            accepted_equivalents=(
                criterion.accepted_equivalents + ("another equivalent",)
                if mutation == "accepted_equivalents"
                else criterion.accepted_equivalents
            ),
        )
        kwargs["criteria"] = (new_criterion,)
    elif mutation == "evidence_block_id":
        kwargs["evidence_blocks"] = (
            DirectTextSemanticEvidenceBlock("B2", base.evidence_blocks[0].content),
        )
    elif mutation == "evidence_block_content":
        kwargs["evidence_blocks"] = (
            DirectTextSemanticEvidenceBlock(
                base.evidence_blocks[0].block_id,
                base.evidence_blocks[0].content + "!",
            ),
        )

    changed = DirectTextSemanticRequest(**kwargs)
    assert module.direct_text_semantic_request_fingerprint(changed) != module.direct_text_semantic_request_fingerprint(base)


def test_red_order_is_preserved_in_request_fingerprint() -> None:
    module = _require_module()
    c1 = _request().criteria[0]
    c2 = DirectTextSemanticCriterion(
        criterion_id="C2",
        operational_description="Second criterion.",
        evidence_requirement="LOCAL",
        performance_levels=(DirectTextSemanticLevel("FULL", "Full"),),
        accepted_equivalents=(),
    )
    b1 = DirectTextSemanticEvidenceBlock("B1", "one")
    b2 = DirectTextSemanticEvidenceBlock("B2", "two")

    a = _request(criteria=(c1, c2), evidence_blocks=(b1, b2))
    b = _request(criteria=(c2, c1), evidence_blocks=(b1, b2))
    c = _request(criteria=(c1, c2), evidence_blocks=(b2, b1))
    assert module.direct_text_semantic_request_fingerprint(a) != module.direct_text_semantic_request_fingerprint(b)
    assert module.direct_text_semantic_request_fingerprint(a) != module.direct_text_semantic_request_fingerprint(c)


def test_red_provider_provenance_is_separate_from_request_fingerprint() -> None:
    module = _require_module()
    signature = inspect.signature(module.direct_text_semantic_request_fingerprint)
    assert "provenance" not in signature.parameters
    request = _request()
    fingerprint = module.direct_text_semantic_request_fingerprint(request)
    first_fixture = module.DirectTextSemanticReplayFixture(
        request_fingerprint=fingerprint,
        provenance=_provenance(module, "p1", "m1"),
        raw_payload=b"one",
    )
    second_fixture = module.DirectTextSemanticReplayFixture(
        request_fingerprint=fingerprint,
        provenance=_provenance(module, "p2", "m2"),
        raw_payload=b"two",
    )
    assert first_fixture.request_fingerprint == second_fixture.request_fingerprint


def test_red_fixture_shape_and_validation() -> None:
    module = _require_module()
    cls = module.DirectTextSemanticReplayFixture
    assert tuple(field.name for field in fields(cls)) == (
        "request_fingerprint",
        "provenance",
        "raw_payload",
    )
    request = _request()
    provenance = _provenance(module)
    fingerprint = module.direct_text_semantic_request_fingerprint(request)
    fixture = cls(fingerprint, provenance, b"payload")
    assert fixture.request_fingerprint == fingerprint
    assert fixture.provenance is provenance
    assert fixture.raw_payload == b"payload"
    with pytest.raises((TypeError, ValueError)):
        cls("ABC", provenance, b"payload")
    with pytest.raises(TypeError):
        cls(fingerprint, object(), b"payload")
    with pytest.raises(TypeError):
        cls(fingerprint, provenance, bytearray(b"payload"))


def test_red_provider_construction_rejects_malformed_fixture_collection() -> None:
    module = _require_module()
    provenance = _provenance(module)
    fixture = _fixture(module, _request())
    cls = module.ReplayDirectTextSemanticProvider
    with pytest.raises(TypeError):
        cls(provenance=provenance, fixtures=[fixture])
    with pytest.raises(TypeError):
        cls(provenance=provenance, fixtures=(object(),))
    with pytest.raises(TypeError):
        cls(provenance=object(), fixtures=(fixture,))


def test_red_provider_rejects_fixture_provenance_mismatch_and_duplicates() -> None:
    module = _require_module()
    request = _request()
    fixture = _fixture(module, request)
    with pytest.raises(ValueError):
        module.ReplayDirectTextSemanticProvider(
            provenance=_provenance(module, "other", "model-y"),
            fixtures=(fixture,),
        )
    with pytest.raises(ValueError):
        module.ReplayDirectTextSemanticProvider(
            provenance=fixture.provenance,
            fixtures=(fixture, fixture),
        )


def test_red_exact_hit_returns_exact_raw_bytes_and_exact_miss_fails() -> None:
    module = _require_module()
    request = _request()
    raw = b'{"schema_version":"1","judgments":[]}'
    fixture = _fixture(module, request, raw)
    provider = module.ReplayDirectTextSemanticProvider(
        provenance=fixture.provenance,
        fixtures=(fixture,),
    )
    returned = provider.evaluate(request=request)
    assert type(returned) is bytes
    assert returned == raw
    with pytest.raises(module.DirectTextSemanticProviderReplayMissError):
        provider.evaluate(request=_request(question_id="Q2"))


def test_red_no_nearest_or_first_fixture_fallback() -> None:
    module = _require_module()
    first_request = _request(question_id="Q1")
    second_request = _request(question_id="Q2")
    first = _fixture(module, first_request, b"first")
    second = module.DirectTextSemanticReplayFixture(
        request_fingerprint=module.direct_text_semantic_request_fingerprint(second_request),
        provenance=first.provenance,
        raw_payload=b"second",
    )
    provider = module.ReplayDirectTextSemanticProvider(
        provenance=first.provenance,
        fixtures=(first, second),
    )
    with pytest.raises(module.DirectTextSemanticProviderReplayMissError):
        provider.evaluate(request=_request(question_id="Q3"))


def test_red_repeated_calls_are_deterministic_and_stateless() -> None:
    module = _require_module()
    request = _request()
    fixture = _fixture(module, request, b"same")
    provider = module.ReplayDirectTextSemanticProvider(
        provenance=fixture.provenance,
        fixtures=(fixture,),
    )
    before = repr(provider)
    assert provider.evaluate(request=request) == b"same"
    assert provider.evaluate(request=request) == b"same"
    assert repr(provider) == before


def test_red_replay_provider_signature_matches_frozen_provider_shape() -> None:
    module = _require_module()
    signature = inspect.signature(module.ReplayDirectTextSemanticProvider.evaluate)
    assert tuple(signature.parameters) == ("self", "request")
    assert signature.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.return_annotation in (bytes, "bytes")


def test_red_replay_provider_does_not_decode_or_admit_provider_payload() -> None:
    module = _require_module()
    request = _request()
    hostile = b"\xffnot-json\x00"
    fixture = _fixture(module, request, hostile)
    provider = module.ReplayDirectTextSemanticProvider(
        provenance=fixture.provenance,
        fixtures=(fixture,),
    )
    assert provider.evaluate(request=request) == hostile


def test_red_public_contract_contains_no_live_provider_or_execution_authority_surface() -> None:
    module = _require_module()
    forbidden = {
        "timeout",
        "retry",
        "cost",
        "latency",
        "token",
        "health",
        "credential",
        "api_key",
        "endpoint",
        "evaluation_attempt_id",
        "provider_attempt_id",
        "capability_ref",
        "grade",
        "score",
        "review",
        "publish",
    }
    public_names = {name.lower() for name in module.__all__}
    for term in forbidden:
        assert all(term not in name for name in public_names)
