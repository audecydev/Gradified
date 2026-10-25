"""Verify nested evidence graphs and callback integrity using real scoring constructors."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from enum import Enum

import pytest

from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.contracts.result import RuleDecision, RuleType
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, _detached_signature,
    compose_nonpublishing_constituents,
)
from grading.risk_policy import RiskReviewRecommender
from test_result_constituents_provenance import example
from test_risk_policy_recommendations import current


def candidate():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    return compose_nonpublishing_constituents(
        execution=execution, evidence=evidence, policy_query=query, recommender=recommender)


@pytest.mark.parametrize('path,value', [
    ('criterion_level', object()),
    ('criterion_effect_amount', 'FOREIGN'),
    ('criterion_effect_decimal', Decimal('NaN')),
    ('rule_type', object()),
    ('rule_effect', 'FOREIGN'),
    ('stage', object()),
    ('stage_before', 'FOREIGN'),
    ('stage_source_rules', ('real', object())),
    ('profile', 'FOREIGN-PROFILE'),
    ('policy_semantics', 'FOREIGN-SEMANTICS'),
    ('rubric_version', -1),
    ('paper_profile', 'FOREIGN-PROFILE'),
    ('paper_decimal', Decimal('Infinity')),
])
def test_nested_unsafe_values_never_pass_public_constituent(path, value):
    c = deepcopy(candidate())
    question = c.question_scores[0]
    if path == 'criterion_level':
        object.__setattr__(question.criterion_effects[0], 'selected_level', value)
    elif path == 'criterion_effect_amount':
        object.__setattr__(question.criterion_effects[0], 'effective_contribution', value)
    elif path == 'criterion_effect_decimal':
        object.__setattr__(question.criterion_effects[0].base_contribution, '_value', value)
    elif path in ('rule_type', 'rule_effect'):
        rule = RuleDecision('R1', RuleType.CAP, False, None)
        object.__setattr__(question, 'rule_decisions', (rule,))
        if path == 'rule_type':
            object.__setattr__(rule, 'rule_type', value)
        else:
            object.__setattr__(rule, 'configured_effect', value)
    elif path == 'stage':
        object.__setattr__(question.stage_effects[0], 'stage', value)
    elif path == 'stage_before':
        object.__setattr__(question.stage_effects[0], 'before', value)
    elif path == 'stage_source_rules':
        object.__setattr__(question.stage_effects[0], 'source_rule_ids', value)
    elif path == 'profile':
        object.__setattr__(question, 'numeric_profile_version', value)
    elif path == 'policy_semantics':
        object.__setattr__(question.scoring_policy_ref, 'scoring_semantics_version', value)
    elif path == 'rubric_version':
        object.__setattr__(question.rubric_ref, 'version', value)
    elif path == 'paper_profile':
        object.__setattr__(c.paper_score, 'numeric_profile_version', value)
    elif path == 'paper_decimal':
        object.__setattr__(c.paper_score.final_score, '_value', value)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)


def test_noncanonical_raw_scoring_decimal_is_denied_not_rewritten():
    c = deepcopy(candidate())
    actual = c.paper_score.final_score
    object.__setattr__(actual, '_value', Decimal('1.00'))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)
    assert actual.as_decimal().as_tuple() == Decimal('1.00').as_tuple()


def test_wrong_nested_number_is_rejected_before_policy_reader_contact():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    object.__setattr__(execution.paper_score.question_results[0], 'final_score', 'BAD')
    class Reader:
        calls = 0
        def read_current(self, *, query):
            self.calls += 1
            return current(query)
    reader = Reader()
    recommender = RiskReviewRecommender(reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                            policy_query=query, recommender=recommender)
    assert reader.calls == 0


def test_enum_type_identity_distinguishes_same_named_classes():
    Left = Enum('Same', {'MEMBER': 'VALUE'})
    Right = Enum('Same', {'MEMBER': 'VALUE'})
    assert Left.__name__ == Right.__name__
    assert Left.MEMBER.name == Right.MEMBER.name
    assert _detached_signature(Left.MEMBER) != _detached_signature(Right.MEMBER)


def test_valid_nested_numeric_stays_unchanged_and_remains_nonofficial():
    c = candidate()
    verified = replace(c)
    # A validated copy now owns its score graph independently of the source.
    assert verified.paper_score is not c.paper_score
    assert verified.paper_score.final_score == c.paper_score.final_score
    assert verified.question_scores[0].numeric_profile_version == NUMERIC_PROFILE_VERSION
    assert not verified.official_result
