"""Verify evaluator runtime callbacks preserve original-operation custody and source integrity."""
from dataclasses import replace
from grading.integration.joint_effect_authority import JointEffectAdmission, EffectDecision
from tests.integration.test_joint_effect_time_authority_contract import components, ConditionalFixtureOwner


def prepared():
    return components.__wrapped__()


def test_control_real_bound_f25_and_synthetic_cas_fixture():
    owner, request, cas = prepared()
    gate=JointEffectAdmission(owner=owner)
    assert gate.claim(request=request).state is EffectDecision.COMMITTED
    assert gate.commit(request=cas).state is EffectDecision.COMMITTED


def test_mutated_f25_approval_original_identity_must_survive_unknown():
    owner, request, cas=prepared()
    original_approval=request.authority.runtime.approval_ref
    class Mutating(ConditionalFixtureOwner):
        def claim_if_current(self, *, request):
            reply=super().claim_if_current(request=request)
            object.__setattr__(request.authority.runtime,'approval_ref','REPLACED-APPROVAL-REF')
            return reply
    actual=Mutating(owner.q1_claim,owner.academic_revision,owner.runtime_revision)
    result=JointEffectAdmission(owner=actual).claim(request=request)
    assert result.state is EffectDecision.UNKNOWN
    assert len(actual.claim_effects)==1
    assert result.request.authority.runtime.approval_ref==original_approval, 'UNKNOWN lost original approved-runtime identity'


def test_mutated_cas_approval_original_identity_must_survive_unknown():
    owner, request, cas=prepared()
    original_approval=cas.authority.runtime.approval_ref
    class Mutating(ConditionalFixtureOwner):
        def commit_if_current(self, *, request):
            reply=super().commit_if_current(request=request)
            object.__setattr__(request.authority.runtime,'approval_ref','REPLACED-APPROVAL-REF')
            return reply
    actual=Mutating(owner.q1_claim,owner.academic_revision,owner.runtime_revision)
    result=JointEffectAdmission(owner=actual).commit(request=cas)
    assert result.state is EffectDecision.UNKNOWN
    assert len(actual.cas_effects)==1
    assert result.request.authority.runtime.approval_ref==original_approval, 'UNKNOWN lost original scored-CAS approved runtime identity'


def test_mutated_f25_binding_original_identity_must_survive_unknown():
    owner, request, cas=prepared()
    original_binding=request.preparation.binding_ref
    class Mutating(ConditionalFixtureOwner):
        def claim_if_current(self, *, request):
            reply=super().claim_if_current(request=request)
            object.__setattr__(request.preparation,'binding_ref','REPLACED-BINDING')
            return reply
    actual=Mutating(owner.q1_claim,owner.academic_revision,owner.runtime_revision)
    result=JointEffectAdmission(owner=actual).claim(request=request)
    assert result.state is EffectDecision.UNKNOWN
    assert len(actual.claim_effects)==1
    assert result.request.preparation.binding_ref==original_binding, 'UNKNOWN lost original physical binding identity'
