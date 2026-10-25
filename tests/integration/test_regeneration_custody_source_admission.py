"""Adversarial tests for bounded source admission during rubric regeneration."""
from dataclasses import replace
import pytest
from grading.rubric.regeneration_custody import CustodyState
from tests.integration.test_rubric_regeneration_custody import (
    QualifiedSourceFixture, AtomicStoreFixture, regenerate,
)

class CopyWitness:
    visits = 0
    def __deepcopy__(self, memo):
        type(self).visits += 1
        return CopyWitness()


def test_invalid_nested_rounding_never_traversed_or_read_source_before_admission():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    generated = replace(source.base)
    object.__setattr__(generated, 'rounding', CopyWitness())
    CopyWitness.visits = 0
    result = regenerate(source, store, generated)
    assert result.state is CustodyState.BLOCKED
    assert CopyWitness.visits == 0, 'pre-work admission allowed invalid nested payload into deepcopy'
    assert source.calls == 0, 'invalid nested generated content should be refused before source contact'
    assert store.calls == 0


def test_missing_top_level_generated_field_must_block_not_throw():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    generated = replace(source.base)
    object.__delattr__(generated, 'criteria')
    result = regenerate(source, store, generated)
    assert result.state is CustodyState.BLOCKED and source.calls == 0 and store.calls == 0


def test_missing_top_level_source_field_must_block_not_throw():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    read = source.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    bad = replace(read.baseline_generated)
    object.__delattr__(bad, 'criteria')
    source.override = replace(read, baseline_generated=bad)
    result = regenerate(source, store)
    assert result.state is CustodyState.BLOCKED and store.calls == 0


def test_genuine_normal_draft_positive_control():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    result = regenerate(source, store)
    assert result.state is CustodyState.STORED and store.calls == 1


def test_bad_actor_positive_denial_control():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    result = regenerate(source, store, actor_ref='unapproved')
    assert result.state is CustodyState.BLOCKED and source.calls == 1 and store.calls == 0

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class FakeNestedLifecycleEvidence:
    wrapped: object
    def __getattr__(self, name):
        return getattr(self.wrapped, name)
    def __post_init__(self):
        pass  # Untrusted shape pretends it is validated provenance


@pytest.mark.parametrize('child_name', ['compilation', 'approval'])
def test_forged_noncontract_nested_lifecycle_evidence_must_not_store(child_name):
    from copy import deepcopy
    from grading.rubric.lifecycle import validate_version, approve_version
    base = QualifiedSourceFixture()
    approved = approve_version(validate_version(base.current, limits=base.limits), teacher_ref='teacher-1')
    child = deepcopy(getattr(approved, child_name))
    object.__setattr__(child, 'version', float(child.version))
    tampered = deepcopy(approved)
    object.__setattr__(tampered, child_name, FakeNestedLifecycleEvidence(child))
    source = QualifiedSourceFixture(current=tampered, limits=base.limits)
    store = AtomicStoreFixture()
    outcome = regenerate(source, store)
    assert outcome.state is CustodyState.BLOCKED and store.calls == 0, (outcome.state, store.calls)
