"""Validate CHOICE attempt lineage and acknowledged audit evidence.

This is the Gradified-owned *structural* consumer of one owned evaluator invocation call.
The installed physical attempt claim/ledger/legal operation transition/audit backend MUST provide actual authoritative,
transactional facts before use outside conformance fixtures. No local lock,
record, receipt or fixture demonstrates durable uniqueness or legal policy.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from threading import local
from enum import Enum
from typing import Protocol

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.contracts.job_state import GradingJobState, GRADING_JOB_TERMINAL_STATES
from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.evaluator_invocation import (
    AttemptReservation, AttemptReservationRejected, OneQuestionExecutionCandidate,
    ProductionChoiceEvaluatorInvoker, _reservation_copy,
    InvocationDenied, InvocationContractError, InvocationUnavailable,
)
from grading.integration.execution_eligibility import _capture, _id, _scope, _strip


class AttemptLineageDenied(ValueError):
    """Wrong identity, forbidden replay/transition, or conflicting attempt."""


class AttemptLineageUnavailable(Exception):
    """Trusted ledger, legal operation transition or audit outcome is missing or uncertain."""


class AttemptLineageContractError(ValueError):
    """Installed port returned a malformed or identity-inconsistent record."""


class AttemptDisposition(str, Enum):
    NEW = 'NEW'
    REPLAY_IDENTICAL = 'REPLAY_IDENTICAL'
    CONFLICTING_DUPLICATE = 'CONFLICTING_DUPLICATE'
    STALE_OR_LATE = 'STALE_OR_LATE'
    FOREIGN = 'FOREIGN'
    INDETERMINATE = 'INDETERMINATE'


@dataclass(frozen=True, slots=True, repr=False)
class TrustedAttemptObservation:
    """Claim returned by *installed* trusted ledger, not accepted from caller."""
    reservation: AttemptReservation
    disposition: AttemptDisposition
    current_state: GradingJobState
    ledger_revision: str
    event_ref: str
    result_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class GradingTransitionApproval:
    """Claim returned by installed versioned legal operation-transition decision authority."""
    scope: ChoiceAdmissionScope
    attempt_id: str
    source_state: GradingJobState
    target_state: GradingJobState
    policy_id: str
    policy_version: int
    approval_ref: str
    ledger_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class LegalGradingTransitionPolicy:
    """Versioned legal edges supplied by accountable policy owner at install.

    This is a validation mechanism, NOT self-issued policy approval. Fixture
    allowed edges do not authorize production transitions.
    """
    policy_id: str
    policy_version: int
    allowed_edges: tuple[tuple[GradingJobState, GradingJobState], ...]


@dataclass(frozen=True, slots=True, repr=False)
class AttemptAuditEvent:
    """Small allowlisted event envelope; no student answer/exception payload."""
    event_ref: str
    ledger_revision: str
    result_ref: str
    scope: ChoiceAdmissionScope
    attempt_id: str
    reservation_ref: str
    event_kind: str
    f57_policy_id: str
    f57_policy_version: int
    source_state: GradingJobState
    target_state: GradingJobState
    approval_ref: str
    request_ref: str | None = None
    predecessor_result_ref: str | None = None
    regrade_approval_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class AuditCommitReceipt:
    """Reported committed transaction; durability depends on actual backend."""
    event_ref: str
    ledger_revision: str
    attempt_id: str
    result_ref: str
    transaction_ref: str
    target_state: GradingJobState
    approval_ref: str
    request_ref: str | None = None
    predecessor_result_ref: str | None = None
    regrade_approval_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class AuditedOneQuestionCandidate:
    """Local owned-call correlation; neither publication nor transferable grant."""
    execution: OneQuestionExecutionCandidate
    observation: TrustedAttemptObservation
    approval: GradingTransitionApproval
    audit_receipt: AuditCommitReceipt


class AttemptLineageLedger(Protocol):
    def classify_owned_result(self, *, reservation: AttemptReservation,
                              candidate: OneQuestionExecutionCandidate) -> TrustedAttemptObservation: ...


class GradingTransitionAuthority(Protocol):
    def authorize_result_transition(
        self, *, observation: TrustedAttemptObservation,
        candidate: OneQuestionExecutionCandidate,
    ) -> GradingTransitionApproval: ...


class CommittedGradingAudit(Protocol):
    def commit_event(self, *, event: AttemptAuditEvent,
                     candidate: OneQuestionExecutionCandidate) -> AuditCommitReceipt: ...


def _snapshot_owned(value: object, *, limit: int = 12000) -> tuple[object, ...]:
    """Bounded, value-and-object-identity snapshot of trusted grading records.

    This is an in-process callback-continuity check, NOT a signature, scorer,
    issuance credential or durable transaction attestation. The evaluator invoker
    has already admitted the complete result before this snapshot is captured.
    No arbitrary __eq__, descriptor, repr, iterator or custom serializer runs.
    """
    remaining = [limit]
    active: set[int] = set()

    def visit(item: object, depth: int) -> tuple[object, ...]:
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 24:
            raise AttemptLineageContractError('Owned record exceeds snapshot budget.')
        cls = type(item)
        if cls in (str, int, bool, type(None), bytes):
            if cls in (str, bytes) and len(item) > 65536:
                raise AttemptLineageContractError('Owned scalar exceeds snapshot budget.')
            return (cls, item)
        if cls is Decimal:
            if not item.is_finite():
                raise AttemptLineageContractError('Nonfinite owned decimal.')
            return (Decimal, item.as_tuple())
        if cls is ScoringDecimal:
            value = object.__getattribute__(item, '_value')
            if type(value) is not Decimal or not value.is_finite():
                raise AttemptLineageContractError('Malformed owned scoring decimal.')
            return (ScoringDecimal, id(item), value.as_tuple())
        if isinstance(item, Enum):
            if cls.__module__.startswith('grading.'):
                return (cls, item.name)
            raise AttemptLineageContractError('Foreign enum in owned record.')
        if cls is tuple:
            if len(item) > remaining[0]:
                raise AttemptLineageContractError('Owned tuple exceeds snapshot budget.')
            return (tuple, tuple(visit(x, depth + 1) for x in item))
        if not cls.__module__.startswith('grading.') or not hasattr(cls, '__dataclass_fields__'):
            raise AttemptLineageContractError('Foreign object in owned result.')
        key = id(item)
        if key in active:
            raise AttemptLineageContractError('Cyclic owned result.')
        active.add(key)
        try:
            parts = tuple((field.name, visit(object.__getattribute__(item, field.name), depth + 1))
                          for field in fields(cls))
            return (cls, key, parts)
        finally:
            active.remove(key)

    try:
        return visit(value, 0)
    except AttemptLineageContractError:
        raise
    except Exception:
        raise AttemptLineageContractError('Owned record cannot be structurally inspected.') from None


@dataclass(frozen=True, slots=True, repr=False)
class _Installation:
    invocation: object
    inspect: object
    transition: object
    commit: object
    identifier_limit: int
    policy_id: str
    policy_version: int
    allowed_edges: frozenset[tuple[GradingJobState, GradingJobState]]
    thread_state: object
    history: object
    correlation: object
    correlation_begin: object
    correlation_finish: object


class ProductionChoiceAttemptLifecycle:
    """Owns evaluator invocation invocation then attempt provenance correlation: no caller candidate input.

    physical attempt claim MUST block duplicate physical attempts *before* evaluator dispatch;
    post-execution ledger classification cannot retroactively prevent a call.
    Audit commit MUST be implemented as an authoritative transaction by backend.
    """
    __slots__ = ('_installation',)

    def __setattr__(self, name: str, value: object) -> None:
        if name == '_installation':
            try:
                object.__getattribute__(self, '_installation')
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed attempt lifecycle is immutable.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == '_installation':
            raise AttributeError('Installed attempt lifecycle cannot be deleted.')
        object.__delattr__(self, name)

    def __init__(self, *, invoker: ProductionChoiceEvaluatorInvoker,
                 ledger: AttemptLineageLedger,
                 transitions: GradingTransitionAuthority,
                 audit: CommittedGradingAudit,
                 approved_f57_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int,
                 history: object = None, correlation: object = None) -> None:
        try:
            try:
                if (type(invoker) is not ProductionChoiceEvaluatorInvoker
                        or type(max_identifier_characters) is not int
                        or max_identifier_characters <= 0):
                    raise AttemptLineageContractError('Exact installed invoker and limits required.')
                installed = object.__getattribute__(invoker, '_installation')
                if installed is None:
                    raise AttemptLineageContractError('Invoker is not installed.')
                if type(approved_f57_policy) is not LegalGradingTransitionPolicy:
                    raise AttemptLineageContractError('Approved lifecycle authorization policy is required.')
                policy_id = _id(approved_f57_policy.policy_id, max_identifier_characters)
                version = approved_f57_policy.policy_version
                edges = approved_f57_policy.allowed_edges
                if (type(version) is not int or version <= 0
                        or type(edges) is not tuple or not edges):
                    raise AttemptLineageContractError('lifecycle authorization policy revision or transitions are invalid.')
                validated_edges = set()
                for item in edges:
                    if (type(item) is not tuple or len(item) != 2
                            or type(item[0]) is not GradingJobState
                            or type(item[1]) is not GradingJobState
                            or item[0] in GRADING_JOB_TERMINAL_STATES
                            or item in validated_edges):
                        raise AttemptLineageContractError('lifecycle authorization policy transition is invalid.')
                    validated_edges.add(item)
                invoke = _capture(invoker, 'run_one_question', ('request',))
                inspect = _capture(ledger, 'classify_owned_result', ('reservation', 'candidate'))
                transition = _capture(transitions, 'authorize_result_transition',
                                      ('observation', 'candidate'))
                commit = _capture(audit, 'commit_event', ('event', 'candidate'))
                if (history is None) != (correlation is None):
                    raise AttemptLineageContractError('History and correlation must be installed together.')
                record = (None if history is None else _capture(history, 'emit_phase', (
                    'request_ref','scope','stage','effect','attempt_id','reservation_ref',
                    'result_ref','predecessor_result_ref')))
                context = (None if correlation is None else
                           _capture(correlation, 'current_request_context', ()))
                begin = (None if correlation is None else
                         _capture(correlation, 'begin_operation', ()))
                finish = (None if correlation is None else
                          _capture(correlation, 'finish_operation', ('token',)))
                self._installation = _Installation(
                    invoke, inspect, transition, commit, max_identifier_characters,
                    policy_id, version, frozenset(validated_edges), local(),
                    record, context, begin, finish)
            except AttemptLineageContractError:
                raise
            except Exception:
                raise AttemptLineageContractError('Installed attempt lifecycle is invalid.') from None
        except AttemptLineageContractError as exc:
            _strip(exc)
            raise

    def run_choice(self, *, request: object) -> AuditedOneQuestionCandidate:
        """Never expose a private exception chain or an unverified audit claim."""
        config = self._installation
        try:
            if getattr(config.thread_state, 'busy', False):
                raise AttemptLineageDenied('Attempt lifecycle reentry is forbidden.')
            config.thread_state.busy = True
            try:
                # This occurs before paper execution integrity. Otherwise a denied new request can
                # inherit a preceding successful attempt's thread-local key.
                correlation_token = None
                if config.correlation_begin is not None:
                    correlation_token = config.correlation_begin()
                try:
                    return self._run_with_error_mapping(request=request)
                except (AttemptLineageDenied, AttemptLineageUnavailable,
                        AttemptLineageContractError) as failed:
                    if config.history is not None:
                        from grading.integration.attempt_history import AttemptStage, AttemptEffect
                        try:
                            key = config.correlation()
                            if key is not None:
                                if (type(key) is not tuple or len(key) != 4):
                                    raise ValueError('wrong context')
                                scope = _scope(key[0], config.identifier_limit)
                                reference = _id(key[1], config.identifier_limit)
                                attempt_id = None if key[2] is None else _id(key[2], config.identifier_limit)
                                reservation_ref = None if key[3] is None else _id(key[3], config.identifier_limit)
                                # Public denial/contract taxonomy is separate
                                # from possible prior physical attempt claim or audit effects.
                                # Until the backend reconciles them, the event
                                # must not claim those effects did not happen.
                                category = AttemptEffect.UNKNOWN
                                config.history(request_ref=reference, scope=scope,
                                    stage=AttemptStage.FAILURE, effect=category,
                                    attempt_id=attempt_id,reservation_ref=reservation_ref,
                                    result_ref=None, predecessor_result_ref=None)
                        except AttemptReservationRejected:
                            # An altered attempt correlation cannot be used for
                            # failure history. Preserve the original denial;
                            # reconciliation remains necessary for prior effects.
                            pass
                        except Exception as history_error:
                            from grading.integration.attempt_history import AttemptHistoryDenied
                            if isinstance(history_error, AttemptHistoryDenied):
                                raise AttemptLineageDenied(
                                    'Authoritative failure history explicitly denied.') from None
                            raise AttemptLineageUnavailable(
                                'Attempt failed and authoritative failure history is uncertain.') from None
                    raise
            finally:
                try:
                    if config.correlation_finish is not None and correlation_token is not None:
                        config.correlation_finish(token=correlation_token)
                finally:
                    config.thread_state.busy = False
        except (AttemptLineageDenied, AttemptLineageUnavailable,
                AttemptLineageContractError) as exc:
            _strip(exc)
            raise
        except AttemptReservationRejected as exc:
            # The attempt correlation-begin failure is a definitive refusal.
            # Sanitize at this outer public boundary, AFTER it was raised.
            _strip(exc)
            raise
        except AttemptReservationUnavailable:
            try:
                raise AttemptLineageUnavailable('grading-attempt lifecycle correlation uncertain.') from None
            except AttemptLineageUnavailable as clean:
                _strip(clean)
                raise

    def _run_with_error_mapping(self, *, request: object) -> AuditedOneQuestionCandidate:
        try:
            return self._run_choice(request=request)
        except (AttemptLineageDenied, AttemptLineageUnavailable,
                AttemptLineageContractError):
            raise
        except InvocationDenied:
            raise AttemptLineageDenied('Owned invocation or source was denied.') from None
        except InvocationContractError:
            raise AttemptLineageContractError('Owned invocation contract failed.') from None
        except InvocationUnavailable:
            raise AttemptLineageUnavailable('Owned invocation outcome uncertain; reconcile.') from None
        except Exception:
            raise AttemptLineageUnavailable(
                'Owned invocation or attempt lineage failed; reconcile authoritatively.') from None

    @staticmethod
    def _verify_candidate(candidate: OneQuestionExecutionCandidate,
                          reservation: AttemptReservation, original_result: object,
                          original_judgments: object, identifier_limit: int,
                          result_snapshot: tuple[object, ...]) -> None:
        """Validate complete evaluator invocation-owned result continuity across later effects."""
        try:
            if (type(candidate) is not OneQuestionExecutionCandidate
                    or object.__getattribute__(candidate, 'execution') is not original_result
                    or object.__getattribute__(candidate, 'emitted_judgments') is not original_judgments):
                raise AttemptLineageDenied('Owned candidate changed during trusted callback.')
            current = _reservation_copy(object.__getattribute__(candidate, 'reservation'),
                                        expected=reservation, maximum=identifier_limit)
            if (current.attempt_id != reservation.attempt_id
                    or current.reservation_ref != reservation.reservation_ref):
                raise AttemptLineageDenied('Owned reservation identity changed during callback.')
            current_snapshot = _snapshot_owned(original_result)
            if current_snapshot != result_snapshot:
                raise AttemptLineageDenied('Owned result changed during trusted callback.')
        except AttemptLineageDenied:
            raise
        except Exception:
            raise AttemptLineageDenied('Owned candidate was corrupted during callback.') from None

    @staticmethod
    def _verify_snapshot(value: object, expected: tuple[object, ...],
                         label: str) -> None:
        try:
            if _snapshot_owned(value) != expected:
                raise AttemptLineageDenied(f'{label} changed during trusted callback.')
        except AttemptLineageDenied:
            raise
        except Exception:
            raise AttemptLineageDenied(f'{label} was corrupted during callback.') from None

    def _run_choice(self, *, request: object) -> AuditedOneQuestionCandidate:
        config = self._installation
        candidate = config.invocation(request=request)
        if type(candidate) is not OneQuestionExecutionCandidate:
            raise AttemptLineageContractError('Owned invoker returned an invalid candidate.')
        reservation = object.__getattribute__(candidate, 'reservation')
        if type(reservation) is not AttemptReservation:
            raise AttemptLineageContractError('Owned reservation has invalid type.')
        # Scope is read only from the owned invocation. It is not a caller grant.
        original_result = object.__getattribute__(candidate, 'execution')
        original_judgments = object.__getattribute__(candidate, 'emitted_judgments')
        result_snapshot = _snapshot_owned(original_result)
        expected = _reservation_copy(reservation, expected=reservation,
                                     maximum=config.identifier_limit)
        if config.history is not None:
            from grading.integration.attempt_history import AttemptStage, AttemptEffect
            if expected.request_ref is None:
                raise AttemptLineageContractError('Owned verification lacks grading-attempt request identity.')
            try:
                config.history(request_ref=expected.request_ref,scope=expected.scope,
                    stage=AttemptStage.VERIFY,effect=AttemptEffect.CONFIRMED,
                    attempt_id=expected.attempt_id,reservation_ref=expected.reservation_ref,
                    result_ref=None,predecessor_result_ref=None)
            except Exception as verification_error:
                self._verify_candidate(candidate, expected, original_result,
                    original_judgments,config.identifier_limit,result_snapshot)
                from grading.integration.attempt_history import AttemptHistoryDenied
                if isinstance(verification_error, AttemptHistoryDenied):
                    raise AttemptLineageDenied('Verification history explicitly denied.') from None
                raise AttemptLineageUnavailable('Verification event not acknowledged.') from None
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments,config.identifier_limit,result_snapshot)
        try:
            observation = config.inspect(reservation=expected, candidate=candidate)
        except AttemptLineageDenied:
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments, config.identifier_limit, result_snapshot)
            raise
        except Exception:
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments, config.identifier_limit, result_snapshot)
            raise AttemptLineageUnavailable('Authoritative attempt ledger is unavailable.') from None
        self._verify_candidate(candidate, expected, original_result,
                               original_judgments, config.identifier_limit, result_snapshot)
        if type(observation) is not TrustedAttemptObservation:
            raise AttemptLineageContractError('Trusted ledger observation has invalid type.')
        try:
            if (type(observation.disposition) is not AttemptDisposition
                    or type(observation.current_state) is not GradingJobState):
                raise AttemptLineageContractError('Ledger disposition/state is malformed.')
            ledger_reservation = _reservation_copy(observation.reservation,
                                                    expected=expected,
                                                    maximum=config.identifier_limit)
            if (ledger_reservation.attempt_id != expected.attempt_id
                    or ledger_reservation.reservation_ref != expected.reservation_ref):
                raise AttemptLineageDenied('Ledger attempt/reservation identity changed.')
            revision = _id(observation.ledger_revision, config.identifier_limit)
            event_ref = _id(observation.event_ref, config.identifier_limit)
            result_ref = _id(observation.result_ref, config.identifier_limit)
        except (AttemptLineageDenied, InvocationDenied):
            raise AttemptLineageDenied('Ledger observation is for another attempt.') from None
        except Exception:
            raise AttemptLineageContractError('Ledger observation identity is malformed.') from None
        if observation.disposition is AttemptDisposition.INDETERMINATE:
            raise AttemptLineageUnavailable('Attempt lineage is indeterminate; reconciliation required.')
        if observation.disposition is not AttemptDisposition.NEW:
            # Replay/late/conflict MUST not become a new candidate or audit claim.
            raise AttemptLineageDenied('Attempt is not a fresh authorized physical attempt.')
        observation_snapshot = _snapshot_owned(observation)
        try:
            approval = config.transition(observation=observation, candidate=candidate)
        except AttemptLineageDenied:
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments, config.identifier_limit, result_snapshot)
            self._verify_snapshot(observation, observation_snapshot, 'Ledger observation')
            raise
        except Exception:
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments, config.identifier_limit, result_snapshot)
            self._verify_snapshot(observation, observation_snapshot, 'Ledger observation')
            raise AttemptLineageUnavailable('Approved lifecycle authorization transition decision is unavailable.') from None
        self._verify_candidate(candidate, expected, original_result,
                               original_judgments, config.identifier_limit, result_snapshot)
        self._verify_snapshot(observation, observation_snapshot, 'Ledger observation')
        if type(approval) is not GradingTransitionApproval:
            raise AttemptLineageContractError('lifecycle authorization transition approval has invalid type.')
        try:
            approved_scope = _scope(approval.scope, config.identifier_limit)
            attempt_id = _id(approval.attempt_id, config.identifier_limit)
            policy_id = _id(approval.policy_id, config.identifier_limit)
            policy_version = approval.policy_version
            approval_ref = _id(approval.approval_ref, config.identifier_limit)
            approval_revision = _id(approval.ledger_revision, config.identifier_limit)
            if (type(approval.source_state) is not GradingJobState
                    or type(approval.target_state) is not GradingJobState
                    or type(policy_version) is not int or policy_version <= 0):
                raise AttemptLineageContractError('lifecycle authorization approved state/policy is malformed.')
            if (approved_scope != expected.scope or attempt_id != expected.attempt_id
                    or approval.source_state is not observation.current_state
                    or approval_revision != revision):
                raise AttemptLineageDenied('lifecycle authorization approval does not bind the installed attempt.')
        except AttemptLineageDenied:
            raise
        except Exception:
            raise AttemptLineageContractError('lifecycle authorization approval identity is malformed.') from None
        if (policy_id != config.policy_id or policy_version != config.policy_version
                or (approval.source_state, approval.target_state) not in config.allowed_edges):
            raise AttemptLineageDenied('lifecycle authorization transition is not permitted by installed policy.')
        # An approved authority must install the legal graph; the engine checks
        # exact policy identity and edges, while the real store owns the
        # authoritative transaction. Fixture graphs are not real approval.
        event = AttemptAuditEvent(event_ref, revision, result_ref, expected.scope,
                                  expected.attempt_id, expected.reservation_ref,
                                  'ATTEMPT_RESULT_CANDIDATE', policy_id,
                                  policy_version, approval.source_state,
                                  approval.target_state, approval_ref,
                                  expected.request_ref,
                                  expected.predecessor_result_ref,
                                  expected.regrade_approval_ref)
        approval_snapshot = _snapshot_owned(approval)
        event_snapshot = _snapshot_owned(event)
        try:
            receipt = config.commit(event=event, candidate=candidate)
        except AttemptLineageDenied:
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments, config.identifier_limit, result_snapshot)
            self._verify_snapshot(observation, observation_snapshot, 'Ledger observation')
            self._verify_snapshot(approval, approval_snapshot, 'attempt lifecycle transition approval')
            self._verify_snapshot(event, event_snapshot, 'Audit event')
            raise
        except Exception:
            self._verify_candidate(candidate, expected, original_result,
                                   original_judgments, config.identifier_limit, result_snapshot)
            self._verify_snapshot(observation, observation_snapshot, 'Ledger observation')
            self._verify_snapshot(approval, approval_snapshot, 'attempt lifecycle transition approval')
            self._verify_snapshot(event, event_snapshot, 'Audit event')
            # A timed-out commit may have persisted. Do NOT retry automatically.
            raise AttemptLineageUnavailable('Attempt/audit commit uncertain; reconcile.') from None
        self._verify_candidate(candidate, expected, original_result,
                               original_judgments, config.identifier_limit, result_snapshot)
        self._verify_snapshot(observation, observation_snapshot, 'Ledger observation')
        self._verify_snapshot(approval, approval_snapshot, 'attempt lifecycle transition approval')
        self._verify_snapshot(event, event_snapshot, 'Audit event')
        try:
            if (_scope(event.scope, config.identifier_limit) != expected.scope
                    or _id(event.event_ref, config.identifier_limit) != event_ref
                    or _id(event.result_ref, config.identifier_limit) != result_ref
                    or _id(event.ledger_revision, config.identifier_limit) != revision
                    or _id(event.attempt_id, config.identifier_limit) != expected.attempt_id
                    or _id(event.reservation_ref, config.identifier_limit) != expected.reservation_ref
                    or _id(event.event_kind, config.identifier_limit) != 'ATTEMPT_RESULT_CANDIDATE'
                    or _id(event.f57_policy_id, config.identifier_limit) != policy_id
                    or type(event.f57_policy_version) is not int
                    or event.f57_policy_version != policy_version
                    or event.source_state is not approval.source_state
                    or event.target_state is not approval.target_state
                    or _id(event.approval_ref, config.identifier_limit) != approval_ref
                    or event.request_ref != expected.request_ref
                    or event.predecessor_result_ref != expected.predecessor_result_ref
                    or event.regrade_approval_ref != expected.regrade_approval_ref):
                raise AttemptLineageDenied('Audit callback changed event identity.')
        except AttemptLineageDenied:
            raise
        except Exception:
            raise AttemptLineageDenied('Audit callback corrupted its event.') from None
        if type(receipt) is not AuditCommitReceipt:
            raise AttemptLineageContractError('Attempt/audit receipt has invalid type.')
        try:
            # Installed audit ports need not be the concrete CAS adapter.
            # Independently admit optional lineage before value comparison.
            predecessor = receipt.predecessor_result_ref
            regrade_approval = receipt.regrade_approval_ref
            if (predecessor is None) != (regrade_approval is None):
                raise AttemptLineageContractError('Audit receipt regrade lineage is incomplete.')
            if predecessor is not None:
                predecessor = _id(predecessor, config.identifier_limit)
                regrade_approval = _id(regrade_approval, config.identifier_limit)
            # A legacy structural invoker may have no request key; the
            # authoritative physical attempt claim seam requires one separately at installation.
            receipt_request_ref = receipt.request_ref
            if receipt_request_ref is not None:
                receipt_request_ref = _id(receipt_request_ref, config.identifier_limit)
            if (type(receipt.target_state) is not GradingJobState
                    or _id(receipt.event_ref, config.identifier_limit) != event_ref
                    or _id(receipt.ledger_revision, config.identifier_limit) != revision
                    or _id(receipt.attempt_id, config.identifier_limit) != attempt_id
                    or _id(receipt.result_ref, config.identifier_limit) != result_ref
                    or _id(receipt.approval_ref, config.identifier_limit) != approval_ref
                    or receipt_request_ref != expected.request_ref
                    or predecessor != expected.predecessor_result_ref
                    or regrade_approval != expected.regrade_approval_ref
                    or receipt.target_state is not approval.target_state):
                raise AttemptLineageContractError('Audit receipt does not match event.')
            _id(receipt.transaction_ref, config.identifier_limit)
        except AttemptLineageContractError:
            raise
        except Exception:
            raise AttemptLineageContractError('Attempt/audit receipt is malformed.') from None
        return AuditedOneQuestionCandidate(candidate, observation, approval, receipt)
