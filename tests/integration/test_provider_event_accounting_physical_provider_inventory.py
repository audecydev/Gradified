"""physical provider inventory separate physical-call accounting, including multiple calls per question."""
from dataclasses import replace

from grading.integration.paper_provider_inventory import (
    ProductionProviderInventory, OriginalProviderInventory, PhysicalAttemptObservation,
    PhysicalProviderOperation, ProviderCompletenessFact, ProviderInventoryState,
)
from grading.providers.attempt_accounting import ProviderAttemptIdentity
from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle
from tests.integration.test_original_recovery_complete_paper_gate import FakeProviderReadStore

class FixedInventory:
    def __init__(self, value): self.value=value
    def resolve_original_provider_inventory(self): return self.value

class FixedCompleteness:
    def __init__(self, fact): self.fact=fact
    def resolve_provider_completeness(self): return self.fact


def fixture(*, provider=False, completions=False):
    service, plan, physical, audit, _=setup_lifecycle()
    observation=service.execute_first(plan=plan)
    custody=observation.cas.custody
    by_q=tuple(PhysicalAttemptObservation(q.question_id,q.f25_call_started,
        q.original_f25_request,q.reservation) for q in custody.questions)
    if provider:
        changed_question=replace(plan.questions[0], family='DIRECT')
        plan=replace(plan, questions=(changed_question, *plan.questions[1:]))
        issued=replace(custody.outcome.issued_paper,questions=(
            replace(custody.outcome.issued_paper.questions[0],family='DIRECT'),
            *custody.outcome.issued_paper.questions[1:]))
        first=by_q[0]
        by_q=(replace(first,original_request=replace(first.original_request,family='DIRECT'),
                      reservation=replace(first.reservation,family='DIRECT')),*by_q[1:])
    else:
        issued=custody.outcome.issued_paper
    ops=[]; backends=[]
    if provider:
        for i in range(2):
            identity=ProviderAttemptIdentity('OP-'+str(i),'EVENT-'+str(i),
                'LOGICAL-Q1',by_q[0].reservation.attempt_id,
                by_q[0].reservation.request_ref,'PROVIDER-X','MODEL-X','CONFIG-X','b'*64)
            back=FakeProviderReadStore()
            reader=ReadOnlyAccountingReconciler(identity=identity,store=back,
                                               max_identifier_characters=128)
            ops.append(PhysicalProviderOperation('Q1',identity,reader))
            backends.append(back)
    record=OriginalProviderInventory(plan,issued,by_q,'INV-1',
        ('Q1',) if provider else (),tuple(ops),True)
    source=FixedInventory(record)
    comp=None
    if completions:
        comp=FixedCompleteness(ProviderCompletenessFact('INV-1','POLICY-USAGE',1,
            ('OP-0','OP-1'),('actual_tokens','actual_cost'),
            ('actual_tokens','actual_cost'),True))
    consumer=ProductionProviderInventory(original_source=source,max_identifier_characters=128,
        max_questions=10,completeness_source=comp)
    return consumer,source,backends,comp


def test_choice_no_vendor_operations_never_invents_zero_usage():
    svc,_,backs,_=fixture()
    assert svc.reconcile().state is ProviderInventoryState.NOT_APPLICABLE
    assert backs==[]


def test_multiple_real_reported_operations_one_question_are_not_collapsed():
    svc,_,backs,_=fixture(provider=True)
    assert svc.reconcile().state is ProviderInventoryState.EVENTS_RECORDED
    assert [b.reads for b in backs]==[1,1]


def test_measurement_completeness_requires_separate_versioned_provider_evidence():
    svc,_,backs,source=fixture(provider=True,completions=True)
    assert svc.reconcile().state is ProviderInventoryState.COMPLETENESS_REPORTED
    assert [b.reads for b in backs]==[1,1]
    source.fact=replace(source.fact, present_measurements=('actual_tokens',))
    assert svc.reconcile().state is ProviderInventoryState.UNKNOWN


def test_missing_provider_event_not_counted_as_zero_or_complete():
    svc,_,backs,_=fixture(provider=True)
    backs[1].mode='NOT_FOUND'
    assert svc.reconcile().state is ProviderInventoryState.UNKNOWN


def test_foreign_provider_attempt_denies_all_provider_reads():
    svc,source,backs,_=fixture(provider=True)
    first=source.value.operations[0]
    alien=replace(first.identity,attempt_id='OTHER-PHYSICAL-ATTEMPT')
    source.value=replace(source.value,operations=(replace(first,identity=alien),
        *source.value.operations[1:]))
    assert svc.reconcile().state is ProviderInventoryState.CONFLICT
    assert [b.reads for b in backs]==[0,0]


def test_duplicate_operation_id_denies_before_any_read():
    svc,source,backs,_=fixture(provider=True)
    first,second=source.value.operations
    source.value=replace(source.value, operations=(first,replace(second,
        identity=replace(second.identity,operation_ref=first.identity.operation_ref))))
    assert svc.reconcile().state is ProviderInventoryState.CONFLICT
    assert [b.reads for b in backs]==[0,0]


def test_unqualified_incomplete_transport_inventory_is_unknown_not_zero():
    svc,source,backs,_=fixture(provider=True)
    source.value=replace(source.value,complete_operation_inventory=False)
    assert svc.reconcile().state is ProviderInventoryState.UNKNOWN
    assert [b.reads for b in backs]==[0,0]
