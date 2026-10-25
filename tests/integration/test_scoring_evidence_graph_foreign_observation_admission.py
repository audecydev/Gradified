"""Verify fake observations are rejected during constituent evidence admission."""
from dataclasses import replace
import pytest
from test_result_constituents_provenance import example
from grading.risk import RiskObservation
from grading.risk_policy import RecommendationReason
from grading.integration.result_constituents import (
    compose_nonpublishing_constituents, CandidateConstituentsDenied,
)

class ForeignEquality:
    def __init__(self):
        self.calls = 0
    def __eq__(self, other):
        self.calls += 1
        return True


def genuine_candidate():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    return compose_nonpublishing_constituents(
        execution=execution, evidence=evidence, policy_query=query, recommender=recommender,
    )


def test_f53_direct_constructor_rejects_foreign_observation_before_comparison():
    original = genuine_candidate()
    foreign = ForeignEquality()
    altered = replace(original.review_recommendation, observations=(foreign,))
    with pytest.raises(CandidateConstituentsDenied):
        replace(original, review_recommendation=altered)
    assert foreign.calls == 0, 'foreign equality should not be evaluated'


def test_f53_rejects_subclassed_risk_observation_spoofing_equality():
    original = genuine_candidate()
    class SubclassedObservation(RiskObservation):
        calls = 0
        def __eq__(self, other):
            SubclassedObservation.calls += 1
            return True
    expected = original.risk_observations.observations[0]
    foreign = SubclassedObservation(expected.code, 'FOREIGN-QUESTION', expected.evidence_block_id, None)
    altered = replace(original.review_recommendation, observations=(foreign,))
    with pytest.raises(CandidateConstituentsDenied):
        replace(original, review_recommendation=altered)
    assert SubclassedObservation.calls == 0, 'subclass equality must not execute'


def test_f53_rejects_mutated_exact_risk_record_with_foreign_field_equality():
    original = genuine_candidate()
    observation = replace(original.review_recommendation.observations[0])
    foreign = ForeignEquality()
    # Simulates an installed callback corrupting a shared frozen record, without
    # reusing or monkeypatching any Gradified implementation.
    object.__setattr__(observation, 'question_id', foreign)
    altered = replace(original.review_recommendation, observations=(observation,))
    with pytest.raises(CandidateConstituentsDenied):
        replace(original, review_recommendation=altered)
    assert foreign.calls == 0


def test_f53_genuine_candidate_control_is_accepted():
    original = genuine_candidate()
    copy = replace(original)
    assert copy.review_recommendation.observations == original.risk_observations.observations
    assert copy.official_result is False

@pytest.mark.parametrize('reason', [RecommendationReason.POLICY_REVOKED,
                                   RecommendationReason.POLICY_UNAVAILABLE])
def test_f53_empty_risk_must_not_claim_unobserved_policy_lookup(reason):
    execution, evidence, query, recommender, reader = example(unknown_ocr=False)
    candidate = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                     policy_query=query, recommender=recommender)
    assert reader.calls == 0
    assert candidate.review_recommendation.reason is RecommendationReason.NO_POSITIVE_ELIGIBILITY
    forged = replace(candidate.review_recommendation, reason=reason)
    with pytest.raises(CandidateConstituentsDenied):
        replace(candidate, review_recommendation=forged)
