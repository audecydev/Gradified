"""Permanent paper execution integrity review regressions: original physical attempt claim read and global recovery custody.

Original independent attacks reproduced on exact prior tree 6efbdc4504876d8132bb5493d1223963db141715.
"""

from dataclasses import replace
import pytest
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.whole_paper_attempt_custody import (ProductionPaperAttemptCustody, PaperCustodyDenied, _admit, PaperRecoveryState)
from tests.integration.test_whole_paper_choice_execution import _setup_one
from tests.integration.test_attempt_authority import Issuer, AtomicStore

class RotatingIssuer(Issuer):
    def __init__(self):
        super().__init__()
        self.revision = 0
    def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                     implementation_ref, eligibility_policy_id,
                                     eligibility_policy_version):
        req=super().identify_reservation_request(scope=scope, family=family,
            runtime_id=runtime_id, runtime_version=runtime_version,
            implementation_ref=implementation_ref,
            eligibility_policy_id=eligibility_policy_id,
            eligibility_policy_version=eligibility_policy_version)
        return replace(req,request_ref='REQUEST-ORIGINAL' if self.revision==0 else 'REQUEST-FOREIGN')

class InspectingStore(AtomicStore):
    def __init__(self):
        super().__init__(); self.recovered_refs=[]
    def reconcile_reservation(self, *, request):
        self.recovered_refs.append(request.request_ref)
        return super().reconcile_reservation(request=request)

class OriginalSource:
    def __init__(self): self.requests={}; self.calls=0
    def resolve_original_request(self, *, plan, question_id, request_ref):
        self.calls+=1
        return self.requests[question_id]

def configured():
    first, plan, *_= _setup_one()
    issuer=RotatingIssuer(); store=InspectingStore()
    attempts=ClaimedAttemptAllocator(issuer=issuer,store=store,max_identifier_characters=128)
    root=ProductionWholePaperChoiceExecutor(contact=first._contact,correlation=first._correlation,
          handoff=first._handoff,attempts=attempts,max_identifier_characters=128,max_questions=10)
    src=OriginalSource(); service=ProductionPaperAttemptCustody(executor=root,attempts=attempts,request_source=src,
          max_identifier_characters=128,max_questions=10)
    record=service.execute_and_capture(plan=plan)
    assert record.outcome.state=='COMPLETE'
    r=record.questions[0].reservation
    src.requests['Q1']=__import__('grading.integration.attempt_authority',fromlist=['AttemptClaimRequest']).AttemptClaimRequest(
      r.request_ref,r.scope,r.family,r.runtime_id,r.runtime_version,r.implementation_ref,
      r.eligibility_policy_id,r.eligibility_policy_version,r.predecessor_result_ref,r.regrade_approval_ref)
    return issuer,store,service,record

def test_original_request_read_must_not_contact_different_issuer_request():
    issuer,store,service,record = configured()
    issuer.revision=1
    recovery=service.reconcile(record=record)
    print('FACT',recovery.questions[0].state, 'BACKEND_READ_REFS',store.recovered_refs)
    assert store.recovered_refs == ['REQUEST-ORIGINAL'], 'Backend must read precisely the original issued request'
    assert recovery.questions[0].state is PaperRecoveryState.RESERVED
    assert issuer.calls == 1, 'Read-only recovery must not ask current issuer to issue a replacement request'

def test_public_denial_must_not_preserve_exception_context():
    issuer,store,service,record = configured()
    try:
        _admit(record.plan,object(),10,128)
    except PaperCustodyDenied as exc:
        print('EXCEPTION', repr(exc.__cause__),repr(exc.__context__),exc.__suppress_context__)
        assert exc.__cause__ is None
        assert exc.__context__ is None, 'Public exception retains private context'
    else:
        pytest.fail('Expected denied')

def test_stable_original_request_permits_read_only_recovery():
    issuer,store,service,record=configured()
    before=store.claims
    recovered=service.reconcile(record=record)
    assert recovered.questions[0].state is PaperRecoveryState.RESERVED
    assert store.recovered_refs == ['REQUEST-ORIGINAL']
    assert store.claims == before


