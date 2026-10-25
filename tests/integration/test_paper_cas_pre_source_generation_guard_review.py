"""Verify invalid CAS generation is rejected before avoidable source reads."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery, PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


def fixture():
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    source = FixedPaperOriginal(actual.cas.transaction)
    reader = ProductionPaperCASDurableRecovery(original_source=source, store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    observation = replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    return actual.cas.transaction, observation, reader, source, store


def prior(current, *, differ_run=True, differ_f25=True, differ_cas=True, foreign=False):
    req=current.intent.plan.request
    oldreq=replace(req, grading_run_id=('PRIOR-RUN' if differ_run else req.grading_run_id),
                   tenant_ref=('FOREIGN-TENANT' if foreign else req.tenant_ref))
    claims=(tuple((q,'PRIOR-'+request,'PRIOR-'+attempt,'PRIOR-'+reservation)
                  for q,request,attempt,reservation in current.intent.question_claims)
            if differ_f25 else current.intent.question_claims)
    old_intent=replace(current.intent,
        plan=replace(current.intent.plan,request=oldreq,
            questions=tuple(replace(q,request=replace(q.request,
                grading_run_id=oldreq.grading_run_id,tenant_ref=oldreq.tenant_ref))
                for q in current.intent.plan.questions)),
        issued=replace(current.intent.issued,request=oldreq),
        question_claims=claims,
        original_claim_requests=tuple(replace(o,
            request_ref=('PRIOR-'+o.request_ref if differ_f25 else o.request_ref),
            scope=replace(o.scope,grading_run_id=oldreq.grading_run_id,
                tenant_ref=oldreq.tenant_ref)) for o in current.intent.original_claim_requests),
        result=replace(current.intent.result,context=replace(current.intent.result.context,
            grading_run_id=oldreq.grading_run_id)))
    return replace(current,intent=old_intent,
        request_ref=('PRIOR-REQ' if differ_cas else current.request_ref),
        event_ref=('PRIOR-EVENT' if differ_cas else current.event_ref),
        result_ref=('PRIOR-RESULT' if differ_cas else current.result_ref))

@pytest.mark.parametrize('collision', ['same_run','same_F25','same_CAS','foreign_scope'])
def test_known_predecessor_contradiction_never_contacts_original_source(collision):
    current,outcome,reader,source,store=fixture()
    p=prior(current, differ_run=collision!='same_run', differ_f25=collision!='same_F25',
            differ_cas=collision!='same_CAS',foreign=collision=='foreign_scope')
    before=store.reads
    result=reader.reconcile(outcome=outcome,disjoint_from=p)
    assert result is PaperCASState.BLOCKED,(collision,result)
    assert store.reads == before
    assert source.calls == 0,(collision,'avoidable original source read',source.calls)

def test_valid_previous_generations_preserve_original_source_and_backend_reads():
    current,outcome,reader,source,store=fixture()
    before=store.reads
    result=reader.reconcile(outcome=outcome,disjoint_from=prior(current))
    assert result is PaperCASState.COMMITTED
    assert source.calls == 1
    assert store.reads == before + 1

def test_no_submitted_transaction_still_permits_genuine_original_resolution():
    current,outcome,reader,source,store=fixture()
    unknown=replace(outcome,transaction=None)
    result=reader.reconcile(outcome=unknown,disjoint_from=prior(current))
    assert result is PaperCASState.COMMITTED
    assert source.calls == 1
