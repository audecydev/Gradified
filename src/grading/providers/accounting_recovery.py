"""reference qualification read-only accounting-event reconciliation.

Reconciliation never reissues an execution or returns provider bytes. Backend
issuance, the durability of a RECORDED fact, and permission to query remain
adapter-conformance obligations, not properties of these Python records.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.providers.attempt_accounting import (
    ProviderAccountingDenied, ProviderAccountingIndeterminate,
    ProviderAccountingReceipt, ProviderAttemptIdentity, _id, _identity, _raise_public,
    _capture_provider_method,
)


class AccountingRecoveryDisposition(Enum):
    RECORDED = "RECORDED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AccountingRecoveryFact:
    identity: ProviderAttemptIdentity
    disposition: AccountingRecoveryDisposition
    recorded_status: str | None
    receipt: ProviderAccountingReceipt | None


class AccountingReadOnlyStore(Protocol):
    def reconcile_outcome(self, *, identity: ProviderAttemptIdentity) -> AccountingRecoveryFact: ...


def _validate_fact(fact: object, expected: ProviderAttemptIdentity,
                   limit: int) -> AccountingRecoveryFact:
    if type(fact) is not AccountingRecoveryFact:
        raise ProviderAccountingDenied("Invalid accounting recovery response.")
    if type(fact.disposition) is not AccountingRecoveryDisposition:
        raise ProviderAccountingDenied("Invalid accounting recovery disposition.")
    if _identity(fact.identity, limit) != expected:
        raise ProviderAccountingDenied("Foreign accounting recovery identity.")
    if fact.disposition is AccountingRecoveryDisposition.RECORDED:
        if (type(fact.recorded_status) is not str
                or fact.recorded_status not in ("RESULT_RETURNED", "INDETERMINATE")):
            raise ProviderAccountingDenied("Invalid recorded accounting status.")
        receipt = fact.receipt
        if (type(receipt) is not ProviderAccountingReceipt
                or type(receipt.event_ref) is not str
                or type(receipt.operation_ref) is not str
                or type(receipt.status) is not str
                or receipt.event_ref != expected.event_ref
                or receipt.operation_ref != expected.operation_ref
                or receipt.status != fact.recorded_status):
            raise ProviderAccountingDenied("Invalid recorded accounting receipt.")
        return AccountingRecoveryFact(expected, fact.disposition,
                                      fact.recorded_status,
                                      ProviderAccountingReceipt(receipt.event_ref,
                                                                receipt.operation_ref,
                                                                receipt.status))
    if fact.recorded_status is not None or fact.receipt is not None:
        raise ProviderAccountingDenied("Nonrecorded outcome cannot carry a receipt.")
    return AccountingRecoveryFact(expected, fact.disposition, None, None)


class ReadOnlyAccountingReconciler:
    """One installed read-only store, keyed by the original operation/event.

    A NOT_FOUND fact does not authorize another physical request or event write.
    A RECORDED fact only reports what the backend attests was recorded; it cannot
    recreate the lost provider payload or turn a trial into an official grade.
    """

    __slots__ = ("_installation", "_lock", "_active")

    def __init__(self, *, identity: ProviderAttemptIdentity,
                 store: AccountingReadOnlyStore,
                 max_identifier_characters: int) -> None:
        try:
            if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
                raise ProviderAccountingDenied("Invalid accounting identity limit.")
            installed = _identity(identity, max_identifier_characters)
            operation = _capture_provider_method(store, "reconcile_outcome", ("identity",))
            object.__setattr__(self, "_installation", (installed, operation, max_identifier_characters))
            object.__setattr__(self, "_lock", Lock())
            object.__setattr__(self, "_active", False)
        except Exception:
            _raise_public(ProviderAccountingDenied("Invalid accounting recovery installation."))

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("_installation", "_lock", "_active") and hasattr(self, name):
            raise AttributeError("Installed accounting recovery configuration is fixed.")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in ("_installation", "_lock", "_active"):
            raise AttributeError("Installed accounting recovery configuration is fixed.")
        object.__delattr__(self, name)

    def reconcile(self) -> AccountingRecoveryFact:
        with self._lock:
            if self._active:
                _raise_public(ProviderAccountingDenied("Nested accounting reconciliation denied."))
            object.__setattr__(self, "_active", True)
        try:
            installed, operation, limit = self._installation
            original = _identity(installed, limit)
            query = _identity(original, limit)
            fact = None
            callback_error: Exception | None = None
            try:
                fact = operation(identity=query)
            except Exception as exc:
                callback_error = exc
            # Integrity takes precedence over the callback's reported error.
            try:
                intact = (_identity(query, limit) == original
                          and _identity(installed, limit) == original)
            except Exception:
                intact = False
            if not intact:
                _raise_public(ProviderAccountingDenied("Accounting recovery identity was altered."))
            if callback_error is not None:
                if isinstance(callback_error, ProviderAccountingDenied):
                    _raise_public(ProviderAccountingDenied("Accounting recovery definitively denied."))
                _raise_public(ProviderAccountingIndeterminate("Accounting recovery is unavailable."))
            try:
                return _validate_fact(fact, original, limit)
            except Exception:
                _raise_public(ProviderAccountingDenied("Invalid accounting recovery fact."))
        finally:
            with self._lock:
                object.__setattr__(self, "_active", False)
