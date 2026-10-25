"""Hostile historical rule/effect coherence tests against actual CAS recovery."""
from dataclasses import replace

import pytest

from grading.contracts.result import RuleDecision, RuleType
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.whole_paper_cas import PaperCASState
from grading.scoring.reducer import reduce_question
from tests.integration.test_paper_cas_predecessor_contract_independent import scenario
from tests.unit.test_reducer_adversarial import full_authority, full_judgments


def sd(raw):
    return ScoringDecimal.from_raw(str(raw))


@pytest.mark.parametrize('defect', (
    'base_contribution_contradiction',
    'unrecorded_gate_change',
    'unrecorded_deduction_change',
    'unrecorded_cap_change',
    'unbacked_blocking_dependency',
    'triggered_gate_without_stage_source',
    'triggered_deduction_without_stage_source',
))
def test_predecessor_must_reject_locally_impossible_rule_effects_before_reads(defect):
    _, predecessor, recovery, outcome, store, source = scenario()
    result = predecessor.intent.result
    record = result.questions[0]
    score = record.score
    if defect == 'base_contribution_contradiction':
        effects = list(score.criterion_effects)
        effects[0] = replace(effects[0], base_contribution=sd(9))
        score = replace(score, criterion_effects=tuple(effects))
    elif defect == 'unbacked_blocking_dependency':
        effects = list(score.criterion_effects)
        effects[0] = replace(effects[0], blocking_dependency_rule_ids=('DEP-FAKE',),
                             effective_contribution=sd(2))
        score = replace(score, criterion_effects=tuple(effects))
    elif defect in ('triggered_gate_without_stage_source',
                    'triggered_deduction_without_stage_source'):
        kind = (RuleType.GATE if defect.startswith('triggered_gate')
                else RuleType.DEDUCTION)
        score = replace(score, rule_decisions=(RuleDecision(
            'FORGED-RULE', kind, True, sd(1)),))
    else:
        stages = list(score.stage_effects)
        index = {'unrecorded_gate_change': 0, 'unrecorded_cap_change': 1,
                 'unrecorded_deduction_change': 2}[defect]
        stages[index] = replace(stages[index], after=sd(4))
        for pos in range(index + 1, 4):
            stages[pos] = replace(stages[pos], before=sd(4), after=sd(4))
        score = replace(score, stage_effects=tuple(stages),
                        score_before_rounding=sd(4), final_score=sd(4))
    records = (replace(record, score=score), *result.questions[1:])
    paper = replace(result.paper_score, question_results=tuple(r.score for r in records),
                    final_score=(sd(9) if defect.startswith('unrecorded_')
                                 else result.paper_score.final_score))
    previous = replace(predecessor, intent=replace(predecessor.intent, result=replace(
        result, questions=records, paper_score=paper)))
    original_reads = store.reads
    assert recovery.reconcile(outcome=outcome, disjoint_from=previous) is PaperCASState.BLOCKED
    assert source.calls == 0
    assert store.reads == original_reads


def test_genuine_original_predecessor_recovery_remains_successful():
    _, previous, recovery, outcome, store, source = scenario()
    original_reads = store.reads
    assert recovery.reconcile(outcome=outcome, disjoint_from=previous) is PaperCASState.COMMITTED
    assert source.calls == 1 and store.reads == original_reads + 1


def test_actual_frozen_reducer_multi_rule_output_is_admissible():
    """Nontrivial dependencies, gate/cap/deduction/rounding emitted by real scorer."""
    from grading.integration.whole_paper_cas import _valid_locally_replayable_rule_trace
    produced = reduce_question(full_authority(), full_judgments())
    assert any(effect.blocking_dependency_rule_ids for effect in produced.criterion_effects)
    assert all(stage.source_rule_ids for stage in produced.stage_effects)
    assert _valid_locally_replayable_rule_trace(produced)
