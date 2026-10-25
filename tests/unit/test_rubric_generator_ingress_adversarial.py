from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.providers import rubric_ingress as ingress
from grading.rubric.generator import RubricGenerationProposal
from grading.rubric.models import RubricCompilationLimits


# Independent count for _raw(): one node per JSON value/container, not object-key text.
# This is intentionally not derived from the implementation's scanner.
_EXPECTED_VALID_FIXTURE_NODES = 22


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
    *,
    raw_bytes: int = 100_000,
    depth: int = 32,
    nodes: int = 10_000,
    provenance_text: int = 256,
    **compilation_overrides,
) -> ingress.RubricProviderIngressLimits:
    return ingress.RubricProviderIngressLimits(
        max_raw_bytes=raw_bytes,
        max_json_depth=depth,
        max_json_nodes=nodes,
        max_provenance_text_characters=provenance_text,
        compilation_limits=_compilation_limits(**compilation_overrides),
    )


def _provenance() -> ingress.RubricProviderProvenance:
    return ingress.RubricProviderProvenance(
        provider_id="fake-provider",
        model_id="fixture-model-v1",
    )


def _criterion(
    *,
    text: str = "Award credit for the required method.",
    contribution: object = 5,
):
    return {
        "criterion_id": "C1",
        "operational_description": text,
        "evidence_requirement": "Evidence demonstrates the required method.",
        "performance_levels": [
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
        ],
        "accepted_equivalents": ["equivalent-0"],
    }


def _document(**overrides):
    value = {
        "schema_version": "1",
        "criteria": [_criterion()],
        "positive_credit_dependencies": [],
        "gates": [],
        "caps": [],
        "deductions": [],
    }
    value.update(overrides)
    return value


def _raw(document=None) -> bytes:
    return json.dumps(
        _document() if document is None else document,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _parse(raw_payload: bytes, *, limits=None):
    return ingress.parse_rubric_provider_payload(
        raw_payload=raw_payload,
        limits=_limits() if limits is None else limits,
        provenance=_provenance(),
    )


def _forged_admitted_kwargs() -> dict[str, object]:
    return {
        "proposal": RubricGenerationProposal((), (), (), (), ()),
        "provenance": _provenance(),
        "raw_payload_sha256": "0" * 64,
        "schema_version": "1",
        "ingress_profile_version": "1",
    }


def test_admitted_wrapper_cannot_be_forged_via_supported_public_construction() -> None:
    # The output type may be public for inspection/type checking, but a caller must
    # not be able to mint an object that claims parser admission without parsing.
    with pytest.raises(TypeError):
        ingress.AdmittedRubricProviderProposal(**_forged_admitted_kwargs())


def test_admitted_wrapper_cannot_be_forged_via_dataclasses_replace() -> None:
    admitted = _parse(_raw())

    # dataclasses.replace() must not become a second admission-forgery path either.
    with pytest.raises(TypeError):
        replace(admitted, raw_payload_sha256="0" * 64)


def test_admitted_wrapper_cannot_be_forged_via_public_subclass_smuggling() -> None:
    forged_values = _forged_admitted_kwargs()

    # The admitted marker is a public type. Normal Python subclassing must not create
    # another supported-looking way to mint an admitted-looking instance that can pass
    # ordinary isinstance/type-hint boundaries without parser admission.
    with pytest.raises(TypeError):
        class ForgedAdmittedRubricProviderProposal(ingress.AdmittedRubricProviderProposal):
            proposal = forged_values["proposal"]
            provenance = forged_values["provenance"]
            raw_payload_sha256 = forged_values["raw_payload_sha256"]
            schema_version = forged_values["schema_version"]
            ingress_profile_version = forged_values["ingress_profile_version"]

            def __init__(self) -> None:
                pass

        ForgedAdmittedRubricProviderProposal()


def test_over_depth_rejects_before_full_json_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    nested = (b"[" * 40) + b"0" + (b"]" * 40)
    raw_payload = (
        b'{"schema_version":"1","criteria":'
        + nested
        + b',"positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]}'
    )

    def forbidden_decode(_text: str):
        raise AssertionError("full JSON materialization must not start")

    monkeypatch.setattr(ingress, "_decode_json", forbidden_decode)
    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(depth=8, nodes=1000))


