"""V6 source/iterator admission: adversarial rejection and valid-routing pairs.

Tests intentionally exercise the public bounded selector admission operation, not private stubs.
"""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from grading.integration.selector_admission import (
    SelectionSourceContractError, SelectionSourceReadError,
    bounded_source_bytes,
)
from tests.integration.test_selector_admission_regression import rig, run


class DynamicClassification:
    def __init__(self, classification):
        self.value = classification
        self.fail = False
        self.lookups = 0

    def __getattr__(self, name):
        if name != "resolve_question_evaluation_classification":
            raise AttributeError(name)
        self.lookups += 1
        if self.fail:
            raise AttributeError("remote method resolution temporarily failed")
        return lambda **kwargs: self.value


class DynamicReader:
    def __init__(self):
        self.fail = False
        self.lookups = 0

    def __getattr__(self, name):
        if name != "read":
            raise AttributeError(name)
        self.lookups += 1
        if self.fail:
            raise AttributeError("reader method resolution failed")
        return lambda n: b""


@pytest.mark.parametrize("fail", [False, True])
def test_dynamic_classification_method_is_not_a_supported_port(fail):
    r = list(rig())
    source = DynamicClassification(r[1].value)
    source.fail = fail
    r[1] = source
    r[4].expected_sources = (source, r[2], r[3])
    with pytest.raises(SelectionSourceContractError, match="declared method"):
        run(tuple(r))
    assert source.lookups == 0  # no invocation even to inspect a dynamic method
    assert r[2].header_reads == 0 and not r[3].calls


def test_static_classification_positive_selection():
    r = rig()
    result = run(r)
    assert result.policy_ref == r[5].expected_policy_ref
    assert len(r[3].calls) == 1


@pytest.mark.parametrize("fail", [False, True])
def test_dynamic_binary_reader_is_not_a_supported_port(fail):
    reader = DynamicReader()
    reader.fail = fail
    with pytest.raises(SelectionSourceContractError, match="declared method"):
        bounded_source_bytes(reader, limits=rig()[6])
    assert reader.lookups == 0


def test_static_binary_reader_positive_limit_exactly():
    limits = replace(rig()[6], max_source_bytes=3)
    assert bounded_source_bytes(BytesIO(b"abc"), limits=limits) == b"abc"


class PoisonClassIterator:
    class_lookups = 0

    @property
    def __class__(self):
        type(self).class_lookups += 1
        raise RuntimeError("poison class property")


class FakeClassIterator:
    class_lookups = 0

    @property
    def __class__(self):
        from collections.abc import Iterator
        type(self).class_lookups += 1
        return Iterator


@pytest.mark.parametrize("iterator_cls", [PoisonClassIterator, FakeClassIterator])
def test_foreign_instance_class_property_is_not_consulted(iterator_cls):
    r = list(rig())
    iterator_cls.class_lookups = 0
    r[2].iter_policy_rules = lambda: iterator_cls()
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(r))
    assert iterator_cls.class_lookups == 0
    assert r[2].header_reads == 1 and not r[3].calls


class NonCallableNext:
    def __iter__(self):
        return self
    __next__ = None


class NonCallableIter:
    __iter__ = None
    def __next__(self):
        return None


@pytest.mark.parametrize("iterator_cls", [NonCallableNext, NonCallableIter])
def test_non_callable_iterator_protocol_is_contract_error(iterator_cls):
    r = list(rig())
    r[2].iter_policy_rules = lambda: iterator_cls()
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(r))
    assert not r[3].calls


def test_real_custom_iterator_still_selects():
    r = list(rig())
    rule = r[2].rules[0]
    class OneRule:
        def __init__(self):
            self.emitted = False
        def __iter__(self):
            return self
        def __next__(self):
            if self.emitted:
                raise StopIteration
            self.emitted = True
            return rule
    r[2].iter_policy_rules = lambda: OneRule()
    result = run(tuple(r))
    assert result.policy_ref == r[5].expected_policy_ref and len(r[3].calls) == 1


def test_valid_iterator_next_failure_is_read_error_with_cause():
    r = list(rig())
    class Failing:
        def __iter__(self):
            return self
        def __next__(self):
            raise ValueError("underlying iterator I/O failure")
    r[2].iter_policy_rules = lambda: Failing()
    with pytest.raises(SelectionSourceReadError) as exc:
        run(tuple(r))
    assert isinstance(exc.value.__cause__, ValueError)
    assert not r[3].calls


