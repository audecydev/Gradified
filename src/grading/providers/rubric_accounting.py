"""reference qualification rubric-generation provider accounting, without granting academic authority.

Captures a separate ``generate(source=...)`` operation; a trusted issuer must
admit an exact generation request before contact. Records UNKNOWN physical
usage because the legacy RubricGenerationProvider does not expose telemetry.
The caller still owns rubric provider ingress parsing, rubric authoring authoring and teacher approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.providers.attempt_accounting import ProviderPhysicalObservation
from grading.providers.rubric_generation import rubric_provider_request_fingerprint
from grading.providers.rubric_ingress import RubricProviderProvenance
from grading.rubric.generator import RubricGenerationInput


class RubricAccountingDenied(ValueError):
    """The configured grant/identity/provenance was definitively not admitted."""


class RubricAccountingIndeterminate(RuntimeError):
    """Provider or audit side effect could have occurred; never retry blindly."""


def _public(error: Exception) -> None:
    try:
        raise error
    finally:
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True


def _id(value: object, limit: int) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > limit:
        raise RubricAccountingDenied('Invalid rubric-accounting identity.')
    return value


def _fingerprint(value: object) -> str:
    if (type(value) is not str or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value)):
        raise RubricAccountingDenied('Invalid rubric-generation fingerprint.')
    return value


@dataclass(frozen=True, slots=True)
class RubricAccountingIdentity:
    tenant_ref: str
    generation_request_ref: str
    operation_ref: str
    event_ref: str
    provider_id: str
    model_id: str
    configuration_ref: str
    source_fingerprint: str


def _identity(value: object, limit: int) -> RubricAccountingIdentity:
    if type(value) is not RubricAccountingIdentity:
        raise RubricAccountingDenied('Invalid rubric-accounting identity type.')
    parts = tuple(_id(getattr(value, n), limit) for n in (
        'tenant_ref', 'generation_request_ref', 'operation_ref', 'event_ref',
        'provider_id', 'model_id', 'configuration_ref'))
    return RubricAccountingIdentity(*parts, _fingerprint(value.source_fingerprint))


def _provenance(value: object, limit: int) -> RubricProviderProvenance:
    if type(value) is not RubricProviderProvenance:
        raise RubricAccountingDenied('Invalid rubric-provider provenance type.')
    return RubricProviderProvenance(_id(value.provider_id, limit), _id(value.model_id, limit))


class RubricGrantDisposition(Enum):
    ALLOWED = 'ALLOWED'
    DENIED = 'DENIED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class RubricGenerationGrant:
    identity: RubricAccountingIdentity
    disposition: RubricGrantDisposition
    approval_ref: str | None
    policy_id: str | None
    policy_version: str | None


def _grant(value: object, identity: RubricAccountingIdentity, limit: int) -> RubricGenerationGrant:
    if (type(value) is not RubricGenerationGrant
            or type(value.disposition) is not RubricGrantDisposition
            or _identity(value.identity, limit) != identity):
        raise RubricAccountingDenied('Foreign rubric-generation grant.')
    if value.disposition is not RubricGrantDisposition.ALLOWED:
        if (value.approval_ref is not None or value.policy_id is not None
                or value.policy_version is not None):
            raise RubricAccountingDenied('Nonapproved rubric grant carries authority.')
        return RubricGenerationGrant(identity, value.disposition, None, None, None)
    return RubricGenerationGrant(identity, value.disposition,
                                 _id(value.approval_ref, limit),
                                 _id(value.policy_id, limit),
                                 _id(value.policy_version, limit))


@dataclass(frozen=True, slots=True)
class RubricAccountingEvent:
    identity: RubricAccountingIdentity
    approval_ref: str
    policy_id: str
    policy_version: str
    status: str
    physical_request_count: int | None
    sdk_retry_count: int | None
    failure_kind: str | None


@dataclass(frozen=True, slots=True)
class RubricAccountingReceipt:
    event_ref: str
    operation_ref: str
    approval_ref: str
    status: str


class RubricGrantAuthority(Protocol):
    def authorize_generation(self, *, identity: RubricAccountingIdentity) -> RubricGenerationGrant: ...


class RubricAccountingSink(Protocol):
    def record_rubric_generation(self, *, event: RubricAccountingEvent) -> RubricAccountingReceipt: ...


class OneShotRubricGenerationAccountingProvider:
    """One use of original installed generate callback, gated by external grant.

    Drop-in ``RubricGenerationProvider`` for ``generate_rubric_with_provider``;
    the physical vendor effect is never counted by calling Python once.
    """
    __slots__ = ('_installation', '_lock', '_used')

    def __init__(self, *, identity: RubricAccountingIdentity, provider: object,
                 authority: RubricGrantAuthority, sink: RubricAccountingSink,
                 max_identifier_characters: int, max_raw_response_bytes: int) -> None:
        try:
            if (type(max_identifier_characters) is not int
                    or not 0 < max_identifier_characters <= 2**31-1
                    or type(max_raw_response_bytes) is not int
                    or not 0 < max_raw_response_bytes <= 2**63-1):
                raise RubricAccountingDenied('Unadmitted rubric resource limits.')
            original = _identity(identity, max_identifier_characters)
            provenance = _provenance(getattr(provider, 'provenance'), max_identifier_characters)
            if (provenance.provider_id != original.provider_id
                    or provenance.model_id != original.model_id):
                raise RubricAccountingDenied('Rubric provider provenance mismatch.')
            generation = getattr(provider, 'generate')
            authorize = getattr(authority, 'authorize_generation')
            write = getattr(sink, 'record_rubric_generation')
            if not (callable(generation) and callable(authorize) and callable(write)):
                raise RubricAccountingDenied('Missing installed rubric-accounting operation.')
            object.__setattr__(self, '_installation', (original, provider, provenance,
                                generation, authorize, write, max_identifier_characters,
                                max_raw_response_bytes))
            object.__setattr__(self, '_lock', Lock())
            object.__setattr__(self, '_used', False)
        except Exception:
            _public(RubricAccountingDenied('Invalid rubric-accounting installation.'))

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError('Rubric provider installation cannot change.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError('Rubric provider installation cannot be deleted.')
        object.__delattr__(self, name)

    @property
    def provenance(self) -> RubricProviderProvenance:
        _, _, original, *_ = self._installation
        return _provenance(original, self._installation[-2])

    def generate(self, *, source: RubricGenerationInput) -> bytes:
        with self._lock:
            if self._used:
                _public(RubricAccountingDenied('Rubric generation already consumed.'))
            object.__setattr__(self, '_used', True)
        original, provider, expected_provenance, generation, authorize, write, limit, max_bytes = self._installation
        try:
            expected = _identity(original, limit)
            if type(source) is not RubricGenerationInput:
                raise RubricAccountingDenied('Unadmitted rubric-generation source.')
            fingerprint = rubric_provider_request_fingerprint(source)
            if fingerprint != expected.source_fingerprint:
                raise RubricAccountingDenied('Rubric-generation source mismatch.')
        except Exception:
            _public(RubricAccountingDenied('Rubric-generation input rejected.'))
        query = _identity(expected, limit)
        answer = None
        issuance_error: Exception | None = None
        try:
            answer = authorize(identity=query)
        except Exception as exc:
            issuance_error = exc
        try:
            same = (_identity(query, limit) == expected and _identity(original, limit) == expected
                    and rubric_provider_request_fingerprint(source) == fingerprint
                    and _provenance(getattr(provider, 'provenance'), limit) == expected_provenance)
        except Exception:
            same = False
        if not same:
            _public(RubricAccountingDenied('Rubric issuance altered request identity.'))
        if issuance_error is not None:
            if isinstance(issuance_error, RubricAccountingDenied):
                _public(RubricAccountingDenied('Rubric issuance denied.'))
            _public(RubricAccountingIndeterminate('Rubric authority unavailable.'))
        try:
            grant = _grant(answer, expected, limit)
        except Exception:
            _public(RubricAccountingDenied('Invalid rubric-generation authority response.'))
        if grant.disposition is RubricGrantDisposition.DENIED:
            _public(RubricAccountingDenied('Rubric generation definitively denied.'))
        if grant.disposition is not RubricGrantDisposition.ALLOWED:
            _public(RubricAccountingIndeterminate('Rubric-generation authority uncertain.'))
        payload = None
        status = 'RESULT_RETURNED'
        failure = None
        try:
            payload = generation(source=source)
            if type(payload) is not bytes or len(payload) > max_bytes:
                raise RubricAccountingIndeterminate('Unadmitted rubric-generation bytes.')
        except Exception:
            payload = None
            status = 'INDETERMINATE'
            failure = 'PROVIDER_OR_RESPONSE_UNKNOWN'
        try:
            intact = (_identity(original, limit) == expected
                      and rubric_provider_request_fingerprint(source) == fingerprint
                      and _provenance(getattr(provider, 'provenance'), limit) == expected_provenance
                      and _grant(grant, expected, limit) == grant)
        except Exception:
            intact = False
        if not intact:
            payload = None
            status = 'INDETERMINATE'
            failure = 'REQUEST_OR_PROVIDER_INTEGRITY_LOST'
        event = RubricAccountingEvent(_identity(expected, limit), grant.approval_ref,
                 grant.policy_id, grant.policy_version, status, None, None, failure)
        try:
            receipt = write(event=event)
            if (type(event) is not RubricAccountingEvent
                    or type(receipt) is not RubricAccountingReceipt
                    or any(type(getattr(receipt, n)) is not str for n in
                           ('event_ref', 'operation_ref', 'approval_ref', 'status'))
                    or receipt.event_ref != expected.event_ref
                    or receipt.operation_ref != expected.operation_ref
                    or receipt.approval_ref != grant.approval_ref
                    or receipt.status != status
                    or _identity(original, limit) != expected
                    or rubric_provider_request_fingerprint(source) != fingerprint
                    or _provenance(getattr(provider, 'provenance'), limit) != expected_provenance
                    or _grant(grant, expected, limit) != grant
                    or type(event.status) is not str or event.status != status
                    or not (type(event.failure_kind) is str or type(event.failure_kind) is type(None))
                    or event.failure_kind != failure
                    or any(type(getattr(event, n)) is not str for n in
                           ('approval_ref', 'policy_id', 'policy_version'))
                    or event.approval_ref != grant.approval_ref
                    or event.policy_id != grant.policy_id
                    or event.policy_version != grant.policy_version
                    or type(event.physical_request_count) is not type(None)
                    or type(event.sdk_retry_count) is not type(None)
                    or _identity(event.identity, limit) != expected
                    or (event.approval_ref, event.policy_id, event.policy_version)
                       != (grant.approval_ref, grant.policy_id, grant.policy_version)):
                raise RubricAccountingDenied('Invalid rubric-accounting receipt or event.')
        except Exception:
            _public(RubricAccountingIndeterminate('Rubric accounting uncertain; reconcile.'))
        if status != 'RESULT_RETURNED':
            _public(RubricAccountingIndeterminate('Rubric effect uncertain; no retry.'))
        return payload

class RubricRecoveryDisposition(Enum):
    RECORDED = 'RECORDED'
    NOT_FOUND = 'NOT_FOUND'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class RubricAccountingRecoveryFact:
    identity: RubricAccountingIdentity
    disposition: RubricRecoveryDisposition
    recorded_status: str | None
    policy_id: str | None
    policy_version: str | None
    receipt: RubricAccountingReceipt | None


class RubricAccountingRecoveryStore(Protocol):
    def reconcile_rubric_generation(self, *, identity: RubricAccountingIdentity) -> RubricAccountingRecoveryFact: ...


def _recovery(value: object, original: RubricAccountingIdentity,
              limit: int) -> RubricAccountingRecoveryFact:
    if (type(value) is not RubricAccountingRecoveryFact
            or type(value.disposition) is not RubricRecoveryDisposition
            or _identity(value.identity, limit) != original):
        raise RubricAccountingDenied('Invalid rubric accounting recovery.')
    if value.disposition is not RubricRecoveryDisposition.RECORDED:
        if (value.recorded_status is not None or value.policy_id is not None
                or value.policy_version is not None or value.receipt is not None):
            raise RubricAccountingDenied('Nonrecorded rubric recovery claims a result.')
        return RubricAccountingRecoveryFact(original, value.disposition, None, None, None, None)
    if (type(value.recorded_status) is not str
            or value.recorded_status not in ('RESULT_RETURNED', 'INDETERMINATE')
            or type(value.receipt) is not RubricAccountingReceipt):
        raise RubricAccountingDenied('Invalid recorded rubric recovery status.')
    policy_id = _id(value.policy_id, limit)
    policy_version = _id(value.policy_version, limit)
    receipt = value.receipt
    if (any(type(getattr(receipt, n)) is not str for n in
            ('event_ref', 'operation_ref', 'approval_ref', 'status'))
            or _id(receipt.approval_ref, limit) != receipt.approval_ref
            or receipt.event_ref != original.event_ref
            or receipt.operation_ref != original.operation_ref
            or receipt.status != value.recorded_status):
        raise RubricAccountingDenied('Foreign recorded rubric recovery receipt.')
    return RubricAccountingRecoveryFact(original, value.disposition, value.recorded_status,
                                        policy_id, policy_version,
                                        RubricAccountingReceipt(receipt.event_ref, receipt.operation_ref,
                                                                receipt.approval_ref, receipt.status))


class ReadOnlyRubricAccountingRecovery:
    """Stable-generation-request reconciliation; cannot authorize another call."""
    __slots__ = ('_installation', '_lock', '_active')

    def __init__(self, *, identity: RubricAccountingIdentity,
                 store: RubricAccountingRecoveryStore,
                 max_identifier_characters: int) -> None:
        try:
            if (type(max_identifier_characters) is not int
                    or not 0 < max_identifier_characters <= 2**31-1):
                raise RubricAccountingDenied('Invalid recovery limits.')
            original = _identity(identity, max_identifier_characters)
            op = getattr(store, 'reconcile_rubric_generation')
            if not callable(op):
                raise RubricAccountingDenied('Missing recovery operation.')
            object.__setattr__(self, '_installation', (original, op, max_identifier_characters))
            object.__setattr__(self, '_lock', Lock())
            object.__setattr__(self, '_active', False)
        except Exception:
            _public(RubricAccountingDenied('Invalid rubric recovery installation.'))

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError('Rubric recovery installation is fixed.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError('Rubric recovery installation is fixed.')
        object.__delattr__(self, name)

    def reconcile(self) -> RubricAccountingRecoveryFact:
        with self._lock:
            if self._active:
                _public(RubricAccountingDenied('Recursive rubric reconciliation rejected.'))
            object.__setattr__(self, '_active', True)
        try:
            identity, original_op, limit = self._installation
            expected = _identity(identity, limit)
            query = _identity(expected, limit)
            result = None
            error: Exception | None = None
            try:
                result = original_op(identity=query)
            except Exception as exc:
                error = exc
            try:
                intact = (_identity(query, limit) == expected and _identity(identity, limit) == expected)
            except Exception:
                intact = False
            if not intact:
                _public(RubricAccountingDenied('Rubric recovery query integrity lost.'))
            if error is not None:
                if isinstance(error, RubricAccountingDenied):
                    _public(RubricAccountingDenied('Rubric recovery definitively denied.'))
                _public(RubricAccountingIndeterminate('Rubric recovery unavailable.'))
            try:
                return _recovery(result, expected, limit)
            except Exception:
                _public(RubricAccountingDenied('Unadmitted rubric recovery statement.'))
        finally:
            with self._lock:
                object.__setattr__(self, '_active', False)
