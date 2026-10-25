"""Adversarial DIRECT execution tests reject foreign original-operation scope and uncertain authority."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_direct_provider_route_connected import install
from tests.integration.test_direct_issued_effect_authority import forged
from tests.integration.test_production_paper_operations import _root


def arrange():
    cas,plan,_,physical,_,f25,_,store,_ = connected('DIRECT')
    executor=cas._custody._executor
    route,source,sender,writer=install(executor,plan,'FIRST')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    return root,plan,route,source,sender,writer,physical,store,executor


def test_foreign_tenant_scope_is_rejected_before_uncertain_effect_authority():
    root,plan,route,source,sender,writer,physical,store,executor=arrange()
    owner=route._authorize.__self__
    full=executor._resolve(plan=plan)
    foreign_scope=replace(full.scopes[0],tenant_ref='FOREIGN-TENANT')
    wrong=forged(foreign_scope,101)
    def lost_ack(_):
        raise RuntimeError('effect-owner transport timeout; no reliable decision')
    owner.on_authorize=lost_ack
    with pytest.raises(ValueError):
        route.consume_issued_effect(source.grants[('Q1','FIRST')],wrong)
    # This original tenant mismatch is known without a remote call.
    assert owner.calls==0, 'Foreign tenant reached effect authority, risking false UNKNOWN/one-use poisoning.'
    assert not route._consumed
    owner.on_authorize=None
    result=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and len(sender.dispatched)==len(writer.events)==1


def test_legitimate_first_positive_control():
    root,plan,route,source,sender,writer,physical,store,executor=arrange()
    result=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and len(sender.dispatched)==len(writer.events)==1

@pytest.mark.parametrize('field,foreign',[
    ('tenant_ref','FOREIGN-TENANT'),
    ('submission_ref','FOREIGN-SUBMISSION'),
    ('question_id','Q2-FOREIGN'),
])
def test_incompatible_scope_must_not_poison_valid_event(field,foreign):
    root,plan,route,source,sender,writer,physical,store,executor=arrange()
    owner=route._authorize.__self__
    full=executor._resolve(plan=plan)
    scope=replace(full.scopes[0], **{field:foreign})
    wrong=forged(scope,202)
    def unavailable(_):
        raise TimeoutError('synthetic authority timeout')
    owner.on_authorize=unavailable
    with pytest.raises(ValueError):
        route.consume_issued_effect(source.grants[('Q1','FIRST')],wrong)
    owner.on_authorize=None
    result=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED, (
        f'{field}: valid event poisoned by a definitely foreign reservation; '
        f'authority contacted {owner.calls} times, consumed={route._consumed}')
    assert physical.claims==1 and len(sender.dispatched)==1 and len(writer.events)==1

@pytest.mark.parametrize('field,foreign', [
    ('actor_ref','FOREIGN-ACTOR'),
    ('session_ref','FOREIGN-SESSION'),
    ('grading_run_id','FOREIGN-RUN'),
    ('exam_ref','FOREIGN-EXAM'),
    ('source_revision','FOREIGN-REVISION'),
    ('source_artifact_ref','FOREIGN-ARTIFACT'),
    ('evidence_scope_ref','FOREIGN-EVIDENCE'),
    ('ocr_provenance','FOREIGN-PROVENANCE'),
])
def test_entire_foreign_question_custody_rejected_before_external_authority(field,foreign):
    root,plan,route,source,sender,writer,physical,store,executor=arrange()
    owner=route._authorize.__self__
    valid=executor._resolve(plan=plan).scopes[0]
    foreign_scope=replace(valid,**{field:foreign})
    wrong=forged(foreign_scope,100)
    owner.on_authorize=lambda _: (_ for _ in ()).throw(TimeoutError('lost ack'))
    with pytest.raises(ValueError):
        route.consume_issued_effect(source.grants[('Q1','FIRST')],wrong)
    assert owner.calls == 0
    assert not route._consumed
    owner.on_authorize=None
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and len(sender.dispatched)==len(writer.events)==1
