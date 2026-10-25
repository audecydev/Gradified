"""Verify result-constituent admission preserves approved source and evidence identity."""
import pytest
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents, _detached_signature,
)
from grading.risk_policy import RiskReviewRecommender, ReviewDisposition, RecommendationReason
from test_result_constituents_provenance import example
from test_risk_policy_recommendations import current


def _reader():
    class Reader:
        calls = 0
        def read_current(self, *, query):
            self.calls += 1
            return current(query)
    reader = Reader()
    return reader, RiskReviewRecommender(reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)


def test_signature_preserves_primitive_type():
    assert _detached_signature(1) != _detached_signature(True)
    assert _detached_signature(0) != _detached_signature(False)


def test_callback_cannot_swap_evidence_reading_order_int_to_bool():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    block = evidence.questions[0].blocks[0]
    before = block.reading_order
    class Reader:
        calls = 0
        def read_current(self, *, query):
            self.calls += 1
            object.__setattr__(block, 'reading_order', bool(before))
            return current(query)
    reader = Reader()
    recommender = RiskReviewRecommender(reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4)
    try:
        with pytest.raises(CandidateConstituentsDenied):
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                               policy_query=query, recommender=recommender)
        assert reader.calls == 1
    finally:
        object.__setattr__(block, 'reading_order', before)


@pytest.mark.parametrize('field,bad', [('page', True), ('reading_order', True), ('confidence', 'PRIVATE_INVALID')])
def test_invalid_evidence_must_be_denied_before_policy_callback(field, bad):
    execution, evidence, query, _, _ = example(unknown_ocr=False)
    block = evidence.questions[0].blocks[0]
    old = getattr(block, field)
    reader, recommender = _reader()
    object.__setattr__(block, field, bad)
    try:
        with pytest.raises(CandidateConstituentsDenied):
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                               policy_query=query, recommender=recommender)
        assert reader.calls == 0
    finally:
        object.__setattr__(block, field, old)


def test_invalid_evaluator_metadata_must_be_denied_before_policy_callback():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    metadata = execution.questions[0].verified.evaluated_judgments[0].evaluator_metadata
    old = metadata.version
    reader, recommender = _reader()
    object.__setattr__(metadata, 'version', True)
    try:
        with pytest.raises(CandidateConstituentsDenied):
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                               policy_query=query, recommender=recommender)
        assert reader.calls == 0
    finally:
        object.__setattr__(metadata, 'version', old)


def test_valid_policy_recommendation_still_works():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    result = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                policy_query=query, recommender=recommender)
    assert result.review_recommendation.disposition is ReviewDisposition.HUMAN_REVIEW
    assert result.official_result is False and reader.calls == 1


def test_empty_risk_still_skips_policy_reader():
    execution, evidence, query, recommender, reader = example(unknown_ocr=False)
    result = compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                                policy_query=query, recommender=recommender)
    assert result.review_recommendation.disposition is ReviewDisposition.DEFERRED
    assert result.review_recommendation.reason is RecommendationReason.NO_POSITIVE_ELIGIBILITY
    assert reader.calls == 0


def test_public_denial_does_not_retain_private_submitted_identity_in_context():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    record = execution.questions[0]
    original_score = record.score.question_id
    original_verified = record.verified.question_id
    sentinel = 'CONFIDENTIAL_ATTEMPT_TOKEN_FOR_NEGATIVE_TEST'
    object.__setattr__(record.score, 'question_id', sentinel)
    object.__setattr__(record.verified, 'question_id', sentinel)
    try:
        with pytest.raises(CandidateConstituentsDenied) as caught:
            compose_nonpublishing_constituents(execution=execution, evidence=evidence,
                                               policy_query=query, recommender=recommender)
        assert reader.calls == 0
        exc = caught.value
        assert sentinel not in str(exc)
        # A public Python exception exposes these objects, despite `from None`.
        assert exc.__cause__ is None
        assert exc.__context__ is None
    finally:
        object.__setattr__(record.score, 'question_id', original_score)
        object.__setattr__(record.verified, 'question_id', original_verified)
