"""Independent admission falsification at new source integrity checks joint-authority constructor."""
from dataclasses import replace
import pytest
from grading.integration.joint_effect_authority import (
  JointAuthoritySnapshot, ConditionalEffectClaim, ConditionalScoredCAS,
  GradingEffectKind, JointEffectAdmission, EffectDecision,
)
from tests.integration.test_joint_effect_time_authority_contract import components


def setup():
 return components.__wrapped__()


def test_positive_control_valid_approved_runtime():
 owner, claim, cas=setup()
 assert JointEffectAdmission(owner=owner).claim(request=claim).state is EffectDecision.COMMITTED


@pytest.mark.parametrize('field,forgery', [
 ('capability_ref', None),
 ('approved_modalities', ('VALID',None)),
 ('approved_modalities', ('DUPLICATE','DUPLICATE')),
 ])
def test_malformed_approved_runtime_must_not_cross_effect(field,forgery):
 owner, claim, cas=setup()
 runtime=replace(claim.authority.runtime, **{field:forgery})
 with pytest.raises(ValueError):
  JointAuthoritySnapshot(claim.authority.academic, runtime, 128, 10)
 assert owner.claim_effects == []
