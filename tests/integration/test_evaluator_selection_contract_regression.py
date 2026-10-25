from __future__ import annotations

from dataclasses import fields
from importlib import import_module
from inspect import signature
from typing import Any

import pytest

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.capability_registry import (
    EvaluatorCapabilityAmbiguityError,
    EvaluatorCapabilityBindingError,
    EvaluatorCapabilityMissingError,
    EvaluatorCapabilitySourceExecutionError,
    EvaluatorCapabilitySourceResultError,
)
from grading.contracts.capability import (
    EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION,
    EvaluatorCapabilityRecord,
    EvaluatorCapabilityRef,
    EvaluatorCapabilityStatus,
)
from grading.contracts.evaluation import EvaluatorMetadata
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.rubric.lifecycle import (
    activate_version,
    approve_version,
    create_initial_version,
    get_active_scoring_authority,
    validate_version,
)
from tests.support.rubric_authoring import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


_UNSET = object()

_MISSING_MESSAGE = (
    "Authoritative classification and exact evaluator-policy selection "
    "+ exact capability resolution are absent."
)


def _batch4_modules() -> tuple[Any, Any]:
    try:
        contract = import_module("grading.contracts.evaluator_selection")
    except ModuleNotFoundError as exc:
        if exc.name == "grading.contracts.evaluator_selection":
            pytest.fail(_MISSING_MESSAGE, pytrace=False)
        raise

    try:
        runtime = import_module("grading.evaluator_selection")
    except ModuleNotFoundError as exc:
        if exc.name == "grading.evaluator_selection":
            pytest.fail(_MISSING_MESSAGE, pytrace=False)
        raise

    return contract, runtime


def _question_authority(
    *,
    context_policy: ContextPolicy = ContextPolicy.DIRECT,
) -> ResolvedQuestionAuthority:
    draft = create_initial_version(simple_basis(), simple_content())
    validated = validate_version(draft, limits=authoring_test_limits())
    approved = approve_version(validated, teacher_ref="teacher-42")
    active = activate_version(approved, limits=authoring_test_limits())
    return ResolvedQuestionAuthority(
        grading_spec_ref=GradingSpecRef(id="SPEC-1", version=1),
        question_id="Q1",
        question_text="Explain the required result.",
        context_policy=context_policy,
        rubric_content=active.content,
        scoring_authority=get_active_scoring_authority(active),
    )


def _capability_ref(
    *,
    evaluator_id: str = "gradified-direct-text",
    evaluator_version: str = "1",
    record_version: int = 1,
) -> EvaluatorCapabilityRef:
    return EvaluatorCapabilityRef(
        evaluator_metadata=EvaluatorMetadata(
            evaluator_id=evaluator_id,
            version=evaluator_version,
        ),
        record_version=record_version,
    )


def _capability_record(
    *,
    capability_ref: EvaluatorCapabilityRef | None = None,
    status: EvaluatorCapabilityStatus = EvaluatorCapabilityStatus.PILOT,
    answer_types: tuple[str, ...] = ("SHORT_TEXT",),
    languages: tuple[str, ...] = ("en",),
    modalities: tuple[str, ...] = (),
) -> EvaluatorCapabilityRecord:
    return EvaluatorCapabilityRecord(
        schema_version=EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION,
        capability_ref=capability_ref or _capability_ref(),
        status=status,
        supported_answer_types=answer_types,
        supported_languages=languages,
        supported_modalities=modalities,
        tested_grade_range=None,
        domain_scope=None,
        verification_mechanisms=(),
        benchmark_version=None,
        known_failure_modes=(),
        cost_profile=None,
        latency_profile=None,
    )


