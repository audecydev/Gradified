"""Recovery must admit original draft content before cross-record equality."""
from copy import deepcopy
from grading.rubric.regeneration_custody import CustodyState, recover_regeneration_write
from tests.integration.test_rubric_regeneration_custody import (
    QualifiedSourceFixture, AtomicStoreFixture, regenerate,
)

class PoisonEquality:
    calls = 0
    def __eq__(self, other):  # noqa: D105 — must never be invoked
        type(self).calls += 1
        raise RuntimeError('foreign equality executed before validated admission')

class LookupSpy:
    def __init__(self, backend): self.backend=backend; self.lookups=0
    def lookup_operation(self, original):
        self.lookups += 1
        return self.backend.lookup_operation(original)

def original_operation():
    db=AtomicStoreFixture()
    initial=regenerate(QualifiedSourceFixture(),db)
    assert initial.state is CustodyState.STORED
    return deepcopy(initial.request), db

def test_malformed_original_must_block_without_untrusted_eq_or_lookup():
    request,db=original_operation()
    PoisonEquality.calls=0
    object.__setattr__(request.draft.content,'policy_id',PoisonEquality())
    spy=LookupSpy(db)
    result=recover_regeneration_write(store=spy,original=request)
    assert result.state is CustodyState.BLOCKED
    assert spy.lookups==0 and PoisonEquality.calls==0

def test_genuine_original_recovers_using_read_only_lookup():
    request,db=original_operation()
    spy=LookupSpy(db)
    result=recover_regeneration_write(store=spy,original=request)
    assert result.state is CustodyState.STORED
    assert spy.lookups==1 and db.calls==1

def test_malformed_version_denied_without_lookup():
    request,db=original_operation()
    object.__setattr__(request.draft,'version',2.0)
    spy=LookupSpy(db)
    result=recover_regeneration_write(store=spy,original=request)
    assert result.state is CustodyState.BLOCKED
    assert spy.lookups==0


class HostileHashEquality:
    calls = 0

    def __eq__(self, other):
        type(self).calls += 1
        raise RuntimeError("recovered hash equality must not execute")


def test_malformed_recovered_source_hash_rejected_before_comparison_or_lookup():
    request, db = original_operation()
    HostileHashEquality.calls = 0
    object.__setattr__(request.draft, 'source_content_hash', HostileHashEquality())
    spy = LookupSpy(db)
    assert recover_regeneration_write(store=spy, original=request).state is CustodyState.BLOCKED
    assert spy.lookups == 0 and HostileHashEquality.calls == 0


def test_malformed_recovered_question_hash_rejected_before_comparison_or_lookup():
    request, db = original_operation()
    HostileHashEquality.calls = 0
    object.__setattr__(request.draft, 'finalized_question_hash', HostileHashEquality())
    spy = LookupSpy(db)
    assert recover_regeneration_write(store=spy, original=request).state is CustodyState.BLOCKED
    assert spy.lookups == 0 and HostileHashEquality.calls == 0
