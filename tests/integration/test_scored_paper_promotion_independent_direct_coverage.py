"""governed scored-paper handoff should not promote a mixed paper whose original attempt accounting original omits its DIRECT call."""
from dataclasses import replace
from decimal import Decimal
from grading.integration.scored_paper_promotion import ProductionPaperPromotion,PaperHandoffEligibilityState
from grading.integration.paper_accounting import ProductionPaperAccounting, OriginalProviderOperation, PaperProviderApplicability
from grading.integration.paper_provider_inventory import (PhysicalProviderOperation,
    ProviderCompletenessFact, ProviderMeasurementInventory, OperationMeasurementFact,
    PhysicalProviderMeasurement, QuestionTransportDisposition)
from grading.providers.attempt_accounting import ProviderAttemptIdentity
from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff,FixedSource,FakeProviderReadStore
from tests.integration.test_authorized_retry_claim import POLICY


def test_direct_not_accounted_in_c4d_even_when_numeric_operation_is_recorded():
    gate, stores, source, cas_store, physical = recorded_handoff('MIXED',False)
    original = source.value
    plan=original.plan
    direct=original.operations[0]
    numeric_q = next(q for q in plan.questions if q.family == 'NUMERIC')
    numeric_claim = next(q for q in gate._original.__self__.original.cas.transaction.intent.question_claims
                         if q[0] == numeric_q.request.question_id)
    numeric_identity=ProviderAttemptIdentity('NUMERIC-OP','NUMERIC-EVENT','NUMERIC-LOGICAL',
        numeric_claim[2],numeric_claim[1], 'NUMERIC-PROVIDER','NUMERIC-MODEL','CONFIG', 'c'*64)
    numeric_backend=FakeProviderReadStore()
    numeric_reader=ReadOnlyAccountingReconciler(identity=numeric_identity,store=numeric_backend,
                                               max_identifier_characters=128)
    numeric_port=PhysicalProviderOperation(numeric_q.request.question_id,numeric_identity,numeric_reader)
    source.value=replace(original, required_question_ids=(direct.question_id,numeric_q.request.question_id),
                         operations=(direct,numeric_port))
    app=gate._physical_accounting._applicability.__self__
    app.value=replace(app.value,question_dispositions=tuple(
        (q.request.question_id,QuestionTransportDisposition.PROVIDER_REQUIRED)
        for q in plan.questions))
    completion=gate._physical_accounting._completeness.__self__
    completion.value=replace(completion.value, operation_refs=(direct.identity.operation_ref,numeric_identity.operation_ref))
    measured=gate._physical_accounting._measurements.__self__
    measured.value=replace(measured.value, operations=(*measured.value.operations,
       OperationMeasurementFact(numeric_identity.operation_ref,'NUMERIC-MEASUREMENT',(
           PhysicalProviderMeasurement('tokens','token',Decimal('5'),'NUMERIC-TOKEN'),
           PhysicalProviderMeasurement('cost','USD',Decimal('0.01'),'NUMERIC-COST'))),))
    intent=gate._original.__self__.original.cas.transaction.intent
    # original attempt accounting independently asserts ONLY the NUMERIC transport, silently omitting DIRECT.
    accounting=ProductionPaperAccounting(
        operations=(OriginalProviderOperation(numeric_q.request.question_id,numeric_identity,numeric_reader),),
        max_identifier_characters=128,
        applicability_source=FixedSource(PaperProviderApplicability(plan.request,plan.approval_revision,(numeric_q.request.question_id,))),
        original_intent_source=FixedSource(intent))
    assert accounting.reconcile(intent=intent).state.value=='REPORTED_RECORDED'
    assert gate._physical_accounting.reconcile().state.value=='MEASUREMENTS_REPORTED'
    gate2=ProductionPaperPromotion(original_source=gate._original.__self__,
        audit_recovery=gate._audit,accounting=accounting,
        physical_accounting=gate._physical_accounting,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10)
    outcome=gate2.assess()
    assert outcome.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, (
      'Scored-paper promotion must preserve original-operation DIRECT transport accounting')
