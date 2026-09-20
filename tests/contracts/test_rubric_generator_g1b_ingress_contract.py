from __future__ import annotations

from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
import hashlib
import importlib
import importlib.util
import inspect
import json

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.compiler import CompiledRubricCandidate
from grading.rubric.generator import GeneratedRubricCandidate, RubricGenerationProposal
from grading.rubric.models import RubricCompilationLimits


MODULE_NAME = "grading.providers.rubric_ingress"


def _module_exists() -> bool:
    try:
        return importlib.util.find_spec(MODULE_NAME) is not None
    except ModuleNotFoundError:
        return False


def _ingress_module():
    if not _module_exists():
        pytest.skip("RubricGenerator G1b provider-ingress module is not implemented yet.")
    return importlib.import_module(MODULE_NAME)


def _require_api(*names: str):
    module = _ingress_module()
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail("Missing RubricGenerator G1b required API: " + ", ".join(missing))
    return module


def _compilation_limits(**overrides) -> RubricCompilationLimits:
    values = {
        "max_criteria": 20,
        "max_levels_per_criterion": 10,
        "max_accepted_equivalents_per_criterion": 20,
        "max_rules": 50,
        "max_conditions_per_rule": 20,
        "max_allowed_level_ids_per_condition": 10,
        "max_text_characters_per_field": 2000,
        "max_serialized_authority_bytes": 100000,
        "max_reconciliation_states": 1000,
    }
    values.update(overrides)
    return RubricCompilationLimits(**values)


def _limits(
    module,
    *,
    raw_bytes: int = 100_000,
    depth: int = 32,
    nodes: int = 10_000,
    provenance_text: int = 256,
    **compilation_overrides,
):
    return module.RubricProviderIngressLimits(
        max_raw_bytes=raw_bytes,
        max_json_depth=depth,
        max_json_nodes=nodes,
        max_provenance_text_characters=provenance_text,
        compilation_limits=_compilation_limits(**compilation_overrides),
    )


def _provenance(module):
    return module.RubricProviderProvenance(
        provider_id="fake-provider",
        model_id="fixture-model-v1",
    )


def _criterion_payload(
    criterion_id: str = "C1",
    *,
    contribution: int | float = 5,
    level_count: int = 2,
    equivalent_count: int = 1,
    text: str = "Award credit for the required method.",
):
    levels = [
        {
            "level_id": "FULL",
            "operational_description": "Fully met.",
            "contribution": contribution,
        },
        {
            "level_id": "NOT_MET",
            "operational_description": "Not met.",
            "contribution": 0,
        },
    ]
    for index in range(2, level_count):
        levels.append(
            {
                "level_id": f"L{index}",
                "operational_description": f"Level {index}.",
                "contribution": 0,
            }
        )
    return {
        "criterion_id": criterion_id,
        "operational_description": text,
        "evidence_requirement": "Evidence demonstrates the required method.",
        "performance_levels": levels,
        "accepted_equivalents": [f"equivalent-{index}" for index in range(equivalent_count)],
    }


def _condition_payload(*, allowed_count: int = 1):
    return {
        "criterion_id": "C1",
        "allowed_level_ids": ["FULL"] + [f"L{index}" for index in range(1, allowed_count)],
    }


def _document(**overrides):
    value = {
        "schema_version": "1",
        "criteria": [_criterion_payload()],
        "positive_credit_dependencies": [],
        "gates": [],
        "caps": [],
        "deductions": [],
    }
    value.update(overrides)
    return value


