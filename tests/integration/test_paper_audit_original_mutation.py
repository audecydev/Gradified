"""Original-audit admission: independent plan scope and read-time mutation.

External responses are assertions, never institutionally authentic grants.
"""
from dataclasses import replace

from grading.integration.paper_lifecycle import (
    PaperLifecycleAuditState, PaperLifecycleState, ProductionPaperLifecycle,
)
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_pre_effect import POLICY, setup_lifecycle
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


def test_foreign_grading_run_in_permission_rejected_without_read():
    service, plan, physical, store, issuer = setup_lifecycle()
    genuine = service.execute_first(plan=plan)
    assert genuine.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    corrupted_request = replace(genuine.permission.plan.request,
                                grading_run_id='FOREIGN-GRADING-RUN')
    foreign_plan = replace(genuine.permission.plan, request=corrupted_request)
    invalid = replace(genuine, permission=replace(genuine.permission, plan=foreign_plan))
    original = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(genuine.cas.transaction),
        store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    reader = ProductionPaperLifecycle(
        cas=service._cas, permission_source=issuer, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10, audit_recovery=original)
    before = (store.reads, store.commits, physical.claims)
    result = reader.reconcile_audit(observation=invalid)
    assert result.state is PaperLifecycleAuditState.UNKNOWN
    assert (store.reads, store.commits, physical.claims) == before


def test_original_observation_mutated_during_recovery_is_never_endorsed():
    service, plan, physical, store, issuer = setup_lifecycle()
    genuine = service.execute_first(plan=plan)
    assert genuine.state is PaperLifecycleState.CAS_ACKNOWLEDGED

    class MutatingReader:
        def reconcile_whole_paper(self, *, transaction):
            # External qualified callbacks are executable; a pathological
            # callback can try to change a frozen record using Python internals.
            object.__setattr__(genuine.permission, 'approval_ref', 'MUTATED-DURING-READ')
            return store.reconcile_whole_paper(transaction=transaction)

    original = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(genuine.cas.transaction),
        store=MutatingReader(), legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    reader = ProductionPaperLifecycle(
        cas=service._cas, permission_source=issuer, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10, audit_recovery=original)
    before = (store.reads, store.commits, physical.claims)
    result = reader.reconcile_audit(observation=genuine)
    assert result.state is PaperLifecycleAuditState.UNKNOWN
    assert (store.reads, store.commits, physical.claims) == (
        before[0] + 1, before[1], before[2])
    assert not result.authorizes_retry and not result.authorizes_publication
