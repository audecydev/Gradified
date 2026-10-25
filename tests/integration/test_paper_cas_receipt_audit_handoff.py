"""Downstream paper lifecycle audit consequence of malformed locally supplied CAS receipt."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import PaperCASState, ProductionPaperCASDurableRecovery
from grading.integration.paper_lifecycle import PaperLifecycleState,PaperLifecycleAuditState,ProductionPaperLifecycle
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle,POLICY,Permissions
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('bad', ['LOCALLY-INVALID', 1])
def test_c4_audit_must_not_report_committed_from_malformed_local_cas_receipt(bad):
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),
        store=store, legal_policy=POLICY, max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    uncertain=replace(actual,state=PaperLifecycleState.UNKNOWN,cas=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=bad))
    before=store.reads
    result=reader.reconcile_audit(observation=uncertain)
    assert result.state is not PaperLifecycleAuditState.REPORTED_COMMITTED, (bad, result.state)
    assert store.reads==before

def test_c4_genuine_lost_ack_original_recovery_positive_control():
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),
        store=store, legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    reader=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    uncertain=replace(actual,state=PaperLifecycleState.UNKNOWN,cas=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=None))
    assert reader.reconcile_audit(observation=uncertain).state is PaperLifecycleAuditState.REPORTED_COMMITTED
