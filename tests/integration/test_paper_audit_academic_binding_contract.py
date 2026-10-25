"""Contract validation of CAS locally reported academic-binding flag."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle,PaperLifecycleState,PaperLifecycleAuditState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery,PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle,POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('flag',[None,1,'yes', [], object()])
def test_cas_flag_type_does_not_positive_unknown(flag):
    svc,plan,physical,store,source=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    evidence=replace(actual,state=PaperLifecycleState.UNKNOWN,cas=replace(actual.cas,state=PaperCASState.UNKNOWN,
         academic_binding_verified=flag,receipt=None))
    rec=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),store=store,
          legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    audit=ProductionPaperLifecycle(cas=svc._cas,permission_source=source,legal_policy=POLICY,
          max_identifier_characters=128,max_questions=10,audit_recovery=rec)
    before=(store.reads,store.commits,physical.claims)
    res=audit.reconcile_audit(observation=evidence)
    assert res.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(repr(flag),res.state)
    assert (store.reads,store.commits,physical.claims)==before

@pytest.mark.parametrize('flag',[True,False])
def test_bool_flag_genuine_unknown_recovered(flag):
    svc,plan,physical,store,source=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    evidence=replace(actual,state=PaperLifecycleState.UNKNOWN,cas=replace(actual.cas,state=PaperCASState.UNKNOWN,
       academic_binding_verified=flag,receipt=None))
    rec=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),store=store,
       legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    audit=ProductionPaperLifecycle(cas=svc._cas,permission_source=source,legal_policy=POLICY,
       max_identifier_characters=128,max_questions=10,audit_recovery=rec)
    assert audit.reconcile_audit(observation=evidence).state is PaperLifecycleAuditState.REPORTED_COMMITTED
