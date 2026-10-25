"""Verify original-operation recovery rejects premature backend reads and foreign scope.

Synthetic adapters do not establish real provider execution."""
from dataclasses import replace
import pytest
from grading.integration.paper_accounting import PaperAccountingState
from tests.integration.test_original_recovery_complete_paper_gate import _provider_accounting_fixture

CASES = (
    'foreign_tenant','foreign_submission','foreign_session','foreign_family',
    'foreign_runtime','foreign_approval_policy','wrong_question','missing_original',
    'missing_claim','duplicate_physical','duplicate_stable_request',
    'duplicate_reservation','missing_scored_paper', 'missing_scored_question',
)

def scenario(kind):
    consumer, intent, applicability, backend = _provider_accounting_fixture()
    # The developer's synthetic DIRECT fixture originally reuses a CHOICE physical attempt claim
    # family. Normalize that *synthetic-only* fixture to test independent defects.
    originals = (replace(intent.original_claim_requests[0], family='DIRECT'),
                 *intent.original_claim_requests[1:])
    intent=replace(intent, original_claim_requests=originals)
    if kind == 'foreign_tenant':
        originals=(replace(originals[0], scope=replace(originals[0].scope, tenant_ref='T-WRONG')),*originals[1:])
    elif kind == 'foreign_submission':
        originals=(replace(originals[0], scope=replace(originals[0].scope, submission_ref='SUB-WRONG')),*originals[1:])
    elif kind == 'foreign_session':
        originals=(replace(originals[0], scope=replace(originals[0].scope, session_ref='SESSION-WRONG')),*originals[1:])
    elif kind == 'foreign_family':
        originals=(replace(originals[0], family='CHOICE'),*originals[1:])
    elif kind == 'foreign_runtime':
        originals=(replace(originals[0], runtime_id='RUNTIME-WRONG'),*originals[1:])
    elif kind == 'foreign_approval_policy':
        originals=(replace(originals[0], scope=replace(originals[0].scope, policy_revision='WRONG')), *originals[1:])
    elif kind == 'wrong_question':
        originals=(replace(originals[0], scope=replace(originals[0].scope, question_id='FOREIGN-Q')), *originals[1:])
    elif kind == 'missing_original':
        originals=originals[:1]
    elif kind == 'missing_claim':
        intent=replace(intent,question_claims=intent.question_claims[:1])
    elif kind == 'duplicate_physical':
        q1,q2=intent.question_claims
        intent=replace(intent,question_claims=(q1,(q2[0],q2[1],q1[2],q2[3])))
    elif kind == 'duplicate_stable_request':
        originals=(originals[0],replace(originals[1],request_ref=originals[0].request_ref))
        q1,q2=intent.question_claims
        intent=replace(intent,question_claims=(q1,(q2[0],q1[1],q2[2],q2[3])))
    elif kind == 'duplicate_reservation':
        q1,q2=intent.question_claims
        intent=replace(intent,question_claims=(q1,(q2[0],q2[1],q2[2],q1[3])))
    elif kind == 'missing_scored_paper':
        intent=replace(intent,result=None)
    elif kind == 'missing_scored_question':
        intent=replace(intent, result=replace(intent.result,questions=intent.result.questions[:1]))
    return consumer,replace(intent,original_claim_requests=originals),backend

@pytest.mark.parametrize('kind',CASES)
def test_inconsistent_paper_custody_must_never_read_provider_backend(kind):
    consumer,intent,backend=scenario(kind)
    observed=consumer.reconcile(intent=intent)
    assert backend.reads==0, f'{kind} read provider backend {backend.reads} time(s)'
    assert observed.state is not PaperAccountingState.REPORTED_RECORDED, f'{kind} false positive'

def test_valid_synthetic_original_provider_event_still_reconciles():
    consumer,intent,backend=scenario('valid')
    observed=consumer.reconcile(intent=intent)
    assert observed.state is PaperAccountingState.REPORTED_RECORDED
    assert backend.reads==1
