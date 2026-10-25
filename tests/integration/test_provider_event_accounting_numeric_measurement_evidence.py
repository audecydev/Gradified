"""Bounded per-operation reported value admission; no fabricated metric semantics."""
from dataclasses import replace
from decimal import Decimal
import pytest
from grading.integration.paper_provider_inventory import (
    ProductionProviderInventory, ProviderInventoryState,
    PhysicalProviderMeasurement, OperationMeasurementFact, ProviderMeasurementInventory,
)
from tests.integration.test_provider_event_accounting_physical_provider_inventory import fixture

class MetricSource:
    def __init__(self, fact): self.fact=fact; self.calls=0
    def resolve_provider_measurements(self):
        self.calls+=1
        return self.fact


def rig():
    _,source,backends,completion=fixture(provider=True,completions=True)
    measured=ProviderMeasurementInventory('INV-1','POLICY-USAGE',1,
        tuple(OperationMeasurementFact('OP-'+str(i),'TRUSTED-PROVIDER-RECEIPT-'+str(i),
           (PhysicalProviderMeasurement('actual_tokens','tokens',Decimal('32'),'E-TOKENS-'+str(i)),
            PhysicalProviderMeasurement('actual_cost','USD',Decimal('0.08'),'E-COST-'+str(i))))
            for i in range(2)),True)
    measures=MetricSource(measured)
    svc=ProductionProviderInventory(original_source=source,
        completeness_source=completion,measurement_source=measures,
        max_identifier_characters=128,max_questions=10)
    return svc,source,backends,completion,measures


def test_real_per_operation_decimal_evidence_still_only_source_reported():
    svc,src,backs,complete,metric=rig()
    assert svc.reconcile().state is ProviderInventoryState.MEASUREMENTS_REPORTED
    assert [b.reads for b in backs]==[1,1] and metric.calls==1


@pytest.mark.parametrize('mutation',('nan','float','boolean','missing_second','foreign_operation',
                                     'duplicate_metric','foreign_policy','false_complete','missing_metric'))
def test_malformed_incomplete_or_foreign_measurement_never_positive(mutation):
    svc,src,backs,complete,metric=rig()
    fact=metric.fact
    ops=list(fact.operations)
    first=ops[0]
    fields=list(first.measurements)
    if mutation=='nan': fields[0]=replace(fields[0],value=Decimal('NaN'))
    elif mutation=='float': fields[0]=replace(fields[0],value=0.0)
    elif mutation=='boolean': fields[0]=replace(fields[0],value=True)
    elif mutation=='missing_second': ops=ops[:1]
    elif mutation=='foreign_operation': ops[0]=replace(first,operation_ref='FOREIGN')
    elif mutation=='duplicate_metric': fields[1]=replace(fields[1],metric_ref=fields[0].metric_ref)
    elif mutation=='foreign_policy': fact=replace(fact,policy_id='FOREIGN-POLICY')
    elif mutation=='false_complete': fact=replace(fact,complete=False)
    elif mutation=='missing_metric': fields=fields[:1]
    if mutation in ('nan','float','boolean','duplicate_metric','missing_metric'):
        ops[0]=replace(first,measurements=tuple(fields))
    metric.fact=replace(fact,operations=tuple(ops))
    assert svc.reconcile().state is not ProviderInventoryState.MEASUREMENTS_REPORTED


def test_measurement_inventory_resource_cap_stops_oversized_metric_entry_count():
    svc,src,backs,complete,metric=rig()
    capped=ProductionProviderInventory(original_source=src,
        completeness_source=complete,measurement_source=metric,
        max_identifier_characters=128,max_questions=10,max_measurement_entries=3)
    assert capped.reconcile().state is ProviderInventoryState.CONFLICT


def test_missing_actual_measurement_port_does_not_fabricate_numeric_completeness():
    svc,src,backs,complete,metric=rig()
    legacy=ProductionProviderInventory(original_source=src,completeness_source=complete,
        max_identifier_characters=128,max_questions=10)
    assert legacy.reconcile().state is ProviderInventoryState.COMPLETENESS_REPORTED


def test_source_reported_values_are_preserved_as_detached_per_operation_evidence():
    svc,src,backs,complete,metric=rig()
    observed=svc.reconcile()
    assert observed.state is ProviderInventoryState.MEASUREMENTS_REPORTED
    assert observed.measurement_policy == ('POLICY-USAGE',1)
    assert tuple(x.operation_ref for x in observed.measurement_evidence) == ('OP-0','OP-1')
    assert tuple(x.source_ref for x in observed.measurement_evidence) == (
        'TRUSTED-PROVIDER-RECEIPT-0','TRUSTED-PROVIDER-RECEIPT-1')
    assert observed.measurement_evidence[0].measurements[0].value == Decimal('32')
    assert observed.measurement_evidence[0].measurements[1].value == Decimal('0.08')
    assert observed.measurement_evidence[0] is not metric.fact.operations[0]
    assert observed.measurement_evidence[0].measurements[0] is not metric.fact.operations[0].measurements[0]
    object.__setattr__(metric.fact.operations[0].measurements[0],'value',Decimal('900000'))
    assert observed.measurement_evidence[0].measurements[0].value == Decimal('32')
    assert not observed.authorizes_publication and not observed.authorizes_retry


@pytest.mark.parametrize('value',(
    Decimal('1E+9999999'), Decimal('1E-9999999'), Decimal('12345678901234567890')))
def test_measurement_transport_resource_bounds_reject_extreme_decimals(value):
    svc,src,backs,complete,metric=rig()
    a,b=metric.fact.operations
    bad=replace(a, measurements=(replace(a.measurements[0],value=value), a.measurements[1]))
    metric.fact=replace(metric.fact, operations=(bad,b))
    capped=ProductionProviderInventory(original_source=src,
        completeness_source=complete,measurement_source=metric,
        max_identifier_characters=128,max_questions=10,
        max_measurement_coefficient_digits=10,
        max_measurement_absolute_exponent=20)
    result=capped.reconcile()
    assert result.state is not ProviderInventoryState.MEASUREMENTS_REPORTED
    assert result.measurement_evidence == ()


def test_invalid_measurement_resource_configuration_is_rejected():
    _,src,backs,complete,metric=rig()
    with pytest.raises(ValueError):
        ProductionProviderInventory(original_source=src,
            max_identifier_characters=128,max_questions=10,
            max_measurement_absolute_exponent=True)


def test_extreme_finite_exponent_never_becomes_reported_measured_usage():
    svc,src,backs,complete,metric=rig()
    a,b=metric.fact.operations
    bad=replace(a, measurements=(replace(a.measurements[0],
        value=Decimal('1E+9999999')),a.measurements[1]))
    metric.fact=replace(metric.fact,operations=(bad,b))
    out=svc.reconcile()
    assert out.state is not ProviderInventoryState.MEASUREMENTS_REPORTED
    assert not out.authorizes_publication
