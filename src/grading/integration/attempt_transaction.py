"""Typed Gradified legal operation transition/result/state/audit compare-and-set transaction seam.

Only a real installed transactional backend can establish atomicity/durability.
The engine cannot promote a locally matching receipt to publication authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import (
    AttemptAuditEvent, AuditCommitReceipt, AttemptLineageDenied, AttemptLineageUnavailable,
    _snapshot_owned,
)
from grading.integration.evaluator_invocation import OneQuestionExecutionCandidate, _reservation_copy
from grading.integration.execution_eligibility import _capture, _id, _scope, _strip
from grading.integration.attempt_history import _private_constructor


class TransactionDisposition(str, Enum):
    COMMITTED = 'COMMITTED'
    STALE_REVISION = 'STALE_REVISION'
    CONFLICT = 'CONFLICT'
    INDETERMINATE = 'INDETERMINATE'


class TransactionReconciliation(str, Enum):
    COMMITTED = 'COMMITTED'
    NOT_COMMITTED = 'NOT_COMMITTED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


class TransactionDenied(AttemptLineageDenied):
    """Authoritative source revision or transaction identity was rejected."""


class TransactionUnavailable(AttemptLineageUnavailable):
    """Committed outcome unknown; must not blindly retry a write."""


@dataclass(frozen=True, slots=True, repr=False)
class ResultStateAuditCAS:
    """Exact request store MUST apply atomically against durable source revision.

    This is a copy of primitive references, not the original mutable callback
    event, and not an authenticated capability by itself.
    """
    event_ref: str
    result_ref: str
    attempt_id: str
    reservation_ref: str
    scope: object
    expected_ledger_revision: str
    f57_approval_ref: str
    f57_policy_id: str
    f57_policy_version: int
    source_state: GradingJobState
    target_state: GradingJobState
    event_kind: str
    request_ref: str
    predecessor_result_ref: str | None = None
    regrade_approval_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class CASDecision:
    transaction: ResultStateAuditCAS
    disposition: TransactionDisposition
    receipt: AuditCommitReceipt | None


@dataclass(frozen=True, slots=True, repr=False)
class CASRecovery:
    transaction: ResultStateAuditCAS
    disposition: TransactionReconciliation
    receipt: AuditCommitReceipt | None


@dataclass(frozen=True, slots=True, repr=False)
class RequestCASRecovery:
    """Authoritative read-only result keyed by original backend request identity."""
    request_ref: str
    scope: object
    disposition: TransactionReconciliation
    transaction: ResultStateAuditCAS | None
    receipt: AuditCommitReceipt | None


class AuthoritativeCASStore(Protocol):
    def commit_result_state_audit(self, *, transaction: ResultStateAuditCAS,
                                  candidate: OneQuestionExecutionCandidate) -> CASDecision: ...
    def reconcile_result_state_audit(self, *, transaction: ResultStateAuditCAS) -> CASRecovery: ...
    def reconcile_request_state_audit(self, *, scope: object,
                                      request_ref: str) -> RequestCASRecovery: ...


def _cas_fields(transaction: object, limit: int) -> tuple[object, ...]:
    if type(transaction) is not ResultStateAuditCAS:
        raise TransactionDenied('Atomic transaction contract is malformed.')
    try:
        attrs = tuple(_id(object.__getattribute__(transaction, name), limit) for name in (
            'event_ref','result_ref','attempt_id','reservation_ref',
            'expected_ledger_revision','f57_approval_ref','f57_policy_id','event_kind','request_ref'))
        scope = _scope(object.__getattribute__(transaction, 'scope'), limit)
        version = object.__getattribute__(transaction, 'f57_policy_version')
        source = object.__getattribute__(transaction, 'source_state')
        target = object.__getattribute__(transaction, 'target_state')
        if type(version) is not int or version <= 0 or type(source) is not GradingJobState or type(target) is not GradingJobState:
            raise ValueError('invalid CAS version or state')
        predecessor = object.__getattribute__(transaction,'predecessor_result_ref')
        approval = object.__getattribute__(transaction,'regrade_approval_ref')
        if (predecessor is None) != (approval is None):
            raise ValueError('incomplete regrade CAS')
        if predecessor is not None:
            _id(predecessor,limit)
            _id(approval,limit)
        return (*attrs, scope, version, source, target, predecessor, approval)
    except Exception:
        raise TransactionDenied('Atomic transaction contract is malformed.') from None


def _matching_receipt(receipt: object, transaction: ResultStateAuditCAS, maximum: int) -> AuditCommitReceipt:
    if type(receipt) is not AuditCommitReceipt:
        raise TransactionDenied('Committed transaction acknowledgment is malformed.')
    try:
        # Admit both optional lineage references as exact primitives BEFORE
        # comparison: foreign equality must never decide an audit receipt.
        predecessor = receipt.predecessor_result_ref
        approval = receipt.regrade_approval_ref
        if (predecessor is None) != (approval is None):
            raise TransactionDenied('Committed receipt regrade lineage is incomplete.')
        if predecessor is not None:
            predecessor = _id(predecessor, maximum)
            approval = _id(approval, maximum)
        if (type(receipt.target_state) is not GradingJobState
                or _id(receipt.event_ref, maximum) != transaction.event_ref
                or _id(receipt.ledger_revision, maximum) != transaction.expected_ledger_revision
                or _id(receipt.attempt_id, maximum) != transaction.attempt_id
                or _id(receipt.result_ref, maximum) != transaction.result_ref
                or _id(receipt.approval_ref, maximum) != transaction.f57_approval_ref
                or _id(receipt.request_ref, maximum) != transaction.request_ref
                or predecessor != transaction.predecessor_result_ref
                or approval != transaction.regrade_approval_ref
                or receipt.target_state is not transaction.target_state):
            raise TransactionDenied('Transaction receipt does not bind its exact decision.')
        _id(receipt.transaction_ref, maximum)
        return receipt
    except Exception:
        raise TransactionDenied('Transaction receipt does not bind its exact decision.') from None


def _candidate_snapshot(candidate: object) -> tuple[object, ...]:
    try:
        if type(candidate) is not OneQuestionExecutionCandidate:
            raise ValueError('invalid candidate')
        return _snapshot_owned(candidate)
    except Exception:
        raise TransactionDenied('Owned scoring candidate changed during transaction.') from None


class AtomicResultStateAudit:
    """Adapter to attempt provenance's commit_event port. Not a database implementation.

    The backend contract must guarantee CAS + result + event in one durable
    operation and authoritative reconciliation. The positive fixtures do not.
    """
    __slots__ = ('_commit', '_reconcile', '_reconcile_request', '_maximum')

    def __setattr__(self, name, value):
        if name in self.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed transaction operation cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self.__slots__:
            raise AttributeError('Installed transaction operation cannot be deleted.')
        object.__delattr__(self, name)

    @_private_constructor
    def __init__(self, *, store: AuthoritativeCASStore, max_identifier_characters: int):
        if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
            raise ValueError('A finite identifier limit is required.')
        try:
            self._commit = _capture(store, 'commit_result_state_audit', ('transaction','candidate'))
            self._reconcile = _capture(store, 'reconcile_result_state_audit', ('transaction',))
            self._reconcile_request = _capture(store, 'reconcile_request_state_audit',
                                                ('scope','request_ref'))
        except Exception:
            raise ValueError('Atomic transaction ports are not installed.') from None
        self._maximum = max_identifier_characters

    def _request(self, event: object) -> ResultStateAuditCAS:
        if type(event) is not AttemptAuditEvent:
            raise TransactionDenied('Invalid owned attempt audit event.')
        try:
            transaction = ResultStateAuditCAS(
                event_ref=object.__getattribute__(event,'event_ref'),
                result_ref=object.__getattribute__(event,'result_ref'),
                attempt_id=object.__getattribute__(event,'attempt_id'),
                reservation_ref=object.__getattribute__(event,'reservation_ref'),
                scope=_scope(object.__getattribute__(event,'scope'),self._maximum),
                expected_ledger_revision=object.__getattribute__(event,'ledger_revision'),
                f57_approval_ref=object.__getattribute__(event,'approval_ref'),
                f57_policy_id=object.__getattribute__(event,'f57_policy_id'),
                f57_policy_version=object.__getattribute__(event,'f57_policy_version'),
                source_state=object.__getattribute__(event,'source_state'),
                target_state=object.__getattribute__(event,'target_state'),
                event_kind=object.__getattribute__(event,'event_kind'),
                request_ref=object.__getattribute__(event,'request_ref'),
                predecessor_result_ref=object.__getattribute__(event,'predecessor_result_ref'),
                regrade_approval_ref=object.__getattribute__(event,'regrade_approval_ref'),
            )
            _cas_fields(transaction, self._maximum)
            if transaction.event_kind != 'ATTEMPT_RESULT_CANDIDATE':
                raise TransactionDenied('Only audited candidate transactions are supported by this port.')
            return transaction
        except TransactionDenied:
            raise
        except Exception:
            raise TransactionDenied('Attempt event cannot form an atomic transaction.') from None

    def commit_event(self, *, event: AttemptAuditEvent,
                     candidate: OneQuestionExecutionCandidate) -> AuditCommitReceipt:
        try:
            transaction = self._request(event)
            original = _cas_fields(transaction, self._maximum)
            result_original = _candidate_snapshot(candidate)

            def require_original_identity():
                # The backend receives a detached CAS, but a callback can
                # retain the original event. Its custody is independently
                # required by this direct adapter, including on exceptions.
                if (_cas_fields(transaction, self._maximum) != original
                        or _candidate_snapshot(candidate) != result_original
                        or _cas_fields(self._request(event), self._maximum) != original):
                    raise TransactionDenied('Transaction, result or original event changed during commit.')

            try:
                reservation = _reservation_copy(candidate.reservation,
                    expected=candidate.reservation,maximum=self._maximum)
                if (transaction.scope != reservation.scope
                        or transaction.attempt_id != reservation.attempt_id
                        or transaction.reservation_ref != reservation.reservation_ref
                        or transaction.request_ref != reservation.request_ref
                        or transaction.predecessor_result_ref != reservation.predecessor_result_ref
                        or transaction.regrade_approval_ref != reservation.regrade_approval_ref):
                    raise TransactionDenied('Attempt transaction does not bind the owned reservation.')
            except Exception:
                raise TransactionDenied('Attempt transaction does not bind the owned reservation.') from None
            try:
                decision = self._commit(transaction=transaction, candidate=candidate)
            except Exception:
                require_original_identity()
                raise TransactionUnavailable('Atomic transaction outcome unknown; reconcile.') from None
            require_original_identity()
            if type(decision) is not CASDecision or _cas_fields(decision.transaction, self._maximum) != original:
                raise TransactionDenied('Store returned a foreign or invalid transaction.')
            if type(decision.disposition) is not TransactionDisposition:
                raise TransactionDenied('Store disposition malformed.')
            if decision.disposition in (TransactionDisposition.STALE_REVISION, TransactionDisposition.CONFLICT):
                if decision.receipt is not None:
                    raise TransactionDenied('Rejected CAS must not claim a committed receipt.')
                raise TransactionDenied('Transaction not authorized by current durable state.')
            if decision.disposition is TransactionDisposition.INDETERMINATE:
                raise TransactionUnavailable('Atomic transaction status unknown; reconcile.')
            return _matching_receipt(decision.receipt, transaction, self._maximum)
        except (TransactionDenied, TransactionUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc = TransactionUnavailable('Atomic transaction status unavailable; reconcile.')
            _strip(exc)
            raise exc from None

    def reconcile_event(self, *, event: AttemptAuditEvent) -> CASRecovery:
        """Read only; never resubmit the transaction or grant publication."""
        try:
            transaction = self._request(event)
            original = _cas_fields(transaction, self._maximum)

            def require_original_identity():
                if (_cas_fields(transaction, self._maximum) != original
                        or _cas_fields(self._request(event), self._maximum) != original):
                    raise TransactionDenied('Recovery transaction or original event changed.')

            try:
                recovery = self._reconcile(transaction=transaction)
            except Exception as failure:
                # A failed backend read cannot erase an observed input-integrity breach.
                require_original_identity()
                if isinstance(failure, TransactionDenied):
                    raise TransactionDenied('Transaction reconciliation was refused.') from None
                raise TransactionUnavailable('Atomic transaction reconciliation unavailable.') from None
            require_original_identity()
            if type(recovery) is not CASRecovery or _cas_fields(recovery.transaction, self._maximum) != original:
                raise TransactionDenied('Transaction reconciliation has foreign identity.')
            if type(recovery.disposition) is not TransactionReconciliation:
                raise TransactionDenied('Transaction reconciliation disposition invalid.')
            if recovery.disposition is TransactionReconciliation.COMMITTED:
                _matching_receipt(recovery.receipt, transaction, self._maximum)
            elif recovery.receipt is not None:
                raise TransactionDenied('Noncommitted transaction cannot supply a receipt.')
            return recovery
        except (TransactionDenied, TransactionUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc = TransactionDenied('Transaction reconciliation input malformed.')
            _strip(exc)
            raise exc from None

    def reconcile_owned_request(self, *, scope: object, request_ref: str) -> RequestCASRecovery:
        """No write or publication. Backend must enforce read grants and durability."""
        try:
            original_scope = _scope(scope, self._maximum)
            admitted_scope = _scope(original_scope, self._maximum)
            key = _id(request_ref, self._maximum)

            def require_original_scope():
                if (_scope(scope, self._maximum) != original_scope
                        or _scope(admitted_scope, self._maximum) != original_scope):
                    raise TransactionDenied('Request scope changed during reconciliation.')

            try:
                fact = self._reconcile_request(scope=admitted_scope, request_ref=key)
            except Exception as failure:
                require_original_scope()
                if isinstance(failure, TransactionDenied):
                    raise TransactionDenied('Request reconciliation was refused.') from None
                raise TransactionUnavailable('Request transaction reconciliation unavailable.') from None
            require_original_scope()
            if type(fact) is not RequestCASRecovery:
                raise TransactionDenied('Reconciled transaction type malformed.')
            if (_id(fact.request_ref, self._maximum) != key
                    or _scope(fact.scope, self._maximum) != original_scope
                    or type(fact.disposition) is not TransactionReconciliation):
                raise TransactionDenied('Reconciled transaction has foreign identity.')
            if fact.disposition is TransactionReconciliation.COMMITTED:
                transaction = fact.transaction
                _cas_fields(transaction, self._maximum)
                if transaction.event_kind != 'ATTEMPT_RESULT_CANDIDATE':
                    raise TransactionDenied('Recovered transaction event kind is unsupported.')
                if (transaction.request_ref != key
                        or _scope(transaction.scope, self._maximum) != original_scope):
                    raise TransactionDenied('Committed recovery has foreign transaction.')
                _matching_receipt(fact.receipt, transaction, self._maximum)
            elif fact.transaction is not None or fact.receipt is not None:
                raise TransactionDenied('Noncommitted recovery cannot carry a commit record.')
            return fact
        except (TransactionDenied, TransactionUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc = TransactionDenied('Request transaction reconciliation malformed.')
            _strip(exc)
            raise exc from None
