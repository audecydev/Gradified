from dataclasses import replace
import pytest
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents
from grading.risk_policy import ReviewDisposition
from test_result_constituents_provenance import example


def candidate():
    e,ev,q,r,_=example(unknown_ocr=True)
    return compose_nonpublishing_constituents(execution=e,evidence=ev,policy_query=q,recommender=r)

@pytest.mark.parametrize('field', ['exam_ref','grading_spec_id','grading_spec_version'])
def test_reject_foreign_recommendation_authority_scope(field):
    c=candidate()
    changed = 'FOREIGN' if field!='grading_spec_version' else 99
    bad_query=replace(c.review_recommendation.query,**{field:changed})
    bad_recommendation=replace(c.review_recommendation,query=bad_query)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c,review_recommendation=bad_recommendation)

@pytest.mark.parametrize('state', ['AUTO_CANDIDATE', 'OFFICIAL'])
def test_reject_invalid_recommendation_disposition(state):
    c=candidate()
    bad=replace(c.review_recommendation, disposition=state)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c,review_recommendation=bad)

@pytest.mark.parametrize('field', ['grading_run_id','submission_ref'])
def test_reject_foreign_risk_observation_set_identity(field):
    c=candidate()
    bad=replace(c.risk_observations,**{field:'FOREIGN'})
    with pytest.raises(CandidateConstituentsDenied):
        replace(c,risk_observations=bad)

@pytest.mark.parametrize('field', ['schema_version','reason','policy_version'])
def test_reject_malformed_recommendation_field(field):
    c=candidate()
    bad=replace(c.review_recommendation,**{field: 'INVALID' if field!='policy_version' else True})
    with pytest.raises(CandidateConstituentsDenied):
        replace(c,review_recommendation=bad)


def test_reject_risk_question_outside_scored_question_scope():
    c=candidate()
    old=c.risk_observations.observations[0]
    bad_risk=replace(c.risk_observations, observations=(replace(old,question_id='OTHER-QUESTION'),))
    bad_review=replace(c.review_recommendation, observations=bad_risk.observations)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c,risk_observations=bad_risk,review_recommendation=bad_review)

def test_control_valid_factory_candidate_is_admitted():
    c=candidate()
    assert replace(c) == c

def test_control_official_true_is_denied():
    c=candidate()
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, official_result=True)
