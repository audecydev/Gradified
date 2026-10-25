"""New independent governed result checks custody checks; exercise candidate source unchanged."""
from dataclasses import replace
import pytest
from grading.rubric.models import QuestionRubricAuthoringContent, FinalizedQuestionScoringBasis
from grading.rubric.regeneration_custody import CustodyState, propose_and_persist_regeneration
from tests.integration.test_rubric_regeneration_custody import (
    QualifiedSourceFixture, AtomicStoreFixture, regenerate
)


def test_valid_genuine_draft_positive_control():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    result = regenerate(source, store)
    assert result.state is CustodyState.STORED
    assert store.calls == 1 and result.request.draft.approval is None


def test_invalid_actor_negative_control():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    result = regenerate(source, store, actor_ref='not-authorized')
    assert result.state is CustodyState.BLOCKED and store.calls == 0


def test_untrusted_source_record_malformed_baseline_criteria_is_denied_not_uncaught_typeerror():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    fresh = replace(source.base, criteria=(replace(source.base.criteria[0], evidence_requirement='fresh'), source.base.criteria[1]))
    admitted = source.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    malformed = replace(admitted.baseline_generated)
    object.__setattr__(malformed, 'criteria', 37)
    source.override = replace(admitted, baseline_generated=malformed)
    result = regenerate(source, store, fresh)
    assert result.state is CustodyState.BLOCKED and store.calls == 0


def test_untrusted_source_record_malformed_current_teacher_criteria_is_denied_not_uncaught_typeerror():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    admitted = source.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    invalid_content = replace(admitted.current_teacher.content)
    object.__setattr__(invalid_content, 'criteria', 37)
    # Frozen dataclass can still be altered by an installed source callback.
    from copy import deepcopy
    bad_current = deepcopy(admitted.current_teacher)
    object.__setattr__(bad_current, 'content', invalid_content)
    source.override = replace(admitted, current_teacher=bad_current)
    result = regenerate(source, store)
    assert result.state is CustodyState.BLOCKED and store.calls == 0


def test_oversize_generated_criteria_rejected_without_deep_copy_before_finite_admission(monkeypatch):
    import grading.rubric.regeneration_custody as owner
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    generated = replace(source.base, criteria=source.base.criteria * 500)
    assert len(generated.criteria) > source.limits.max_criteria
    orig_copy=owner.deepcopy
    attempted=[]
    def traced_copy(value):
        attempted.append(value is generated)
        return orig_copy(value)
    monkeypatch.setattr(owner,'deepcopy',traced_copy)
    result = regenerate(source, store, generated)
    assert result.state is CustodyState.BLOCKED
    assert True not in attempted, "oversized generated data was copied before cardinality admission"
    assert store.calls == 0


def test_oversize_academic_question_basis_not_fingerprinted_before_budget_admission(monkeypatch):
    import grading.rubric.regeneration_custody as owner
    from copy import deepcopy
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    original = source.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    bad_question = replace(original.finalized_question, question_id='Q'*1_000_000)
    current = deepcopy(original.current_teacher)
    object.__setattr__(current, 'finalized_question', bad_question)
    source.override = replace(original, finalized_question=bad_question, current_teacher=current)
    invoked=[]
    fingerprint=owner.finalized_question_fingerprint
    def spy(basis):
        invoked.append(len(basis.question_id))
        return fingerprint(basis)
    monkeypatch.setattr(owner,'finalized_question_fingerprint',spy)
    result = regenerate(source,store)
    assert result.state is CustodyState.BLOCKED
    assert invoked == [], 'unbounded question ID was fingerprinted before its resource limit check'
    assert store.calls == 0


def test_invalid_source_version_is_blocked_not_uncaught_typeerror():
    from copy import deepcopy
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    original = source.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    current = deepcopy(original.current_teacher)
    object.__setattr__(current, 'version', 'forged-number')
    source.override=replace(original,current_teacher=current)
    result=regenerate(source,store)
    assert result.state is CustodyState.BLOCKED and store.calls==0
