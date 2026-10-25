"""Independent fourth-pass check of necessary frozen criterion scoring policy invariants."""
import pytest
from dataclasses import replace
from grading.contracts.result import RuleDecision, RuleType
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents
from test_result_constituents_provenance import example


def attempt_mutated_rule(decision, rounding_overlap=False):
    ex, evidence, query, rec, reader=example(unknown_ocr=True)
    q=ex.paper_score.question_results[0]
    object.__setattr__(q, 'rule_decisions', (decision,))
    if rounding_overlap:
        object.__setattr__(q.stage_effects[-1], 'source_rule_ids', (decision.rule_id,))
    try:
        compose_nonpublishing_constituents(execution=ex,evidence=evidence,policy_query=query,recommender=rec)
    except CandidateConstituentsDenied:
        pass
    else:
        pytest.fail('Candidate constituent readmission accepted impossible rule provenance for a valid scoring policy')
    assert reader.calls == 0

def test_rounding_and_conditional_rule_id_cannot_collide():
    attempt_mutated_rule(RuleDecision('REPEATED-ID',RuleType.DEPENDENCY,False,None),True)

def test_deduction_must_be_strictly_positive_even_if_untriggered():
    attempt_mutated_rule(RuleDecision('BAD-DEDUCTION',RuleType.DEDUCTION,False,ScoringDecimal.from_raw('0')))

def test_gate_ceiling_must_be_within_question_range_even_if_untriggered():
    attempt_mutated_rule(RuleDecision('BAD-GATE',RuleType.GATE,False,ScoringDecimal.from_raw('999')))

def test_valid_input_control():
    ex,evidence,query,rec,reader=example(unknown_ocr=True)
    c=compose_nonpublishing_constituents(execution=ex,evidence=evidence,policy_query=query,recommender=rec)
    assert reader.calls==1 and not c.official_result
