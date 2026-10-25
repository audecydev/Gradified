"""criterion scoring/scoring aggregation numerical lineage re-admission at the nonofficial second-pass evidence admission boundary."""
from copy import deepcopy
from dataclasses import replace
import pytest

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents,
)
from test_result_constituents_provenance import example


def _candidate():
    ex, ev, query, recommender, _ = example(unknown_ocr=True)
    return compose_nonpublishing_constituents(execution=ex, evidence=ev,
                                               policy_query=query, recommender=recommender)


@pytest.mark.parametrize('case', (
    'paper_aggregate_substitution', 'question_base_subtotal_substitution',
    'question_stage_chain_disconnected', 'question_wrong_final_stage',
    'invalid_rule_decision_id',
))
def test_invalid_numerical_lineage_rejected_on_direct_public_admission(case):
    c = deepcopy(_candidate())
    q = c.paper_score.question_results[0]
    if case == 'paper_aggregate_substitution':
        # A valid, in-range paper total still contradicts its original question.
        object.__setattr__(c.paper_score, 'final_score', ScoringDecimal.from_raw('4'))
    elif case == 'question_base_subtotal_substitution':
        object.__setattr__(q, 'base_subtotal', ScoringDecimal.from_raw('4'))
    elif case == 'question_stage_chain_disconnected':
        object.__setattr__(q.stage_effects[1], 'before', ScoringDecimal.from_raw('4'))
    elif case == 'question_wrong_final_stage':
        object.__setattr__(q.stage_effects[-1], 'after', ScoringDecimal.from_raw('4'))
    else:
        from grading.contracts.result import RuleDecision, RuleType
        object.__setattr__(q, 'rule_decisions', (
            RuleDecision(' ', RuleType.GATE, False, None),
        ))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)


def test_bad_paper_total_rejected_before_policy_reader():
    ex, ev, query, recommender, reader = example(unknown_ocr=True)
    object.__setattr__(ex.paper_score, 'final_score', ScoringDecimal.from_raw('4'))
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=ex, evidence=ev,
                                            policy_query=query, recommender=recommender)
    assert reader.calls == 0


def test_public_direct_constituent_error_does_not_retain_private_context():
    c = deepcopy(_candidate())
    effect = c.paper_score.question_results[0].criterion_effects[0]
    sentinel = 'PRIVATE_CRITERION_SCOPE_TOKEN'
    object.__setattr__(effect, 'criterion_id', ' ' + sentinel)
    with pytest.raises(CandidateConstituentsDenied) as caught:
        replace(c)
    assert sentinel not in str(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_question_range_remains_binding_even_if_paper_sum_and_range_are_coherent():
    c = deepcopy(_candidate())
    q = c.paper_score.question_results[0]
    # Isolate the QUESTION limit: paper remains in-range and paper=sum(question),
    # and the recorded final stage agrees with the altered question final.
    high = ScoringDecimal.from_raw('999')
    object.__setattr__(q, 'final_score', high)
    object.__setattr__(q.stage_effects[-1], 'after', high)
    object.__setattr__(c.paper_score, 'final_score', high)
    object.__setattr__(c.paper_score, 'maximum_score', ScoringDecimal.from_raw('1000'))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c)
