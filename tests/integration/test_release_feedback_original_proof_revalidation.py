"""Independent student-safe feedback historical-proof continuity against fixed-original release.

Synthetic sources intentionally accept corrupted stored intents so that the
engine-owned pre-effect admission, not a benevolent fixture, must reject them.
No fixture grants real school authority or backend durability.
"""
from dataclasses import replace

import pytest

from grading.integration.official_result_release import (
    ReleasePurpose, ReleaseState, _CANONICAL_RELEASE_FEEDBACK_MESSAGES,
)
from grading.integration.student_safe_feedback import FeedbackCategory
from tests.integration.test_official_result_release import original_source_rig
from tests.integration.test_prepared_release_resolution import scenario


def _alter(intent, mutation):
    assert intent.feedback is not None
    if mutation == 'criterion':
        return replace(intent, feedback=replace(intent.feedback, criterion_ref='BOGUS_C'))
    if mutation == 'evidence':
        return replace(intent, feedback=replace(intent.feedback, evidence_ref='BOGUS_E'))
    if mutation == 'category':
        category = FeedbackCategory.FORMULA_ERROR
        assert category is not intent.feedback.category
        return replace(intent, feedback=replace(
            intent.feedback, category=category,
            message=_CANONICAL_RELEASE_FEEDBACK_MESSAGES[category]))
    if mutation == 'binding':
        return replace(intent, feedback_binding_revision='FOREIGN_GENERATION')
    raise AssertionError(mutation)


@pytest.mark.parametrize('mutation', ('criterion', 'evidence', 'category', 'binding'))
def test_historical_read_only_observation_does_not_launder_unconfirmed_g10_proof(mutation):
    graph, _, history, make_owner = original_source_rig()
    legitimate = make_owner().transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert legitimate.state is ReleaseState.RELEASED
    corrupted = _alter(legitimate.intent, mutation)
    assert corrupted.release_identity == legitimate.intent.release_identity
    graph[1].intent_ledger[legitimate.intent.release_identity] = corrupted
    # Simulate matching durable historic result even when original proof is forged.
    graph[1].calls.append(corrupted)
    before = len(history.requests)
    result = make_owner().reconcile_original(release=legitimate.intent.release_identity)
    assert result.state is ReleaseState.UNKNOWN
    assert result.receipt is None
    assert len(history.requests) == before  # reject before trusting receipt


@pytest.mark.parametrize('mutation', ('criterion', 'evidence', 'category', 'binding'))
def test_prepared_release_cannot_apply_unconfirmed_g10_proof(mutation):
    graph, _, resolver, new_owner, initial, before = scenario(
        purpose=ReleasePurpose.STUDENT_FEEDBACK, mode='TIMEOUT_AFTER')
    key = initial.intent.release_identity
    corrupted = _alter(initial.intent, mutation)
    graph[1].intent_ledger[key] = corrupted
    resolver.approved_intents[key] = corrupted
    result = new_owner().resolve_prepared(release=key)
    assert result.state is ReleaseState.UNKNOWN
    assert result.receipt is None
    assert resolver.calls == []  # no effect-capable callback
    assert resolver.durable_effects == {}
    assert graph[1].calls == []  # no legacy commit


def test_prepared_release_cannot_apply_stale_confirmed_error_after_source_unavailable():
    graph, _, resolver, new_owner, initial, _ = scenario(
        purpose=ReleasePurpose.STUDENT_FEEDBACK, mode='TIMEOUT_AFTER')
    graph[13].mode = 'ABSENT'  # independent academic confirmation no longer available
    result = new_owner().resolve_prepared(release=initial.intent.release_identity)
    assert result.state is ReleaseState.UNKNOWN
    assert resolver.calls == []
    assert resolver.durable_effects == {}


def test_same_original_valid_feedback_remains_reconcilable_and_resolvable():
    graph, _, history, make_owner = original_source_rig()
    initial = make_owner().transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert initial.state is ReleaseState.RELEASED
    historical = make_owner().reconcile_original(release=initial.intent.release_identity)
    assert historical.state is ReleaseState.RELEASED
    assert historical.receipt is not None and historical.receipt.intent == initial.intent
    graph, _, resolver, new_owner, initial, _ = scenario(
        purpose=ReleasePurpose.STUDENT_FEEDBACK, mode='TIMEOUT_AFTER')
    applied = new_owner().resolve_prepared(release=initial.intent.release_identity)
    assert applied.state is ReleaseState.RELEASED
    assert applied.receipt is not None and len(resolver.durable_effects) == 1
