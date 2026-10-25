"""result envelope: scoring-native scores, exact scope, negative trust/publication boundary."""
from dataclasses import replace
import pytest
from grading.contracts.evidence import EvidenceConfidenceStatus
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, CandidateReadiness, ConstituentEvidenceState,
    compose_nonpublishing_constituents,
)
from grading.risk_policy import PolicyQuery, ReviewDisposition, RiskReviewRecommender
from test_risk_policy_recommendations import Reader, current
from test_synthetic_execution_eligibility_regression import (
    _execute, _evidence, _question_evidence, _block,
)


def example(*, unknown_ocr=False):
    q = _question_evidence('Q1', block=_block('Q1', confidence_status=
        EvidenceConfidenceStatus.UNAVAILABLE if unknown_ocr else EvidenceConfidenceStatus.PRESENT))
    evidence = _evidence((q,))
    execution = _execute(question_ids=('Q1',), evidence=evidence)
    c = execution.context
    policy = PolicyQuery('TENANT', 'SCHOOL', c.grading_run_id, c.submission_ref,
                         c.exam_ref, c.grading_spec_ref.id, c.grading_spec_ref.version, '1')
    reader = Reader(lambda query: current(query))
    recommender = RiskReviewRecommender(reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    return execution, evidence, policy, recommender, reader


def test_nonpublishing_constituent_preserves_original_score_without_criterion_redistribution():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    candidate = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                    policy_query=query, recommender=recommender)
    assert candidate.paper_score is not execution.paper_score
    assert candidate.paper_score.final_score == execution.paper_score.final_score
    assert candidate.question_scores == execution.paper_score.question_results
    assert candidate.question_scores[0].criterion_effects == execution.questions[0].score.criterion_effects
    assert candidate.question_scores[0].stage_effects == execution.questions[0].score.stage_effects
    assert candidate.usage_evidence_state is ConstituentEvidenceState.UNKNOWN
    assert candidate.audit_evidence_state is ConstituentEvidenceState.UNKNOWN
    assert candidate.readiness is CandidateReadiness.INCOMPLETE_UNATTESTED_EXECUTION
    assert candidate.official_result is False
    assert candidate.review_recommendation.disposition is ReviewDisposition.HUMAN_REVIEW
    assert not hasattr(candidate, 'awarded_marks')
    assert reader.calls == 1


def test_empty_risk_never_complete_or_auto_and_no_policy_lookup():
    execution, evidence, query, recommender, reader = example()
    candidate = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                    policy_query=query, recommender=recommender)
    assert candidate.review_recommendation.disposition is ReviewDisposition.DEFERRED
    assert candidate.readiness is CandidateReadiness.INCOMPLETE_UNATTESTED_EXECUTION
    assert not candidate.official_result
    assert reader.calls == 0


@pytest.mark.parametrize('change', [
    {'grading_run_id':'WRONG'},
    {'submission_ref':'WRONG'},
    {'exam_ref':'WRONG'},
    {'grading_spec_id':'WRONG'},
    {'grading_spec_version':99},
])
def test_foreign_policy_scope_rejected_before_policy_read(change):
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                            policy_query=replace(query, **change), recommender=recommender)
    assert reader.calls == 0


def test_wrong_submission_evidence_fails_before_lookup():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=execution,
            evidence=replace(evidence, submission_ref='FOREIGN'),
            policy_query=query, recommender=recommender)
    assert reader.calls == 0


def test_policy_lookup_mutating_original_question_result_is_rejected():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    record = execution.questions[0]
    score = record.score
    original = score.question_id
    class Mutator:
        def read_current(self, *, query):
            object.__setattr__(score, 'question_id', 'MUTATED')
            return current(query)
    recommender = RiskReviewRecommender(reader=Mutator(), issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    try:
        with pytest.raises(CandidateConstituentsDenied):
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                policy_query=query, recommender=recommender)
    finally:
        object.__setattr__(score, 'question_id', original)


def test_absent_reader_returns_incomplete_candidate_not_success():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    class Down:
        def read_current(self, *, query):
            raise TimeoutError('PRIVATE_POLICY_SERVICE')
    recommender = RiskReviewRecommender(reader=Down(), issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    candidate = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                    policy_query=query, recommender=recommender)
    assert candidate.review_recommendation.disposition is ReviewDisposition.DEFERRED
    assert candidate.official_result is False
    assert 'PRIVATE_POLICY_SERVICE' not in repr(candidate)


def test_policy_callback_cannot_change_numeric_value_then_return_admitted_evidence():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    from grading.contracts.scoring_decimal import ScoringDecimal
    from grading.contracts.result import QuestionScoreResult
    paper = execution.paper_score
    original = paper.final_score
    class Mutator:
        def read_current(self, *, query):
            object.__setattr__(paper, 'final_score', ScoringDecimal.from_raw('123'))
            return current(query)
    recommender = RiskReviewRecommender(reader=Mutator(), issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    try:
        with pytest.raises(CandidateConstituentsDenied):
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                policy_query=query, recommender=recommender)
    finally:
        object.__setattr__(paper, 'final_score', original)

def test_after_return_mutated_original_score_cannot_change_detached_candidate():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    c = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                           policy_query=query, recommender=recommender)
    paper = execution.paper_score
    old = paper.final_score
    from grading.contracts.scoring_decimal import ScoringDecimal
    try:
        object.__setattr__(paper, 'final_score', ScoringDecimal.from_raw('123'))
        assert c.paper_score.final_score == old
        assert c.paper_score.final_score != paper.final_score
    finally:
        object.__setattr__(paper, 'final_score', old)


def test_candidate_model_cannot_be_spoofed_as_official_or_complete():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    candidate = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                    policy_query=query, recommender=recommender)
    with pytest.raises(CandidateConstituentsDenied):
        replace(candidate, official_result=True)
    with pytest.raises(CandidateConstituentsDenied):
        replace(candidate, schema_version='FUTURE')
    with pytest.raises(CandidateConstituentsDenied):
        replace(candidate, audit_evidence_state='KNOWN')


def test_policy_query_foreign_string_cannot_invoke_equality_before_read():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    class ForeignStr(str):
        def __eq__(self, other):
            raise AssertionError('UNTRUSTED_EQUALITY_EXECUTED')
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=execution, evidence=evidence,
            policy_query=replace(query, exam_ref=ForeignStr(query.exam_ref)), recommender=recommender)
    assert reader.calls == 0
