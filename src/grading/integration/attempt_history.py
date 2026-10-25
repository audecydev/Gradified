"""Engine-owned failure/recovery/event and authorized immutable regrade contracts.

All IDs and grants must be issued by installed accountable authorities. No
synthetic timestamps, invented attempt identities, policy or persistence here.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from enum import Enum
from typing import Protocol

from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.execution_eligibility import _capture, _id, _scope, _strip


def _private_constructor(method):
    """Sanitize the *final* public installer exception, including ambient context.

    A trusted installation defect is not a reason to expose backend exceptions
    or fabricate replacement authorities. Process-level BaseException escapes.
    """
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            try:
                return method(*args, **kwargs)
            except ValueError:
                raise
            except Exception:
                raise ValueError('Required grading authority installation is invalid.') from None
        except ValueError as exc:
            _strip(exc)
            raise
    return guarded


class AttemptHistoryDenied(ValueError):
    """An unapproved, malformed, foreign or conflicting history operation."""


class AttemptHistoryUnavailable(Exception):
    """The authoritative history/authorization outcome is not established."""


class AttemptStage(str, Enum):
    PRE = 'PRE'
    ATTEMPT = 'ATTEMPT'
    EVALUATION = 'EVALUATION'
    VERIFY = 'VERIFY'
    F57 = 'F57'
    AUDIT = 'AUDIT'
    FAILURE = 'FAILURE'
    RECOVERY = 'RECOVERY'
    RETRY = 'RETRY'
    REGRADE = 'REGRADE'


class AttemptEffect(str, Enum):
    DISPATCH_AUTHORIZED = 'DISPATCH_AUTHORIZED'  # actual CHOICE has not yet returned
    DENIED = 'DENIED'
    CONFIRMED = 'CONFIRMED'
    UNAVAILABLE = 'UNAVAILABLE'
    UNKNOWN = 'UNKNOWN'
    CONFLICT = 'CONFLICT'
    SUPERSEDED = 'SUPERSEDED'


@dataclass(frozen=True, slots=True, repr=False)
class CorrelatedAttemptEvent:
    """Allowlisted event; absent attempt_id is truthful prior to physical attempt claim response."""
    event_ref: str
    request_ref: str
    scope: ChoiceAdmissionScope
    stage: AttemptStage
    effect: AttemptEffect
    attempt_id: str | None = None
    reservation_ref: str | None = None
    result_ref: str | None = None
    predecessor_result_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class AttemptEventAcknowledgment:
    event_ref: str
    request_ref: str
    receipt_ref: str


class HistoryEventWriter(Protocol):
    def append_attempt_event(self, *, event: CorrelatedAttemptEvent) -> AttemptEventAcknowledgment: ...


class RegradeAuthorizationSource(Protocol):
    def resolve_authorized_regrade(self, *, prior_result_ref: str) -> 'AuthorizedRegrade': ...


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedRegrade:
    """Backend-returned approval only, not a grant constructible by a caller."""
    approval_ref: str
    predecessor_result_ref: str
    predecessor_scope: ChoiceAdmissionScope
    new_scope: ChoiceAdmissionScope
    new_request_ref: str


def _event_identity(event: object, limit: int) -> tuple[object, ...]:
    if type(event) is not CorrelatedAttemptEvent:
        raise AttemptHistoryDenied('Attempt event must have the exact contract type.')
    try:
        ids = tuple(_id(object.__getattribute__(event, name), limit) for name in (
            'event_ref', 'request_ref'))
        scope = _scope(object.__getattribute__(event, 'scope'), limit)
        stage = object.__getattribute__(event, 'stage')
        effect = object.__getattribute__(event, 'effect')
        if type(stage) is not AttemptStage or type(effect) is not AttemptEffect:
            raise ValueError('invalid stage/effect')
        optional = []
        for key in ('attempt_id','reservation_ref','result_ref','predecessor_result_ref'):
            value = object.__getattribute__(event, key)
            optional.append(None if value is None else _id(value, limit))
        if ((optional[0] is None) != (optional[1] is None)
                or (stage in (AttemptStage.PRE, AttemptStage.ATTEMPT) and optional[2] is not None)
                or (stage is AttemptStage.REGRADE and optional[3] is None)
                or (stage is not AttemptStage.REGRADE and optional[3] is not None)
                or (stage in (AttemptStage.EVALUATION, AttemptStage.VERIFY)
                    and optional[0] is None)
                or (effect is AttemptEffect.DISPATCH_AUTHORIZED
                    and stage is not AttemptStage.EVALUATION)):
            raise ValueError('inconsistent event lineage')
        return (*ids, scope, stage, effect, *optional)
    except Exception:
        raise AttemptHistoryDenied('Attempt event has malformed or contradictory identity.') from None


class AttemptHistoryCustody:
    """Installed event writer; receipt comparison is NOT proof of durability."""
    __slots__ = ('_append', '_maximum')

    def __setattr__(self, name, value):
        if name in self.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed history authority cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self.__slots__:
            raise AttributeError('Installed history authority cannot be deleted.')
        object.__delattr__(self, name)

    @_private_constructor
    def __init__(self, *, writer: HistoryEventWriter, max_identifier_characters: int):
        if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
            raise ValueError('Attempt history identifier bound is required.')
        try:
            self._append = _capture(writer,'append_attempt_event',('event',))
        except Exception:
            raise ValueError('Required attempt history writer is not installed.') from None
        self._maximum = max_identifier_characters

    def record(self, *, event: CorrelatedAttemptEvent) -> AttemptEventAcknowledgment:
        try:
            original = _event_identity(event,self._maximum)
            try:
                acknowledgment = self._append(event=event)
            except Exception as error:
                if _event_identity(event,self._maximum) != original:
                    raise AttemptHistoryDenied('History event was corrupted during write.') from None
                if isinstance(error, AttemptHistoryDenied):
                    raise AttemptHistoryDenied('History writer explicitly denied the event.') from None
                raise AttemptHistoryUnavailable('History write outcome uncertain; reconcile.') from None
            if _event_identity(event,self._maximum) != original:
                raise AttemptHistoryDenied('History event was corrupted during write.')
            if type(acknowledgment) is not AttemptEventAcknowledgment:
                raise AttemptHistoryDenied('History acknowledgment is malformed.')
            if (_id(acknowledgment.event_ref,self._maximum) != original[0]
                    or _id(acknowledgment.request_ref,self._maximum) != original[1]):
                raise AttemptHistoryDenied('History acknowledgment has foreign identity.')
            _id(acknowledgment.receipt_ref,self._maximum)
            return acknowledgment
        except (AttemptHistoryDenied,AttemptHistoryUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc = AttemptHistoryDenied('History contract malformed.')
            _strip(exc)
            raise exc from None


class AuthorizedRegradeCustody:
    """Read-only regrade lineage. Never mutates historical scores or invokes physical attempt claim."""
    __slots__ = ('_authorize','_maximum')

    def __setattr__(self, name, value):
        if name in self.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed history authority cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self.__slots__:
            raise AttributeError('Installed history authority cannot be deleted.')
        object.__delattr__(self, name)

    @_private_constructor
    def __init__(self, *, source: RegradeAuthorizationSource, max_identifier_characters: int):
        if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
            raise ValueError('Regrade identifier bound is required.')
        try:
            self._authorize = _capture(source,'resolve_authorized_regrade',('prior_result_ref',))
        except Exception:
            raise ValueError('Regrade authorization source missing.') from None
        self._maximum = max_identifier_characters

    def resolve(self, *, prior_result_ref: str) -> AuthorizedRegrade:
        try:
            prior = _id(prior_result_ref,self._maximum)
            try:
                grant = self._authorize(prior_result_ref=prior)
            except AttemptHistoryDenied:
                raise AttemptHistoryDenied('Regrade authority explicitly denied the grant.') from None
            except Exception:
                raise AttemptHistoryUnavailable('Regrade approval unavailable.') from None
            if type(grant) is not AuthorizedRegrade:
                raise AttemptHistoryDenied('Regrade authority returned malformed grant.')
            if (_id(grant.approval_ref,self._maximum) == ''
                    or _id(grant.predecessor_result_ref,self._maximum) != prior):
                raise AttemptHistoryDenied('Regrade predecessor does not match.')
            old = _scope(grant.predecessor_scope,self._maximum)
            new = _scope(grant.new_scope,self._maximum)
            _id(grant.new_request_ref,self._maximum)
            if (old.grading_run_id == new.grading_run_id
                    or old.tenant_ref != new.tenant_ref
                    or old.submission_ref != new.submission_ref
                    or old.exam_ref != new.exam_ref
                    or old.question_id != new.question_id):
                raise AttemptHistoryDenied('Regrade must be a new authorized run for the same subject.')
            # Academic/spec revisions need an owner policy, not guessed equivalence.
            return grant
        except (AttemptHistoryDenied,AttemptHistoryUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc = AttemptHistoryDenied('Regrade lineage is malformed.')
            _strip(exc)
            raise exc from None


class CorrelatedEventIssuer(Protocol):
    """Accountable event identity source; event refs must not be invented by engine."""
    def issue_correlated_event(self, *, request_ref: str, scope: ChoiceAdmissionScope,
                               stage: AttemptStage, effect: AttemptEffect,
                               attempt_id: str | None, reservation_ref: str | None,
                               result_ref: str | None,
                               predecessor_result_ref: str | None) -> CorrelatedAttemptEvent: ...


class CorrelatedHistoryRecorder:
    """Phase-to-event adapter with backend-issued identifiers and acknowledged writes."""
    __slots__=('_issue','_custody','_maximum')

    def __setattr__(self, name, value):
        if name in self.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed history authority cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self.__slots__:
            raise AttributeError('Installed history authority cannot be deleted.')
        object.__delattr__(self, name)

    @_private_constructor
    def __init__(self, *, issuer: CorrelatedEventIssuer, writer: HistoryEventWriter,
                 max_identifier_characters: int):
        if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
            raise ValueError('History identifier bound required.')
        try:
            self._issue=_capture(issuer,'issue_correlated_event',(
                'request_ref','scope','stage','effect','attempt_id',
                'reservation_ref','result_ref','predecessor_result_ref'))
            self._custody=AttemptHistoryCustody(
                writer=writer,max_identifier_characters=max_identifier_characters)
        except Exception:
            raise ValueError('History issuer/writer ports invalid.') from None
        self._maximum=max_identifier_characters

    def record_phase(self, *, request_ref: str, scope: ChoiceAdmissionScope,
                     stage: AttemptStage, effect: AttemptEffect,
                     attempt_id: str | None = None, reservation_ref: str | None = None,
                     result_ref: str | None = None,
                     predecessor_result_ref: str | None = None) -> AttemptEventAcknowledgment:
        try:
            if type(stage) is not AttemptStage or type(effect) is not AttemptEffect:
                raise AttemptHistoryDenied('Event stage/effect invalid.')
            ref=_id(request_ref,self._maximum)
            bound=_scope(scope,self._maximum)
            original_bound=_scope(bound,self._maximum)
            optional=[]
            for value in (attempt_id,reservation_ref,result_ref,predecessor_result_ref):
                optional.append(None if value is None else _id(value,self._maximum))
            expected=(ref,bound,stage,effect,*optional)
            try:
                event=self._issue(request_ref=ref,scope=bound,stage=stage,effect=effect,
                                  attempt_id=optional[0],reservation_ref=optional[1],
                                  result_ref=optional[2],predecessor_result_ref=optional[3])
            except Exception as error:
                try:
                    if _scope(bound,self._maximum) != original_bound:
                        raise AttemptHistoryDenied('Event issuer corrupted scope before exception.')
                except AttemptHistoryDenied:
                    raise
                except Exception:
                    raise AttemptHistoryDenied('Event issuer corrupted scope before exception.') from None
                if isinstance(error, AttemptHistoryDenied):
                    raise AttemptHistoryDenied('Event issuer explicitly denied the event.') from None
                raise AttemptHistoryUnavailable('Event identity issuer unavailable.') from None
            received=_event_identity(event,self._maximum)
            if _scope(bound,self._maximum) != original_bound:
                raise AttemptHistoryDenied('Event issuer corrupted the scope argument.')
            if received[1:] != expected:
                raise AttemptHistoryDenied('Issued event does not bind exact operation.')
            receipt=self._custody.record(event=event)
            if _event_identity(event,self._maximum) != received:
                raise AttemptHistoryDenied('Issued event changed during append.')
            return receipt
        except (AttemptHistoryDenied,AttemptHistoryUnavailable) as exc:
            _strip(exc)
            raise
        except Exception:
            exc=AttemptHistoryDenied('Event emission contract malformed.')
            _strip(exc)
            raise exc from None


    def emit_phase(self, *, request_ref: str, scope: ChoiceAdmissionScope,
                   stage: AttemptStage, effect: AttemptEffect,
                   attempt_id: str | None, reservation_ref: str | None,
                   result_ref: str | None,
                   predecessor_result_ref: str | None) -> AttemptEventAcknowledgment:
        """Strict installed callback signature; all lineage facts explicit."""
        return self.record_phase(request_ref=request_ref,scope=scope,
            stage=stage,effect=effect,attempt_id=attempt_id,
            reservation_ref=reservation_ref,result_ref=result_ref,
            predecessor_result_ref=predecessor_result_ref)


class RegradeScopedAttemptClaimRequestIssuer:
    """Enforce backend-issued new-run/regrade identity BEFORE the physical attempt claim.

    A regrade grant is read from an installed authenticated authority via
    AuthorizedRegradeCustody, not made by the grader or caller. The owner of
    the physical-attempt backend must still enforce uniqueness and immutable history.
    """
    __slots__=('_identify','_scope','_request_ref','_prior_ref','_approval_ref','_maximum')

    def __setattr__(self, name, value):
        if name in self.__slots__:
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise AttributeError('Installed history authority cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self.__slots__:
            raise AttributeError('Installed history authority cannot be deleted.')
        object.__delattr__(self, name)

    @_private_constructor
    def __init__(self, *, grant: AuthorizedRegrade, issuer: object,
                 max_identifier_characters: int):
        from grading.integration.attempt_authority import _request_snapshot
        if type(grant) is not AuthorizedRegrade or type(max_identifier_characters) is not int or max_identifier_characters <= 0:
            raise AttemptHistoryDenied('A validated regrade grant and bounds are required.')
        try:
            old=_scope(grant.predecessor_scope,max_identifier_characters)
            new=_scope(grant.new_scope,max_identifier_characters)
            if (old.grading_run_id == new.grading_run_id or old.tenant_ref != new.tenant_ref
                    or old.submission_ref != new.submission_ref
                    or old.exam_ref != new.exam_ref or old.question_id != new.question_id):
                raise AttemptHistoryDenied('Regrade scopes do not preserve authorized history.')
            self._scope=new
            self._request_ref=_id(grant.new_request_ref,max_identifier_characters)
            self._prior_ref=_id(grant.predecessor_result_ref,max_identifier_characters)
            self._approval_ref=_id(grant.approval_ref,max_identifier_characters)
            self._identify=_capture(issuer,'identify_reservation_request',(
                'scope','family','runtime_id','runtime_version',
                'implementation_ref','eligibility_policy_id','eligibility_policy_version'))
            self._maximum=max_identifier_characters
        except AttemptHistoryDenied:
            raise
        except Exception:
            raise AttemptHistoryDenied('Regrade grading-attempt authority configuration invalid.') from None

    def identify_reservation_request(self, *, scope: ChoiceAdmissionScope,
                                     family: str, runtime_id: str,
                                     runtime_version: str, implementation_ref: str,
                                     eligibility_policy_id: str,
                                     eligibility_policy_version: int) -> object:
        from grading.integration.attempt_authority import _request_snapshot
        try:
            try:
                supplied = _scope(scope, self._maximum)
                if supplied != self._scope:
                    raise AttemptHistoryDenied('grading attempted wrong regrade grading-run identity.')
                # An independently detached primitive-validated scope must remain
                # identical to the object *actually passed* to the installed issuer.
                admitted_scope = _scope(supplied, self._maximum)
                try:
                    returned = self._identify(scope=supplied, family=family,
                        runtime_id=runtime_id, runtime_version=runtime_version,
                        implementation_ref=implementation_ref,
                        eligibility_policy_id=eligibility_policy_id,
                        eligibility_policy_version=eligibility_policy_version)
                finally:
                    # Check on both successful and exceptional callback exits,
                    # before allowing any later physical attempt claim.
                    try:
                        if _scope(supplied, self._maximum) != admitted_scope:
                            raise AttemptHistoryDenied(
                                'grading-attempt regrade issuer changed admitted new-run scope.')
                    except AttemptHistoryDenied:
                        raise
                    except Exception:
                        raise AttemptHistoryDenied(
                            'grading-attempt regrade issuer corrupted admitted new-run scope.') from None
                try:
                    values = _request_snapshot(returned, self._maximum)
                except Exception:
                    raise AttemptHistoryDenied('Regrade grading-attempt returned an invalid request.') from None
                if (values[0] != self._scope or values[1] != self._request_ref
                        or values[8] != self._prior_ref or values[9] != self._approval_ref):
                    raise AttemptHistoryDenied('grading-attempt regrade grant does not bind backend request.')
                return returned
            except AttemptHistoryDenied:
                raise
            except Exception:
                raise AttemptHistoryUnavailable('Regrade request issuance unavailable.') from None
        except (AttemptHistoryDenied, AttemptHistoryUnavailable) as exc:
            # Public port method, not just the evaluator invocation containing invoker,
            # must not retain confidential backend or ambient error graphs.
            _strip(exc)
            raise


def establish_authorized_regrade_history(*, source: RegradeAuthorizationSource,
                                         prior_result_ref: str,
                                         issuer: CorrelatedEventIssuer,
                                         writer: HistoryEventWriter,
                                         max_identifier_characters: int) -> AuthorizedRegrade:
    """Backend-issued regrade + recorded new-run link, without starting physical attempt claim.

    This creates no scoring result or physical attempt; the caller must then
    install RegradeScopedAttemptClaimRequestIssuer and use paper execution integrity admitted new-run request.
    """
    try:
        grant=AuthorizedRegradeCustody(
            source=source,max_identifier_characters=max_identifier_characters,
        ).resolve(prior_result_ref=prior_result_ref)
        # Capture the entire validated grant into independent contract values.
        # Do not return the issuer-owned object after a mutable writer callback.
        original = (_id(grant.approval_ref,max_identifier_characters),
                    _id(grant.predecessor_result_ref,max_identifier_characters),
                    _scope(grant.predecessor_scope,max_identifier_characters),
                    _scope(grant.new_scope,max_identifier_characters),
                    _id(grant.new_request_ref,max_identifier_characters))
        recorder=CorrelatedHistoryRecorder(
            issuer=issuer,writer=writer,
            max_identifier_characters=max_identifier_characters)
        try:
            recorder.record_phase(request_ref=original[4],
                scope=original[3],stage=AttemptStage.REGRADE,
                effect=AttemptEffect.CONFIRMED,
                predecessor_result_ref=original[1])
        finally:
            try:
                current=(_id(grant.approval_ref,max_identifier_characters),
                         _id(grant.predecessor_result_ref,max_identifier_characters),
                         _scope(grant.predecessor_scope,max_identifier_characters),
                         _scope(grant.new_scope,max_identifier_characters),
                         _id(grant.new_request_ref,max_identifier_characters))
                if current != original:
                    raise AttemptHistoryDenied('Regrade grant changed after recorded authorization.')
            except AttemptHistoryDenied:
                raise
            except Exception:
                raise AttemptHistoryDenied('Regrade grant was corrupted during event write.') from None
        return AuthorizedRegrade(*original)
    except (AttemptHistoryDenied, AttemptHistoryUnavailable) as exc:
        _strip(exc)
        raise
    except Exception:
        exc = AttemptHistoryDenied('Regrade history could not be validated.')
        _strip(exc)
        raise exc from None
