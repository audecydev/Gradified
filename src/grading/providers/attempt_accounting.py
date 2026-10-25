"""P-D1: one-shot DIRECT provider operation and honest observational accounting.

This module validates locally owned ordering. It does not authenticate an physical attempt claim
attempt, bound a vendor transport stream, or verify durable audit persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from grading.providers.semantic_replay import direct_text_semantic_request_fingerprint
from grading.semantic_evaluator import DirectTextSemanticRequest


def _capture_provider_method(owner: object, name: str, keywords: tuple[str, ...]):
    """Bind the exact installed method without executing foreign descriptors.

    Provider transport and accounting are effectful. A callable attribute alone
    does not establish that the operation later executed is the admitted one.
    """
    import inspect
    from types import FunctionType
    try:
        declared = inspect.getattr_static(type(owner), name)
        on_instance = inspect.getattr_static(owner, name)
        if (type(declared) is not FunctionType or on_instance is not declared
                or '__signature__' in declared.__dict__
                or '__wrapped__' in declared.__dict__):
            raise ValueError('Non-plain installed operation.')
        parameters = tuple(inspect.signature(declared, follow_wrapped=False).parameters.values())
        if (len(parameters) != len(keywords) + 1
                or parameters[0].kind not in (
                    inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                or tuple(p.name for p in parameters[1:]) != keywords
                or any(p.kind is not inspect.Parameter.KEYWORD_ONLY
                       or p.default is not inspect.Parameter.empty for p in parameters[1:])):
            raise ValueError('Installed method signature mismatches execution.')
        return declared.__get__(owner, type(owner))
    except Exception:
        raise ValueError('Installed provider operation is not qualified.') from None


class ProviderAccountingDenied(ValueError):
    """Invalid request, observation, or identity: no grading response admitted."""


class ProviderAccountingIndeterminate(RuntimeError):
    """A provider or accounting effect may have occurred; do not retry blindly."""


def _raise_public(error: Exception) -> None:
    try:
        raise error
    finally:
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True


def _id(value: object, limit: int, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > limit:
        raise ProviderAccountingDenied(f"Invalid {name}.")
    return value


def _nonnegative(value: object, name: str) -> int | None:
    # Exact nonnegative signed-64-bit storage representation. This is NOT an
    # institutional request/billing quota; positive telemetry still requires
    # external source conformance.
    if value is not None and (type(value) is not int or value < 0 or value.bit_length() > 63):
        raise ProviderAccountingDenied(f"Invalid {name}.")
    return value


@dataclass(frozen=True, slots=True)
class ProviderAttemptIdentity:
    """Caller/issuer-supplied correlation, not authentication or permission."""
    operation_ref: str
    event_ref: str
    logical_evaluation_ref: str
    attempt_id: str
    request_ref: str
    provider_id: str
    model_id: str
    configuration_ref: str
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProviderPhysicalObservation:
    """Unknown is None, never numerical zero. Values need real-adapter proof."""
    physical_request_count: int | None
    sdk_retry_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    elapsed_milliseconds: int | None
    billable_minor_units: int | None
    billing_currency: str | None
    telemetry_source_ref: str | None


@dataclass(frozen=True, slots=True)
class ProviderTransportOutcome:
    raw_payload: bytes
    observation: ProviderPhysicalObservation


@dataclass(frozen=True, slots=True)
class ProviderAccountingEvent:
    identity: ProviderAttemptIdentity
    status: str  # RESULT_RETURNED or INDETERMINATE
    observation: ProviderPhysicalObservation | None
    failure_kind: str | None  # opaque public category, not backend details


@dataclass(frozen=True, slots=True)
class ProviderAccountingReceipt:
    event_ref: str
    operation_ref: str
    status: str


class ProviderOneShotTransport(Protocol):
    def execute_once(self, *, request: DirectTextSemanticRequest,
                     identity: ProviderAttemptIdentity) -> ProviderTransportOutcome: ...


class ProviderAccountingSink(Protocol):
    def record_outcome(self, *, event: ProviderAccountingEvent) -> ProviderAccountingReceipt: ...


def _identity(identity: object, limit: int) -> ProviderAttemptIdentity:
    if type(identity) is not ProviderAttemptIdentity:
        raise ProviderAccountingDenied("Invalid provider attempt identity type.")
    values = tuple(_id(getattr(identity, key), limit, key) for key in (
        "operation_ref", "event_ref", "logical_evaluation_ref", "attempt_id",
        "request_ref", "provider_id", "model_id", "configuration_ref",
    ))
    digest = identity.request_fingerprint
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ProviderAccountingDenied("Invalid request fingerprint.")
    return ProviderAttemptIdentity(*values, digest)


def _observation(observation: object, limit: int) -> ProviderPhysicalObservation:
    if type(observation) is not ProviderPhysicalObservation:
        raise ProviderAccountingDenied("Invalid provider observation type.")
    values = tuple(_nonnegative(getattr(observation, key), key) for key in (
        "physical_request_count", "sdk_retry_count", "input_tokens", "output_tokens",
        "elapsed_milliseconds", "billable_minor_units",
    ))
    currency = observation.billing_currency
    source = observation.telemetry_source_ref
    if (currency is None) != (values[5] is None):
        raise ProviderAccountingDenied("Billing amount requires currency and vice versa.")
    if currency is not None:
        _id(currency, limit, "billing currency")
    if source is not None:
        _id(source, limit, "telemetry source")
    if any(x is not None for x in values) and source is None:
        raise ProviderAccountingDenied("Numerical telemetry without provenance must be unknown.")
    if values[0] is not None and values[1] is not None and values[1] > values[0]:
        raise ProviderAccountingDenied("SDK retry count cannot exceed physical requests.")
    return ProviderPhysicalObservation(*values, currency, source)


class OneShotDirectTextAccountingProvider:
    """Drop-in DIRECT provider: one dispatch, acknowledged accounting, raw bytes.

    This instance is single-use, even if the call fails. The provider transport
    and event writer must be separately approved/qualified by the integrator.
    """

    __slots__ = ("_config", "_busy", "_lock")

    def __init__(self, *, identity: ProviderAttemptIdentity,
                 transport: ProviderOneShotTransport, sink: ProviderAccountingSink,
                 max_identifier_characters: int, max_raw_response_bytes: int) -> None:
        try:
            if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
                raise ProviderAccountingDenied("Invalid identifier bound.")
            if type(max_raw_response_bytes) is not int or max_raw_response_bytes <= 0:
                raise ProviderAccountingDenied("Invalid response bound.")
            admitted = _identity(identity, max_identifier_characters)
            transport_call = _capture_provider_method(transport, "execute_once", ("request", "identity"))
            sink_call = _capture_provider_method(sink, "record_outcome", ("event",))
            object.__setattr__(self, "_config", (admitted, transport_call, sink_call,
                                                    max_identifier_characters, max_raw_response_bytes))
            object.__setattr__(self, "_busy", True)
            object.__setattr__(self, "_lock", Lock())
        except Exception:
            _raise_public(ProviderAccountingDenied("Invalid provider-accounting installation."))

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("_config", "_busy", "_lock") and hasattr(self, name):
            raise AttributeError("Installed provider configuration cannot change.")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in ("_config", "_busy", "_lock"):
            raise AttributeError("Installed provider configuration cannot be deleted.")
        object.__delattr__(self, name)

    def evaluate(self, *, request: DirectTextSemanticRequest) -> bytes:
        with self._lock:
            if self._busy is False:
                _raise_public(ProviderAccountingDenied("Provider operation already consumed."))
            # Consume the right to invoke BEFORE callback contact. Nothing retries here.
            object.__setattr__(self, "_busy", False)
        identity, dispatch, write, limit, max_response = self._config
        original_identity = _identity(identity, limit)
        if type(request) is not DirectTextSemanticRequest:
            _raise_public(ProviderAccountingDenied("Invalid provider request type."))
        try:
            original_fingerprint = direct_text_semantic_request_fingerprint(request)
        except Exception:
            _raise_public(ProviderAccountingDenied("Invalid provider request."))
        if original_fingerprint != identity.request_fingerprint:
            _raise_public(ProviderAccountingDenied("Provider request does not match attempt."))
        status = "RESULT_RETURNED"
        failure_kind = None
        observation = None
        payload = None
        try:
            outcome = dispatch(request=request, identity=identity)
            if type(outcome) is not ProviderTransportOutcome:
                raise ProviderAccountingDenied("Invalid transport response type.")
            if type(outcome.raw_payload) is not bytes or len(outcome.raw_payload) > max_response:
                raise ProviderAccountingDenied("Invalid or oversized provider response.")
            observation = _observation(outcome.observation, limit)
            payload = outcome.raw_payload
        except Exception:
            status = "INDETERMINATE"
            failure_kind = "TRANSPORT_OR_RESPONSE_NOT_ADMITTED"
        try:
            if (direct_text_semantic_request_fingerprint(request) != original_fingerprint
                    or _identity(identity, limit) != original_identity):
                status = "INDETERMINATE"
                failure_kind = "REQUEST_INTEGRITY_LOST"
        except Exception:
            status = "INDETERMINATE"
            failure_kind = "REQUEST_INTEGRITY_LOST"
        if status != "RESULT_RETURNED":
            observation = None
            payload = None
        expected_event = ProviderAccountingEvent(_identity(original_identity, limit), status,
                                                 _observation(observation, limit) if observation is not None else None,
                                                 failure_kind)
        event = ProviderAccountingEvent(_identity(original_identity, limit), status,
                                        _observation(observation, limit) if observation is not None else None,
                                        failure_kind)
        try:
            receipt = write(event=event)
            if (type(event) is not ProviderAccountingEvent
                    or type(receipt) is not ProviderAccountingReceipt
                    # Callback-owned receipt fields cannot supply their own equality.
                    or type(receipt.event_ref) is not str
                    or type(receipt.operation_ref) is not str
                    or type(receipt.status) is not str
                    # The sink can mutate a frozen dataclass via object.__setattr__.
                    # Validate its primitive shape before any equality comparison.
                    or type(event.status) is not str
                    or not (type(event.failure_kind) is str or type(event.failure_kind) is type(None))
                    or receipt.event_ref != original_identity.event_ref
                    or receipt.operation_ref != original_identity.operation_ref
                    or receipt.status != status
                    or _identity(identity, limit) != original_identity
                    or direct_text_semantic_request_fingerprint(request) != original_fingerprint
                    or _identity(event.identity, limit) != original_identity
                    or event.status != expected_event.status
                    or event.failure_kind != expected_event.failure_kind
                    or (event.observation is None) != (expected_event.observation is None)
                    or (event.observation is not None
                        and _observation(event.observation, limit) != expected_event.observation)):
                raise ProviderAccountingDenied("Invalid accounting acknowledgment.")
        except Exception:
            _raise_public(ProviderAccountingIndeterminate(
                "Provider effect/accounting acknowledgment uncertain; reconciliation required."
            ))
        if status != "RESULT_RETURNED":
            _raise_public(ProviderAccountingIndeterminate(
                "Provider effect uncertain or response invalid; no automatic retry."
            ))
        return payload
