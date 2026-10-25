"""Fresh independently authored producer-accounting continuity adversarial cases."""
import pytest
from test_attempt_accounting import Sink as DirectSink, request, wrapper
from test_rubric_accounting import Sink as RubricSink, installed, source
from grading.providers.attempt_accounting import (ProviderAccountingIndeterminate,
    ProviderAccountingReceipt, ProviderAccountingEvent)
from grading.providers.rubric_accounting import (RubricAccountingIndeterminate,
    RubricAccountingReceipt, RubricAccountingEvent)

@pytest.mark.parametrize('operation',('direct','rubric'))
def test_sink_class_swap_must_not_return_success(operation):
    if operation=='direct':
        ForeignEvent=type('ForeignDirectEvent',(),{'__slots__':ProviderAccountingEvent.__slots__})
        class MutatingSink(DirectSink):
            def record_outcome(self,*,event):
                assert type(event) is ProviderAccountingEvent
                original=event.identity
                object.__setattr__(event,'__class__',ForeignEvent)
                assert type(event) is ForeignEvent
                return ProviderAccountingReceipt(original.event_ref, original.operation_ref, event.status)
        op,*_=wrapper(sink=MutatingSink())
        with pytest.raises(ProviderAccountingIndeterminate) as caught:
            op.evaluate(request=request())
    else:
        ForeignEvent=type('ForeignRubricEvent',(),{'__slots__':RubricAccountingEvent.__slots__})
        class MutatingSink(RubricSink):
            def record_rubric_generation(self,*,event):
                assert type(event) is RubricAccountingEvent
                original=event.identity
                object.__setattr__(event,'__class__',ForeignEvent)
                assert type(event) is ForeignEvent
                return RubricAccountingReceipt(original.event_ref, original.operation_ref, event.approval_ref, event.status)
        op,*_=installed(sink=MutatingSink())
        with pytest.raises(RubricAccountingIndeterminate) as caught:
            op.generate(source=source())

    assert caught.value.__context__ is None and caught.value.__cause__ is None

@pytest.mark.parametrize('operation',('direct','rubric'))
def test_legitimate_accounting_sink_returns_bytes(operation):
    if operation=='direct':
        op,*_=wrapper(sink=DirectSink())
        out=op.evaluate(request=request())
    else:
        op,*_=installed(sink=RubricSink())
        out=op.generate(source=source())
    assert type(out) is bytes

@pytest.mark.parametrize('operation',('direct','rubric'))
def test_sink_foreign_class_descriptor_not_invoked_after_callback(operation):
    calls=[]
    if operation=='direct':
        class ForeignEvent:
            __slots__=ProviderAccountingEvent.__slots__
            def __getattribute__(self,name):
                calls.append(name)
                return object.__getattribute__(self,name)
        class MutatingSink(DirectSink):
            def record_outcome(self,*,event):
                identity=event.identity
                status=event.status
                object.__setattr__(event,'__class__',ForeignEvent)
                return ProviderAccountingReceipt(identity.event_ref,identity.operation_ref,status)
        op,*_=wrapper(sink=MutatingSink())
        with pytest.raises(ProviderAccountingIndeterminate) as caught:
            op.evaluate(request=request())
    else:
        class ForeignEvent:
            __slots__=RubricAccountingEvent.__slots__
            def __getattribute__(self,name):
                calls.append(name)
                return object.__getattribute__(self,name)
        class MutatingSink(RubricSink):
            def record_rubric_generation(self,*,event):
                identity=event.identity
                approval=event.approval_ref
                status=event.status
                object.__setattr__(event,'__class__',ForeignEvent)
                return RubricAccountingReceipt(identity.event_ref,identity.operation_ref,approval,status)
        op,*_=installed(sink=MutatingSink())
        with pytest.raises(RubricAccountingIndeterminate) as caught:
            op.generate(source=source())
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert calls == [], f'Untrusted foreign class getter executed during accounting readmission: {calls}'
