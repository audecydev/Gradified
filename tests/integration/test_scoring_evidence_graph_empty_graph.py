"""Independent fourth-pass black-box falsification of impossible scoring/scoring aggregation inventories."""
import pytest
from dataclasses import replace
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents
from test_result_constituents_provenance import example

ZERO = ScoringDecimal.from_raw('0')

def _compose(ex, evidence, query, recommender):
    return compose_nonpublishing_constituents(execution=ex,evidence=evidence,policy_query=query,recommender=recommender)

def test_empty_paper_is_not_a_real_b3_aggregation():
    ex, evidence, query, rec, reader = example(unknown_ocr=False)
    object.__setattr__(ex, 'questions', ())
    object.__setattr__(ex.paper_score, 'question_results', ())
    object.__setattr__(ex.paper_score, 'final_score', ZERO)
    with pytest.raises(CandidateConstituentsDenied):
        _compose(ex,evidence,query,rec)
    assert reader.calls==0

def test_nonempty_question_with_zero_criteria_cannot_come_from_b2():
    ex, evidence, query, rec, reader = example(unknown_ocr=False)
    record=ex.questions[0]
    q=record.score
    for v in (q,):
        object.__setattr__(v, 'criterion_effects', ())
        object.__setattr__(v, 'base_subtotal', ZERO)
        object.__setattr__(v, 'score_before_rounding', ZERO)
        object.__setattr__(v, 'final_score', ZERO)
    object.__setattr__(record.verified, 'evaluated_judgments', ())
    object.__setattr__(record.verified, 'scoring_judgments', ())
    for s in q.stage_effects:
        object.__setattr__(s,'before',ZERO)
        object.__setattr__(s,'after',ZERO)
    object.__setattr__(ex.paper_score, 'final_score', ZERO)
    with pytest.raises(CandidateConstituentsDenied):
        _compose(ex,evidence,query,rec)
    assert reader.calls==0

def test_valid_single_question_control():
    ex,evidence,query,rec,reader=example(unknown_ocr=False)
    c=_compose(ex,evidence,query,rec)
    assert len(c.question_scores)==1
    assert len(c.question_scores[0].criterion_effects)>=1
    assert c.official_result is False
