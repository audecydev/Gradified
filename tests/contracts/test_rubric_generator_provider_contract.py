from __future__ import annotations

from dataclasses import fields, is_dataclass
import hashlib
import importlib
import importlib.util
import inspect
import json

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.providers.rubric_ingress import (
    AdmittedRubricProviderProposal,
    RubricProviderIngressLimits,
    RubricProviderMalformedResponseError,
    RubricProviderProvenance,
    RubricProviderSchemaError,
)
from grading.rubric.compiler import CompiledRubricCandidate, compile_rubric_content
from grading.rubric.generator import (
    GeneratedRubricCandidate,
    RubricGenerationInput,
)
from grading.rubric.models import (
    AuthoringRoundingRule,
    FinalizedQuestionScoringBasis,
    RubricCompilationLimits,
)


MODULE_NAME = "grading.providers.rubric_generation"


def sd(value: int | str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def _module_exists() -> bool:
    try:
        return importlib.util.find_spec(MODULE_NAME) is not None
    except ModuleNotFoundError:
        return False


def _provider_module():
    if not _module_exists():
        pytest.skip("RubricGenerator provider abstraction is not implemented yet.")
    return importlib.import_module(MODULE_NAME)


def _require_api(*names: str):
    module = _provider_module()
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail("Missing RubricGenerator provider API: " + ", ".join(missing))
    return module


def _compilation_limits() -> RubricCompilationLimits:
    return RubricCompilationLimits(
        max_criteria=20,
        max_levels_per_criterion=10,
        max_accepted_equivalents_per_criterion=20,
        max_rules=50,
        max_conditions_per_rule=20,
        max_allowed_level_ids_per_condition=10,
        max_text_characters_per_field=2000,
        max_serialized_authority_bytes=100000,
        max_reconciliation_states=1000,
    )


def _ingress_limits() -> RubricProviderIngressLimits:
    return RubricProviderIngressLimits(
        max_raw_bytes=100_000,
        max_json_depth=32,
        max_json_nodes=10_000,
        max_provenance_text_characters=256,
        compilation_limits=_compilation_limits(),
    )


def _provenance(
    *,
    provider_id: str = "replay-provider",
    model_id: str = "fixture-model-v1",
) -> RubricProviderProvenance:
    return RubricProviderProvenance(provider_id=provider_id, model_id=model_id)


def _source(
    *,
    question_id: str = "Q1",
    max_marks: int | str = 5,
    question_text: str = "Explain why 2 + 3 = 5.",
    model_answer_text: str = "Two objects plus three objects make five objects.",
    rubric_id: str = "rubric-Q1",
    policy_id: str = "policy-Q1",
    minimum_score: int | str = 0,
    rounding: AuthoringRoundingRule | None = None,
) -> RubricGenerationInput:
    return RubricGenerationInput(
        finalized_question=FinalizedQuestionScoringBasis(question_id, sd(max_marks)),
        question_text=question_text,
        model_answer_text=model_answer_text,
        rubric_id=rubric_id,
        policy_id=policy_id,
        minimum_score=sd(minimum_score),
        rounding=rounding,
    )


def _criterion_payload() -> dict[str, object]:
    return {
        "criterion_id": "C1",
        "operational_description": "Award credit for the required explanation.",
        "evidence_requirement": "Evidence explains the required relationship.",
        "performance_levels": [
            {
                "level_id": "FULL",
                "operational_description": "Fully met.",
                "contribution": 5,
            },
            {
                "level_id": "NOT_MET",
                "operational_description": "Not met.",
                "contribution": 0,
            },
        ],
        "accepted_equivalents": [],
    }


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1",
        "criteria": [_criterion_payload()],
        "positive_credit_dependencies": [],
        "gates": [],
        "caps": [],
        "deductions": [],
    }
    document.update(overrides)
    return document


