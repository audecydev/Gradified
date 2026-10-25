"""Validate and reconcile physical attempt claims, including lost responses.

The engine validates installed *claims*, not credentials or database commits.
The accountable physical attempt claim owner must supply an atomic, durable, authenticated
implementation; without it no production freshness is established.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from threading import local
from typing import Protocol

from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.evaluator_invocation import (
    AttemptReservation, AttemptReservationRejected, AttemptReservationUnavailable,
    _reservation_copy,
)
from grading.integration.execution_eligibility import _capture, _id, _scope, _strip
from grading.integration.attempt_history import _private_constructor


class DefinitiveAttemptClaimRefusal(AttemptReservationRejected):
    """Qualified physical attempt claim store explicitly denied a fresh claim; NOT a post-claim shape error.

    This class asserts a trusted backend disposition, not independently proven
    durability. Malformed FRESH replies never receive this classification.
    """


class AttemptClaimDisposition(str, Enum):
    FRESH = 'FRESH'
    REPLAY = 'REPLAY'
    CONFLICT = 'CONFLICT'
    REVOKED = 'REVOKED'
    EXPIRED = 'EXPIRED'
    INDETERMINATE = 'INDETERMINATE'


class AttemptClaimRecoveryDisposition(str, Enum):
    NOT_RESERVED = 'NOT_RESERVED'
    RESERVED = 'RESERVED'
    CONFLICT = 'CONFLICT'
    INDETERMINATE = 'INDETERMINATE'


@dataclass(frozen=True, slots=True, repr=False)
class AttemptClaimRequest:
    """Authenticated backend-owned stable identity; never synthesized locally."""
    request_ref: str
    scope: ChoiceAdmissionScope
    family: str
    runtime_id: str
    runtime_version: str
    implementation_ref: str
    eligibility_policy_id: str
    eligibility_policy_version: int
    predecessor_result_ref: str | None = None
    regrade_approval_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class AttemptClaim:
    """Backend claims one execution permit. A reservation is present ONLY for FRESH."""
    request: AttemptClaimRequest
    disposition: AttemptClaimDisposition
    reservation: AttemptReservation | None


@dataclass(frozen=True, slots=True, repr=False)
class AttemptClaimRecoveryFact:
    """Read-only ledger answer; RESERVED never authorizes executing again."""
    request: AttemptClaimRequest
    disposition: AttemptClaimRecoveryDisposition
    reservation: AttemptReservation | None


class StableAttemptClaimRequestIssuer(Protocol):
    def identify_reservation_request(self, *, scope: ChoiceAdmissionScope, family: str,
                                     runtime_id: str, runtime_version: str,
                                     implementation_ref: str, eligibility_policy_id: str,
                                     eligibility_policy_version: int) -> AttemptClaimRequest: ...


class AtomicAttemptClaimStore(Protocol):
    """Backend MUST atomically claim fresh identity before issuing an executable permit."""
    def claim_fresh_attempt(self, *, request: AttemptClaimRequest) -> AttemptClaim: ...

    def reconcile_reservation(self, *, request: AttemptClaimRequest) -> AttemptClaimRecoveryFact: ...


def _request_snapshot(value: object, maximum: int) -> tuple[object, ...]:
    if type(value) is not AttemptClaimRequest:
        raise AttemptReservationRejected('grading-attempt request identity is malformed.')
    try:
        scope = _scope(object.__getattribute__(value, 'scope'), maximum)
        ids = tuple(_id(object.__getattribute__(value, name), maximum) for name in (
            'request_ref', 'family', 'runtime_id', 'runtime_version',
            'implementation_ref', 'eligibility_policy_id'))
        version = object.__getattribute__(value, 'eligibility_policy_version')
        if type(version) is not int or version <= 0:
            raise ValueError('bad version')
        extras=tuple(object.__getattribute__(value, key) for key in (
            'predecessor_result_ref','regrade_approval_ref'))
        if (extras[0] is None) != (extras[1] is None):
            raise ValueError('incomplete regrade')
        for extra in extras:
            if extra is not None:
                _id(extra,maximum)
        return (scope, *ids, version, *extras)
    except Exception:
        raise AttemptReservationRejected('grading-attempt request identity is malformed.') from None



def _make_operation_gate():
    """Ownership capability kept in a closure, separate from event diagnostics.

    Ports receiving the allocator cannot ordinarily obtain its owner token by
    inspecting callback-visible correlation fields. This is not code isolation:
    privileged introspection of closure cells remains outside the trust model.
    """
    state = local()

    def begin():
        if (getattr(state, 'token', None) is not None
                or getattr(state, 'busy', False)):
            raise AttemptReservationRejected('Active grading-attempt correlation cannot be replaced.')
        state.token = object()
        state.consumed = False
        return state.token

    def finish(token):
        if (token is None or token is not getattr(state, 'token', None)
                or getattr(state, 'busy', False)):
            raise AttemptReservationRejected('grading-attempt correlation release is not owned.')
        state.token = None
        state.consumed = False

    def acquire():
        if (getattr(state, 'busy', False)
                or (getattr(state, 'token', None) is not None
                    and getattr(state, 'consumed', False))):
            raise AttemptReservationRejected('grading-attempt reservation already attempted in this operation.')
        if getattr(state, 'token', None) is not None:
            state.consumed = True
        state.busy = True

    def release():
        state.busy = False

    return begin, finish, acquire, release

def _make_authorized_regrade_gate():
    """Invocation-owned legal operation transition predecessor check before an original physical attempt claim.

    This is a trusted-process continuity guard, not institutional authorization:
    only a qualified legal operation transition source and atomic claim backend can establish those.
    """
    state = local()

    def begin(plan, predecessor, approval, prior_requests, maximum, questions, permission=None):
        from grading.integration.paper_execution_correlation import _plan
        verified = _plan(plan, questions, maximum)
        _id(predecessor, maximum)
        _id(approval, maximum)
        if (type(prior_requests) is not tuple or not prior_requests
                or any(type(ref) is not str for ref in prior_requests)):
            raise AttemptReservationRejected('Original predecessor grading-attempt request identities are required.')
        for ref in prior_requests:
            _id(ref, maximum)
        if len(set(prior_requests)) != len(prior_requests):
            raise AttemptReservationRejected('Predecessor grading-attempt requests conflict.')
        if getattr(state, 'token', None) is not None:
            raise AttemptReservationRejected('An authorized regrade is already active.')
        token = object()
        state.token = token
        state.plan = verified
        state.predecessor = predecessor
        state.permission = permission
        state.approval = approval
        state.prior_requests = frozenset(prior_requests)
        state.seen = set()
        state.new_requests = set()
        return token

    def check(original, maximum):
        token = getattr(state, 'token', None)
        if token is None:
            return
        from grading.integration.paper_execution_correlation import _plan
        approved = _plan(state.plan, len(state.plan.questions), maximum)
        if approved != state.plan:
            raise AttemptReservationRejected('Regrade academic plan changed before physical claim.')
        scope = original[0]
        req = approved.request
        expected = (req.tenant_ref, req.session_ref, req.grading_run_id,
                    req.submission_ref, req.exam_ref, req.grading_spec_ref)
        actual = (scope.tenant_ref, scope.session_ref, scope.grading_run_id,
                  scope.submission_ref, scope.exam_ref, scope.grading_spec_ref)
        known = {q.request.question_id for q in approved.questions}
        if (actual != expected or scope.question_id not in known
                or original[8] != state.predecessor or original[9] != state.approval
                or original[1] in state.prior_requests
                or original[1] in state.new_requests
                or scope.question_id in state.seen):
            raise AttemptReservationRejected('Original grading-attempt claim is not bound to approved regrade lineage.')
        state.seen.add(scope.question_id)
        state.new_requests.add(original[1])

    def finish(token):
        if token is not getattr(state, 'token', None):
            raise AttemptReservationRejected('Regrade authorization owner mismatch.')
        state.token = None
        state.plan = None
        state.predecessor = None
        state.permission = None
        state.approval = None
        state.prior_requests = None
        state.seen = None
        state.new_requests = None

    def current_permission():
        return getattr(state, 'permission', None)

    return begin, check, finish, current_permission


def _make_authorized_first_gate():
    """An invocation-owned FIRST approved operation-transition grant reaches every actual conditional physical attempt claim.

    The grant is not self-authenticating: a qualified physical owner must check
    current issuer/transition authorization in the same atomic claim boundary.
    """
    state = local()

    def begin(plan, permission, maximum, questions):
        from grading.integration.paper_execution_correlation import _plan
        from grading.integration.paper_lifecycle import PaperLifecyclePermission, PaperLifecycleKind
        admitted = _plan(plan, questions, maximum)
        if type(permission) is not PaperLifecyclePermission:
            raise AttemptReservationRejected('Exact FIRST lifecycle authorization grant required.')
        # Validate the source record before comparing dataclass values.
        _plan(permission.plan, questions, maximum)
        if (permission.kind is not PaperLifecycleKind.FIRST
                or permission.predecessor is not None
                or permission.predecessor_custody is not None
                or permission.plan != admitted):
            raise AttemptReservationRejected('Original FIRST lifecycle authorization grant does not bind this paper.')
        _id(permission.approval_ref, maximum)
        _id(permission.policy_id, maximum)
        if (type(permission.policy_version) is not int or permission.policy_version <= 0):
            raise AttemptReservationRejected('FIRST policy version malformed.')
        if getattr(state, 'token', None) is not None:
            raise AttemptReservationRejected('FIRST purpose already active in this thread.')
        token = object()
        state.token = token
        state.plan = admitted
        state.permission = permission
        state.seen = set()
        return token

    def check(original, maximum):
        from grading.integration.paper_execution_correlation import _plan
        permission = getattr(state, 'permission', None)
        if getattr(state, 'token', None) is None or permission is None:
            raise AttemptReservationRejected('FIRST lifecycle authorization purpose missing before physical claim.')
        admitted = _plan(state.plan, len(state.plan.questions), maximum)
        _plan(permission.plan, len(admitted.questions), maximum)
        if permission.plan != admitted:
            raise AttemptReservationRejected('FIRST lifecycle authorization purpose changed before claim.')
        scope = original[0]
        request = admitted.request
        if (original[8] is not None or original[9] is not None
                or (scope.tenant_ref, scope.session_ref, scope.grading_run_id,
                    scope.submission_ref, scope.exam_ref, scope.grading_spec_ref)
                   != (request.tenant_ref, request.session_ref, request.grading_run_id,
                       request.submission_ref, request.exam_ref, request.grading_spec_ref)
                or scope.question_id not in {q.request.question_id for q in admitted.questions}
                or scope.question_id in state.seen):
            raise AttemptReservationRejected('FIRST claim is not bound to the original permission.')
        state.seen.add(scope.question_id)

    def finish(token):
        if token is None or token is not getattr(state, 'token', None):
            raise AttemptReservationRejected('FIRST purpose release not owned.')
        state.token = None
        state.plan = None
        state.permission = None
        state.seen = None

    def current_permission():
        return getattr(state, 'permission', None)

    return begin, check, finish, current_permission


class ClaimedAttemptAllocator:
    """Single physical attempt reservation operation consumed by the existing evaluator invoker.

    No second reservation is made. Missing/unknown/duplicate facts never emit
    an AttemptReservation to evaluator invocation, so CHOICE cannot execute in these branches.
    It cannot independently prove the installed attempt issuer/store is authentic.
    """
    __slots__ = ('_identify', '_claim', '_reconcile', '_maximum', '_history', '_current', '_sealed',
                 '_begin_gate', '_finish_gate', '_take_claim', '_release_claim',
                 '_academic_prepare', '_academic_claim', '_academic_recover', '_academic_reconcile_physical',
                 '_academic_max_questions', '_joint_effect', '_begin_regrade', '_check_regrade', '_finish_regrade', '_regrade_permission',
                 '_begin_first', '_check_first', '_finish_first', '_first_permission')

    def __setattr__(self, name, value):
        if name == '__class__':
            raise AttributeError('Installed grading-attempt allocator class cannot be replaced.')
        if name in self.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed grading-attempt operation cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self.__slots__:
            raise AttributeError('Installed grading-attempt operation cannot be deleted.')
        object.__delattr__(self, name)

    def begin_operation(self) -> object:
        """Start the owned physical attempt claim lifetime before paper execution integrity; token retained by lifecycle."""
        try:
            return self._begin_gate()
        except AttemptReservationRejected as exc:
            _strip(exc)
            raise

    def finish_operation(self, *, token: object) -> None:
        """Only an actual owner token may release an active claim lifetime."""
        try:
            self._finish_gate(token)
        except AttemptReservationRejected as exc:
            _strip(exc)
            raise
        self._current.record = None
        self._current.original_record = None
        self._sealed.record = None
        self._sealed.academic_preparation = None

    def _require_request_custody(self, *, request: AttemptClaimRequest,
                                 original: tuple[object, ...],
                                 correlation: tuple[object, ...]) -> None:
        """Compare validated original identity BEFORE the next external effect."""
        try:
            active = self.current_request_context()
            if (type(active) is not tuple or len(active) != 4
                    or _scope(active[0], self._maximum) != correlation[0]
                    or any(type(value) is not str for value in active[1:] if value is not None)
                    or active != correlation
                    or _request_snapshot(request, self._maximum) != original):
                raise AttemptReservationRejected('grading-attempt history changed admitted attempt identity.')
        except AttemptReservationRejected:
            raise
        except Exception:
            raise AttemptReservationRejected('grading-attempt history corrupted admitted identity.') from None

    @_private_constructor
    def __init__(self, *, issuer: StableAttemptClaimRequestIssuer,
                 store: AtomicAttemptClaimStore, max_identifier_characters: int,
                 history: object = None, academic_store: object = None,
                 academic_max_questions: int = 1000, joint_effect: object = None) -> None:
        if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
            raise ValueError('grading-attempt identifier bound is required.')
        try:
            self._identify = _capture(issuer, 'identify_reservation_request', (
                'scope', 'family', 'runtime_id', 'runtime_version',
                'implementation_ref', 'eligibility_policy_id', 'eligibility_policy_version'))
            self._claim = (None if joint_effect is not None else
                           _capture(store, 'claim_fresh_attempt', ('request',)))
            self._reconcile = _capture(store, 'reconcile_reservation', ('request',))
        except Exception:
            raise ValueError('grading-attempt authority ports are missing or invalid.') from None
        if type(academic_max_questions) is not int or not 0 < academic_max_questions <= 10000:
            raise ValueError('Finite academic inventory ceiling is required.')
        # Strict installation: one conditional joint authority/effect path.
        # Existing legacy installations are not qualified for joint effect-time authority.
        if joint_effect is not None:
            from grading.integration.joint_effect_authority import JointEffectAdmission
            if type(joint_effect) is not JointEffectAdmission or academic_store is None:
                raise ValueError('Joint grading-attempt effect needs an installed bound academic source.')
        self._joint_effect = joint_effect
        self._academic_max_questions = academic_max_questions
        if academic_store is None:
            self._academic_prepare = None
            self._academic_claim = None
            self._academic_recover = None
            self._academic_reconcile_physical = None
        else:
            # The installed qualified provider owns BOTH durable original
            # preparation and the claim that enforces its revision/lease.
            self._academic_prepare = _capture(academic_store, 'prepare_original_binding', ('intent',))
            self._academic_claim = (None if joint_effect is not None else
                                    _capture(academic_store, 'claim_bound_fresh', ('preparation',)))
            self._academic_recover = _capture(academic_store, 'reconcile_original_binding', ('intent',))
            self._academic_reconcile_physical = _capture(academic_store, 'reconcile_bound_attempt', ('request',))
        self._maximum = max_identifier_characters
        self._current = local()
        # The callback-visible diagnostic record is not an authority. The
        # operation seal and the ownership capability live in separate state.
        # This prevents ordinary mutation of diagnostics from changing origin.
        # This is NOT a sandbox against privileged same-interpreter introspection.
        self._sealed = local()
        (self._begin_gate, self._finish_gate,
         self._take_claim, self._release_claim) = _make_operation_gate()
        (self._begin_regrade, self._check_regrade,
         self._finish_regrade, self._regrade_permission) = _make_authorized_regrade_gate()
        (self._begin_first, self._check_first, self._finish_first,
         self._first_permission) = _make_authorized_first_gate()
        self._history = None if history is None else _capture(history, 'emit_phase', (
            'request_ref','scope','stage','effect','attempt_id','reservation_ref',
            'result_ref','predecessor_result_ref'))

    def begin_authorized_first(self, *, plan, permission) -> object:
        if self._joint_effect is None:
            raise AttemptReservationRejected('FIRST operation gate requires joint effect owner.')
        return self._begin_first(plan, permission, self._maximum, self._academic_max_questions)

    def finish_authorized_first(self, *, token: object) -> None:
        self._finish_first(token)

    def begin_authorized_regrade(self, *, plan, predecessor_result_ref: str,
                                 regrade_approval_ref: str,
                                 predecessor_request_refs: tuple[str, ...],
                                 permission: object = None) -> object:
        if self._academic_prepare is None:
            raise AttemptReservationRejected('Regrade requires academically bound claiming.')
        if self._joint_effect is not None:
            from grading.integration.paper_lifecycle import PaperLifecyclePermission
            if type(permission) is not PaperLifecyclePermission:
                raise AttemptReservationRejected('Current source-issued regrade purpose is required.')
        return self._begin_regrade(plan, predecessor_result_ref,
                                   regrade_approval_ref, predecessor_request_refs, self._maximum,
                                   self._academic_max_questions, permission)

    def finish_authorized_regrade(self, *, token: object) -> None:
        self._finish_regrade(token)

    def observed_original_request(self) -> AttemptClaimRequest | None:
        """Detached identity actually issued for the latest same-thread claim.

        This is a local historical observation, NOT an authenticated backend
        acknowledgment, durable recovery proof, or execution permission. A
        missing observation must remain UNKNOWN rather than being reconstructed
        from a later issuer response. The next claim clears it before issuance.
        """
        original = getattr(self._sealed, 'original_request', None)
        if original is None:
            return None
        snapshot = _request_snapshot(original, self._maximum)
        correlation = self.current_request_context()
        if (correlation is None or correlation[0] != snapshot[0]
                or correlation[1] != snapshot[1]):
            raise AttemptReservationRejected('Original grading-attempt request observation is unbound.')
        return AttemptClaimRequest(snapshot[1], snapshot[0],
            *snapshot[2:8], snapshot[8], snapshot[9])

    def observed_academic_preparation(self):
        """Local pre-claim acknowledgment, not an authenticated durable receipt."""
        return getattr(self._sealed, 'academic_preparation', None)

    def current_request_context(self) -> object:
        """Return only current-operation, originally admitted correlation.

        A callback-visible mutable record is never itself history authority.
        If that record drifts, withhold history rather than misattribute it.
        """
        original = getattr(self._sealed, 'record', None)
        diagnostic_original = getattr(self._current, 'original_record', None)
        current = getattr(self._current, 'record', None)
        if original is None:
            if current is not None or diagnostic_original is not None:
                raise AttemptReservationRejected('grading-attempt correlation has no admitted source.')
            return None
        if (type(original) is not tuple or len(original) != 4
                or type(diagnostic_original) is not tuple or len(diagnostic_original) != 4
                or type(current) is not tuple or len(current) != 4):
            raise AttemptReservationRejected('grading-attempt admitted correlation was corrupted.')
        try:
            for key in (original, diagnostic_original, current):
                _scope(key[0], self._maximum)
                _id(key[1], self._maximum)
                for optional in key[2:]:
                    if optional is not None:
                        _id(optional, self._maximum)
            if current != original or diagnostic_original != original:
                raise AttemptReservationRejected('grading-attempt correlation changed after admission.')
        except AttemptReservationRejected:
            raise
        except Exception:
            raise AttemptReservationRejected('grading-attempt correlation is invalid.') from None
        return original

    def _emit(self, stage: object, effect: object) -> None:
        if self._history is None:
            return
        from grading.integration.attempt_history import AttemptStage, AttemptEffect
        if type(stage) is not AttemptStage or type(effect) is not AttemptEffect:
            raise AttemptReservationUnavailable('grading-attempt event grammar invalid.')
        record = self.current_request_context()
        if record is None:
            raise AttemptReservationUnavailable('grading-attempt correlation unavailable.')
        # Regrade lineage is emitted from the validated ORIGINAL request,
        # never guessed from a current receipt or omitted after an effect.
        original_request = getattr(self._sealed, 'original_request', None)
        prior = (None if original_request is None
                 else _request_snapshot(original_request, self._maximum)[8])
        try:
            self._history(request_ref=record[1], scope=record[0], stage=stage,
                          effect=effect, attempt_id=record[2],
                          reservation_ref=record[3], result_ref=None,
                          predecessor_result_ref=prior)
        except AttemptReservationRejected:
            # A local correlation/lifecycle integrity refusal must not be
            # obscured as a backend outage before the physical attempt claim.
            raise
        except Exception as failure:
            from grading.integration.attempt_history import AttemptHistoryDenied
            if isinstance(failure, AttemptHistoryDenied):
                raise AttemptReservationRejected('grading-attempt lifecycle history integrity denied.') from None
            # An unavailable or timed-out writer might already have committed.
            raise AttemptReservationUnavailable('grading-attempt lifecycle event not acknowledged.') from None

    def _identify_request(self, *, scope: ChoiceAdmissionScope, family: str,
                          runtime_id: str, runtime_version: str,
                          implementation_ref: str, eligibility_policy_id: str,
                          eligibility_policy_version: int) -> tuple[AttemptClaimRequest, tuple[object, ...]]:
        maximum = self._maximum
        safe_scope = _scope(scope, maximum)
        unchanged_scope = _scope(safe_scope, maximum)
        details = (family, runtime_id, runtime_version, implementation_ref, eligibility_policy_id)
        for value in details:
            _id(value, maximum)
        if type(eligibility_policy_version) is not int or eligibility_policy_version <= 0:
            raise AttemptReservationRejected('grading-attempt policy version is malformed.')
        try:
            request = self._identify(
                scope=safe_scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version, implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version,
            )
        except Exception as issuance_failure:
            from grading.integration.attempt_history import AttemptHistoryDenied
            try:
                if _scope(safe_scope, maximum) != unchanged_scope:
                    raise AttemptReservationRejected('grading-attempt scope was changed during failed issuance.')
            except AttemptReservationRejected:
                raise
            except Exception:
                raise AttemptReservationRejected('grading-attempt scope was corrupted during failed issuance.') from None
            if isinstance(issuance_failure, AttemptHistoryDenied):
                raise AttemptReservationRejected('grading-attempt new-run identity was denied.') from None
            raise AttemptReservationUnavailable('grading-attempt request issuance unavailable.') from None
        # A port must not modify its passed scope before authority is checked.
        if _scope(safe_scope, maximum) != unchanged_scope:
            raise AttemptReservationRejected('grading-attempt request source changed during issuance.')
        values = _request_snapshot(request, maximum)
        # Request reference belongs to the installed issuer; every other
        # identity field must be exactly the requested installed scope.
        if values[0] != safe_scope or values[2:8] != (*details, eligibility_policy_version):
            raise AttemptReservationRejected('grading-attempt request identity does not bind this invocation.')
        # The authorized regrade binding must match the ORIGINAL physical attempt request,
        # before history, durable academic preparation or physical attempt claim contact.
        self._check_regrade(values, maximum)
        if self._joint_effect is not None and values[8] is None:
            self._check_first(values, maximum)
        return request, values

    @property
    def academic_binding_enabled(self) -> bool:
        return self._academic_prepare is not None

    def reserve_attempt(self, *, scope: ChoiceAdmissionScope, family: str,
                        runtime_id: str, runtime_version: str,
                        implementation_ref: str, eligibility_policy_id: str,
                        eligibility_policy_version: int) -> AttemptReservation:
        """Preserved exact evaluator invocation installed interface; cannot bypass bound mode."""
        return self._reserve_scoped_attempt(scope=scope, family=family,
            runtime_id=runtime_id, runtime_version=runtime_version,
            implementation_ref=implementation_ref,
            eligibility_policy_id=eligibility_policy_id,
            eligibility_policy_version=eligibility_policy_version)

    def reserve_academically_bound_attempt(self, *, scope: ChoiceAdmissionScope,
                        family: str, runtime_id: str, runtime_version: str,
                        implementation_ref: str, eligibility_policy_id: str,
                        eligibility_policy_version: int, academic_paper: object,
                        academic_scoring: object,
                        approved_runtime: object = None) -> AttemptReservation:
        """academic-bound physical claim physical claim under full authorized paper and versioned scorer."""
        if self._academic_prepare is None:
            raise AttemptReservationRejected('No installed academic claim authority.')
        return self._reserve_scoped_attempt(scope=scope, family=family,
            runtime_id=runtime_id, runtime_version=runtime_version,
            implementation_ref=implementation_ref,
            eligibility_policy_id=eligibility_policy_id,
            eligibility_policy_version=eligibility_policy_version,
            academic_paper=academic_paper, academic_scoring=academic_scoring,
            approved_runtime=approved_runtime)

    def _reserve_scoped_attempt(self, *, scope: ChoiceAdmissionScope, family: str,
                        runtime_id: str, runtime_version: str,
                        implementation_ref: str, eligibility_policy_id: str,
                        eligibility_policy_version: int,
                        academic_paper: object = None,
                        academic_scoring: object = None,
                        approved_runtime: object = None) -> AttemptReservation:
        """Consume local claim right BEFORE issuer/history/physical-attempt backend effects."""
        try:
            self._take_claim()
            try:
                return self._reserve_attempt_once(
                    scope=scope, family=family, runtime_id=runtime_id,
                    runtime_version=runtime_version,
                    implementation_ref=implementation_ref,
                    eligibility_policy_id=eligibility_policy_id,
                    eligibility_policy_version=eligibility_policy_version,
                    academic_paper=academic_paper,
                    academic_scoring=academic_scoring,
                    approved_runtime=approved_runtime,
                )
            finally:
                self._release_claim()
        except (AttemptReservationRejected, AttemptReservationUnavailable) as exc:
            # Sanitize the exception after the final callback/translation frame.
            # In particular, `raise ... from None` alone retains __context__.
            _strip(exc)
            raise

    def _reserve_attempt_once(self, *, scope: ChoiceAdmissionScope, family: str,
                              runtime_id: str, runtime_version: str,
                              implementation_ref: str, eligibility_policy_id: str,
                              eligibility_policy_version: int,
                              academic_paper: object = None,
                        academic_scoring: object = None,
                        approved_runtime: object = None) -> AttemptReservation:
        self._current.record = None
        self._current.original_record = None
        self._sealed.record = None
        self._sealed.original_request = None
        self._sealed.academic_preparation = None
        claimed_effect = False
        definitive_refusal = False
        try:
            request, original = self._identify_request(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version, implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version)
            # The original validated request identity must survive even if the
            # claim commits and the store response is lost. Capture BEFORE
            # history/store callbacks and never infer it from recovery output.
            self._sealed.original_request = AttemptClaimRequest(
                original[1], original[0], *original[2:8], original[8], original[9])
            self._current.original_record = (original[0],original[1],None,None)
            self._sealed.record = self._current.original_record
            self._current.record = self._current.original_record
            if self._history is not None:
                from grading.integration.attempt_history import AttemptStage, AttemptEffect
                expected_correlation = self._current.record
                try:
                    self._emit(AttemptStage.PRE,AttemptEffect.CONFIRMED)
                finally:
                    self._require_request_custody(request=request, original=original,
                                                  correlation=expected_correlation)
            failure = None
            result = None
            preparation = None
            if self._joint_effect is not None and approved_runtime is None:
                raise AttemptReservationRejected('Joint grading-attempt claim requires original approved runtime.')
            if self._academic_prepare is not None:
                from grading.integration.academic_claim_binding import (
                    academic_intent, validate_preparation,
                )
                try:
                    academic = academic_intent(request, academic_paper, academic_scoring, self._maximum,
                                               self._academic_max_questions)
                    from grading.integration.academic_claim_binding import academic_identity_snapshot
                    paper_snapshot = academic_identity_snapshot(academic, self._maximum,
                                                                self._academic_max_questions)
                except Exception:
                    raise AttemptReservationRejected('Academic request binding is missing or invalid.') from None
                try:
                    preparation = self._academic_prepare(intent=academic)
                    # Revalidate BOTH original approved paper and actual request
                    # after the persistence callback, before physical attempt claim contact.
                    if (academic_identity_snapshot(academic_intent(request, academic_paper, academic_scoring,
                        self._maximum, self._academic_max_questions), self._maximum,
                        self._academic_max_questions) != paper_snapshot):
                        raise ValueError('Preclaim academic authority changed during persistence.')
                    preparation = validate_preparation(preparation, academic, self._maximum)
                    prepared_fields = (preparation.binding_ref, preparation.approval_revision,
                                       preparation.state, preparation.intent)
                    self._sealed.academic_preparation = preparation
                except Exception:
                    # A durable prepare operation may have committed despite a
                    # lost response. Without its verified receipt NO physical attempt claim.
                    raise AttemptReservationUnavailable('Academic preclaim persistence not confirmed.') from None
            try:
                claimed_effect = True
                if self._joint_effect is not None:
                    from grading.integration.joint_effect_authority import (
                        JointAuthoritySnapshot, ConditionalEffectClaim,
                        GradingEffectKind, EffectDecision,
                    )
                    from grading.integration.academic_claim_binding import validate_bound_claim
                    joint_request = ConditionalEffectClaim(
                        JointAuthoritySnapshot(academic, approved_runtime,
                                               self._maximum, self._academic_max_questions),
                        preparation, (GradingEffectKind.REGRADE_F25
                                      if original[8] is not None else GradingEffectKind.FIRST_F25),
                        regrade_permission=(self._regrade_permission() if original[8] is not None else None),
                        first_permission=(self._first_permission() if original[8] is None else None),
                    )
                    joint_answer = self._joint_effect.claim(request=joint_request)
                    if joint_answer.state is EffectDecision.REJECTED:
                        definitive_refusal = True
                        raise DefinitiveAttemptClaimRefusal('Joint authority denied physical attempt claim.')
                    if joint_answer.state is not EffectDecision.COMMITTED:
                        raise AttemptReservationUnavailable('Joint physical attempt outcome unknown.')
                    result = validate_bound_claim(joint_answer.bound_claim,
                                                  preparation, self._maximum)
                elif preparation is not None:
                    from grading.integration.academic_claim_binding import validate_bound_claim
                    bound_result = self._academic_claim(preparation=preparation)
                    result = validate_bound_claim(bound_result, preparation, self._maximum)
                else:
                    result = self._claim(request=request)
            except DefinitiveAttemptClaimRefusal:
                raise
            except Exception:
                failure = AttemptReservationUnavailable
            if preparation is not None:
                try:
                    from grading.integration.academic_claim_binding import academic_intent, academic_identity_snapshot
                    if (preparation.binding_ref, preparation.approval_revision,
                        preparation.state, preparation.intent) != prepared_fields:
                        raise ValueError('Academic binding receipt changed during claim.')
                    if (academic_identity_snapshot(academic_intent(request, academic_paper, academic_scoring,
                        self._maximum, self._academic_max_questions), self._maximum,
                        self._academic_max_questions) != paper_snapshot):
                        raise ValueError('Academic paper changed across physical attempt claim.')
                except Exception:
                    raise AttemptReservationUnavailable('Academic claim changed current paper.') from None
            # A mutated request must be rejected regardless of claim/exception.
            if _request_snapshot(request, self._maximum) != original:
                raise AttemptReservationRejected('grading-attempt request changed during claim.')
            if failure:
                raise AttemptReservationUnavailable('grading-attempt claim outcome unknown; reconcile.')
            if type(result) is not AttemptClaim:
                raise AttemptReservationRejected('grading-attempt claim response malformed.')
            if _request_snapshot(result.request, self._maximum) != original:
                raise AttemptReservationRejected('grading-attempt claim has foreign request identity.')
            disposition = result.disposition
            if type(disposition) is not AttemptClaimDisposition:
                raise AttemptReservationRejected('grading-attempt claim disposition is malformed.')
            if disposition is AttemptClaimDisposition.INDETERMINATE:
                raise AttemptReservationUnavailable('grading-attempt claim not resolved; reconcile.')
            if disposition is not AttemptClaimDisposition.FRESH:
                # AttemptClaim permits a reservation ONLY for FRESH. An inconsistent
                # post-contact record cannot attest a definitive no-new-claim.
                if result.reservation is not None:
                    raise AttemptReservationRejected(
                        'Non-FRESH grading-attempt claim carried a reservation.')
                # No executable permit; distinguish backend's definitive refusal
                # from corruption or uncertain durable effects.
                definitive_refusal = True
                raise DefinitiveAttemptClaimRefusal('grading-attempt did not authorize a fresh attempt.')
            claimed = result.reservation
            if type(claimed) is not AttemptReservation:
                raise AttemptReservationRejected('grading-attempt fresh reservation is missing or malformed.')
            expected = AttemptReservation(original[0], '', '', *original[2:8],
                request_ref=original[1],predecessor_result_ref=original[8],
                regrade_approval_ref=original[9])
            try:
                copied = _reservation_copy(claimed, expected=expected, maximum=self._maximum)
                _id(copied.attempt_id, self._maximum)
                _id(copied.reservation_ref, self._maximum)
                if (copied.request_ref != original[1]
                        or copied.predecessor_result_ref != original[8]
                        or copied.regrade_approval_ref != original[9]):
                    raise AttemptReservationRejected('grading-attempt reserved a different request or regrade identity.')
            except Exception:
                raise AttemptReservationRejected('grading-attempt fresh claim has invalid scope or identity.') from None
            self._current.original_record = (original[0],original[1],copied.attempt_id,copied.reservation_ref)
            self._sealed.record = self._current.original_record
            self._current.record = self._current.original_record
            if self._history is not None:
                expected_correlation = self._current.record
                try:
                    self._emit(AttemptStage.ATTEMPT,AttemptEffect.CONFIRMED)
                    self._require_request_custody(request=request, original=original,
                                                  correlation=expected_correlation)
                    # Dispatch permission is NOT proof that evaluation succeeded.
                    self._emit(AttemptStage.EVALUATION,AttemptEffect.DISPATCH_AUTHORIZED)
                finally:
                    self._require_request_custody(request=request, original=original,
                                                  correlation=expected_correlation)
            return copied
        except (AttemptReservationRejected, AttemptReservationUnavailable) as exc:
            if claimed_effect and self._history is not None:
                from grading.integration.attempt_history import AttemptStage, AttemptEffect
                effect=(AttemptEffect.DENIED if definitive_refusal
                        else AttemptEffect.UNKNOWN)
                self._emit(AttemptStage.ATTEMPT,effect)
            raise
        except Exception:
            raise AttemptReservationUnavailable('grading-attempt claim could not be validated.') from None

    def identify_for_reconciliation(self, *, scope: ChoiceAdmissionScope,
                                     family: str, runtime_id: str,
                                     runtime_version: str, implementation_ref: str,
                                     eligibility_policy_id: str,
                                     eligibility_policy_version: int) -> str:
        """Re-identify original backend request without reserving or executing."""
        try:
            _, values = self._identify_request(
                scope=scope,family=family,runtime_id=runtime_id,
                runtime_version=runtime_version,implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version)
            return values[1]
        except (AttemptReservationRejected,AttemptReservationUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc=AttemptReservationUnavailable('Stable evaluation-attempt request unavailable.')
            _strip(exc)
            raise exc from None

    def reconcile_request(self, *, scope: ChoiceAdmissionScope, family: str,
                          runtime_id: str, runtime_version: str,
                          implementation_ref: str, eligibility_policy_id: str,
                          eligibility_policy_version: int,
                          original_request: AttemptClaimRequest | None = None) -> AttemptClaimRecoveryFact:
        """Read only; never dispatch CHOICE or repeat a prior claim.

        An explicitly supplied original request is checked against the caller's
        exact scope and installation parameters BEFORE any backend read. That
        path never re-identifies via the current issuer. Existing callers that
        omit it retain the earlier re-identification behavior. Neither path
        authenticates the request or grants a new attempt or retry.
        """
        try:
            if original_request is None:
                request, original = self._identify_request(
                    scope=scope, family=family, runtime_id=runtime_id,
                    runtime_version=runtime_version, implementation_ref=implementation_ref,
                    eligibility_policy_id=eligibility_policy_id,
                    eligibility_policy_version=eligibility_policy_version)
            else:
                request = original_request
                original = _request_snapshot(request, self._maximum)
                checked_scope = _scope(scope, self._maximum)
                expected = (family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version)
                if original[0] != checked_scope or original[2:8] != expected:
                    raise AttemptReservationRejected('Original grading-attempt request does not bind recovery.')
            try:
                # In bound mode the SAME qualified academic/physical attempt claim provider must
                # supply physical recovery, never an unrelated raw physical attempt claim store.
                read = self._academic_reconcile_physical or self._reconcile
                fact = read(request=request)
            except Exception as failure:
                try:
                    unchanged = _request_snapshot(request, self._maximum) == original
                except Exception:
                    unchanged = False
                if not unchanged:
                    raise AttemptReservationRejected('grading-attempt request changed during failed reconciliation.') from None
                if isinstance(failure, AttemptReservationRejected):
                    raise AttemptReservationRejected('grading-attempt reconciliation was refused.') from None
                raise AttemptReservationUnavailable('grading-attempt reconciliation outcome unknown.') from None
            if _request_snapshot(request, self._maximum) != original:
                raise AttemptReservationRejected('grading-attempt request changed during reconciliation.')
            if type(fact) is not AttemptClaimRecoveryFact or _request_snapshot(fact.request, self._maximum) != original:
                raise AttemptReservationRejected('grading-attempt reconciliation identity malformed.')
            if type(fact.disposition) is not AttemptClaimRecoveryDisposition:
                raise AttemptReservationRejected('grading-attempt reconciliation disposition malformed.')
            if fact.disposition is AttemptClaimRecoveryDisposition.RESERVED:
                if type(fact.reservation) is not AttemptReservation:
                    raise AttemptReservationRejected('grading-attempt recovery reservation missing.')
                expected = AttemptReservation(original[0], '', '', *original[2:8],
                request_ref=original[1],predecessor_result_ref=original[8],
                regrade_approval_ref=original[9])
                try:
                    rec = _reservation_copy(fact.reservation, expected=expected,
                                            maximum=self._maximum)
                    if (rec.request_ref != original[1]
                            or rec.predecessor_result_ref != original[8]
                            or rec.regrade_approval_ref != original[9]):
                        raise AttemptReservationRejected('grading-attempt recovery request/lineage mismatch.')
                except Exception:
                    raise AttemptReservationRejected('grading-attempt recovery scope does not match.') from None
            elif fact.reservation is not None:
                raise AttemptReservationRejected('grading-attempt unresolved fact cannot supply reservation.')
            return fact
        except (AttemptReservationRejected, AttemptReservationUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc = AttemptReservationUnavailable('Evaluation-attempt recovery unavailable.')
            _strip(exc)
            raise exc from None


def assemble_controlled_choice_root(*, handoff: object,
                                    request_issuer: StableAttemptClaimRequestIssuer,
                                    f25_store: AtomicAttemptClaimStore,
                                    ledger: object, transitions: object,
                                    transaction_store: object,
                                    approved_f57_policy: object,
                                    max_identifier_characters: int,
                                    history_issuer: object = None,
                                    history_writer: object = None) -> object:
    """One Gradified-owned composition: paper execution integrity -> atomic physical attempt claim -> CHOICE -> operation transitions and conditional score commits.

    There is no fallback, second reservation, hard-coded request identity or
    fake production approval. Only the deployment owner can establish that
    its installed issuers and transactional stores meet these protocols.
    """
    from grading.integration.evaluator_invocation import ProductionChoiceEvaluatorInvoker
    from grading.integration.attempt_lineage import ProductionChoiceAttemptLifecycle
    from grading.integration.attempt_transaction import AtomicResultStateAudit
    from grading.integration.attempt_history import CorrelatedHistoryRecorder
    if (request_issuer is None or f25_store is None or ledger is None
            or transitions is None or transaction_store is None
            or approved_f57_policy is None or history_issuer is None
            or history_writer is None):
        raise ValueError('All trusted attempt, lifecycle, history, and transaction authorities are required.')
    history = CorrelatedHistoryRecorder(
        issuer=history_issuer,writer=history_writer,
        max_identifier_characters=max_identifier_characters)
    claim = ClaimedAttemptAllocator(issuer=request_issuer, store=f25_store,
        max_identifier_characters=max_identifier_characters,history=history)
    invocation = ProductionChoiceEvaluatorInvoker(
        handoff=handoff, attempts=claim,
        max_identifier_characters=max_identifier_characters)
    atomic = AtomicResultStateAudit(
        store=transaction_store,max_identifier_characters=max_identifier_characters)
    lifecycle=ProductionChoiceAttemptLifecycle(
        invoker=invocation, ledger=ledger, transitions=transitions,
        audit=atomic, approved_f57_policy=approved_f57_policy,
        max_identifier_characters=max_identifier_characters,
        history=history, correlation=claim)
    return ControlledChoiceAttemptRoot(managed=lifecycle,claim=claim,
        audit=atomic,handoff=handoff,maximum=max_identifier_characters)


class ControlledChoiceAttemptRoot:
    """One owned entry point, including admitted paper execution *read-only* reconciliation.

    A caller cannot gain ledger access by providing a matching scope dataclass;
    both recovery methods obtain scope through the actual trusted paper execution integrity handoff.
    Publication remains exclusively outside the grading engine.
    """
    __slots__=('_managed','_claim','_audit','_handoff','_maximum','_thread')

    def __setattr__(self,name: str,value: object) -> None:
        if name in self.__slots__:
            try: object.__getattribute__(self,name)
            except AttributeError: pass
            else: raise AttributeError('Owned attempt installation cannot be replaced.')
        object.__setattr__(self,name,value)

    def __delattr__(self, name: str) -> None:
        if name in self.__slots__:
            raise AttributeError('Owned attempt installation cannot be deleted.')
        object.__delattr__(self, name)

    @_private_constructor
    def __init__(self, *, managed: object, claim: ClaimedAttemptAllocator,
                 audit: object, handoff: object, maximum: int) -> None:
        self._managed=managed
        self._claim=claim
        self._audit=audit
        self._handoff=handoff
        self._maximum=maximum
        self._thread=local()

    def _enter(self) -> None:
        """Exclude same-thread execution during read-only recovery callbacks.

        Not a distributed attempt lock: physical attempt claim must enforce actual uniqueness.
        """
        if getattr(self._thread, 'busy', False):
            exc=AttemptReservationRejected('Owned attempt root reentry is forbidden.')
            _strip(exc)
            raise exc from None
        self._thread.busy=True

    def run_choice(self, *, request: object) -> object:
        try:
            self._enter()
        except AttemptReservationRejected as exc:
            _strip(exc)
            raise
        try:
            return self._managed.run_choice(request=request)
        finally:
            self._thread.busy=False

    def _owned_recovery_scope(self, *, request: object) -> tuple[object, ...]:
        from grading.integration.evaluator_invocation import _validated_binding_snapshot
        from grading.choice_evaluator import evaluate_single_select_choice
        try:
            root=self._handoff
            root._require_root()
            bound=root.prepare_choice_runtime(request=request)
            snapshot=_validated_binding_snapshot(bound,handoff=root,maximum=self._maximum)
            scope,_,_,policy,_,_,_,approved,runtime=snapshot
            if runtime.handler is not evaluate_single_select_choice:
                raise AttemptReservationRejected('Recovered runtime is not installed CHOICE.')
            root._require_root()
            if _validated_binding_snapshot(bound,handoff=root,maximum=self._maximum) != snapshot:
                raise AttemptReservationRejected('Recovered whole-paper execution authority changed.')
            return (scope,'CHOICE',approved.runtime_id,approved.runtime_version,
                    approved.implementation_ref,policy.policy_id,policy.policy_version)
        except AttemptReservationRejected:
            raise
        except Exception:
            raise AttemptReservationUnavailable('Trusted whole-paper execution recovery prerequisites unavailable.') from None

    def reconcile_owned_attempt(self, *, request: object) -> AttemptClaimRecoveryFact:
        try:
            self._enter()
        except AttemptReservationRejected as exc:
            _strip(exc)
            raise
        try:
            scope,family,rid,version,implementation,pid,pver=self._owned_recovery_scope(request=request)
            return self._claim.reconcile_request(scope=scope,family=family,
                runtime_id=rid,runtime_version=version,implementation_ref=implementation,
                eligibility_policy_id=pid,eligibility_policy_version=pver)
        except (AttemptReservationRejected,AttemptReservationUnavailable) as exc:
            _strip(exc)
            raise
        finally:
            self._thread.busy=False

    def reconcile_owned_transaction(self, *, request: object) -> object:
        """No new physical claim, choice evaluation, legal transition or commit; reconciles by original key."""
        try:
            self._enter()
        except AttemptReservationRejected as exc:
            _strip(exc)
            raise
        try:
            scope,family,rid,version,implementation,pid,pver=self._owned_recovery_scope(request=request)
            request_ref=self._claim.identify_for_reconciliation(scope=scope,family=family,
                runtime_id=rid,runtime_version=version,implementation_ref=implementation,
                eligibility_policy_id=pid,eligibility_policy_version=pver)
            return self._audit.reconcile_owned_request(scope=scope,request_ref=request_ref)
        except (AttemptReservationRejected,AttemptReservationUnavailable) as exc:
            _strip(exc)
            raise
        finally:
            self._thread.busy=False
