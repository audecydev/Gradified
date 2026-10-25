"""Adversarial regressions for numeric wrapper mutation and active rubric authority."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import pytest
from grading.rubric.regeneration_custody import CustodyState
from tests.integration.test_rubric_regeneration_custody import QualifiedSourceFixture, AtomicStoreFixture, regenerate

class CopyWitness:
    copies = 0
    def __deepcopy__(self, memo):
        type(self).copies += 1
        return CopyWitness()

@pytest.mark.parametrize('field', ['minimum_score', 'level_contribution'])
def test_corrupt_nested_decimal_must_not_execute_copy_hook_or_call_source(field):
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    generated = deepcopy(source.base)
    numeric = generated.minimum_score if field == 'minimum_score' else generated.criteria[0].performance_levels[0].contribution
    object.__setattr__(numeric, '_value', CopyWitness())
    CopyWitness.copies = 0
    outcome = regenerate(source, store, generated)
    assert outcome.state is CustodyState.BLOCKED
    assert CopyWitness.copies == 0
    assert source.calls == 0 and store.calls == 0

def test_malformed_source_question_max_marks_rejected_before_fingerprint_or_store():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    original = source.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    modified = deepcopy(original.finalized_question)
    object.__setattr__(modified.max_marks, '_value', CopyWitness())
    source.override = replace(original, finalized_question=modified)
    CopyWitness.copies = 0
    outcome = regenerate(source, store)
    assert outcome.state is CustodyState.BLOCKED
    assert CopyWitness.copies == 0 and store.calls == 0

def test_positive_unmodified_regeneration_and_recovery():
    source, store = QualifiedSourceFixture(), AtomicStoreFixture()
    outcome = regenerate(source, store)
    assert outcome.state is CustodyState.STORED and store.calls == 1
