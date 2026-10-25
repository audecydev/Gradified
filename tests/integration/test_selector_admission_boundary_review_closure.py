"""Verify selector admission rejects malformed protocols while retaining valid controls."""
from __future__ import annotations

from io import BytesIO
from typing import get_type_hints

import pytest

from grading.integration.selector_admission import (
    DeferredBinaryClassificationSource,
    DeferredBinaryPolicySource,
    SelectionPolicyStreamSource,
    SelectionSourceContractError,
    SelectionSourceReadError,
)
from tests.integration.test_selector_admission_regression import rig, run


def _with_iterator(candidate):
    args = list(rig())
    args[2].iter_policy_rules = lambda: candidate
    return args


def test_class_invalid_iterator_cannot_use_instance_shadow_to_reach_if1():
    base = rig()
    rule = base[2].rules[0]

    class InvalidIterator:
        def __init__(self):
            self.__iter__ = lambda: self
            self.sent = False
        def __iter__(self):
            return iter(())
        def __next__(self):
            if self.sent:
                raise StopIteration
            self.sent = True
            return rule

    candidate = InvalidIterator()
    assert iter(candidate) is not candidate  # Independent Python language oracle
    args = _with_iterator(candidate)
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(args))
    assert not args[3].calls


def test_valid_iterator_not_rejected_by_irrelevant_instance_shadow():
    rule = rig()[2].rules[0]

    class ValidIterator:
        def __init__(self):
            self.__iter__ = lambda: (_ for _ in ()).throw(RuntimeError("shadow invoked"))
            self.sent = False
        def __iter__(self):
            return self
        def __next__(self):
            if self.sent:
                raise StopIteration
            self.sent = True
            return rule

    candidate = ValidIterator()
    assert iter(candidate) is candidate
    args = _with_iterator(candidate)
    assert run(tuple(args)).policy_ref == args[5].expected_policy_ref
    assert len(args[3].calls) == 1


def test_custom_getattribute_cannot_spoof_real_iterator_dispatch():
    rule = rig()[2].rules[0]

    class InvalidIterator:
        def __init__(self):
            self.sent = False
        def __getattribute__(self, name):
            if name == "__iter__":
                return lambda: self
            return object.__getattribute__(self, name)
        def __iter__(self):
            return iter(())
        def __next__(self):
            if self.sent:
                raise StopIteration
            self.sent = True
            return rule

    candidate = InvalidIterator()
    assert iter(candidate) is not candidate
    args = _with_iterator(candidate)
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(args))
    assert not args[3].calls


def test_public_policy_annotations_resolve_to_real_iterator_type():
    assert "return" in get_type_hints(SelectionPolicyStreamSource.iter_policy_rules)
    assert "iter_rules" in get_type_hints(DeferredBinaryPolicySource)


def test_iterator_next_declaration_corrupted_during_real_initialization_is_contract_error():
    rule = rig()[2].rules[0]

    class MutableProtocol:
        def __iter__(self):
            type(self).__next__ = None
            return self
        def __next__(self):
            return rule

    args = _with_iterator(MutableProtocol())
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(args))
    assert not args[3].calls


def test_iterator_next_callable_replaced_during_init_is_contract_error():
    rule = rig()[2].rules[0]

    class MutableProtocol:
        def __iter__(self):
            type(self).__next__ = lambda self: rule
            return self
        def __next__(self):
            raise StopIteration

    args = _with_iterator(MutableProtocol())
    with pytest.raises(SelectionSourceContractError, match="iterator"):
        run(tuple(args))
    assert not args[3].calls


def _deferred_classification(reader):
    args = list(rig())
    original = args[1].value
    args[1] = DeferredBinaryClassificationSource(
        open_reader=lambda: reader,
        decode=lambda raw: original if raw == b"ok" else None,
    )
    args[4].expected_sources = (args[1], args[2], args[3])
    return args


def test_normal_reader_cleanup_runs_before_policy_and_valid_selection():
    class Reader(BytesIO):
        close_count = 0
        def close(self):
            self.close_count += 1
            super().close()
    reader = Reader(b"ok")
    args = _deferred_classification(reader)
    result = run(tuple(args))
    assert result.policy_ref == args[5].expected_policy_ref
    assert reader.close_count == 1 and reader.closed
    assert len(args[3].calls) == 1


