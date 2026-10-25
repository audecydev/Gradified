"""Hostile durability/read-only student-safe feedback admission against the installed release owner.

These are synthetic issuer fixtures, not school/backend authenticity evidence.
A durable history can contain structurally plausible but noncanonical records;
reconciliation must not launder them into a RELEASED observation.
"""
from dataclasses import replace

import pytest

from grading.integration.official_result_release import ReleasePurpose, ReleaseState
from grading.integration.student_safe_feedback import FeedbackCategory
from tests.integration.test_official_result_release import original_source_rig


@pytest.mark.parametrize('mutation', (
    {'message': 'The teacher approved a failing grade.'},
    {'category': 'UNVERIFIED_DIAGNOSIS'},
    {'category': 'CONCEPTUAL_ERROR'},  # str/Enum equality is NOT exact type
    {'criterion_ref': None},
    {'evidence_ref': None},
    {'criterion_ref': 'X' * 129},
))
def test_restart_history_rejects_forged_or_malformed_student_feedback(mutation):
    r, source, history, make_owner = original_source_rig()
    prior = make_owner().transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert prior.state is ReleaseState.RELEASED
    assert type(prior.intent.feedback.category) is FeedbackCategory
    assert len(r[1].calls) == 1
    corrupted = replace(prior.intent,
                        feedback=replace(prior.intent.feedback, **mutation))
    assert corrupted.release_identity == prior.intent.release_identity
    r[1].intent_ledger[prior.intent.release_identity] = corrupted  # corrupt synthetic persisted original
    latest = make_owner().reconcile_original(release=prior.intent.release_identity)
    assert latest.state is ReleaseState.UNKNOWN
    assert latest.receipt is None
    assert len(r[1].calls) == 1


def test_restart_history_preserves_valid_fixed_student_feedback():
    r, source, history, make_owner = original_source_rig()
    prior = make_owner().transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert prior.state is ReleaseState.RELEASED
    outcome = make_owner().reconcile_original(release=prior.intent.release_identity)
    assert outcome.state is ReleaseState.RELEASED
    assert outcome.receipt.intent == prior.intent
    assert len(r[1].calls) == 1


def test_release_recovery_vocabulary_matches_upstream_fixed_g10_formatter():
    from grading.integration.official_result_release import _CANONICAL_RELEASE_FEEDBACK_MESSAGES
    from grading.integration.student_safe_feedback import (
        ConfirmedErrorEvidence, student_safe_feedback,
    )
    for category, message in _CANONICAL_RELEASE_FEEDBACK_MESSAGES.items():
        actual = student_safe_feedback(
            question_id='Q1',
            error=ConfirmedErrorEvidence(category, 'C1', 'E1', 'synthetic-only'),
            admitted_criterion_refs=('C1',), admitted_evidence_refs=('E1',),
            max_identifier_characters=128)
        assert actual.message == message
    assert set(_CANONICAL_RELEASE_FEEDBACK_MESSAGES) == (
        set(FeedbackCategory) - {FeedbackCategory.UNKNOWN, FeedbackCategory.NOT_APPLICABLE}
    )
