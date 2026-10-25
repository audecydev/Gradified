"""Locally provable frozen deterministic scoring/reducer predecessor coherence before historical CAS reads."""
from dataclasses import replace
import pytest
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_paper_cas_predecessor_contract_independent import scenario

@pytest.mark.parametrize('defect', [
    'no_s1_evidence_refs',
    'blank_s1_evidence_ref',
    'whitespace_s1_evidence_ref',
    'no_frozen_stages',
    'reordered_frozen_stages',
    'broken_stage_continuity',
    'broken_score_before_rounding',
    'broken_base_subtotal',
    'broken_final_stage',
])
def test_historical_predecessor_must_preserve_real_s1_and_frozen_reducer_proof(defect):
    _, previous, recovery, outcome, store, source = scenario()
    graded = previous.intent.result
    records = list(graded.questions)
    rec = records[0]
    if defect in ('no_s1_evidence_refs', 'blank_s1_evidence_ref', 'whitespace_s1_evidence_ref'):
        projections = list(rec.verified.evaluated_judgments)
        projections[0] = replace(projections[0], evidence_refs=(
            () if defect == 'no_s1_evidence_refs' else
            ('',) if defect == 'blank_s1_evidence_ref' else ('  ',)))
        rec = replace(rec, verified=replace(rec.verified, evaluated_judgments=tuple(projections)))
    else:
        score = rec.score
        if defect == 'no_frozen_stages':
            score = replace(score, stage_effects=())
        elif defect == 'reordered_frozen_stages':
            stages = list(score.stage_effects)
            stages[0], stages[1] = stages[1], stages[0]
            score = replace(score, stage_effects=tuple(stages))
        elif defect == 'broken_stage_continuity':
            stages = list(score.stage_effects)
            stages[1] = replace(stages[1], before=ScoringDecimal.from_raw(999))
            score = replace(score, stage_effects=tuple(stages))
        elif defect == 'broken_score_before_rounding':
            score = replace(score, score_before_rounding=ScoringDecimal.from_raw(999))
        elif defect == 'broken_base_subtotal':
            score = replace(score, base_subtotal=ScoringDecimal.from_raw(999))
        elif defect == 'broken_final_stage':
            stages = list(score.stage_effects)
            stages[-1] = replace(stages[-1], after=ScoringDecimal.from_raw(999))
            score = replace(score, stage_effects=tuple(stages))
        rec = replace(rec, score=score)
    records[0] = rec
    graded = replace(graded, questions=tuple(records), paper_score=replace(
        graded.paper_score, question_results=tuple(item.score for item in records)))
    previous = replace(previous, intent=replace(previous.intent, result=graded))
    backend_reads = store.reads
    state = recovery.reconcile(outcome=outcome, disjoint_from=previous)
    assert state is PaperCASState.BLOCKED, (defect, state)
    assert source.calls == 0, (defect, 'unexpected original-source contact')
    assert store.reads == backend_reads, (defect, 'unexpected backend contact')


def test_valid_stable_recovery_survives():
    _, previous, recovery, outcome, store, source = scenario()
    reads = store.reads
    assert recovery.reconcile(outcome=outcome, disjoint_from=previous) is PaperCASState.COMMITTED
    assert source.calls == 1 and store.reads == reads + 1
