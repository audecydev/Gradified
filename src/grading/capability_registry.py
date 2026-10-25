from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grading.contracts.capability import (
    EvaluatorCapabilityRecord,
    EvaluatorCapabilityRef,
    InvalidEvaluatorCapabilityRecordError,
    InvalidEvaluatorCapabilityRefError,
    validate_evaluator_capability_record,
    validate_evaluator_capability_ref,
)
from grading.contracts.evaluation import EvaluatorMetadata


class EvaluatorCapabilityResolutionError(Exception):
    """Base class for expected evaluator capability resolution exact-resolution failures."""


class EvaluatorCapabilitySourceExecutionError(EvaluatorCapabilityResolutionError):
    """Configured capability source failed during exact lookup."""


class EvaluatorCapabilitySourceResultError(EvaluatorCapabilityResolutionError):
    """Configured source returned an inadmissible result container/value."""


class EvaluatorCapabilityMissingError(EvaluatorCapabilityResolutionError):
    """No record exists for the exact caller-supplied capability reference."""


class EvaluatorCapabilityAmbiguityError(EvaluatorCapabilityResolutionError):
    """More than one record exists for the exact caller-supplied reference."""


class EvaluatorCapabilityBindingError(EvaluatorCapabilityResolutionError):
    """The materialized record does not bind the exact requested reference."""


class EvaluatorCapabilitySource(Protocol):
    """Configured exact-reference source; conformance does not authenticate it."""

    def find_exact_capabilities(
        self,
        *,
        capability_ref: EvaluatorCapabilityRef,
    ) -> tuple[EvaluatorCapabilityRecord, ...]:
        ...


@dataclass(frozen=True, slots=True)
class ResolvedEvaluatorCapability:
    """Read-only snapshot of one exact capability record.

    Object/class identity is not proof that this resolver ran and is not
    evaluator-execution or workflow authorization.
    """

    record: EvaluatorCapabilityRecord

    def __post_init__(self) -> None:
        if type(self.record) is not EvaluatorCapabilityRecord:
            raise TypeError(
                "ResolvedEvaluatorCapability.record must be an exact EvaluatorCapabilityRecord."
            )
        validate_evaluator_capability_record(self.record)


def _refs_equal(left: EvaluatorCapabilityRef, right: EvaluatorCapabilityRef) -> bool:
    left_metadata = object.__getattribute__(left, "evaluator_metadata")
    right_metadata = object.__getattribute__(right, "evaluator_metadata")
    return (
        object.__getattribute__(left_metadata, "evaluator_id")
        == object.__getattribute__(right_metadata, "evaluator_id")
        and object.__getattribute__(left_metadata, "version")
        == object.__getattribute__(right_metadata, "version")
        and object.__getattribute__(left, "record_version")
        == object.__getattribute__(right, "record_version")
    )


def _snapshot_ref(value: EvaluatorCapabilityRef) -> EvaluatorCapabilityRef:
    metadata = object.__getattribute__(value, "evaluator_metadata")
    return EvaluatorCapabilityRef(
        evaluator_metadata=EvaluatorMetadata(
            evaluator_id=object.__getattribute__(metadata, "evaluator_id"),
            version=object.__getattribute__(metadata, "version"),
        ),
        record_version=object.__getattribute__(value, "record_version"),
    )


def _snapshot_record(value: EvaluatorCapabilityRecord) -> EvaluatorCapabilityRecord:
    """Copy validated primitive/tuple state so later source mutation cannot rewrite the result."""

    return EvaluatorCapabilityRecord(
        schema_version=object.__getattribute__(value, "schema_version"),
        capability_ref=_snapshot_ref(object.__getattribute__(value, "capability_ref")),
        status=object.__getattribute__(value, "status"),
        supported_answer_types=object.__getattribute__(value, "supported_answer_types"),
        supported_languages=object.__getattribute__(value, "supported_languages"),
        supported_modalities=object.__getattribute__(value, "supported_modalities"),
        tested_grade_range=object.__getattribute__(value, "tested_grade_range"),
        domain_scope=object.__getattribute__(value, "domain_scope"),
        verification_mechanisms=object.__getattribute__(value, "verification_mechanisms"),
        benchmark_version=object.__getattribute__(value, "benchmark_version"),
        known_failure_modes=object.__getattribute__(value, "known_failure_modes"),
        cost_profile=object.__getattribute__(value, "cost_profile"),
        latency_profile=object.__getattribute__(value, "latency_profile"),
    )


def resolve_evaluator_capability(
    *,
    capability_ref: EvaluatorCapabilityRef,
    source: EvaluatorCapabilitySource,
) -> ResolvedEvaluatorCapability:
    """Resolve one explicitly selected capability record by exact identity/version only."""

    try:
        validate_evaluator_capability_ref(capability_ref)
    except InvalidEvaluatorCapabilityRefError:
        raise

    # Pass a stable snapshot to the source; later caller mutation cannot alter the
    # exact lookup key observed by the configured integration seam.
    requested = _snapshot_ref(capability_ref)
    lookup_ref = _snapshot_ref(requested)

    try:
        records = source.find_exact_capabilities(capability_ref=lookup_ref)
    except Exception as exc:
        raise EvaluatorCapabilitySourceExecutionError(
            "Evaluator capability source failed during exact-reference lookup."
        ) from exc

    if type(records) is not tuple:
        raise EvaluatorCapabilitySourceResultError(
            "Evaluator capability source must return an exact tuple."
        )
    if not records:
        raise EvaluatorCapabilityMissingError(
            "No evaluator capability record exists for the exact requested reference."
        )
    if len(records) > 1:
        raise EvaluatorCapabilityAmbiguityError(
            "More than one evaluator capability record exists for the exact requested reference."
        )

    record = records[0]
    if type(record) is not EvaluatorCapabilityRecord:
        raise EvaluatorCapabilitySourceResultError(
            "Evaluator capability source returned a non-capability-record value."
        )

    # Revalidate current source-owned state before using any record fields.
    validate_evaluator_capability_record(record)
    snapshot = _snapshot_record(record)

    if not _refs_equal(snapshot.capability_ref, requested):
        raise EvaluatorCapabilityBindingError(
            "Resolved evaluator capability record does not bind the exact requested reference."
        )

    return ResolvedEvaluatorCapability(record=snapshot)
