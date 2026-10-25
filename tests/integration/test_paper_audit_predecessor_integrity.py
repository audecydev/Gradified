"""Adversarial tests for predecessor evidence and paper audit integrity."""
from dataclasses import replace
import pytest
from grading.contracts.job_state import GradingJobState
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleAuditState, PaperLifecycleState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_regrade import setup_regrade,POLICY
from tests.integration.test_paper_lifecycle_pre_effect import Permissions
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('change', [
    {'f57_policy_id':'OTHER-F57-POLICY'},
    {'f57_policy_version':400},
    {'source_state':GradingJobState.COMPLETED},
    {'target_state':GradingJobState.COMPLETED},
    {'request_ref':None},
    {'result_ref':'FORGED-PREDECESSOR-RESULT'},
    {'expected_ledger_revision':None},
])
def test_regrade_audit_rejects_invalid_predecessor_before_backend_read(monkeypatch,change):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    outcome=svc.execute_regrade(plan=plan)
    assert outcome.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(outcome.cas.transaction),
      store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
      legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    malformed=replace(old.transaction,**change)
    altered=replace(outcome,predecessor=malformed,permission=replace(outcome.permission,predecessor=malformed))
    before=(store.reads,store.commits,physical.claims)
    status=reader.reconcile_audit(observation=altered)
    assert status.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(change,status.state)
    assert (store.reads,store.commits,physical.claims)==before,(change,'forbidden read',store.reads-before[0])

def test_valid_regrade_audit_control(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    outcome=svc.execute_regrade(plan=plan)
    assert outcome.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(outcome.cas.transaction),
      store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
      legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=store.reads
    status=reader.reconcile_audit(observation=outcome)
    assert status.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert store.reads==before+1

@pytest.mark.parametrize('field',['request_ref','event_ref','result_ref'])
def test_regrade_audit_reused_predecessor_cas_identity_pre_read(monkeypatch,field):
    from grading.integration.whole_paper_cas import PaperCASState
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    outcome=svc.execute_regrade(plan=plan)
    assert outcome.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    duplicated=replace(outcome.cas.transaction,**{field:getattr(old.transaction,field)})
    modified_cas=replace(outcome.cas,transaction=duplicated,receipt=replace(outcome.cas.receipt,transaction=duplicated))
    altered=replace(outcome,cas=modified_cas)
    recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(duplicated),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=(store.reads,store.commits,physical.claims)
    status=reader.reconcile_audit(observation=altered)
    assert status.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(field,status.state)
    assert (store.reads,store.commits,physical.claims)==before, (field, 'forbidden read')

@pytest.mark.parametrize('field',['request_ref','event_ref','result_ref'])
def test_regrade_lost_reply_audit_reused_predecessor_cas_identity(monkeypatch,field):
    from grading.integration.whole_paper_cas import PaperCASState
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    outcome=svc.execute_regrade(plan=plan)
    duplicated=replace(outcome.cas.transaction,**{field:getattr(old.transaction,field)})
    altered=replace(outcome,state=PaperLifecycleState.UNKNOWN,
        cas=replace(outcome.cas,state=PaperCASState.UNKNOWN,transaction=None,receipt=None,academic_binding_verified=False))
    recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(duplicated),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=(store.reads,store.commits,physical.claims)
    status=reader.reconcile_audit(observation=altered)
    assert status.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(field,status.state)
    assert (store.reads,store.commits,physical.claims)==before,(field,'forbidden read')

def test_valid_regrade_original_cas_lost_reply_still_reconciles(monkeypatch):
    from grading.integration.whole_paper_cas import PaperCASState
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    outcome=svc.execute_regrade(plan=plan)
    assert outcome.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    lost=replace(outcome,state=PaperLifecycleState.UNKNOWN,
      cas=replace(outcome.cas,state=PaperCASState.UNKNOWN,transaction=None,receipt=None,academic_binding_verified=False))
    recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(outcome.cas.transaction),
       store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
       legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=(store.reads,store.commits,physical.claims)
    status=reader.reconcile_audit(observation=lost)
    assert status.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads,store.commits,physical.claims)==(before[0]+1,before[1],before[2])
