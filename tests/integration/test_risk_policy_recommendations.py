"""risk recommendation review-policy recommendation: installed policy is issuer-reported; no AUTO/grade promotion."""
from dataclasses import replace
import pytest
from grading.risk import RiskObservation, RiskObservationCode as Code, RiskObservationSet
from grading.risk_policy import (
    PolicyQuery, PolicyRule, PolicyFact, PolicyFactStatus as Status,
    ReviewDisposition as Decision, RecommendationReason as Reason,
    RiskReviewRecommender, RiskPolicyDenied,
)


QUERY = PolicyQuery('TENANT', 'SCHOOL', 'RUN', 'SUB', 'EXAM', 'SPEC', 1, '1')
OCR = RiskObservation(Code.OCR_CONFIDENCE_UNKNOWN, 'Q1', 'B1', None)
EVAL = RiskObservation(Code.EVALUATOR_UNCERTAINTY_REPORTED, 'Q1', None, 'C1')


def risk(*observations):
    return RiskObservationSet('1', 'RUN', 'SUB', tuple(observations))


def current(query=QUERY, **changes):
    base = PolicyFact(query, 'SCHOOL_POLICY_AUTHORITY', Status.CURRENT,
                      'POLICY', 2, 'APPROVED_REVISION', (
                          PolicyRule(Code.OCR_CONFIDENCE_UNKNOWN, Decision.HUMAN_REVIEW),
                          PolicyRule(Code.EVALUATOR_UNCERTAINTY_REPORTED, Decision.HUMAN_REVIEW),
                      ), '1')
    return replace(base, **changes)


class Reader:
    def __init__(self, callback=None):
        self.calls = 0
        self.callback = callback or current

    def read_current(self, *, query):
        self.calls += 1
        return self.callback(query)


def engine(reader=None, **changes):
    reader = reader or Reader()
    return RiskReviewRecommender(reader=reader, issuer_ref='SCHOOL_POLICY_AUTHORITY',
                                 max_observations=4, **changes), reader


def test_no_observation_is_not_positive_auto_eligibility_and_skips_lookup():
    recommender, reader = engine()
    result = recommender.recommend(query=QUERY, observations=risk())
    assert result.disposition is Decision.DEFERRED
    assert result.reason is Reason.NO_POSITIVE_ELIGIBILITY
    assert result.policy_ref is None and result.approval_ref is None
    assert reader.calls == 0


def test_one_and_two_signals_apply_exact_admitted_policy_without_auto_or_side_effects():
    recommender, reader = engine()
    for observations in ((OCR,), (EVAL,), (OCR, EVAL)):
        result = recommender.recommend(query=QUERY, observations=risk(*observations))
        assert result.disposition is Decision.HUMAN_REVIEW
        assert result.reason is Reason.ADMITTED_OBSERVATIONS
        assert (result.policy_ref, result.policy_version, result.approval_ref) == ('POLICY', 2, 'APPROVED_REVISION')
        assert result.query == QUERY and result.observations == observations
    assert reader.calls == 3


def test_approved_second_check_is_a_recommendation_not_new_executor():
    def fact(q):
        rules = tuple(PolicyRule(code, Decision.SECOND_CHECK) for code in Code)
        return current(q, rules=rules)
    recommender, reader = engine(Reader(fact))
    result = recommender.recommend(query=QUERY, observations=risk(EVAL))
    assert result.disposition is Decision.SECOND_CHECK
    assert result.policy_ref == 'POLICY' and reader.calls == 1


def test_conflicting_approved_signals_defer_instead_of_inventing_severity():
    def fact(q):
        return current(q, rules=(PolicyRule(Code.OCR_CONFIDENCE_UNKNOWN, Decision.HUMAN_REVIEW),
                                 PolicyRule(Code.EVALUATOR_UNCERTAINTY_REPORTED, Decision.SECOND_CHECK)))
    recommender, reader = engine(Reader(fact))
    result = recommender.recommend(query=QUERY, observations=risk(OCR, EVAL))
    assert result.disposition is Decision.DEFERRED
    assert result.reason is Reason.CONFLICTING_RULES
    assert result.policy_ref == 'POLICY' and reader.calls == 1


@pytest.mark.parametrize('status, expected', [(Status.REVOKED, Reason.POLICY_REVOKED),
                                             (Status.UNKNOWN, Reason.POLICY_UNAVAILABLE)])
