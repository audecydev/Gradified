"""original physical attempt claim-effect authorization: causal adversarial tests, no external credentials."""
from dataclasses import replace

import pytest

from grading.integration.evaluator_invocation import AttemptReservation
from grading.integration.direct_provider_route import DirectEffectDecision
from grading.providers.semantic_replay import direct_text_semantic_request_fingerprint
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_direct_provider_route_connected import install
from tests.integration.test_production_paper_operations import _root
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind


def unissued():
    cas, plan, _, physical, _, _, _, _, _ = connected('DIRECT')
    executor = cas._custody._executor
    route, source, sender, writer = install(executor, plan, 'FIRST')
    full = executor._resolve(plan=plan)
    op=full.operations[0]
    grant=source.grants[('Q1','FIRST')]
    prepared=op.evaluator.prepare_request(authority=op.authority,
        evidence=full.evidence.evidence,execution_context=full.context,
        evaluation_attempt_id=op.evaluation_attempt_id)
    assert direct_text_semantic_request_fingerprint(prepared)==grant.request_sha256
    return route, sender, writer, physical, full, plan, op, grant, prepared


def forged(scope, index):
    return AttemptReservation(scope=scope, attempt_id='FAKE-ATT-'+str(index),
        reservation_ref='FAKE-RES-'+str(index),family='DIRECT',
        runtime_id='RUNTIME',runtime_version='V1',implementation_ref='IMPL',
        eligibility_policy_id='POLICY',eligibility_policy_version=1,
        request_ref='FAKE-REQUEST-'+str(index))


def test_forged_structural_f25_denied_without_vendor_or_accounting():
    route,sender,writer,physical,full,plan,op,grant,prepared=unissued()
    bound=route.bind_attempt(approved=grant,plan=plan,evaluator=op.evaluator,
        reservation=forged(full.scopes[0],1),prepared_request=prepared)
    with pytest.raises(ValueError, match='grading-attempt effect denied'):
        bound._provider.evaluate(request=prepared)
    assert physical.claims==0 and not sender.dispatched and not writer.events


def test_two_unissued_bindings_do_not_create_two_effects():
    route,sender,writer,physical,full,plan,op,grant,prepared=unissued()
    for i in (1,2):
        bound=route.bind_attempt(approved=grant,plan=plan,evaluator=op.evaluator,
            reservation=forged(full.scopes[0],i),prepared_request=prepared)
        with pytest.raises(ValueError):
            bound._provider.evaluate(request=prepared)
    assert physical.claims==0 and not sender.dispatched and not writer.events


def test_foreign_tenant_reservation_rejected_before_issuer_and_effect():
    route,sender,writer,physical,full,plan,op,grant,prepared=unissued()
    with pytest.raises(ValueError,match='foreign to original'):
        route.bind_attempt(approved=grant,plan=plan,evaluator=op.evaluator,
            reservation=forged(replace(full.scopes[0],tenant_ref='FOREIGN-TENANT'),3),
            prepared_request=prepared)
    assert physical.claims==0 and not sender.dispatched and not writer.events


@pytest.mark.parametrize('decision',[DirectEffectDecision.DENIED, DirectEffectDecision.INDETERMINATE])
def test_issued_attempt_with_revoked_or_unknown_effect_disposition_never_sends(decision):
    cas,plan,_,physical,_,f25,_,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    route._authorize.__self__.forced=decision
    lifecycle=ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and store.commits==0
    assert sender.dispatched==[] and writer.events==[]


def test_repeat_effect_after_genuine_issued_attempt_is_denied():
    cas,plan,_,physical,_,f25,_,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and len(sender.dispatched)==len(writer.events)==1
    original=physical.last_reservation
    with pytest.raises(ValueError,match='already attempted'):
        route.consume_issued_effect(source.grants[('Q1','FIRST')],original)
    assert len(sender.dispatched)==len(writer.events)==1


def test_effect_authority_is_required_at_route_installation():
    from grading.integration.direct_provider_route import ProductionDirectProviderRoute
    route,*_=unissued()
    with pytest.raises(TypeError):
        ProductionDirectProviderRoute(source=object(),sender=object(),accounting=object(),
            max_identifier_characters=128,max_questions=10,
            max_request_bytes=1000,max_response_bytes=1000,sender_ref='SENDER')


def test_forged_denial_does_not_poison_later_genuine_claim_of_same_route():
    cas,plan,_,physical,_,f25,_,store,conditional=connected('DIRECT')
    executor=cas._custody._executor
    route,source,sender,writer=install(executor,plan,'FIRST')
    full=executor._resolve(plan=plan)
    op=full.operations[0]
    grant=source.grants[('Q1','FIRST')]
    with pytest.raises(ValueError):
        route.consume_issued_effect(grant, forged(full.scopes[0],8))
    assert physical.claims==0
    lifecycle=ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    result=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and len(sender.dispatched)==len(writer.events)==1


def test_issuer_callback_replaces_sender_after_f25_no_dispatch():
    cas,plan,_,physical,_,f25,_,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    owner=route._authorize.__self__
    initial_sender=route._deliver
    def substitute(_):
        object.__setattr__(route, '_deliver', lambda *, dispatch: (_ for _ in ()).throw(RuntimeError('FORGED')))
    owner.on_authorize=substitute
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and store.commits==0
    assert sender.dispatched==[] and writer.events==[]


def test_concurrent_bindings_cannot_consume_one_original_provider_event_twice():
    from threading import Barrier, Thread
    cas,plan,_,physical,_,f25,_,store,conditional=connected('DIRECT')
    executor=cas._custody._executor
    first,source,sender,writer=install(executor,plan,'FIRST')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    assert root.execute(request=plan.request,kind=PaperOperationKind.FIRST).execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1
    route,source,second_sender,second_writer=install(executor,plan,'FIRST')
    claimed=physical.last_reservation
    original_grant=source.grants[('Q1','FIRST')]
    start=Barrier(3)
    outcomes=[]
    def run():
        start.wait()
        try:
            route.consume_issued_effect(original_grant,claimed)
            outcomes.append('AUTHORIZED')
        except ValueError:
            outcomes.append('DENIED')
    threads=[Thread(target=run),Thread(target=run)]
    for t in threads:t.start()
    start.wait()
    for t in threads:t.join(timeout=5)
    assert all(not t.is_alive() for t in threads)
    assert sorted(outcomes)==['AUTHORIZED','DENIED']
    assert second_sender.dispatched==[] and second_writer.events==[]
