"""Engine-owned PREPARED resolution; all persistence/authority is SYNTHETIC.

The resolver fixture models a single atomic backend effect protocol. It is not
proof of actual database durability, publication or permission to notify.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Lock

import pytest

from grading.integration.official_result_release import (
    ConditionalReleaseReply, ConditionalReleaseReceipt,
    ProductionGovernedResultRelease, ReleaseOperationIdentity,
    ReleasePurpose, ReleaseState,
)
from tests.integration.test_official_result_release import (
    original_source_rig, no_new_scoring,
)


class AtomicPreparedFixture:
    def __init__(self, backend):
        self.backend = backend
        self.calls = []
        self.mode = 'NORMAL'
        self.lock = Lock()
        self.durable_effects = {}
        self.approved_intents = deepcopy(backend.intent_ledger)

    def resolve_fixed_intent_if_current(self, *, request):
        self.calls.append(request)
        if self.mode == 'TIMEOUT_BEFORE':
            raise TimeoutError('authoritative resolution unavailable')
        if self.mode == 'UNKNOWN':
            return ConditionalReleaseReply(request, ReleaseState.UNKNOWN)
        if self.mode == 'INVALID':
            return ConditionalReleaseReply(request, 'RELEASED')
        if self.mode == 'FOREIGN':
            return ConditionalReleaseReply(replace(request, policy_revision='FOREIGN'),
                                           ReleaseState.RELEASED)
        if self.mode == 'MUTATE_REQUEST':
            object.__setattr__(request, 'policy_revision', 'CHANGED_BY_ADAPTER')
            return ConditionalReleaseReply(request, ReleaseState.RELEASED,
                ConditionalReleaseReceipt(request, 'event', 'authorization', 'issuer', 'generation'))
        if self.mode == 'WRONG_RECEIPT':
            return ConditionalReleaseReply(request, ReleaseState.RELEASED,
                ConditionalReleaseReceipt(replace(request, decision_ref='OTHER'),
                    'event', 'authorization', 'issuer', 'generation'))
        # Simulated transaction: full intent must already be written, and a
        # single persistent original/purpose key admits exactly one effect.
        with self.lock:
            stored = self.backend.intent_ledger.get(request.release_identity)
            if stored != request or self.approved_intents.get(request.release_identity) != request:
                return ConditionalReleaseReply(request, ReleaseState.UNKNOWN)
            if request.release_identity not in self.durable_effects:
                if self.mode == 'DENIED':
                    return ConditionalReleaseReply(request, ReleaseState.DENIED)
                self.durable_effects[request.release_identity] = ConditionalReleaseReceipt(
                    request, 'event-1', 'authorization-1', 'issuer-1', 'generation-1')
            receipt = self.durable_effects[request.release_identity]
        if self.mode == 'LOST_ACK':
            raise TimeoutError('effect committed then acknowledgment lost')
        return ConditionalReleaseReply(request, ReleaseState.RELEASED, receipt)


def scenario(*, purpose=ReleasePurpose.OFFICIAL_RESULT, mode='TIMEOUT_AFTER'):
    graph, source, history, _ = original_source_rig()
    backend = graph[1]
    backend.custody_mode = mode
    before = no_new_scoring(graph)
    initiator = ProductionGovernedResultRelease(
        recovery=graph[2], teacher_review=graph[3],
        feedback_candidate=graph[4], effect_owner=backend,
        intent_custody=backend, original_intent_source=source,
        release_history=history, max_identifier_characters=128)
    original = initiator.transition(purpose=purpose)
    assert original.state is ReleaseState.UNKNOWN and original.intent
    assert not backend.calls and no_new_scoring(graph) == before
    assert backend.intent_ledger.get(original.intent.release_identity) == original.intent
    resolver = AtomicPreparedFixture(backend)

    def new_owner(*, qualified=True, source_override=None):
        return ProductionGovernedResultRelease(
            recovery=graph[2], teacher_review=graph[3],
            feedback_candidate=graph[4], effect_owner=backend,
            intent_custody=backend,
            original_intent_source=source if source_override is None else source_override,
            release_history=history,
            prepared_resolver=resolver if qualified else None,
            max_identifier_characters=128)

    return graph, source, resolver, new_owner, original, before


@pytest.mark.parametrize('purpose', (ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK))
@pytest.mark.parametrize('mode', ('TIMEOUT_AFTER', 'UNKNOWN_AFTER'))
def test_prepared_intent_progresses_from_original_after_restart_without_repeating_writer(purpose, mode):
    graph, source, resolver, new_owner, initial, before = scenario(purpose=purpose, mode=mode)
    next_owner = new_owner()
    out = next_owner.resolve_prepared(release=initial.intent.release_identity)
    assert out.state is ReleaseState.RELEASED and out.intent == initial.intent
    assert out.receipt.intent == initial.intent and len(resolver.durable_effects) == 1
    assert len(resolver.calls) == 1 and len(graph[1].calls) == 0
    assert no_new_scoring(graph) == before
    assert not out.authorizes_publication and not out.authorizes_retry
    # No second effect contact from the same owner, regardless of outcome.
    assert next_owner.resolve_prepared(release=initial.intent.release_identity).state is ReleaseState.UNKNOWN
    assert len(resolver.calls) == 1


def test_prepared_resolver_is_not_ordinary_read_only_reconciliation():
    graph, _, resolver, new_owner, initial, before = scenario()
    owner = new_owner()
    assert owner.reconcile_original(release=initial.intent.release_identity).state is ReleaseState.UNKNOWN
    assert not resolver.calls and no_new_scoring(graph) == before
    assert owner.resolve_prepared(release=initial.intent.release_identity).state is ReleaseState.RELEASED
    assert len(resolver.calls) == 1


def test_no_qualified_resolver_is_a_closed_gate_not_a_fake_positive():
    graph, _, resolver, new_owner, initial, before = scenario()
    assert new_owner(qualified=False).resolve_prepared(
        release=initial.intent.release_identity).state is ReleaseState.UNKNOWN
    assert not resolver.calls and no_new_scoring(graph) == before


@pytest.mark.parametrize('mode', ('TIMEOUT_BEFORE','UNKNOWN','INVALID','FOREIGN','WRONG_RECEIPT','MUTATE_REQUEST','LOST_ACK','DENIED'))
def test_prepared_resolution_outcomes_are_explicit_and_never_trigger_old_writer(mode):
    graph, _, resolver, new_owner, initial, before = scenario()
    resolver.mode = mode
    owner = new_owner()
    out = owner.resolve_prepared(release=initial.intent.release_identity)
    assert out.state is (ReleaseState.DENIED if mode == 'DENIED' else ReleaseState.UNKNOWN)
    assert out.intent == initial.intent and out.receipt is None
    assert len(resolver.calls) == 1 and len(graph[1].calls) == 0
    assert no_new_scoring(graph) == before
    resolver.mode = 'NORMAL'
    assert owner.resolve_prepared(release=initial.intent.release_identity).state is ReleaseState.UNKNOWN
    assert len(resolver.calls) == 1


@pytest.mark.parametrize('mutation', ('DIFFERENT_POLICY', 'DIFFERENT_PURPOSE', 'DIFFERENT_RESULT', 'MISSING', 'UNAVAILABLE'))
def test_no_foreign_changed_or_unknown_original_can_reach_resolver(mutation):
    graph, source, resolver, new_owner, initial, before = scenario()
    key = initial.intent.release_identity
    if mutation == 'DIFFERENT_POLICY':
        graph[1].intent_ledger[key] = replace(initial.intent, policy_revision='OTHER')
    elif mutation == 'DIFFERENT_PURPOSE':
        source.mode = 'WRONG_PURPOSE'
    elif mutation == 'DIFFERENT_RESULT':
        source.mode = 'FOREIGN'
    elif mutation == 'MISSING':
        del graph[1].intent_ledger[key]
    elif mutation == 'UNAVAILABLE':
        source.mode = 'TIMEOUT'
    out = new_owner().resolve_prepared(release=key)
    if mutation == 'DIFFERENT_POLICY':
        # The historical source is not itself the current policy issuer; the
        # independent atomic backend must reject a replaced decision.
        assert out.state is ReleaseState.UNKNOWN
        assert not resolver.durable_effects
    else:
        assert out.state is ReleaseState.UNKNOWN
        assert resolver.calls == []
    assert graph[1].calls == [] and no_new_scoring(graph) == before


def test_two_independent_owners_converge_on_one_durable_original_effect():
    graph, _, resolver, new_owner, initial, before = scenario()
    owners = (new_owner(), new_owner())
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = tuple(pool.map(lambda o: o.resolve_prepared(release=initial.intent.release_identity), owners))
    # Current teacher review/authorized result release/governed scored-paper handoff revalidation uses fail-closed, nonblocking read-only
    # consumers. One overlapping owner may receive UNKNOWN under contention,
    # but that is never a second publication permit. At least one progresses;
    # a later distinct owner can resolve the SAME durable intent.
    assert a.state in (ReleaseState.RELEASED, ReleaseState.UNKNOWN)
    assert b.state in (ReleaseState.RELEASED, ReleaseState.UNKNOWN)
    assert ReleaseState.RELEASED in (a.state, b.state)
    assert 1 <= len(resolver.calls) <= 2
    assert len(resolver.durable_effects) == 1
    assert new_owner().resolve_prepared(release=initial.intent.release_identity).state is ReleaseState.RELEASED
    assert len(resolver.durable_effects) == 1
    assert graph[1].calls == [] and no_new_scoring(graph) == before


def test_backend_conflicting_immutable_request_must_never_commit():
    graph, _, resolver, new_owner, initial, before = scenario()
    owner = new_owner()
    original_key = initial.intent.release_identity
    # Simulates a conflicting stored original for this same key, rather than
    # authorizing a new generation on the same release identity.
    graph[1].intent_ledger[original_key] = replace(initial.intent, policy_revision='OTHER')
    resolver.mode = 'NORMAL'
    output = owner.resolve_prepared(release=original_key)
    assert output.state is ReleaseState.UNKNOWN
    assert output.intent.policy_revision == 'OTHER'
    assert resolver.durable_effects == {}
    assert len(graph[1].calls) == 0


def test_invalid_operation_key_rejected_before_effect_capable_resolution():
    _, _, resolver, new_owner, _, _ = scenario()
    with pytest.raises(ValueError):
        new_owner().resolve_prepared(release='NOT_A_RELEASE_ID')
    assert resolver.calls == []


def test_malformed_resolver_signature_refused_at_installation():
    graph, source, _, _, _, _ = scenario()
    class WrongSignature:
        def resolve_fixed_intent_if_current(self, not_request):
            raise AssertionError('cannot be invoked')
    with pytest.raises((TypeError, ValueError)):
        ProductionGovernedResultRelease(
            recovery=graph[2], teacher_review=graph[3],
            feedback_candidate=graph[4], effect_owner=graph[1],
            original_intent_source=source, prepared_resolver=WrongSignature(),
            max_identifier_characters=128)


def test_fresh_owner_resolves_previously_lost_resolution_ack_without_second_effect():
    graph, _, resolver, new_owner, initial, before = scenario()
    key = initial.intent.release_identity
    resolver.mode = 'LOST_ACK'
    assert new_owner().resolve_prepared(release=key).state is ReleaseState.UNKNOWN
    assert len(resolver.durable_effects) == 1
    resolver.mode = 'NORMAL'
    result = new_owner().resolve_prepared(release=key)
    assert result.state is ReleaseState.RELEASED
    assert len(resolver.calls) == 2 and len(resolver.durable_effects) == 1
    assert not graph[1].calls and no_new_scoring(graph) == before