@pytest.mark.parametrize("raised", [AttributeError, RuntimeError])
def test_declared_reader_close_descriptor_failure_cannot_be_silently_skipped(raised):
    class Reader:
        def read(self, size):
            return b"ok" if not hasattr(self, "sent") else b""
        @property
        def close(self):
            raise raised("close descriptor failed")
    reader = Reader()
    # Avoid other reader-side failures: bytes are returned once then EOF.
    reader.sent = False
    def read(self, n):
        if self.sent:
            return b""
        self.sent = True
        return b"ok"
    Reader.read = read
    args = _deferred_classification(reader)
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(args))
    assert type(caught.value.__cause__) is raised
    assert args[2].header_reads == 0 and not args[3].calls


def test_close_callable_raising_attributeerror_is_read_failure():
    class Reader:
        def __init__(self): self.sent = False
        def read(self, n):
            if self.sent: return b""
            self.sent = True
            return b"ok"
        def close(self):
            raise AttributeError("close operation failed")
    args = _deferred_classification(Reader())
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(args))
    assert type(caught.value.__cause__) is AttributeError
    assert args[2].header_reads == 0 and not args[3].calls


def test_reader_with_no_declared_close_remains_supported():
    class Reader:
        def __init__(self):
            self.sent = False
        def read(self, n):
            if self.sent:
                return b""
            self.sent = True
            return b"ok"
    args = _deferred_classification(Reader())
    assert run(tuple(args)).policy_ref == args[5].expected_policy_ref
    assert len(args[3].calls) == 1


def test_read_error_stays_primary_if_cleanup_also_fails():
    class Reader:
        def read(self, size):
            raise OSError("read failed")
        @property
        def close(self):
            raise AttributeError("close descriptor failed")
    args = _deferred_classification(Reader())
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(args))
    assert isinstance(caught.value.__cause__, OSError)
    assert args[2].header_reads == 0 and not args[3].calls
    # The cleanup failure is recorded without replacing the causal read error.
    assert any("cleanup" in note.lower() for note in getattr(caught.value, "__notes__", []))


def test_structural_read_error_not_replaced_by_cleanup_failure():
    class Reader:
        def read(self, size):
            return "invalid non-bytes"
        def close(self):
            raise RuntimeError("cleanup fails")
    args = _deferred_classification(Reader())
    with pytest.raises(SelectionSourceContractError) as caught:
        run(tuple(args))
    assert args[2].header_reads == 0 and not args[3].calls
    assert any("cleanup" in note.lower() for note in getattr(caught.value, "__notes__", []))


def test_declared_noncallable_close_is_malformed_source():
    class Reader:
        def __init__(self):
            self.sent = False
        def read(self, n):
            if self.sent: return b""
            self.sent = True
            return b"ok"
        close = None
    args = _deferred_classification(Reader())
    with pytest.raises(SelectionSourceContractError):
        run(tuple(args))
    assert args[2].header_reads == 0 and not args[3].calls


def test_deferred_policy_reader_cleanup_failure_blocks_header_and_rules():
    from grading.integration.selector_admission import DeferredBinaryPolicySource
    args = list(rig())
    event = []
    original_policy = args[2]
    class Reader:
        def __init__(self): self.sent = False
        def read(self, n):
            if self.sent: return b""
            self.sent = True
            return b"policy"
        @property
        def close(self):
            event.append("close_descriptor")
            raise AttributeError("policy cleanup failed")
    args[2] = DeferredBinaryPolicySource(
        open_reader=Reader,
        decode_header=lambda raw: event.append("header_decode") or original_policy.read_policy_header(),
        iter_rules=lambda raw: event.append("rules") or iter(original_policy.rules),
    )
    args[4].expected_sources = (args[1], args[2], args[3])
    with pytest.raises(SelectionSourceReadError) as caught:
        run(tuple(args))
    assert isinstance(caught.value.__cause__, AttributeError)
    assert event == ["close_descriptor"]
    assert not args[3].calls


def test_over_budget_reader_is_closed_and_failure_stays_resource_owned():
    from dataclasses import replace
    from grading.integration.selector_admission import SelectorResourceLimitError
    args = list(rig())
    class Reader:
        def __init__(self): self.closed = 0
        def read(self, n): return b"x" * n
        def close(self): self.closed += 1
    reader = Reader()
    args[1] = DeferredBinaryClassificationSource(
        open_reader=lambda: reader,
        decode=lambda raw: (_ for _ in ()).throw(AssertionError("decoder must not run")),
    )
    args[4].expected_sources = (args[1], args[2], args[3])
    args[6] = replace(args[6], max_source_bytes=3)
    args[4].expected_limits = args[6]
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(args))
    assert reader.closed == 1
    assert args[2].header_reads == 0 and not args[3].calls
