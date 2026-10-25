"""Independent historical-CAS scoring-consistency checks before source reads."""
from dataclasses import replace
import pytest

from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_paper_cas_predecessor_contract_independent import scenario


@pytest.mark.parametrize('defect', [
    'foreign_question_id',
    'reordered_question_records',
    'foreign_paper_scoring_spec',
    'detached_paper_question_scores',
    'contradictory_paper_total',
    'out_of_range_paper_total',
])
def test_prior_generation_scored_record_must_match_prior_paper_before_source(defect):
    _, predecessor, reader, observation, store, source = scenario()
    scored = predecessor.intent.result
    if defect == 'foreign_question_id':
        questions = list(scored.questions)
        questions[0] = replace(questions[0], score=replace(
            questions[0].score, question_id='FOREIGN-QUESTION'))
        scored = replace(scored, questions=tuple(questions))
    elif defect == 'reordered_question_records':
        scored = replace(scored, questions=tuple(reversed(scored.questions)))
    elif defect == 'foreign_paper_scoring_spec':
        spec = replace(scored.paper_score.grading_spec_ref, id='FOREIGN-SPEC')
        scored = replace(scored, paper_score=replace(scored.paper_score, grading_spec_ref=spec))
    elif defect == 'detached_paper_question_scores':
        scores = tuple(reversed(scored.paper_score.question_results))
        scored = replace(scored, paper_score=replace(scored.paper_score, question_results=scores))
    elif defect == 'contradictory_paper_total':
        scored = replace(scored, paper_score=replace(scored.paper_score,
            final_score=scored.questions[0].score.final_score))
    else:
        scored = replace(scored, paper_score=replace(scored.paper_score,
            maximum_score=scored.paper_score.minimum_score))
    predecessor = replace(predecessor, intent=replace(predecessor.intent, result=scored))
    reads_before = store.reads
    status = reader.reconcile(outcome=observation, disjoint_from=predecessor)
    assert status is not PaperCASState.COMMITTED, (defect, status)
    assert source.calls == 0, (defect, 'avoidable original-source read')
    assert store.reads == reads_before, (defect, 'avoidable backend read')


def test_consistent_previous_scoring_still_permits_fixed_origin_recovery():
    _, predecessor, reader, observation, store, source = scenario()
    reads_before = store.reads
    assert reader.reconcile(outcome=observation, disjoint_from=predecessor) is PaperCASState.COMMITTED
    assert source.calls == 1 and store.reads == reads_before + 1



def test_mutated_prior_scoring_profile_is_rejected_before_source_or_backend():
    _, predecessor, reader, observation, store, source = scenario()
    old = predecessor.intent
    for record in old.result.questions:
        object.__setattr__(record.score, 'numeric_profile_version', 'UNSUPPORTED-PROFILE')
    object.__setattr__(old.result.paper_score, 'numeric_profile_version', 'UNSUPPORTED-PROFILE')
    reads_before = store.reads
    status = reader.reconcile(outcome=observation, disjoint_from=predecessor)
    assert status is PaperCASState.BLOCKED
    assert source.calls == 0
    assert store.reads == reads_before


def test_bool_scoring_spec_version_is_not_accepted_as_integer_one():
    _, predecessor, reader, observation, store, source = scenario()
    old = predecessor.intent
    object.__setattr__(old.result.paper_score.grading_spec_ref, 'version', True)
    reads_before = store.reads
    status = reader.reconcile(outcome=observation, disjoint_from=predecessor)
    assert status is PaperCASState.BLOCKED
    assert source.calls == 0
    assert store.reads == reads_before
