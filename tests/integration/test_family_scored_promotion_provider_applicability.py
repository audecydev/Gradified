"""Connected family physical attempt claim/CAS/paper lifecycle -> governed scored-paper handoff; applicability is a test-source fact, not an approval.

The conditional physical attempt claim/CAS fixtures are simulated and do not certify a real backend.
"""
from dataclasses import replace

from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.scored_paper_promotion import ProductionPaperPromotion, PaperHandoffEligibilityState
from grading.integration.paper_accounting import (
    ProductionPaperAccounting, PaperProviderApplicability,
)
from grading.integration.paper_provider_inventory import (
    OriginalProviderInventory, PhysicalAttemptObservation, ProviderApplicabilityFact,
    ProductionProviderInventory, QuestionTransportDisposition,
)
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_original_recovery_complete_paper_gate import _gate


class OriginalAccountingApplicability:
    def __init__(self, value):
        self.value = value

    def resolve_original_provider_applicability(self):
        return self.value


class OriginalInventory:
    def __init__(self, inventory):
        self.inventory = inventory
        self.reads = 0

    def resolve_original_provider_inventory(self):
        self.reads += 1
        return self.inventory


class OriginalApplicability:
    def __init__(self, value):
        self.value = value
        self.reads = 0

    def resolve_provider_applicability(self):
        self.reads += 1
        return self.value


def connected_handoff(kind='NUMERIC'):
    cas, plan, permission, physical, backend, f25, provider, store, atomic = connected(kind)
    lifecycle = ProductionPaperLifecycle(
        cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    history = lifecycle.execute_first(plan=plan)
    assert history.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    simple, original, _ = _gate(history, store)
    custody = history.cas.custody
    inventory = OriginalProviderInventory(
        custody.plan, custody.outcome.issued_paper,
        tuple(PhysicalAttemptObservation(
            q.question_id, q.f25_call_started, q.original_f25_request,
            q.reservation) for q in custody.questions),
        'ORIGINAL-FAMILY-INVENTORY', (), (), True)
    source = OriginalInventory(inventory)
    facts = OriginalApplicability(ProviderApplicabilityFact(
        inventory.inventory_ref, custody.plan, 'EXPLICIT-TEST-POLICY', 1,
        tuple((q.request.question_id, QuestionTransportDisposition.APPROVED_NO_TRANSPORT)
              for q in custody.plan.questions)))
    provider_accounting = ProductionProviderInventory(
        original_source=source, applicability_source=facts,
        max_identifier_characters=128, max_questions=10)
    accounting = ProductionPaperAccounting(
        operations=(), max_identifier_characters=128,
        applicability_source=OriginalAccountingApplicability(
            PaperProviderApplicability(custody.plan.request,
                custody.plan.approval_revision, ())))
    gate = ProductionPaperPromotion(
        original_source=original, audit_recovery=simple._audit,
        accounting=accounting, physical_accounting=provider_accounting,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    return gate, source, facts, custody, store, physical


def test_numeric_first_c5_uses_explicit_fixture_no_transport_policy_without_publishing():
    gate, source, facts, custody, store, physical = connected_handoff()
    before = (physical.claims, store.commits, store.reads)
    outcome = gate.assess()
    assert outcome.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert outcome.authorizes_retry is False and outcome.authorizes_publication is False
    assert source.reads == facts.reads == 1
    assert (physical.claims, store.commits) == before[:2]
    assert store.reads == before[2] + 1


def test_numeric_first_c5_missing_transport_policy_remains_unknown():
    gate, source, facts, custody, store, physical = connected_handoff()
    gate_without_policy = ProductionPaperPromotion(
        original_source=gate._original.__self__, audit_recovery=gate._audit,
        accounting=gate._accounting,
        physical_accounting=ProductionProviderInventory(
            original_source=source,max_identifier_characters=128,max_questions=10),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    assert gate_without_policy.assess().state is PaperHandoffEligibilityState.UNKNOWN
    assert physical.claims == 1 and store.commits == 1


def test_numeric_first_c5_wrong_paper_applicability_never_promotes():
    gate, source, facts, custody, store, physical = connected_handoff()
    facts.value = replace(facts.value, plan=replace(custody.plan, approval_revision='FOREIGN'))
    assert gate.assess().state in (PaperHandoffEligibilityState.CONFLICT, PaperHandoffEligibilityState.UNKNOWN)
    assert physical.claims == 1 and store.commits == 1


def test_direct_first_empty_inventory_does_not_suggest_provider_never_called():
    gate, source, facts, custody, store, physical = connected_handoff('DIRECT')
    # The DIRECT fixture did invoke a semantic provider. Our fabricated
    # transport-free facts are not trustworthy provenance and MUST NOT be
    # interpreted as an actual conformance test. We deliberately do not run
    # this scenario as a claimed positive release acceptance.
    source.inventory = replace(source.inventory, complete_operation_inventory=False)
    assert gate.assess().state is PaperHandoffEligibilityState.UNKNOWN
    assert physical.claims == 1 and store.commits == 1
