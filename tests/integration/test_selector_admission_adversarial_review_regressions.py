"""Causal review regressions for malformed roots, context custody, and error provenance."""
from __future__ import annotations

from dataclasses import replace

import pytest

from grading.active_question_authority import ContextPolicy
from grading.evaluator_selection import QuestionClassificationBindingError
from grading.integration.selector_admission import (
    SelectionAdmissionDenied, SelectionSourceContractError,
    SelectorResourceLimitError,
)
from tests.integration.test_selector_admission_regression import rig, run


@pytest.mark.parametrize('field', ['configuration_ref', 'expected_policy_ref', 'grading_spec_ref'])
def test_corrupt_config_exact_root_is_typed_denial_before_source_reads(field):
    r = list(rig())
    object.__delattr__(r[5], field)
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_corrupt_config_nested_policy_ref_is_typed_denial():
    r = list(rig())
    object.__delattr__(r[5].expected_policy_ref, 'policy_id')
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


@pytest.mark.parametrize('field', ['schema_version', 'max_source_bytes', 'max_policy_rules'])
def test_corrupt_resource_profile_is_typed_limit_rejection(field):
    r = list(rig())
    object.__delattr__(r[6], field)
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


@pytest.mark.parametrize('field', ['grading_spec_ref', 'question_id', 'context_policy', 'question_text', 'rubric_content', 'scoring_authority'])
def test_corrupt_question_authority_is_typed_before_source_reads(field):
    r = list(rig())
    object.__delattr__(r[0], field)
    with pytest.raises(QuestionClassificationBindingError):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


@pytest.mark.parametrize('field', ['grading_spec_ref', 'answer_type', 'language'])
def test_corrupt_classification_is_typed_source_contract_error(field):
    r = list(rig())
    object.__delattr__(r[1].value, field)
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert r[2].header_reads == 0 and not r[3].calls


@pytest.mark.parametrize('field', ['policy_id', 'version'])
def test_corrupt_policy_header_ref_is_typed_source_contract_error(field):
    r = list(rig())
    # Keep the trusted expected reference intact; corrupt only source-returned policy.
    r[2].policy_ref = replace(r[2].policy_ref)
    object.__delattr__(r[2].policy_ref, field)
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert r[2].header_reads == 1 and not r[3].calls


def test_admission_can_explicitly_bind_canonical_active_context_policy():
    r = list(rig())
    seen = []
    class ContextBoundAdmission:
        def authorize_selection_sources(self, *, context, **kwargs):
            seen.append(context.context_policy)
            return context.context_policy is ContextPolicy.DIRECT
    r[4] = ContextBoundAdmission()
    correct = run(tuple(r))
    assert correct.context_policy is ContextPolicy.DIRECT
    assert seen == [ContextPolicy.DIRECT]
    r = list(rig())
    r[0] = replace(r[0], context_policy=ContextPolicy.DIRECT_PLUS_REFERENCE)
    r[4] = ContextBoundAdmission()
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert seen[-1] is ContextPolicy.DIRECT_PLUS_REFERENCE
    assert not r[1].calls and not r[2].header_reads and not r[3].calls
