"""Adversarial tests for source-graph admission and guarded callback handling."""
from dataclasses import replace
import pytest
from grading.contracts.result import RuleDecision, RuleType, CriterionEffect
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents
from grading.execution import GradingExecutionResult
from test_result_constituents_provenance import example
from test_synthetic_execution_eligibility_regression import _evidence,_question_evidence,_execute


def test_triggered_dependency_without_any_criterion_blocker_denied_before_policy_reader():
    ex, evidence, query, recommender, reader = example(unknown_ocr=True)
    original_score = ex.paper_score.question_results[0]
    bogus_score = replace(original_score, rule_decisions=(RuleDecision('DEP-ORPHAN', RuleType.DEPENDENCY, True, None),))
    new_paper = replace(ex.paper_score, question_results=(bogus_score,))
    forged_ex = replace(ex, paper_score=new_paper, questions=(replace(ex.questions[0], score=bogus_score),))
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=forged_ex, evidence=evidence,
                                          policy_query=query, recommender=recommender)
    assert reader.calls == 0


def test_swapped_execution_question_order_denied_before_policy_reader():
    evidence = _evidence((_question_evidence('Q1'), _question_evidence('Q2')))
    ex = _execute(question_ids=('Q1','Q2'), evidence=evidence)
    from grading.risk_policy import PolicyQuery, RiskReviewRecommender
    from test_risk_policy_recommendations import Reader, current
    c=ex.context
    query=PolicyQuery('TENANT','SCHOOL',c.grading_run_id,c.submission_ref,c.exam_ref,c.grading_spec_ref.id,c.grading_spec_ref.version,'1')
    reader=Reader(lambda query: current(query))
    recommender=RiskReviewRecommender(reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    forged_ex=replace(ex, questions=tuple(reversed(ex.questions)))
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=forged_ex, evidence=evidence,
                                          policy_query=query,recommender=recommender)
    assert reader.calls == 0

def test_one_triggered_dependency_cannot_block_two_distinct_criteria():
    ex, evidence, query, recommender, reader = example(unknown_ocr=True)
    original = ex.paper_score.question_results[0]
    c1=original.criterion_effects[0]
    blocked1=replace(c1, effective_contribution=ScoringDecimal.from_raw('0'),
                     blocking_dependency_rule_ids=('ONE-TARGET-RULE',))
    c2=CriterionEffect('C2','FULL',ScoringDecimal.from_raw('0'),
                       ScoringDecimal.from_raw('0'), ('ONE-TARGET-RULE',))
    zero=ScoringDecimal.from_raw('0')
    stages=tuple(replace(stage, before=zero, after=zero) for stage in original.stage_effects)
    score=replace(original, criterion_effects=(blocked1,c2),
                  rule_decisions=(RuleDecision('ONE-TARGET-RULE', RuleType.DEPENDENCY,True,None),),
                  stage_effects=stages,base_subtotal=zero,score_before_rounding=zero,
                  final_score=zero)
    paper=replace(ex.paper_score,question_results=(score,),final_score=zero)
    cand=compose_nonpublishing_constituents(execution=ex,evidence=evidence,
                                            policy_query=query,recommender=recommender)
    from dataclasses import replace as r
    with pytest.raises(CandidateConstituentsDenied):
        r(cand, question_scores=(score,), paper_score=paper)


def test_original_valid_score_and_valid_factory_still_accepted():
    ex, evidence, query, recommender, reader = example(unknown_ocr=True)
    cand = compose_nonpublishing_constituents(execution=ex,evidence=evidence,
                                              policy_query=query,recommender=recommender)
    assert not cand.official_result and cand.validated_snapshot().question_scores == cand.question_scores

def test_actual_frozen_reducer_triggered_dependency_has_exact_one_blocker_even_at_zero():
    from grading.contracts.authority import QuestionScoringAuthority
    from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
    from grading.contracts.policy import QuestionScoringPolicy, PositiveCreditDependencyRule, CriterionCondition, SCORING_SEMANTICS_V1
    from grading.contracts.judgment import CriterionJudgment
    from grading.scoring.reducer import reduce_question
    from grading.integration.result_constituents import _readmit_question_score
    sd=ScoringDecimal.from_raw
    rubric=CompiledQuestionRubric('R',1,'Q',sd('5'),(
        AtomicCriterion('C1','Target criterion',(PerformanceLevel('FULL',sd('5')),PerformanceLevel('NONE',sd('0')))),
        AtomicCriterion('C2','Prerequisite criterion',(PerformanceLevel('FULL',sd('0')),PerformanceLevel('NONE',sd('0')))),
    ))
    policy=QuestionScoringPolicy('P',1,'Q',SCORING_SEMANTICS_V1,sd('0'),sd('5'),
        positive_credit_dependencies=(PositiveCreditDependencyRule('DEP','C1',(CriterionCondition('C2',('FULL',)),)),))
    for selected_target in ('FULL','NONE'):
        result=reduce_question(QuestionScoringAuthority(rubric,policy),(
            CriterionJudgment('C1',selected_target),CriterionJudgment('C2','NONE')))
        assert result.rule_decisions[0].triggered
        assert result.criterion_effects[0].blocking_dependency_rule_ids == ('DEP',)
        assert result.criterion_effects[1].blocking_dependency_rule_ids == ()
        _readmit_question_score(result)
