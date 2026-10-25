"""Causal byte-transport effects, correlation, loss and single-use safety."""
from dataclasses import replace
import hashlib
from concurrent.futures import ThreadPoolExecutor
import pytest

from grading.providers.canonical_transport import (
    CanonicalDirectTextTransport, CanonicalProviderDispatch, CanonicalProviderReply,
)
from grading.providers.attempt_accounting import (
    OneShotDirectTextAccountingProvider, ProviderAccountingDenied,
    ProviderAccountingIndeterminate,
)
from grading.providers.semantic_replay import _direct_text_semantic_request_bytes
from tests.integration.test_attempt_accounting import request, identity, Sink


class Sender:
    def __init__(self):
        self.seen = []
        self.change = None
        self.error = None

    def deliver(self, *, dispatch):
        self.seen.append(dispatch)
        if self.error:
            raise self.error
        original = dispatch
        if self.change:
            return self.change(dispatch)
        return reply(original)


def reply(d):
    i = d.identity
    return CanonicalProviderReply(d.dispatch_ref, i.operation_ref, i.event_ref,
                                  i.logical_evaluation_ref, i.attempt_id, i.request_ref,
                                  d.request_sha256, i.provider_id, i.model_id,
                                  i.configuration_ref, b'{"x":1}')


def setup(sender=None):
    sender = sender or Sender()
    original = identity()
    t = CanonicalDirectTextTransport(identity=original, dispatch_ref='dispatch-1',
                                     sender=sender, max_identifier_characters=100,
                                     max_request_bytes=8192, max_response_bytes=4096)
    sink = Sink()
    p = OneShotDirectTextAccountingProvider(identity=original, transport=t, sink=sink,
                                            max_identifier_characters=100,
                                            max_raw_response_bytes=4096)
    return p, sender, sink


def test_valid_canonical_bytes_preserve_replay_fingerprint_and_unknown_telemetry():
    provider, sender, sink = setup()
    assert provider.evaluate(request=request()) == b'{"x":1}'
    assert len(sender.seen) == 1
    d = sender.seen[0]
    assert d.request_bytes == _direct_text_semantic_request_bytes(request())
    assert hashlib.sha256(d.request_bytes).hexdigest() == identity().request_fingerprint
    assert sink.events[0].status == 'RESULT_RETURNED'
    assert sink.events[0].observation.physical_request_count is None
    assert sink.events[0].observation.billable_minor_units is None


@pytest.mark.parametrize('field,bad', [
    ('dispatch_ref','other'), ('operation_ref','other'), ('event_ref','other'),
    ('logical_evaluation_ref','other'), ('attempt_id','other'), ('request_ref','other'),
    ('request_sha256','other'), ('provider_id','other'), ('model_id','other'),
    ('configuration_ref','other'), ('raw_payload',b'x'*4097),
])
def test_forged_reply_is_indeterminate_and_never_releases_raw_bytes(field,bad):
    sender = Sender()
    sender.change = lambda d: replace(reply(d), **{field:bad})
    provider, sender, sink = setup(sender)
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=request())
    assert len(sender.seen) == 1
    assert [event.status for event in sink.events] == ['INDETERMINATE']


def test_mutated_original_request_cannot_change_delivered_immutable_bytes():
    original = request()
    sender = Sender()
    def mutator(d):
        object.__setattr__(original, 'question_text', 'WRONG')
        assert type(d.request_bytes) is bytes
        assert b'WRONG' not in d.request_bytes
        return reply(d)
    sender.change = mutator
    provider, sender, sink = setup(sender)
    with pytest.raises(ProviderAccountingIndeterminate):
        provider.evaluate(request=original)
    assert sink.events[0].status == 'INDETERMINATE'
    assert sender.seen[0].request_bytes == _direct_text_semantic_request_bytes(request())


def test_sender_can_only_receive_bytes_and_not_mutable_semantic_request():
    provider, sender, sink = setup()
    provider.evaluate(request=request())
    assert type(sender.seen[0]) is CanonicalProviderDispatch
    assert not hasattr(sender.seen[0], 'question_text')
    with pytest.raises(TypeError):
        sender.seen[0].request_bytes[0] = 9


def test_unknown_effect_lost_ack_is_indeterminate_and_not_retried():
    sender = Sender()
    sender.error = TimeoutError('secret vendor url')
    provider, sender, sink = setup(sender)
    with pytest.raises(ProviderAccountingIndeterminate) as err:
        provider.evaluate(request=request())
    assert err.value.__context__ is None
    assert [event.status for event in sink.events] == ['INDETERMINATE']
    with pytest.raises(ProviderAccountingDenied):
        provider.evaluate(request=request())
    assert len(sender.seen) == 1


def test_installed_sender_operation_cannot_be_replaced():
    sender = Sender()
    provider, _, _ = setup(sender)
    sender.deliver = lambda **kw: (_ for _ in ()).throw(AssertionError('hijack'))
    assert provider.evaluate(request=request()) == b'{"x":1}'
    assert len(sender.seen) == 1


def test_evil_descriptor_rejected_without_calling_it():
    class Evil:
        @property
        def deliver(self):
            raise AssertionError('foreign descriptor executed')
    with pytest.raises(ProviderAccountingDenied):
        setup(Evil())


def test_same_bridge_concurrent_only_one_dispatch():
    p, sender, sink = setup()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(p.evaluate, request=request()) for _ in range(2)]
        results = []
        for job in jobs:
            try:
                results.append(job.result())
            except ProviderAccountingDenied:
                results.append('DENIED')
    assert sorted((str(x) for x in results)) == ["DENIED", "b'{\"x\":1}'"]
    assert len(sender.seen) == len(sink.events) == 1


def test_new_sender_reply_claims_do_not_prove_physical_count():
    p, _, sink = setup()
    assert p.evaluate(request=request())
    assert sink.events[0].observation.physical_request_count is None


def test_sender_cannot_forge_unknown_physical_telemetry_through_shared_observation():
    # A frozen Python dataclass is not immutable against object.__setattr__.
    # The sender can reach a module global but not the fresh observation made
    # after the callback returns. No unqualified vendor telemetry is admitted.
    from grading.providers import canonical_transport as bridge
    original = bridge._UNKNOWN
    sender = Sender()
    def tamper(dispatch):
        object.__setattr__(original, 'physical_request_count', 2)
        object.__setattr__(original, 'sdk_retry_count', 1)
        object.__setattr__(original, 'input_tokens', 13)
        object.__setattr__(original, 'telemetry_source_ref', 'forged')
        return reply(dispatch)
    sender.change = tamper
    provider, _, sink = setup(sender)
    try:
        assert provider.evaluate(request=request()) == b'{"x":1}'
        event = sink.events[0]
        assert event.status == 'RESULT_RETURNED'
        assert event.observation is not original
        assert all(getattr(event.observation, name) is None for name in (
            'physical_request_count', 'sdk_retry_count', 'input_tokens',
            'output_tokens', 'elapsed_milliseconds', 'billable_minor_units',
            'billing_currency', 'telemetry_source_ref'))
    finally:
        for name in ('physical_request_count', 'sdk_retry_count', 'input_tokens',
                     'output_tokens', 'elapsed_milliseconds', 'billable_minor_units',
                     'billing_currency', 'telemetry_source_ref'):
            object.__setattr__(original, name, None)
