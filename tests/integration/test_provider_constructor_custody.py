"""Verify physical provider accounting resists callback changes to its observation factory."""
from grading.providers import canonical_transport as bridge
from grading.providers.attempt_accounting import ProviderPhysicalObservation
from tests.integration.test_canonical_provider_transport import Sender, reply, setup, request


def test_sender_cannot_substitute_unknown_observation_constructor_after_callback():
    saved_constructor = bridge.ProviderPhysicalObservation
    sender = Sender()

    def malicious_sender(dispatch):
        # Separately installed sender can modify a publicly accessible module symbol.
        # Restore immediately after evaluate so no global mutation survives the test.
        bridge.ProviderPhysicalObservation = lambda *values: ProviderPhysicalObservation(
            2, 1, 13, None, None, None, None, 'unqualified-claim')
        return reply(dispatch)

    sender.change = malicious_sender
    provider, _, sink = setup(sender)
    try:
        result = provider.evaluate(request=request())
        assert result == b'{"x":1}'
        assert len(sink.events) == 1
        recorded = sink.events[0]
        assert recorded.status == 'RESULT_RETURNED'
        assert recorded.observation.physical_request_count is None, (
            'Sender-substituted module constructor supplied unverified physical count at accounting effect'
        )
        assert recorded.observation.sdk_retry_count is None
        assert recorded.observation.input_tokens is None
        assert recorded.observation.telemetry_source_ref is None
    finally:
        bridge.ProviderPhysicalObservation = saved_constructor


def test_sender_cannot_substitute_transport_outcome_constructor_after_callback():
    from grading.providers.attempt_accounting import ProviderTransportOutcome, ProviderPhysicalObservation
    saved_constructor = bridge.ProviderTransportOutcome
    sender = Sender()

    def malicious_sender(dispatch):
        bridge.ProviderTransportOutcome = lambda payload, observation: ProviderTransportOutcome(
            payload,
            ProviderPhysicalObservation(2, 1, 13, None, None, None, None, 'unqualified-claim'),
        )
        return reply(dispatch)

    sender.change = malicious_sender
    provider, _, sink = setup(sender)
    try:
        result = provider.evaluate(request=request())
        assert result == b'{"x":1}'
        assert len(sink.events) == 1
        recorded = sink.events[0]
        assert recorded.status == 'RESULT_RETURNED'
        assert recorded.observation.physical_request_count is None, (
            'Sender-substituted return-outcome factory supplied forged metrics')
        assert recorded.observation.sdk_retry_count is None
        assert recorded.observation.telemetry_source_ref is None
    finally:
        bridge.ProviderTransportOutcome = saved_constructor
