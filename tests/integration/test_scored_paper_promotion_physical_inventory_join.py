"""governed scored-paper handoff only joins physical accounting from the SAME complete original paper."""
from dataclasses import replace
from grading.integration.paper_provider_inventory import (
    PhysicalAttemptObservation, OriginalProviderInventory, ProductionProviderInventory,
)
from grading.integration.scored_paper_promotion import ProductionPaperPromotion, PaperHandoffEligibilityState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import _gate

class Original:
    def __init__(self, value): self.value=value; self.mode='OK'
    def resolve_original_provider_inventory(self):
        if self.mode == 'UNAVAILABLE':
            raise RuntimeError('PRIVATE-ORIGINAL-INVENTORY-UNAVAILABLE')
        return self.value


def setup():
    svc,plan,_,audit,_=setup_lifecycle()
    history=svc.execute_first(plan=plan)
    base,original_source,_=_gate(history,audit)
    observed=history.cas.custody
    fact=OriginalProviderInventory(observed.plan,observed.outcome.issued_paper,
        tuple(PhysicalAttemptObservation(q.question_id,q.f25_call_started,
            q.original_f25_request,q.reservation) for q in observed.questions),
        'INV-ORIGINAL-NATIVE-CHOICE',(),(),True)
    source=Original(fact)
    physical=ProductionProviderInventory(original_source=source,
        max_identifier_characters=128,max_questions=10)
    gate=ProductionPaperPromotion(original_source=original_source,
        audit_recovery=base._audit,accounting=base._accounting,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,
        physical_accounting=physical)
    return gate,source,audit


def test_genuine_native_choice_inventory_joins_same_paper_without_fabricating_transport():
    gate,_,audit=setup()
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF


def test_different_original_run_cannot_satisfy_hand_off_inventory():
    gate,source,audit=setup()
    old=audit.reads
    different=replace(source.value.plan,
        request=replace(source.value.plan.request,grading_run_id='WRONG-PHYSICAL-RUN'))
    source.value=replace(source.value,plan=different)
    assert gate.assess().state is PaperHandoffEligibilityState.CONFLICT
    assert audit.reads == old+1  # original CAS was legitimately read first


def test_missing_original_provider_inventory_is_unknown_not_eligible():
    gate,source,audit=setup()
    source.mode='UNAVAILABLE'
    assert gate.assess().state is PaperHandoffEligibilityState.UNKNOWN