def test_raising_iterator_initialization_is_source_error():
    r = list(rig())
    class RaisingIter:
        def __iter__(self):
            raise RuntimeError("source reader init failed")
        def __next__(self):
            raise StopIteration
    r[2].iter_policy_rules = lambda: RaisingIter()
    with pytest.raises(SelectionSourceReadError) as exc:
        run(tuple(r))
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert not r[3].calls


def test_invalid_iterator_self_return_is_contract_error():
    r = list(rig())
    class BadIter:
        def __iter__(self):
            return iter(())
        def __next__(self):
            raise StopIteration
    r[2].iter_policy_rules = lambda: BadIter()
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(r))
    assert not r[3].calls


@pytest.mark.parametrize("port", ["policy_header", "policy_rules", "capability"])
def test_dynamic_methods_rejected_without_reads(port):
    r = list(rig())
    index, name = {"policy_header": (2, "read_policy_header"),
                   "policy_rules": (2, "iter_policy_rules"),
                   "capability": (3, "find_exact_capabilities")}[port]
    original = r[index]
    class Dynamic:
        def __init__(self):
            self.lookup_count = 0
        def __getattr__(self, attr):
            if attr != name:
                raise AttributeError(attr)
            self.lookup_count += 1
            return getattr(original, attr)
    source = Dynamic()
    if port == "policy_header":
        source.iter_policy_rules = original.iter_policy_rules
    elif port == "policy_rules":
        source.read_policy_header = original.read_policy_header
    r[index] = source
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError, match="declared method"):
        run(tuple(r))
    assert source.lookup_count == 0
    assert not r[3].calls if port != "capability" else not original.calls


def test_declared_raising_descriptor_remains_read_error():
    r = list(rig())
    class DescriptorFailure:
        @property
        def resolve_question_evaluation_classification(self):
            raise AttributeError("descriptor internal failure")
    source = DescriptorFailure()
    r[1] = source
    r[4].expected_sources = (source, r[2], r[3])
    with pytest.raises(SelectionSourceReadError) as exc:
        run(tuple(r))
    assert isinstance(exc.value.__cause__, AttributeError)
    assert r[2].header_reads == 0 and not r[3].calls


def test_declared_policy_and_capability_methods_support_real_positive_selection():
    r = rig()
    result = run(r)
    assert result.policy_ref == r[5].expected_policy_ref
    assert len(r[2].rules) == 1 and r[2].yielded == 1
    assert len(r[3].calls) == 1


def test_declared_capability_method_failure_is_frozen_if1_execution_error():
    from grading.capability_registry import EvaluatorCapabilitySourceExecutionError
    r = list(rig())
    cap = r[3]
    def failing(*, capability_ref):
        raise RuntimeError("capability store unavailable")
    cap.find_exact_capabilities = failing
    with pytest.raises(EvaluatorCapabilitySourceExecutionError) as exc:
        run(tuple(r))
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert r[2].header_reads == 1 and r[2].yielded == 1


def test_declared_capability_noncallable_is_typed_source_contract_before_if1():
    r = list(rig())
    r[3].find_exact_capabilities = None
    with pytest.raises(SelectionSourceContractError, match="not callable"):
        run(tuple(r))
    assert r[2].header_reads == 1 and r[2].yielded == 1
    assert not r[3].calls


def test_declared_reader_descriptor_failure_is_read_error_with_cause():
    class Broken:
        @property
        def read(self):
            raise AttributeError("real reader descriptor failure")
    with pytest.raises(SelectionSourceReadError) as exc:
        bounded_source_bytes(Broken(), limits=rig()[6])
    assert isinstance(exc.value.__cause__, AttributeError)


def test_healthy_iterator_raises_typeerror_from_its_initializer_as_read_failure():
    r = list(rig())
    class OperationalTypeError:
        def __iter__(self):
            raise TypeError('underlying source iterator creation failed')
        def __next__(self):
            raise StopIteration
    r[2].iter_policy_rules = lambda: OperationalTypeError()
    with pytest.raises(SelectionSourceReadError) as exc:
        run(tuple(r))
    assert isinstance(exc.value.__cause__, TypeError)
    assert not r[3].calls


def test_staticmethod_iterator_compatibility():
    r = list(rig())
    rule = r[2].rules[0]
    class StaticIterator:
        exhausted = False
        @staticmethod
        def __iter__():
            return cursor
        def __next__(self):
            if self.exhausted:
                raise StopIteration
            self.exhausted = True
            return rule
    cursor = StaticIterator()
    r[2].iter_policy_rules = lambda: cursor
    selected = run(tuple(r))
    assert selected.policy_ref == r[5].expected_policy_ref
    assert len(r[3].calls) == 1
