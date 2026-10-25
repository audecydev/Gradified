"""Verify nested lint provenance admission before governed result comparisons."""
from copy import deepcopy
import pytest
from grading.rubric.lifecycle import validate_version, approve_version
from grading.rubric.regeneration_custody import CustodyState, recover_regeneration_write
from tests.integration.test_rubric_regeneration_custody import (
    QualifiedSourceFixture, AtomicStoreFixture, regenerate,
)

class PoisonIssues:
    calls = 0
    def __iter__(self):
        type(self).calls += 1
        raise RuntimeError('unadmitted lint evidence iterator executed')


def test_invalid_lint_issues_before_write_must_block_without_iteration():
    src = QualifiedSourceFixture()
    version = validate_version(src.current, limits=src.limits)
    object.__setattr__(version.compilation.lint_result, 'issues', PoisonIssues())
    src = QualifiedSourceFixture(current=version, limits=src.limits)
    store = AtomicStoreFixture()
    PoisonIssues.calls = 0
    result = regenerate(src, store)
    assert result.state is CustodyState.BLOCKED
    assert store.calls == 0 and PoisonIssues.calls == 0


def test_invalid_lint_issues_during_recovery_must_block_without_lookup():
    src, store = QualifiedSourceFixture(), AtomicStoreFixture()
    original = regenerate(src,store)
    assert original.state is CustodyState.STORED
    request = deepcopy(original.request)
    approved = approve_version(validate_version(request.authority.current_teacher,limits=src.limits),teacher_ref='teacher-1')
    # Retain the original request structure, but supply an altered source-compilation
    # inside a version of the correct outer dataclass type.
    object.__setattr__(approved.compilation.lint_result,'issues',PoisonIssues())
    object.__setattr__(request.authority,'current_teacher',approved)
    PoisonIssues.calls = 0
    pre = store.lookups
    result = recover_regeneration_write(store=store,original=request)
    assert result.state is CustodyState.BLOCKED
    assert store.lookups == pre and PoisonIssues.calls == 0


def test_genuine_validated_source_success():
    src=QualifiedSourceFixture()
    validated=validate_version(src.current,limits=src.limits)
    src=QualifiedSourceFixture(current=validated,limits=src.limits)
    store=AtomicStoreFixture(); store.current_ref='current-1'
    outcome=regenerate(src,store)
    assert outcome.state is CustodyState.STORED and store.calls==1


def test_genuine_original_recovery_success():
    src,store=QualifiedSourceFixture(),AtomicStoreFixture()
    outcome=regenerate(src,store)
    assert outcome.state is CustodyState.STORED
    before=store.lookups
    recovered=recover_regeneration_write(store=store,original=deepcopy(outcome.request))
    assert recovered.state is CustodyState.STORED and store.lookups==before+1
