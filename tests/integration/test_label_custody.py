from dataclasses import replace
import pytest
from grading.benchmark.label_custody import (
    KIND, LabelCustodyDenied, LabelCustodyIndeterminate, LabelLinkageEvent,
    LabelLinkageReceipt, OneShotNonAcademicLabelLinkageAudit,
)
from test_label_reference import bound


class History:
    def __init__(self, change=None, failure=None):
        self.change=change
        self.failure=failure
        self.calls=0
        self.events=[]

    def record_label_linkage(self, *, event):
        self.calls+=1
        self.events.append(event)
        if self.change is not None:
            return self.change(event)
        if self.failure is not None:
            raise self.failure
        c=event.continuity
        return LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,
                                   c.attestation_ref,event.event_kind,'RECORDED')


def candidate():
    q, issuer=bound()
    return q.reconcile()


def installed(*, continuity=None, history=None):
    h=history if history is not None else History()
    a=OneShotNonAcademicLabelLinkageAudit(
        continuity=candidate() if continuity is None else continuity,
        history=h,max_identifier_characters=100)
    return a,h


def test_acknowledged_nonacademic_event_and_one_attempt_only():
    a,h=installed()
    receipt=a.record()
    assert receipt.status=='RECORDED' and receipt.event_kind==KIND
    assert h.calls==1 and len(h.events)==1
    assert h.events[0].event_kind==KIND
    assert not hasattr(h.events[0],'grade') and not hasattr(receipt,'teacher_mark')
    with pytest.raises(LabelCustodyDenied):a.record()
    assert h.calls==1


@pytest.mark.parametrize('field,bad',[
    ('trial_request_ref','different'),('observation_event_ref','different'),
    ('attestation_ref','different'),('event_kind','OFFICIAL_GRADE'),
    ('status','APPROVED'),('status','UNKNOWN'),
])
def test_wrong_receipt_never_returns_positive_custody(field,bad):
    def corrupt(e):
        c=e.continuity
        receipt=LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,
                                    c.attestation_ref,KIND,'RECORDED')
        return replace(receipt,**{field:bad})
    a,h=installed(history=History(change=corrupt))
    with pytest.raises(LabelCustodyIndeterminate):a.record()
    assert h.calls==1


@pytest.mark.parametrize('field,bad',[
    ('issuer_ref',''),('attestation_ref', ''),('evidence_type','TEACHER_APPROVED'),
    ('output_sha256','bad'),('observation_event_ref',''),
])
def test_invalid_continuity_denied_before_history(field,bad):
    c=candidate();h=History()
    with pytest.raises(LabelCustodyDenied):installed(continuity=replace(c,**{field:bad}),history=h)
    assert h.calls==0


def test_output_is_detached_from_caller_mutation():
    c=candidate()
    a,h=installed(continuity=c)
    object.__setattr__(c,'issuer_ref','evil')
    receipt=a.record()
    assert receipt.status=='RECORDED'
    assert h.events[0].continuity.issuer_ref=='issuer-A'


@pytest.mark.parametrize('raised', [False, True])
def test_event_mutation_on_callback_success_or_failure_indeterminate(raised):
    def change(event):
        object.__setattr__(event.continuity.query,'case_ref','changed')
        if raised:raise RuntimeError('PRIVATE-STORE-ERROR')
        c=event.continuity
        return LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,
                                   c.attestation_ref,KIND,'RECORDED')
    a,h=installed(history=History(change=change))
    with pytest.raises(LabelCustodyIndeterminate) as caught:a.record()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert h.calls==1


def test_private_write_exception_is_indeterminate_and_not_retried():
    a,h=installed(history=History(failure=TimeoutError('PRIVATE_DB_TOKEN')))
    with pytest.raises(LabelCustodyIndeterminate) as caught:a.record()
    assert 'PRIVATE' not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    with pytest.raises(LabelCustodyDenied):a.record()
    assert h.calls==1


def test_history_operation_captured_against_rebinding():
    h=History()
    a,h=installed(history=h)
    h.record_label_linkage=lambda **kw: (_ for _ in ()).throw(RuntimeError('REBOUND'))
    assert a.record().status=='RECORDED'


def test_immutable_installed_custody():
    a,h=installed()
    with pytest.raises(AttributeError):a._installation=None
    with pytest.raises(AttributeError):del a._installation
    assert a.record().status=='RECORDED'


def test_receipt_foreign_equality_subclass_rejected():
    class Foreign(str):
        def __eq__(self, x):return True
    def forge(event):
        c=event.continuity
        return LabelLinkageReceipt(Foreign('not-original'),c.observation_event_ref,
                                   c.attestation_ref,KIND,'RECORDED')
    a,h=installed(history=History(change=forge))
    with pytest.raises(LabelCustodyIndeterminate):a.record()


