"""bounded selector admission V3: causal regressions for source order and failure provenance.

The adversarial changes occur only in synthetic, explicitly admitted fixtures.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from grading.contracts.evaluator_selection import EvaluatorSelectionRule
from grading.integration.selector_admission import (
    SelectionAdmissionDenied,
    SelectionAdmissionUnavailable,
    SelectionSourceContractError,
    SelectorResourceLimitError,
)
from tests.integration.test_evaluator_selection_contract_regression import _capability_ref
from tests.integration.test_selector_admission_regression import rig, run


def test_invalid_policy_revision_does_not_acquire_rules_descriptor():
    r = list(rig())
    calls = []
    class WrongRevision:
        def read_policy_header(self):
            calls.append("header")
            return ("1", replace(r[5].expected_policy_ref, version=77))

        @property
        def iter_policy_rules(self):
            calls.append("rule_descriptor")
            raise AssertionError("Must not acquire wrong revision's rule interface")

    r[2] = WrongRevision()
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError, match="revision"):
        run(tuple(r))
    assert calls == ["header"]
    assert not r[3].calls


@pytest.mark.parametrize("bad", [None, 42, "", " leading", "trailing "])
def test_malformed_classification_identifier_is_source_contract_not_budget(bad):
    r = list(rig())
    obj = r[1].value
    object.__setattr__(obj, "answer_type", bad)
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert r[2].header_reads == 0 and not r[3].calls


@pytest.mark.parametrize("bad", [None, 5, "", " leading", "trailing "])
def test_malformed_policy_rule_identifier_is_source_contract_not_budget(bad):
    r = list(rig())
    original = r[2].rules[0]
    object.__setattr__(original, "answer_type", bad)
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert r[2].header_reads == 1 and not r[3].calls


def test_malformed_policy_header_reference_is_not_resource_exhaustion():
    r = list(rig())
    r[2].policy_ref = replace(r[2].policy_ref)
    object.__setattr__(r[2].policy_ref, "policy_id", None)
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls


def test_valid_oversized_identifier_is_still_resource_exhaustion():
    r = list(rig())
    object.__setattr__(r[1].value, "answer_type", "A" * (r[6].max_identifier_codepoints + 1))
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[2].header_reads and not r[3].calls


def test_missing_admission_port_is_unavailable_not_explicit_denial():
    r = list(rig())
    r[4] = None
    with pytest.raises(SelectionAdmissionUnavailable):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_explicit_denial_is_distinct_from_missing_port():
    r = list(rig(approved=False))
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_malformed_caller_configuration_is_not_source_resource_error():
    r = list(rig())
    r[5] = replace(r[5], configuration_ref=None)
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_valid_admitted_route_continues_after_header_check():
    r = rig(rules=[EvaluatorSelectionRule("SHORT_TEXT", "en", r_policy(), _capability_ref())])
    assert run(r).policy_ref == r[5].expected_policy_ref
    assert r[2].header_reads == 1 and r[2].yielded == 1 and len(r[3].calls) == 1


def r_policy():
    from grading.active_question_authority import ContextPolicy
    return ContextPolicy.DIRECT
