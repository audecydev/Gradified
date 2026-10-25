"""Preserve teacher-label reference linkage for offline benchmarks without exposing label content.

Only a backend history adapter can assert atomic durability/replay protection.
This layer binds its acknowledgment to the exact event and never retries an
uncertain write. It does not mint benchmark claim or label authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.benchmark.label_reference import (
    LabelReferenceContinuity, LabelReferenceQuery, _id, _query, _sha,
)


class LabelCustodyDenied(ValueError):
    """Reference linkage cannot be recorded under this request."""


class LabelCustodyIndeterminate(RuntimeError):
    """History outcome uncertain: read-only reconciliation required."""


KIND = 'F33_NONACADEMIC_LABEL_REFERENCE_LINKAGE'


def _public(error: Exception) -> None:
    try:
        raise error
    finally:
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True


def _continuity(value: object, limit: int) -> LabelReferenceContinuity:
    if (type(value) is not LabelReferenceContinuity
            or type(value.evidence_type) is not str
            or value.evidence_type != 'ISSUER_REPORTED_REFERENCE_NONACADEMIC_OFFLINE_REPLAY'):
        raise LabelCustodyDenied('Unadmitted benchmark reference continuity.')
    try:
        query = _query(value.query, limit)
        issuer = _id(value.issuer_ref, limit)
        version = _id(value.issuer_version, limit)
        attestation = _id(value.attestation_ref, limit)
        output = _sha(value.output_sha256)
        event = _id(value.observation_event_ref, limit)
    except Exception:
        raise LabelCustodyDenied('Invalid benchmark reference continuity scope.') from None
    return LabelReferenceContinuity(query, issuer, version, attestation, output, event)


@dataclass(frozen=True, slots=True)
class LabelLinkageEvent:
    continuity: LabelReferenceContinuity
    event_kind: str = KIND


@dataclass(frozen=True, slots=True)
class LabelLinkageReceipt:
    trial_request_ref: str
    observation_event_ref: str
    attestation_ref: str
    event_kind: str
    status: str


class LabelLinkageHistory(Protocol):
    def record_label_linkage(self, *, event: LabelLinkageEvent) -> LabelLinkageReceipt: ...


def _event(value: object, anchor: LabelReferenceContinuity, limit: int) -> LabelLinkageEvent:
    if (type(value) is not LabelLinkageEvent
            or type(value.event_kind) is not str or value.event_kind != KIND
            or _continuity(value.continuity, limit) != anchor):
        raise LabelCustodyDenied('Label-linkage history event mutated.')
    return LabelLinkageEvent(anchor)


def _receipt(value: object, anchor: LabelReferenceContinuity, limit: int) -> LabelLinkageReceipt:
    if type(value) is not LabelLinkageReceipt:
        raise LabelCustodyDenied('Invalid label-linkage history receipt.')
    try:
        ids = tuple(_id(getattr(value, name), limit) for name in (
            'trial_request_ref', 'observation_event_ref', 'attestation_ref'))
    except Exception:
        raise LabelCustodyDenied('Malformed label-linkage acknowledgment.') from None
    if (ids != (anchor.query.trial_request_ref, anchor.observation_event_ref,
                anchor.attestation_ref)
            or type(value.event_kind) is not str or value.event_kind != KIND
            or type(value.status) is not str or value.status != 'RECORDED'):
        raise LabelCustodyDenied('Foreign label-linkage acknowledgment.')
    return LabelLinkageReceipt(*ids, KIND, 'RECORDED')


class OneShotNonAcademicLabelLinkageAudit:
    """One acknowledged write. Does not expose a successful result on uncertainty."""

    __slots__ = ('_installation', '_lock', '_used')

    def __init__(self, *, continuity: LabelReferenceContinuity,
                 history: LabelLinkageHistory, max_identifier_characters: int) -> None:
        try:
            if type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 2**31-1:
                raise LabelCustodyDenied('Invalid audit resource bound.')
            original = _continuity(continuity, max_identifier_characters)
            operation = getattr(history, 'record_label_linkage')
            if not callable(operation):
                raise LabelCustodyDenied('History operation unavailable.')
            object.__setattr__(self, '_installation',
                               (original, operation, max_identifier_characters))
            object.__setattr__(self, '_lock', Lock())
            object.__setattr__(self, '_used', False)
        except Exception:
            _public(LabelCustodyDenied('Label-linkage audit installation denied.'))

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError('Installed label-linkage audit cannot be rebound.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError('Installed label-linkage audit cannot be deleted.')
        object.__delattr__(self, name)

    def record(self) -> LabelLinkageReceipt:
        with self._lock:
            if self._used:
                _public(LabelCustodyDenied('Label-linkage event already attempted.'))
            object.__setattr__(self, '_used', True)
        anchor, write, limit = self._installation
        original = _continuity(anchor, limit)
        event = LabelLinkageEvent(_continuity(original, limit))
        error = None
        result = None
        try:
            result = write(event=event)
        except Exception as exc:
            error = exc
        try:
            if (_event(event, original, limit).continuity != original
                    or _continuity(anchor, limit) != original):
                raise LabelCustodyDenied('Label audit identity changed.')
        except Exception:
            _public(LabelCustodyIndeterminate('Label audit event identity uncertain.'))
        if error is not None:
            _public(LabelCustodyIndeterminate('Label audit write outcome uncertain.'))
        try:
            return _receipt(result, original, limit)
        except Exception:
            _public(LabelCustodyIndeterminate('Label audit receipt uncertain.'))


class LabelLinkageRecoveryStatus(Enum):
    COMMITTED = 'COMMITTED'
    NOT_FOUND = 'NOT_FOUND'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class LabelLinkageRecoveryFact:
    event: LabelLinkageEvent
    status: LabelLinkageRecoveryStatus
    receipt: LabelLinkageReceipt | None


class LabelLinkageRecoveryStore(Protocol):
    def reconcile_label_linkage(self, *, event: LabelLinkageEvent) -> LabelLinkageRecoveryFact: ...


def _recovery(value: object, expected: LabelLinkageEvent, limit: int) -> LabelLinkageRecoveryFact:
    if (type(value) is not LabelLinkageRecoveryFact
            or type(value.status) is not LabelLinkageRecoveryStatus
            or _event(value.event, expected.continuity, limit) != expected):
        raise LabelCustodyDenied('Foreign label-linkage recovery response.')
    if value.status is LabelLinkageRecoveryStatus.COMMITTED:
        receipt = _receipt(value.receipt, expected.continuity, limit)
        return LabelLinkageRecoveryFact(expected, value.status, receipt)
    if value.receipt is not None:
        raise LabelCustodyDenied('Uncommitted linkage recovery contains a receipt.')
    return LabelLinkageRecoveryFact(expected, value.status, None)


class ReadOnlyLabelLinkageRecovery:
    """Inspect a prior linkage event; cannot issue another write or trial."""

    __slots__ = ('_installation', '_lock', '_used')

    def __init__(self, *, continuity: LabelReferenceContinuity,
                 store: LabelLinkageRecoveryStore, max_identifier_characters: int) -> None:
        try:
            if type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 2**31-1:
                raise LabelCustodyDenied('Invalid recovery bound.')
            event = LabelLinkageEvent(_continuity(continuity, max_identifier_characters))
            operation = getattr(store, 'reconcile_label_linkage')
            if not callable(operation):
                raise LabelCustodyDenied('No read-only recovery operation.')
            object.__setattr__(self, '_installation', (event, operation, max_identifier_characters))
            object.__setattr__(self, '_lock', Lock())
            object.__setattr__(self, '_used', False)
        except Exception:
            _public(LabelCustodyDenied('Label-linkage recovery installation denied.'))

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError('Installed linkage recovery cannot be rebound.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError('Installed linkage recovery cannot be deleted.')
        object.__delattr__(self, name)

    def reconcile(self) -> LabelLinkageRecoveryFact:
        with self._lock:
            if self._used:
                _public(LabelCustodyDenied('Linkage recovery already requested.'))
            object.__setattr__(self, '_used', True)
        anchor, operation, limit = self._installation
        expected = _event(anchor, anchor.continuity, limit)
        query = LabelLinkageEvent(_continuity(expected.continuity, limit))
        error = None
        result = None
        try:
            result = operation(event=query)
        except Exception as exc:
            error = exc
        try:
            _event(query, expected.continuity, limit)
            _event(anchor, expected.continuity, limit)
        except Exception:
            _public(LabelCustodyIndeterminate('Linkage recovery request mutated.'))
        if error is not None:
            _public(LabelCustodyIndeterminate('Linkage recovery outcome uncertain.'))
        try:
            return _recovery(result, expected, limit)
        except Exception:
            _public(LabelCustodyIndeterminate('Linkage recovery evidence malformed.'))
