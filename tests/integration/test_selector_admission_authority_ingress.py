"""bounded selector admission A/B/C: positive and negative causal checks (not vendor tests)."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from grading.active_question_authority import ContextPolicy
from grading.contracts.evaluator_selection import EvaluatorSelectionPolicyRef, EvaluatorSelectionRule
from grading.integration.selector_admission import (
    DeferredBinaryClassificationSource, DeferredBinaryPolicySource,
    SelectionAdmissionDenied, SelectionSourceContractError, SelectionSourceReadError,
    SelectorResourceLimitError, SelectorResourceLimits,
)
from tests.integration.test_evaluator_selection_contract_regression import _capability_ref, _capability_record
from tests.integration.test_selector_admission_regression import Admission, rig, run


def test_snapshot_context_mutation_selects_only_original_admitted_context():
    r = list(rig(rules=[
        EvaluatorSelectionRule("SHORT_TEXT", "en", ContextPolicy.DIRECT, _capability_ref()),
        EvaluatorSelectionRule("SHORT_TEXT", "en", ContextPolicy.DIRECT_PLUS_REFERENCE, _capability_ref()),
    ]))
    read = r[1].resolve_question_evaluation_classification

    def mutate(**kwargs):
        object.__setattr__(r[0], "context_policy", ContextPolicy.DIRECT_PLUS_REFERENCE)
        return read(**kwargs)

    r[1].resolve_question_evaluation_classification = mutate
    result = run(tuple(r))
    assert result.context_policy is ContextPolicy.DIRECT
    assert len(r[3].calls) == 1


def test_admission_callback_cannot_redirect_nested_spec_policy_or_profile():
    r = list(rig())
    spec_version = r[5].grading_spec_ref.version
    original_policy = r[5].expected_policy_ref
    malicious = EvaluatorSelectionPolicyRef("wrong-policy", 97)
    class MutatingAdmission(Admission):
        def authorize_selection_sources(self, **kw):
            result = super().authorize_selection_sources(**kw)
            object.__setattr__(kw["context"].grading_spec_ref, "version", 900)
            object.__setattr__(kw["config"].grading_spec_ref, "version", 900)
            object.__setattr__(kw["config"].expected_policy_ref, "policy_id", "wrong-policy")
            object.__setattr__(kw["limits"], "max_policy_rules", 256)
            return result
    auth = MutatingAdmission(True, expected_sources=(r[1], r[2], r[3]))
    auth.expected_limits = r[6]
    r[4] = auth
    result = run(tuple(r))
    assert result.policy_ref == original_policy
    assert r[5].grading_spec_ref.version == spec_version
    assert result.classification.grading_spec_ref.version == spec_version


def _use_deferred(r, *, class_payload: bytes, policy_payload: bytes, decoder_a=None, decoder_b=None):
    """Adapters are admitted as the *actual* instances, never substituted later."""
    c, p = r[1], r[2]
    events = []

    def reader(label: str, payload: bytes):
        def open_reader():
            events.append(label)
            return BytesIO(payload)
        return open_reader

    r[1] = DeferredBinaryClassificationSource(
        open_reader=reader("classification_open", class_payload),
        decode=decoder_a or (lambda b: c.value if b == class_payload else None),
    )
    r[2] = DeferredBinaryPolicySource(
        open_reader=reader("policy_open", policy_payload),
        decode_header=lambda b: p.read_policy_header() if b == policy_payload else None,
        iter_rules=decoder_b or (lambda b: iter(p.rules) if b == policy_payload else None),
    )
    r[4].expected_sources = (r[1], r[2], r[3])
    return events


def test_deferred_raw_adapters_are_opened_only_after_authorization():
    r = list(rig())
    events = _use_deferred(r, class_payload=b"CLASS", policy_payload=b"POLICY")
    r[4].approve = False
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert events == []
    r[4].approve = True
    result = run(tuple(r))
    assert result.policy_ref == r[5].expected_policy_ref
    assert events == ["classification_open", "policy_open"]
    assert len(r[3].calls) == 1


def test_aggregate_raw_budget_exact_limit_and_one_byte_over():
    for policy_payload, accepted in ((b"p"*5, True), (b"p"*6, False)):
        r = list(rig())
        events = _use_deferred(r, class_payload=b"c"*4, policy_payload=policy_payload)
        r[6] = replace(r[6], max_source_bytes=9)
        r[4].expected_limits = r[6]
        if accepted:
            assert run(tuple(r)).policy_ref == r[5].expected_policy_ref
            assert events == ["classification_open", "policy_open"]
        else:
            with pytest.raises(SelectorResourceLimitError):
                run(tuple(r))
            assert events == ["classification_open", "policy_open"]
            assert not r[3].calls


def test_overreturn_reader_rejected_before_decoder_and_if2():
    r = list(rig())
    decoded = []
    class OverReturn:
        def read(self, requested):
            return b"x" * (requested + 1)
        def close(self):
            pass
    r[1] = DeferredBinaryClassificationSource(
        open_reader=lambda: OverReturn(),
        decode=lambda b: decoded.append(b),
    )
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not decoded and not r[2].header_reads and not r[3].calls


def test_raw_profile_mutation_does_not_increase_admitted_ingress():
    r = list(rig())
    _use_deferred(r, class_payload=b"a"*8, policy_payload=b"b"*8)
    r[6] = replace(r[6], max_source_bytes=9)
    class Mutator(Admission):
        def authorize_selection_sources(self, **kw):
            decision = super().authorize_selection_sources(**kw)
            object.__setattr__(kw["limits"], "max_source_bytes", 100_000)
            return decision
    auth = Mutator(expected_sources=(r[1], r[2], r[3])); auth.expected_limits = r[6]
    r[4] = auth
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[3].calls


def test_deferred_reader_open_failure_has_source_provenance():
    r = list(rig())
    def fail():
        raise RuntimeError("downstream source unavailable")
    r[1] = DeferredBinaryClassificationSource(open_reader=fail, decode=lambda b: None)
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(r))
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert not r[2].header_reads and not r[3].calls


def test_policy_decoder_must_return_lazy_rule_iterator():
    r = list(rig())
    p = r[2]
    _use_deferred(r, class_payload=b"c", policy_payload=b"p", decoder_b=lambda b: p.rules)
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls


def test_nested_version_representation_bound_is_local_to_admission():
    # Exact maximum is POSITIVELY admitted, with a matching real evaluator capability resolution capability.
    # An unrelated exception is therefore a test failure, not an accepted result.
    maximum = (1 << 256) - 1
    ref = _capability_ref(record_version=maximum)
    r = list(rig(rules=[EvaluatorSelectionRule(
        "SHORT_TEXT", "en", ContextPolicy.DIRECT, ref,
    )]))
    r[3].records = (_capability_record(capability_ref=ref),)
    result = run(tuple(r))
    assert result.selected_capability_ref == ref
    assert len(r[3].calls) == 1

    r = list(rig())
    r[2].rules = [EvaluatorSelectionRule("SHORT_TEXT", "en", ContextPolicy.DIRECT,
                                      _capability_ref(record_version=(1 << 256)))]
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[3].calls


def test_classification_descriptor_acquired_once_and_then_called_once():
    r = list(rig())
    underlying = r[1]
    class StatefulDescriptor:
        def __init__(self):
            self.lookups = 0
        @property
        def resolve_question_evaluation_classification(self):
            self.lookups += 1
            if self.lookups > 1:
                raise AssertionError("Method was retrieved a second time")
            return underlying.resolve_question_evaluation_classification
    source = StatefulDescriptor()
    r[1] = source
    r[4].expected_sources = (r[1], r[2], r[3])
    assert run(tuple(r)).context_policy is ContextPolicy.DIRECT
    assert source.lookups == 1


def test_crashing_method_descriptor_preserves_source_error_cause():
    r = list(rig())
    class Descriptor:
        @property
        def resolve_question_evaluation_classification(self):
            raise RuntimeError("reader descriptor failure")
    r[1] = Descriptor()
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(r))
    assert type(caught.value.__cause__) is RuntimeError
    assert not r[2].header_reads and not r[3].calls


def test_raw_factory_and_decoder_captured_before_admission_callback():
    r = list(rig())
    c = r[1]
    old_data = b"approved"
    accesses = []
    source = DeferredBinaryClassificationSource(
        open_reader=lambda: (accesses.append("approved") or BytesIO(old_data)),
        decode=lambda b: c.value if b == old_data else None,
    )
    r[1] = source
    class Mutator(Admission):
        def authorize_selection_sources(self, **kw):
            result = super().authorize_selection_sources(**kw)
            object.__setattr__(source, "open_reader", lambda: (accesses.append("changed") or BytesIO(b"wrong")))
            object.__setattr__(source, "decode", lambda b: None)
            return result
    a = Mutator(expected_sources=(r[1], r[2], r[3])); a.expected_limits = r[6]; r[4] = a
    assert run(tuple(r)).context_policy is ContextPolicy.DIRECT
    assert accesses == ["approved"]


def test_policy_source_revision_drift_after_admission_fails_before_if1():
    r = list(rig())
    class Mutator(Admission):
        def authorize_selection_sources(self, **kw):
            result = super().authorize_selection_sources(**kw)
            r[2].policy_ref = EvaluatorSelectionPolicyRef("different-revision", 11)
            return result
    a = Mutator(expected_sources=(r[1], r[2], r[3])); a.expected_limits = r[6]; r[4] = a
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls


def test_malformed_deferred_factory_rejected_before_admission_or_open():
    r = list(rig())
    r[1] = DeferredBinaryClassificationSource(open_reader=None, decode=lambda b: None)
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[4].calls and not r[2].header_reads


def test_oversized_configured_identity_precedes_admission_and_reads():
    r = list(rig())
    r[5] = replace(r[5], configuration_ref="A" * 100_000)
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[4].calls and not r[1].calls and not r[2].header_reads


@pytest.mark.parametrize("factory_result", [None, object(), type("NoRead", (), {"read": None})()])
def test_malformed_deferred_reader_is_contract_failure_not_io_error(factory_result):
    r = list(rig())
    decoded = []
    r[1] = DeferredBinaryClassificationSource(
        open_reader=lambda: factory_result,
        decode=lambda raw: decoded.append(raw),
    )
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not decoded and not r[2].header_reads and not r[3].calls


def test_valid_reader_raising_io_error_retains_read_provenance():
    r = list(rig())
    class FailingReader:
        def read(self, requested):
            raise OSError("underlying I/O failed")
        def close(self):
            pass
    r[1] = DeferredBinaryClassificationSource(
        open_reader=FailingReader, decode=lambda raw: None,
    )
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(r))
    assert type(caught.value.__cause__) is OSError
    assert not r[2].header_reads and not r[3].calls


def test_descriptor_attributeerror_with_hostile_metaclass_stays_typed():
    r = list(rig())
    class HostileMeta(type):
        def __getattribute__(cls, name):
            if name == "resolve_question_evaluation_classification":
                raise RuntimeError("hostile metaclass lookup")
            return super().__getattribute__(name)
    class BrokenSource(metaclass=HostileMeta):
        @property
        def resolve_question_evaluation_classification(self):
            raise AttributeError("broken descriptor")
    r[1] = BrokenSource()
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(r))
    assert type(caught.value.__cause__) is AttributeError
    assert not r[2].header_reads and not r[3].calls


def test_genuinely_missing_source_method_retains_contract_classification():
    r = list(rig())
    r[1] = object()
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[2].header_reads and not r[3].calls
