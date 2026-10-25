"""Verify that legal workflow transitions alone do not authorize a new physical retry."""
from dataclasses import replace
from grading.contracts.job_state import GradingJobState
from grading.integration.paper_retry_claim import RetryClaimState
from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from tests.integration.test_authorized_retry_claim import rig
from tests.integration.test_scored_paper_retry_handoff import make


def test_wrong_purpose_edge_cannot_claim_original_or_new_paper():
    svc, plan, physical, authority, academic, atomic = rig()
    authority.approval = replace(authority.approval,
        source_state=GradingJobState.SCORING,
        target_state=GradingJobState.REVIEW_REQUIRED)
    observation = svc.claim(plan=plan)
    assert observation.state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert physical.claims == 0 and academic.prepares == 0 and atomic.calls == 0


def test_wrong_purpose_grant_cannot_reach_audit_read_on_fixed_history():
    gate, fixed, history, store, physical, unused_f25 = make()
    fixed.original = replace(history, authorization=replace(history.authorization,
        source_state=GradingJobState.SCORING,
        target_state=GradingJobState.REVIEW_REQUIRED))
    reads_before = store.reads
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == reads_before

import pytest
from grading.integration.retry_purpose_authorization import RetryPurposeTransitionPolicy, RETRY_CLAIM_PURPOSE
from grading.integration.paper_retry_claim import ProductionAuthorizedPaperRetry
from tests.integration.test_authorized_retry_claim import RETRY_PURPOSE

@pytest.mark.parametrize('field,value',(
    ('purpose_policy_id', 'UNRELATED-STAGE-POLICY'),
    ('purpose_policy_id', None),
    ('purpose_policy_version', 2),
    ('purpose_policy_version', True),
))
def test_wrong_stage_approval_identity_blocks_physical_effect(field,value):
    svc,plan,physical,authority,academic,atomic=rig()
    authority.approval=replace(authority.approval,**{field:value})
    assert svc.claim(plan=plan).state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)

@pytest.mark.parametrize('field,value',(
    ('purpose', 'AUDIT_ONLY'),
    ('approval_policy_version', 2),
    ('legal_policy_id', 'UNRELATED-LEGAL-POLICY'),
    ('permitted_edges', ((GradingJobState.SCORING,GradingJobState.REVIEW_REQUIRED),)),
    ('permitted_edges', ((GradingJobState.QUEUED,GradingJobState.GRADING),)*2),
    ('permitted_edges', ()),
))
def test_misinstalled_purpose_policy_denies_before_preparation(field,value):
    svc,plan,physical,authority,academic,atomic=rig()
    # The existing service has fixed installation. Install an independent
    # alternative only in the isolated fixture, before effects.
    alt=replace(RETRY_PURPOSE,**{field:value})
    svc2=ProductionAuthorizedPaperRetry(recovery=svc._recovery,
        retry_authority=authority,academic_store=academic,atomic_retry_store=atomic,
        legal_policy=svc._policy,max_identifier_characters=128,max_questions=10,
        retry_purpose_policy=alt)
    assert svc2.claim(plan=plan).state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)


def test_missing_independent_retry_purpose_admission_fails_closed():
    svc,plan,physical,authority,academic,atomic=rig()
    uninstalled=ProductionAuthorizedPaperRetry(recovery=svc._recovery,
        retry_authority=authority,academic_store=academic,atomic_retry_store=atomic,
        legal_policy=svc._policy,max_identifier_characters=128,max_questions=10)
    assert uninstalled.claim(plan=plan).state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)


def test_c5_missing_purpose_approval_rejects_before_current_cas_recovery():
    gate,fixed,history,store,physical,unused_f25=make()
    from grading.integration.scored_paper_promotion import ProductionPaperPromotion
    incomplete=ProductionPaperPromotion(original_source=fixed,
        audit_recovery=gate._audit,accounting=gate._accounting,
        legal_policy=gate._policy,max_identifier_characters=128,max_questions=10,
        retry_original_recovery=gate._retry_recovery)
    before=store.reads
    assert incomplete.assess().state is PaperHandoffEligibilityState.BLOCKED
    assert store.reads==before
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,1)
