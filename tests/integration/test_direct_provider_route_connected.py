"""Qualified synthetic backend and canonical sender: engine contract, not vendor truth."""
from dataclasses import replace

import pytest

from grading.integration.direct_provider_route import (
    IssuedDirectProviderRoute, ProductionDirectProviderRoute,
    DirectEffectRequest, DirectEffectResponse, DirectEffectDecision,
)
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.paper_family_evaluation import DirectQuestionEvaluation
from grading.providers.canonical_transport import CanonicalProviderReply
from grading.providers.attempt_accounting import ProviderAccountingReceipt
from grading.providers.semantic_replay import direct_text_semantic_request_fingerprint
from tests.integration.test_direct_text_semantic_evaluator_regression import _provider_response


class RouteSource:
    def __init__(self, grants):
        self.grants=grants
        self.calls=[]
        self.revoked=False
        self.revoke_on_read=None
    def read_current_direct_route(self, *, plan, question_id, purpose):
        self.calls.append((question_id,purpose))
        if self.revoke_on_read==len(self.calls): self.revoked=True
        if self.revoked:
            return None
        return self.grants[(question_id,purpose)]


class CanonicalSender:
    def __init__(self):
        self.dispatched=[]
        self.fail=False
    def deliver(self, *, dispatch):
        self.dispatched.append(dispatch)
        if self.fail: raise RuntimeError('lost vendor acknowledgment')
        id=dispatch.identity
        return CanonicalProviderReply(dispatch.dispatch_ref,id.operation_ref,id.event_ref,
            id.logical_evaluation_ref,id.attempt_id,id.request_ref,dispatch.request_sha256,
            id.provider_id,id.model_id,id.configuration_ref,_provider_response())


class Accounting:
    def __init__(self): self.events=[]
    def record_outcome(self, *, event):
        self.events.append(event)
        return ProviderAccountingReceipt(event.identity.event_ref,event.identity.operation_ref,event.status)


class SyntheticIssuedEffectOwner:
    """Connected fixture ONLY. Reads the simulated attempt ledger, not request shape.

    This is not authentication, durable CAS, or external vendor conformance.
    """
    def __init__(self, executor):
        self.executor=executor
        self.lock=__import__('threading').Lock()
        self.consumed=set()
        self.forced=None
        self.calls=0
        self.on_authorize=None

    def consume_issued_direct_effect(self, *, request):
        self.calls+=1
        if type(request) is not DirectEffectRequest:
            raise ValueError('Not an original physical claim')
        res=request.reservation
        if self.on_authorize is not None:
            self.on_authorize(request)
        conditional=self.executor._attempts._joint_effect._claim.__self__
        if hasattr(conditional, 'backend'):
            original=conditional.backend.claimed.get(res.request_ref)
            original=None if original is None else original.reservation
        elif hasattr(conditional, 'atomic'):
            # RETRY's conditional claim uses the separate authorized retry claim physical store.
            physical = conditional.atomic.physical
            # An indexed multi-question fixture has one authoritative entry
            # per request. A missing key is NOT permission to borrow the
            # legacy last-reservation pointer for another request.
            if hasattr(physical, "reservations"):
                ledger = physical.reservations
                original = ledger.get(res.request_ref) if type(ledger) is dict else None
            else:
                # Compatibility only with genuine legacy single-reservation
                # synthetic stores that never supported indexed issuance.
                original = physical.last_reservation
        else:
            original=None
        with self.lock:
            key=(request.grant.operation_ref,request.grant.event_ref,
                 request.grant.logical_evaluation_ref)
            if original != res:
                # Synthetic attempt ledger is authoritative only for this fixture.
                return DirectEffectResponse(request, DirectEffectDecision.NOT_ISSUED)
            if self.forced is not None or key in self.consumed:
                return DirectEffectResponse(request, self.forced or DirectEffectDecision.DENIED)
            self.consumed.add(key)
            return DirectEffectResponse(request, DirectEffectDecision.AUTHORIZED)