class _ClassificationSource:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_question_evaluation_classification(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        self.calls.append((grading_spec_ref, question_id))
        return self.value


class _PolicySource:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls = 0

    def resolve_evaluator_selection_policy(self) -> object:
        self.calls += 1
        return self.value


class _CapabilitySource:
    def __init__(self, records: tuple[EvaluatorCapabilityRecord, ...]) -> None:
        self.records = records
        self.calls: list[EvaluatorCapabilityRef] = []

    def find_exact_capabilities(
        self,
        *,
        capability_ref: EvaluatorCapabilityRef,
    ) -> tuple[EvaluatorCapabilityRecord, ...]:
        self.calls.append(capability_ref)
        return self.records


class _ExplodingClassificationSource:
    def resolve_question_evaluation_classification(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        del grading_spec_ref, question_id
        raise RuntimeError("classification backend unavailable")


class _ExplodingPolicySource:
    def resolve_evaluator_selection_policy(self) -> object:
        raise RuntimeError("policy backend unavailable")


class _ExplodingCapabilitySource:
    def __init__(self) -> None:
        self.calls: list[EvaluatorCapabilityRef] = []

    def find_exact_capabilities(
        self,
        *,
        capability_ref: EvaluatorCapabilityRef,
    ) -> tuple[EvaluatorCapabilityRecord, ...]:
        self.calls.append(capability_ref)
        raise RuntimeError("capability backend unavailable")


class _MalformedCapabilitySource:
    def __init__(self) -> None:
        self.calls: list[EvaluatorCapabilityRef] = []

    def find_exact_capabilities(
        self,
        *,
        capability_ref: EvaluatorCapabilityRef,
    ) -> object:
        self.calls.append(capability_ref)
        return []


class _ExplodingForeignValue:
    def __getattribute__(self, name: str) -> object:
        if name in {"__class__", "__repr__"}:
            return object.__getattribute__(self, name)
        raise AssertionError(f"foreign value attribute dispatch is forbidden: {name}")


def _classification(contract: Any, **overrides: object) -> object:
    values: dict[str, object] = {
        "schema_version": "1",
        "grading_spec_ref": GradingSpecRef(id="SPEC-1", version=1),
        "question_id": "Q1",
        "answer_type": "SHORT_TEXT",
        "language": "en",
    }
    values.update(overrides)
    return contract.QuestionEvaluationClassification(**values)


def _policy_ref(contract: Any, **overrides: object) -> object:
    values: dict[str, object] = {"policy_id": "IF2-POLICY", "version": 1}
    values.update(overrides)
    return contract.EvaluatorSelectionPolicyRef(**values)


def _rule(contract: Any, **overrides: object) -> object:
    values: dict[str, object] = {
        "answer_type": "SHORT_TEXT",
        "language": "en",
        "context_policy": ContextPolicy.DIRECT,
        "capability_ref": _capability_ref(),
    }
    values.update(overrides)
    return contract.EvaluatorSelectionRule(**values)


def _policy(contract: Any, **overrides: object) -> object:
    values: dict[str, object] = {
        "schema_version": "1",
        "policy_ref": _policy_ref(contract),
        "rules": (_rule(contract),),
    }
    values.update(overrides)
    return contract.EvaluatorSelectionPolicy(**values)


def _resolve(
    contract: Any,
    runtime: Any,
    *,
    question_authority: ResolvedQuestionAuthority | None = None,
    classification: object = _UNSET,
    policy: object = _UNSET,
    capability_records: object = _UNSET,
) -> tuple[object, _ClassificationSource, _PolicySource, _CapabilitySource]:
    authority = question_authority or _question_authority()
    classification_source = _ClassificationSource(
        _classification(contract) if classification is _UNSET else classification
    )
    policy_source = _PolicySource(_policy(contract) if policy is _UNSET else policy)
    capability_source = _CapabilitySource(
        (_capability_record(),)
        if capability_records is _UNSET
        else capability_records
    )
    result = runtime.resolve_question_evaluator_selection(
        question_authority=authority,
        classification_source=classification_source,
        policy_source=policy_source,
        capability_source=capability_source,
    )
    return result, classification_source, policy_source, capability_source


def test_batch4_prerequisites_are_frozen_before_if2_red() -> None:
    authority = _question_authority(context_policy=ContextPolicy.REFERENCE_ONLY)
    ref = _capability_ref()
    record = _capability_record(capability_ref=ref)

    assert authority.grading_spec_ref == GradingSpecRef(id="SPEC-1", version=1)
    assert authority.question_id == "Q1"
    assert authority.context_policy is ContextPolicy.REFERENCE_ONLY
    assert record.capability_ref == ref
    assert EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION == "1"


def test_contract_versions_and_exact_public_value_shapes_are_v1() -> None:
    contract, _ = _batch4_modules()

    assert contract.QUESTION_EVALUATION_CLASSIFICATION_SCHEMA_VERSION == "1"
    assert contract.EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION == "1"
    assert tuple(field.name for field in fields(contract.QuestionEvaluationClassification)) == (
        "schema_version",
        "grading_spec_ref",
        "question_id",
        "answer_type",
        "language",
    )
    assert tuple(field.name for field in fields(contract.EvaluatorSelectionPolicyRef)) == (
        "policy_id",
        "version",
    )
    assert tuple(field.name for field in fields(contract.EvaluatorSelectionRule)) == (
        "answer_type",
        "language",
        "context_policy",
        "capability_ref",
    )
    assert tuple(field.name for field in fields(contract.EvaluatorSelectionPolicy)) == (
        "schema_version",
        "policy_ref",
        "rules",
    )


def test_contract_values_are_immutable_after_construction() -> None:
    contract, _ = _batch4_modules()
    classification = _classification(contract)
    policy_ref = _policy_ref(contract)
    rule = _rule(contract)
    policy = _policy(contract)

    for value, field_name, replacement in (
        (classification, "answer_type", "MUTATED"),
        (policy_ref, "policy_id", "MUTATED"),
        (rule, "language", "MUTATED"),
        (policy, "rules", ()),
    ):
        with pytest.raises(AttributeError):
            setattr(value, field_name, replacement)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("question_id", ""),
        ("question_id", " Q1"),
        ("answer_type", ""),
        ("answer_type", " SHORT_TEXT"),
        ("language", ""),
        ("language", "en "),
        ("answer_type", 7),
        ("language", None),
    ],
)
def test_classification_rejects_malformed_opaque_authority_values(
    field_name: str,
    bad_value: object,
) -> None:
    contract, _ = _batch4_modules()
    with pytest.raises(contract.QuestionEvaluationClassificationContractError):
        _classification(contract, **{field_name: bad_value})