def test_foreign_original_request_denied_before_backend_read():
    issuer,store,service,record=configured()
    original=service._resolve_request.__self__.requests['Q1']
    service._resolve_request.__self__.requests['Q1']=replace(original,request_ref='FOREIGN-ORIGINAL')
    recovered=service.reconcile(record=record)
    assert recovered.questions[0].state is PaperRecoveryState.CONFLICT
    assert store.recovered_refs == []


"""Fresh external adversarial checks on exact submitted C1/C2 tree."""
from dataclasses import replace
import pytest
from tests.integration.test_whole_paper_choice_execution import _setup_two
from grading.integration.attempt_authority import AttemptClaimRequest
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody, PaperRecoveryState


def _as_request(reservation):
    return AttemptClaimRequest(reservation.request_ref,reservation.scope,reservation.family,
        reservation.runtime_id,reservation.runtime_version,reservation.implementation_ref,
        reservation.eligibility_policy_id,reservation.eligibility_policy_version,
        reservation.predecessor_result_ref,reservation.regrade_approval_ref)

@pytest.mark.parametrize('same_field', ['attempt_id', 'reservation_ref'])
def test_recovery_cross_question_collision_must_not_mark_both_reserved(same_field):
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    class OriginalReadOnlySource:
        def resolve_original_request(self, *, plan, question_id, request_ref):
            store.last_reservation = self.records[question_id]
            return _as_request(self.records[question_id])
    lookup=OriginalReadOnlySource()
    custody=ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,request_source=lookup,
                                          max_identifier_characters=128,max_questions=10)
    record=custody.execute_and_capture(plan=plan)
    assert record.outcome.state == 'INDETERMINATE'
    assert len(record.questions)==2
    assert record.questions[0].reservation_validated
    assert not record.questions[1].reservation_validated
    assert record.questions[1].request_ref == 'REQUEST-Q2'
    q1=record.questions[0].reservation
    q2_observed=store.last_reservation
    assert q2_observed.scope.question_id=='Q2'
    assert q2_observed.request_ref=='REQUEST-Q2'
    q2=replace(q2_observed,**{same_field:getattr(q1,same_field)})
    lookup.records={'Q1':q1,'Q2':q2}
    before_claims=store.claims
    recovered=custody.reconcile(record=record)
    assert store.claims==before_claims
    print('CROSS-QUESTION-RECOVERY',same_field, [(q.question_id,q.state,q.reservation.attempt_id if q.reservation else None,q.reservation.reservation_ref if q.reservation else None) for q in recovered.questions])
    # Two distinct questions cannot both report admitted RESERVED against the same physical attempt or reservation identity.
    assert not all(q.state is PaperRecoveryState.RESERVED for q in recovered.questions), 'Duplicate physical identity promoted twice'

def test_unknown_first_recovery_cannot_hide_collision_with_original_verified_attempt():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    class OriginalReadOnlySource:
        def resolve_original_request(self, *, plan, question_id, request_ref):
            if question_id == 'Q1':
                raise RuntimeError('backend read unavailable for first request')
            store.last_reservation = self.q2
            return _as_request(self.q2)
    lookup=OriginalReadOnlySource()
    custody=ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
         request_source=lookup,max_identifier_characters=128,max_questions=10)
    record=custody.execute_and_capture(plan=plan)
    assert record.outcome.state=='INDETERMINATE'
    lookup.q2 = replace(store.last_reservation,attempt_id=record.questions[0].reservation.attempt_id)
    recovery=custody.reconcile(record=record)
    print('COLLISION-WITH-ORIGINAL',[(q.question_id,q.state) for q in recovery.questions])
    assert recovery.questions[0].state is PaperRecoveryState.UNKNOWN
    assert recovery.questions[1].state is PaperRecoveryState.CONFLICT
