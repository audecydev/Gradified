"""Independent negative paper lifecycle original-state/audit correlation, external to source."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleAuditState, PaperLifecycleState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('fake',[PaperLifecycleState.PRE_EFFECT_BLOCKED,PaperLifecycleState.CAS_BLOCKED,PaperLifecycleState.REGRADE_LINEAGE_VERIFIED])
def test_contradictory_precommit_lifecycle_state_no_positive_audit_or_read(fake):
    service,plan,physical,store,issuer=setup_lifecycle()
    result=service.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(result.cas.transaction),store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle=ProductionPaperLifecycle(cas=service._cas,permission_source=issuer,legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before=(store.reads,store.commits,physical.claims)
    actual=lifecycle.reconcile_audit(observation=replace(result,state=fake))
    assert actual.state is not PaperLifecycleAuditState.REPORTED_COMMITTED, (fake,actual.state)
    assert (store.reads,store.commits,physical.claims)==before,(fake,'backend contact')

def test_valid_first_control():
    service,plan,physical,store,issuer=setup_lifecycle()
    result=service.execute_first(plan=plan)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(result.cas.transaction),store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle=ProductionPaperLifecycle(cas=service._cas,permission_source=issuer,legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before=store.reads
    assert lifecycle.reconcile_audit(observation=result).state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert store.reads == before+1


def test_genuine_lost_ack_original_cas_reconciles_without_reclaim():
    from grading.integration.whole_paper_cas import PaperCASState
    service,plan,physical,store,issuer=setup_lifecycle()
    result=service.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    uncertain=replace(result,state=PaperLifecycleState.UNKNOWN,
        cas=replace(result.cas,state=PaperCASState.UNKNOWN,receipt=None))
    durable=ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(result.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle=ProductionPaperLifecycle(cas=service._cas,
        permission_source=issuer,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before=(store.reads,store.commits,physical.claims)
    outcome=lifecycle.reconcile_audit(observation=uncertain)
    assert outcome.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads,store.commits,physical.claims)==(
        before[0]+1,before[1],before[2])
    assert not outcome.authorizes_retry and not outcome.authorizes_publication


@pytest.mark.parametrize('fake',[PaperLifecycleState.PRE_EFFECT_BLOCKED,PaperLifecycleState.CAS_BLOCKED,PaperLifecycleState.REGRADE_LINEAGE_VERIFIED])
def test_nonexecuted_state_cannot_recover_uncertain_cas_as_audited_original(fake):
    from grading.integration.whole_paper_cas import PaperCASState
    service,plan,physical,store,issuer=setup_lifecycle()
    genuine=service.execute_first(plan=plan)
    assert genuine.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    contradiction=replace(genuine,state=fake,
        cas=replace(genuine.cas,state=PaperCASState.UNKNOWN,receipt=None))
    recovery=ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(genuine.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    consumer=ProductionPaperLifecycle(cas=service._cas,
        permission_source=issuer,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=(store.reads,store.commits,physical.claims)
    outcome=consumer.reconcile_audit(observation=contradiction)
    assert outcome.state is not PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads,store.commits,physical.claims)==before
