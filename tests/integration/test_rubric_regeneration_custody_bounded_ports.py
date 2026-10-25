"""governed result checks bounded prework and non-aliased effect-port regressions.

External store/source fixtures here are not proof of real atomic storage.
"""
from dataclasses import replace

from grading.rubric.regeneration_custody import (
    CustodyState, DraftWriteReceipt, DraftWriteState,
    recover_regeneration_write,
)
from tests.integration.test_rubric_regeneration_custody import (
    AtomicStoreFixture, QualifiedSourceFixture, regenerate,
)


def test_nested_oversize_levels_rejected_before_deepcopy(monkeypatch):
    import grading.rubric.regeneration_custody as owner
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    base = source.base
    level = base.criteria[0].performance_levels[0]
    oversized = replace(base.criteria[0], performance_levels=(level,) * 1000)
    generated = replace(base, criteria=(oversized, base.criteria[1]))
    attempted = []
    original_copy = owner.deepcopy
    def traced_copy(value):
        attempted.append(value is generated)
        return original_copy(value)
    monkeypatch.setattr(owner, 'deepcopy', traced_copy)
    result = regenerate(source, store, generated)
    assert result.state is CustodyState.BLOCKED
    assert True not in attempted and source.calls == 0 and store.calls == 0


def test_oversized_nested_rule_conditions_not_copied(monkeypatch):
    import grading.rubric.regeneration_custody as owner
    from grading.rubric.models import AuthoringCriterionCondition, AuthoringGateRule
    from tests.support.rubric_authoring import sd
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    condition = AuthoringCriterionCondition('C1', ('L1',))
    gate = AuthoringGateRule('R1', (condition,) * 1000, sd(0))
    generated = replace(source.base, gates=(gate,))
    original_copy = owner.deepcopy
    copied = []
    def traced_copy(value):
        copied.append(value is generated)
        return original_copy(value)
    monkeypatch.setattr(owner, 'deepcopy', traced_copy)
    result = regenerate(source, store, generated)
    assert result.state is CustodyState.BLOCKED
    assert True not in copied and source.calls == 0 and store.calls == 0


def test_write_callback_receives_detached_request_and_keeps_original():
    source = QualifiedSourceFixture()
    class MutatingStore(AtomicStoreFixture):
        def compare_and_persist(self, request):
            self.calls += 1
            self.seen = request
            object.__setattr__(request.draft, 'version', 123456)
            return DraftWriteReceipt(DraftWriteState.COMMITTED, request)
    store = MutatingStore()
    result = regenerate(source, store)
    assert result.state is CustodyState.UNKNOWN
    assert result.request.draft.version == 2
    assert store.seen is not result.request
    assert store.seen.authority is not result.request.authority
    assert source.current.version == 1
    assert store.calls == 1


def test_lookup_callback_cannot_mutate_original_request():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    stored = regenerate(source, store)
    assert stored.state is CustodyState.STORED
    original = stored.request
    class MutatingLookup(AtomicStoreFixture):
        def lookup_operation(self, request):
            self.lookups += 1
            assert request is not original
            object.__setattr__(request.approved_limits, 'max_criteria', 12345)
            return DraftWriteReceipt(DraftWriteState.COMMITTED, request)
    lookup = MutatingLookup()
    result = recover_regeneration_write(store=lookup, original=original)
    assert result.state is CustodyState.UNKNOWN
    assert result.request.approved_limits.max_criteria == original.approved_limits.max_criteria
    assert lookup.lookups == 1
