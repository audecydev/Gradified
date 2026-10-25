"""Read-only stable-request reconciliation of offline replay trials.

A missing or recorded historical trial is never a permission to execute again.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.benchmark.offline_trial import (
    OfflineTrialRequest, OfflineTrialClaim, OfflineTrialReceipt,
    OfflineTrialDenied, OfflineTrialIndeterminate, TrialClaimDisposition,
    _public, _request, _claim, _receipt, _digest, _number,
)


class OfflineRecoveryDisposition(Enum):
    RECORDED = 'RECORDED'
    CLAIMED = 'CLAIMED'
    NOT_FOUND = 'NOT_FOUND'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class OfflineTrialRecoveryFact:
    request: OfflineTrialRequest
    disposition: OfflineRecoveryDisposition
    claim: OfflineTrialClaim | None
    recorded_status: str | None
    output_sha256: str | None
    receipt: OfflineTrialReceipt | None


class TrialRecoveryStore(Protocol):
    def reconcile_trial_request(self, *, request: OfflineTrialRequest) -> OfflineTrialRecoveryFact: ...


def _fact(value: object, request: OfflineTrialRequest, limit: int) -> OfflineTrialRecoveryFact:
    if type(value) is not OfflineTrialRecoveryFact:
        raise OfflineTrialDenied('Invalid trial recovery fact.')
    if type(value.disposition) is not OfflineRecoveryDisposition:
        raise OfflineTrialDenied('Invalid trial recovery disposition.')
    if _request(value.request, limit) != request:
        raise OfflineTrialDenied('Foreign trial recovery request.')
    if value.disposition in (OfflineRecoveryDisposition.RECORDED, OfflineRecoveryDisposition.CLAIMED):
        claim = _claim(value.claim,request,limit)
        if claim.disposition is not TrialClaimDisposition.FRESH:
            raise OfflineTrialDenied('Missing original fresh trial identity.')
        if value.disposition is OfflineRecoveryDisposition.CLAIMED:
            if value.recorded_status is not None or value.output_sha256 is not None or value.receipt is not None:
                raise OfflineTrialDenied('Uncommitted claimed trial has forged receipt.')
            return OfflineTrialRecoveryFact(request,value.disposition,claim,None,None,None)
        if type(value.recorded_status) is not str or value.recorded_status not in ('TRIAL_OBSERVED','TRIAL_UNKNOWN'):
            raise OfflineTrialDenied('Invalid recorded trial status.')
        if value.recorded_status == 'TRIAL_OBSERVED':
            digest = _digest(value.output_sha256)
        elif value.output_sha256 is not None:
            raise OfflineTrialDenied('Unknown trial cannot report an output digest.')
        else:
            digest = None
        receipt = _receipt(value.receipt,claim,value.recorded_status,digest,limit)
        return OfflineTrialRecoveryFact(request,value.disposition,claim,
                                        value.recorded_status,digest,receipt)
    if any(x is not None for x in (value.claim,value.recorded_status,value.output_sha256,value.receipt)):
        raise OfflineTrialDenied('Unresolved trial recovery carries forged execution outcome.')
    return OfflineTrialRecoveryFact(request,value.disposition,None,None,None,None)


class ReadOnlyOfflineTrialRecovery:
    """A request-keyed query; never calls a dataset reader or replay executor."""

    __slots__ = ('_install','_lock','_active')

    def __init__(self, *, request: OfflineTrialRequest,
                 store: TrialRecoveryStore, max_identifier_characters: int) -> None:
        try:
            limit = _number(max_identifier_characters)
            installed = _request(request,limit)
            operation = getattr(store,'reconcile_trial_request')
            if not callable(operation):
                raise OfflineTrialDenied('Missing trial recovery operation.')
            object.__setattr__(self,'_install',(installed,operation,limit))
            object.__setattr__(self,'_lock',Lock())
            object.__setattr__(self,'_active',False)
        except Exception:
            _public(OfflineTrialDenied('Invalid trial recovery installation.'))

    def __setattr__(self,name,value):
        if name in ('_install','_lock','_active') and hasattr(self,name):
            raise AttributeError('Trial recovery installation is fixed.')
        object.__setattr__(self,name,value)

    def __delattr__(self,name):
        if name in ('_install','_lock','_active'):
            raise AttributeError('Trial recovery installation cannot be deleted.')
        object.__delattr__(self,name)

    def reconcile(self) -> OfflineTrialRecoveryFact:
        with self._lock:
            if self._active:
                _public(OfflineTrialDenied('Recursive trial recovery is prohibited.'))
            object.__setattr__(self,'_active',True)
        try:
            installed, read, limit = self._install
            original = _request(installed,limit)
            query = _request(original,limit)
            result = None
            failure: Exception | None = None
            try:
                result = read(request=query)
            except Exception as error:
                failure = error
            try:
                intact = (_request(query,limit) == original
                          and _request(installed,limit) == original)
            except Exception:
                intact = False
            if not intact:
                _public(OfflineTrialDenied('Trial recovery query identity changed.'))
            if failure is not None:
                if isinstance(failure,OfflineTrialDenied):
                    _public(OfflineTrialDenied('Trial recovery definitively refused.'))
                _public(OfflineTrialIndeterminate('Trial recovery unavailable.'))
            try:
                return _fact(result,original,limit)
            except Exception:
                _public(OfflineTrialDenied('Invalid trial recovery evidence.'))
        finally:
            with self._lock:
                object.__setattr__(self,'_active',False)