def _raw(document=None) -> bytes:
    if document is None:
        document = _document()
    return json.dumps(
        document,
        ensure_ascii=True,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _parse(module, raw_payload: bytes, *, limits=None, provenance=None):
    if limits is None:
        limits = _limits(module)
    if provenance is None:
        provenance = _provenance(module)
    return module.parse_rubric_provider_payload(
        raw_payload=raw_payload,
        limits=limits,
        provenance=provenance,
    )


def test_g1b_ingress_module_exists_at_provider_architecture_boundary() -> None:
    assert _module_exists()


def test_g1b_public_contract_surfaces_and_exact_shapes_exist() -> None:
    module = _require_api(
        "RubricProviderIngressLimits",
        "RubricProviderProvenance",
        "AdmittedRubricProviderProposal",
        "RubricProviderIngressError",
        "RubricProviderResourceError",
        "RubricProviderMalformedResponseError",
        "RubricProviderSchemaError",
        "parse_rubric_provider_payload",
    )

    assert {field.name for field in fields(module.RubricProviderIngressLimits)} == {
        "max_raw_bytes",
        "max_json_depth",
        "max_json_nodes",
        "max_provenance_text_characters",
        "compilation_limits",
    }
    assert {field.name for field in fields(module.RubricProviderProvenance)} == {
        "provider_id",
        "model_id",
    }
    assert {field.name for field in fields(module.AdmittedRubricProviderProposal)} == {
        "proposal",
        "provenance",
        "raw_payload_sha256",
        "schema_version",
        "ingress_profile_version",
    }

    for cls in (
        module.RubricProviderIngressLimits,
        module.RubricProviderProvenance,
        module.AdmittedRubricProviderProposal,
    ):
        assert is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True

    assert issubclass(module.RubricProviderResourceError, module.RubricProviderIngressError)
    assert issubclass(module.RubricProviderMalformedResponseError, module.RubricProviderIngressError)
    assert issubclass(module.RubricProviderSchemaError, module.RubricProviderIngressError)
    assert len({
        module.RubricProviderResourceError,
        module.RubricProviderMalformedResponseError,
        module.RubricProviderSchemaError,
    }) == 3

    for field in fields(module.RubricProviderIngressLimits):
        assert field.default is MISSING
        assert field.default_factory is MISSING


def test_g1b_parse_api_requires_exact_raw_bytes_explicit_limits_and_out_of_band_provenance() -> None:
    module = _require_api("parse_rubric_provider_payload")
    signature = inspect.signature(module.parse_rubric_provider_payload)
    assert set(signature.parameters) == {"raw_payload", "limits", "provenance"}
    for parameter in signature.parameters.values():
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    limits = _limits(module)
    provenance = _provenance(module)
    for invalid in ("{}", bytearray(b"{}"), {}, memoryview(b"{}")):
        with pytest.raises(TypeError):
            module.parse_rubric_provider_payload(
                raw_payload=invalid,
                limits=limits,
                provenance=provenance,
            )


def test_ingress_limit_and_provenance_objects_require_exact_reviewed_runtime_shapes() -> None:
    module = _require_api("RubricProviderIngressLimits", "RubricProviderProvenance")

    with pytest.raises((TypeError, ValueError)):
        module.RubricProviderIngressLimits(
            max_raw_bytes=True,
            max_json_depth=10,
            max_json_nodes=10,
            max_provenance_text_characters=10,
            compilation_limits=_compilation_limits(),
        )
    with pytest.raises((TypeError, ValueError)):
        module.RubricProviderIngressLimits(
            max_raw_bytes=10,
            max_json_depth=10,
            max_json_nodes=10,
            max_provenance_text_characters=10,
            compilation_limits=object(),
        )
    with pytest.raises((TypeError, ValueError)):
        module.RubricProviderProvenance(provider_id="", model_id="model")
    with pytest.raises((TypeError, ValueError)):
        module.RubricProviderProvenance(provider_id="provider", model_id="")

    limits = _limits(module, provenance_text=5)
    with pytest.raises(module.RubricProviderResourceError):
        _parse(
            module,
            _raw(),
            limits=limits,
            provenance=module.RubricProviderProvenance(
                provider_id="provider-too-long",
                model_id="model",
            ),
        )


def test_raw_size_is_admitted_before_utf8_or_json_parsing() -> None:
    module = _require_api(
        "RubricProviderResourceError",
        "RubricProviderMalformedResponseError",
        "parse_rubric_provider_payload",
    )
    raw_payload = b"\xff" * 20
    with pytest.raises(module.RubricProviderResourceError):
        _parse(module, raw_payload, limits=_limits(module, raw_bytes=10))


def test_exact_raw_byte_limit_is_accepted_and_one_byte_over_is_rejected() -> None:
    module = _require_api("RubricProviderResourceError", "parse_rubric_provider_payload")
    raw_payload = _raw()

    accepted = _parse(module, raw_payload, limits=_limits(module, raw_bytes=len(raw_payload)))
    assert type(accepted.proposal) is RubricGenerationProposal

    with pytest.raises(module.RubricProviderResourceError):
        _parse(module, raw_payload, limits=_limits(module, raw_bytes=len(raw_payload) - 1))


@pytest.mark.parametrize(
    "raw_payload",
    [
        b"",
        b"{",
        b"[] trailing",
        b"\xff",
        b"NaN",
        b'{"schema_version":"1","criteria":[],"positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]} trailing',
    ],
)
def test_malformed_non_document_or_non_utf8_payloads_fail_as_malformed_response(raw_payload: bytes) -> None:
    module = _require_api("RubricProviderMalformedResponseError")
    with pytest.raises(module.RubricProviderMalformedResponseError):
        _parse(module, raw_payload)


def test_valid_json_with_wrong_root_type_fails_as_schema_rejection_not_malformed_transport() -> None:
    module = _require_api("RubricProviderSchemaError")
    for raw_payload in (b"null", b"[]", b"true", b"1"):
        with pytest.raises(module.RubricProviderSchemaError):
            _parse(module, raw_payload)


def test_excessive_nesting_is_rejected_as_resource_failure_before_schema_interpretation() -> None:
    module = _require_api("RubricProviderResourceError")
    nested = (b"[" * 80) + b"0" + (b"]" * 80)
    raw_payload = b'{"schema_version":"1","criteria":' + nested + b',"positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]}'
    with pytest.raises(module.RubricProviderResourceError):
        _parse(module, raw_payload, limits=_limits(module, depth=16))


def test_json_node_budget_rejects_before_nested_schema_validation() -> None:
    module = _require_api("RubricProviderResourceError")
    raw_payload = _raw(_document(criteria=[{} for _ in range(20)]))
    with pytest.raises(module.RubricProviderResourceError):
        _parse(
            module,
            raw_payload,
            limits=_limits(module, nodes=10, max_criteria=100),
        )


def test_duplicate_object_keys_are_rejected_instead_of_last_value_wins() -> None:
    module = _require_api("RubricProviderSchemaError")
    raw_payload = (
        b'{"schema_version":"1","criteria":[],"criteria":[],'
        b'"positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]}'
    )
    with pytest.raises(module.RubricProviderSchemaError):
        _parse(module, raw_payload)


def test_schema_is_closed_and_provider_cannot_smuggle_trusted_authority_fields() -> None:
    module = _require_api("RubricProviderSchemaError")
    forbidden = (
        "question_id",
        "max_marks",
        "rubric_id",
        "policy_id",
        "minimum_score",
        "rounding",
        "scoring_semantics_version",
        "approval",
        "teacher_ref",
        "state",
        "authority",
        "provider_id",
        "model_id",
    )
    for field_name in forbidden:
        document = _document()
        document[field_name] = "attacker-controlled"
        with pytest.raises(module.RubricProviderSchemaError):
            _parse(module, _raw(document))


def test_unknown_nested_fields_missing_required_fields_and_wrong_container_types_are_rejected() -> None:
    module = _require_api("RubricProviderSchemaError")

    nested_unknown = _document()
    nested_unknown["criteria"][0]["unexpected"] = "x"
    with pytest.raises(module.RubricProviderSchemaError):
        _parse(module, _raw(nested_unknown))

    missing = _document()
    del missing["deductions"]
    with pytest.raises(module.RubricProviderSchemaError):
        _parse(module, _raw(missing))

    wrong_type = _document(criteria={"not": "a list"})
    with pytest.raises(module.RubricProviderSchemaError):
        _parse(module, _raw(wrong_type))


def test_only_supported_schema_version_is_accepted() -> None:
    module = _require_api("RubricProviderSchemaError")
    for invalid in ("", "2", 1, None):
        with pytest.raises(module.RubricProviderSchemaError):
            _parse(module, _raw(_document(schema_version=invalid)))

    admitted = _parse(module, _raw(_document(schema_version="1")))
    assert admitted.schema_version == "1"


def test_full_structured_proposal_projects_exactly_without_normalization_or_trusted_field_invention() -> None:
    module = _require_api("parse_rubric_provider_payload")
    document = _document(
        criteria=[
            {
                "criterion_id": "C1",
                "operational_description": "  Preserve criterion whitespace.  ",
                "evidence_requirement": "  Preserve evidence whitespace.  ",
                "performance_levels": [
                    {
                        "level_id": "FULL",
                        "operational_description": "  Full description.  ",
                        "contribution": 2.5,
                    },
                    {
                        "level_id": "NOT_MET",
                        "operational_description": "Not met.",
                        "contribution": 0,
                    },
                ],
                "accepted_equivalents": ["  equivalent A  ", "equivalent B"],
            },
            _criterion_payload("C2", contribution=2.5, equivalent_count=0),
        ],
        positive_credit_dependencies=[
            {
                "rule_id": "DEP-1",
                "target_criterion_id": "C2",
                "prerequisite_conditions": [
                    {"criterion_id": "C1", "allowed_level_ids": ["FULL"]}
                ],
            }
        ],
        gates=[
            {
                "rule_id": "GATE-1",
                "required_conditions": [
                    {"criterion_id": "C1", "allowed_level_ids": ["FULL"]}
                ],
                "failure_ceiling": 4.5,
            }
        ],
        caps=[
            {
                "rule_id": "CAP-1",
                "trigger_conditions": [
                    {"criterion_id": "C2", "allowed_level_ids": ["NOT_MET"]}
                ],
                "ceiling": 4,
            }
        ],
        deductions=[
            {
                "rule_id": "DED-1",
                "trigger_conditions": [
                    {"criterion_id": "C2", "allowed_level_ids": ["NOT_MET"]}
                ],
                "amount": 0.5,
            }
        ],
    )
    raw_payload = _raw(document)
    admitted = _parse(module, raw_payload)
    proposal = admitted.proposal

    assert type(proposal) is RubricGenerationProposal
    assert proposal.criteria[0].operational_description == "  Preserve criterion whitespace.  "
    assert proposal.criteria[0].evidence_requirement == "  Preserve evidence whitespace.  "
    assert proposal.criteria[0].accepted_equivalents == ("  equivalent A  ", "equivalent B")
    assert proposal.criteria[0].performance_levels[0].contribution == ScoringDecimal.from_raw("2.5")
    assert proposal.positive_credit_dependencies[0].rule_id == "DEP-1"
    assert proposal.gates[0].failure_ceiling == ScoringDecimal.from_raw("4.5")
    assert proposal.caps[0].ceiling == ScoringDecimal.from_raw("4")
    assert proposal.deductions[0].amount == ScoringDecimal.from_raw("0.5")


def test_scoring_effect_fields_require_json_numbers_not_strings_booleans_or_nonstandard_constants() -> None:
    module = _require_api("RubricProviderMalformedResponseError", "RubricProviderSchemaError")

    for invalid in ("5", True, None):
        document = _document()
        document["criteria"][0]["performance_levels"][0]["contribution"] = invalid
        with pytest.raises(module.RubricProviderSchemaError):
            _parse(module, _raw(document))

    raw_nan = _raw().replace(b'"contribution":5', b'"contribution":NaN', 1)
    with pytest.raises(module.RubricProviderMalformedResponseError):
        _parse(module, raw_nan)


def test_json_numeric_tokens_are_preserved_exactly_without_binary_float_round_trip() -> None:
    module = _require_api("parse_rubric_provider_payload")
    raw_payload = _raw().replace(
        b'"contribution":5',
        b'"contribution":0.10000000000000001',
        1,
    )
    admitted = _parse(module, raw_payload)
    assert (
        admitted.proposal.criteria[0].performance_levels[0].contribution
        == ScoringDecimal.from_raw("0.10000000000000001")
    )


def test_compilation_cardinality_and_text_limits_are_enforced_before_domain_graph_construction() -> None:
    module = _require_api("RubricProviderResourceError")

    cases = []
    cases.append((_document(criteria=[_criterion_payload("C1"), _criterion_payload("C2")]), {"max_criteria": 1}))
    cases.append((_document(criteria=[_criterion_payload(level_count=3)]), {"max_levels_per_criterion": 2}))
    cases.append((_document(criteria=[_criterion_payload(equivalent_count=2)]), {"max_accepted_equivalents_per_criterion": 1}))

    many_rules = _document(
        gates=[
            {"rule_id": "G1", "required_conditions": [], "failure_ceiling": 1},
            {"rule_id": "G2", "required_conditions": [], "failure_ceiling": 1},
        ]
    )
    cases.append((many_rules, {"max_rules": 1}))

    too_many_conditions = _document(
        gates=[
            {
                "rule_id": "G1",
                "required_conditions": [_condition_payload(), _condition_payload()],
                "failure_ceiling": 1,
            }
        ]
    )
    cases.append((too_many_conditions, {"max_conditions_per_rule": 1}))

    too_many_allowed = _document(
        gates=[
            {
                "rule_id": "G1",
                "required_conditions": [_condition_payload(allowed_count=2)],
                "failure_ceiling": 1,
            }
        ]
    )
    cases.append((too_many_allowed, {"max_allowed_level_ids_per_condition": 1}))

    long_text = _document(criteria=[_criterion_payload(text="X" * 6)])
    cases.append((long_text, {"max_text_characters_per_field": 5}))

    for document, override in cases:
        with pytest.raises(module.RubricProviderResourceError):
            _parse(module, _raw(document), limits=_limits(module, **override))


def test_provider_metadata_is_out_of_band_provenance_not_raw_model_authority() -> None:
    module = _require_api("RubricProviderSchemaError")
    provenance = module.RubricProviderProvenance(
        provider_id="adapter-provider",
        model_id="adapter-model",
    )
    admitted = _parse(module, _raw(), provenance=provenance)
    assert admitted.provenance == provenance

    for field_name in ("provider_id", "model_id"):
        document = _document()
        document[field_name] = "model-self-asserted"
        with pytest.raises(module.RubricProviderSchemaError):
            _parse(module, _raw(document), provenance=provenance)


def test_admitted_provider_output_remains_untrusted_proposal_and_has_no_authority_path() -> None:
    module = _require_api("AdmittedRubricProviderProposal")
    admitted = _parse(module, _raw())

    assert type(admitted) is module.AdmittedRubricProviderProposal
    assert type(admitted.proposal) is RubricGenerationProposal
    assert not isinstance(admitted, GeneratedRubricCandidate)
    assert not isinstance(admitted, CompiledRubricCandidate)
    assert not isinstance(admitted, QuestionScoringAuthority)
    names = {field.name for field in fields(admitted)}
    assert {
        "source",
        "finalized_question",
        "question_id",
        "max_marks",
        "rubric_id",
        "policy_id",
        "minimum_score",
        "rounding",
        "approval",
        "teacher_ref",
        "state",
        "authority",
    }.isdisjoint(names)


def test_same_raw_payload_and_provenance_replay_is_deterministic_and_bound_to_exact_raw_bytes() -> None:
    module = _require_api("parse_rubric_provider_payload")
    provenance = _provenance(module)
    raw_payload = _raw()

    first = _parse(module, raw_payload, provenance=provenance)
    second = _parse(module, raw_payload, provenance=provenance)
    assert first == second
    assert first.raw_payload_sha256 == hashlib.sha256(raw_payload).hexdigest()
    assert first.ingress_profile_version == "1"

    semantically_same_different_bytes = json.dumps(
        _document(),
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")
    third = _parse(module, semantically_same_different_bytes, provenance=provenance)
    assert third.proposal == first.proposal
    assert third.raw_payload_sha256 != first.raw_payload_sha256


def test_domain_objects_and_ingress_contracts_are_immutable_after_admission() -> None:
    module = _require_api("AdmittedRubricProviderProposal")
    admitted = _parse(module, _raw())

    with pytest.raises(FrozenInstanceError):
        admitted.raw_payload_sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        admitted.provenance.provider_id = "evil"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        admitted.proposal.criteria[0].criterion_id = "evil"  # type: ignore[misc]
    assert type(admitted.proposal.criteria) is tuple
    assert type(admitted.proposal.criteria[0].performance_levels) is tuple
