"""Immutable byte-dispatch seam for an independently qualified DIRECT provider adapter.

Unlike the legacy object transport, the downstream adapter receives no mutable
semantic request. A matching receipt is a LOCAL assertion, not proof of actual
vendor-side bytes, physical attempts, authentication, billing or durability.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import Lock
from typing import Protocol

from grading.providers.attempt_accounting import (
    ProviderAttemptIdentity, ProviderTransportOutcome, ProviderPhysicalObservation,
    ProviderAccountingDenied, ProviderAccountingIndeterminate, _capture_provider_method,
    _identity, _id, _raise_public,
)
from grading.providers.semantic_replay import _direct_text_semantic_request_bytes
from grading.semantic_evaluator import DirectTextSemanticRequest


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalProviderDispatch:
    """Canonical bytes with Gradified logical IDs (not an authentication token)."""
    identity: ProviderAttemptIdentity
    dispatch_ref: str
    request_bytes: bytes
    request_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalProviderReply:
    """Adapter's asserted correlation, NOT a verified physical transmission."""
    dispatch_ref: str
    operation_ref: str
    event_ref: str
    logical_evaluation_ref: str
    attempt_id: str
    request_ref: str
    request_sha256: str
    provider_id: str
    model_id: str
    configuration_ref: str
    raw_payload: bytes


class ProviderCanonicalByteSender(Protocol):
    def deliver(self, *, dispatch: CanonicalProviderDispatch) -> CanonicalProviderReply: ...


_UNKNOWN = ProviderPhysicalObservation(None, None, None, None, None, None, None, None)


class CanonicalDirectTextTransport:
    """One-use adapter bridge installed under OneShotDirectTextAccountingProvider.

    All unknown physical telemetry stays unknown. Only a qualified byte sender
    and real persisted original records can prove effect/billing conformance.
    """
    __slots__ = ('_installed', '_lock', '_used')

    def __init__(self, *, identity: ProviderAttemptIdentity, dispatch_ref: str,
                 sender: ProviderCanonicalByteSender, max_identifier_characters: int,
                 max_request_bytes: int, max_response_bytes: int) -> None:
        try:
            if (type(max_identifier_characters) is not int
                    or not 0 < max_identifier_characters <= 4096
                    or type(max_request_bytes) is not int or not 0 < max_request_bytes <= 50_000_000
                    or type(max_response_bytes) is not int or not 0 < max_response_bytes <= 50_000_000):
                raise ValueError('Invalid finite byte limits.')
            expected = _identity(identity, max_identifier_characters)
            ref = _id(dispatch_ref, max_identifier_characters, 'dispatch ref')
            deliver = _capture_provider_method(sender, 'deliver', ('dispatch',))
            object.__setattr__(self, '_installed', (expected, ref, deliver,
                                                    max_identifier_characters,
                                                    max_request_bytes, max_response_bytes))
            object.__setattr__(self, '_lock', Lock())
            object.__setattr__(self, '_used', False)
        except Exception:
            _raise_public(ProviderAccountingDenied('Invalid canonical transport installation.'))

    def __setattr__(self, name, value):
        raise AttributeError('Installed canonical transport cannot be replaced.')

    def __delattr__(self, name):
        raise AttributeError('Installed canonical transport cannot be deleted.')

    def execute_once(self, *, request: DirectTextSemanticRequest,
                     identity: ProviderAttemptIdentity) -> ProviderTransportOutcome:
        with self._lock:
            if self._used:
                _raise_public(ProviderAccountingDenied('Canonical dispatch already consumed.'))
            object.__setattr__(self, '_used', True)
        expected, ref, deliver, limit, max_request, max_response = self._installed
        try:
            if _identity(identity, limit) != expected:
                raise ValueError('Wrong identity.')
            encoded = _direct_text_semantic_request_bytes(request)
            if len(encoded) > max_request:
                raise ValueError('Request too large.')
            digest = hashlib.sha256(encoded).hexdigest()
            if digest != expected.request_fingerprint:
                raise ValueError('Wrong canonical request.')
            # No mutable DirectTextSemanticRequest crosses the effect boundary.
            dispatch = CanonicalProviderDispatch(_identity(expected, limit), ref, encoded, digest)
            # A sender may rebind public module names while this callback runs.
            # Retain concrete built-in result types and an owner-created UNKNOWN
            # observation before yielding execution to the sender.
            unknown_observation = ProviderPhysicalObservation(
                None, None, None, None, None, None, None, None)
            outcome_type = ProviderTransportOutcome
        except Exception:
            _raise_public(ProviderAccountingDenied('Canonical provider request not admitted.'))
        try:
            reply = deliver(dispatch=dispatch)
        except Exception:
            _raise_public(ProviderAccountingIndeterminate('Canonical provider effect unknown.'))
        try:
            # This detects persistent substitution, not a malicious adapter
            # which transmits different bytes then restores local values.
            if (type(dispatch) is not CanonicalProviderDispatch
                    or _identity(dispatch.identity, limit) != expected
                    or type(dispatch.dispatch_ref) is not str or dispatch.dispatch_ref != ref
                    or type(dispatch.request_bytes) is not bytes or dispatch.request_bytes != encoded
                    or type(dispatch.request_sha256) is not str or dispatch.request_sha256 != digest
                    or type(reply) is not CanonicalProviderReply
                    or type(reply.dispatch_ref) is not str or reply.dispatch_ref != ref
                    or type(reply.operation_ref) is not str or reply.operation_ref != expected.operation_ref
                    or type(reply.event_ref) is not str or reply.event_ref != expected.event_ref
                    or type(reply.logical_evaluation_ref) is not str
                    or reply.logical_evaluation_ref != expected.logical_evaluation_ref
                    or type(reply.attempt_id) is not str or reply.attempt_id != expected.attempt_id
                    or type(reply.request_ref) is not str or reply.request_ref != expected.request_ref
                    or type(reply.request_sha256) is not str or reply.request_sha256 != digest
                    or type(reply.provider_id) is not str or reply.provider_id != expected.provider_id
                    or type(reply.model_id) is not str or reply.model_id != expected.model_id
                    or type(reply.configuration_ref) is not str
                    or reply.configuration_ref != expected.configuration_ref
                    or type(reply.raw_payload) is not bytes or len(reply.raw_payload) > max_response):
                raise ValueError('Unqualified correlated reply.')
            # These concrete types/values were captured before sender contact;
            # global constructor substitution cannot mint physical telemetry.
            return outcome_type(reply.raw_payload, unknown_observation)
        except Exception:
            _raise_public(ProviderAccountingIndeterminate('Canonical provider reply not admitted.'))