def test_classification_rejects_unknown_schema_and_noncanonical_spec_ref() -> None:
    contract, _ = _batch4_modules()
    with pytest.raises(contract.QuestionEvaluationClassificationContractError):
        _classification(contract, schema_version="2")

    classification = _classification(contract)
    object.__setattr__(classification.grading_spec_ref, "version", 0)
    with pytest.raises(contract.QuestionEvaluationClassificationContractError):
        contract.validate_question_evaluation_classification(classification)


def test_answer_type_and_language_are_opaque_and_not_normalized() -> None:
    contract, _ = _batch4_modules()
    upper = _classification(contract, answer_type="SHORT_TEXT", language="en")
    lower = _classification(contract, answer_type="short_text", language="EN")
    assert upper.answer_type != lower.answer_type
    assert upper.language != lower.language


def test_policy_ref_requires_exact_identity_and_positive_integer_version() -> None:
    contract, _ = _batch4_modules()
    for bad in ("", " IF2", "IF2 "):
        with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
            _policy_ref(contract, policy_id=bad)
    for bad in (True, False, 0, -1, "1"):
        with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
            _policy_ref(contract, version=bad)


def test_rule_requires_canonical_context_policy_and_exact_capability_ref() -> None:
    contract, _ = _batch4_modules()
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        _rule(contract, context_policy="DIRECT")
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        _rule(contract, capability_ref=object())


def test_policy_requires_exact_tuple_and_rejects_duplicate_exact_keys() -> None:
    contract, _ = _batch4_modules()
    rule = _rule(contract)
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        _policy(contract, rules=[rule])
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        _policy(contract, rules=(rule, _rule(contract)))


def test_empty_policy_is_structurally_valid_but_not_a_default_mapping() -> None:
    contract, _ = _batch4_modules()
    policy = _policy(contract, rules=())
    assert contract.validate_evaluator_selection_policy(policy) is policy


def test_runtime_public_api_accepts_sources_not_direct_classification_or_policy_values() -> None:
    _, runtime = _batch4_modules()
    parameters = signature(runtime.resolve_question_evaluator_selection).parameters
    assert tuple(parameters) == (
        "question_authority",
        "classification_source",
        "policy_source",
        "capability_source",
    )
    assert "classification" not in parameters
    assert "policy" not in parameters


