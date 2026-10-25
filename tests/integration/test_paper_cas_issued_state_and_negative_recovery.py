"""Original-state continuity and unresolved negative/commit precedence.

Genuine committed recovery is preserved for exactly typed UNKNOWN. A locally
BLOCKED or NOT_ELIGIBLE assertion is not a permission to upgrade into a
positive read-only observation until the authority precedence is approved.
"""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import (
    PaperCASState, ProductionPaperCASDurableRecovery,
)
from tests.integration.test_whole_paper_cas import setup as setup_cas
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal


@pytest.mark.parametrize('state',[PaperCASState.BLOCKED, PaperCASState.NOT_ELIGIBLE])
def test_durable_negative_state_never_silently_upgrades_to_committed(state):
    service,plan,physical,store,issuer=setup_lifecycle()
    actual=service.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    original=FixedPaperOriginal(actual.cas.transaction)
    recovery=ProductionPaperCASDurableRecovery(original_source=original,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observation=replace(actual.cas,state=state,receipt=None)
    before=store.reads
    assert recovery.reconcile(outcome=observation) is PaperCASState.UNKNOWN
    assert original.calls == 0 and store.reads == before
    unknown=replace(observation,state=PaperCASState.UNKNOWN)
    assert recovery.reconcile(outcome=unknown) is PaperCASState.COMMITTED
    assert original.calls == 1 and store.reads == before+1


@pytest.mark.parametrize('change', ['state','academic','receipt','custody'])
def test_same_process_original_issued_outcome_cannot_change_before_reconciliation(change):
    cas,plan,issuer,store,physical=setup_cas()
    outcome=cas.execute_and_commit(plan=plan)
    assert outcome.state is PaperCASState.COMMITTED
    before=store.reads
    if change=='state':
        object.__setattr__(outcome,'state',PaperCASState.BLOCKED)
    elif change=='academic':
        object.__setattr__(outcome,'academic_binding_verified',True)
    elif change=='receipt':
        object.__setattr__(outcome,'receipt',None)
    else:
        original=outcome.custody
        object.__setattr__(outcome,'custody',replace(original,plan=replace(original.plan,approval_ref='DIFFERENT-APPROVAL')))
    assert cas.reconcile(outcome=outcome) is PaperCASState.UNKNOWN
    assert store.reads==before, 'Mutated originally issued record may not select backend'


def test_same_process_unmodified_original_can_still_reconcile_committed():
    cas,plan,issuer,store,physical=setup_cas()
    outcome=cas.execute_and_commit(plan=plan)
    before=store.reads
    assert cas.reconcile(outcome=outcome) is PaperCASState.COMMITTED
    assert store.reads==before+1
