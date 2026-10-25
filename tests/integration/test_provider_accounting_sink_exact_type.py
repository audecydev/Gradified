"""Verified-defect exception: callback-mutated P-D accounting must not return success.

This test exercises the installed public providers. Event dataclass frozen-ness does
not establish integrity across a callback that can use object.__setattr__.
"""
import pytest

from test_attempt_accounting import Sink as DirectSink, request, wrapper
from test_rubric_accounting import Sink as RubricSink, installed, source
from grading.providers.attempt_accounting import (
    ProviderAccountingIndeterminate,
    ProviderAccountingReceipt,
)
from grading.providers.rubric_accounting import (
    RubricAccountingIndeterminate,
    RubricAccountingReceipt,
)


@pytest.mark.parametrize("operation", ("direct", "rubric"))
@pytest.mark.parametrize("hostile_variant", ("impersonate", "explosive", "metadata"))
def test_accounting_sink_mutated_foreign_failure_kind_never_yields_payload_or_executes_foreign_hooks(
    operation, hostile_variant
):
    foreign_calls = []

    class ForeignMeta(type):
        def __eq__(cls, other):
            foreign_calls.append("foreign class equality")
            if hostile_variant == "explosive":
                raise RuntimeError("private hostile equality")
            return True

    class MetadataMeta(ForeignMeta):
        @property
        def __name__(cls):
            foreign_calls.append("foreign name descriptor")
            return "str"

        @property
        def __module__(cls):
            foreign_calls.append("foreign module descriptor")
            return "builtins"

    class Foreign(metaclass=MetadataMeta if hostile_variant == "metadata" else ForeignMeta):
        def __eq__(self, other):
            foreign_calls.append("foreign value equality")
            if hostile_variant == "explosive":
                raise RuntimeError("private hostile value equality")
            return True

    if operation == "direct":
        class CorruptSink(DirectSink):
            def record_outcome(self, *, event):
                object.__setattr__(event, "failure_kind", Foreign())
                return ProviderAccountingReceipt(
                    event.identity.event_ref, event.identity.operation_ref, event.status
                )

        provider, _, _ = wrapper(sink=CorruptSink())
        with pytest.raises(ProviderAccountingIndeterminate) as caught:
            provider.evaluate(request=request())
    else:
        class CorruptSink(RubricSink):
            def record_rubric_generation(self, *, event):
                object.__setattr__(event, "failure_kind", Foreign())
                return RubricAccountingReceipt(
                    event.identity.event_ref,
                    event.identity.operation_ref,
                    event.approval_ref,
                    event.status,
                )

        provider, _, _, _ = installed(sink=CorruptSink())
        with pytest.raises(RubricAccountingIndeterminate) as caught:
            provider.generate(source=source())

    assert foreign_calls == []
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
