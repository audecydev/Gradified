"""Verify original-attempt receipt admission before durable whole-paper updates."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import (PaperCASState,PaperCASReceipt,ProductionPaperCASDurableRecovery)
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('bad', ['FAKE-RECEIPT', 1, False, object()])
def test_same_process_invalid_original_receipt_must_not_be_accepted(bad):
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    object.__setattr__(actual.cas, 'receipt',bad)
    before=store.reads
    result=svc._cas.reconcile(outcome=actual.cas)
    assert result is not PaperCASState.COMMITTED,('malformed issued original receipt became COMMITTED',bad,result)
    assert store.reads == before, 'unnecessary backend read for locally invalid original evidence'

@pytest.mark.parametrize('bad', ['FAKE-RECEIPT', 1, False, object()])
def test_durable_invalid_original_receipt_must_not_be_accepted(bad):
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    recovered=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=bad)
    source=FixedPaperOriginal(actual.cas.transaction)
    durable=ProductionPaperCASDurableRecovery(original_source=source,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    before=store.reads
    result=durable.reconcile(outcome=recovered)
    assert result is not PaperCASState.COMMITTED,('malformed local receipt became COMMITTED',bad,result)
    assert store.reads == before, 'unnecessary backend read for malformed original evidence'

def test_same_process_unmodified_original_receipt_remains_recoverable():
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert svc._cas.reconcile(outcome=actual.cas) is PaperCASState.COMMITTED

def test_durable_lost_ack_without_original_receipt_remains_recoverable():
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    recovered=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=None)
    assert durable.reconcile(outcome=recovered) is PaperCASState.COMMITTED

@pytest.mark.parametrize('how', ['empty-commit','stale-revision','wrong-transaction'])
def test_same_process_structurally_contradictory_local_receipt_must_not_be_accepted(how):
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    receipt=actual.cas.receipt
    if how=='empty-commit': bad=replace(receipt,commit_ref='')
    elif how=='stale-revision': bad=replace(receipt,committed_ledger_revision=actual.cas.transaction.expected_ledger_revision)
    else: bad=replace(receipt,transaction=replace(receipt.transaction,request_ref='FOREIGN-CAS'))
    object.__setattr__(actual.cas,'receipt',bad)
    before=store.reads
    got=svc._cas.reconcile(outcome=actual.cas)
    assert got is not PaperCASState.COMMITTED,(how,got)
    assert store.reads==before

@pytest.mark.parametrize('how', ['empty-commit','stale-revision','wrong-transaction'])
def test_durable_structurally_contradictory_local_receipt_must_not_be_accepted(how):
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    receipt=actual.cas.receipt
    if how=='empty-commit': bad=replace(receipt,commit_ref='')
    elif how=='stale-revision': bad=replace(receipt,committed_ledger_revision=actual.cas.transaction.expected_ledger_revision)
    else: bad=replace(receipt,transaction=replace(receipt.transaction,request_ref='FOREIGN-CAS'))
    recovered=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=bad)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(actual.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    before=store.reads
    got=durable.reconcile(outcome=recovered)
    assert got is not PaperCASState.COMMITTED,(how,got)
    assert store.reads==before
