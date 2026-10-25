"""Read-only paper audit: original generations are independent, bounded facts."""
from dataclasses import replace

import pytest

from grading.integration.paper_lifecycle import (
    PaperLifecycleAuditState, PaperLifecycleState, ProductionPaperLifecycle,
)
from grading.integration.whole_paper_cas import (
    PaperCASState, ProductionPaperCASDurableRecovery,
)
from tests.integration.test_paper_lifecycle_regrade import POLICY, Permissions, setup_regrade


class CountingOriginal:
    def __init__(self, transaction):
        self.transaction = transaction
        self.calls = 0

    def resolve_owned_original_paper_transaction(self):
        self.calls += 1
        return self.transaction


def _setup(monkeypatch, *, original=None):
    service, plan, physical, store, _, _, predecessor = setup_regrade(monkeypatch)
    observed = service.execute_regrade(plan=plan)
    assert observed.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    source = CountingOriginal(original if original is not None else observed.cas.transaction)
    recovery = ProductionPaperCASDurableRecovery(
        original_source=source, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    audit = ProductionPaperLifecycle(
        cas=service._cas, permission_source=Permissions(), legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10,
        audit_recovery=recovery)
    return observed, audit, source, store, physical, predecessor


@pytest.mark.parametrize('field', ('request_ref', 'event_ref', 'result_ref'))
def test_known_current_cas_identity_reuse_does_not_read_original_source(monkeypatch, field):
    observed, audit, source, store, physical, predecessor = _setup(monkeypatch)
    duplicated = replace(observed.cas.transaction,
                         **{field: getattr(predecessor.transaction, field)})
    corrupted = replace(observed, cas=replace(observed.cas,
        transaction=duplicated,
        receipt=replace(observed.cas.receipt, transaction=duplicated)))
    before = (store.reads, store.commits, physical.claims)
    assert audit.reconcile_audit(observation=corrupted).state is PaperLifecycleAuditState.UNKNOWN
    assert source.calls == 0  # Locally decidable before original-source contact
    assert (store.reads, store.commits, physical.claims) == before


def test_foreign_predecessor_custody_rejected_before_original_source(monkeypatch):
    observed, audit, source, store, physical, _ = _setup(monkeypatch)
    corrupted = replace(observed, permission=replace(observed.permission,
        predecessor_custody=observed.cas.custody))
    before = (store.reads, store.commits, physical.claims)
    assert audit.reconcile_audit(observation=corrupted).state is PaperLifecycleAuditState.UNKNOWN
    assert source.calls == 0
    assert (store.reads, store.commits, physical.claims) == before


def test_real_lost_cas_acknowledgement_is_reconciled_without_new_effects(monkeypatch):
    observed, audit, source, store, physical, _ = _setup(monkeypatch)
    uncertain = replace(observed, state=PaperLifecycleState.UNKNOWN,
        cas=replace(observed.cas, state=PaperCASState.UNKNOWN,
            transaction=None, receipt=None, academic_binding_verified=False))
    before = (store.reads, store.commits, physical.claims)
    assert audit.reconcile_audit(observation=uncertain).state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert source.calls == 1
    assert (store.reads, store.commits, physical.claims) == (before[0]+1,before[1],before[2])
