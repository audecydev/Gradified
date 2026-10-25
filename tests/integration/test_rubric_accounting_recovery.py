from dataclasses import replace
import pytest

from grading.providers.rubric_accounting import (
    ReadOnlyRubricAccountingRecovery, RubricAccountingRecoveryFact,
    RubricRecoveryDisposition, RubricAccountingReceipt,
    RubricAccountingDenied, RubricAccountingIndeterminate,
)
from test_rubric_accounting import identity


class Store:
    def __init__(self, fact=None, effect=None):
        self.fact = fact
        self.effect = effect
        self.calls = 0

    def reconcile_rubric_generation(self, *, identity):
        self.calls += 1
        if self.effect:
            return self.effect(identity)
        return self.fact


def fact(status='RESULT_RETURNED'):
    value = identity()
    return RubricAccountingRecoveryFact(value, RubricRecoveryDisposition.RECORDED,
        status, 'policy-1', 'v1', RubricAccountingReceipt('event-1','operation-1','approval-1',status))


def adapter(store):
    return ReadOnlyRubricAccountingRecovery(identity=identity(), store=store,
                                           max_identifier_characters=120)


def test_exact_readonly_record_uses_original_store_and_no_provider():
    store = Store(fact())
    recovery = adapter(store)
    assert recovery.reconcile().disposition is RubricRecoveryDisposition.RECORDED
    assert store.calls == 1
    with pytest.raises(AttributeError):
        del recovery._installation


@pytest.mark.parametrize('bad', [
    replace(fact(), identity=replace(identity(), tenant_ref='tenant-B')),
    replace(fact(), receipt=replace(fact().receipt, event_ref='foreign')),
    replace(fact(), recorded_status='UNSUPPORTED'),
    replace(fact(), receipt=replace(fact().receipt, approval_ref=False)),
    replace(fact(), disposition=RubricRecoveryDisposition.NOT_FOUND),
])
def test_wrong_recovery_evidence_rejected(bad):
    with pytest.raises(RubricAccountingDenied):
        adapter(Store(bad)).reconcile()


def test_nonrecorded_exact_unknown_is_not_permission_to_retry():
    negative = RubricAccountingRecoveryFact(identity(), RubricRecoveryDisposition.UNKNOWN,
                                            None, None, None, None)
    assert adapter(Store(negative)).reconcile().disposition is RubricRecoveryDisposition.UNKNOWN


def test_mutation_then_denial_has_integrity_priority():
    def corrupt(query):
        object.__setattr__(query, 'tenant_ref', 'foreign')
        raise RubricAccountingDenied('private')
    with pytest.raises(RubricAccountingDenied) as exc:
        adapter(Store(effect=corrupt)).reconcile()
    assert exc.value.__context__ is None


def test_transport_failure_is_unknown_and_publicly_sanitized():
    def fail(query):
        raise RuntimeError('private backend')
    with pytest.raises(RubricAccountingIndeterminate) as exc:
        adapter(Store(effect=fail)).reconcile()
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_extreme_recovery_identifier_bound_rejected_at_installation():
    with pytest.raises(RubricAccountingDenied):
        ReadOnlyRubricAccountingRecovery(identity=identity(), store=Store(fact()),
                                          max_identifier_characters=1<<4096)
