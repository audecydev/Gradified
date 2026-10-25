"""Verify reviewer specification scope and reject inadmissible second-pass evidence."""
from dataclasses import replace
import pytest
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents,
)
from test_result_constituents_provenance import example


def _foreign_paper(paper, *, wrong_version=False):
    original = paper.grading_spec_ref
    other = GradingSpecRef(
        original.id if wrong_version else 'FOREIGN-GRADING-SPEC',
        original.version + 1 if wrong_version else original.version,
    )
    return replace(paper, grading_spec_ref=other)


@pytest.mark.parametrize('wrong_version', [False, True])
def test_composer_must_reject_foreign_paper_scoring_authority(wrong_version):
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    supplied = replace(execution, paper_score=_foreign_paper(
        execution.paper_score, wrong_version=wrong_version))
    # A foreign result must not produce a policy recommendation for the
    # original spec or a falsely associated nonpublishing score envelope.
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(
            execution=supplied, evidence=evidence,
            policy_query=query, recommender=recommender,
        )
    assert reader.calls == 0


@pytest.mark.parametrize('wrong_version', [False, True])
def test_public_constituent_model_must_reject_foreign_paper_scoring_authority(wrong_version):
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    valid = compose_nonpublishing_constituents(
        execution=execution, evidence=evidence,
        policy_query=query, recommender=recommender,
    )
    with pytest.raises(CandidateConstituentsDenied):
        replace(valid, paper_score=_foreign_paper(
            valid.paper_score, wrong_version=wrong_version))


def test_public_constituent_model_must_reject_foreign_review_policy_exam():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    valid = compose_nonpublishing_constituents(
        execution=execution, evidence=evidence,
        policy_query=query, recommender=recommender,
    )
    wrong_query = replace(valid.review_recommendation.query, exam_ref='FOREIGN-EXAM')
    wrong_review = replace(valid.review_recommendation, query=wrong_query)
    with pytest.raises(CandidateConstituentsDenied):
        replace(valid, review_recommendation=wrong_review)


def test_positive_original_admitted_result_remains_nonofficial_and_consistent():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    valid = compose_nonpublishing_constituents(
        execution=execution, evidence=evidence,
        policy_query=query, recommender=recommender,
    )
    assert valid.paper_score.grading_spec_ref == execution.context.grading_spec_ref
    assert valid.grading_spec_id == valid.paper_score.grading_spec_ref.id
    assert valid.grading_spec_version == valid.paper_score.grading_spec_ref.version
    assert valid.review_recommendation.query.exam_ref == valid.exam_ref
    assert not valid.official_result
    assert reader.calls == 1
