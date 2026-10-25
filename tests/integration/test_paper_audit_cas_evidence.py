"""Independent lifecycle/CAS coherence and truthful original recovery review."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleAuditState, PaperLifecycleState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery,PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


def make():
    svc,plan,physical,store,issuer=setup_lifecycle()
    observed=svc.execute_first(plan=plan)
    assert observed.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    recovered=ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(observed.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    c4=ProductionPaperLifecycle(cas=svc._cas,permission_source=issuer,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,
        audit_recovery=recovered)
    return observed,c4,physical,store


@pytest.mark.parametrize('case', ['ack_but_cas_unknown','ack_but_academic_unverified'])
def test_impossible_acknowledgment_must_not_reconcile_or_read(case):
    observed,c4,physical,store=make()
    if case=='ack_but_cas_unknown':
        hostile=replace(observed,cas=replace(observed.cas,state=PaperCASState.UNKNOWN,receipt=None))
    else:
        hostile=replace(observed,cas=replace(observed.cas,academic_binding_verified=False))
    before=(store.reads,store.commits,physical.claims)
    status=c4.reconcile_audit(observation=hostile)
    assert status.state is not PaperLifecycleAuditState.REPORTED_COMMITTED,(case,status.state)
    assert (store.reads,store.commits,physical.claims)==before


@pytest.mark.parametrize('cas_state', [PaperCASState.UNKNOWN, PaperCASState.COMMITTED])
def test_genuine_uncertain_reply_can_recover_owned_backend_commit(cas_state):
    observed,c4,physical,store=make()
    # An unreliable local acknowledgment must not be an authority source:
    # recovered fixed-original CAS is independently committed and receipted.
    local=replace(observed,state=PaperLifecycleState.UNKNOWN,
        cas=replace(observed.cas,state=cas_state,receipt=None))
    before=(store.reads,store.commits,physical.claims)
    result=c4.reconcile_audit(observation=local)
    assert result.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert (store.reads,store.commits,physical.claims)==(
        before[0]+1,before[1],before[2])
    assert not result.authorizes_retry and not result.authorizes_publication
