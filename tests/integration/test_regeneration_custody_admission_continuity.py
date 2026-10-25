"""Verify draft regeneration admission and alias custody across repeated reads."""
from dataclasses import replace

import pytest

from grading.rubric import regeneration_custody as custody
from grading.rubric.models import (
    AuthoringCriterionCondition,
    AuthoringGateRule,
    AuthoringRoundingRule,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from tests.integration.test_rubric_regeneration_custody import (
    QualifiedSourceFixture, AtomicStoreFixture, regenerate,
)


def _modified(base, field, text):
    c = base.criteria[0]
    level = c.performance_levels[0]
    if field == 'criterion_id':
        c = replace(c, criterion_id=text)
    elif field == 'criterion_description':
        c = replace(c, operational_description=text)
    elif field == 'evidence_requirement':
        c = replace(c, evidence_requirement=text)
    elif field == 'level_id':
        c = replace(c, performance_levels=(replace(level, level_id=text),) + c.performance_levels[1:])
    elif field == 'level_description':
        c = replace(c, performance_levels=(replace(level, operational_description=text),) + c.performance_levels[1:])
    elif field == 'equivalent':
        c = replace(c, accepted_equivalents=(text,))
    elif field == 'gate_rule':
        return replace(base, gates=(AuthoringGateRule(text, (), ScoringDecimal.from_raw(1)),))
    elif field == 'condition_criterion':
        return replace(base, gates=(AuthoringGateRule('rule', (AuthoringCriterionCondition(text, ('FULL',)),), ScoringDecimal.from_raw(1)),))
    elif field == 'condition_level':
        return replace(base, gates=(AuthoringGateRule('rule', (AuthoringCriterionCondition('C1', (text,)),), ScoringDecimal.from_raw(1)),))
    elif field == 'rounding_rule':
        return replace(base, rounding=AuthoringRoundingRule(text, ScoringDecimal.from_raw(1), 'HALF_UP'))
    elif field == 'rounding_mode':
        return replace(base, rounding=AuthoringRoundingRule('round', ScoringDecimal.from_raw(1), text))
    else:
        raise AssertionError(field)
    return replace(base, criteria=(c,) + base.criteria[1:])


@pytest.mark.parametrize('field', [
    'criterion_id', 'criterion_description', 'evidence_requirement',
    'level_id', 'level_description', 'equivalent', 'gate_rule',
    'condition_criterion', 'condition_level', 'rounding_rule', 'rounding_mode',
])
def test_oversized_nested_text_denied_before_copy_or_source_contact(monkeypatch, field):
    src, store = QualifiedSourceFixture(), AtomicStoreFixture()
    fresh = _modified(src.base, field, 'X' * (src.limits.max_text_characters_per_field + 1))
    copies = []
    original = custody.deepcopy
    def recorded_copy(value):
        copies.append(True)
        return original(value)
    monkeypatch.setattr(custody, 'deepcopy', recorded_copy)
    result = regenerate(src, store, fresh)
    assert result.state is custody.CustodyState.BLOCKED
    assert copies == [] and src.calls == 0 and store.calls == 0


def test_source_alias_mutated_after_admission_does_not_change_merge_inputs(monkeypatch):
    src, store = QualifiedSourceFixture(), AtomicStoreFixture()
    original = custody.propose_regenerated_draft
    def concurrent_source_mutation(**kwargs):
        # The adapter owns src.current. This must not be the admitted copy.
        object.__setattr__(src.current, 'version', 99)
        return original(**kwargs)
    monkeypatch.setattr(custody, 'propose_regenerated_draft', concurrent_source_mutation)
    result = regenerate(src, store)
    assert result.state is custody.CustodyState.STORED
    assert result.request.authority.current_teacher.version == 1
    assert result.request.draft.version == 2
    assert store.calls == 1

class CopyWitness:
    copies = 0

    def __deepcopy__(self, memo):
        type(self).copies += 1
        return CopyWitness()


@pytest.mark.parametrize('numeric_owner', [
    'minimum_score', 'level_contribution', 'gate_ceiling',
    'cap_ceiling', 'deduction_amount', 'rounding_increment',
])
def test_invalid_nested_numeric_wrapper_denied_before_copy(monkeypatch, numeric_owner):
    from grading.rubric.models import AuthoringCapRule, AuthoringDeductionRule
    from copy import deepcopy
    src, store = QualifiedSourceFixture(), AtomicStoreFixture()
    fresh = deepcopy(src.base)
    number = ScoringDecimal.from_raw(1)
    if numeric_owner == 'minimum_score':
        numeric = fresh.minimum_score
    elif numeric_owner == 'level_contribution':
        numeric = fresh.criteria[0].performance_levels[0].contribution
    elif numeric_owner == 'gate_ceiling':
        fresh = replace(fresh, gates=(AuthoringGateRule('gate', (), number),))
        numeric = number
    elif numeric_owner == 'cap_ceiling':
        fresh = replace(fresh, caps=(AuthoringCapRule('cap', (), number),))
        numeric = number
    elif numeric_owner == 'deduction_amount':
        fresh = replace(fresh, deductions=(AuthoringDeductionRule('deduct', (), number),))
        numeric = number
    else:
        fresh = replace(fresh, rounding=AuthoringRoundingRule('round', number, 'HALF_UP'))
        numeric = number
    object.__setattr__(numeric, '_value', CopyWitness())
    CopyWitness.copies = 0
    out = regenerate(src, store, fresh)
    assert out.state is custody.CustodyState.BLOCKED
    assert CopyWitness.copies == 0 and src.calls == 0 and store.calls == 0


def test_nested_text_at_authorized_limit_allows_genuine_regeneration():
    src, store = QualifiedSourceFixture(), AtomicStoreFixture()
    fresh = _modified(src.base, 'evidence_requirement', 'X' * src.limits.max_text_characters_per_field)
    out = regenerate(src, store, fresh)
    assert out.state is custody.CustodyState.STORED and store.calls == 1
