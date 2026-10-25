"""Verify regeneration recovery rejects locally inconsistent governed results."""
from copy import deepcopy
import pytest
from grading.rubric.regeneration_custody import (CustodyState, DraftWriteReceipt, DraftWriteState, recover_regeneration_write)
from tests.integration.test_rubric_regeneration_custody import QualifiedSourceFixture, AtomicStoreFixture, regenerate

class StrSubclass(str):
    pass

class EchoHistoricalStore:
    """Deliberately unqualified receipt echo; forces local admission to do its job."""
    def __init__(self): self.lookups = 0
    def lookup_operation(self, request):
        self.lookups += 1
        return DraftWriteReceipt(DraftWriteState.COMMITTED, request)

def genuine():
    out = regenerate(QualifiedSourceFixture(), AtomicStoreFixture())
    assert out.state is CustodyState.STORED
    return deepcopy(out.request)

@pytest.mark.parametrize('malformed', [None, object(), 4], ids=['none', 'object', 'integer'])
def test_non_authoring_content_blocked_before_lookup(malformed):
    original = genuine(); store = EchoHistoricalStore()
    object.__setattr__(original.draft, 'content', malformed)
    out = recover_regeneration_write(store=store, original=original)
    assert out.state is CustodyState.BLOCKED and store.lookups == 0

@pytest.mark.parametrize('field', ['rubric_id','policy_id'])
def test_nested_top_level_equal_value_invalid_str_blocked(field):
    original = genuine(); store = EchoHistoricalStore()
    content=original.draft.content
    object.__setattr__(content,field,StrSubclass(getattr(content,field)))
    out=recover_regeneration_write(store=store, original=original)
    assert out.state is CustodyState.BLOCKED and store.lookups == 0

@pytest.mark.parametrize('field', ['criterion_id','operational_description','evidence_requirement'])
def test_nested_criterion_equal_value_invalid_str_blocked(field):
    original=genuine(); store=EchoHistoricalStore()
    criterion=original.draft.content.criteria[0]
    object.__setattr__(criterion,field,StrSubclass(getattr(criterion,field)))
    out=recover_regeneration_write(store=store, original=original)
    assert out.state is CustodyState.BLOCKED and store.lookups == 0

def test_valid_history_still_recoverable():
    original=genuine(); store=EchoHistoricalStore()
    out=recover_regeneration_write(store=store, original=original)
    assert out.state is CustodyState.STORED and store.lookups == 1
