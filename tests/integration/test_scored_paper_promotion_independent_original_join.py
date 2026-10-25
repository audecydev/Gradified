"""External independent governed scored-paper handoff physical/logical identity mismatch reproduction."""
from dataclasses import replace
import pytest
from grading.integration.scored_paper_promotion import ProductionPaperPromotion, PaperHandoffEligibilityState
from grading.integration.paper_accounting import ProductionPaperAccounting, OriginalProviderOperation
from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff
from tests.integration.test_authorized_retry_claim import POLICY, RETRY_PURPOSE

@pytest.mark.parametrize('kind,retry', [('DIRECT',False), ('MIXED',True)])
def test_c5_denies_mismatched_original_event_between_logical_and_physical(kind,retry):
    gate, stores, source, store, physical = recorded_handoff(kind,retry)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    original_logical = gate._accounting._original[0]
    physical_id = source.value.operations[0].identity
    assert original_logical.identity == physical_id
    # Both readers are source-valid individually, refer to the same physical attempt claim and
    # operation_ref, but they make incompatible assertions about the original event.
    alternate_identity = replace(original_logical.identity, event_ref='DIFFERENT-ORIGINAL-EVENT')
    store_port = original_logical.reconciler._installation[1].__self__
    alternate_reader = ReadOnlyAccountingReconciler(identity=alternate_identity, store=store_port,
                                                     max_identifier_characters=128)
    altered = OriginalProviderOperation(original_logical.question_id,alternate_identity,alternate_reader)
    accounting = ProductionPaperAccounting(
        operations=(altered,) + gate._accounting._original[1:],
        max_identifier_characters=128,
        applicability_source=gate._accounting._applicability.__self__,
        original_intent_source=gate._accounting._origin.__self__)
    options = dict(retry_original_recovery=gate._retry_recovery,
                   retry_purpose_policy=gate._retry_purpose) if retry else {}
    mismatch_gate = ProductionPaperPromotion(
        original_source=gate._original.__self__,audit_recovery=gate._audit,
        accounting=accounting,physical_accounting=gate._physical_accounting,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,**options)
    decision=mismatch_gate.assess()
    assert decision.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, f'incompatible actual original provider events authorized: {kind}, retry={retry}'

class IndeterminatePhysicalStore:
    def reconcile_outcome(self, *, identity):
        from grading.providers.accounting_recovery import AccountingRecoveryFact, AccountingRecoveryDisposition
        from grading.providers.attempt_accounting import ProviderAccountingReceipt
        return AccountingRecoveryFact(identity,AccountingRecoveryDisposition.RECORDED,'INDETERMINATE',
                                      ProviderAccountingReceipt(identity.event_ref,identity.operation_ref,'INDETERMINATE'))

@pytest.mark.parametrize('kind,retry', [('DIRECT',False), ('MIXED',True)])
def test_c5_denies_conflicting_original_provider_outcome_status(kind,retry):
    from grading.integration.paper_provider_inventory import ProductionProviderInventory
    gate,stores,source,store,physical = recorded_handoff(kind,retry)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    first=source.value.operations[0]
    different=replace(first,recovery=ReadOnlyAccountingReconciler(identity=first.identity,
                            store=IndeterminatePhysicalStore(),max_identifier_characters=128))
    new_source=type(source)(replace(source.value, operations=(different,)+source.value.operations[1:]))
    old=gate._physical_accounting
    contradictory=ProductionProviderInventory(original_source=new_source,
        applicability_source=old._applicability.__self__,
        completeness_source=old._completeness.__self__,
        measurement_source=old._measurements.__self__,
        max_identifier_characters=128,max_questions=10)
    options=dict(retry_original_recovery=gate._retry_recovery,
                 retry_purpose_policy=gate._retry_purpose) if retry else {}
    mismatch_gate=ProductionPaperPromotion(original_source=gate._original.__self__,
        audit_recovery=gate._audit,accounting=gate._accounting,
        physical_accounting=contradictory,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,**options)
    outcome=mismatch_gate.assess()
    assert outcome.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, 'C4d says RESULT_RETURNED, C4f says INDETERMINATE'

@pytest.mark.parametrize('kind,retry', [('DIRECT',False), ('MIXED',True)])
def test_matching_original_logical_and_physical_sources_remain_eligible(kind,retry):
    gate,stores,source,store,physical=recorded_handoff(kind,retry)
    before=(physical.claims,store.commits)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims,store.commits)==before, 'Scored-paper promotion must not issue new effects'


def test_additional_physical_provider_event_for_same_question_still_allows_genuine_first():
    """Physical provider retries may exceed the one-original-per-question original attempt accounting inventory."""
    from decimal import Decimal
    from grading.integration.paper_provider_inventory import (
        PhysicalProviderOperation, OperationMeasurementFact, PhysicalProviderMeasurement,
    )
    from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
    from tests.integration.test_scored_paper_promotion_family_provider_continuity import FakeProviderReadStore
    gate, stores, source, cas_store, physical = recorded_handoff('DIRECT', False)
    original = source.value
    first = original.operations[0]
    extra_id = replace(first.identity, operation_ref='EXTRA-PHYSICAL-OP',
                       event_ref='EXTRA-PHYSICAL-EVENT')
    extra_reader = ReadOnlyAccountingReconciler(identity=extra_id,
                       store=FakeProviderReadStore(), max_identifier_characters=128)
    source.value = replace(original, operations=original.operations + (
        PhysicalProviderOperation(first.question_id, extra_id, extra_reader),))
    completeness = gate._physical_accounting._completeness.__self__
    completeness.value = replace(completeness.value,
         operation_refs=completeness.value.operation_refs + (extra_id.operation_ref,))
    measurements = gate._physical_accounting._measurements.__self__
    measurements.value = replace(measurements.value, operations=measurements.value.operations + (
        OperationMeasurementFact(extra_id.operation_ref, 'EXTRA-MEASUREMENT', (
            PhysicalProviderMeasurement('tokens', 'token', Decimal('2'), 'EXTRA-TOKENS'),
            PhysicalProviderMeasurement('cost', 'USD', Decimal('0.005'), 'EXTRA-COST'))),))
    before = (physical.claims, cas_store.commits)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims, cas_store.commits) == before


def test_c4f_preserves_detached_full_identities_and_outcome_status_for_c5():
    gate, _, source, _, _ = recorded_handoff('MIXED', True)
    physical = gate._physical_accounting.reconcile()
    assert physical.state.value == 'MEASUREMENTS_REPORTED'
    assert physical.original_operations == tuple(
        (op.question_id, op.identity, 'RESULT_RETURNED') for op in source.value.operations)
