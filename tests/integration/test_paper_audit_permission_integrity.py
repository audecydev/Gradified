"""Independent negative audit permission/provenance tests external to R4 source."""
from dataclasses import replace
import pytest
from grading.contracts.job_state import GradingJobState
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleAuditState, PaperLifecycleState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('which',['foreign_issued_revision','foreign_f57_policy','wrong_f57_policy_version','untyped_f57_state','unauthorized_f57_edge','empty_approval_ref'])
def test_wrong_original_permission_cannot_be_audited_as_ours(which):
    service,plan,physical,store,issuer=setup_lifecycle()
    result=service.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    perm=result.permission
    if which=='foreign_issued_revision':
        perm=replace(perm,plan=replace(perm.plan,approval_revision='FOREIGN-APPROVAL'))
    elif which=='foreign_f57_policy':perm=replace(perm,policy_id='FOREIGN-POLICY')
    elif which=='wrong_f57_policy_version':perm=replace(perm,policy_version=True)
    elif which=='untyped_f57_state':perm=replace(perm,source_state='QUEUED')
    elif which=='unauthorized_f57_edge':perm=replace(perm, target_state=GradingJobState.COMPLETED)
    elif which=='empty_approval_ref':perm=replace(perm,approval_ref='')
    hostile=replace(result,permission=perm)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(result.cas.transaction),store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle=ProductionPaperLifecycle(cas=service._cas,permission_source=issuer,legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before=(store.reads,store.commits,physical.claims)
    actual=lifecycle.reconcile_audit(observation=hostile)
    assert actual.state is not PaperLifecycleAuditState.REPORTED_COMMITTED, (which,actual.state)
    assert (store.reads,store.commits,physical.claims)==before,(which,'backend read')
