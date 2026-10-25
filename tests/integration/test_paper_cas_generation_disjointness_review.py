"""Verify whole-paper CAS generation separation across disjoint attempts."""
from dataclasses import replace
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery, PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


def fixture():
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    reader=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),
        store=store, legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    observed=replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    return actual,reader,observed,store


def test_original_new_same_grading_run_must_not_be_new_generation():
    actual,reader,observed,store=fixture()
    current=actual.cas.transaction
    previous_intent=replace(current.intent,
        question_claims=tuple((qid, "OLDER-"+req, "OLDER-"+attempt, "OLDER-"+res)
                              for qid,req,attempt,res in current.intent.question_claims))
    prior=replace(current,intent=previous_intent,
        request_ref='OTHER-CAS-REQUEST',event_ref='OTHER-CAS-EVENT',result_ref='OTHER-CAS-RESULT')
    assert prior.intent.plan.request.grading_run_id == current.intent.plan.request.grading_run_id
    assert not ({r[1] for r in prior.intent.question_claims} & {r[1] for r in current.intent.question_claims})
    before=store.reads
    state=reader.reconcile(outcome=observed,disjoint_from=prior)
    assert state is PaperCASState.BLOCKED, ("false new-generation claim for identical run",state)
    assert store.reads==before, 'must not contact backend for known same-run collision'


def test_distinct_cas_refs_alone_do_not_prove_distinct_physical_attempts():
    actual,reader,observed,store=fixture()
    current=actual.cas.transaction
    old_request=replace(current.intent.plan.request, grading_run_id='OLDER-RUN')
    old_intent=replace(current.intent,
        plan=replace(current.intent.plan,request=old_request),
        issued=replace(current.intent.issued,request=old_request))
    prior=replace(current,intent=old_intent,
        request_ref='OTHER-CAS-REQUEST',event_ref='OTHER-CAS-EVENT',result_ref='OTHER-CAS-RESULT')
    assert prior.intent.plan.request.grading_run_id != current.intent.plan.request.grading_run_id
    assert prior.intent.question_claims == current.intent.question_claims
    before=store.reads
    state=reader.reconcile(outcome=observed,disjoint_from=prior)
    assert state is PaperCASState.BLOCKED, ("duplicate physical predecessor accepted",state)
    assert store.reads==before


def test_genuinely_distinct_synthetic_predecessor_still_recovers_original():
    actual,reader,observed,store=fixture()
    # A structurally independent predecessor is only a local control; it does not establish real source authenticity.
    old_intent=replace(actual.cas.transaction.intent,
        plan=replace(actual.cas.transaction.intent.plan,
            request=replace(actual.cas.transaction.intent.plan.request, grading_run_id='OLDER-RUN'),
            questions=tuple(replace(q,request=replace(q.request,grading_run_id='OLDER-RUN'))
                for q in actual.cas.transaction.intent.plan.questions)),
        issued=replace(actual.cas.transaction.intent.issued,
            request=replace(actual.cas.transaction.intent.issued.request,grading_run_id='OLDER-RUN')),
        question_claims=tuple((qid, 'OLD-'+req, 'OLD-'+attempt, 'OLD-'+res) for qid,req,attempt,res in actual.cas.transaction.intent.question_claims),
        original_claim_requests=tuple(replace(o,request_ref='OLD-'+o.request_ref,
            scope=replace(o.scope,grading_run_id='OLDER-RUN'))
            for o in actual.cas.transaction.intent.original_claim_requests),
        result=replace(actual.cas.transaction.intent.result,
            context=replace(actual.cas.transaction.intent.result.context,grading_run_id='OLDER-RUN')))
    prior=replace(actual.cas.transaction,intent=old_intent,request_ref='OLD-CAS-REQUEST',event_ref='OLD-CAS-EVENT',result_ref='OLD-CAS-RESULT')
    assert prior.intent.plan.request.grading_run_id != actual.cas.transaction.intent.plan.request.grading_run_id
    assert reader.reconcile(outcome=observed,disjoint_from=prior) is PaperCASState.COMMITTED
