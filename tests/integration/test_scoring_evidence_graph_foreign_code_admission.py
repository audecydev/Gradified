"""Adversarial regressions rejecting foreign code and unsafe constituent sources."""
from copy import deepcopy
from dataclasses import replace
import pytest
from grading.risk import RiskObservation, RiskObservationCode
from grading.risk_policy import PolicyRule, ReviewDisposition
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents,
)
from test_result_constituents_provenance import example


def candidate():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    return compose_nonpublishing_constituents(
        execution=execution, evidence=evidence, policy_query=query,
        recommender=recommender,
    )


class ForeignCode:
    def __eq__(self, other):
        return other is RiskObservationCode.OCR_CONFIDENCE_UNKNOWN
    def __hash__(self):
        return hash(RiskObservationCode.OCR_CONFIDENCE_UNKNOWN)
    def __repr__(self):
        return 'FOREIGN_CODE'


class AlwaysEqual:
    def __eq__(self, other):
        return True
    def __repr__(self):
        return 'FOREIGN_OBSERVATION'


def test_foreign_policy_code_cannot_be_admitted_via_equality():
    c = candidate()
    forged = PolicyRule(ForeignCode(), ReviewDisposition.HUMAN_REVIEW)
    review = replace(c.review_recommendation,
        effective_rules=(forged, c.review_recommendation.effective_rules[1]))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, review_recommendation=review)


def test_foreign_recommendation_observation_cannot_be_admitted_via_equality():
    c = candidate()
    review = replace(c.review_recommendation, observations=(AlwaysEqual(),))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, review_recommendation=review)


@pytest.mark.parametrize('field,value', [
    ('final_score', 'FOREIGN-SCORE'),
    ('rubric_ref', 'FOREIGN-RUBRIC'),
    ('stage_effects', ('FOREIGN-STAGE',)),
])
def test_mutated_question_score_nested_contract_refused(field, value):
    c = deepcopy(candidate())
    object.__setattr__(c.question_scores[0], field, value)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)


def test_mutated_paper_score_nested_final_score_refused():
    c = deepcopy(candidate())
    object.__setattr__(c.paper_score, 'final_score', 'FOREIGN-PAPER-SCORE')
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)


def test_control_original_candidate_remains_valid():
    c = candidate()
    assert replace(c) == c
    assert not c.official_result


def test_control_wrong_official_flag_rejected():
    c = candidate()
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, official_result=True)
