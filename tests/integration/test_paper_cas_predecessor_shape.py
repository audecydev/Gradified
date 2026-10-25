"""Malformed supplied generation must never select an original resolver read."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery,PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle,POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('field', ('intent','plan','request','claims','entry'))
def test_malformed_predecessor_stops_before_original_source(field):
    svc, plan, _,store,_=setup_lifecycle(); actual=svc.execute_first(plan=plan)
    current=actual.cas.transaction
    original=FixedPaperOriginal(current)
    reader=ProductionPaperCASDurableRecovery(original_source=original, store=store, legal_policy=POLICY,
                         max_identifier_characters=128,max_questions=10)
    observed=replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    if field=='intent': prior=replace(current,intent='WRONG')
    elif field=='plan': prior=replace(current,intent=replace(current.intent,plan='WRONG'))
    elif field=='request': prior=replace(current,intent=replace(current.intent,plan=replace(current.intent.plan,request='WRONG')))
    elif field=='claims': prior=replace(current,intent=replace(current.intent,question_claims='WRONG'))
    else: prior=replace(current,intent=replace(current.intent,question_claims=(('Q1','A','B','C'),('MALFORMED',))))
    before=store.reads
    status=reader.reconcile(outcome=observed, disjoint_from=prior)
    assert status is not PaperCASState.COMMITTED
    assert original.calls == 0, (field,original.calls)
    assert store.reads == before
