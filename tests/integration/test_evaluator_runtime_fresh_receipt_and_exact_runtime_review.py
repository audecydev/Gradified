"""source integrity checks locally-provable positive physical attempt claim permit and exact runtime admission."""
from dataclasses import replace
import pytest
from grading.integration.academic_claim_binding import AcademicallyBoundClaim
from grading.integration.joint_effect_authority import (ConditionalEffectClaimResponse,
    EffectDecision, JointEffectAdmission, JointAuthoritySnapshot)
from tests.integration.test_joint_effect_time_authority_contract import components as _components, ConditionalFixtureOwner

@pytest.fixture
def components():
    return _components.__wrapped__()

class StrSubclass(str):
    pass

@pytest.mark.parametrize('field,value',[
    ('eligibility_policy_version',True), ('eligibility_policy_version',1.0),
    ('family',StrSubclass('CHOICE')), ('runtime_id',StrSubclass('EXACT-ID'))])
def test_g5_rejects_runtime_type_coercion(components,field,value):
    _,request,_=components
    runtime=request.authority.runtime
    if field=='runtime_id': value=StrSubclass(runtime.runtime_id)
    with pytest.raises(ValueError):
        JointAuthoritySnapshot(request.authority.academic,replace(runtime,**{field:value}),128,10)

@pytest.mark.parametrize('change',('missing_reservation','foreign_request_ref','empty_attempt_id'))
def test_g5_fresh_malformed_reservation_cannot_authorize_evaluation(components,change):
    fixture,request,_=components
    class Malformed(ConditionalFixtureOwner):
        def claim_if_current(self, *, request):
            prior=fixture.q1_claim
            if change=='missing_reservation':
                forged=replace(prior,reservation=None)
            elif change=='foreign_request_ref':
                forged=replace(prior,reservation=replace(prior.reservation,request_ref='WRONG-REQUEST'))
            else:
                forged=replace(prior,reservation=replace(prior.reservation,attempt_id=''))
            self.claim_effects.append(request)
            return ConditionalEffectClaimResponse(request,EffectDecision.COMMITTED,
                                          AcademicallyBoundClaim(request.preparation,forged))
    owner=Malformed(fixture.q1_claim,fixture.academic_revision,fixture.runtime_revision)
    answer=JointEffectAdmission(owner=owner).claim(request=request)
    assert answer.state is EffectDecision.UNKNOWN
    assert answer.bound_claim is None and len(owner.claim_effects)==1
    assert answer.request.authority.academic.original_request == request.authority.academic.original_request

def test_g5_genuine_fresh_reservation_positive(components):
    owner,request,_=components
    assert JointEffectAdmission(owner=owner).claim(request=request).state is EffectDecision.COMMITTED
