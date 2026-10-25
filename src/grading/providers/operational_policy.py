"""reference qualification provider operational policy finite decision/dispatch seam; positive policy issuance is external.

A retry is permitted ONLY after a trusted step reports definitive NO_EFFECT.
Actual transport deadlines, SDK retries, backoff timing and issuer authenticity
require independent adapter conformance; matching dataclasses cannot prove them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.providers.attempt_accounting import (
    ProviderAccountingDenied, ProviderAccountingIndeterminate,
    ProviderAttemptIdentity, ProviderTransportOutcome, ProviderPhysicalObservation, _identity,
    _id, _raise_public,
)
from grading.providers.semantic_replay import direct_text_semantic_request_fingerprint
from grading.semantic_evaluator import DirectTextSemanticRequest


@dataclass(frozen=True, slots=True)
class OperationalPolicy:
    identity: ProviderAttemptIdentity
    policy_id: str
    policy_version: str
    max_dispatches: int
    deadline_milliseconds: int
    backoff_milliseconds: int
    fallback_ref: str | None


def _numeric(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProviderAccountingDenied('Invalid provider operational policy finite operational value.')
    return value


def _policy(value: object, expected: ProviderAttemptIdentity, limit: int,
            max_dispatches: int, max_deadline_ms: int, max_backoff_ms: int) -> OperationalPolicy:
    if type(value) is not OperationalPolicy:
        raise ProviderAccountingDenied('Invalid provider policy admission.')
    if _identity(value.identity,limit) != expected:
        raise ProviderAccountingDenied('Foreign provider policy identity.')
    ident = _id(value.policy_id,limit,'provider policy identifier')
    version = _id(value.policy_version,limit,'provider policy version')
    attempts = _numeric(value.max_dispatches,1,max_dispatches)
    timeout = _numeric(value.deadline_milliseconds,1,max_deadline_ms)
    backoff = _numeric(value.backoff_milliseconds,0,max_backoff_ms)
    # No fallback implementation can be selected until its exact executable
    # binding, authorization and privacy policy have been independently proved.
    if value.fallback_ref is not None:
        raise ProviderAccountingDenied('provider operational policy fallback not admitted by this seam.')
    return OperationalPolicy(expected,ident,version,attempts,timeout,backoff,None)


class StepDisposition(Enum):
    RESPONSE = 'RESPONSE'
    DEFINITIVE_NO_EFFECT = 'DEFINITIVE_NO_EFFECT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class ProviderStepFact:
    disposition: StepDisposition
    outcome: ProviderTransportOutcome | None
    # A transport-issued structural assertion, NOT authenticated proof.
    # Unless the actual final-step observation is qualified as cumulative,
    # numbers from a later step cannot describe the full logical operation.
    telemetry_scope: str = 'UNVERIFIED'


class OperationalPolicyAuthority(Protocol):
    def authorize_execution_policy(self, *, identity: ProviderAttemptIdentity) -> OperationalPolicy: ...


class ConfiguredTransportStep(Protocol):
    def execute_step(self, *, request: DirectTextSemanticRequest,
                     identity: ProviderAttemptIdentity, policy: OperationalPolicy,
                     attempt_index: int, deadline_milliseconds: int) -> ProviderStepFact: ...


class ApprovedBackoffClock(Protocol):
    def wait_before_retry(self, *, identity: ProviderAttemptIdentity,
                          attempt_index: int, milliseconds: int) -> None: ...


class PolicyBoundDirectTransport:
    """Drop-in one-shot transport with internally finite, effect-aware steps.

    A trusted NO_EFFECT outcome alone allows an explicitly authorized next step.
    UNKNOWN/exception stops. No automated fallback and no unapproved defaults.
    """

    __slots__=('_install','_lock','_used')

    def __init__(self, *, identity: ProviderAttemptIdentity,
                 authority: OperationalPolicyAuthority,
                 transport_step: ConfiguredTransportStep,
                 backoff_clock: ApprovedBackoffClock,
                 max_identifier_characters: int,
                 max_dispatches: int,
                 max_deadline_milliseconds: int,
                 max_backoff_milliseconds: int) -> None:
        try:
            limit = _numeric(max_identifier_characters,1,2**31-1)
            original = _identity(identity,limit)
            caps = (_numeric(max_dispatches,1,2**31-1),
                    _numeric(max_deadline_milliseconds,1,2**31-1),
                    _numeric(max_backoff_milliseconds,0,2**31-1))
            ops = (getattr(authority,'authorize_execution_policy'),
                   getattr(transport_step,'execute_step'),
                   getattr(backoff_clock,'wait_before_retry'))
            if not all(callable(op) for op in ops):
                raise ProviderAccountingDenied('Missing provider operational policy installed operation.')
            object.__setattr__(self,'_install',(original,*ops,limit,*caps))
            object.__setattr__(self,'_lock',Lock())
            object.__setattr__(self,'_used',False)
        except Exception:
            _raise_public(ProviderAccountingDenied('Invalid provider policy/transport installation.'))

    def __setattr__(self,name,value):
        if name in ('_install','_lock','_used') and hasattr(self,name):
            raise AttributeError('Installed provider operational policy operation is fixed.')
        object.__setattr__(self,name,value)

    def __delattr__(self,name):
        if name in ('_install','_lock','_used'):
            raise AttributeError('Installed provider operational policy operation cannot be deleted.')
        object.__delattr__(self,name)

    def execute_once(self, *, request: DirectTextSemanticRequest,
                     identity: ProviderAttemptIdentity) -> ProviderTransportOutcome:
        with self._lock:
            if self._used:
                _raise_public(ProviderAccountingDenied('Provider transport opportunity already consumed.'))
            object.__setattr__(self,'_used',True)
        anchor, authorize, step, wait, limit, max_tries, max_deadline, max_backoff = self._install
        try:
            expected = _identity(anchor,limit)
            supplied = _identity(identity,limit)
            if supplied != expected or type(request) is not DirectTextSemanticRequest:
                raise ProviderAccountingDenied('provider operational policy request identity mismatch.')
            fingerprint = direct_text_semantic_request_fingerprint(request)
            if fingerprint != expected.request_fingerprint:
                raise ProviderAccountingDenied('provider operational policy request fingerprint mismatch.')
        except Exception:
            _raise_public(ProviderAccountingDenied('Provider transport request not admitted.'))
        plan = None
        failure: Exception | None = None
        issued_query = _identity(expected,limit)
        try:
            plan = authorize(identity=issued_query)
        except Exception as err:
            failure = err
        try:
            if (_identity(issued_query,limit) != expected or _identity(anchor,limit) != expected
                    or _identity(identity,limit) != expected
                    or direct_text_semantic_request_fingerprint(request) != fingerprint):
                raise ProviderAccountingDenied('provider operational policy issuance changed request identity.')
        except Exception:
            _raise_public(ProviderAccountingDenied('Provider policy issuance integrity lost.'))
        if failure is not None:
            if isinstance(failure, ProviderAccountingDenied):
                _raise_public(ProviderAccountingDenied('Provider policy definitively denied.'))
            _raise_public(ProviderAccountingIndeterminate('Provider policy issuance uncertain.'))
        try:
            approved = _policy(plan,expected,limit,max_tries,max_deadline,max_backoff)
        except Exception:
            _raise_public(ProviderAccountingDenied('Provider operational policy not admitted.'))
        for i in range(1,approved.max_dispatches+1):
            query = _identity(expected,limit)
            request_fingerprint = fingerprint
            result = None
            step_error: Exception | None = None
            step_policy = _policy(approved,expected,limit,max_tries,max_deadline,max_backoff)
            try:
                result = step(request=request,identity=query,policy=step_policy,
                              attempt_index=i,deadline_milliseconds=approved.deadline_milliseconds)
            except Exception as exc:
                step_error = exc
            try:
                intact = (_identity(query,limit)==expected and _identity(anchor,limit)==expected
                          and _identity(identity,limit)==expected
                          and direct_text_semantic_request_fingerprint(request)==request_fingerprint
                          and _policy(approved,expected,limit,max_tries,max_deadline,max_backoff)==approved
                          and _policy(step_policy,expected,limit,max_tries,max_deadline,max_backoff)==approved)
            except Exception:
                intact = False
            if not intact:
                _raise_public(ProviderAccountingDenied('Provider transport request identity changed.'))
            if step_error is not None:
                _raise_public(ProviderAccountingIndeterminate('Provider transport step effect uncertain; no retry.'))
            if (type(result) is not ProviderStepFact or type(result.disposition) is not StepDisposition
                    or type(result.telemetry_scope) is not str
                    or result.telemetry_scope not in ('UNVERIFIED', 'CUMULATIVE_OPERATION')):
                _raise_public(ProviderAccountingIndeterminate('Unadmitted provider transport effect; no retry.'))
            if result.disposition is StepDisposition.RESPONSE:
                if type(result.outcome) is not ProviderTransportOutcome:
                    _raise_public(ProviderAccountingIndeterminate('Unadmitted provider transport response.'))
                if i > 1 and result.telemetry_scope != 'CUMULATIVE_OPERATION':
                    # A step-local telemetry snapshot must NEVER be represented
                    # as cumulative operation usage after an earlier dispatch.
                    # Retain payload but report all physical usage UNKNOWN.
                    return ProviderTransportOutcome(result.outcome.raw_payload,
                        ProviderPhysicalObservation(None,None,None,None,None,None,None,None))
                return result.outcome
            if result.disposition is StepDisposition.UNKNOWN:
                _raise_public(ProviderAccountingIndeterminate('Unknown provider transport physical effect; no retry.'))
            if result.outcome is not None or result.telemetry_scope != 'UNVERIFIED':
                _raise_public(ProviderAccountingIndeterminate('NO_EFFECT with a payload is incoherent.'))
            if i == approved.max_dispatches:
                _raise_public(ProviderAccountingIndeterminate('Approved provider transport attempts exhausted.'))
            wait_query = _identity(expected,limit)
            wait_error: Exception | None = None
            try:
                wait(identity=wait_query,attempt_index=i,
                     milliseconds=approved.backoff_milliseconds)
            except Exception as exc:
                wait_error = exc
            try:
                wait_intact = (_identity(wait_query,limit) == expected
                               and _identity(anchor,limit) == expected
                               and _identity(identity,limit) == expected
                               and direct_text_semantic_request_fingerprint(request) == fingerprint
                               and _policy(approved,expected,limit,max_tries,max_deadline,max_backoff) == approved)
            except Exception:
                wait_intact = False
            if not wait_intact:
                _raise_public(ProviderAccountingDenied('Provider retry backoff identity integrity lost.'))
            if wait_error is not None:
                _raise_public(ProviderAccountingIndeterminate('Provider retry backoff outcome uncertain.'))
        _raise_public(ProviderAccountingIndeterminate('Provider transport execution did not produce a response.'))
