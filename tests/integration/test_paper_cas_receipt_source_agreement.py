"""Independent CAS receipt cross-source consistency regression.

A locally valid receipt and a genuine recovered backend receipt for the same
transaction must not claim two different commit/revision identities.
"""
from dataclasses import replace

import pytest

from grading.integration.whole_paper_cas import PaperCASState, ProductionPaperCASDurableRecovery
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


@pytest.mark.parametrize('field', ['commit_ref', 'committed_ledger_revision'])
def test_same_process_local_receipt_must_agree_with_fixed_backend_receipt(field):
    service, plan, _, store, _ = setup_lifecycle()
    issued = service.execute_first(plan=plan)
    original_receipt = issued.cas.receipt
    distinct = ('DIFFERENT-COMMIT' if field == 'commit_ref' else 'DIFFERENT-ADVANCED-REVISION')
    object.__setattr__(issued.cas, 'receipt', replace(original_receipt, **{field: distinct}))
    assert service._cas.reconcile(outcome=issued.cas) is not PaperCASState.COMMITTED


@pytest.mark.parametrize('field', ['commit_ref', 'committed_ledger_revision'])
def test_durable_local_receipt_must_agree_with_fixed_backend_receipt(field):
    service, plan, _, store, _ = setup_lifecycle()
    issued = service.execute_first(plan=plan)
    original_receipt = issued.cas.receipt
    distinct = ('DIFFERENT-COMMIT' if field == 'commit_ref' else 'DIFFERENT-ADVANCED-REVISION')
    observation = replace(issued.cas, state=PaperCASState.UNKNOWN,
                          receipt=replace(original_receipt, **{field: distinct}))
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(issued.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    assert durable.reconcile(outcome=observation) is not PaperCASState.COMMITTED


def test_durable_original_matching_local_receipt_still_recovers():
    service, plan, _, store, _ = setup_lifecycle()
    issued = service.execute_first(plan=plan)
    observation = replace(issued.cas, state=PaperCASState.UNKNOWN,
                          receipt=replace(issued.cas.receipt))
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(issued.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    assert durable.reconcile(outcome=observation) is PaperCASState.COMMITTED