def test_happy_path_binds_classification_uses_authority_context_and_composes_real_if1() -> None:
    contract, runtime = _batch4_modules()
    authority = _question_authority(context_policy=ContextPolicy.DIRECT)
    result, classification_source, policy_source, capability_source = _resolve(
        contract,
        runtime,
        question_authority=authority,
    )

    assert classification_source.calls == [(authority.grading_spec_ref, authority.question_id)]
    assert policy_source.calls == 1
    assert len(capability_source.calls) == 1
    assert result.classification.grading_spec_ref == authority.grading_spec_ref
    assert result.classification.question_id == authority.question_id
    assert result.classification.answer_type == "SHORT_TEXT"
    assert result.classification.language == "en"
    assert result.context_policy is authority.context_policy
    assert result.policy_ref.policy_id == "IF2-POLICY"
    assert result.policy_ref.version == 1
    assert result.selected_capability_ref == _capability_ref()
    assert result.resolved_capability.record.capability_ref == _capability_ref()


def test_result_is_routing_identity_only_not_execution_authorization() -> None:
    contract, runtime = _batch4_modules()
    result, *_ = _resolve(contract, runtime)
    for forbidden in (
        "authorized",
        "execution_authorized",
        "execution_eligible",
        "can_execute",
        "evaluation_attempt_id",
        "execute",
        "job_state",
        "grade_result",
    ):
        assert not hasattr(result, forbidden)


def test_foreign_question_authority_is_rejected_before_attribute_dispatch() -> None:
    contract, runtime = _batch4_modules()
    classification_source = _ClassificationSource(_classification(contract))
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))

    with pytest.raises(runtime.QuestionClassificationBindingError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_ExplodingForeignValue(),
            classification_source=classification_source,
            policy_source=policy_source,
            capability_source=capability_source,
        )

    assert classification_source.calls == []
    assert policy_source.calls == 0
    assert capability_source.calls == []


def test_question_authority_is_revalidated_before_sources_are_invoked() -> None:
    contract, runtime = _batch4_modules()
    authority = _question_authority()
    object.__setattr__(authority, "context_policy", "DIRECT")
    classification_source = _ClassificationSource(_classification(contract))
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))

    with pytest.raises(runtime.QuestionClassificationBindingError):
        runtime.resolve_question_evaluator_selection(
            question_authority=authority,
            classification_source=classification_source,
            policy_source=policy_source,
            capability_source=capability_source,
        )

    assert classification_source.calls == []
    assert policy_source.calls == 0
    assert capability_source.calls == []


def test_classification_source_failure_is_not_misclassified_as_missing_route() -> None:
    contract, runtime = _batch4_modules()
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))
    with pytest.raises(runtime.QuestionClassificationSourceExecutionError) as excinfo:
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ExplodingClassificationSource(),
            policy_source=policy_source,
            capability_source=capability_source,
        )
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert policy_source.calls == 0
    assert capability_source.calls == []


@pytest.mark.parametrize(
    "classification",
    [object(), None, ("SHORT_TEXT", "en")],
)
def test_classification_source_must_return_exact_gradified_contract_value(
    classification: object,
) -> None:
    contract, runtime = _batch4_modules()
    with pytest.raises(runtime.QuestionClassificationSourceResultError):
        _resolve(contract, runtime, classification=classification)


def test_invalid_classification_source_result_stops_policy_and_if1_sources() -> None:
    contract, runtime = _batch4_modules()
    classification_source = _ClassificationSource(object())
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))

    with pytest.raises(runtime.QuestionClassificationSourceResultError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=classification_source,
            policy_source=policy_source,
            capability_source=capability_source,
        )

    assert policy_source.calls == 0
    assert capability_source.calls == []


def test_classification_source_rejects_subclass_and_foreign_value_before_dispatch() -> None:
    contract, runtime = _batch4_modules()

    class ClassificationSubclass(contract.QuestionEvaluationClassification):
        pass

    subclass_value = object.__new__(ClassificationSubclass)
    object.__setattr__(subclass_value, "schema_version", "1")
    object.__setattr__(subclass_value, "grading_spec_ref", GradingSpecRef(id="SPEC-1", version=1))
    object.__setattr__(subclass_value, "question_id", "Q1")
    object.__setattr__(subclass_value, "answer_type", "SHORT_TEXT")
    object.__setattr__(subclass_value, "language", "en")
    for value in (subclass_value, _ExplodingForeignValue()):
        with pytest.raises(runtime.QuestionClassificationSourceResultError):
            _resolve(contract, runtime, classification=value)


