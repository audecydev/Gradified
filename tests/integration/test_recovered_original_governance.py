"""Read-only same-original recovery on actual connected synthetic owner fixtures."""
import pytest
from dataclasses import replace
from grading.integration.governed_operation_consumer import GovernedOperationState, ScoredOperationIdentity
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.qualified_governed_operation import ProductionOriginalQualifiedGovernedConsumer
from grading.integration.recovered_original_governance import (
    ProductionRecoveredOriginalGovernance, RecoveredOriginalGovernance,
)
from tests.integration.test_governed_operation_consumer import rig


class PendingOriginal:
    """Synthetic independent fixed recovery target; real backend must issue it."""
    def __init__(self, identity=None):
        self.identity = identity
        self.calls = 0
    def read_fixed_recovery_target(self):
        self.calls += 1
        return self.identity


def identity_from_observed(kind, observed):
    cas = observed.governed.operation.execution.cas
    tx = cas.transaction
    plan = tx.intent.plan
    req = plan.request
    return ScoredOperationIdentity(kind, req.tenant_ref, req.grading_run_id,
        tx.result_ref, plan.source_revision, tx.request_ref, tx.event_ref,
        cas.receipt.commit_ref if cas.receipt is not None else 'NO-ACK')


def setup_scored(*, family='DIRECT'):
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig(family=family)
    qualified = ProductionOriginalQualifiedGovernedConsumer(governed=owner)
    initial = qualified.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert initial.state is GovernedOperationState.HANDOFF_ELIGIBLE
    recovery = ProductionRecoveredOriginalGovernance(qualified=qualified,
        target_source=PendingOriginal(identity_from_observed(PaperOperationKind.FIRST, initial)))
    counters = (physical.claims, store.commits, conditional.contacts)
    return recovery, qualified, source, originals, views, counters, physical, store, conditional


def test_existing_scored_original_recovers_without_any_new_effect():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    calls = source.calls
    result = recovery.recover()
    assert type(result) is RecoveredOriginalGovernance
    assert result.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert result.operation.original_scored_result_ref == result.handoff.decision.original_scored_result_ref
    assert result.operation.commit_ref
    assert source.calls == calls + 1
    assert (physical.claims, store.commits, conditional.contacts) == before
    assert not result.authorizes_publication and not result.authorizes_retry


def test_missing_fixed_original_history_cannot_use_prior_score_as_credential():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    qualified._c5._original.__self__.original = None
    reads = source.calls
    outcome = recovery.recover()
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.operation is None and outcome.handoff is None
    assert source.calls == reads
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_wrong_original_governed_key_blocks_all_academic_readers():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    source.foreign = {'original_scored_result_ref': 'FOREIGN-SCORE'}
    seen = tuple(x.calls for x in originals + views)
    assert recovery.recover().state is GovernedOperationState.UNKNOWN
    assert tuple(x.calls for x in originals + views) == seen
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_fixed_history_revoked_during_governed_read_fails_closed():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    source.on_call = lambda: setattr(qualified._c5._original.__self__, 'original', None)
    outcome = recovery.recover()
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_uncertain_policy_or_readiness_never_becomes_recovered_eligibility():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    originals[2].value = None
    assert recovery.recover().state is GovernedOperationState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_recovered_original_with_independently_reported_review_is_not_eligible():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    originals[1].value = False
    result = recovery.recover()
    assert result.state is GovernedOperationState.REVIEW
    assert result.operation is not None and result.handoff is not None
    assert not result.authorizes_publication
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_recovery_before_any_scored_original_never_initiates_scoring():
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    qualified = ProductionOriginalQualifiedGovernedConsumer(governed=owner)
    # The rig normally seeds a valid prior historical scored operation.
    # Remove that record to represent a genuinely absent original.
    qualified._c5._original.__self__.original = None
    recovery = ProductionRecoveredOriginalGovernance(qualified=qualified,
        target_source=PendingOriginal(None))
    result = recovery.recover()
    assert result.state is GovernedOperationState.UNKNOWN
    assert result.operation is None and result.handoff is None
    assert (physical.claims, store.commits, conditional.contacts, source.calls) == (0, 0, 0, 0)


def test_missing_durable_original_after_lost_ack_does_not_trigger_retry():
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    conditional.lost_ack = True
    qualified = ProductionOriginalQualifiedGovernedConsumer(governed=owner)
    first = qualified.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert first.state is GovernedOperationState.UNKNOWN
    counters = (physical.claims, store.commits, conditional.contacts)
    # A lost acknowledgment is not proof of failure or success. Simulate
    # absent independent committed history, not the rig's seeded prior one.
    qualified._c5._original.__self__.original = None
    recovered = ProductionRecoveredOriginalGovernance(qualified=qualified,
        target_source=PendingOriginal(None)).recover()
    assert recovered.state is GovernedOperationState.UNKNOWN
    assert recovered.operation is None and recovered.handoff is None
    assert (physical.claims, store.commits, conditional.contacts) == counters
    assert source.calls == 0


@pytest.mark.parametrize('family', ('CHOICE', 'NUMERIC', 'MIXED'))
def test_foreign_fixed_target_cannot_reuse_any_family_original(family):
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig(family=family)
    qualified = ProductionOriginalQualifiedGovernedConsumer(governed=owner)
    observed = qualified.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert observed.state is GovernedOperationState.UNKNOWN
    before = (physical.claims, store.commits, conditional.contacts)
    target = identity_from_observed(PaperOperationKind.FIRST, observed)
    recovered = ProductionRecoveredOriginalGovernance(qualified=qualified,
        target_source=PendingOriginal(replace(target, original_scored_result_ref='FOREIGN-SCORE'))).recover()
    assert recovered.state is GovernedOperationState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


# Independently reproduced successor acceptance: the fixed governed scored-paper handoff history must
# agree with the *currently* selected durable pending original at return.
def test_pending_original_changes_during_governed_callback_refuses_eligibility():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    pending = recovery._target.__self__
    original = pending.identity
    source.on_call = lambda: setattr(pending, 'identity',
        replace(original, original_scored_result_ref='OTHER-PENDING-ORIGINAL'))
    outcome = recovery.recover()
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.operation is None and outcome.handoff is None
    assert pending.calls == 2
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_pending_original_disappears_during_governed_review_refuses_review():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    pending = recovery._target.__self__
    originals[1].value = False  # A genuine local REVIEW, not HANDOFF_ELIGIBLE.
    source.on_call = lambda: setattr(pending, 'identity', None)
    outcome = recovery.recover()
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.operation is None
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_unavailable_final_pending_original_read_refuses_after_governed_reads():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    original = recovery._target.__self__.identity
    class FailingPending(PendingOriginal):
        def read_fixed_recovery_target(self):
            if self.calls >= 1:
                raise OSError('Durable pending selector became unavailable')
            return super().read_fixed_recovery_target()
    # Use an installed plain class method, not dynamically replaced callbacks.
    next_recovery = ProductionRecoveredOriginalGovernance(
        qualified=qualified, target_source=FailingPending(original))
    assert next_recovery.recover().state is GovernedOperationState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before
