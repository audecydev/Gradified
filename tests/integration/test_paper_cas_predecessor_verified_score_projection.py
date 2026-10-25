"""Prior deterministic scoring scoring projection must be the one that produced the prior score."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_paper_cas_predecessor_contract_independent import scenario


@pytest.mark.parametrize('defect', [
    'mutated_scoring_judgment_only',
    'internally_coherent_foreign_verified_criterion',
    'mutated_score_selected_level',
])
def test_previous_verified_criterion_projection_matches_scored_effects_before_read(defect):
    _, predecessor, reader, observation, store, source = scenario()
    record = predecessor.intent.result.questions[0]
    verified = record.verified
    if defect == 'mutated_scoring_judgment_only':
        j = verified.scoring_judgments[0]
        object.__setattr__(verified, 'scoring_judgments', (
            replace(j, criterion_id='FOREIGN-CRITERION'), *verified.scoring_judgments[1:]))
    elif defect == 'internally_coherent_foreign_verified_criterion':
        j = verified.scoring_judgments[0]
        e = verified.evaluated_judgments[0]
        object.__setattr__(verified, 'scoring_judgments', (
            replace(j, criterion_id='FOREIGN-CRITERION'), *verified.scoring_judgments[1:]))
        object.__setattr__(verified, 'evaluated_judgments', (
            replace(e, criterion_id='FOREIGN-CRITERION'), *verified.evaluated_judgments[1:]))
    else:
        effect = record.score.criterion_effects[0]
        object.__setattr__(effect, 'selected_level', 'FOREIGN-LEVEL')
    reads_before = store.reads
    assert reader.reconcile(outcome=observation, disjoint_from=predecessor) is PaperCASState.BLOCKED
    assert source.calls == 0
    assert store.reads == reads_before


def test_original_verified_projection_still_allows_fixed_origin_recovery():
    _, predecessor, reader, observation, store, source = scenario()
    before = store.reads
    assert reader.reconcile(outcome=observation, disjoint_from=predecessor) is PaperCASState.COMMITTED
    assert source.calls == 1 and store.reads == before+1

@pytest.mark.parametrize('defect', ['empty_scored_criteria', 'repeated_criterion_with_different_level'])
def test_previous_score_cannot_claim_zero_or_duplicate_scored_criteria(defect):
    _, predecessor, reader, observation, store, source = scenario()
    record = predecessor.intent.result.questions[0]
    verified = record.verified
    if defect == 'empty_scored_criteria':
        object.__setattr__(verified, 'scoring_judgments', ())
        object.__setattr__(verified, 'evaluated_judgments', ())
        object.__setattr__(record.score, 'criterion_effects', ())
    else:
        scoring = verified.scoring_judgments[0]
        evaluated = verified.evaluated_judgments[0]
        effect = record.score.criterion_effects[0]
        object.__setattr__(verified, 'scoring_judgments', (
            scoring, replace(scoring, selected_level='ALTERNATE-LEVEL')))
        object.__setattr__(verified, 'evaluated_judgments', (
            evaluated, replace(evaluated, selected_level='ALTERNATE-LEVEL')))
        object.__setattr__(record.score, 'criterion_effects', (
            effect, replace(effect, selected_level='ALTERNATE-LEVEL')))
    reads_before = store.reads
    assert reader.reconcile(outcome=observation, disjoint_from=predecessor) is PaperCASState.BLOCKED
    assert source.calls == 0
    assert store.reads == reads_before
