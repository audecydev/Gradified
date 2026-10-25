"""whole-paper score commit durable previous-generation admission must retain original paper scope."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery, PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

PAPER_SCOPE = ('tenant_ref', 'session_ref', 'submission_ref', 'exam_ref', 'paper_ref', 'set_ref')


def fixture():
    service, plan, physical, store, issuer = setup_lifecycle()
    actual = service.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    reader = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(actual.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    observation = replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    return actual.cas.transaction, reader, observation, store


def prior_for(current, changed_field=None):
    req = current.intent.plan.request
    replace_attrs = {'grading_run_id':'PREVIOUS-GRADING-RUN'}
    if changed_field is not None:
        replace_attrs[changed_field] = f'FOREIGN-{changed_field.upper()}'
    oldreq = replace(req, **replace_attrs)
    prior_intent = replace(current.intent,
        plan=replace(current.intent.plan, request=oldreq,
            questions=tuple(replace(q,request=replace(q.request,
                grading_run_id=oldreq.grading_run_id)) for q in current.intent.plan.questions)),
        issued=replace(current.intent.issued, request=oldreq),
        question_claims=tuple((qid, 'OLD-'+r, 'OLD-'+a, 'OLD-'+res)
                              for qid,r,a,res in current.intent.question_claims),
        original_claim_requests=tuple(replace(o,request_ref='OLD-'+o.request_ref,
            scope=replace(o.scope,grading_run_id=oldreq.grading_run_id,
                tenant_ref=oldreq.tenant_ref)) for o in current.intent.original_claim_requests),
        result=replace(current.intent.result,context=replace(current.intent.result.context,
            grading_run_id=oldreq.grading_run_id)))
    return replace(current, intent=prior_intent,
                   request_ref='OLD-CAS-REQ', event_ref='OLD-CAS-EVENT', result_ref='OLD-CAS-RESULT')


@pytest.mark.parametrize('changed_field', PAPER_SCOPE)
def test_foreign_predecessor_scope_rejected_before_backend(changed_field):
    current, reader, observation, store = fixture()
    previous = prior_for(current, changed_field)
    before = store.reads
    status = reader.reconcile(outcome=observation, disjoint_from=previous)
    assert status is PaperCASState.BLOCKED, (changed_field, status)
    assert store.reads == before, 'No backend read for known incompatible prior paper scope'


def test_genuine_distinct_same_paper_scope_recovers():
    current, reader, observation, store = fixture()
    previous = prior_for(current)
    before = store.reads
    assert reader.reconcile(outcome=observation, disjoint_from=previous) is PaperCASState.COMMITTED
    assert store.reads == before + 1
