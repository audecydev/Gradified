"""Independent original-source probes: contradictory CAS outcome status at paper lifecycle audit boundary."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState, PaperLifecycleAuditState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery, PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_paper_lifecycle_regrade import setup_regrade
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal
from tests.integration.test_paper_lifecycle_pre_effect import Permissions


def setup_first():
    svc,plan,phys,store,perms=setup_lifecycle()
    res=svc.execute_first(plan=plan)
    assert res.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    rec=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(res.cas.transaction), store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    audit=ProductionPaperLifecycle(cas=svc._cas,permission_source=perms,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=rec)
    return res,audit,phys,store

@pytest.mark.parametrize('cas_state', ['UNKNOWN','COMMITTED','BLOCKED', 'NOT_ELIGIBLE', True, 1, None])
def test_malformed_cas_state_unknown_lifecycle_not_positive(cas_state):
    res,audit,phys,store=setup_first()
    hostile=replace(res, state=PaperLifecycleState.UNKNOWN, cas=replace(res.cas,state=cas_state, receipt=None))
    before=(store.reads,store.commits,phys.claims)
    decision=audit.reconcile_audit(observation=hostile)
    assert decision.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(repr(cas_state),decision.state)
    assert (store.reads,store.commits,phys.claims)==before,('forbidden read',cas_state)

@pytest.mark.parametrize('cas_state',[PaperCASState.UNKNOWN, PaperCASState.COMMITTED])
def test_genuine_uncertain_cas_ack_recovers(cas_state):
    res,audit,phys,store=setup_first()
    uncertain=replace(res,state=PaperLifecycleState.UNKNOWN,cas=replace(res.cas,state=cas_state,receipt=None))
    before=(store.reads,store.commits,phys.claims)
    assert audit.reconcile_audit(observation=uncertain).state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads,store.commits,phys.claims)==(before[0]+1,before[1],before[2])

@pytest.mark.parametrize('cas_state', ['UNKNOWN', 'COMMITTED', 1, None])
def test_malformed_regrade_cas_state_unknown_lifecycle_not_positive(monkeypatch,cas_state):
    svc,plan,phys,store,issuer,backend,old=setup_regrade(monkeypatch)
    res=svc.execute_regrade(plan=plan)
    assert res.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    rec=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(res.cas.transaction), store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    audit=ProductionPaperLifecycle(cas=svc._cas,permission_source=Permissions(),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,audit_recovery=rec)
    hostile=replace(res,state=PaperLifecycleState.UNKNOWN,cas=replace(res.cas,state=cas_state,receipt=None))
    before=(store.reads,store.commits,phys.claims)
    decision=audit.reconcile_audit(observation=hostile)
    assert decision.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(repr(cas_state),decision.state)
    assert (store.reads,store.commits,phys.claims)==before,('forbidden read',cas_state)

@pytest.mark.parametrize(('field', 'invalid'), [
    ('state', 'UNKNOWN'), ('academic_binding_verified', 'yes'),
])
def test_c4_rejects_malformed_cas_before_invoking_independent_reconciler(
        field, invalid, monkeypatch):
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    original_source = FixedPaperOriginal(actual.cas.transaction)
    recovery = ProductionPaperCASDurableRecovery(
        original_source=original_source, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    audit = ProductionPaperLifecycle(
        cas=svc._cas, permission_source=issuer, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10, audit_recovery=recovery)
    uncertain = replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    corrupted = replace(actual, state=PaperLifecycleState.UNKNOWN,
                        cas=replace(uncertain, **{field: invalid}))
    calls = []
    original_method = ProductionPaperCASDurableRecovery.reconcile

    def counted(self, *, outcome, disjoint_from=None):
        calls.append((outcome, disjoint_from))
        return original_method(self, outcome=outcome, disjoint_from=disjoint_from)

    monkeypatch.setattr(ProductionPaperCASDurableRecovery, 'reconcile', counted)
    before = (store.reads, store.commits, physical.claims)
    assert audit.reconcile_audit(observation=corrupted).state is PaperLifecycleAuditState.UNKNOWN
    assert calls == [], 'Recovery must reject before selecting even a safe recovery adapter'
    assert (store.reads, store.commits, physical.claims) == before
