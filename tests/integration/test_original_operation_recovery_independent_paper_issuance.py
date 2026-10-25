"""Independent paper lifecycle/governed scored-paper handoff boundary challenge; does not modify product source."""
from dataclasses import replace
from grading.integration.paper_accounting import PaperAccountingState, ProductionPaperAccounting
from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from tests.integration.test_original_recovery_complete_paper_gate import (
    _provider_accounting_fixture, setup_lifecycle, _gate)


def test_c4_rejects_provider_positive_on_inconsistent_original_family():
    consumer, intent, source, store = _provider_accounting_fixture()
    intent = replace(intent, issued=replace(intent.issued, questions=(
        replace(intent.issued.questions[0], family='DIRECT'), *intent.issued.questions[1:])))
    assert intent.plan.questions[0].family == 'DIRECT'
    assert intent.issued.questions[0].family == 'DIRECT'
    tampered = replace(intent, issued=replace(intent.issued, questions=(
        replace(intent.issued.questions[0], family='CHOICE'), *intent.issued.questions[1:])))
    assert consumer.reconcile(intent=tampered).state is PaperAccountingState.CONFLICT
    assert store.reads == 0


def test_c4_rejects_provider_positive_on_foreign_issued_paper():
    consumer, intent, source, store = _provider_accounting_fixture()
    intent = replace(intent, issued=replace(intent.issued, questions=(
        replace(intent.issued.questions[0], family='DIRECT'), *intent.issued.questions[1:])))
    tampered = replace(intent, issued=replace(intent.issued, approval_revision='WRONG-ACADEMIC-ISSUANCE'))
    assert consumer.reconcile(intent=tampered).state is PaperAccountingState.CONFLICT
    assert store.reads == 0


def test_c4_genuine_native_choice_is_not_applicable_without_provider_receipt():
    svc, plan, physical, store, _ = setup_lifecycle()
    observed = svc.execute_first(plan=plan)
    assert observed.cas is not None and observed.cas.transaction is not None
    native = ProductionPaperAccounting(operations=(), max_identifier_characters=128)
    assert native.reconcile(intent=observed.cas.transaction.intent).state is PaperAccountingState.NOT_APPLICABLE


def test_c5_genuine_complete_choice_requires_original_cas_read():
    svc, plan, physical, store, _ = setup_lifecycle()
    observed = svc.execute_first(plan=plan)
    gate, _, _ = _gate(observed, store)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
