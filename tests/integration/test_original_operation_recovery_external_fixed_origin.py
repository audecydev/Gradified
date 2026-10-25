"""paper lifecycle positive provider observations require independently selected historical original.
These are synthetic provider-contract shape cases; no real DIRECT execution is claimed.
"""
from dataclasses import replace
from grading.integration.paper_accounting import (
    ProductionPaperAccounting, PaperAccountingState,
)
from tests.integration.test_original_recovery_complete_paper_gate import _provider_accounting_fixture

class History:
    def __init__(self, intent, fail=False):
        self.intent=intent
        self.fail=fail
        self.calls=0
    def resolve_original_paper_accounting_intent(self):
        self.calls+=1
        if self.fail:
            raise RuntimeError('PRIVATE-HISTORY-UNAVAILABLE')
        return self.intent

def build(history=None):
    old, intent, applicability, backend = _provider_accounting_fixture()
    c=ProductionPaperAccounting(operations=tuple(old._original),
        max_identifier_characters=128, applicability_source=applicability,
        original_intent_source=history)
    return c,intent,backend

def test_missing_original_source_returns_unknown_without_provider_read():
    c, i, backend = build()
    assert c.reconcile(intent=i).state is PaperAccountingState.UNKNOWN
    assert backend.reads == 0

def test_unavailable_original_source_returns_unknown_without_provider_read():
    _, i, _, _ = _provider_accounting_fixture()
    h=History(i, fail=True)
    c,i,backend=build(h)
    assert c.reconcile(intent=i).state is PaperAccountingState.UNKNOWN
    assert backend.reads == 0 and h.calls == 1

def test_independent_original_source_detects_changed_runtime_before_read():
    _, i, _, _ = _provider_accounting_fixture()
    h=History(i)
    c,intent,backend=build(h)
    wrong=replace(intent, original_claim_requests=(
        replace(intent.original_claim_requests[0],runtime_id='WRONG-RUNTIME'),
        *intent.original_claim_requests[1:]))
    assert c.reconcile(intent=wrong).state is PaperAccountingState.CONFLICT
    assert backend.reads == 0 and h.calls == 1

def test_independent_original_source_detects_changed_policy_before_read():
    _, i, _, _ = _provider_accounting_fixture()
    h=History(i)
    c,intent,backend=build(h)
    wrong=replace(intent, original_claim_requests=(
        replace(intent.original_claim_requests[0],scope=replace(intent.original_claim_requests[0].scope,policy_revision='WRONG-POLICY')),
        *intent.original_claim_requests[1:]))
    assert c.reconcile(intent=wrong).state is PaperAccountingState.CONFLICT
    assert backend.reads == 0 and h.calls == 1

def test_detached_but_same_original_value_is_admitted():
    _, i, _, _ = _provider_accounting_fixture()
    h=History(replace(i))
    c,intent,backend=build(h)
    assert c.reconcile(intent=intent).state is PaperAccountingState.REPORTED_RECORDED
    assert backend.reads == 1 and h.calls == 1

def test_malformed_historical_source_must_not_override_paper_scope():
    _, correct, _, _ = _provider_accounting_fixture()
    bad = replace(correct, original_claim_requests=(
        replace(correct.original_claim_requests[0], scope=replace(
            correct.original_claim_requests[0].scope,tenant_ref='FOREIGN-TENANT')),
        *correct.original_claim_requests[1:]))
    old, _, applicability, backend = _provider_accounting_fixture()
    # Both assertions agree; they still contradict the approved *paper*.
    c = ProductionPaperAccounting(operations=tuple(old._original),
        max_identifier_characters=128, applicability_source=applicability,
        original_intent_source=History(bad))
    assert c.reconcile(intent=bad).state is PaperAccountingState.CONFLICT
    assert backend.reads == 0

def test_original_source_and_caller_agree_but_scored_context_is_foreign():
    _, correct, _, _ = _provider_accounting_fixture()
    wrong=replace(correct, result=replace(correct.result,
        context=replace(correct.result.context, grading_run_id='FOREIGN-RUN')))
    old, _, applicability, backend = _provider_accounting_fixture()
    c=ProductionPaperAccounting(operations=tuple(old._original),
        max_identifier_characters=128, applicability_source=applicability,
        original_intent_source=History(wrong))
    assert c.reconcile(intent=wrong).state is PaperAccountingState.CONFLICT
    assert backend.reads == 0