from grading.benchmark.label_custody import (
    LabelLinkageRecoveryFact, LabelLinkageRecoveryStatus,
    ReadOnlyLabelLinkageRecovery,
)


class Recovery:
    def __init__(self, status=LabelLinkageRecoveryStatus.COMMITTED, mutate=None, error=None):
        self.status=status
        self.mutate=mutate
        self.error=error
        self.calls=0

    def reconcile_label_linkage(self, *, event):
        self.calls+=1
        if self.mutate is not None:
            return self.mutate(event)
        if self.error is not None:
            raise self.error
        c=event.continuity
        receipt=LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,
                                     c.attestation_ref,KIND,'RECORDED') if self.status is LabelLinkageRecoveryStatus.COMMITTED else None
        return LabelLinkageRecoveryFact(event,self.status,receipt)


def recovery(*, store=None):
    store=store if store is not None else Recovery()
    return ReadOnlyLabelLinkageRecovery(continuity=candidate(),store=store,
                                        max_identifier_characters=100),store


@pytest.mark.parametrize('status,has_receipt',[
    (LabelLinkageRecoveryStatus.COMMITTED,True),
    (LabelLinkageRecoveryStatus.NOT_FOUND,False),
    (LabelLinkageRecoveryStatus.CONFLICT,False),
    (LabelLinkageRecoveryStatus.UNKNOWN,False),
])
def test_read_only_recovery_never_writes_or_promotes_status(status,has_receipt):
    r,store=recovery(store=Recovery(status=status))
    result=r.reconcile()
    assert result.status is status and (result.receipt is not None)==has_receipt
    assert store.calls==1
    with pytest.raises(LabelCustodyDenied):r.reconcile()
    assert store.calls==1


def test_foreign_committed_recovery_receipt_never_admitted():
    def foreign(event):
        c=event.continuity
        receipt=LabelLinkageReceipt('OTHER',c.observation_event_ref,c.attestation_ref,KIND,'RECORDED')
        return LabelLinkageRecoveryFact(event,LabelLinkageRecoveryStatus.COMMITTED,receipt)
    r,store=recovery(store=Recovery(mutate=foreign))
    with pytest.raises(LabelCustodyIndeterminate):r.reconcile()
    assert store.calls==1


def test_noncommitted_recovery_cannot_contain_committed_receipt():
    def forge(event):
        c=event.continuity
        receipt=LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,c.attestation_ref,KIND,'RECORDED')
        return LabelLinkageRecoveryFact(event,LabelLinkageRecoveryStatus.NOT_FOUND,receipt)
    r,store=recovery(store=Recovery(mutate=forge))
    with pytest.raises(LabelCustodyIndeterminate):r.reconcile()


@pytest.mark.parametrize('raises',[False,True])
def test_recovery_callback_scope_mutation_on_return_or_exception(raises):
    def corrupt(event):
        object.__setattr__(event.continuity.query,'teacher_annotation_ref','ATTACK')
        if raises:raise RuntimeError('PRIVATE BACKEND')
        return LabelLinkageRecoveryFact(event,LabelLinkageRecoveryStatus.NOT_FOUND,None)
    r,store=recovery(store=Recovery(mutate=corrupt))
    with pytest.raises(LabelCustodyIndeterminate) as caught:r.reconcile()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert store.calls==1


def test_recovery_transport_timeout_indeterminate():
    r,store=recovery(store=Recovery(error=TimeoutError('PRIVATE DB CREDENTIAL')))
    with pytest.raises(LabelCustodyIndeterminate) as caught:r.reconcile()
    assert caught.value.__cause__ is None
    assert store.calls==1


def test_recovery_invalid_event_kind_even_when_claimed_committed():
    def forge(event):
        object.__setattr__(event,'event_kind','OFFICIAL_RESULT')
        c=event.continuity
        receipt=LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,c.attestation_ref,KIND,'RECORDED')
        return LabelLinkageRecoveryFact(event,LabelLinkageRecoveryStatus.COMMITTED,receipt)
    r,store=recovery(store=Recovery(mutate=forge))
    with pytest.raises(LabelCustodyIndeterminate):r.reconcile()
    assert store.calls==1


def test_recovery_returned_foreign_event_not_promoted_to_committed():
    def foreign(event):
        c=event.continuity
        returned=LabelLinkageEvent(replace(c,attestation_ref='OTHER-ASSERTION'))
        receipt=LabelLinkageReceipt(c.query.trial_request_ref,c.observation_event_ref,c.attestation_ref,KIND,'RECORDED')
        return LabelLinkageRecoveryFact(returned,LabelLinkageRecoveryStatus.COMMITTED,receipt)
    r,store=recovery(store=Recovery(mutate=foreign))
    with pytest.raises(LabelCustodyIndeterminate):r.reconcile()
    assert store.calls==1
