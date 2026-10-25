"""Verify locally invalid receipts are rejected before avoidable source reads."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery, PaperCASState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal

@pytest.mark.parametrize('bad',('empty_commit','unadvanced_ledger','foreign_transaction'))
@pytest.mark.parametrize('consumer',('durable','same_process'))
def test_known_bad_receipt_stops_before_original_reader(bad,consumer):
    svc,plan,physical,store,issuer=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    if bad=='empty_commit': receipt=replace(actual.cas.receipt,commit_ref='')
    elif bad=='unadvanced_ledger': receipt=replace(actual.cas.receipt,committed_ledger_revision=actual.cas.transaction.expected_ledger_revision)
    else: receipt=replace(actual.cas.receipt,transaction=replace(actual.cas.transaction,request_ref='FOREIGN-REQ'))
    if consumer=='durable':
        source=FixedPaperOriginal(actual.cas.transaction)
        recoverer=ProductionPaperCASDurableRecovery(original_source=source,store=store,legal_policy=POLICY,
            max_identifier_characters=128,max_questions=10)
        outcome=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=receipt)
    else:
        source=None
        recoverer=svc._cas
        outcome=actual.cas
        object.__setattr__(outcome,'receipt',receipt)
    result=recoverer.reconcile(outcome=outcome)
    assert result is not PaperCASState.COMMITTED
    if source is not None:
        assert source.calls==0,(bad,'unnecessary fixed-original contact')

@pytest.mark.parametrize('bad',('empty_commit','unadvanced_ledger','foreign_transaction'))
def test_same_process_bad_original_receipt_stops_before_original_resolver(bad):
    from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
    from grading.integration.whole_paper_cas import ProductionWholePaperCAS
    from tests.integration.test_academic_effect_preclaim import setup_bound
    from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
    from tests.integration.test_whole_paper_cas import OriginalSource, Issuer, Store
    root,plan,_,_=setup_bound()
    custody=ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,
        request_source=KnownRequests(),max_identifier_characters=128,max_questions=10)
    original=OriginalSource()
    cas=ProductionWholePaperCAS(custody=custody,issuer=Issuer(original),original_source=original,
        store=Store(),legal_policy=POLICY,max_identifier_characters=128,max_questions=10,
        require_academic_preclaim=True)
    outcome=cas.execute_and_commit(plan=plan)
    assert outcome.state is PaperCASState.COMMITTED
    if bad=='empty_commit': receipt=replace(outcome.receipt,commit_ref='')
    elif bad=='unadvanced_ledger': receipt=replace(outcome.receipt,committed_ledger_revision=outcome.transaction.expected_ledger_revision)
    else: receipt=replace(outcome.receipt,transaction=replace(outcome.transaction,request_ref='FOREIGN-REQ'))
    object.__setattr__(outcome,'receipt',receipt)
    before=original.reads
    assert cas.reconcile(outcome=outcome) is not PaperCASState.COMMITTED
    assert original.reads==before,'same-process read was avoidable for an invalid issued receipt'
