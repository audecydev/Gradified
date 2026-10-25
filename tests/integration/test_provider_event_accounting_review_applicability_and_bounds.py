"""Independent-review adversarial physical provider inventory coverage, including actual backend read counts."""
from dataclasses import replace
import pytest
from grading.integration.paper_provider_inventory import (
    ProductionProviderInventory, ProviderApplicabilityFact,
    QuestionTransportDisposition as Disposition, ProviderInventoryState,
)
from tests.integration.test_provider_event_accounting_physical_provider_inventory import fixture, FixedInventory, FixedCompleteness

class FixedApplicability:
    def __init__(self, fact): self.fact=fact; self.calls=0
    def resolve_provider_applicability(self):
        self.calls+=1
        return self.fact


def make_svc(source, complete, applicability, **bounds):
    return ProductionProviderInventory(original_source=source,
        completeness_source=complete, applicability_source=applicability,
        max_identifier_characters=128, max_questions=10, **bounds)


def missing_second_direct():
    svc,source,backends,complete=fixture(provider=True,completions=True)
    old=source.value
    q=replace(old.plan.questions[1],family='DIRECT')
    plan=replace(old.plan,questions=(old.plan.questions[0],q))
    issued=replace(old.issued,questions=(old.issued.questions[0],
        replace(old.issued.questions[1],family='DIRECT')))
    second=old.f25_observations[1]
    f25=replace(second, original_request=replace(second.original_request,family='DIRECT'),
        reservation=replace(second.reservation,family='DIRECT'))
    source.value=replace(old,plan=plan,issued=issued,
        f25_observations=(old.f25_observations[0],f25))
    return source,backends,complete


def applicability(source, q2):
    fact=source.value
    return FixedApplicability(ProviderApplicabilityFact(fact.inventory_ref, fact.plan,
        'APPROVED-TRANSPORT', 1, (
            ('Q1',Disposition.PROVIDER_REQUIRED),('Q2',q2))))


def test_omitted_direct_is_unknown_without_independent_exemption_no_provider_read():
    source,backends,complete=missing_second_direct()
    assert make_svc(source,complete,None).reconcile().state is ProviderInventoryState.UNKNOWN
    assert [b.reads for b in backends]==[0,0]


def test_direct_versioned_no_transport_contradiction_rejects_before_provider_read():
    source,backends,complete=missing_second_direct()
    app=applicability(source,Disposition.APPROVED_NO_TRANSPORT)
    observed=make_svc(source,complete,app).reconcile()
    # An approved-shaped fact cannot contradict the installed DIRECT
    # evaluator's mandatory semantic provider call. No accounting read.
    assert observed.state is ProviderInventoryState.UNKNOWN
    assert app.calls==1 and [b.reads for b in backends]==[0,0]


@pytest.mark.parametrize('variant',('unresolved','foreign_ref','wrong_paper','foreign_policy_version','missing_question','duplicate_question','foreign_type'))
def test_invalid_application_denied_before_any_provider_accounting_read(variant):
    source,backends,complete=missing_second_direct()
    app=applicability(source,Disposition.APPROVED_NO_TRANSPORT)
    fact=app.fact
    if variant=='unresolved': fact=replace(fact,question_dispositions=(fact.question_dispositions[0],('Q2',Disposition.UNRESOLVED)))
    elif variant=='foreign_ref': fact=replace(fact,inventory_ref='OTHER-INVENTORY')
    elif variant=='wrong_paper': fact=replace(fact,plan=replace(fact.plan, approval_revision='UNAPPROVED'))
    elif variant=='foreign_policy_version': fact=replace(fact,policy_version=0)
    elif variant=='missing_question': fact=replace(fact,question_dispositions=(fact.question_dispositions[0],))
    elif variant=='duplicate_question': fact=replace(fact,question_dispositions=(fact.question_dispositions[0],fact.question_dispositions[0]))
    elif variant=='foreign_type': fact=replace(fact,question_dispositions=(('Q1','PROVIDER_REQUIRED'),fact.question_dispositions[1]))
    app.fact=fact
    assert make_svc(source,complete,app).reconcile().state is not ProviderInventoryState.COMPLETENESS_REPORTED
    assert [b.reads for b in backends]==[0,0]


@pytest.mark.parametrize('value',(1,'yes',(1,), object()))
def test_malformed_boolean_never_certifies_provider_completeness(value):
    svc,source,backends,complete=fixture(provider=True,completions=True)
    complete.fact=replace(complete.fact,complete=value)
    assert svc.reconcile().state is ProviderInventoryState.CONFLICT
    assert [b.reads for b in backends]==[1,1]


def test_over_limit_physical_operations_denied_before_reader_contact():
    svc,source,backends,complete=fixture(provider=True,completions=True)
    consumer=make_svc(source,complete,None,max_physical_operations=1)
    assert consumer.reconcile().state is ProviderInventoryState.CONFLICT
    assert [b.reads for b in backends]==[0,0]


def test_over_limit_measurements_never_reported_complete():
    svc,source,backends,complete=fixture(provider=True,completions=True)
    consumer=make_svc(source,complete,None,max_measurement_entries=1)
    assert consumer.reconcile().state is ProviderInventoryState.CONFLICT
    assert [b.reads for b in backends]==[1,1]


def test_direct_whole_paper_versioned_no_transport_claim_cannot_report_not_applicable():
    source,backends,complete=missing_second_direct()
    original=source.value
    source.value=replace(original, required_question_ids=(), operations=())
    app=FixedApplicability(ProviderApplicabilityFact(source.value.inventory_ref,source.value.plan,
        'APPROVED-NO-TRANSPORT', 1, (
          ('Q1',Disposition.APPROVED_NO_TRANSPORT),
          ('Q2',Disposition.APPROVED_NO_TRANSPORT))))
    # Both questions are DIRECT in this fixture; all-transport-free facts
    # would incorrectly erase known semantic-provider effects.
    assert make_svc(source,None,app).reconcile().state is ProviderInventoryState.UNKNOWN
    assert [b.reads for b in backends] == [0,0]