def _raw(document: dict[str, object] | None = None) -> bytes:
    if document is None:
        document = _document()
    return json.dumps(
        document,
        ensure_ascii=True,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class _FakeProvider:
    """Test-local provider double; it must cross the real frozen rubric provider ingress ingress."""

    def __init__(
        self,
        *,
        provenance: RubricProviderProvenance,
        raw_payload: object = b"",
        failure: BaseException | None = None,
    ) -> None:
        self.provenance = provenance
        self.raw_payload = raw_payload
        self.failure = failure
        self.calls: list[RubricGenerationInput] = []

    def generate(self, *, source: RubricGenerationInput):
        self.calls.append(source)
        if self.failure is not None:
            raise self.failure
        return self.raw_payload


def _fixture_has_provenance(module) -> bool:
    return "provenance" in {
        field.name for field in fields(module.RubricProviderReplayFixture)
    }


def _require_fixture_provenance(module) -> None:
    if not _fixture_has_provenance(module):
        pytest.skip("Replay fixture provenance binding is not implemented yet.")


def _replay_fixture(
    module,
    source: RubricGenerationInput,
    *,
    raw_payload: bytes | None = None,
    provenance: RubricProviderProvenance | None = None,
):
    if raw_payload is None:
        raw_payload = _raw()
    if provenance is None:
        provenance = _provenance()
    kwargs = {
        "request_fingerprint": module.rubric_provider_request_fingerprint(source),
        "raw_payload": raw_payload,
    }
    if _fixture_has_provenance(module):
        kwargs["provenance"] = provenance
    return module.RubricProviderReplayFixture(**kwargs)


def _replay_provider(
    module,
    source: RubricGenerationInput,
    *,
    raw_payload: bytes | None = None,
    provenance: RubricProviderProvenance | None = None,
):
    if provenance is None:
        provenance = _provenance()
    fixture = _replay_fixture(
        module,
        source,
        raw_payload=raw_payload,
        provenance=provenance,
    )
    return module.ReplayRubricProvider(
        provenance=provenance,
        fixtures=(fixture,),
    )


def test_provider_abstraction_module_exists_at_provider_boundary() -> None:
    assert _module_exists()


def test_provider_public_contract_surfaces_exist_and_errors_are_typed() -> None:
    module = _require_api(
        "RubricGenerationProvider",
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
        "ProviderGeneratedRubricCandidate",
        "RubricProviderError",
        "RubricProviderTimeoutError",
        "RubricProviderUnavailableError",
        "RubricProviderReplayMissError",
        "rubric_provider_request_fingerprint",
        "generate_rubric_with_provider",
    )

    assert issubclass(module.RubricProviderTimeoutError, module.RubricProviderError)
    assert issubclass(module.RubricProviderUnavailableError, module.RubricProviderError)
    assert issubclass(module.RubricProviderReplayMissError, module.RubricProviderError)

    assert {field.name for field in fields(module.RubricProviderReplayFixture)} == {
        "request_fingerprint",
        "provenance",
        "raw_payload",
    }
    assert {field.name for field in fields(module.ProviderGeneratedRubricCandidate)} == {
        "request_fingerprint",
        "provider_profile_version",
        "admitted_proposal",
        "candidate",
    }
    for cls in (
        module.RubricProviderReplayFixture,
        module.ReplayRubricProvider,
        module.ProviderGeneratedRubricCandidate,
    ):
        assert is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_provider_generation_api_requires_explicit_source_provider_and_ingress_limits() -> None:
    module = _require_api("generate_rubric_with_provider")
    signature = inspect.signature(module.generate_rubric_with_provider)
    assert set(signature.parameters) == {"source", "provider", "ingress_limits"}
    for parameter in signature.parameters.values():
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_request_fingerprint_is_stable_and_bound_to_exact_trusted_source_content() -> None:
    module = _require_api("rubric_provider_request_fingerprint")
    source = _source()
    first = module.rubric_provider_request_fingerprint(source)
    second = module.rubric_provider_request_fingerprint(source)

    assert type(first) is str
    assert len(first) == 64
    assert first == second

    variants = (
        _source(question_id="Q2"),
        _source(question_text=" Explain why 2 + 3 = 5."),
        _source(model_answer_text="Two plus three is five."),
        _source(max_marks=6),
        _source(rubric_id="rubric-Q1-v2"),
        _source(policy_id="policy-Q1-v2"),
        _source(minimum_score=1),
        _source(rounding=AuthoringRoundingRule("ROUND", sd("0.5"), "HALF_UP")),
    )
    variant_hashes = {module.rubric_provider_request_fingerprint(value) for value in variants}
    assert first not in variant_hashes
    assert len(variant_hashes) == len(variants)


def test_replay_provider_matches_exact_request_and_returns_exact_raw_bytes() -> None:
    module = _require_api(
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
        "rubric_provider_request_fingerprint",
    )
    source = _source()
    raw_payload = b'{"schema_version":"1","criteria":[],"positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]}'
    provider = _replay_provider(module, source, raw_payload=raw_payload)

    assert provider.provenance == _provenance()
    assert provider.generate(source=source) == raw_payload
    assert provider.generate(source=source) == raw_payload


def test_replay_provider_rejects_missing_or_wrong_request_fixture() -> None:
    module = _require_api("RubricProviderReplayMissError")
    source = _source()
    provider = _replay_provider(module, source)

    with pytest.raises(module.RubricProviderReplayMissError):
        provider.generate(source=_source(question_text="A different finalized question."))


def test_replay_provider_rejects_ambiguous_duplicate_request_fixtures() -> None:
    module = _require_api(
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
        "rubric_provider_request_fingerprint",
    )
    source = _source()
    first = _replay_fixture(module, source, raw_payload=_raw())
    second = _replay_fixture(module, source, raw_payload=b"{}")

    with pytest.raises(ValueError):
        module.ReplayRubricProvider(
            provenance=_provenance(),
            fixtures=(first, second),
        )


def test_replay_fixture_matching_provider_model_provenance_is_accepted() -> None:
    module = _require_api(
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
    )
    _require_fixture_provenance(module)
    source = _source()
    provenance = _provenance(provider_id="provider-A", model_id="model-A1")
    fixture = _replay_fixture(
        module,
        source,
        provenance=provenance,
    )

    provider = module.ReplayRubricProvider(
        provenance=provenance,
        fixtures=(fixture,),
    )

    assert fixture.provenance == provenance
    assert provider.generate(source=source) == fixture.raw_payload


def test_replay_provider_rejects_cross_model_fixture_provenance() -> None:
    module = _require_api(
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
    )
    _require_fixture_provenance(module)
    source = _source()
    fixture = _replay_fixture(
        module,
        source,
        provenance=_provenance(provider_id="provider-A", model_id="model-A1"),
    )

    with pytest.raises(ValueError):
        module.ReplayRubricProvider(
            provenance=_provenance(provider_id="provider-A", model_id="model-A2"),
            fixtures=(fixture,),
        )


def test_replay_provider_rejects_cross_provider_fixture_provenance() -> None:
    module = _require_api(
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
    )
    _require_fixture_provenance(module)
    source = _source()
    fixture = _replay_fixture(
        module,
        source,
        provenance=_provenance(provider_id="provider-A", model_id="model-A1"),
    )

    with pytest.raises(ValueError):
        module.ReplayRubricProvider(
            provenance=_provenance(provider_id="provider-B", model_id="model-B1"),
            fixtures=(fixture,),
        )


def test_replay_provider_checks_provenance_of_every_fixture() -> None:
    module = _require_api(
        "RubricProviderReplayFixture",
        "ReplayRubricProvider",
    )
    _require_fixture_provenance(module)
    provenance = _provenance(provider_id="provider-A", model_id="model-A1")
    fixtures = (
        _replay_fixture(module, _source(question_id="Q1"), provenance=provenance),
        _replay_fixture(
            module,
            _source(question_id="Q2"),
            provenance=_provenance(provider_id="provider-A", model_id="model-A2"),
        ),
        _replay_fixture(module, _source(question_id="Q3"), provenance=provenance),
    )

    with pytest.raises(ValueError):
        module.ReplayRubricProvider(
            provenance=provenance,
            fixtures=fixtures,
        )


def test_structural_fake_provider_flows_through_frozen_g1b_and_g1a() -> None:
    module = _require_api("generate_rubric_with_provider")
    source = _source()
    raw_payload = _raw()
    provider = _FakeProvider(provenance=_provenance(), raw_payload=raw_payload)

    result = module.generate_rubric_with_provider(
        source=source,
        provider=provider,
        ingress_limits=_ingress_limits(),
    )

    assert provider.calls == [source]
    assert type(result.admitted_proposal) is AdmittedRubricProviderProposal
    assert type(result.candidate) is GeneratedRubricCandidate
    assert result.candidate.source == source
    assert result.candidate.proposal == result.admitted_proposal.proposal
    assert result.admitted_proposal.raw_payload_sha256 == hashlib.sha256(raw_payload).hexdigest()


def test_provider_must_return_exact_raw_bytes_not_preparsed_or_mutable_payloads() -> None:
    module = _require_api("generate_rubric_with_provider")
    provider = _FakeProvider(
        provenance=_provenance(),
        raw_payload=bytearray(_raw()),
    )

    with pytest.raises(TypeError):
        module.generate_rubric_with_provider(
            source=_source(),
            provider=provider,
            ingress_limits=_ingress_limits(),
        )


def test_configured_provider_model_provenance_survives_generation_result() -> None:
    module = _require_api("generate_rubric_with_provider")
    provenance = _provenance(provider_id="configured-provider", model_id="configured-model")
    provider = _FakeProvider(provenance=provenance, raw_payload=_raw())

    result = module.generate_rubric_with_provider(
        source=_source(),
        provider=provider,
        ingress_limits=_ingress_limits(),
    )

    assert result.admitted_proposal.provenance == provenance
    assert result.admitted_proposal.provenance.provider_id == "configured-provider"
    assert result.admitted_proposal.provenance.model_id == "configured-model"


def test_provider_timeout_and_unavailable_fail_without_fallback_candidate() -> None:
    module = _require_api(
        "RubricProviderTimeoutError",
        "RubricProviderUnavailableError",
        "generate_rubric_with_provider",
    )

    for failure in (
        module.RubricProviderTimeoutError("timeout"),
        module.RubricProviderUnavailableError("unavailable"),
    ):
        provider = _FakeProvider(provenance=_provenance(), failure=failure)
        with pytest.raises(type(failure)):
            module.generate_rubric_with_provider(
                source=_source(),
                provider=provider,
                ingress_limits=_ingress_limits(),
            )


def test_unexpected_provider_programming_failure_remains_a_technical_failure() -> None:
    module = _require_api("generate_rubric_with_provider")
    provider = _FakeProvider(
        provenance=_provenance(),
        failure=ValueError("injected unexpected provider defect"),
    )

    with pytest.raises(ValueError, match="injected unexpected provider defect"):
        module.generate_rubric_with_provider(
            source=_source(),
            provider=provider,
            ingress_limits=_ingress_limits(),
        )


def test_malformed_provider_bytes_are_rejected_by_frozen_g1b_not_accepted_upstream() -> None:
    module = _require_api("generate_rubric_with_provider")
    provider = _FakeProvider(provenance=_provenance(), raw_payload=b"{not-json")

    with pytest.raises(RubricProviderMalformedResponseError):
        module.generate_rubric_with_provider(
            source=_source(),
            provider=provider,
            ingress_limits=_ingress_limits(),
        )


def test_provider_payload_cannot_inject_trusted_question_marks_or_policy_authority() -> None:
    module = _require_api("generate_rubric_with_provider")
    hostile = _document(
        question_id="Q-EVIL",
        max_marks=999,
        policy_id="provider-policy",
        minimum_score=-100,
    )
    provider = _FakeProvider(provenance=_provenance(), raw_payload=_raw(hostile))

    with pytest.raises(RubricProviderSchemaError):
        module.generate_rubric_with_provider(
            source=_source(),
            provider=provider,
            ingress_limits=_ingress_limits(),
        )


def test_provider_generation_result_preserves_provenance_without_becoming_authority() -> None:
    module = _require_api("ProviderGeneratedRubricCandidate", "generate_rubric_with_provider")
    source = _source()
    result = module.generate_rubric_with_provider(
        source=source,
        provider=_FakeProvider(provenance=_provenance(), raw_payload=_raw()),
        ingress_limits=_ingress_limits(),
    )

    assert type(result) is module.ProviderGeneratedRubricCandidate
    assert result.provider_profile_version == "1"
    assert result.request_fingerprint == module.rubric_provider_request_fingerprint(source)
    assert result.admitted_proposal.provenance == _provenance()
    assert not isinstance(result, CompiledRubricCandidate)
    assert not isinstance(result, QuestionScoringAuthority)
    assert not hasattr(result, "authority")
    assert not hasattr(result, "approval")
    assert not hasattr(result, "activate")


def test_identical_replay_and_trusted_source_produce_identical_g1a_identities() -> None:
    module = _require_api("generate_rubric_with_provider")
    source = _source()
    provider = _replay_provider(module, source)

    first = module.generate_rubric_with_provider(
        source=source,
        provider=provider,
        ingress_limits=_ingress_limits(),
    )
    second = module.generate_rubric_with_provider(
        source=source,
        provider=provider,
        ingress_limits=_ingress_limits(),
    )

    assert first.request_fingerprint == second.request_fingerprint
    assert first.admitted_proposal.raw_payload_sha256 == second.admitted_proposal.raw_payload_sha256
    assert first.candidate.source_fingerprint == second.candidate.source_fingerprint
    assert first.candidate.proposal_fingerprint == second.candidate.proposal_fingerprint
    assert first.candidate.content_fingerprint == second.candidate.content_fingerprint


def test_provider_public_surface_exposes_no_compilation_approval_activation_or_reducer_authority() -> None:
    module = _provider_module()
    forbidden = {
        "QuestionScoringAuthority",
        "CompiledRubricCandidate",
        "compile_rubric_content",
        "approve_version",
        "activate_version",
        "get_active_scoring_authority",
        "reduce_question",
    }

    exported = set(getattr(module, "__all__", ()))
    assert forbidden.isdisjoint(exported)
    for name in forbidden:
        assert not hasattr(module, name), name


def test_synthetic_no_network_vertical_path_reaches_frozen_compiler_as_unapproved_candidate() -> None:
    module = _require_api("generate_rubric_with_provider")
    source = _source(
        question_text="Explain why adding two objects to three objects gives five objects.",
        model_answer_text="Two objects together with three objects form a total of five objects.",
    )
    provider = _replay_provider(module, source)
    ingress_limits = _ingress_limits()

    generated = module.generate_rubric_with_provider(
        source=source,
        provider=provider,
        ingress_limits=ingress_limits,
    )
    compiled = compile_rubric_content(
        generated.candidate.content,
        finalized_question=source.finalized_question,
        version=1,
        limits=ingress_limits.compilation_limits,
    )

    assert type(generated.candidate) is GeneratedRubricCandidate
    assert type(compiled) is CompiledRubricCandidate
    assert compiled.finalized_question == source.finalized_question
    assert compiled.source_content == generated.candidate.content
    assert compiled.source_content_hash == generated.candidate.content_fingerprint
    assert not hasattr(compiled, "authority")
