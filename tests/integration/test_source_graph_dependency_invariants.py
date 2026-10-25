"""Independent fifth-pass producer-invariant probes. No source changes."""
from dataclasses import replace
import pytest
from grading.contracts.result import RuleDecision, RuleType
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents, _readmit_question_score
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.policy import QuestionScoringPolicy, PositiveCreditDependencyRule, CriterionCondition, SCORING_SEMANTICS_V1
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.judgment import CriterionJudgment
from grading.scoring.reducer import reduce_question
from test_result_constituents_provenance import example

def amt(x): return ScoringDecimal.from_raw(str(x))

def dependency_result(*, prerequisite_level="NO"):
    criteria = (
        AtomicCriterion('PREREQ','prerequisite', (PerformanceLevel('YES',amt(2)),PerformanceLevel('NO',amt(0)))),
        AtomicCriterion('TARGET','target', (PerformanceLevel('YES',amt(3)),PerformanceLevel('NO',amt(0)))),
    )
    rubric=CompiledQuestionRubric('RUBRIC',1,'Q',amt(5),criteria)
    policy=QuestionScoringPolicy('POLICY',1,'Q',SCORING_SEMANTICS_V1,amt(0),amt(5),
        positive_credit_dependencies=(PositiveCreditDependencyRule('DEP', 'TARGET', (CriterionCondition('PREREQ', ('YES',)),)),))
    return reduce_question(QuestionScoringAuthority(rubric,policy), (CriterionJudgment('PREREQ',prerequisite_level),CriterionJudgment('TARGET','YES')))

def test_valid_real_reducer_dependency_control():
    score=dependency_result()
    assert score.rule_decisions[0].triggered is True
    assert score.criterion_effects[1].blocking_dependency_rule_ids == ('DEP',)
    _readmit_question_score(score)

def test_reject_triggered_dependency_with_no_target_before_reader():
    ex, ev, query, rec, reader = example(unknown_ocr=True)
    score=ex.paper_score.question_results[0]
    object.__setattr__(score,'rule_decisions', (RuleDecision('ORPHAN', RuleType.DEPENDENCY, True, None),))
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=ex,evidence=ev,policy_query=query,recommender=rec)
    assert reader.calls == 0

def test_reject_dependency_blocker_replicated_across_two_criteria():
    score=dependency_result()
    # PREREQ has a legitimate zero base/effective contribution. Adding
    # the already-triggered DEP ID to PREREQ changes no amount yet makes it
    # impossible that this score came from a single-target dependency rule.
    object.__setattr__(score.criterion_effects[0], 'blocking_dependency_rule_ids', ('DEP',))
    with pytest.raises(CandidateConstituentsDenied):
        _readmit_question_score(score)

def test_valid_real_reducer_nontriggered_dependency_control():
    score=dependency_result(prerequisite_level="YES")
    assert score.rule_decisions[0].triggered is False
    assert all(not effect.blocking_dependency_rule_ids for effect in score.criterion_effects)
    _readmit_question_score(score)