def test_classification_must_bind_exact_spec_and_question_identity() -> None:
    contract, runtime = _batch4_modules()
    for classification in (
        _classification(contract, grading_spec_ref=GradingSpecRef(id="SPEC-X", version=1)),
        _classification(contract, question_id="Q-X"),
    ):
        with pytest.raises(runtime.QuestionClassificationBindingError):
            _resolve(contract, runtime, classification=classification)


def test_mutated_classification_is_revalidated_before_selection() -> None:
    contract, runtime = _batch4_modules()
    classification = _classification(contract)
    object.__setattr__(classification, "language", " en")
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))
    with pytest.raises(runtime.QuestionClassificationSourceResultError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(classification),
            policy_source=policy_source,
            capability_source=capability_source,
        )
    assert policy_source.calls == 0
    assert capability_source.calls == []


def test_mutated_nested_classification_identity_is_revalidated_before_binding() -> None:
    contract, runtime = _batch4_modules()
    classification = _classification(contract)
    object.__setattr__(classification.grading_spec_ref, "version", 0)
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))
    with pytest.raises(runtime.QuestionClassificationSourceResultError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(classification),
            policy_source=policy_source,
            capability_source=capability_source,
        )
    assert policy_source.calls == 0
    assert capability_source.calls == []


def test_policy_source_failure_is_not_translated_into_selection_miss() -> None:
    contract, runtime = _batch4_modules()
    capability_source = _CapabilitySource((_capability_record(),))
    with pytest.raises(runtime.SelectionPolicySourceExecutionError) as excinfo:
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(_classification(contract)),
            policy_source=_ExplodingPolicySource(),
            capability_source=capability_source,
        )
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert capability_source.calls == []


@pytest.mark.parametrize("policy", [object(), None, ()])
def test_policy_source_must_return_exact_gradified_policy(policy: object) -> None:
    contract, runtime = _batch4_modules()
    with pytest.raises(runtime.SelectionPolicySourceResultError):
        _resolve(contract, runtime, policy=policy)


def test_invalid_policy_source_result_stops_if1_source_lookup() -> None:
    contract, runtime = _batch4_modules()
    capability_source = _CapabilitySource((_capability_record(),))

    with pytest.raises(runtime.SelectionPolicySourceResultError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(_classification(contract)),
            policy_source=_PolicySource(object()),
            capability_source=capability_source,
        )

    assert capability_source.calls == []


def test_policy_source_rejects_subclass_and_foreign_value_before_dispatch() -> None:
    contract, runtime = _batch4_modules()

    class PolicySubclass(contract.EvaluatorSelectionPolicy):
        pass

    subclass_value = object.__new__(PolicySubclass)
    object.__setattr__(subclass_value, "schema_version", "1")
    object.__setattr__(subclass_value, "policy_ref", _policy_ref(contract))
    object.__setattr__(subclass_value, "rules", (_rule(contract),))
    for value in (subclass_value, _ExplodingForeignValue()):
        with pytest.raises(runtime.SelectionPolicySourceResultError):
            _resolve(contract, runtime, policy=value)


def test_mutated_policy_current_state_is_revalidated() -> None:
    contract, runtime = _batch4_modules()
    policy = _policy(contract)
    object.__setattr__(policy, "schema_version", "2")
    capability_source = _CapabilitySource((_capability_record(),))
    with pytest.raises(runtime.SelectionPolicySourceResultError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(_classification(contract)),
            policy_source=_PolicySource(policy),
            capability_source=capability_source,
        )
    assert capability_source.calls == []


