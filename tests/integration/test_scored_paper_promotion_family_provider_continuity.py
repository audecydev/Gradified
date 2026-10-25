"""Connected governed scored-paper handoff accounting join: original family attempt, provider receipts and CAS.

These source-backed test fixtures exercise real Gradified ports, not a deployed
provider, authenticated policy issuer, monetary meaning or durable DB guarantee.
"""
from dataclasses import replace
from decimal import Decimal

import pytest

from grading.integration.scored_paper_promotion import ProductionPaperPromotion, PaperHandoffEligibilityState
from grading.integration.paper_accounting import (
    ProductionPaperAccounting, OriginalProviderOperation, PaperProviderApplicability,
)
from grading.integration.paper_provider_inventory import (
    ProductionProviderInventory, OriginalProviderInventory, PhysicalAttemptObservation,
    PhysicalProviderOperation, ProviderApplicabilityFact, QuestionTransportDisposition,
    ProviderCompletenessFact, ProviderMeasurementInventory, OperationMeasurementFact,
    PhysicalProviderMeasurement,
)
from grading.providers.attempt_accounting import ProviderAttemptIdentity
from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_original_recovery_complete_paper_gate import (
    FixedLifecycleOriginal, FixedPaperOriginal, FakeProviderReadStore,
)
from tests.integration.test_family_scored_promotion_provider_applicability import connected_handoff
from tests.integration.test_family_retry_accounting import connected_family_retry
from tests.integration.test_authorized_retry_claim import POLICY, RETRY_PURPOSE


class FixedSource:
    def __init__(self, value):
        self.value = value

    def resolve_original_paper_accounting_intent(self):
        return self.value

    def resolve_original_provider_applicability(self):
        return self.value

    def resolve_original_provider_inventory(self):
        return self.value

    def resolve_provider_applicability(self):
        return self.value

    def resolve_provider_completeness(self):
        return self.value

    def resolve_provider_measurements(self):
        return self.value


def recorded_handoff(kind='DIRECT', retry=False):
    if retry:
        grade, plan, physical, atomic, store, joint, semantic_provider = connected_family_retry(kind)
        history = grade.execute_and_commit(plan=plan)
        assert history.cas is not None and history.state.value == 'CAS_ACKNOWLEDGED'
        retry_args = {'retry_original_recovery': grade._claims._recovery,
                      'retry_purpose_policy': RETRY_PURPOSE}
    else:
        base, _, _, _, store, physical = connected_handoff(kind)
        history = base._original.__self__.original
        retry_args = {}
    custody = history.cas.custody
    intent = history.cas.transaction.intent
    plan = custody.plan
    requests = tuple(PhysicalAttemptObservation(
        q.question_id, q.f25_call_started, q.original_f25_request, q.reservation)
        for q in custody.questions)
    direct = tuple(q for q in plan.questions if q.family == 'DIRECT')
    assert direct  # all recorded fixtures exercise actual semantic execution
    operations = []
    stores = []
    for index, q in enumerate(direct):
        claim = next(c for c in intent.question_claims if c[0] == q.request.question_id)
        identity = ProviderAttemptIdentity(
            f'PHYSICAL-{index}',f'EVENT-{index}',f'LOGICAL-{index}',
            claim[2],claim[1],'TEST-PROVIDER','TEST-MODEL','TEST-CONFIG','a'*64)
        backend = FakeProviderReadStore()
        reader = ReadOnlyAccountingReconciler(
            identity=identity,store=backend,max_identifier_characters=128)
        operations.append((q.request.question_id, identity, reader))
        stores.append(backend)
    original_provider = OriginalProviderInventory(
        plan, custody.outcome.issued_paper, requests,
        'RECORDED-INVENTORY',tuple(x[0] for x in operations),
        tuple(PhysicalProviderOperation(*x) for x in operations),True)
    applicability = ProviderApplicabilityFact(
        original_provider.inventory_ref,plan,'TEST-APPROVED-APPLICABILITY',1,
        tuple((q.request.question_id,
               QuestionTransportDisposition.PROVIDER_REQUIRED if q.family == 'DIRECT'
               else QuestionTransportDisposition.APPROVED_NO_TRANSPORT)
              for q in plan.questions))
    completion = ProviderCompletenessFact(
        original_provider.inventory_ref,'TEST-METRICS',1,
        tuple(x[1].operation_ref for x in operations),
        ('tokens','cost'),('tokens','cost'),True)
    measurements = ProviderMeasurementInventory(
        original_provider.inventory_ref,'TEST-METRICS',1,
        tuple(OperationMeasurementFact(identity.operation_ref,
            f'FIXTURE-MEASURED-{index}',(
                PhysicalProviderMeasurement('tokens','token',Decimal('10'),f'TOK-{index}'),
                PhysicalProviderMeasurement('cost','USD',Decimal('0.01'),f'COST-{index}')))
            for index,(_,identity,_) in enumerate(operations)), True)
    source = FixedSource(original_provider)
    physical_consumer = ProductionProviderInventory(
        original_source=source,
        applicability_source=FixedSource(applicability),
        completeness_source=FixedSource(completion),
        measurement_source=FixedSource(measurements),
        max_identifier_characters=128,max_questions=10)
    accounting = ProductionPaperAccounting(
        operations=tuple(OriginalProviderOperation(*x) for x in operations),
        max_identifier_characters=128,
        applicability_source=FixedSource(PaperProviderApplicability(
            plan.request,plan.approval_revision,tuple(x[0] for x in operations))),
        original_intent_source=FixedSource(intent))
    recovery = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(history.cas.transaction),
        store=store,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10)
    gate = ProductionPaperPromotion(
        original_source=FixedLifecycleOriginal(history),
        audit_recovery=recovery,accounting=accounting,
        physical_accounting=physical_consumer, legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,**retry_args)
    return gate, stores, source, store, physical