def test_over_node_budget_rejects_before_full_json_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_payload = _raw(_document(criteria=[{} for _ in range(20)]))

    def forbidden_decode(_text: str):
        raise AssertionError("full JSON materialization must not start")

    monkeypatch.setattr(ingress, "_decode_json", forbidden_decode)
    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(nodes=10, max_criteria=100))


def test_object_member_pressure_is_covered_by_value_node_budget_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_payload = ("{" + ",".join(f'\"k{i}\":0' for i in range(50)) + "}").encode("ascii")

    def forbidden_decode(_text: str):
        raise AssertionError("full JSON materialization must not start")

    monkeypatch.setattr(ingress, "_decode_json", forbidden_decode)
    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(nodes=10, max_criteria=100))


def test_cardinality_rejection_happens_before_domain_graph_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_payload = _raw(_document(criteria=[_criterion(), _criterion()]))

    def forbidden_build(_document):
        raise AssertionError("domain graph construction must not start")

    monkeypatch.setattr(ingress, "_build_proposal", forbidden_build)
    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(max_criteria=1))


def test_text_resource_rejection_happens_before_domain_graph_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_payload = _raw(_document(criteria=[_criterion(text="X" * 6)]))

    def forbidden_build(_document):
        raise AssertionError("domain graph construction must not start")

    monkeypatch.setattr(ingress, "_build_proposal", forbidden_build)
    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(max_text_characters_per_field=5))


def test_unexpected_decoder_runtime_error_remains_technical(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(_text: str):
        raise RuntimeError("injected decoder defect")

    monkeypatch.setattr(ingress, "_decode_json", unexpected)
    with pytest.raises(RuntimeError, match="injected decoder defect"):
        _parse(_raw())


def test_unexpected_decoder_recursion_error_is_not_disguised_as_provider_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(_text: str):
        raise RecursionError("injected decoder defect")

    monkeypatch.setattr(ingress, "_decode_json", unexpected)
    with pytest.raises(RecursionError, match="injected decoder defect"):
        _parse(_raw())


def test_unexpected_schema_validation_assertion_remains_technical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(_document, _limits):
        raise AssertionError("injected validator defect")

    monkeypatch.setattr(ingress, "_validate_document", unexpected)
    with pytest.raises(AssertionError, match="injected validator defect"):
        _parse(_raw())


def test_depth_limit_exact_boundary_is_stable() -> None:
    raw_payload = _raw()
    admitted = _parse(raw_payload, limits=_limits(raw_bytes=len(raw_payload), depth=6))
    assert type(admitted.proposal) is RubricGenerationProposal

    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(raw_bytes=len(raw_payload), depth=5))


def test_node_limit_exact_boundary_is_stable() -> None:
    raw_payload = _raw()
    admitted = _parse(
        raw_payload,
        limits=_limits(raw_bytes=len(raw_payload), nodes=_EXPECTED_VALID_FIXTURE_NODES),
    )
    assert type(admitted.proposal) is RubricGenerationProposal

    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(
            raw_payload,
            limits=_limits(
                raw_bytes=len(raw_payload),
                nodes=_EXPECTED_VALID_FIXTURE_NODES - 1,
            ),
        )


def test_nested_duplicate_keys_are_rejected_deterministically() -> None:
    raw_payload = (
        b'{"schema_version":"1","criteria":[{"criterion_id":"C1","criterion_id":"C2",'
        b'"operational_description":"x","evidence_requirement":"e",'
        b'"performance_levels":[],"accepted_equivalents":[]}],'
        b'"positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]}'
    )
    with pytest.raises(ingress.RubricProviderSchemaError):
        _parse(raw_payload)