def test_mutated_nested_policy_state_is_revalidated_before_selection_or_if1() -> None:
    contract, runtime = _batch4_modules()

    policies = []
    policy = _policy(contract)
    object.__setattr__(policy.rules[0], "context_policy", "DIRECT")
    policies.append(policy)

    policy = _policy(contract)
    object.__setattr__(policy.rules[0].capability_ref, "record_version", 0)
    policies.append(policy)

    policy = _policy(contract)
    object.__setattr__(policy.policy_ref, "version", 0)
    policies.append(policy)

    for policy in policies:
        capability_source = _CapabilitySource((_capability_record(),))
        with pytest.raises(runtime.SelectionPolicySourceResultError):
            runtime.resolve_question_evaluator_selection(
                question_authority=_question_authority(),
                classification_source=_ClassificationSource(_classification(contract)),
                policy_source=_PolicySource(policy),
                capability_source=capability_source,
            )
        assert capability_source.calls == []


def test_selection_is_exact_for_answer_type_language_and_context_policy() -> None:
    contract, runtime = _batch4_modules()
    mismatches = (
        _classification(contract, answer_type="short_text"),
        _classification(contract, language="EN"),
    )
    for classification in mismatches:
        with pytest.raises(runtime.EvaluatorSelectionMissingRuleError):
            _resolve(contract, runtime, classification=classification)

    authority = _question_authority(context_policy=ContextPolicy.REFERENCE_ONLY)
    with pytest.raises(runtime.EvaluatorSelectionMissingRuleError):
        _resolve(contract, runtime, question_authority=authority)


def test_literal_wildcard_text_is_not_wildcard_behavior() -> None:
    contract, runtime = _batch4_modules()
    wildcard_rule = _rule(contract, answer_type="*", language="*")
    policy = _policy(contract, rules=(wildcard_rule,))
    with pytest.raises(runtime.EvaluatorSelectionMissingRuleError):
        _resolve(contract, runtime, policy=policy)


def test_nonmatching_rule_before_exact_rule_does_not_create_first_match_fallback() -> None:
    contract, runtime = _batch4_modules()
    wrong = _rule(contract, answer_type="NUMERIC")
    exact = _rule(contract)
    policy = _policy(contract, rules=(wrong, exact))
    result, *_ = _resolve(contract, runtime, policy=policy)
    assert result.selected_capability_ref == exact.capability_ref


def test_post_construction_duplicate_policy_key_is_invalid_source_result() -> None:
    contract, runtime = _batch4_modules()
    policy = _policy(contract)
    duplicate = _rule(contract)
    object.__setattr__(policy, "rules", (policy.rules[0], duplicate))
    with pytest.raises(runtime.SelectionPolicySourceResultError):
        _resolve(contract, runtime, policy=policy)


def test_empty_policy_fails_closed_without_fallback() -> None:
    contract, runtime = _batch4_modules()
    with pytest.raises(runtime.EvaluatorSelectionMissingRuleError):
        _resolve(contract, runtime, policy=_policy(contract, rules=()))


def test_selected_capability_must_claim_exact_answer_type_and_language() -> None:
    contract, runtime = _batch4_modules()
    for record in (
        _capability_record(answer_types=()),
        _capability_record(answer_types=("short_text",)),
        _capability_record(languages=()),
        _capability_record(languages=("EN",)),
    ):
        with pytest.raises(runtime.EvaluatorCapabilitySupportMismatchError):
            _resolve(contract, runtime, capability_records=(record,))


def test_status_and_modality_do_not_become_execution_eligibility_in_batch4() -> None:
    contract, runtime = _batch4_modules()
    for status in (
        EvaluatorCapabilityStatus.VALIDATED,
        EvaluatorCapabilityStatus.PILOT,
        EvaluatorCapabilityStatus.DISABLED,
    ):
        record = _capability_record(status=status, modalities=())
        result, *_ = _resolve(contract, runtime, capability_records=(record,))
        assert result.resolved_capability.record.status is status
        assert result.resolved_capability.record.supported_modalities == ()


def test_native_if1_missing_error_remains_if1_owned() -> None:
    contract, runtime = _batch4_modules()
    with pytest.raises(EvaluatorCapabilityMissingError):
        _resolve(contract, runtime, capability_records=())


def test_native_if1_ambiguity_error_remains_if1_owned() -> None:
    contract, runtime = _batch4_modules()
    record = _capability_record()
    with pytest.raises(EvaluatorCapabilityAmbiguityError):
        _resolve(contract, runtime, capability_records=(record, record))