@pytest.mark.parametrize('kind',('DIRECT','MIXED'))
@pytest.mark.parametrize('retry',(False,True))
def test_source_reported_direct_transport_joins_original_to_read_only_c5(kind,retry):
    gate, provider_stores, source, store, physical = recorded_handoff(kind,retry)
    original = (physical.claims,store.commits)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert [x.reads for x in provider_stores] == [2]*len(provider_stores)
    assert (physical.claims,store.commits) == original
    assert not gate.assess().authorizes_publication
    assert not gate.assess().authorizes_retry


@pytest.mark.parametrize('mode',('NOT_FOUND','CONFLICT','THROW'))
def test_missing_late_or_conflicting_original_provider_receipt_never_promotes(mode):
    gate, provider_stores, source, store, physical = recorded_handoff()
    provider_stores[0].mode = mode
    original = (physical.claims,store.commits)
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims,store.commits) == original


def test_provider_inventory_original_replaced_with_empty_while_accounting_remains_recorded():
    gate, stores, source, store, physical = recorded_handoff()
    source.value = replace(source.value,operations=(),required_question_ids=())
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims,store.commits) == (1,1)


def test_direct_handoff_without_independent_versioned_transport_applicability_is_unknown():
    gate, stores, source, store, physical = recorded_handoff()
    from grading.integration.paper_provider_inventory import ProductionProviderInventory
    # Physical operations and their measurement facts are present, but no
    # independently issued whole-paper applicability record is installed.
    old = gate._physical_accounting
    unqualified = ProductionProviderInventory(
        original_source=old._source.__self__,
        completeness_source=old._completeness.__self__,
        measurement_source=old._measurements.__self__,
        max_identifier_characters=128,max_questions=10)
    gate2 = ProductionPaperPromotion(
        original_source=gate._original.__self__, audit_recovery=gate._audit,
        accounting=gate._accounting,physical_accounting=unqualified,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    assert gate2.assess().state is PaperHandoffEligibilityState.UNKNOWN


def test_missing_source_reported_metric_inventory_stays_unknown():
    gate, stores, source, store, physical = recorded_handoff()
    gate._physical_accounting._measurements.__self__.value = replace(
        gate._physical_accounting._measurements.__self__.value, complete=False)
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims, store.commits) == (1, 1)