def install(executor, plan, purpose):
    # Test-only, explicitly synthetic issuer. Production integration MUST
    # supply its own authenticated versioned issuer and vendor-qualified sender.
    paper=executor._resolve(plan=plan)
    grants={}
    for op in paper.operations:
        if type(op) is not DirectQuestionEvaluation:
            continue
        evaluator=op.evaluator
        mock=evaluator._provider
        # Derive the fixture's exact canonical request using the unchanged
        # evaluator; this is *setup*, before the operation under test.
        evaluator.evaluate(authority=op.authority,evidence=paper.evidence.evidence,
            execution_context=paper.context,evaluation_attempt_id=op.evaluation_attempt_id)
        request=mock.requests.pop()
        digest=direct_text_semantic_request_fingerprint(request)
        qid=op.authority.question_id
        grants[(qid,purpose)]=IssuedDirectProviderRoute(plan,qid,purpose,
            'CANONICAL-'+qid,'REV-1','SCHOOL-ISSUER',
            evaluator._evaluator_metadata.evaluator_id,evaluator._evaluator_metadata.version,
            'VENDOR','MODEL','CONFIG','SENDER',''+digest,
            'PROVIDER-OP-'+qid,'PROVIDER-EVENT-'+qid,'EVALUATION-'+qid)
    source=RouteSource(grants)
    sender=CanonicalSender()
    accounting=Accounting()
    route=ProductionDirectProviderRoute(source=source,sender=sender,accounting=accounting,
        effect_authority=SyntheticIssuedEffectOwner(executor),
        max_identifier_characters=128,max_questions=10,
        max_request_bytes=100000,max_response_bytes=100000,sender_ref='SENDER')
    # Existing cross-domain fixture constructs its executor first. Production
    # installers instead pass direct_route=route to the executor constructor.
    object.__setattr__(executor,'_direct_route',route)
    return route,source,sender,accounting


def test_qualified_first_source_issued_attempt_dispatch_and_accounting():
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
    from tests.integration.test_production_paper_operations import _root
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    result=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED, result.execution
    assert physical.claims==1 and store.commits==1 and conditional.contacts==1
    assert len(sender.dispatched)==len(writer.events)==1
    assert sender.dispatched[0].identity.attempt_id=='BACKEND-ATT-1'
    assert writer.events[0].identity==sender.dispatched[0].identity
    assert writer.events[0].status=='RESULT_RETURNED'
    assert old.requests==[]
    assert not result.authorizes_publication


def test_route_revocation_before_f25_no_claim_and_no_provider_effect():
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from tests.integration.test_production_paper_operations import _root
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    _,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    source.revoked=True
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state.value!='CAS_ACKNOWLEDGED'
    assert physical.claims==0 and store.commits==0 and sender.dispatched==[] and writer.events==[]


def test_unknown_vendor_ack_never_blind_resends():
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from tests.integration.test_production_paper_operations import _root
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    _,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    sender.fail=True
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state.value!='CAS_ACKNOWLEDGED'
    assert physical.claims==1 and store.commits==0
    assert len(sender.dispatched)==1
    assert len(writer.events)==1 and writer.events[0].status=='INDETERMINATE'


def test_source_approved_request_hash_must_match_real_post_f25_bytes():
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from tests.integration.test_production_paper_operations import _root
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    _,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    old_grant=source.grants[('Q1','FIRST')]
    source.grants[('Q1','FIRST')]=replace(old_grant, request_sha256='0'*64)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert outcome.execution.state.value!='CAS_ACKNOWLEDGED'
    assert physical.claims==0 and sender.dispatched==[] and writer.events==[] and store.commits==0


def test_sender_installation_mismatch_fails_before_any_f25_claim():
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from tests.integration.test_production_paper_operations import _root
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    _,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    source.grants[('Q1','FIRST')]=replace(source.grants[('Q1','FIRST')],sender_ref='FOREIGN')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert outcome.execution.state.value!='CAS_ACKNOWLEDGED'
    assert physical.claims==0 and not sender.dispatched and not writer.events and store.commits==0


