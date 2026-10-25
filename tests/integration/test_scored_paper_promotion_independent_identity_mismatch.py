"""Independent challenge: original attempt accounting/physical provider inventory must describe SAME physical provider identity."""
from dataclasses import replace
import pytest
from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from grading.integration.paper_provider_inventory import PhysicalProviderOperation
from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff, FakeProviderReadStore

@pytest.mark.parametrize('kind', ['DIRECT','MIXED'])
@pytest.mark.parametrize('retry', [False,True])
@pytest.mark.parametrize('changed', [
    {'event_ref':'FOREIGN-EVENT-IDENTITY'},
    {'provider_id':'FOREIGN-PROVIDER'},
    {'model_id':'FOREIGN-MODEL'},
    {'configuration_ref':'FOREIGN-CONFIG'},
    {'request_fingerprint':'b'*64},
])
def test_mismatched_provider_identity_must_not_be_handoff_eligible(changed,kind,retry):
    gate, stores, source, cas_store, physical = recorded_handoff(kind,retry)
    original = source.value
    op = original.operations[0]
    different = replace(op.identity, **changed)
    new_port = PhysicalProviderOperation(op.question_id,different,ReadOnlyAccountingReconciler(
        identity=different,store=FakeProviderReadStore(),max_identifier_characters=128))
    source.value = replace(original, operations=(new_port,))
    before = (physical.claims,cas_store.commits)
    observed = gate.assess()
    assert observed.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, (
        f'C5 accepted inconsistent C4d and C4f original provider identities: {changed}')
    assert (physical.claims,cas_store.commits) == before

@pytest.mark.parametrize('kind', ['DIRECT','MIXED'])
@pytest.mark.parametrize('retry', [False,True])
def test_original_genuine_cross_identity_control(kind,retry):
    gate, stores, source, cas_store, physical = recorded_handoff(kind,retry)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