def test_noncurrent_policy_deferred_without_fabricating_revision(status, expected):
    recommender, reader = engine(Reader(lambda q: PolicyFact(q, 'SCHOOL_POLICY_AUTHORITY', status, None, None, None, (), '1')))
    result = recommender.recommend(query=QUERY, observations=risk(OCR))
    assert result.disposition is Decision.DEFERRED and result.reason is expected
    assert result.policy_ref is None and reader.calls == 1


@pytest.mark.parametrize('transform', [
    lambda q: current(replace(q, tenant_ref='FOREIGN')),
    lambda q: current(replace(q, grading_run_id='FOREIGN')),
    lambda q: current(q, issuer_ref='FOREIGN_ISSUER'),
    lambda q: current(q, approval_ref=None),
    lambda q: current(q, policy_version=True),
    lambda q: current(q, rules=(PolicyRule(Code.OCR_CONFIDENCE_UNKNOWN, Decision.HUMAN_REVIEW),)),
    lambda q: current(q, rules=(PolicyRule(Code.OCR_CONFIDENCE_UNKNOWN, Decision.HUMAN_REVIEW),)*2),
    lambda q: current(q, rules=(PolicyRule(Code.OCR_CONFIDENCE_UNKNOWN, Decision.DEFERRED),
                               PolicyRule(Code.EVALUATOR_UNCERTAINTY_REPORTED, Decision.HUMAN_REVIEW))),
    lambda q: PolicyFact(q, 'SCHOOL_POLICY_AUTHORITY', Status.REVOKED, 'FAKE', 1, 'FAKE', (), '1'),
    lambda q: current(q, schema_version='99'),
    lambda q: None,
    lambda q: (_ for _ in ()).throw(RuntimeError('PRIVATE_BACKEND_POLICY')),
])
def test_malformed_foreign_missing_or_failed_policy_is_only_unavailable(transform):
    recommender, reader = engine(Reader(transform))
    result = recommender.recommend(query=QUERY, observations=risk(OCR))
    assert result.disposition is Decision.DEFERRED
    assert result.reason is Reason.POLICY_UNAVAILABLE
    assert result.policy_ref is None and reader.calls == 1
    assert 'PRIVATE' not in repr(result)


def test_policy_lookup_mutating_query_does_not_admit_authority():
    def change(q):
        object.__setattr__(q, 'tenant_ref', 'FOREIGN')
        return current(q)
    recommender, reader = engine(Reader(change))
    result = recommender.recommend(query=QUERY, observations=risk(OCR))
    assert result.disposition is Decision.DEFERRED and result.reason is Reason.POLICY_UNAVAILABLE
    assert result.query == QUERY and QUERY.tenant_ref == 'TENANT'
    assert reader.calls == 1


def test_issuer_mutating_existing_observation_does_not_retroactively_mutate_result():
    original = risk(OCR)
    def change(q):
        object.__setattr__(OCR, 'question_id', 'FOREIGN')
        return current(q)
    recommender, reader = engine(Reader(change))
    try:
        result = recommender.recommend(query=QUERY, observations=original)
        assert result.disposition is Decision.HUMAN_REVIEW
        assert result.observations[0].question_id == 'Q1'
        assert reader.calls == 1
    finally:
        object.__setattr__(OCR, 'question_id', 'Q1')


def test_invalid_input_rejected_before_lookup():
    recommender, reader = engine()
    for query, obs in [
        (replace(QUERY, grading_run_id='FOREIGN'), risk(OCR)),
        (replace(QUERY, grading_spec_version=True), risk(OCR)),
        (QUERY, risk(OCR, OCR)),
        (QUERY, RiskObservationSet('1', 'RUN-OTHER', 'SUB', (OCR,))),
        (QUERY, RiskObservationSet('1', 'RUN', 'SUB', (OCR,)*5)),
    ]:
        with pytest.raises(RiskPolicyDenied):
            recommender.recommend(query=query, observations=obs)
    assert reader.calls == 0


def test_foreign_equality_does_not_run_on_policy_fact():
    class Foreign(str):
        def __eq__(self, other):
            raise AssertionError('FOREIGN_EQ_EXECUTED')
    recommender, reader = engine(Reader(lambda q: current(q, issuer_ref=Foreign('SCHOOL_POLICY_AUTHORITY'))))
    result = recommender.recommend(query=QUERY, observations=risk(OCR))
    assert result.reason is Reason.POLICY_UNAVAILABLE and reader.calls == 1


def test_reader_cannot_be_replaced_after_installation():
    recommender, _ = engine()
    with pytest.raises(AttributeError):
        recommender._read = lambda **_: current()