def test_authorized_direct_retry_uses_claimed_new_attempt_and_original_c4e():
    from tests.integration.test_family_retry_accounting import connected_family_retry
    from tests.integration.test_production_paper_operations import _root
    from grading.integration.paper_retry_grading import GradedRetryState
    retry,plan,physical,_,store,_,old=connected_family_retry('DIRECT')
    _,source,sender,writer=install(retry._executor,plan,'RETRY')
    root,_=_root(retry=retry,plan=plan,kinds=(PaperOperationKind.RETRY,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.RETRY)
    assert out.execution.state is GradedRetryState.CAS_ACKNOWLEDGED
    assert len(sender.dispatched)==len(writer.events)==1
    assert sender.dispatched[0].identity.attempt_id==out.execution.physical.claimed[0].reservation.attempt_id
    assert physical.claims==1 and store.commits==1 and old.requests==[]


def test_authorized_direct_regrade_uses_actual_new_f25_and_scored_cas():
    from tests.integration.test_family_first_scored_cas import connected_regrade
    from tests.integration.test_production_paper_operations import _root
    from grading.integration.paper_lifecycle import PaperLifecycleState
    lifecycle,plan,physical,backend,f25,old,storage,conditional,prior,f57=connected_regrade()
    _,source,sender,writer=install(lifecycle._cas._custody._executor,plan,'REGRADE')
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.REGRADE,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.REGRADE)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert len(sender.dispatched)==len(writer.events)==1
    assert physical.claims==1 and storage.commits==2
    assert sender.dispatched[0].identity.attempt_id==out.execution.cas.custody.outcome.completed[0].reservation.attempt_id


def test_source_revoked_after_issued_f25_before_real_provider_contact():
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from tests.integration.test_production_paper_operations import _root
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    _,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    # Preflight and last pre-claim read pass; the first post-claim read fails.
    source.revoke_on_read=3
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    result=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert result.execution.state.value!='CAS_ACKNOWLEDGED'
    assert physical.claims==1 and store.commits==0
    assert sender.dispatched==[] and writer.events==[] and old.requests==[]


def test_retry_request_keyed_f25_ledger_missing_key_cannot_borrow_last_reservation():
    """A valid *different* reservation is not issuance for this request.

    This is an adversarial synthetic-issuer oracle regression, not a claim of
    authentic external physical attempt claim/backend enforcement.
    """
    from tests.integration.test_family_retry_accounting import connected_family_retry
    from tests.integration.test_production_paper_operations import _root

    retry, plan, physical, _, store, _, old_provider = connected_family_retry('MIXED')
    route, source, sender, accounting = install(retry._executor, plan, 'RETRY')
    effect = route._authorize.__self__
    ledger = retry._executor._attempts._joint_effect._claim.__self__.atomic.physical
    observed = []

    def drop_issued_key(request):
        assert len(ledger.reservations) == 2
        assert ledger.reservations.pop(request.reservation.request_ref) == request.reservation
        # Stale last-reservation pointer still matches the direct Q1 request.
        # It must not override the now-missing authoritative request-keyed entry.
        ledger.last_reservation = request.reservation
        assert len(ledger.reservations) == 1
        observed.append(request.reservation.request_ref)

    effect.on_authorize = drop_issued_key
    root, _ = _root(retry=retry, plan=plan, kinds=(PaperOperationKind.RETRY,))
    out = root.execute(request=plan.request, kind=PaperOperationKind.RETRY)
    assert observed
    assert out.execution.state.name != 'CAS_ACKNOWLEDGED'
    assert out.execution.cas is None or out.execution.cas.state.name != 'COMMITTED'
    assert physical.claims == len(plan.questions)
    assert store.commits == 0
    assert sender.dispatched == [] and accounting.events == []