def test_native_if1_binding_error_remains_if1_owned() -> None:
    contract, runtime = _batch4_modules()
    wrong_ref = _capability_ref(evaluator_id="other-evaluator")
    wrong_record = _capability_record(capability_ref=wrong_ref)
    with pytest.raises(EvaluatorCapabilityBindingError):
        _resolve(contract, runtime, capability_records=(wrong_record,))


def test_native_if1_source_execution_error_remains_if1_owned() -> None:
    contract, runtime = _batch4_modules()
    source = _ExplodingCapabilitySource()
    with pytest.raises(EvaluatorCapabilitySourceExecutionError) as excinfo:
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(_classification(contract)),
            policy_source=_PolicySource(_policy(contract)),
            capability_source=source,
        )
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert len(source.calls) == 1


def test_native_if1_source_result_error_remains_if1_owned() -> None:
    contract, runtime = _batch4_modules()
    source = _MalformedCapabilitySource()
    with pytest.raises(EvaluatorCapabilitySourceResultError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=_ClassificationSource(_classification(contract)),
            policy_source=_PolicySource(_policy(contract)),
            capability_source=source,
        )
    assert len(source.calls) == 1


def test_selection_result_snapshots_classification_policy_and_capability_identity() -> None:
    contract, runtime = _batch4_modules()
    classification = _classification(contract)
    policy = _policy(contract)
    record = _capability_record()
    result, *_ = _resolve(
        contract,
        runtime,
        classification=classification,
        policy=policy,
        capability_records=(record,),
    )

    object.__setattr__(classification, "answer_type", "MUTATED")
    object.__setattr__(classification.grading_spec_ref, "id", "MUTATED")
    object.__setattr__(policy.policy_ref, "policy_id", "MUTATED")
    object.__setattr__(
        policy.rules[0].capability_ref.evaluator_metadata,
        "evaluator_id",
        "MUTATED",
    )
    object.__setattr__(record.capability_ref.evaluator_metadata, "evaluator_id", "MUTATED")

    assert result.classification.answer_type == "SHORT_TEXT"
    assert result.classification.grading_spec_ref == GradingSpecRef(id="SPEC-1", version=1)
    assert result.policy_ref.policy_id == "IF2-POLICY"
    assert result.selected_capability_ref.evaluator_metadata.evaluator_id == "gradified-direct-text"
    assert (
        result.resolved_capability.record.capability_ref.evaluator_metadata.evaluator_id
        == "gradified-direct-text"
    )


def test_selection_result_is_immutable_after_resolution() -> None:
    contract, runtime = _batch4_modules()
    result, *_ = _resolve(contract, runtime)
    with pytest.raises(AttributeError):
        result.context_policy = ContextPolicy.REFERENCE_ONLY
    with pytest.raises(AttributeError):
        result.selected_capability_ref = _capability_ref(evaluator_id="MUTATED")


def test_batch4_contract_exposes_no_grading_mode_subject_evidence_or_execution_fields() -> None:
    contract, _ = _batch4_modules()
    classification_fields = {
        field.name for field in fields(contract.QuestionEvaluationClassification)
    }
    rule_fields = {field.name for field in fields(contract.EvaluatorSelectionRule)}
    policy_fields = {field.name for field in fields(contract.EvaluatorSelectionPolicy)}

    forbidden = {
        "grading_mode",
        "subject",
        "question_text",
        "rubric",
        "evidence",
        "modality",
        "status",
        "evaluation_attempt_id",
        "authorized",
    }
    assert classification_fields.isdisjoint(forbidden)
    assert rule_fields.isdisjoint(forbidden)
    assert policy_fields.isdisjoint(forbidden)


def test_policy_rule_not_hardcoded_default_owns_selected_capability_identity() -> None:
    contract, runtime = _batch4_modules()
    alternate_ref = _capability_ref(
        evaluator_id="gradified-alternate-semantic",
        evaluator_version="7",
        record_version=9,
    )
    alternate_rule = _rule(contract, capability_ref=alternate_ref)
    alternate_policy = _policy(contract, rules=(alternate_rule,))
    alternate_record = _capability_record(capability_ref=alternate_ref)

    result, _, _, capability_source = _resolve(
        contract,
        runtime,
        policy=alternate_policy,
        capability_records=(alternate_record,),
    )

    assert result.selected_capability_ref == alternate_ref
    assert result.resolved_capability.record.capability_ref == alternate_ref
    assert capability_source.calls == [alternate_ref]


