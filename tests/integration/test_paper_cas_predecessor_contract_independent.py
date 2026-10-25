"""Adversarial tests for locally detectable predecessor contract violations."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery,PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle,POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal
from tests.integration.test_paper_cas_predecessor_paper_scope import prior_for

def scenario():
    svc,plan,physical,store,issuer=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    original=FixedPaperOriginal(actual.cas.transaction)
    recovery=ProductionPaperCASDurableRecovery(original_source=original,store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    outcome=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=None)
    return actual.cas.transaction,prior_for(actual.cas.transaction),recovery,outcome,store,original

@pytest.mark.parametrize('field,bad',[
    ('request_ref', None),('event_ref',''),('result_ref',1),('expected_ledger_revision',None),
    ('f57_approval_ref',''),('f57_policy_id',None),('f57_policy_version',True),
    ('source_state','QUEUED'),('target_state',None),
])
def test_malformed_predecessor_transaction_must_be_rejected_before_source(field,bad):
    current,prior,reader,outcome,store,original=scenario()
    prior=replace(prior,**{field:bad})
    before=store.reads
    got=reader.reconcile(outcome=outcome,disjoint_from=prior)
    assert got is not PaperCASState.COMMITTED, (field,bad,got)
    assert original.calls==0,(field,original.calls)
    assert store.reads==before,(field,store.reads-before)

def test_consistent_distinct_previous_operation_still_reports_commit():
    current,prior,reader,outcome,store,original=scenario()
    before=store.reads
    assert reader.reconcile(outcome=outcome,disjoint_from=prior) is PaperCASState.COMMITTED
    assert original.calls==1 and store.reads==before+1

def test_impossible_original_receipt_without_transaction_must_not_contact_source():
    current,prior,reader,outcome,store,original=scenario()
    impossible=replace(outcome,transaction=None,receipt=replace(store.receipts[0]) if hasattr(store,'receipts') else None)
    if impossible.receipt is None:
        from grading.integration.whole_paper_cas import PaperCASReceipt
        impossible=replace(outcome,transaction=None,receipt=PaperCASReceipt(current,'OLD-ACK','NEXT-LEDGER'))
    before=store.reads
    got=reader.reconcile(outcome=impossible)
    assert got is not PaperCASState.COMMITTED
    assert original.calls==0
    assert store.reads==before

@pytest.mark.parametrize('mode',['foreign-question-id','foreign-issued-paper-run','duplicate-question-ids'])
def test_previous_generation_paper_inventory_must_be_coherent(mode):
    current,prior,reader,outcome,store,original=scenario()
    if mode=='foreign-question-id':
        claims=list(prior.intent.question_claims)
        claims[0]=('FOREIGN-QUESTION',*claims[0][1:])
        prior=replace(prior,intent=replace(prior.intent,question_claims=tuple(claims)))
    elif mode=='foreign-issued-paper-run':
        issued=replace(prior.intent.issued,request=replace(prior.intent.issued.request,grading_run_id='UNRELATED-RUN'))
        prior=replace(prior,intent=replace(prior.intent,issued=issued))
    else:
        claims=list(prior.intent.question_claims)
        claims[1]=(claims[0][0],*claims[1][1:])
        prior=replace(prior,intent=replace(prior.intent,question_claims=tuple(claims)))
    before=store.reads
    got=reader.reconcile(outcome=outcome,disjoint_from=prior)
    assert got is not PaperCASState.COMMITTED,(mode,got)
    assert original.calls == 0
    assert store.reads == before

@pytest.mark.parametrize('mode', ['missing-requests','wrong-request-ref','foreign-physical-run',
                                  'malformed-result','wrong-scored-run'])
def test_prior_original_attempt_or_scored_context_contradiction_blocks_source(mode):
    current,prior,reader,outcome,store,source=scenario()
    if mode=='missing-requests':
        intent=replace(prior.intent,original_claim_requests=())
    elif mode=='wrong-request-ref':
        originals=list(prior.intent.original_claim_requests)
        originals[0]=replace(originals[0],request_ref='FOREIGN-F25-REQUEST')
        intent=replace(prior.intent,original_claim_requests=tuple(originals))
    elif mode=='foreign-physical-run':
        originals=list(prior.intent.original_claim_requests)
        originals[0]=replace(originals[0],scope=replace(originals[0].scope,grading_run_id='FOREIGN-RUN'))
        intent=replace(prior.intent,original_claim_requests=tuple(originals))
    elif mode=='malformed-result':
        intent=replace(prior.intent,result='NOT-A-SCORED-PAPER')
    else:
        intent=replace(prior.intent,result=replace(prior.intent.result,
            context=replace(prior.intent.result.context,grading_run_id='FOREIGN-RUN')))
    bad=replace(prior,intent=intent)
    before=store.reads
    assert reader.reconcile(outcome=outcome,disjoint_from=bad) is not PaperCASState.COMMITTED
    assert source.calls==0 and store.reads==before
