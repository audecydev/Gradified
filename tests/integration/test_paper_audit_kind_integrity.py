"""Read-only paper lifecycle audit must not misreport a different lifecycle generation/kind."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import (
    ProductionPaperLifecycle, PaperLifecycleKind, PaperLifecycleAuditState,
)
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


@pytest.mark.parametrize('kind', ['FIRST', 'REGRADE', PaperLifecycleKind.REGRADE])
def test_false_or_untyped_audit_kind_does_not_read_backend(kind):
    service, plan, physical, store, issuer = setup_lifecycle()
    result = service.execute_first(plan=plan)
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(result.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle = ProductionPaperLifecycle(
        cas=service._cas, permission_source=issuer,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before = (store.reads, store.commits, physical.claims)
    actual = lifecycle.reconcile_audit(observation=replace(result, kind=kind))
    assert actual.state is not PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads, store.commits, physical.claims) == before


def test_genuine_read_only_first_kind_reports_cas_without_permission_grant():
    service,plan,physical,store,issuer=setup_lifecycle()
    result=service.execute_first(plan=plan)
    durable=ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(result.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle=ProductionPaperLifecycle(cas=service._cas,
        permission_source=issuer,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before=store.reads
    outcome=lifecycle.reconcile_audit(observation=result)
    assert outcome.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert store.reads==before+1
    assert outcome.authorizes_publication is False
    assert outcome.authorizes_retry is False


def test_forged_permission_and_kind_cannot_relabel_original_first_as_regrade():
    service,plan,physical,store,issuer=setup_lifecycle()
    genuine=service.execute_first(plan=plan)
    tx=genuine.cas.transaction
    forged=replace(genuine, kind=PaperLifecycleKind.REGRADE,
        predecessor=tx,
        permission=replace(genuine.permission,kind=PaperLifecycleKind.REGRADE,
                           predecessor=tx,predecessor_custody=genuine.cas.custody))
    durable=ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(tx),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    lifecycle=ProductionPaperLifecycle(cas=service._cas,
        permission_source=issuer,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=durable)
    before=(store.reads,store.commits,physical.claims)
    assert lifecycle.reconcile_audit(observation=forged).state is PaperLifecycleAuditState.UNKNOWN
    assert (store.reads,store.commits,physical.claims)==before
