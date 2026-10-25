"""Verify effective evidence mapping, authority, and mutation scope during result-constituent admission."""
from dataclasses import replace
import pytest
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents,
)
from grading.risk_policy import (
    PolicyAuthorityState, PolicyRule, PolicyFactStatus, ReviewDisposition,
    RecommendationReason, RiskReviewRecommender,
)
from test_result_constituents_provenance import example
from test_risk_policy_recommendations import current
from grading.risk import RiskObservationCode


def candidate():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    result = compose_nonpublishing_constituents(
        execution=execution, evidence=evidence, policy_query=query,
        recommender=recommender)
    return result, reader


def test_snapshot_equals_mapping_read_not_unbound_version_alias():
    c, reader = candidate()
    assert reader.calls == 1
    assert c.review_recommendation.authority_state is PolicyAuthorityState.UNVERIFIED_EXTERNAL_AUTHORITY
    assert c.review_recommendation.effective_rules == (
        PolicyRule(RiskObservationCode.OCR_CONFIDENCE_UNKNOWN, ReviewDisposition.HUMAN_REVIEW),
        PolicyRule(RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED, ReviewDisposition.HUMAN_REVIEW),
    )
    assert c.review_recommendation.policy_version == 2
    assert not c.official_result


@pytest.mark.parametrize('change', [
    {'authority_state': 'VERIFIED'},
    {'reason': RecommendationReason.POLICY_UNAVAILABLE},
    {'disposition': ReviewDisposition.DEFERRED},
    {'effective_rules': ()},
    {'effective_rules': (PolicyRule(RiskObservationCode.OCR_CONFIDENCE_UNKNOWN,
                                   ReviewDisposition.SECOND_CHECK),
                         PolicyRule(RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED,
                                   ReviewDisposition.SECOND_CHECK))},
    {'policy_ref': ' FOREIGN '},
    {'approval_ref': None},
    {'issuer_ref': None},
    {'policy_version': True},
])
def test_public_result_rejects_forged_policy_evidence(change):
    c, _ = candidate()
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, review_recommendation=replace(c.review_recommendation, **change))


@pytest.mark.parametrize('field', ['grading_run_id', 'submission_ref', 'exam_ref', 'grading_spec_id'])
def test_public_result_rejects_noncanonical_identity(field):
    c, _ = candidate()
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, **{field: 'x'*257})


def test_public_result_rejects_changed_risk_observation_code():
    c, _ = candidate()
    orig = c.risk_observations.observations[0]
    bad = replace(orig, code=RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED,
                  evidence_block_id=None, criterion_id='FOREIGN-CRITERION')
    obs = replace(c.risk_observations, observations=(bad,))
    rec = replace(c.review_recommendation, observations=(bad,))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, risk_observations=obs, review_recommendation=rec)


def test_policy_reader_cannot_mutate_evidence_content_while_preserving_risk_flags():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    block = evidence.questions[0].blocks[0]
    old_content = block.content
    class Mutator:
        def read_current(self, *, query):
            object.__setattr__(block, 'content', 'MUTATED ANSWER')
            return current(query)
    try:
        recommender = RiskReviewRecommender(reader=Mutator(), issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
        with pytest.raises(CandidateConstituentsDenied):
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                policy_query=query, recommender=recommender)
    finally:
        object.__setattr__(block, 'content', old_content)


def test_no_risk_still_no_policy_read_and_no_authority():
    execution, evidence, query, recommender, reader = example(unknown_ocr=False)
    c = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                            policy_query=query, recommender=recommender)
    assert reader.calls == 0
    assert c.review_recommendation.effective_rules == ()
    assert c.review_recommendation.authority_state is PolicyAuthorityState.UNVERIFIED_EXTERNAL_AUTHORITY
    assert c.review_recommendation.reason is RecommendationReason.NO_POSITIVE_ELIGIBILITY
    assert not c.official_result
