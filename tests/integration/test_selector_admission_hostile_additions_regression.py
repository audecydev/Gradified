"""Independent causal REDs for defects verified in the uncommitted source admission candidate.

These tests deliberately target the exact trusted-callback/typing/error boundaries.
They are not approvals of new academic policy or of an external adapter.
"""
from __future__ import annotations

from dataclasses import replace
import pytest

from grading.active_question_authority import ContextPolicy
from grading.contracts.evaluator_selection import EvaluatorSelectionPolicyRef, EvaluatorSelectionRule
from grading.integration.selector_admission import (
    SelectionSourceContractError, SelectionSourceReadError,
    SelectorResourceLimitError,
)
from tests.integration.test_evaluator_selection_contract_regression import _capability_ref
from tests.integration.test_selector_admission_regression import Admission, rig, run


class ComparisonSpoof:
    def __ne__(self, other):
        return False

    def __eq__(self, other):
        return True


def test_admitted_context_does_not_drift_during_source_call():
    r = list(rig(rules=[
        EvaluatorSelectionRule('SHORT_TEXT', 'en', ContextPolicy.DIRECT, _capability_ref()),
        EvaluatorSelectionRule('SHORT_TEXT', 'en', ContextPolicy.DIRECT_PLUS_REFERENCE, _capability_ref()),
    ]))
    originally_admitted = r[0].context_policy
    original = r[1].resolve_question_evaluation_classification
    def mutating_source(**kwargs):
        object.__setattr__(r[0], 'context_policy', ContextPolicy.DIRECT_PLUS_REFERENCE)
        return original(**kwargs)
    r[1].resolve_question_evaluation_classification = mutating_source
    selected = run(tuple(r))
    assert selected.context_policy is originally_admitted
    assert len(r[3].calls) == 1


def test_admitted_rule_limit_survives_mutation_of_admission_argument():
    rules = [EvaluatorSelectionRule('SHORT_TEXT' if i == 0 else f'TYPE_{i}', 'en',
                                   ContextPolicy.DIRECT, _capability_ref()) for i in range(5)]
    r = list(rig(rules=rules, limit_rules=3))
    class Mutator(Admission):
        def authorize_selection_sources(self, **kwargs):
            result = super().authorize_selection_sources(**kwargs)
            assert kwargs['limits'].max_policy_rules == 3
            object.__setattr__(kwargs['limits'], 'max_policy_rules', 256)
            return result
    m = Mutator(True, expected_sources=(r[1],r[2],r[3])); m.expected_limits = r[6]; r[4] = m
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[3].calls


def test_admitted_policy_reference_survives_mutation_of_admission_argument():
    r = list(rig())
    alternative = EvaluatorSelectionPolicyRef('other-policy', 9)
    original = r[5].expected_policy_ref
    class Mutator(Admission):
        def authorize_selection_sources(self, **kwargs):
            result = super().authorize_selection_sources(**kwargs)
            assert kwargs['config'].expected_policy_ref == original
            object.__setattr__(kwargs['config'], 'expected_policy_ref', alternative)
            return result
    m = Mutator(True, expected_sources=(r[1],r[2],r[3])); m.expected_limits = r[6]; r[4] = m
    r[2].policy_ref = alternative
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls


@pytest.mark.parametrize('schema_field', ['policy_header', 'limit_profile'])
def test_schema_version_requires_exact_string(schema_field):
    r = list(rig())
    if schema_field == 'policy_header':
        r[2].read_policy_header = lambda: (ComparisonSpoof(), r[2].policy_ref)
        expected = SelectionSourceContractError
    else:
        r[6] = replace(r[6], schema_version=ComparisonSpoof())
        r[4].expected_limits = r[6]
        expected = SelectorResourceLimitError
    with pytest.raises(expected):
        run(tuple(r))
    assert not r[3].calls


@pytest.mark.parametrize('port', ['classification', 'policy'])
def test_crashing_source_method_lookup_is_typed(port):
    r = list(rig())
    if port == 'classification':
        class Crashing:
            @property
            def resolve_question_evaluation_classification(self):
                raise RuntimeError('source getter failed')
        r[1] = Crashing()
    else:
        class Crashing:
            @property
            def read_policy_header(self):
                raise RuntimeError('source getter failed')
        r[2] = Crashing()
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises((SelectionSourceReadError, SelectionSourceContractError)):
        run(tuple(r))
    assert not r[3].calls


@pytest.mark.parametrize('error_type', [SelectorResourceLimitError, SelectionSourceContractError,
                                        ValueError, TypeError, AttributeError])
def test_iterator_failures_are_not_gradified_local_contract_failures(error_type):
    r = list(rig())
    class BrokenIterator:
        def __iter__(self): return self
        def __next__(self): raise error_type('source-generated error')
    r[2].iter_policy_rules = lambda: BrokenIterator()
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(r))
    assert type(caught.value.__cause__) is error_type
    assert not r[3].calls


def test_oversized_capability_version_rejected_before_if1():
    r = list(rig())
    r[2].rules = [EvaluatorSelectionRule('SHORT_TEXT', 'en', ContextPolicy.DIRECT,
                                       _capability_ref(record_version=(1 << 300_000)))]
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[3].calls
