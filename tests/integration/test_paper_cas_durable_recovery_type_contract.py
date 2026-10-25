"""Original-CAS source admission rejects malformed nested facts."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import PaperLifecycleState, PaperLifecycleAuditState, ProductionPaperLifecycle
from grading.integration.whole_paper_cas import PaperCASState, ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_pre_effect import POLICY, setup_lifecycle
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('invalid', ['UNKNOWN', 'COMMITTED', 'BLOCKED', 'NOT_ELIGIBLE', object()])
def test_c4_audit_malformed_cas_state_cannot_report_committed_or_read(invalid):
    svc,plan,physical,store,issuer=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert actual.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    consumer=ProductionPaperLifecycle(cas=svc._cas, permission_source=issuer, legal_policy=POLICY,
       max_identifier_characters=128,max_questions=10,
       audit_recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),
           store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10))
    corrupt=replace(actual, state=PaperLifecycleState.UNKNOWN, cas=replace(actual.cas, state=invalid, receipt=None))
    before=(store.reads, store.commits, physical.claims)
    result=consumer.reconcile_audit(observation=corrupt)
    assert result.state is PaperLifecycleAuditState.UNKNOWN,(invalid,result.state)
    assert (store.reads,store.commits,physical.claims)==before, (invalid,'unexpected side effect')

def test_c4_audit_legitimate_unknown_cas_recovery_works():
    svc,plan,physical,store,issuer=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert actual.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    consumer=ProductionPaperLifecycle(cas=svc._cas, permission_source=issuer, legal_policy=POLICY,
       max_identifier_characters=128,max_questions=10,
       audit_recovery=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),
           store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10))
    uncertain=replace(actual, state=PaperLifecycleState.UNKNOWN, cas=replace(actual.cas, state=PaperCASState.UNKNOWN,receipt=None))
    before=(store.reads,store.commits,physical.claims)
    result=consumer.reconcile_audit(observation=uncertain)
    assert result.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads,store.commits,physical.claims)==(before[0]+1,before[1],before[2])

@pytest.mark.parametrize('invalid',['UNKNOWN','COMMITTED','BLOCKED','NOT_ELIGIBLE'])
def test_fixed_original_cas_recovery_rejects_untyped_state_before_backend(invalid):
    svc,plan,physical,store,issuer=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert actual.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    invalid_outcome=replace(actual.cas,state=invalid,receipt=None)
    before=(store.reads,store.commits,physical.claims)
    result=durable.reconcile(outcome=invalid_outcome)
    assert result is PaperCASState.UNKNOWN,(invalid,result)
    assert (store.reads,store.commits,physical.claims)==before


@pytest.mark.parametrize('invalid', [None, 1, 'yes', object()])
def test_fixed_original_cas_recovery_rejects_nonboolean_academic_binding_before_backend(invalid):
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(actual.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    malformed = replace(actual.cas, state=PaperCASState.UNKNOWN,
                        academic_binding_verified=invalid, receipt=None)
    before = (store.reads, store.commits, physical.claims)
    assert durable.reconcile(outcome=malformed) is PaperCASState.UNKNOWN
    assert (store.reads, store.commits, physical.claims) == before


@pytest.mark.parametrize('flag', [False, True])
def test_fixed_original_cas_recovery_preserves_typed_unknown_academic_binding(flag):
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(actual.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    uncertain = replace(actual.cas, state=PaperCASState.UNKNOWN,
                        academic_binding_verified=flag, receipt=None)
    before = (store.reads, store.commits, physical.claims)
    assert durable.reconcile(outcome=uncertain) is PaperCASState.COMMITTED
    assert (store.reads, store.commits, physical.claims) == (before[0]+1, before[1], before[2])


@pytest.mark.parametrize(('field', 'malformed'), [
    ('state', 'COMMITTED'), ('state', 1),
    ('academic_binding_verified', 'yes'), ('academic_binding_verified', 1),
])
def test_issued_same_process_paper_cas_recovery_rejects_corrupted_nested_evidence(field, malformed):
    svc, plan, physical, store, issuer = setup_lifecycle()
    issued = svc.execute_first(plan=plan)
    assert issued.cas.state is PaperCASState.COMMITTED
    assert id(issued.cas) in svc._cas._issued
    # The exact internally issued object, not a caller-fabricated clone.
    # Frozen dataclass typing is not a runtime integrity check.
    object.__setattr__(issued.cas, field, malformed)
    before = (store.reads, store.commits, physical.claims)
    assert svc._cas.reconcile(outcome=issued.cas) is PaperCASState.UNKNOWN
    assert (store.reads, store.commits, physical.claims) == before


def test_issued_same_process_paper_cas_recovery_valid_control():
    svc, plan, physical, store, issuer = setup_lifecycle()
    issued = svc.execute_first(plan=plan)
    before = (store.reads, store.commits, physical.claims)
    assert svc._cas.reconcile(outcome=issued.cas) is PaperCASState.COMMITTED
    assert (store.reads, store.commits, physical.claims) == (before[0]+1, before[1], before[2])
