"""Verify release write-ahead producer and consumer agree on in-memory custody.

These fixtures do not prove durable persistence, issuer authentication, or publication authority."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from grading.integration.official_result_release import (
    ProductionGovernedResultRelease,
    ReleaseIntentEstablishmentReply, ReleaseIntentEstablishmentState,
    ReleasePurpose, ReleaseState,
)
from tests.integration.test_official_result_release import (
    original_source_rig, rig,
)


def test_no_write_ahead_installation_fails_closed_even_with_valid_governance():
    r = rig()
    owner = ProductionGovernedResultRelease(
        recovery=r[2], teacher_review=r[3], feedback_candidate=r[4],
        effect_owner=r[1], max_identifier_characters=128)
    response = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert response.state is ReleaseState.UNKNOWN and response.intent is not None
    assert r[1].calls == [] and r[1].establish_calls == []


@pytest.mark.parametrize('purpose', (ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK))
def test_real_captured_writer_sees_exact_previously_established_original(purpose):
    r = rig()
    backend = r[1]
    assert backend.intent_ledger == {}

    def verify_before_effect(request):
        assert backend.intent_ledger[request.release_identity] == request
        assert len(backend.establish_calls) == 1

    backend.on_commit = verify_before_effect
    output = r[0].transition(purpose=purpose)
    assert output.state is ReleaseState.RELEASED
    assert backend.intent_ledger[output.intent.release_identity] == output.intent
    assert len(backend.calls) == len(backend.establish_calls) == 1


@pytest.mark.parametrize('mode,established', (
    ('TIMEOUT_BEFORE', False), ('TIMEOUT_AFTER', True),
    ('UNKNOWN_AFTER', True), ('MALFORMED', False), ('FOREIGN', False),
))
def test_ambiguous_or_malformed_custody_never_calls_release_writer(mode, established):
    r = rig()
    backend = r[1]
    backend.custody_mode = mode
    outcome = r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert outcome.state is ReleaseState.UNKNOWN
    assert outcome.original and outcome.intent
    assert not backend.calls
    assert bool(backend.intent_ledger) is established
    backend.custody_mode = 'NORMAL'
    assert r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert not backend.calls and len(backend.establish_calls) == 1


def test_writer_sees_immutable_snapshot_even_if_it_mutates_original_argument():
    r = rig()
    backend = r[1]

    def change(request):
        object.__setattr__(request, 'policy_revision', 'SPOOFED')

    backend.on_commit = change
    response = r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert response.state is ReleaseState.UNKNOWN
    assert backend.intent_ledger[response.intent.release_identity] == response.intent
    assert backend.calls and len(backend.calls) == 1
    assert r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert len(backend.calls) == 1


@pytest.mark.parametrize('mutate', ('IDENTICAL','CHANGED_POLICY', 'CHANGED_DECISION'))
def test_existing_prepared_intent_or_conflict_never_reissues_release(mutate):
    r, source, history, make_owner = original_source_rig()
    backend = r[1]
    # A completed first release generates a real previously established intent.
    first = make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert first.state is ReleaseState.RELEASED
    key = first.intent.release_identity
    assert key in backend.intent_ledger
    if mutate == 'CHANGED_POLICY':
        backend.intent_ledger[key] = replace(first.intent, policy_revision='OTHER')
    elif mutate == 'CHANGED_DECISION':
        backend.intent_ledger[key] = replace(first.intent, decision_ref='OTHER')
    next_result = make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert next_result.state is ReleaseState.UNKNOWN
    assert len(backend.calls) == 1  # no repeated publication contact


def test_prepared_but_uncontacted_original_remains_recoverable_without_claiming_release():
    r, source, history, make_owner = original_source_rig()
    backend = r[1]
    backend.custody_mode = 'TIMEOUT_AFTER'
    attempt = make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert attempt.state is ReleaseState.UNKNOWN and not backend.calls
    assert backend.intent_ledger[attempt.intent.release_identity] == attempt.intent
    backend.custody_mode = 'NORMAL'
    # A new process must not infer from the absent release receipt that the
    # same identity is free to send again. Only qualified external resolution
    # may authorize continuation of an already-established intent.
    later = make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert later.state is ReleaseState.UNKNOWN and not backend.calls


def test_two_distinct_workers_atomic_custody_simulation_one_release_writer():
    r, source, history, make_owner = original_source_rig()
    backend = r[1]
    owners = [make_owner(), make_owner()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(o.transition, purpose=ReleasePurpose.OFFICIAL_RESULT) for o in owners]
        results = [j.result() for j in jobs]
    assert sorted(x.state.value for x in results) == ['RELEASED', 'UNKNOWN']
    assert len(backend.calls) == 1
    assert len(backend.establish_calls) == 1  # read-only preflight catches second
    assert len(backend.intent_ledger) == 1


def test_custody_atomic_compare_stops_two_workers_without_original_selection():
    r = rig()
    other = rig()  # distinct FIRST/scoring owner graph, identical exact original
    backend = r[1]
    assert r[2]._target.__self__.identity == other[2]._target.__self__.identity
    def fresh(graph):
        return ProductionGovernedResultRelease(
            recovery=graph[2], teacher_review=graph[3], feedback_candidate=graph[4],
            effect_owner=backend, intent_custody=backend, max_identifier_characters=128)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(fresh(r).transition, purpose=ReleasePurpose.OFFICIAL_RESULT)
        b = pool.submit(fresh(other).transition, purpose=ReleasePurpose.OFFICIAL_RESULT)
        results = [a.result(), b.result()]
    assert sorted(x.state.value for x in results) == ['RELEASED', 'UNKNOWN']
    assert len(backend.establish_calls) == 2 and len(backend.calls) == 1


def test_separate_purposes_establish_distinct_intents_without_cross_publication():
    r = rig()
    backend = r[1]
    official = r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    feedback = r[0].transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert official.state is feedback.state is ReleaseState.RELEASED
    assert len(backend.intent_ledger) == 2
    assert set(key.purpose for key in backend.intent_ledger) == {
        ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK}
    assert official.intent.feedback is None and feedback.intent.feedback is not None


def test_malformed_establishment_enums_and_foreign_snapshot_are_not_authority():
    r = rig()
    backend = r[1]
    backend.custody_mode = 'MALFORMED'
    response = r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert response.state is ReleaseState.UNKNOWN
    assert backend.calls == []


def test_authoritative_receipt_reconciliation_does_not_reestablish_or_send():
    r, source, history, make_owner = original_source_rig()
    backend = r[1]
    backend.mode = 'LOST_ACK'
    first = make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert first.state is ReleaseState.UNKNOWN
    established = len(backend.establish_calls)
    restored = make_owner().reconcile_original(release=first.intent.release_identity)
    assert restored.state is ReleaseState.RELEASED
    assert restored.intent == first.intent
    assert len(backend.calls) == 1 and len(backend.establish_calls) == established


def test_precontact_invalid_academic_source_does_not_establish_an_intent():
    r = rig()
    from grading.integration.teacher_review_journal import TeacherReviewRecoveryState
    r[7].state = TeacherReviewRecoveryState.UNKNOWN
    assert r[0].transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert r[1].establish_calls == [] and r[1].calls == []
