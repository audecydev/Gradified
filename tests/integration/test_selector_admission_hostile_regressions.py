"""Adversarial tests for selector admission and independent source-boundary failures."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from grading.contracts.evaluator_selection import EvaluatorSelectionPolicyRef
from grading.integration.selector_admission import (
    DeferredBinaryPolicySource, SelectionSourceContractError,
    SelectionSourceReadError,
)
from tests.integration.test_selector_admission_regression import rig, run


def test_nested_classification_spec_never_dispatches_foreign_properties():
    for property_name in ("id", "version"):
        r = list(rig())
        touched = []
        class Poison:
            @property
            def id(self):
                touched.append('id')
                raise RuntimeError('poison id')
            @property
            def version(self):
                touched.append('version')
                raise RuntimeError('poison version')
        object.__setattr__(r[1].value, 'grading_spec_ref', Poison())
        with pytest.raises(SelectionSourceContractError):
            run(tuple(r))
        assert touched == [], f"read untrusted {property_name} before type admission"
        assert r[2].header_reads == 0 and not r[3].calls


@pytest.mark.parametrize('failure', ['revision', 'policy_id', 'schema'])
def test_binary_policy_does_not_acquire_rules_before_accepted_header(failure):
    r = list(rig())
    events = []
    real_ref = r[5].expected_policy_ref
    bad_ref = (replace(real_ref, version=real_ref.version + 1) if failure == 'revision'
               else EvaluatorSelectionPolicyRef('not-approved-policy', real_ref.version))
    header = ('unsupported-schema' if failure == 'schema' else '1',
              real_ref if failure == 'schema' else bad_ref)
    def header_only(raw):
        events.append('header')
        return header
    def rules_only(raw):
        events.append('rules')
        return iter(())
    r[2] = DeferredBinaryPolicySource(
        open_reader=lambda: BytesIO(b'payload'),
        decode_header=header_only, iter_rules=rules_only,
    )
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert events == ['header'], events
    assert not r[3].calls


def test_valid_binary_policy_header_routes_successfully_and_acquires_rules_late():
    r = list(rig())
    old_source = r[2]
    events = []
    def header(raw):
        events.append('header')
        assert raw == b'p'
        return old_source.read_policy_header()
    def rules(raw):
        events.append('rules')
        assert raw == b'p'
        return iter(old_source.rules)
    r[2] = DeferredBinaryPolicySource(
        open_reader=lambda: BytesIO(b'p'), decode_header=header, iter_rules=rules,
    )
    r[4].expected_sources = (r[1], r[2], r[3])
    selection = run(tuple(r))
    assert selection.policy_ref == r[5].expected_policy_ref
    assert events == ['header', 'rules'] and len(r[3].calls) == 1


@pytest.mark.parametrize('port', ['classification', 'policy', 'capability'])
def test_admission_callback_method_substitution_is_detected(port):
    r = list(rig())
    names = {'classification': (1, 'resolve_question_evaluation_classification'),
             'policy': (2, 'read_policy_header'),
             'capability': (3, 'find_exact_capabilities')}
    idx, name = names[port]
    source = r[idx]
    called = []
    original = getattr(source, name)
    class Mutator:
        def authorize_selection_sources(self, **kwargs):
            called.append('admission')
            setattr(source, name, lambda **k: (_ for _ in ()).throw(RuntimeError('replaced')))
            return True
    r[4] = Mutator()
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert called == ['admission']
    assert not r[3].calls
    setattr(source, name, original)


def test_policy_header_callback_cannot_replace_rule_method_mid_read():
    r = list(rig())
    source = r[2]
    header = source.read_policy_header
    def replacing_header():
        source.iter_policy_rules = lambda: iter(source.rules)
        return header()
    source.read_policy_header = replacing_header
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls
