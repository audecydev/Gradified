from __future__ import annotations

import inspect

import pytest

from grading.capability_registry import (
    EvaluatorCapabilityAmbiguityError,
    EvaluatorCapabilityBindingError,
    EvaluatorCapabilityMissingError,
    EvaluatorCapabilitySourceExecutionError,
    EvaluatorCapabilitySourceResultError,
    ResolvedEvaluatorCapability,
    resolve_evaluator_capability,
)
from grading.contracts.capability import (
    EvaluatorCapabilityRecord,
    EvaluatorCapabilityRef,
    EvaluatorCapabilityStatus,
    InvalidEvaluatorCapabilityRecordError,
    InvalidEvaluatorCapabilityRefError,
)
from grading.contracts.evaluation import EvaluatorMetadata


def _ref(
    evaluator_id: str = "evaluator-a",
    evaluator_version: str = "1",
    record_version: int = 1,
) -> EvaluatorCapabilityRef:
    return EvaluatorCapabilityRef(
        evaluator_metadata=EvaluatorMetadata(evaluator_id, evaluator_version),
        record_version=record_version,
    )


def _record(
    *,
    ref: EvaluatorCapabilityRef | None = None,
    status: EvaluatorCapabilityStatus = EvaluatorCapabilityStatus.PILOT,
) -> EvaluatorCapabilityRecord:
    return EvaluatorCapabilityRecord(
        schema_version="1",
        capability_ref=ref or _ref(),
        status=status,
        supported_answer_types=("NUMERIC",),
        supported_languages=(),
        supported_modalities=("TEXT",),
        tested_grade_range=None,
        domain_scope="bounded-test-scope",
        verification_mechanisms=("contract-tests",),
        benchmark_version=None,
        known_failure_modes=(),
        cost_profile=None,
        latency_profile=None,
    )


class _Source:
    def __init__(self, records: object) -> None:
        self.records = records
        self.calls: list[EvaluatorCapabilityRef] = []

    def find_exact_capabilities(self, *, capability_ref: EvaluatorCapabilityRef):
        self.calls.append(capability_ref)
        return self.records


def test_exact_record_resolves_and_returns_independent_snapshot() -> None:
    requested = _ref()
    source_record = _record(ref=_ref())
    source = _Source((source_record,))

    resolved = resolve_evaluator_capability(capability_ref=requested, source=source)

    assert type(resolved) is ResolvedEvaluatorCapability
    assert resolved.record == source_record
    assert resolved.record is not source_record
    assert resolved.record.capability_ref is not source_record.capability_ref
    assert resolved.record.capability_ref.evaluator_metadata is not source_record.capability_ref.evaluator_metadata
    assert len(source.calls) == 1
    assert source.calls[0] == requested
    assert source.calls[0] is not requested


def test_source_mutation_after_resolution_does_not_rewrite_resolved_snapshot() -> None:
    source_record = _record()
    resolved = resolve_evaluator_capability(capability_ref=_ref(), source=_Source((source_record,)))
    object.__setattr__(source_record, "status", EvaluatorCapabilityStatus.DISABLED)
    assert resolved.record.status is EvaluatorCapabilityStatus.PILOT


@pytest.mark.parametrize(
    "status",
    [
        EvaluatorCapabilityStatus.VALIDATED,
        EvaluatorCapabilityStatus.PILOT,
        EvaluatorCapabilityStatus.DISABLED,
    ],
)
def test_status_is_metadata_and_does_not_block_or_authorize_resolution(status: EvaluatorCapabilityStatus) -> None:
    resolved = resolve_evaluator_capability(
        capability_ref=_ref(),
        source=_Source((_record(status=status),)),
    )
    assert resolved.record.status is status


def test_missing_exact_record_is_distinct() -> None:
    with pytest.raises(EvaluatorCapabilityMissingError):
        resolve_evaluator_capability(capability_ref=_ref(), source=_Source(()))


def test_duplicate_exact_records_are_ambiguous() -> None:
    record = _record()
    with pytest.raises(EvaluatorCapabilityAmbiguityError):
        resolve_evaluator_capability(capability_ref=_ref(), source=_Source((record, record)))


