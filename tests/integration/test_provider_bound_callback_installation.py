"""Effectful provider callbacks must be the exact, inspectable operation installed."""
import pytest
from grading.providers.attempt_accounting import (
    OneShotDirectTextAccountingProvider, ProviderAccountingDenied,
)
from grading.providers.accounting_recovery import (
    ReadOnlyAccountingReconciler,
)
from tests.integration.test_attempt_accounting import identity, request, Transport, Sink


def one_shot(transport, sink):
    return OneShotDirectTextAccountingProvider(
        identity=identity(), transport=transport, sink=sink,
        max_identifier_characters=100, max_raw_response_bytes=4096)


def test_valid_effect_methods_are_stably_bound_after_install():
    transport = Transport()
    sink = Sink()
    installed = one_shot(transport, sink)
    # Instance monkey-patching cannot replace the admitted class method.
    transport.execute_once = lambda **kw: (_ for _ in ()).throw(AssertionError('hijacked'))
    sink.record_outcome = lambda **kw: (_ for _ in ()).throw(AssertionError('hijacked'))
    assert installed.evaluate(request=request()) == b'{"x":1}'
    assert len(transport.calls) == len(sink.events) == 1


def test_descriptor_not_executed_at_install():
    class Evil:
        @property
        def execute_once(self):
            raise AssertionError('foreign property executed')
    with pytest.raises(ProviderAccountingDenied):
        one_shot(Evil(), Sink())


def test_wrong_execution_signatures_block_before_dispatch():
    class Positional:
        def execute_once(self, request, identity):
            raise AssertionError('wrong operation executed')
    class SinkWithExtra:
        def record_outcome(self, *, event, foreign):
            raise AssertionError('wrong write executed')
    with pytest.raises(ProviderAccountingDenied):
        one_shot(Positional(), Sink())
    with pytest.raises(ProviderAccountingDenied):
        one_shot(Transport(), SinkWithExtra())


def test_instance_replacement_rejected_at_install():
    t = Transport()
    t.execute_once = lambda **kw: b'fake'
    with pytest.raises(ProviderAccountingDenied):
        one_shot(t, Sink())


def test_accounting_reader_rejects_nonplain_or_wrong_signature_before_read():
    class Evil:
        @property
        def reconcile_outcome(self):
            raise AssertionError('read descriptor executed')
    class Positional:
        def reconcile_outcome(self, identity):
            raise AssertionError('wrong lookup executed')
    for reader in (Evil(), Positional()):
        with pytest.raises(ProviderAccountingDenied):
            ReadOnlyAccountingReconciler(
                identity=identity(), store=reader, max_identifier_characters=100)
