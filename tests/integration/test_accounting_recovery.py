from __future__ import annotations

from dataclasses import replace

import pytest

from grading.providers.accounting_recovery import (
    AccountingRecoveryDisposition as D, AccountingRecoveryFact as F,
    ReadOnlyAccountingReconciler,
)
from grading.providers.attempt_accounting import (
    ProviderAccountingDenied, ProviderAccountingIndeterminate,
    ProviderAccountingReceipt, ProviderAttemptIdentity,
)


IDENTITY = ProviderAttemptIdentity('op', 'evt', 'eval', 'att', 'request',
                                   'provider', 'model', 'config', 'a' * 64)


class Store:
    def __init__(self, result=None, exception=None):
        self.calls = 0
        self.result = result
        self.exception = exception

    def reconcile_outcome(self, *, identity):
        self.calls += 1
        if self.exception is not None:
            raise self.exception
        return self.result or F(identity, D.RECORDED, 'RESULT_RETURNED',
                                ProviderAccountingReceipt(identity.event_ref,
                                                          identity.operation_ref, 'RESULT_RETURNED'))


def build(store):
    return ReadOnlyAccountingReconciler(identity=IDENTITY, store=store,
                                      max_identifier_characters=120)


def test_exact_recorded_fact_is_structurally_admitted_without_provider_dispatch():
    store = Store()
    result = build(store).reconcile()
    assert result.disposition is D.RECORDED
    assert result.receipt == ProviderAccountingReceipt('evt', 'op', 'RESULT_RETURNED')
    assert store.calls == 1
    assert not hasattr(result, 'raw_payload')


@pytest.mark.parametrize('disposition', [D.NOT_FOUND, D.CONFLICT, D.UNKNOWN])
def test_nonrecorded_dispositions_are_not_retry_permissions(disposition):
    store = Store(F(IDENTITY, disposition, None, None))
    result = build(store).reconcile()
    assert result.disposition is disposition and result.receipt is None
    assert store.calls == 1


@pytest.mark.parametrize('variant', [
    lambda i: F(replace(i, attempt_id='foreign'), D.RECORDED, 'RESULT_RETURNED',
                ProviderAccountingReceipt('evt','op','RESULT_RETURNED')),
    lambda i: F(i, D.RECORDED, 'RESULT_RETURNED',
                ProviderAccountingReceipt('FOREIGN','op','RESULT_RETURNED')),
    lambda i: F(i, D.RECORDED, 'RESULT_RETURNED',
                ProviderAccountingReceipt('evt','FOREIGN','RESULT_RETURNED')),
    lambda i: F(i, D.RECORDED, 'RESULT_RETURNED',
                ProviderAccountingReceipt('evt','op','INDETERMINATE')),
    lambda i: F(i, D.NOT_FOUND, 'RESULT_RETURNED', None),
    lambda i: F(i, D.UNKNOWN, None, ProviderAccountingReceipt('evt','op','RESULT_RETURNED')),
    lambda i: F(i, 'RECORDED', 'RESULT_RETURNED', ProviderAccountingReceipt('evt','op','RESULT_RETURNED')),
])
def test_foreign_or_incoherent_fact_cannot_be_admitted(variant):
    with pytest.raises(ProviderAccountingDenied):
        build(Store(variant(IDENTITY))).reconcile()


def test_recovery_foreign_equality_object_is_not_called():
    class Foreign:
        def __eq__(self, other):
            raise AssertionError('foreign equality must never execute')
    forged = ProviderAccountingReceipt('evt', object(), 'RESULT_RETURNED')
    object.__setattr__(forged, 'operation_ref', Foreign())
    with pytest.raises(ProviderAccountingDenied):
        build(Store(F(IDENTITY, D.RECORDED, 'RESULT_RETURNED', forged))).reconcile()


def test_callback_mutates_read_identity_then_raises_is_denied_with_private_context_removed():
    class Mutator(Store):
        def reconcile_outcome(self, *, identity):
            object.__setattr__(identity, 'attempt_id', 'foreign')
            raise RuntimeError('PRIVATE_STORE_SECRET')
    with pytest.raises(ProviderAccountingDenied) as e:
        build(Mutator()).reconcile()
    assert e.value.__cause__ is None and e.value.__context__ is None


def test_missing_recovery_fact_is_deny_not_positive_not_found():
    class NoneStore(Store):
        def reconcile_outcome(self, *, identity):
            return None
    with pytest.raises(ProviderAccountingDenied):
        build(NoneStore()).reconcile()


def test_technical_outage_must_not_create_retry_or_false_not_found():
    with pytest.raises(ProviderAccountingIndeterminate) as e:
        build(Store(exception=TimeoutError('PRIVATE_NETWORK'))).reconcile()
    assert e.value.__cause__ is None and e.value.__context__ is None


def test_explicit_denial_subclass_retains_denied_taxonomy():
    class Refused(ProviderAccountingDenied):
        pass
    with pytest.raises(ProviderAccountingDenied) as e:
        build(Store(exception=Refused('PRIVATE_GRANT'))).reconcile()
    assert not isinstance(e.value, ProviderAccountingIndeterminate)
    assert e.value.__context__ is None


def test_callback_attempts_reentry_cannot_change_original_record():
    class Reentrant(Store):
        def reconcile_outcome(self, *, identity):
            with pytest.raises(ProviderAccountingDenied):
                self.reader.reconcile()
            return F(identity, D.NOT_FOUND, None, None)
    store = Reentrant()
    store.reader = build(store)
    assert store.reader.reconcile().disposition is D.NOT_FOUND


def test_store_method_reconfiguration_after_install_is_not_used():
    store = Store()
    reader = build(store)
    store.reconcile_outcome = lambda **kwargs: (_ for _ in ()).throw(AssertionError('replaced'))
    assert reader.reconcile().disposition is D.RECORDED


def test_accounting_recovery_constructor_sanitizes_private_ambient_context():
    try:
        raise RuntimeError('PRIVATE_AMBIENT_ACCOUNTING')
    except RuntimeError:
        with pytest.raises(ProviderAccountingDenied) as exc:
            ReadOnlyAccountingReconciler(identity=IDENTITY,store=Store(),max_identifier_characters=0)
    assert exc.value.__context__ is None and exc.value.__cause__ is None