def test_classification_source_values_drive_exact_mapping_not_question_text_inference() -> None:
    contract, runtime = _batch4_modules()
    authority = _question_authority(context_policy=ContextPolicy.DIRECT)
    alternate_ref = _capability_ref(
        evaluator_id="gradified-unitless-numeric",
        evaluator_version="2",
        record_version=3,
    )
    classification = _classification(
        contract,
        answer_type="NUMERIC",
        language="kn",
    )
    policy = _policy(
        contract,
        rules=(
            _rule(
                contract,
                answer_type="NUMERIC",
                language="kn",
                capability_ref=alternate_ref,
            ),
        ),
    )
    record = _capability_record(
        capability_ref=alternate_ref,
        answer_types=("NUMERIC",),
        languages=("kn",),
    )

    result, *_ = _resolve(
        contract,
        runtime,
        question_authority=authority,
        classification=classification,
        policy=policy,
        capability_records=(record,),
    )

    assert authority.question_text == "Explain the required result."
    assert result.classification.answer_type == "NUMERIC"
    assert result.classification.language == "kn"
    assert result.selected_capability_ref == alternate_ref


def test_classification_binding_failure_stops_policy_and_capability_sources() -> None:
    contract, runtime = _batch4_modules()
    authority = _question_authority()
    classification_source = _ClassificationSource(
        _classification(contract, question_id="Q-X")
    )
    policy_source = _PolicySource(_policy(contract))
    capability_source = _CapabilitySource((_capability_record(),))

    with pytest.raises(runtime.QuestionClassificationBindingError):
        runtime.resolve_question_evaluator_selection(
            question_authority=authority,
            classification_source=classification_source,
            policy_source=policy_source,
            capability_source=capability_source,
        )

    assert classification_source.calls == [(authority.grading_spec_ref, authority.question_id)]
    assert policy_source.calls == 0
    assert capability_source.calls == []


def test_missing_policy_rule_stops_before_if1_source_lookup() -> None:
    contract, runtime = _batch4_modules()
    classification_source = _ClassificationSource(_classification(contract))
    policy_source = _PolicySource(_policy(contract, rules=()))
    capability_source = _CapabilitySource((_capability_record(),))

    with pytest.raises(runtime.EvaluatorSelectionMissingRuleError):
        runtime.resolve_question_evaluator_selection(
            question_authority=_question_authority(),
            classification_source=classification_source,
            policy_source=policy_source,
            capability_source=capability_source,
        )

    assert capability_source.calls == []


def test_policy_revalidates_mutated_nested_rule_and_capability_reference() -> None:
    contract, _ = _batch4_modules()
    policy = _policy(contract)
    object.__setattr__(policy.rules[0], "context_policy", "DIRECT")
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        contract.validate_evaluator_selection_policy(policy)

    policy = _policy(contract)
    object.__setattr__(policy.rules[0].capability_ref, "record_version", 0)
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        contract.validate_evaluator_selection_policy(policy)


def test_policy_revalidates_mutated_policy_identity() -> None:
    contract, _ = _batch4_modules()
    policy = _policy(contract)
    object.__setattr__(policy.policy_ref, "version", 0)
    with pytest.raises(contract.EvaluatorSelectionPolicyContractError):
        contract.validate_evaluator_selection_policy(policy)


class _MutatingClassificationLookupKeySource:
    def __init__(self, contract: Any) -> None:
        self.contract = contract

    def resolve_question_evaluation_classification(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        object.__setattr__(grading_spec_ref, "id", "MUTATED-BY-SOURCE")
        return _classification(self.contract, question_id=question_id)


def test_classification_source_receives_snapshot_not_mutable_authority_reference() -> None:
    contract, runtime = _batch4_modules()
    authority = _question_authority()
    result = runtime.resolve_question_evaluator_selection(
        question_authority=authority,
        classification_source=_MutatingClassificationLookupKeySource(contract),
        policy_source=_PolicySource(_policy(contract)),
        capability_source=_CapabilitySource((_capability_record(),)),
    )

    assert authority.grading_spec_ref == GradingSpecRef(id="SPEC-1", version=1)
    assert result.classification.grading_spec_ref == authority.grading_spec_ref
