"""Dependency cardinality against the accepted criterion scoring producer, not a second reducer."""
from dataclasses import replace
import pytest
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.policy import (QuestionScoringPolicy, PositiveCreditDependencyRule,
    CriterionCondition, SCORING_SEMANTICS_V1)
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import (
    _readmit_question_score, CandidateConstituentsDenied,
    compose_nonpublishing_constituents,
)
from grading.scoring.reducer import reduce_question
from grading.risk_policy import RiskReviewRecommender
from test_risk_policy_recommendations import current
from test_result_constituents_provenance import example


def amount(value):
    return ScoringDecimal.from_raw(str(value))


def score_from_real_reducer(target_mark='5', num_rules=1):
    rubric = CompiledQuestionRubric('RUBRIC', 1, 'Q', amount('5'), (
        AtomicCriterion('TARGET', 'target',
                        (PerformanceLevel('FULL', amount(target_mark)),
                         PerformanceLevel('NONE', amount('0')))),
        AtomicCriterion('PREREQ', 'prereq',
                        (PerformanceLevel('FULL', amount('0')),
                         PerformanceLevel('NONE', amount('0')))),
    ))
    dependencies = tuple(PositiveCreditDependencyRule('D'+str(index), 'TARGET',
        (CriterionCondition('PREREQ', ('FULL',)),)) for index in range(num_rules))
    policy = QuestionScoringPolicy('POLICY', 1, 'Q', SCORING_SEMANTICS_V1,
                                   amount('-5'), amount('5'),
                                   positive_credit_dependencies=dependencies)
    return reduce_question(QuestionScoringAuthority(rubric, policy),
                           (CriterionJudgment('TARGET', 'FULL'),
                            CriterionJudgment('PREREQ', 'NONE')))


@pytest.mark.parametrize('mark', ('5', '0', '-2'))
def test_actual_reducer_dependency_target_cardinality_including_nonpositive(mark):
    score = score_from_real_reducer(mark)
    assert score.rule_decisions[0].triggered
    assert score.criterion_effects[0].blocking_dependency_rule_ids == ('D0',)
    assert score.criterion_effects[1].blocking_dependency_rule_ids == ()
    _readmit_question_score(score)


def test_multiple_real_triggered_dependencies_can_target_one_criterion():
    score = score_from_real_reducer('5', num_rules=2)
    assert score.criterion_effects[0].blocking_dependency_rule_ids == ('D0', 'D1')
    _readmit_question_score(score)


def test_validated_snapshot_denies_new_orphaned_rule_after_return():
    from grading.contracts.result import RuleDecision, RuleType
    ex, evidence, query, recommender, reader = example(unknown_ocr=True)
    candidate = compose_nonpublishing_constituents(
        execution=ex, evidence=evidence, policy_query=query, recommender=recommender)
    score = candidate.paper_score.question_results[0]
    object.__setattr__(score, 'rule_decisions',
                       (RuleDecision('ORPHAN', RuleType.DEPENDENCY, True, None),))
    with pytest.raises(CandidateConstituentsDenied):
        candidate.validated_snapshot()


def test_policy_callback_cannot_add_orphan_dependency_undetected():
    from grading.contracts.result import RuleDecision, RuleType
    ex, evidence, query, _, _ = example(unknown_ocr=True)
    class Mutator:
        def read_current(self, *, query):
            score = ex.paper_score.question_results[0]
            object.__setattr__(score, 'rule_decisions',
                (RuleDecision('ORPHAN', RuleType.DEPENDENCY, True, None),))
            return current(query)
    recommender = RiskReviewRecommender(reader=Mutator(),
       issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    with pytest.raises(CandidateConstituentsDenied) as caught:
        compose_nonpublishing_constituents(
            execution=ex, evidence=evidence, policy_query=query, recommender=recommender)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
