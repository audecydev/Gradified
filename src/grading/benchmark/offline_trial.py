"""Bounded offline replay of a qualified benchmark, without grade or publication authority.

Issuer/reader/executor/writer implementations and their grants are external
trusted ports. A Python grant-shaped record is never proof of institutional
permission, durable freshness, or actual physical provider call accounting.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from threading import Lock
from typing import Protocol


class OfflineTrialDenied(ValueError):
    """Definitive local contract denial; no result admitted."""


class OfflineTrialIndeterminate(RuntimeError):
    """A trusted external effect may have occurred; read-only recovery required."""


def _public(error: Exception) -> None:
    try:
        raise error
    finally:
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True


def _identifier(value: object, limit: int) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > limit:
        raise OfflineTrialDenied('Malformed trial identifier.')
    return value


def _digest(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise OfflineTrialDenied('Malformed trial digest.')
    return value


def _number(value: object, *, allow_zero: bool = False) -> int:
    # Engineering representability cap; NOT a policy default or billing allowance.
    if type(value) is not int or value < (0 if allow_zero else 1) or value.bit_length() > 63:
        raise OfflineTrialDenied('Malformed trial resource bound.')
    return value


@dataclass(frozen=True, slots=True)
class OfflineResourceLimits:
    max_dataset_bytes: int
    max_output_bytes: int
    max_trial_invocations: int
    max_parallel_invocations: int
    max_external_provider_requests: int


def _limits(value: object) -> OfflineResourceLimits:
    if type(value) is not OfflineResourceLimits:
        raise OfflineTrialDenied('Unadmitted benchmark limits.')
    dataset = _number(value.max_dataset_bytes)
    output = _number(value.max_output_bytes)
    invocations = _number(value.max_trial_invocations)
    parallel = _number(value.max_parallel_invocations)
    external = _number(value.max_external_provider_requests, allow_zero=True)
    # This engine mechanism implements exactly one replay invocation and NO live
    # provider requests. Larger grants do not become implemented capabilities.
    if invocations != 1 or parallel != 1 or external != 0:
        raise OfflineTrialDenied('Unsupported offline replay resource profile.')
    return OfflineResourceLimits(dataset, output, invocations, parallel, external)


@dataclass(frozen=True, slots=True)
class OfflineTrialRequest:
    tenant_ref: str
    run_ref: str
    trial_request_ref: str
    case_ref: str
    dataset_ref: str
    dataset_revision: str
    dataset_sha256: str
    read_scope_ref: str
    evaluator_ref: str
    configuration_ref: str
    execution_mode: str
    limits: OfflineResourceLimits


def _request(value: object, limit: int) -> OfflineTrialRequest:
    if type(value) is not OfflineTrialRequest:
        raise OfflineTrialDenied('Invalid trial request type.')
    strings = tuple(_identifier(getattr(value, name), limit) for name in (
        'tenant_ref','run_ref','trial_request_ref','case_ref','dataset_ref',
        'dataset_revision','read_scope_ref','evaluator_ref','configuration_ref'))
    digest = _digest(value.dataset_sha256)
    if type(value.execution_mode) is not str or value.execution_mode != 'OFFLINE_REPLAY':
        raise OfflineTrialDenied('Live or unsupported benchmark execution not admitted.')
    return OfflineTrialRequest(*strings[:6], digest, *strings[6:], 'OFFLINE_REPLAY', _limits(value.limits))


class TrialClaimDisposition(Enum):
    FRESH = 'FRESH'
    REPLAY = 'REPLAY'
    CONFLICT = 'CONFLICT'
    REVOKED = 'REVOKED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class OfflineTrialClaim:
    request: OfflineTrialRequest
    disposition: TrialClaimDisposition
    trial_ref: str | None
    event_ref: str | None
    read_grant_ref: str | None
    policy_id: str | None
    policy_version: str | None


def _claim(value: object, original: OfflineTrialRequest, limit: int) -> OfflineTrialClaim:
    if type(value) is not OfflineTrialClaim or type(value.disposition) is not TrialClaimDisposition:
        raise OfflineTrialDenied('Invalid trial authorization response.')
    if _request(value.request, limit) != original:
        raise OfflineTrialDenied('Foreign trial authorization scope.')
    attrs = tuple(getattr(value, name) for name in ('trial_ref','event_ref','read_grant_ref','policy_id','policy_version'))
    if value.disposition is TrialClaimDisposition.FRESH:
        values = tuple(_identifier(v, limit) for v in attrs)
        return OfflineTrialClaim(original, value.disposition, *values)
    # Non-FRESH states may refer to an existing durable trial, but must not be
    # promoted into a usable fresh permission or disclose fabricated identities.
    if any(v is not None for v in attrs):
        raise OfflineTrialDenied('Nonfresh trial response includes executable grant.')
    return OfflineTrialClaim(original, value.disposition, None, None, None, None, None)


@dataclass(frozen=True, slots=True)
class OfflineTrialOutput:
    raw_output: bytes


@dataclass(frozen=True, slots=True)
class OfflineTrialEvent:
    request: OfflineTrialRequest
    trial_ref: str
    event_ref: str
    policy_id: str
    policy_version: str
    status: str
    output_sha256: str | None


def _event(value: object, original: OfflineTrialRequest, claim: OfflineTrialClaim,
           status: str, digest: str | None, limit: int) -> OfflineTrialEvent:
    if type(value) is not OfflineTrialEvent or _request(value.request, limit) != original:
        raise OfflineTrialDenied('Invalid trial history event.')
    strings = tuple(_identifier(getattr(value, name), limit) for name in (
        'trial_ref','event_ref','policy_id','policy_version'))
    if (strings != (claim.trial_ref, claim.event_ref, claim.policy_id, claim.policy_version)
            or type(value.status) is not str or value.status != status
            or (value.output_sha256 is not None and _digest(value.output_sha256) != value.output_sha256)
            or value.output_sha256 != digest):
        raise OfflineTrialDenied('Trial history event identity drift.')
    return OfflineTrialEvent(original,*strings,status,digest)


@dataclass(frozen=True, slots=True)
class OfflineTrialReceipt:
    event_ref: str
    trial_ref: str
    status: str
    output_sha256: str | None


def _receipt(value: object, claim: OfflineTrialClaim, status: str,
             digest: str | None, limit: int) -> OfflineTrialReceipt:
    if type(value) is not OfflineTrialReceipt:
        raise OfflineTrialDenied('Invalid trial audit acknowledgment.')
    parts = (_identifier(value.event_ref, limit), _identifier(value.trial_ref, limit))
    if (parts != (claim.event_ref, claim.trial_ref)
            or type(value.status) is not str or value.status != status
            or (value.output_sha256 is not None and _digest(value.output_sha256) != value.output_sha256)
            or value.output_sha256 != digest):
        raise OfflineTrialDenied('Foreign trial audit acknowledgment.')
    return OfflineTrialReceipt(*parts,status,digest)


@dataclass(frozen=True, slots=True)
class OfflineTrialEvidence:
    """A digest-only non-grade replay observation, never a grading result."""
    request: OfflineTrialRequest
    trial_ref: str
    event_ref: str
    policy_id: str
    policy_version: str
    output_sha256: str
    output_size_bytes: int
    evidence_type: str = 'NON_AUTHORITATIVE_OFFLINE_REPLAY'


class OfflineTrialClaimStore(Protocol):
    def authorize_and_claim(self, *, request: OfflineTrialRequest) -> OfflineTrialClaim: ...


class ProtectedOfflineDatasetReader(Protocol):
    def read_dataset(self, *, request: OfflineTrialRequest, claim: OfflineTrialClaim,
                     max_bytes: int) -> bytes: ...


class OfflineReplayExecutor(Protocol):
    def execute_replay(self, *, request: OfflineTrialRequest, claim: OfflineTrialClaim,
                       dataset_bytes: bytes, max_output_bytes: int) -> OfflineTrialOutput: ...


class OfflineTrialHistory(Protocol):
    def record_trial(self, *, event: OfflineTrialEvent) -> OfflineTrialReceipt: ...


class ClaimedOfflineReplayTrial:
    """Single run; backend FRESH grant before dataset access or replay effects."""

    __slots__ = ('_install','_lock','_used')

    def __init__(self, *, request: OfflineTrialRequest,
                 claims: OfflineTrialClaimStore,
                 reader: ProtectedOfflineDatasetReader,
                 executor: OfflineReplayExecutor,
                 history: OfflineTrialHistory,
                 max_identifier_characters: int) -> None:
        try:
            limit = _number(max_identifier_characters)
            admitted = _request(request, limit)
            operations = tuple(getattr(owner, name) for owner,name in (
                (claims,'authorize_and_claim'),(reader,'read_dataset'),
                (executor,'execute_replay'),(history,'record_trial')))
            if not all(callable(operation) for operation in operations):
                raise OfflineTrialDenied('Incomplete trial port installation.')
            object.__setattr__(self,'_install',(admitted,*operations,limit))
            object.__setattr__(self,'_lock',Lock())
            object.__setattr__(self,'_used',False)
        except Exception:
            _public(OfflineTrialDenied('Invalid offline trial installation.'))

    def __setattr__(self,name,value):
        if name in ('_install','_lock','_used') and hasattr(self,name):
            raise AttributeError('Installed offline trial configuration cannot change.')
        object.__setattr__(self,name,value)

    def __delattr__(self,name):
        if name in ('_install','_lock','_used'):
            raise AttributeError('Installed offline trial configuration cannot be deleted.')
        object.__delattr__(self,name)

    def run(self) -> OfflineTrialEvidence:
        with self._lock:
            if self._used:
                _public(OfflineTrialDenied('Offline trial already consumed.'))
            object.__setattr__(self,'_used',True)
        installed, authorize, read, replay, write, limit = self._install
        original = _request(installed,limit)  # private detached operation anchor
        # No hidden second issuance or implicit retry on a claim timeout.
        # A local failure *before* calling the issuer is a definitive denial.
        # After issuer contact, neither its exception class nor an invalid reply
        # proves that an external FRESH reservation did not commit.
        claim_query = _request(original,limit)
        callback_result = None
        callback_error: Exception | None = None
        try:
            callback_result = authorize(request=claim_query)
        except Exception as exc:
            callback_error = exc
        try:
            if (_request(installed,limit) != original
                    or _request(claim_query,limit) != original):
                raise OfflineTrialDenied('Trial request was altered during claim.')
        except Exception:
            _public(OfflineTrialIndeterminate('Trial request integrity lost after claim contact; reconcile only.'))
        if callback_error is not None:
            _public(OfflineTrialIndeterminate('Trial claim outcome uncertain; reconcile only.'))
        try:
            claim = _claim(callback_result,original,limit)
        except Exception:
            _public(OfflineTrialIndeterminate('Unadmitted trial-claim response; reconcile only.'))
        if claim.disposition is not TrialClaimDisposition.FRESH:
            if claim.disposition is TrialClaimDisposition.UNKNOWN:
                _public(OfflineTrialIndeterminate('Trial freshness uncertain; reconcile only.'))
            _public(OfflineTrialDenied('Trial was not freshly authorized.'))
        original_claim = _claim(claim,original,limit)
        # The read port must independently enforce the authentic grant/revocation
        # and the passed preallocation limit before protected I/O.
        status = 'TRIAL_OBSERVED'
        digest: str | None = None
        result_size = 0
        try:
            read_request = _request(original,limit)
            read_claim = _claim(original_claim,original,limit)
            data = read(request=read_request,claim=read_claim,max_bytes=original.limits.max_dataset_bytes)
            if type(data) is not bytes or len(data) > original.limits.max_dataset_bytes:
                raise OfflineTrialDenied('Invalid bounded dataset read.')
            if sha256(data).hexdigest() != original.dataset_sha256:
                raise OfflineTrialDenied('Dataset digest mismatch.')
            if (_request(installed,limit) != original
                    or _request(read_request,limit) != original
                    or _claim(read_claim,original,limit) != original_claim):
                raise OfflineTrialDenied('Trial request changed during protected read.')
            replay_request = _request(original,limit)
            replay_claim = _claim(original_claim,original,limit)
            output = replay(request=replay_request,claim=replay_claim,dataset_bytes=data,
                            max_output_bytes=original.limits.max_output_bytes)
            if type(output) is not OfflineTrialOutput or type(output.raw_output) is not bytes:
                raise OfflineTrialDenied('Unadmitted replay output.')
            if (_request(replay_request,limit) != original
                    or _claim(replay_claim,original,limit) != original_claim):
                raise OfflineTrialDenied('Trial identity drift during replay.')
            if not output.raw_output:
                raise OfflineTrialDenied('Empty replay cannot be reported as evidence.')
            if len(output.raw_output) > original.limits.max_output_bytes:
                raise OfflineTrialDenied('Replay output too large.')
            digest = sha256(output.raw_output).hexdigest()
            result_size = len(output.raw_output)
        except Exception:
            status = 'TRIAL_UNKNOWN'
            digest = None
        # Any callback may have partially acted; no result will be returned on
        # an uncertain execution or unacknowledged event.
        try:
            if (_request(installed,limit) != original
                    or _request(original,limit) != original_claim.request
                    or _claim(claim,original,limit) != original_claim):
                status = 'TRIAL_UNKNOWN'
                digest = None
        except Exception:
            status = 'TRIAL_UNKNOWN'
            digest = None
        recorded = OfflineTrialEvent(_request(original,limit),original_claim.trial_ref,original_claim.event_ref,
                                     original_claim.policy_id,original_claim.policy_version,status,digest)
        event = OfflineTrialEvent(_request(original,limit),original_claim.trial_ref,original_claim.event_ref,
                                  original_claim.policy_id,original_claim.policy_version,status,digest)
        try:
            receipt = write(event=event)
            _event(event,original,original_claim,status,digest,limit)
            _receipt(receipt,original_claim,status,digest,limit)
            if (_request(installed,limit) != original
                    or _request(original,limit) != original_claim.request
                    or _claim(claim,original,limit) != original_claim):
                raise OfflineTrialDenied('Trial identity corrupted after audit write.')
        except Exception:
            _public(OfflineTrialIndeterminate('Trial audit write uncertain; reconcile only.'))
        if status != 'TRIAL_OBSERVED':
            _public(OfflineTrialIndeterminate('Trial read or replay uncertain; reconcile only.'))
        return OfflineTrialEvidence(recorded.request,recorded.trial_ref,recorded.event_ref,
                                    recorded.policy_id,recorded.policy_version,digest,result_size)
