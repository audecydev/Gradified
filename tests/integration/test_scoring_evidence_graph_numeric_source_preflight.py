"""Verify exact numeric-source type admission precedes copying and callbacks."""
import pytest
from grading.contracts.evidence import EvidenceConfidenceStatus
from grading.integration.result_constituents import (
    CandidateConstituentsDenied, compose_nonpublishing_constituents,
)
from grading.risk_policy import RiskReviewRecommender
from test_result_constituents_provenance import example
from test_risk_policy_recommendations import current


@pytest.mark.parametrize('target', ['bbox', 'confidence', 'metadata', 'question_record'])
def test_pre_invalid_source_does_not_dispatch_foreign_methods(target):
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    effects = []

    class HostileMeta(type):
        def __eq__(cls, other):
            effects.append('class-equality')
            return True

    class Foreign(metaclass=HostileMeta):
        def __float__(self):
            effects.append('numeric-coercion')
            return 0.5

        def __getattr__(self, name):
            effects.append('foreign-attribute')
            return self

        def __deepcopy__(self, memo):
            effects.append('foreign-copy')
            return self

    block = evidence.questions[0].blocks[0]
    if target == 'bbox':
        object.__setattr__(block.location, 'bbox', (Foreign(),))
    elif target == 'confidence':
        object.__setattr__(block, 'confidence_status', EvidenceConfidenceStatus.PRESENT)
        object.__setattr__(block, 'confidence', Foreign())
    elif target == 'metadata':
        meta = execution.questions[0].verified.evaluated_judgments[0].evaluator_metadata
        object.__setattr__(meta, 'version', Foreign())
    else:
        object.__setattr__(execution, 'questions', (Foreign(),))

    with pytest.raises(CandidateConstituentsDenied) as caught:
        compose_nonpublishing_constituents(
            execution=execution, evidence=evidence,
            policy_query=query, recommender=recommender,
        )
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert reader.calls == 0
    assert effects == []


def test_reader_mutating_evidence_to_foreign_value_is_denied_without_foreign_callback():
    execution, evidence, query, _, _ = example(unknown_ocr=True)
    effects = []

    class HostileMeta(type):
        def __eq__(cls, other):
            effects.append('class-equality')
            return True

    class Foreign(metaclass=HostileMeta):
        def __float__(self):
            effects.append('numeric-coercion')
            return 0.5

    block = evidence.questions[0].blocks[0]

    class MutatingReader:
        calls = 0
        def read_current(self, *, query):
            self.calls += 1
            object.__setattr__(block, 'confidence_status', EvidenceConfidenceStatus.PRESENT)
            object.__setattr__(block, 'confidence', Foreign())
            return current(query)

    reader = MutatingReader()
    recommender = RiskReviewRecommender(
        reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY', max_observations=4,
    )
    with pytest.raises(CandidateConstituentsDenied) as caught:
        compose_nonpublishing_constituents(
            execution=execution, evidence=evidence,
            policy_query=query, recommender=recommender,
        )
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert reader.calls == 1
    assert effects == []


def test_valid_reader_and_detached_candidate_remain_available():
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    candidate = compose_nonpublishing_constituents(
        execution=execution, evidence=evidence,
        policy_query=query, recommender=recommender,
    )
    assert reader.calls == 1
    assert candidate.official_result is False
    assert candidate.validated_snapshot().paper_score == candidate.paper_score


def test_oversized_incoming_evidence_text_stops_before_policy_contact():
    from grading.integration.result_constituents import _MAX_CONSTITUENT_TEXT_CHARS
    execution, evidence, query, recommender, reader = example(unknown_ocr=True)
    block = evidence.questions[0].blocks[0]
    object.__setattr__(block, 'content', 'x' * (_MAX_CONSTITUENT_TEXT_CHARS + 1))
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(
            execution=execution, evidence=evidence,
            policy_query=query, recommender=recommender,
        )
    assert reader.calls == 0
