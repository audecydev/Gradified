from dataclasses import replace
import pytest
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import CandidateConstituentsDenied,compose_nonpublishing_constituents
from test_result_constituents_provenance import example

def valid_candidate():
    ex,ev,q,r,_ = example()
    return compose_nonpublishing_constituents(execution=ex,evidence=ev,policy_query=q,recommender=r)

def test_no_questions_paper_cannot_come_from_b3():
    c=valid_candidate()
    zero=ScoringDecimal.from_raw('0')
    empty_paper=replace(c.paper_score,question_results=(),final_score=zero,minimum_score=zero)
    with pytest.raises(CandidateConstituentsDenied):
       replace(c,question_scores=(),paper_score=empty_paper)

def test_no_criteria_question_cannot_come_from_b2():
    c=valid_candidate()
    zero=ScoringDecimal.from_raw('0')
    q=c.question_scores[0]
    # repair all dependent stage sums so zero effects have a consistent score
    stages=tuple(replace(s,before=zero,after=zero) for s in q.stage_effects)
    no_crit=replace(q,criterion_effects=(),base_subtotal=zero,score_before_rounding=zero,final_score=zero,stage_effects=stages)
    paper=replace(c.paper_score,question_results=(no_crit,),final_score=zero)
    with pytest.raises(CandidateConstituentsDenied):
       replace(c,question_scores=(no_crit,),paper_score=paper)

def test_rounding_without_round_rule_cannot_change_score():
    c=valid_candidate()
    q=c.question_scores[0]
    round_stage=q.stage_effects[-1]
    assert round_stage.source_rule_ids == ()
    assert round_stage.before == round_stage.after
    fake=ScoringDecimal.from_raw('4')
    altered_stage=replace(round_stage,after=fake)
    altered_q=replace(q,stage_effects=q.stage_effects[:-1]+(altered_stage,),final_score=fake)
    altered_p=replace(c.paper_score,question_results=(altered_q,),final_score=fake)
    with pytest.raises(CandidateConstituentsDenied):
        replace(c,question_scores=(altered_q,),paper_score=altered_p)

def test_legitimate_candidate_survives_fresh_validation():
    c=valid_candidate()
    checked=c.validated_snapshot()
    assert checked.official_result is False
    assert checked.paper_score == c.paper_score
    assert checked.paper_score is not c.paper_score

def test_factory_must_deny_impossible_rounding_before_policy_reader_contact():
    ex, ev, policy, recommender, reader = example(unknown_ocr=True)
    q=ex.questions[0].score
    assert q.stage_effects[-1].source_rule_ids == ()
    fake=ScoringDecimal.from_raw('4')
    new_stage=replace(q.stage_effects[-1],after=fake)
    new_q=replace(q,stage_effects=q.stage_effects[:-1]+(new_stage,),final_score=fake)
    new_p=replace(ex.paper_score,question_results=(new_q,),final_score=fake)
    foreign_ex=replace(ex,questions=(replace(ex.questions[0],score=new_q),),paper_score=new_p)
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=foreign_ex,evidence=ev,policy_query=policy,recommender=recommender)
    assert reader.calls == 0