def test_wrong_returned_reference_is_binding_failure() -> None:
    wrong = _record(ref=_ref(record_version=2))
    with pytest.raises(EvaluatorCapabilityBindingError):
        resolve_evaluator_capability(capability_ref=_ref(record_version=1), source=_Source((wrong,)))


def test_source_exception_remains_source_execution_failure() -> None:
    class FailingSource:
        def find_exact_capabilities(self, *, capability_ref: EvaluatorCapabilityRef):
            raise RuntimeError("backend exploded")

    with pytest.raises(EvaluatorCapabilitySourceExecutionError) as captured:
        resolve_evaluator_capability(capability_ref=_ref(), source=FailingSource())
    assert isinstance(captured.value.__cause__, RuntimeError)


@pytest.mark.parametrize("foreign_result", [None, [], {}, "record"])
def test_source_must_return_exact_tuple(foreign_result: object) -> None:
    with pytest.raises(EvaluatorCapabilitySourceResultError):
        resolve_evaluator_capability(capability_ref=_ref(), source=_Source(foreign_result))


def test_tuple_subclass_is_rejected() -> None:
    class TupleSubclass(tuple):
        pass

    with pytest.raises(EvaluatorCapabilitySourceResultError):
        resolve_evaluator_capability(
            capability_ref=_ref(),
            source=_Source(TupleSubclass((_record(),))),
        )


def test_foreign_record_is_rejected_before_attribute_dispatch() -> None:
    class ForeignRecord:
        @property
        def capability_ref(self) -> object:
            raise AssertionError("foreign record attribute accessed")

    with pytest.raises(EvaluatorCapabilitySourceResultError):
        resolve_evaluator_capability(capability_ref=_ref(), source=_Source((ForeignRecord(),)))


def test_current_record_mutation_is_detected_before_resolution() -> None:
    record = _record()
    object.__setattr__(record, "supported_answer_types", ["NUMERIC"])
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        resolve_evaluator_capability(capability_ref=_ref(), source=_Source((record,)))


def test_current_nested_reference_mutation_is_detected_before_binding() -> None:
    record = _record()
    object.__setattr__(record.capability_ref, "record_version", True)
    with pytest.raises(InvalidEvaluatorCapabilityRecordError):
        resolve_evaluator_capability(capability_ref=_ref(), source=_Source((record,)))


def test_caller_reference_current_mutation_is_detected_before_source_call() -> None:
    ref = _ref()
    object.__setattr__(ref, "record_version", True)
    source = _Source((_record(),))
    with pytest.raises(InvalidEvaluatorCapabilityRefError):
        resolve_evaluator_capability(capability_ref=ref, source=source)
    assert source.calls == []


def test_hostile_source_cannot_rewrite_the_retained_requested_identity() -> None:
    class MutatingSource:
        def find_exact_capabilities(self, *, capability_ref: EvaluatorCapabilityRef):
            object.__setattr__(capability_ref, "record_version", 2)
            return (_record(ref=_ref(record_version=2)),)

    with pytest.raises(EvaluatorCapabilityBindingError):
        resolve_evaluator_capability(capability_ref=_ref(record_version=1), source=MutatingSource())


def test_lookup_has_no_latest_fallback_or_routing_parameters() -> None:
    signature = inspect.signature(resolve_evaluator_capability)
    assert tuple(signature.parameters) == ("capability_ref", "source")
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())


def test_empty_scope_metadata_resolves_without_becoming_a_wildcard_api() -> None:
    record = _record()
    object.__setattr__(record, "supported_answer_types", ())
    object.__setattr__(record, "supported_languages", ())
    object.__setattr__(record, "supported_modalities", ())
    resolved = resolve_evaluator_capability(capability_ref=_ref(), source=_Source((record,)))
    assert resolved.record.supported_answer_types == ()
    assert not hasattr(resolved, "supports")
    assert not hasattr(resolved, "select")


def test_resolved_container_is_not_execution_proof_or_authorization_api() -> None:
    resolved = ResolvedEvaluatorCapability(record=_record())
    assert not hasattr(resolved, "evaluation_attempt_id")
    assert not hasattr(resolved, "authorized")
    assert not hasattr(resolved, "execute")
