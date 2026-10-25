"""Verify benchmark corpus and source continuity without deciding academic quality.

Teacher annotation reference values in this manifest are assertions to be
verified by an authenticated integration issuer. Validation establishes exact
shape, bounds and non-overlap only; it grants neither protected reads nor
permission to execute or claim benchmark performance.
"""
from __future__ import annotations

from dataclasses import dataclass


class BenchmarkSourceDenied(ValueError):
    """Malformed or cross-bound benchmark source/provenance."""


def _id(value: object, max_chars: int) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > max_chars:
        raise BenchmarkSourceDenied('Invalid benchmark source identity.')
    return value


def _sha(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise BenchmarkSourceDenied('Invalid benchmark source digest.')
    return value


@dataclass(frozen=True, slots=True)
class BenchmarkCaseReference:
    """Reference, not proof, of an owner-authenticated teacher-labeled case."""
    case_ref: str
    teacher_annotation_ref: str
    teacher_annotation_revision: str
    teacher_annotation_sha256: str


@dataclass(frozen=True, slots=True)
class BenchmarkSourceManifest:
    tenant_ref: str
    benchmark_run_ref: str
    source_policy_id: str
    source_policy_version: str
    dataset_ref: str
    dataset_revision: str
    dataset_sha256: str
    evaluator_ref: str
    configuration_ref: str
    development: tuple[BenchmarkCaseReference, ...]
    calibration: tuple[BenchmarkCaseReference, ...]
    heldout: tuple[BenchmarkCaseReference, ...]


@dataclass(frozen=True, slots=True)
class AdmittedBenchmarkSourceShape:
    """Non-authoritative corpus structure; must not be used as an execution grant."""
    manifest: BenchmarkSourceManifest
    evidence_type: str = 'STRUCTURAL_BENCHMARK_SOURCE_UNVERIFIED'


def _admit_source_shape(*, source: BenchmarkSourceManifest,
                                 max_identifier_characters: int,
                                 max_cases: int) -> AdmittedBenchmarkSourceShape:
    """Validate a finite, split-isolated manifest before any protected read.

    Does not read source data, authorize an evaluator, compute metrics, or
    certify teacher annotations, label provenance, academic results or an
    approval. Caller-supplied bounds are resource controls, not policy facts.
    """
    if (type(max_identifier_characters) is not int or max_identifier_characters <= 0
            or type(max_cases) is not int or not 0 < max_cases <= 2**31-1
            or type(source) is not BenchmarkSourceManifest):
        raise BenchmarkSourceDenied('Unadmitted benchmark source profile.')
    attrs = tuple(_id(getattr(source, name), max_identifier_characters) for name in (
        'tenant_ref', 'benchmark_run_ref', 'source_policy_id', 'source_policy_version',
        'dataset_ref', 'dataset_revision', 'evaluator_ref', 'configuration_ref'))
    digest = _sha(source.dataset_sha256)
    case_splits = (source.development, source.calibration, source.heldout)
    if any(type(group) is not tuple for group in case_splits):
        raise BenchmarkSourceDenied('Benchmark case splits must be finite exact tuples.')
    if any(len(group) > max_cases for group in case_splits) or sum(map(len, case_splits)) > max_cases:
        raise BenchmarkSourceDenied('Benchmark source resource limit exceeded.')
    # The three separate datasets are an engineering benchmark-evidence
    # prerequisite, not a fabricated academic acceptance threshold.
    if not all(case_splits):
        raise BenchmarkSourceDenied('Development, calibration and held-out sources required.')
    seen_cases: set[str] = set()
    seen_labels: set[str] = set()
    admitted_splits = []
    for group in case_splits:
        admitted = []
        for case in group:
            if type(case) is not BenchmarkCaseReference:
                raise BenchmarkSourceDenied('Malformed benchmark case reference.')
            case_ref = _id(case.case_ref, max_identifier_characters)
            label_ref = _id(case.teacher_annotation_ref, max_identifier_characters)
            label_revision = _id(case.teacher_annotation_revision, max_identifier_characters)
            label_sha = _sha(case.teacher_annotation_sha256)
            # Avoid training/heldout leakage through repeated cases or teacher
            # annotation revisions. Even the same annotation with a different
            # revision refers to a shared source and is rejected.
            if case_ref in seen_cases or label_ref in seen_labels:
                raise BenchmarkSourceDenied('Benchmark case or label reused across splits.')
            seen_cases.add(case_ref)
            seen_labels.add(label_ref)
            admitted.append(BenchmarkCaseReference(case_ref, label_ref, label_revision, label_sha))
        admitted_splits.append(tuple(admitted))
    return AdmittedBenchmarkSourceShape(BenchmarkSourceManifest(
        *attrs[:6], digest, *attrs[6:], *admitted_splits))


def admit_benchmark_source_shape(*, source: BenchmarkSourceManifest,
                                 max_identifier_characters: int,
                                 max_cases: int) -> AdmittedBenchmarkSourceShape:
    """Public fail-closed boundary with no private exception context."""
    try:
        return _admit_source_shape(source=source,
                                   max_identifier_characters=max_identifier_characters,
                                   max_cases=max_cases)
    except Exception:
        error = BenchmarkSourceDenied('Benchmark source not admitted.')
        try:
            raise error
        finally:
            error.__cause__ = None
            error.__context__ = None
            error.__suppress_context__ = True
