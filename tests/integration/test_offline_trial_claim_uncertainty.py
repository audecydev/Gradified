"""Causal teacher-label reference claim-effect taxonomy: contact never proves no external effect.

These tests model an issuer that has *already made* a durable reservation but
fails to return an admissible acknowledgment. The submitted original source
incorrectly reports such outcomes as definitive local denials.
"""
from dataclasses import replace

import pytest

from grading.benchmark.offline_trial import (
    OfflineTrialClaim, OfflineTrialDenied, OfflineTrialIndeterminate,
    TrialClaimDisposition,
)
from test_offline_trial import Backend, make


class PostEffectIssuer(Backend):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.reservations = []

    def authorize_and_claim(self, *, request):
        self.calls += 1
        # Simulates a committed FRESH reservation in an external atomic store.
        self.reservations.append((request.tenant_ref, request.trial_request_ref))
        return self.operation(request)


def _run_uncertain(issuer):
    trial, backend, reader, replay, history = make(backend=issuer)
    with pytest.raises(OfflineTrialIndeterminate) as caught:
        trial.run()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert backend.calls == 1
    assert len(backend.reservations) == 1
    assert (reader.calls, replay.calls, len(history.events)) == (0, 0, 0)
    # Never locally grant a second attempt to try to discover the status.
    with pytest.raises(OfflineTrialDenied):
        trial.run()
    assert backend.calls == 1


def test_issuer_post_effect_domain_denial_cannot_claim_no_effect():
    def fail(request):
        raise OfflineTrialDenied('issuer raised after committing')
    _run_uncertain(PostEffectIssuer(fail))


def test_issuer_post_effect_malformed_return_cannot_claim_no_effect():
    _run_uncertain(PostEffectIssuer(lambda request: object()))


def test_issuer_post_effect_foreign_claim_cannot_claim_no_effect():
    def foreign(request):
        return OfflineTrialClaim(
            replace(request, tenant_ref='foreign-tenant'), TrialClaimDisposition.FRESH,
            'trial', 'event', 'grant', 'policy', 'v1')
    _run_uncertain(PostEffectIssuer(foreign))


def test_issuer_post_effect_request_mutation_cannot_claim_no_effect():
    def mutate(request):
        object.__setattr__(request, 'tenant_ref', 'foreign-tenant')
        return OfflineTrialClaim(
            request, TrialClaimDisposition.FRESH, 'trial', 'event', 'grant', 'policy', 'v1')
    _run_uncertain(PostEffectIssuer(mutate))


def test_issuer_post_effect_malformed_nonfresh_receipt_cannot_claim_no_effect():
    def malformed(request):
        return OfflineTrialClaim(
            request, TrialClaimDisposition.CONFLICT, 'claimed-trial', None, None, None, None)
    _run_uncertain(PostEffectIssuer(malformed))


def test_well_formed_nonfresh_response_remains_explicit_denial_without_read():
    # Exact issuer response is authoritative within the installed trusted-port
    # contract.  It is not a guarantee against a dishonest backend.
    trial, backend, reader, replay, history = make(backend=Backend(disposition=TrialClaimDisposition.REVOKED))
    with pytest.raises(OfflineTrialDenied):
        trial.run()
    assert (backend.calls, reader.calls, replay.calls, len(history.events)) == (1, 0, 0, 0)


def test_uncertain_contact_reconciles_original_request_read_only_without_reclaim():
    from test_offline_trial import REQ
    from grading.benchmark.offline_trial import TrialClaimDisposition
    from grading.benchmark.recovery import (
        OfflineRecoveryDisposition, OfflineTrialRecoveryFact,
        ReadOnlyOfflineTrialRecovery,
    )

    def fail_after_reservation(request):
        raise OfflineTrialDenied('committed but reply lost')

    issuer = PostEffectIssuer(fail_after_reservation)
    _run_uncertain(issuer)

    class RecoveryStore:
        def __init__(self):
            self.requests = []

        def reconcile_trial_request(self, *, request):
            self.requests.append(request)
            original_claim = OfflineTrialClaim(
                request, TrialClaimDisposition.FRESH,
                'trial', 'event', 'grant', 'policy', 'v1')
            return OfflineTrialRecoveryFact(
                request, OfflineRecoveryDisposition.CLAIMED, original_claim,
                None, None, None)

    store = RecoveryStore()
    fact = ReadOnlyOfflineTrialRecovery(
        request=REQ, store=store, max_identifier_characters=100).reconcile()
    assert fact.disposition is OfflineRecoveryDisposition.CLAIMED
    assert fact.receipt is None and fact.output_sha256 is None
    assert store.requests == [REQ]
    assert issuer.calls == 1  # recovery did not issue a second trial claim
