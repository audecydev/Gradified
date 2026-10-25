from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from grading.providers.semantic_replay import direct_text_semantic_request_fingerprint
from grading.providers.attempt_accounting import (
    OneShotDirectTextAccountingProvider, ProviderAccountingDenied,
    ProviderAccountingIndeterminate, ProviderAttemptIdentity,
    ProviderPhysicalObservation, ProviderTransportOutcome,
    ProviderAccountingReceipt,
)
from grading.semantic_evaluator import DirectTextSemanticRequest


def request() -> DirectTextSemanticRequest:
    return DirectTextSemanticRequest('Q1', 'A question', 'Authorized model answer', (), ())


def identity(value=None) -> ProviderAttemptIdentity:
    return ProviderAttemptIdentity('operation-1', 'event-1', 'evaluation-1', 'attempt-1',
                                   'f25-request-1', 'provider-A', 'model-A', 'config-A',
                                   direct_text_semantic_request_fingerprint(value or request()))


UNKNOWN = ProviderPhysicalObservation(None, None, None, None, None, None, None, None)


class Transport:
    def __init__(self, *, outcome=None, error=None):
        self.outcome = outcome if outcome is not None else ProviderTransportOutcome(b'{"x":1}', UNKNOWN)
        self.error = error
        self.calls = []

    def execute_once(self, *, request, identity):
        self.calls.append((request, identity))
        if self.error is not None:
            raise self.error
        return self.outcome


class Sink:
    def __init__(self, *, error=None, wrong=False):
        self.error = error
        self.wrong = wrong
        self.events = []

    def record_outcome(self, *, event):
        self.events.append(event)
        if self.error is not None:
            raise self.error
        return ProviderAccountingReceipt(event.identity.event_ref,
                                         'another-operation' if self.wrong else event.identity.operation_ref,
                                         event.status)


def wrapper(transport=None, sink=None, *, context=None):
    transport = transport or Transport()
    sink = sink or Sink()
    return (OneShotDirectTextAccountingProvider(identity=context or identity(), transport=transport,
                                                 sink=sink, max_identifier_characters=100,
                                                 max_raw_response_bytes=4096), transport, sink)


def test_positive_single_use_reports_unknown_physical_cost_not_zero():
    provider, transport, sink = wrapper()
    assert provider.evaluate(request=request()) == b'{"x":1}'
    assert len(transport.calls) == 1
    event = sink.events[0]
    assert event.status == 'RESULT_RETURNED'
    assert event.observation.physical_request_count is None
    assert event.observation.sdk_retry_count is None
    assert event.observation.billable_minor_units is None
    with pytest.raises(ProviderAccountingDenied):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1


def test_foreign_request_rejected_before_transport_and_sink():
    provider, transport, sink = wrapper()
    with pytest.raises(ProviderAccountingDenied):
        provider.evaluate(request=replace(request(), question_id='foreign-Q2'))
    assert transport.calls == [] and sink.events == []


def test_transport_timeout_is_indeterminate_accounted_once_and_not_retried():
    provider, transport, sink = wrapper(Transport(error=TimeoutError('private network address')))
    with pytest.raises(ProviderAccountingIndeterminate) as info:
        provider.evaluate(request=request())
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert len(transport.calls) == 1 and len(sink.events) == 1
    assert sink.events[0].status == 'INDETERMINATE'
    assert sink.events[0].observation is None
    with pytest.raises(ProviderAccountingDenied):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1


def test_response_already_returned_but_accounting_fails_is_indeterminate():
    provider, transport, sink = wrapper(sink=Sink(error=RuntimeError('private store name')))
    with pytest.raises(ProviderAccountingIndeterminate) as info:
        provider.evaluate(request=request())
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert len(transport.calls) == 1 and len(sink.events) == 1


def test_foreign_ack_cannot_admit_provider_payload():
    provider, transport, sink = wrapper(sink=Sink(wrong=True))
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1


def test_oversized_response_causes_uncertain_failure_not_success():
    provider, transport, sink = wrapper(Transport(outcome=ProviderTransportOutcome(b'x'*5000, UNKNOWN)))
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert sink.events[0].status == 'INDETERMINATE'


