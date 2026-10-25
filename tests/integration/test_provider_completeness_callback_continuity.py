"""Verify callbacks cannot rewrite admitted physical provider inventory completeness."""
from dataclasses import replace
import pytest
from grading.integration.paper_provider_inventory import ProductionProviderInventory, ProviderInventoryState
from grading.integration.scored_paper_promotion import ProductionPaperPromotion, PaperHandoffEligibilityState
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff
from tests.integration.test_authorized_retry_claim import POLICY

class MutatingMeasurements:
    def __init__(self, completion_source, measurements_source, mode):
        self.completion = completion_source
        self.measured = measurements_source
        self.mode = mode
        self.calls = 0
    def resolve_provider_measurements(self):
        self.calls += 1
        original = self.completion.value
        if self.mode == 'policy_id':
            object.__setattr__(original, 'policy_id', 'REVOKED-REPLACED-METRIC-POLICY')
            return replace(self.measured.value, policy_id=original.policy_id)
        if self.mode == 'policy_version':
            object.__setattr__(original, 'policy_version', 99)
            return replace(self.measured.value, policy_version=99)
        if self.mode == 'completeness_withdrawn':
            object.__setattr__(original, 'complete', False)
            return self.measured.value
        if self.mode == 'policy_new_required_metric':
            object.__setattr__(original, 'required_measurements', original.required_measurements + ('unmeasured-late',))
            return self.measured.value
        return self.measured.value

def _setup(mode='none', retry=False):
    gate, stores, source, cas_store, physical = recorded_handoff('DIRECT', retry)
    old=gate._physical_accounting
    completeness=old._completeness.__self__
    measured=old._measurements.__self__
    callback=MutatingMeasurements(completeness, measured, mode)
    physical_inventory=ProductionProviderInventory(
        original_source=old._source.__self__,
        applicability_source=old._applicability.__self__,
        completeness_source=completeness,
        measurement_source=callback,
        max_identifier_characters=128, max_questions=10,
    )
    opts = {'retry_original_recovery': gate._retry_recovery,
            'retry_purpose_policy':gate._retry_purpose} if retry else {}
    assessed=ProductionPaperPromotion(
        original_source=gate._original.__self__,audit_recovery=gate._audit,
        accounting=gate._accounting, physical_accounting=physical_inventory,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,**opts)
    return assessed, callback, physical_inventory,physical,cas_store

@pytest.mark.parametrize('mode', ('policy_id','policy_version','completeness_withdrawn','policy_new_required_metric'))
@pytest.mark.parametrize('retry',(False,True))
def test_mutated_qualified_completeness_cannot_authorize_handoff(mode,retry):
    gate, callback, c4f, physical, store = _setup(mode,retry)
    before=(physical.claims,store.commits)
    result=gate.assess()
    assert callback.calls==1, 'must actually exercise adversarial measurement callback'
    assert (physical.claims,store.commits)==before, 'no new physical effects in C5'
    assert result.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, (
       f'Callback rewrote already-admitted original completeness {mode}, then returned positive {result.state}')

@pytest.mark.parametrize('retry',(False,True))
def test_genuine_unmodified_policy_unchanged_positive(retry):
    gate, callback, _, physical, store=_setup('none',retry)
    before=(physical.claims,store.commits)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert callback.calls==1
    assert (physical.claims,store.commits)==before
