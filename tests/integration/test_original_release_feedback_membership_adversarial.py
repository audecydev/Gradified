"""Hostile student-safe feedback fixed-scored-question continuity in historical release consumers.

A syntactically plausible stored intent is NOT proof that its feedback question
belongs to the immutable scored question set. Fixtures below are synthetic;
backend authenticity/atomic durability remain separate requirements.
"""
from dataclasses import replace

from grading.integration.official_result_release import ReleasePurpose, ReleaseState
from tests.integration.test_official_result_release import original_source_rig
from tests.integration.test_prepared_release_resolution import scenario


def _foreign_scored_question(intent):
    original_feedback = intent.feedback
    assert original_feedback is not None
    foreign = replace(original_feedback, question_id='NOT_SCORED',
                      original=replace(original_feedback.original, question_id='NOT_SCORED'))
    return replace(intent, feedback=foreign)


def test_restarted_read_only_history_rejects_feedback_for_unscored_question():
    graph, source, history, make_owner = original_source_rig()
    first = make_owner().transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert first.state is ReleaseState.RELEASED
    assert graph[2].recover().scored_question_ids == ('Q1',)
    foreign = _foreign_scored_question(first.intent)
    assert foreign.release_identity == first.intent.release_identity
    graph[1].intent_ledger[first.intent.release_identity] = foreign
    # Model a historical source and receipt that agree with each other but
    # disagree with the independently recovered scored original.
    graph[1].calls.append(foreign)
    before = len(graph[1].calls)
    out = make_owner().reconcile_original(release=first.intent.release_identity)
    assert out.state is ReleaseState.UNKNOWN
    assert out.receipt is None
    assert len(graph[1].calls) == before
    assert history.requests == []  # Reject BEFORE relying on history receipt.


def test_prepared_effect_resolver_never_contacts_backend_for_unscored_feedback():
    graph, _, resolver, new_owner, initial, _ = scenario(
        purpose=ReleasePurpose.STUDENT_FEEDBACK, mode='TIMEOUT_AFTER')
    foreign = _foreign_scored_question(initial.intent)
    assert graph[2].recover().scored_question_ids == ('Q1',)
    assert foreign.release_identity == initial.intent.release_identity
    graph[1].intent_ledger[initial.intent.release_identity] = foreign
    resolver.approved_intents[initial.intent.release_identity] = foreign
    out = new_owner().resolve_prepared(release=initial.intent.release_identity)
    assert out.state is ReleaseState.UNKNOWN
    assert out.receipt is None
    assert resolver.calls == []  # No effect-capable contact.
    assert graph[1].calls == []
