"""Independent R11C hostile prior scoring-evidence correlation."""
from dataclasses import replace
import pytest
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_paper_cas_predecessor_contract_independent import scenario

@pytest.mark.parametrize('defect', [
    'foreign_verified_question', 'foreign_verified_submission',
    'swapped_verified_question', 'foreign_scored_rubric', 'foreign_scored_policy',
])
def test_predecessor_verified_and_scored_identity_are_authoritatively_aligned(defect):
    _, predecessor, reader, observation, store, source = scenario()
    score = predecessor.intent.result
    questions=list(score.questions)
    if defect=='foreign_verified_question':
        questions[0]=replace(questions[0], verified=replace(questions[0].verified, question_id='Q-FOREIGN'))
    elif defect=='foreign_verified_submission':
        questions[0]=replace(questions[0], verified=replace(questions[0].verified, submission_ref='S-FOREIGN'))
    elif defect=='swapped_verified_question':
        questions[0]=replace(questions[0], verified=replace(questions[0].verified, question_id=questions[1].verified.question_id))
    elif defect=='foreign_scored_rubric':
        questions[0]=replace(questions[0],score=replace(questions[0].score, rubric_ref=replace(questions[0].score.rubric_ref,id='FOREIGN-RUBRIC')))
        score=replace(score,paper_score=replace(score.paper_score,question_results=tuple(q.score for q in questions)))
    elif defect=='foreign_scored_policy':
        questions[0]=replace(questions[0],score=replace(questions[0].score, scoring_policy_ref=replace(questions[0].score.scoring_policy_ref,id='FOREIGN-POLICY')))
        score=replace(score,paper_score=replace(score.paper_score,question_results=tuple(q.score for q in questions)))
    score=replace(score,questions=tuple(questions))
    bad=replace(predecessor,intent=replace(predecessor.intent,result=score))
    before=store.reads
    result=reader.reconcile(outcome=observation,disjoint_from=bad)
    assert result is not PaperCASState.COMMITTED,(defect,result)
    assert source.calls==0,(defect,'avoidable source',source.calls)
    assert store.reads==before,(defect,'avoidable CAS read',store.reads-before)


def test_legitimate_predecessor_control():
    _,p,r,o,store,source=scenario(); before=store.reads
    assert r.reconcile(outcome=o,disjoint_from=p) is PaperCASState.COMMITTED
    assert source.calls==1 and store.reads==before+1

@pytest.mark.parametrize('defect', [
    'rubric_version_bool', 'policy_version_bool',
    'unsupported_policy_semantics', 'verified_question_nonstring',
    'unsupported_question_numeric_profile',
])
def test_historical_contracts_reject_mutated_types_and_versions_before_effects(defect):
    _, predecessor, reader, observation, store, source = scenario()
    result = predecessor.intent.result
    record = result.questions[0]
    if defect == 'rubric_version_bool':
        object.__setattr__(record.score.rubric_ref, 'version', True)
    elif defect == 'policy_version_bool':
        object.__setattr__(record.score.scoring_policy_ref, 'version', True)
    elif defect == 'unsupported_policy_semantics':
        object.__setattr__(record.score.scoring_policy_ref, 'scoring_semantics_version', 'UNSUPPORTED-SEMANTICS')
    elif defect == 'verified_question_nonstring':
        object.__setattr__(record.verified, 'question_id', True)
    else:
        object.__setattr__(record.score, 'numeric_profile_version', 'UNSUPPORTED-PROFILE')
    reads_before = store.reads
    assert reader.reconcile(outcome=observation, disjoint_from=predecessor) is PaperCASState.BLOCKED
    assert source.calls == 0
    assert store.reads == reads_before
