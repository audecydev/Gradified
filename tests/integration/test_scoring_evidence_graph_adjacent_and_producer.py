"""Necessary inherited criterion scoring/scoring aggregation producer invariants; no independent scorer."""
from dataclasses import replace

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.policy import (
    SCORING_SEMANTICS_V1, CriterionCondition, CapRule, GateRule, DeductionRule,
    QuestionScoringPolicy, RoundingRule, RoundingMode,
)
from grading.contracts.result import RuleDecision, RuleType, ScoreStage
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, _readmit_question_score,
    compose_nonpublishing_constituents,
)
from grading.scoring.reducer import reduce_question
from test_result_constituents_provenance import example


def amount(value):
    return ScoringDecimal.from_raw(str(value))


def _actual_reducer_result(*, selected_level='YES', rounded=True):
    criterion = AtomicCriterion('CRITERION', 'Assess the required step', (
        PerformanceLevel('YES', amount('3.5')),
        PerformanceLevel('NO', amount('0')),
    ))
    c = (CriterionCondition('CRITERION', ('YES',)),)
    policy = QuestionScoringPolicy(
        policy_id='POLICY', version=1, question_id='QUESTION',
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=amount('0'), maximum_score=amount('5'),
        gates=(GateRule('G', c, amount('2')) ,),
        caps=(CapRule('C', c, amount('3')) ,),
        deductions=(DeductionRule('D', c, amount('0.5')) ,),
        rounding=RoundingRule('R', amount('1'), RoundingMode.HALF_UP) if rounded else None,
    )
    rubric = CompiledQuestionRubric('RUBRIC', 1, 'QUESTION', amount('5'), (criterion,))
    return reduce_question(QuestionScoringAuthority(rubric,policy),
                           (CriterionJudgment('CRITERION',selected_level),))


@pytest.mark.parametrize('selected_level,rounded', [
    ('YES', True), ('NO', True), ('YES', False), ('NO', False),
])
def test_actual_b2_reducer_results_survive_f53_readmission(selected_level, rounded):
    actual = _actual_reducer_result(selected_level=selected_level, rounded=rounded)
    _readmit_question_score(actual)
    assert len(actual.criterion_effects) == 1
    assert all(item.rule_id in ('G', 'C', 'D') for item in actual.rule_decisions)
    assert actual.stage_effects[-1].source_rule_ids == (('R',) if rounded else ())


@pytest.mark.parametrize('kind', [RuleType.GATE, RuleType.CAP])
def test_untriggered_out_of_range_ceiling_rejected_before_policy_lookup(kind):
    ex, evidence, query, recommender, reader = example(unknown_ocr=True)
    score = ex.paper_score.question_results[0]
    object.__setattr__(score, 'rule_decisions',
                       (RuleDecision('OVERSIZED', kind, False, amount('999')),))
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=ex, evidence=evidence,
                                           policy_query=query, recommender=recommender)
    assert reader.calls == 0


def test_mutated_snapshot_cannot_admit_zero_questions():
    ex, evidence, query, recommender, reader = example(unknown_ocr=False)
    candidate = compose_nonpublishing_constituents(execution=ex, evidence=evidence,
                                                   policy_query=query, recommender=recommender)
    object.__setattr__(candidate.paper_score,'question_results',())
    with pytest.raises(CandidateConstituentsDenied):
        candidate.validated_snapshot()


def test_mutated_snapshot_cannot_admit_invalid_untriggered_deduction():
    ex, evidence, query, recommender, reader = example(unknown_ocr=False)
    candidate = compose_nonpublishing_constituents(execution=ex, evidence=evidence,
                                                   policy_query=query, recommender=recommender)
    score = candidate.question_scores[0]
    object.__setattr__(score, 'rule_decisions',
                       (RuleDecision('D', RuleType.DEDUCTION, False, amount('0')),))
    with pytest.raises(CandidateConstituentsDenied):
        candidate.validated_snapshot()