def test_numeric_telemetry_requires_stated_source_and_exact_nonnegative_types():
    for invalid in (
        replace(UNKNOWN, physical_request_count=0),
        replace(UNKNOWN, sdk_retry_count=False, telemetry_source_ref='telemetry-1'),
        replace(UNKNOWN, physical_request_count=-1, telemetry_source_ref='telemetry-1'),
        replace(UNKNOWN, billable_minor_units=0, telemetry_source_ref='telemetry-1'),
        replace(UNKNOWN, billable_minor_units=0, billing_currency='USD'),
        replace(UNKNOWN, physical_request_count=1, sdk_retry_count=2,
                telemetry_source_ref='telemetry-1'),
    ):
        provider, _, sink = wrapper(Transport(outcome=ProviderTransportOutcome(b'valid', invalid)))
        with pytest.raises(ProviderAccountingIndeterminate):
            provider.evaluate(request=request())
        assert sink.events[0].status == 'INDETERMINATE'


def test_valid_explicit_observation_is_provenance_labeled_not_backend_verified():
    observed = ProviderPhysicalObservation(2, 1, 13, 9, 250, 3, 'USD', 'adapter-telemetry-ref')
    provider, _, sink = wrapper(Transport(outcome=ProviderTransportOutcome(b'ok', observed)))
    assert provider.evaluate(request=request()) == b'ok'
    assert sink.events[0].observation == observed


def test_callback_mutates_request_then_raises_refuses_to_return_success():
    class Mutator(Transport):
        def execute_once(self, *, request, identity):
            self.calls.append(1)
            object.__setattr__(request, 'question_id', 'foreign')
            raise RuntimeError('private')
    req = request()
    provider, _, sink = wrapper(Mutator())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=req)
    assert sink.events[0].failure_kind == 'REQUEST_INTEGRITY_LOST'


def test_installation_public_error_strips_ambient_context():
    try:
        raise RuntimeError('private ambient secret')
    except RuntimeError:
        with pytest.raises(ProviderAccountingDenied) as captured:
            OneShotDirectTextAccountingProvider(identity=identity(), transport=Transport(), sink=Sink(),
                                                max_identifier_characters=0, max_raw_response_bytes=100)
    assert captured.value.__context__ is None and captured.value.__cause__ is None


def test_provider_callback_operation_fixed_after_installation():
    transport = Transport()
    provider, _, sink = wrapper(transport)
    with pytest.raises(AttributeError):
        provider._config = (identity(), Transport().execute_once, sink.record_outcome, 100, 4096)
    assert provider.evaluate(request=request()) == b'{"x":1}'
    assert len(transport.calls) == 1


def test_same_instance_concurrent_invocations_only_one_transport_dispatch():
    provider, transport, sink = wrapper()
    def run():
        try:
            provider.evaluate(request=request())
            return 'success'
        except ProviderAccountingDenied:
            return 'denied'
    with ThreadPoolExecutor(max_workers=2) as executor:
        out = list(executor.map(lambda _: run(), range(2)))
    assert sorted(out) == ['denied', 'success']
    assert len(transport.calls) == 1 and len(sink.events) == 1


def test_transport_mutates_original_identity_then_claims_success_is_uncertain():
    class Mutator(Transport):
        def execute_once(self, *, request, identity):
            self.calls.append(1)
            object.__setattr__(identity, 'attempt_id', 'foreign-attempt')
            return ProviderTransportOutcome(b'valid', UNKNOWN)
    provider, _, sink = wrapper(Mutator())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert sink.events[0].status == 'INDETERMINATE'


def test_writer_mutates_event_identity_to_matching_receipt_is_denied():
    class MutatingSink(Sink):
        def record_outcome(self, *, event):
            object.__setattr__(event.identity, 'attempt_id', 'foreign')
            return ProviderAccountingReceipt(event.identity.event_ref,
                                             event.identity.operation_ref, event.status)
    provider, transport, sink = wrapper(sink=MutatingSink())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1


def test_writer_mutates_observation_before_matching_receipt_is_denied():
    original = ProviderPhysicalObservation(None, None, None, None, None, None, None, None)
    class MutatingSink(Sink):
        def record_outcome(self, *, event):
            object.__setattr__(event.observation, 'physical_request_count', 0)
            return ProviderAccountingReceipt(event.identity.event_ref,
                                             event.identity.operation_ref, event.status)
    provider, _, sink = wrapper(Transport(outcome=ProviderTransportOutcome(b'ok', original)), MutatingSink())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())


