"""Verify retry recovery cannot accept authority from another original operation."""
from dataclasses import replace
import pytest
from grading.integration.joint_effect_authority import ConditionalEffectClaim, GradingEffectKind
from tests.integration.test_joint_retry_connected_execution import connected_retry, ConditionalRetryFixture

@pytest.fixture
def sampled(monkeypatch):
    seen = []
    original = ConditionalRetryFixture.claim_if_current
    def observe(self, *, request):
        seen.append(request)
        return original(self, request=request)
    monkeypatch.setattr(ConditionalRetryFixture, 'claim_if_current', observe)
    grade,plan,physical,atomic,store,*_=connected_retry()
    outcome=grade.execute_and_commit(plan=plan)
    assert outcome.state.value=='CAS_ACKNOWLEDGED' and len(seen)==2
    assert physical.claims==2 and store.commits==1
    return seen[0]

def expect_blocked(original, *, recovery=None, grant=None):
    with pytest.raises(ValueError):
        ConditionalEffectClaim(original.authority,original.preparation, GradingEffectKind.RETRY_F25,
            original_retry=original.original_retry if recovery is None else recovery,
            retry_grant=original.retry_grant if grant is None else grant)

def test_negative_recovery_read_claims_different_original_request(sampled):
    old=sampled.original_retry
    q=old.details.questions[0]
    assert q.request_ref is not None
    changed=replace(old, details=replace(old.details,questions=(replace(q,request_ref='FOREIGN-OLD-REQUEST'),*old.details.questions[1:])))
    expect_blocked(sampled,recovery=changed)

def test_negative_retry_issued_original_request_refs_foreign(sampled):
    grant=sampled.retry_grant
    assert grant.original_request_refs[0] is not None
    changed=replace(grant,original_request_refs=('FOREIGN-OLD-REQUEST',*grant.original_request_refs[1:]))
    expect_blocked(sampled,grant=changed)

def test_negative_retry_purpose_version_malformed_bool(sampled):
    changed=replace(sampled.retry_grant,purpose_policy_version=True)
    expect_blocked(sampled,grant=changed)

def test_negative_retry_other_question_request_is_foreign(sampled):
    grant=sampled.retry_grant
    q=grant.new_requests[1]
    bad_q=replace(q, scope=replace(q.scope, question_id='FOREIGN-Q2'))
    changed=replace(grant,new_requests=(grant.new_requests[0],bad_q))
    expect_blocked(sampled,grant=changed)

def test_positive_unmodified_claim_remains_valid(sampled):
    r=ConditionalEffectClaim(sampled.authority,sampled.preparation,GradingEffectKind.RETRY_F25,
                         original_retry=sampled.original_retry,retry_grant=sampled.retry_grant)
    assert r.retry_grant is sampled.retry_grant

def test_negative_foreign_original_read_reaches_effect_owner(sampled):
    """The forbidden boundary is contact with the conditional physical attempt claim owner."""
    from grading.integration.joint_effect_authority import (
        JointEffectAdmission, ConditionalEffectClaimResponse, EffectDecision,
    )
    source=sampled.original_retry
    changed=replace(source, details=replace(source.details, questions=(
        replace(source.details.questions[0], request_ref='FOREIGN-OLD-REQUEST'),
        *source.details.questions[1:],
    )))
    contacted=[]
    class Spy:
        def claim_if_current(self, *, request):
            contacted.append(request)
            return ConditionalEffectClaimResponse(request, EffectDecision.REJECTED)
        def commit_if_current(self, *, request):
            raise AssertionError('no scored CAS should be contacted')
    try:
        unsafe=ConditionalEffectClaim(sampled.authority,sampled.preparation,
            GradingEffectKind.RETRY_F25,original_retry=changed,retry_grant=sampled.retry_grant)
    except ValueError:
        pass
    else:
        JointEffectAdmission(owner=Spy()).claim(request=unsafe)
    assert contacted == [], 'Malformed original-recovery relation reached physical owner'

def test_negative_retry_grant_issuer_approval_differs_from_joint_academic(sampled):
    grant=sampled.retry_grant
    foreign=replace(grant,issued_paper=replace(grant.issued_paper,approval_ref='FOREIGN-ISSUER-APPROVAL'))
    expect_blocked(sampled,grant=foreign)

def test_negative_retry_grant_scoring_differs_from_joint_academic(sampled):
    grant=sampled.retry_grant
    foreign_ref=replace(grant.scoring.grading_spec_ref,id='FOREIGN-GRADING-SPEC')
    foreign=replace(grant,scoring=replace(grant.scoring,grading_spec_ref=foreign_ref))
    expect_blocked(sampled,grant=foreign)

def test_negative_not_contacted_recovery_must_not_invent_request_reference(sampled):
    recovered=sampled.original_retry
    question=recovered.details.questions[1]
    assert question.state.value=='NOT_CONTACTED' and question.request_ref is None
    forged=replace(recovered,details=replace(recovered.details,questions=(
        recovered.details.questions[0],replace(question,request_ref='INVENTED-NEVER-CONTACTED'))))
    expect_blocked(sampled,recovery=forged)
