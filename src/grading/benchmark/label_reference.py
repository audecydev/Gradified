"""teacher-label reference read-only teacher-label *reference* continuity for nonacademic replay.

A trusted integration adapter must authenticate the issuer, tenant, permissions,
label revision and revocation.  This module checks the exact response scope but
cannot verify those external facts, the label content, or any academic metric.
No protected dataset read, benchmark execution, grade or publication occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.benchmark.offline_trial import (
    OfflineTrialEvidence, OfflineTrialRequest, _digest, _identifier, _number, _request,
)
from grading.benchmark.source_bound_trial import SourceBoundOfflineReplayEvidence


class LabelReferenceDenied(ValueError):
    """No label-reference continuity evidence can be admitted."""


class LabelReferenceIndeterminate(RuntimeError):
    """The authority response was uncertain; do not infer label authenticity."""


def _public(error: Exception) -> None:
    try:
        raise error
    finally:
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True


def _id(value: object, limit: int) -> str:
    try:
        return _identifier(value, limit)
    except Exception:
        raise LabelReferenceDenied('Malformed label-reference identity.') from None


def _sha(value: object) -> str:
    try:
        return _digest(value)
    except Exception:
        raise LabelReferenceDenied('Malformed label-reference digest.') from None


@dataclass(frozen=True, slots=True)
class LabelReferenceQuery:
    tenant_ref: str
    run_ref: str
    trial_request_ref: str
    trial_ref: str
    dataset_ref: str
    dataset_revision: str
    dataset_sha256: str
    read_scope_ref: str
    case_ref: str
    split: str
    source_policy_id: str
    source_policy_version: str
    teacher_annotation_ref: str
    teacher_annotation_revision: str
    teacher_annotation_sha256: str


class LabelReferenceStatus(Enum):
    CURRENT = 'CURRENT'
    REVOKED = 'REVOKED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class LabelReferenceFact:
    query: LabelReferenceQuery
    status: LabelReferenceStatus
    issuer_ref: str | None
    issuer_version: str | None
    attestation_ref: str | None


@dataclass(frozen=True, slots=True)
class LabelReferenceContinuity:
    """Issuer-reported reference only; never a teacher mark or quality result."""
    query: LabelReferenceQuery
    issuer_ref: str
    issuer_version: str
    attestation_ref: str
    output_sha256: str
    observation_event_ref: str
    evidence_type: str = 'ISSUER_REPORTED_REFERENCE_NONACADEMIC_OFFLINE_REPLAY'


class TeacherLabelReferenceAuthority(Protocol):
    def resolve_label_reference(self, *, query: LabelReferenceQuery) -> LabelReferenceFact: ...


def _query(value: object, limit: int) -> LabelReferenceQuery:
    if type(value) is not LabelReferenceQuery:
        raise LabelReferenceDenied('Foreign label-reference query.')
    names = (
        'tenant_ref', 'run_ref', 'trial_request_ref', 'trial_ref',
        'dataset_ref', 'dataset_revision', 'read_scope_ref', 'case_ref',
        'source_policy_id', 'source_policy_version', 'teacher_annotation_ref',
        'teacher_annotation_revision',
    )
    admitted = {name: _id(getattr(value, name), limit) for name in names}
    if type(value.split) is not str or value.split not in ('development', 'calibration', 'heldout'):
        raise LabelReferenceDenied('Foreign benchmark split.')
    return LabelReferenceQuery(
        admitted['tenant_ref'], admitted['run_ref'], admitted['trial_request_ref'],
        admitted['trial_ref'], admitted['dataset_ref'], admitted['dataset_revision'],
        _sha(value.dataset_sha256), admitted['read_scope_ref'], admitted['case_ref'],
        value.split, admitted['source_policy_id'], admitted['source_policy_version'],
        admitted['teacher_annotation_ref'], admitted['teacher_annotation_revision'],
        _sha(value.teacher_annotation_sha256),
    )


def _source_evidence(value: object, limit: int) -> tuple[LabelReferenceQuery, str, str]:
    if (type(value) is not SourceBoundOfflineReplayEvidence
            or type(value.evidence_type) is not str
            or value.evidence_type != 'STRUCTURALLY_BOUND_UNVERIFIED_OFFLINE_REPLAY'
            or type(value.observation) is not OfflineTrialEvidence):
        raise LabelReferenceDenied('Foreign offline replay evidence.')
    observation = value.observation
    request = _request(observation.request, limit)
    if (type(observation.evidence_type) is not str
            or observation.evidence_type != 'NON_AUTHORITATIVE_OFFLINE_REPLAY'
            or type(observation.output_size_bytes) is not int
            or not 0 < observation.output_size_bytes <= 2**63-1):
        raise LabelReferenceDenied('Foreign replay observation.')
    output_sha = _sha(observation.output_sha256)
    trial_ref = _id(observation.trial_ref, limit)
    event_ref = _id(observation.event_ref, limit)
    _id(observation.policy_id, limit)
    _id(observation.policy_version, limit)
    if (type(value.case_ref) is not str or value.case_ref != request.case_ref
            or type(value.benchmark_source_ref) is not str
            or value.benchmark_source_ref != request.dataset_ref
            or type(value.benchmark_source_revision) is not str
            or value.benchmark_source_revision != request.dataset_revision
            or type(value.benchmark_source_sha256) is not str
            or value.benchmark_source_sha256 != request.dataset_sha256):
        raise LabelReferenceDenied('Source/replay identity mismatch.')
    query = _query(LabelReferenceQuery(
        request.tenant_ref, request.run_ref, request.trial_request_ref, trial_ref,
        request.dataset_ref, request.dataset_revision, request.dataset_sha256,
        request.read_scope_ref, request.case_ref, value.split,
        value.source_policy_id, value.source_policy_version,
        value.teacher_annotation_ref, value.teacher_annotation_revision,
        value.teacher_annotation_sha256,
    ), limit)
    return query, output_sha, event_ref


def _fact(value: object, original: LabelReferenceQuery, limit: int) -> LabelReferenceFact:
    if type(value) is not LabelReferenceFact or type(value.status) is not LabelReferenceStatus:
        raise LabelReferenceDenied('Foreign label-reference authority response.')
    if _query(value.query, limit) != original:
        raise LabelReferenceDenied('Label-reference response has wrong scope.')
    if value.status is LabelReferenceStatus.CURRENT:
        ids = tuple(_id(getattr(value, field), limit) for field in (
            'issuer_ref', 'issuer_version', 'attestation_ref'))
        return LabelReferenceFact(original, LabelReferenceStatus.CURRENT, *ids)
    if any(getattr(value, f) is not None for f in ('issuer_ref', 'issuer_version', 'attestation_ref')):
        raise LabelReferenceDenied('Noncurrent authority response supplied positive evidence.')
    return LabelReferenceFact(original, value.status, None, None, None)


class ReadOnlyTeacherLabelReferenceContinuity:
    """One read-only query of a *trusted installed* reference issuer.

    This deliberately does not accept a caller-constructed `CURRENT` as an
    authority. The installed adapter must be authenticated in the real
    composition root. A successful result is only reference continuity, not
    an attested teacher mark, grade agreement, or academic qualification.
    """

    __slots__ = ('_installation', '_lock', '_used')

    def __init__(self, *, evidence: SourceBoundOfflineReplayEvidence,
                 authority: TeacherLabelReferenceAuthority,
                 max_identifier_characters: int) -> None:
        try:
            limit = _number(max_identifier_characters)
            query, digest, event_ref = _source_evidence(evidence, limit)
            operation = getattr(authority, 'resolve_label_reference')
            if not callable(operation):
                raise LabelReferenceDenied('Label authority operation missing.')
            object.__setattr__(self, '_installation', (query, digest, event_ref, operation, limit))
            object.__setattr__(self, '_lock', Lock())
            object.__setattr__(self, '_used', False)
        except Exception:
            _public(LabelReferenceDenied('Label-reference continuity not installed.'))

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError('Installed label-reference continuity cannot be rebound.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError('Installed label-reference continuity cannot be deleted.')
        object.__delattr__(self, name)

    def reconcile(self) -> LabelReferenceContinuity:
        with self._lock:
            if self._used:
                _public(LabelReferenceDenied('Label-reference query already consumed.'))
            object.__setattr__(self, '_used', True)
        original, output_sha, event_ref, operation, limit = self._installation
        query = _query(original, limit)
        fact = None
        error = None
        try:
            fact = operation(query=query)
        except Exception as exc:
            error = exc
        try:
            if _query(query, limit) != original or _query(original, limit) != original:
                raise LabelReferenceDenied('Label lookup scope mutated.')
        except Exception:
            _public(LabelReferenceIndeterminate('Label lookup scope uncertain.'))
        if error is not None:
            if isinstance(error, LabelReferenceDenied):
                _public(LabelReferenceDenied('Label reference definitively denied.'))
            _public(LabelReferenceIndeterminate('Label lookup outcome uncertain.'))
        try:
            admitted = _fact(fact, original, limit)
        except Exception:
            _public(LabelReferenceDenied('Label lookup response not admitted.'))
        if admitted.status is LabelReferenceStatus.UNKNOWN:
            _public(LabelReferenceIndeterminate('Label reference status unknown.'))
        if admitted.status is LabelReferenceStatus.REVOKED:
            _public(LabelReferenceDenied('Label reference revoked.'))
        return LabelReferenceContinuity(original, admitted.issuer_ref, admitted.issuer_version,
                                        admitted.attestation_ref, output_sha, event_ref)
