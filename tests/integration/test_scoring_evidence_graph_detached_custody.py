"""Verify evidence graph detachment during admission and subsequent structural use."""
from copy import deepcopy
from dataclasses import replace

import pytest

from grading.contracts.result import RuleDecision, RuleType
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.result_constituents import (
    CandidateConstituentsDenied,
    CandidateReadiness,
    compose_nonpublishing_constituents,
)
from grading.risk_policy import RecommendationReason, PolicyAuthorityState
from test_result_constituents_provenance import example


def candidate():
    ex, ev, query, rec, reader = example(unknown_ocr=True)
    candidate = compose_nonpublishing_constituents(
        execution=ex, evidence=ev, policy_query=query, recommender=rec)
    assert reader.calls == 1
    return candidate, ex, ev


def test_public_construction_owns_detached_scores():
    original, _, _ = candidate()
    constructed = replace(original)
    assert constructed.paper_score is not original.paper_score
    assert constructed.question_scores[0] is not original.question_scores[0]
    object.__setattr__(original.paper_score.question_results[0], 'final_score',
                       ScoringDecimal.from_raw('123'))
    assert constructed.paper_score.question_results[0].final_score == ScoringDecimal.from_raw('5')
    assert constructed.validated_snapshot().official_result is False


def test_factory_snapshot_is_not_an_alias_of_supplied_execution():
    c, ex, _ = candidate()
    assert c.paper_score is not ex.paper_score
    object.__setattr__(ex.paper_score.question_results[0], 'final_score',
                       ScoringDecimal.from_raw('123'))
    assert c.paper_score.question_results[0].final_score == ScoringDecimal.from_raw('5')
    assert c.validated_snapshot().readiness is CandidateReadiness.INCOMPLETE_UNATTESTED_EXECUTION


@pytest.mark.parametrize('field', ['question_scores', 'paper_score'])
def test_after_return_mutated_nested_graph_cannot_be_structurally_consumed(field):
    c, _, _ = candidate()
    if field == 'question_scores':
        score = c.question_scores[0]
    else:
        score = c.paper_score.question_results[0]
    object.__setattr__(score, 'final_score', ScoringDecimal.from_raw('123'))
    with pytest.raises(CandidateConstituentsDenied) as caught:
        c.validated_snapshot()
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_after_return_mutated_paper_total_not_consumable():
    c, _, _ = candidate()
    object.__setattr__(c.paper_score, 'final_score', ScoringDecimal.from_raw('4'))
    with pytest.raises(CandidateConstituentsDenied):
        c.validated_snapshot()


def test_direct_constructor_detaches_recommendation_observations():
    c, _, _ = candidate()
    copied = replace(c)
    assert copied.review_recommendation is not c.review_recommendation
    assert copied.risk_observations is not c.risk_observations
    assert copied.validated_snapshot().official_result is False


def test_policy_revocation_is_never_promoted_to_authenticated_authority():
    c, _, _ = candidate()
    forged = replace(c.review_recommendation,
                     reason=RecommendationReason.POLICY_REVOKED,
                     disposition=c.review_recommendation.disposition)
    # POLICY_REVOKED is a structurally admitted *claim* only when no policy
    # snapshot exists; this current candidate has a CURRENT policy, so it is
    # inconsistent and must fail public construction.
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, review_recommendation=forged)
    assert c.review_recommendation.authority_state is PolicyAuthorityState.UNVERIFIED_EXTERNAL_AUTHORITY


def test_deepcopy_of_candidate_is_not_promotion():
    c, _, _ = candidate()
    copied = deepcopy(c).validated_snapshot()
    assert copied.official_result is False
    assert copied.readiness is CandidateReadiness.INCOMPLETE_UNATTESTED_EXECUTION


def test_triggered_gate_effect_cannot_lie_about_amount():
    c, _, _ = candidate()
    q = c.paper_score.question_results[0]
    forged_rule = RuleDecision('RULE-GATE', RuleType.GATE, True,
                               ScoringDecimal.from_raw('4'))
    object.__setattr__(q, 'rule_decisions', (forged_rule,))
    object.__setattr__(q.stage_effects[0], 'source_rule_ids', ('RULE-GATE',))
    with pytest.raises(CandidateConstituentsDenied):
        c.validated_snapshot()


def test_invalid_public_constructor_does_not_leak_copy_callback_exception():
    c, _, _ = candidate()
    class Foreign:
        def __deepcopy__(self, memo):
            raise RuntimeError('SECRET_PRIVATE_SOURCE')
    invalid = False
    try:
        replace(c, paper_score=Foreign())
    except CandidateConstituentsDenied as exc:
        invalid = True
        assert 'SECRET_PRIVATE_SOURCE' not in str(exc)
        assert exc.__context__ is None and exc.__cause__ is None
    assert invalid


def test_reported_untriggered_gate_still_requires_configured_effect():
    c, _, _ = candidate()
    q = c.paper_score.question_results[0]
    object.__setattr__(q, 'rule_decisions',
        (RuleDecision('GATE-NO-EFFECT', RuleType.GATE, False, None),))
    with pytest.raises(CandidateConstituentsDenied):
        c.validated_snapshot()


def test_blocked_positive_criterion_cannot_claim_effective_credit():
    c, _, _ = candidate()
    q = c.paper_score.question_results[0]
    decision = RuleDecision('DEPENDENCY-1', RuleType.DEPENDENCY, True, None)
    object.__setattr__(q, 'rule_decisions', (decision,))
    criterion = q.criterion_effects[0]
    object.__setattr__(criterion, 'blocking_dependency_rule_ids', ('DEPENDENCY-1',))
    # The unchanged positive effective contribution contradicts frozen criterion scoring.
    with pytest.raises(CandidateConstituentsDenied):
        c.validated_snapshot()