@pytest.mark.parametrize(
    ("token", "canonical"),
    [
        (b"0", "0"),
        (b"-0", "0"),
        (b"0.0", "0"),
        (b"-0.0", "0"),
        (b"1", "1"),
        (b"1.0", "1"),
        (b"1e3", "1000"),
        (b"1E3", "1000"),
        (b"1e-3", "0.001"),
    ],
)
def test_json_numeric_forms_preserve_exact_scoring_semantics(token: bytes, canonical: str) -> None:
    raw_payload = _raw().replace(b'"contribution":5', b'"contribution":' + token, 1)
    admitted = _parse(raw_payload)
    value = admitted.proposal.criteria[0].performance_levels[0].contribution
    assert value == ScoringDecimal.from_raw(canonical)


def test_huge_numeric_token_is_bounded_by_numeric_profile() -> None:
    huge = b"1" + (b"0" * 5000)
    raw_payload = _raw().replace(b'"contribution":5', b'"contribution":' + huge, 1)
    with pytest.raises(ingress.RubricProviderResourceError):
        _parse(raw_payload, limits=_limits(raw_bytes=len(raw_payload)))


def test_cross_process_admission_and_g1a_composition_are_hash_seed_deterministic(
    tmp_path: Path,
) -> None:
    script = tmp_path / "probe.py"
    script.write_text(
        """
import json
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.providers import rubric_ingress as ingress
from grading.rubric.generator import RubricGenerationInput, generate_rubric_candidate
from grading.rubric.models import FinalizedQuestionScoringBasis, RubricCompilationLimits

limits = ingress.RubricProviderIngressLimits(
    max_raw_bytes=100000,
    max_json_depth=32,
    max_json_nodes=10000,
    max_provenance_text_characters=256,
    compilation_limits=RubricCompilationLimits(20,10,20,50,20,10,2000,100000,1000),
)
provenance = ingress.RubricProviderProvenance("fake-provider", "fixture-model-v1")
doc = {
    "schema_version":"1",
    "criteria":[{
        "criterion_id":"C1",
        "operational_description":"Method",
        "evidence_requirement":"Evidence",
        "performance_levels":[
            {"level_id":"FULL","operational_description":"Full","contribution":5},
            {"level_id":"NOT_MET","operational_description":"None","contribution":0}
        ],
        "accepted_equivalents":["Equivalent"]
    }],
    "positive_credit_dependencies":[],"gates":[],"caps":[],"deductions":[]
}
raw = json.dumps(doc, ensure_ascii=True, separators=(",",":"), allow_nan=False).encode("utf-8")
admitted = ingress.parse_rubric_provider_payload(raw_payload=raw, limits=limits, provenance=provenance)
source = RubricGenerationInput(
    finalized_question=FinalizedQuestionScoringBasis("Q1", ScoringDecimal.from_raw("5")),
    question_text="Question",
    model_answer_text="Model answer",
    rubric_id="R1",
    policy_id="P1",
    minimum_score=ScoringDecimal.from_raw("0"),
    rounding=None,
)
candidate = generate_rubric_candidate(source=source, proposal=admitted.proposal)
print(admitted.raw_payload_sha256)
print(candidate.proposal_fingerprint)
print(candidate.content_fingerprint)
""".strip(),
        encoding="utf-8",
    )

    outputs = []
    for seed in ("1", "777", "123456"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        # pytest's ``pythonpath = ["src"]`` modifies the parent interpreter's
        # sys.path; it does not propagate that import path to a plain child Python
        # process. Make the subprocess import boundary explicit so this test measures
        # hash-seed determinism rather than whether the package is installed editable.
        source_root = str(Path.cwd() / "src")
        inherited_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            source_root
            if not inherited_pythonpath
            else source_root + os.pathsep + inherited_pythonpath
        )
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=Path.cwd(),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1] == outputs[2]
