"""Source-issued DIRECT route admission, joined to the actual physical attempt.

The engine checks scope, current issuer approval, canonical request identity,
installed sender, physical attempt and original-accounting correlation. It
cannot authenticate a school issuer or prove external vendor wire/billing:
those are mandatory production adapter-conformance responsibilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from enum import Enum
from threading import Lock

from grading.integration.execution_eligibility import _capture
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.paper_family_evaluation import _admitted_values
from grading.integration.paper_execution_correlation import _plan
from grading.integration.evaluator_invocation import AttemptReservation, _reservation_copy
from grading.providers.attempt_accounting import (
    ProviderAttemptIdentity, OneShotDirectTextAccountingProvider,
    _capture_provider_method, _id,
)
from grading.providers.canonical_transport import CanonicalDirectTextTransport
from grading.providers.semantic_replay import direct_text_semantic_request_fingerprint
from grading.semantic_evaluator import DirectTextSemanticEvaluator, DirectTextSemanticRequest


@dataclass(frozen=True, slots=True, repr=False)
class IssuedDirectProviderRoute:
    """Exact versioned source assertion; not a bearer token or signed proof."""
    plan: AdmittedPaperPlan
    question_id: str
    purpose: str
    route_ref: str
    route_revision: str
    issuer_ref: str
    evaluator_id: str
    evaluator_version: str
    provider_id: str
    model_id: str
    configuration_ref: str
    sender_ref: str
    request_sha256: str
    operation_ref: str
    event_ref: str
    logical_evaluation_ref: str


def _route(value, plan, question_id, purpose, evaluator, maximum, questions):
    if type(value) is not IssuedDirectProviderRoute or type(evaluator) is not DirectTextSemanticEvaluator:
        raise ValueError('Unqualified DIRECT route source.')
    for name in ('question_id', 'purpose', 'route_ref', 'route_revision', 'issuer_ref',
                 'evaluator_id', 'evaluator_version', 'provider_id', 'model_id',
                 'configuration_ref', 'sender_ref', 'operation_ref', 'event_ref',
                 'logical_evaluation_ref'):
        _id(getattr(value, name), maximum, name)
    digest=value.request_sha256
    if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Route requires an exact approved canonical request fingerprint.')
    if (_plan(value.plan,questions,maximum)!=_plan(plan,questions,maximum)
            or value.question_id!=question_id or value.purpose!=purpose
            or purpose not in ('FIRST','REGRADE','RETRY')
            or not any(q.request.question_id==question_id and q.family=='DIRECT'
                       for q in plan.questions)
            or value.evaluator_id!=evaluator._evaluator_metadata.evaluator_id
            or value.evaluator_version!=evaluator._evaluator_metadata.version):
        raise ValueError('DIRECT route does not match admitted paper and evaluator.')
    return IssuedDirectProviderRoute(_plan(value.plan, questions, maximum),
        *(getattr(value,f) for f in IssuedDirectProviderRoute.__dataclass_fields__ if f!='plan'))


class DirectEffectDecision(str, Enum):
    AUTHORIZED = 'AUTHORIZED'
    DENIED = 'DENIED'
    # Authoritative proof that no original physical attempt reservation was ever issued.
    # Unlike DENIED for an issued attempt, it cannot consume physical custody.
    NOT_ISSUED = 'NOT_ISSUED'
    INDETERMINATE = 'INDETERMINATE'


@dataclass(frozen=True, slots=True, repr=False)
class DirectEffectRequest:
    """Original route, issued physical attempt, and exact effect identity.

    Never a bearer permit. The installed authority must atomically prove physical attempt claim
    issuance, tenant/scope/purpose, current authorization and first consumption.
    """
    grant: IssuedDirectProviderRoute
    reservation: AttemptReservation


@dataclass(frozen=True, slots=True, repr=False)
class DirectEffectResponse:
    request: DirectEffectRequest
    decision: DirectEffectDecision


@dataclass(frozen=True, slots=True)
class _PreparedModelAnswer:
    grading_spec_ref: object
    question_id: str
    content: str


@dataclass(frozen=True, slots=True)
class _PreparedModelAnswerSource:
    """No post-claim callback to a mutable model-answer store."""
    answer: _PreparedModelAnswer

    def resolve_model_answer(self, *, grading_spec_ref, question_id):
        if (type(question_id) is not str or question_id != self.answer.question_id
                or grading_spec_ref != self.answer.grading_spec_ref):
            raise ValueError('Prepared DIRECT source belongs to a different original question.')
        return self.answer


def _evaluator_installation(evaluator):
    if type(evaluator) is not DirectTextSemanticEvaluator:
        raise ValueError('Foreign DIRECT evaluator.')
    return (evaluator._provider, evaluator._model_answer_source,
            _admitted_values(evaluator._limits),
            _admitted_values(evaluator._evaluator_metadata))


def _require_evaluator_installation(evaluator, original):
    if (type(evaluator) is not DirectTextSemanticEvaluator
            or evaluator._provider is not original[0]
            or evaluator._model_answer_source is not original[1]
            or _admitted_values(evaluator._limits) != original[2]
            or _admitted_values(evaluator._evaluator_metadata) != original[3]):
        raise ValueError('DIRECT original evaluator installation changed.')


class _BoundByteSender:
    __slots__=('_call',)
    def __init__(self, call): object.__setattr__(self,'_call',call)
    def deliver(self, *, dispatch): return self._call(dispatch=dispatch)


class _BoundAccountingWriter:
    __slots__=('_call',)
    def __init__(self, call): object.__setattr__(self,'_call',call)
    def record_outcome(self, *, event): return self._call(event=event)


class _AuthorizedDirectProvider:
    __slots__=('_route','_grant','_reservation','_plan','_evaluator','_original_evaluator','_lock','_used')
    def __init__(self, route, grant, reservation, plan, evaluator):
        self._route=route
        self._grant=grant
        self._reservation=reservation
        self._plan=plan
        self._evaluator=evaluator
        self._original_evaluator=_evaluator_installation(evaluator)
        self._lock=Lock()
        self._used=False

    def evaluate(self, *, request: DirectTextSemanticRequest) -> bytes:
        with self._lock:
            if self._used:
                raise ValueError('DIRECT approved provider contact already consumed.')
            self._used=True
        route=self._route
        grant=self._grant
        original = capture_direct_route_installation(route)
        if (type(request) is not DirectTextSemanticRequest
                or direct_text_semantic_request_fingerprint(request)!=grant.request_sha256
                or request.question_id!=grant.question_id):
            raise ValueError('DIRECT canonical request is not source-approved.')
        # Re-read current approval immediately before provider/accounting effect.
        # Revocation after physical attempt claim yields UNKNOWN; never repeat the physical claim.
        route.require_current(grant, self._plan, self._evaluator)
        require_direct_route_installation(route, original)
        _require_evaluator_installation(self._evaluator, self._original_evaluator)
        reservation=self._reservation
        # Compare-and-consume MUST occur at the physical sender boundary. The
        # reservation's dataclass shape cannot establish physical attempt claim provenance.
        # Locally fence repeated attempts at one operation/event even if a
        # deployed backend adapter violates its atomicity contract.
        route.consume_issued_effect(grant, reservation)
        require_direct_route_installation(route, original)
        _require_evaluator_installation(self._evaluator, self._original_evaluator)
        identity=ProviderAttemptIdentity(grant.operation_ref,grant.event_ref,
            grant.logical_evaluation_ref,reservation.attempt_id,reservation.request_ref,
            grant.provider_id,grant.model_id,grant.configuration_ref,grant.request_sha256)
        transport=CanonicalDirectTextTransport(identity=identity,
            dispatch_ref=grant.route_ref,sender=_BoundByteSender(route._deliver),
            max_identifier_characters=route._limit,
            max_request_bytes=route._max_request,
            max_response_bytes=route._max_response)
        provider=OneShotDirectTextAccountingProvider(identity=identity,transport=transport,
            sink=_BoundAccountingWriter(route._write),
            max_identifier_characters=route._limit,
            max_raw_response_bytes=route._max_response)
        return provider.evaluate(request=request)


class ProductionDirectProviderRoute:
    """One qualified installation; no dynamic source-chosen provider callback."""
    __slots__=('_read','_deliver','_write','_authorize','_effect_lock','_consumed',
               '_limit','_questions','_max_request','_max_response','_sender_ref','_installed')
    def __init__(self, *, source, sender, accounting, effect_authority,
                 max_identifier_characters: int, max_questions: int,
                 max_request_bytes: int, max_response_bytes: int,
                 sender_ref: str):
        if (type(max_identifier_characters) is not int or not 0<max_identifier_characters<=4096
                or type(max_questions) is not int or not 0<max_questions<=1000
                or type(max_request_bytes) is not int or not 0<max_request_bytes<=50_000_000
                or type(max_response_bytes) is not int or not 0<max_response_bytes<=50_000_000):
            raise ValueError('Finite DIRECT provider route limits required.')
        declared_sender=_id(sender_ref,max_identifier_characters,'installed canonical sender')
        object.__setattr__(self,'_sender_ref',declared_sender)
        object.__setattr__(self,'_read',_capture(source,'read_current_direct_route',('plan','question_id','purpose')))
        object.__setattr__(self,'_deliver',_capture_provider_method(sender,'deliver',('dispatch',)))
        object.__setattr__(self,'_write',_capture_provider_method(accounting,'record_outcome',('event',)))
        object.__setattr__(self,'_authorize',_capture(effect_authority,'consume_issued_direct_effect',('request',)))
        object.__setattr__(self,'_effect_lock',Lock())
        object.__setattr__(self,'_consumed',set())
        object.__setattr__(self,'_limit',max_identifier_characters)
        object.__setattr__(self,'_questions',max_questions)
        object.__setattr__(self,'_max_request',max_request_bytes)
        object.__setattr__(self,'_max_response',max_response_bytes)
        # Capture the effect-bearing functions at construction, not at first
        # use: an approval reader must not be able to redefine a route's owner.
        object.__setattr__(self,'_installed', (self._read, self._deliver, self._write, self._authorize,
            self._sender_ref, self._limit, self._questions,
            self._max_request, self._max_response))

    def __setattr__(self,name,value):
        raise AttributeError('Installed DIRECT provider route cannot be replaced.')

    def preflight(self, *, plan: AdmittedPaperPlan, question_id: str,
                  purpose: str, evaluator: DirectTextSemanticEvaluator) -> IssuedDirectProviderRoute:
        try:
            plan=_plan(plan,self._questions,self._limit)
            _id(question_id,self._limit,'question')
            if type(purpose) is not str or purpose not in ('FIRST','REGRADE','RETRY'):
                raise ValueError('Foreign purpose.')
            issued=self._read(plan=plan,question_id=question_id,purpose=purpose)
            approved=_route(issued,plan,question_id,purpose,evaluator,self._limit,self._questions)
            if approved.sender_ref!=self._sender_ref:
                raise ValueError('Wrong installed canonical sender.')
            return approved
        except Exception:
            raise ValueError('Current source-issued DIRECT route not admitted.') from None

    def require_current(self, approved: IssuedDirectProviderRoute, plan: AdmittedPaperPlan,
                        evaluator: DirectTextSemanticEvaluator) -> None:
        try:
            current=_route(self._read(plan=_plan(plan,self._questions,self._limit),
                question_id=approved.question_id,purpose=approved.purpose),
                plan,approved.question_id,approved.purpose,evaluator,self._limit,self._questions)
            if current.sender_ref!=self._sender_ref or current!=approved:
                raise ValueError('Changed approval.')
        except Exception:
            raise ValueError('DIRECT route revoked, changed or unavailable.') from None

    def consume_issued_effect(self, approved: IssuedDirectProviderRoute,
                              reservation: AttemptReservation) -> None:
        """One attempt-bound physical authorization, never a read-only approval.

        Backend owns issuer verification, revocation, expiry, cross-worker
        single-consumption and durable UNKNOWN recovery. An unclear response
        is consumed, not retried. Local fencing cannot replace backend CAS.
        """
        # Deterministic local errors cannot consume a not-yet-contacted event.
        # The fence must, however, precede any external effect-authority call.
        if type(approved) is not IssuedDirectProviderRoute:
            raise ValueError('Unqualified original DIRECT route.')
        original_installation=capture_direct_route_installation(self)
        original=_reservation_copy(reservation,expected=reservation,maximum=self._limit)
        # The effect owner is independently callable. Verify the same original
        # paper/question custody as bind_attempt BEFORE fencing the event or
        # contacting an authority whose response may be indeterminate.
        plan=_plan(approved.plan,self._questions,self._limit)
        request_original=plan.request
        question=next((q for q in plan.questions
            if q.request.question_id==approved.question_id and q.family=='DIRECT'),None)
        scope=original.scope
        if (approved.purpose not in ('FIRST','REGRADE','RETRY')
                or question is None or original.family!='DIRECT'
                or original.request_ref is None
                or scope.question_id!=approved.question_id
                or scope.actor_ref!=plan.actor_ref
                or scope.tenant_ref!=request_original.tenant_ref
                or scope.session_ref!=request_original.session_ref
                or scope.grading_run_id!=request_original.grading_run_id
                or scope.submission_ref!=request_original.submission_ref
                or scope.exam_ref!=request_original.exam_ref
                or scope.grading_spec_ref!=request_original.grading_spec_ref
                or scope.evidence_scope_ref!=question.evidence_scope_ref
                or scope.source_artifact_ref!=question.source_artifact_ref
                or scope.source_revision!=question.source_revision
                or scope.ocr_provenance!=question.provenance_ref):
            raise ValueError('DIRECT reservation is foreign to the approved original question.')
        request=DirectEffectRequest(approved,original)
        # Preserve the pre-contact original, not the reference which a callback
        # could mutate and then echo as an apparently matching response.
        baseline=deepcopy(request)
        require_direct_route_installation(self, original_installation)
        key=(approved.operation_ref,approved.event_ref,approved.logical_evaluation_ref)
        with self._effect_lock:
            if key in self._consumed:
                raise ValueError('DIRECT original provider effect already attempted.')
            # Consume BEFORE the external callback; failure may be a lost ACK.
            self._consumed.add(key)
        try:
            response=self._authorize(request=request)
            if (type(response) is not DirectEffectResponse
                    or type(response.request) is not DirectEffectRequest
                    or type(response.decision) is not DirectEffectDecision
                    or response.request != baseline or request != baseline):
                raise ValueError('Malformed or mutated original grading-attempt effect decision.')
            require_direct_route_installation(self, original_installation)
            if (_reservation_copy(reservation, expected=original, maximum=self._limit) != original
                    or request != baseline):
                raise ValueError('Physical attempt changed during dispatch authorization.')
            if response.decision is DirectEffectDecision.NOT_ISSUED:
                # Only a trusted proof of *non-issuance* may release the local
                # key so that a later real claim can use this event identity.
                # Denial/revocation of a genuinely ISSUED claim is not that proof.
                with self._effect_lock:
                    self._consumed.discard(key)
                raise ValueError('Original grading attempt never issued.')
            if response.decision is DirectEffectDecision.DENIED:
                # An issued physical claim is already consumed, even when
                # revocation blocks its provider effect. No automatic retry.
                raise ValueError('Original issued grading-attempt effect denied.')
            if response.decision is not DirectEffectDecision.AUTHORIZED:
                raise ValueError('Original grading-attempt effect unknown or unavailable.')
        except Exception:
            raise ValueError('DIRECT grading-attempt effect denied or indeterminate; no dispatch.') from None

    def bind_attempt(self, *, approved: IssuedDirectProviderRoute,
                     plan: AdmittedPaperPlan, evaluator: DirectTextSemanticEvaluator,
                     reservation: AttemptReservation,
                     prepared_request: DirectTextSemanticRequest) -> DirectTextSemanticEvaluator:
        if (type(reservation) is not AttemptReservation
                or reservation.family!='DIRECT'
                or reservation.scope.question_id!=approved.question_id
                or reservation.request_ref is None):
            raise ValueError('DIRECT route requires real issued grading attempt.')
        reservation=_reservation_copy(reservation, expected=reservation, maximum=self._limit)
        original=plan.request
        question=next((q for q in plan.questions
            if q.request.question_id==approved.question_id and q.family=='DIRECT'),None)
        scope=reservation.scope
        if (question is None or scope.actor_ref!=plan.actor_ref
                or scope.tenant_ref!=original.tenant_ref
                or scope.session_ref!=original.session_ref
                or scope.grading_run_id!=original.grading_run_id
                or scope.submission_ref!=original.submission_ref
                or scope.exam_ref!=original.exam_ref
                or scope.grading_spec_ref!=original.grading_spec_ref
                or scope.evidence_scope_ref!=question.evidence_scope_ref
                or scope.source_artifact_ref!=question.source_artifact_ref
                or scope.source_revision!=question.source_revision
                or scope.ocr_provenance!=question.provenance_ref):
            raise ValueError('DIRECT physical attempt is foreign to original admitted question.')
        if (type(prepared_request) is not DirectTextSemanticRequest
                or prepared_request.question_id != approved.question_id
                or direct_text_semantic_request_fingerprint(prepared_request) != approved.request_sha256):
            raise ValueError('Prepared original DIRECT request is not issuer-approved.')
        original = capture_direct_route_installation(self)
        evaluator_original = _evaluator_installation(evaluator)
        self.require_current(approved,plan,evaluator)
        require_direct_route_installation(self, original)
        _require_evaluator_installation(evaluator, evaluator_original)
        # The genuine model-answer reader was contacted before physical attempt claim. Neither a
        # second materialization nor a different reader is allowed after physical attempt claim.
        prepared_source = _PreparedModelAnswerSource(_PreparedModelAnswer(
            plan.request.grading_spec_ref,
            prepared_request.question_id, prepared_request.model_answer_text))
        return DirectTextSemanticEvaluator(model_answer_source=prepared_source,
            provider=_AuthorizedDirectProvider(self,approved,reservation,plan,evaluator),
            limits=evaluator._limits,evaluator_metadata=evaluator._evaluator_metadata)


def capture_direct_route_installation(route: ProductionDirectProviderRoute | None) -> tuple | None:
    """Freeze the actual owner and effect callbacks before untrusted source reads.

    Identity compares on callbacks are intentional: a matching sender_ref or
    source-issued approval cannot authorize a replaced callable. Numeric and
    string configuration fields are exact built-ins, never foreign __eq__.
    """
    if route is None:
        return None
    if type(route) is not ProductionDirectProviderRoute:
        raise ValueError('Foreign installed DIRECT route.')
    saved = route._installed
    if type(saved) is not tuple or len(saved) != 9:
        raise ValueError('Missing original DIRECT route installation.')
    original = (route, *saved)
    require_direct_route_installation(route, original)
    return original


def require_direct_route_installation(route, original) -> None:
    """Reject substitution without executing any foreign comparison method."""
    if original is None:
        if route is not None:
            raise ValueError('DIRECT route changed after installation snapshot.')
        return
    if type(original) is not tuple or len(original) != 10 or route is not original[0] or \
            type(route) is not ProductionDirectProviderRoute:
        raise ValueError('DIRECT route owner changed after installation snapshot.')
    installed = route._installed
    if (type(installed) is not tuple or len(installed) != 9
            or any(installed[i] is not original[i + 1] for i in range(4))):
        raise ValueError('DIRECT original installation record changed.')
    if (route._read is not original[1] or route._deliver is not original[2]
            or route._write is not original[3]
            or route._authorize is not original[4]):
        raise ValueError('DIRECT source, sender or accounting operation replaced.')
    for live, baseline, exact_type in (
            (route._sender_ref, original[5], str),
            (route._limit, original[6], int),
            (route._questions, original[7], int),
            (route._max_request, original[8], int),
            (route._max_response, original[9], int)):
        if type(live) is not exact_type or live != baseline:
            raise ValueError('DIRECT sender identity or installation limits changed.')
    if any(type(installed[i]) is not type(original[i + 1])
           or installed[i] != original[i + 1] for i in range(4, 9)):
        raise ValueError('DIRECT original configuration record changed.')
