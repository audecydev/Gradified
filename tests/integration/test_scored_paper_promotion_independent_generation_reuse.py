"""Verify regrade CAS generation cannot be reused across distinct scored-paper identities."""
from dataclasses import replace
import pytest
from tests.integration.test_paper_lifecycle_regrade import setup_regrade, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import _gate, FixedPaperOriginal, FixedLifecycleOriginal
from grading.integration.scored_paper_promotion import ProductionPaperPromotion,PaperHandoffEligibilityState
from grading.integration.paper_accounting import ProductionPaperAccounting
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery,PaperCASState
from grading.integration.paper_lifecycle import PaperLifecycleState

@pytest.mark.parametrize('field', ['request_ref','event_ref','result_ref'])
def test_regrade_acknowledged_must_reject_reused_predecessor_cas_identity(monkeypatch,field):
    service, plan, physical, store, issuer, backend, old = setup_regrade(monkeypatch)
    history=service.execute_regrade(plan=plan)
    assert history.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert history.cas.transaction is not None
    foreign=replace(history.cas.transaction,**{field:getattr(old.transaction,field)})
    corrupted=replace(history,cas=replace(history.cas,transaction=foreign,
        receipt=replace(history.cas.receipt,transaction=foreign)))
    gate,_,_=_gate(corrupted,store,prior=old)
    before=(physical.claims,store.commits,store.reads)
    result=gate.assess()
    assert result.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, f'Accepted regrade CAS {field} reused from predecessor'
    assert (physical.claims,store.commits)==before[:2]
    assert store.reads == before[2], 'Performed avoidable backend read before rejecting crossed CAS generations'

@pytest.mark.parametrize('field', ['request_ref','event_ref','result_ref'])
def test_regrade_lost_cas_reply_must_reject_recovered_predecessor_cas_identity(monkeypatch,field):
    service, plan, physical, store, issuer, backend, old = setup_regrade(monkeypatch)
    observed=service.execute_regrade(plan=plan)
    assert observed.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    distinct=observed.cas.transaction
    original=replace(distinct,**{field:getattr(old.transaction,field)})
    lost=replace(observed,state=PaperLifecycleState.UNKNOWN,cas=replace(observed.cas,
        state=PaperCASState.UNKNOWN,transaction=None,receipt=None,academic_binding_verified=False))
    current=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(original),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    prev=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(old.transaction),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    accounting=ProductionPaperAccounting(operations=(),max_identifier_characters=128)
    gate=ProductionPaperPromotion(original_source=FixedLifecycleOriginal(lost),
        audit_recovery=current,predecessor_audit_recovery=prev,accounting=accounting,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    before=(physical.claims,store.commits,store.reads)
    result=gate.assess()
    assert result.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, f'Accepted recovered regrade CAS {field} reused from predecessor'
    assert (physical.claims,store.commits)==before[:2]


def test_unchanged_regrade_originals_remain_eligible(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    history=svc.execute_regrade(plan=plan)
    gate,_,_=_gate(history,store,prior=old)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF


def test_distinct_original_cas_recovery_remains_eligible_when_lost(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    observed=svc.execute_regrade(plan=plan)
    lost=replace(observed,state=PaperLifecycleState.UNKNOWN,cas=replace(observed.cas,
        state=PaperCASState.UNKNOWN,transaction=None,receipt=None,academic_binding_verified=False))
    curr=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(observed.cas.transaction),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    prior=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(old.transaction),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    acc=ProductionPaperAccounting(operations=(),max_identifier_characters=128)
    gate=ProductionPaperPromotion(original_source=FixedLifecycleOriginal(lost),
        audit_recovery=curr,predecessor_audit_recovery=prior,accounting=acc,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
