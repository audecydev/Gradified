"""Verify constituent admission enforces criterion identity and explicit bounds."""
from dataclasses import replace
from copy import deepcopy
import pytest
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents,
)
from test_result_constituents_provenance import example


def baseline():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    return compose_nonpublishing_constituents(
        execution=execution,evidence=evidence,policy_query=query,recommender=recommender)


def test_valid_control():
    result = baseline()
    assert replace(result).official_result is False


@pytest.mark.parametrize('field,value', [
    ('criterion_id', ''),
    ('criterion_id', '  '),
    ('selected_level', ''),
    ('blocking_dependency_rule_ids', ('',)),
])
def test_invalid_criterion_identity_rejected(field, value):
    c = deepcopy(baseline())
    ce = c.paper_score.question_results[0].criterion_effects[0]
    object.__setattr__(ce, field, value)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)

@pytest.mark.parametrize('field,value', [
    ('source_rule_ids', ('',)),
    ('source_rule_ids', (' ',)),
])
def test_invalid_stage_rule_identity_rejected(field, value):
    c = deepcopy(baseline())
    se = c.paper_score.question_results[0].stage_effects[0]
    object.__setattr__(se, field, value)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)

@pytest.mark.parametrize('kind', ['question_above_max', 'paper_above_max','paper_reverse_bounds'])
def test_impossible_numerical_score_bounds_rejected(kind):
    from grading.contracts.scoring_decimal import ScoringDecimal
    c = deepcopy(baseline())
    q = c.paper_score.question_results[0]
    high=ScoringDecimal.from_raw('999')
    if kind == 'question_above_max':
        object.__setattr__(q, 'final_score', high)
    elif kind == 'paper_above_max':
        object.__setattr__(c.paper_score, 'final_score', high)
    else:
        object.__setattr__(c.paper_score, 'minimum_score', high)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)
