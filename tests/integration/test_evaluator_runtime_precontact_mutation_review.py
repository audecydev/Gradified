"""Check source integrity checks effect owner refuses now-invalid runtime/CAS records before contact."""
import pytest
from grading.integration.joint_effect_authority import JointEffectAdmission,EffectDecision
from tests.integration.test_joint_effect_time_authority_contract import components


def test_valid_original_control():
    owner, claim, cas = components.__wrapped__()
    gate=JointEffectAdmission(owner=owner)
    assert gate.claim(request=claim).state is EffectDecision.COMMITTED
    assert gate.commit(request=cas).state is EffectDecision.COMMITTED


def test_post_construction_invalid_runtime_record_rejected_before_f25():
    owner, claim, cas=components.__wrapped__()
    object.__setattr__(claim.authority.runtime,'capability_ref',None)
    with pytest.raises(ValueError):
        JointEffectAdmission(owner=owner).claim(request=claim)
    assert not owner.claim_effects


def test_post_construction_invalid_cas_reference_rejected_before_cas():
    owner, claim, cas=components.__wrapped__()
    object.__setattr__(cas,'original_transaction_ref','')
    with pytest.raises(ValueError):
        JointEffectAdmission(owner=owner).commit(request=cas)
    assert not owner.cas_effects