def test_writer_mutates_request_after_successful_transport_is_denied():
    req = request()
    class SinkMutatingRequest(Sink):
        def record_outcome(self, *, event):
            object.__setattr__(req, 'question_id', 'foreign')
            return ProviderAccountingReceipt(event.identity.event_ref,
                                             event.identity.operation_ref, event.status)
    provider, transport, _ = wrapper(sink=SinkMutatingRequest())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=req)
    assert len(transport.calls) == 1


class _ForeignEqual:
    comparisons = 0

    def __eq__(self, other):
        type(self).comparisons += 1
        return True


def test_writer_foreign_receipt_fields_rejected_without_running_equality():
    class ForeignReceipt(Sink):
        def record_outcome(self, *, event):
            self.events.append(event)
            return ProviderAccountingReceipt(_ForeignEqual(), _ForeignEqual(), _ForeignEqual())

    _ForeignEqual.comparisons = 0
    provider, transport, sink = wrapper(sink=ForeignReceipt())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1 and len(sink.events) == 1
    assert _ForeignEqual.comparisons == 0


def test_writer_foreign_event_status_and_failure_kind_never_admit_success():
    class ForeignStatus(Sink):
        def record_outcome(self, *, event):
            self.events.append(event)
            object.__setattr__(event, 'status', _ForeignEqual())
            object.__setattr__(event, 'failure_kind', _ForeignEqual())
            return ProviderAccountingReceipt(event.identity.event_ref,
                                             event.identity.operation_ref, 'RESULT_RETURNED')

    _ForeignEqual.comparisons = 0
    provider, transport, sink = wrapper(sink=ForeignStatus())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1 and len(sink.events) == 1
    assert _ForeignEqual.comparisons == 0


@pytest.mark.parametrize('field', ('event_ref', 'operation_ref', 'status'))
def test_writer_rejects_individual_foreign_receipt_field(field):
    class ForeignOne(Sink):
        def record_outcome(self, *, event):
            receipt = super().record_outcome(event=event)
            object.__setattr__(receipt, field, _ForeignEqual())
            return receipt

    _ForeignEqual.comparisons = 0
    provider, transport, sink = wrapper(sink=ForeignOne())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1
    assert _ForeignEqual.comparisons == 0


@pytest.mark.parametrize('field', ('status', 'failure_kind'))
def test_writer_rejects_individual_foreign_event_field(field):
    class ForeignOne(Sink):
        def record_outcome(self, *, event):
            self.events.append(event)
            object.__setattr__(event, field, _ForeignEqual())
            return ProviderAccountingReceipt(event.identity.event_ref,
                                             event.identity.operation_ref, 'RESULT_RETURNED')

    _ForeignEqual.comparisons = 0
    provider, transport, sink = wrapper(sink=ForeignOne())
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1
    assert _ForeignEqual.comparisons == 0


@pytest.mark.parametrize('field', [
    'physical_request_count', 'sdk_retry_count', 'input_tokens', 'output_tokens',
    'elapsed_milliseconds', 'billable_minor_units',
])
def test_extreme_telemetry_integer_denied_before_raw_result_release(field):
    # The original D-A checkpoint admitted arbitrarily huge ints here.
    valid = ProviderPhysicalObservation(1,0,1,1,1,1,'USD','fixture-telemetry')
    malformed = replace(valid, **{field: 1 << 4096})
    provider, transport, sink = wrapper(
        Transport(outcome=ProviderTransportOutcome(b'private-bytes', malformed)))
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(transport.calls) == 1
    assert len(sink.events) == 1 and sink.events[0].status == 'INDETERMINATE'
    assert sink.events[0].observation is None


def test_signed_64bit_observation_representability_boundary():
    admitted = ProviderPhysicalObservation(2**63-1,None,None,None,None,None,None,'source')
    provider, _, sink = wrapper(
        Transport(outcome=ProviderTransportOutcome(b'ok', admitted)))
    assert provider.evaluate(request=request()) == b'ok'
    assert sink.events[0].observation.physical_request_count == 2**63-1
