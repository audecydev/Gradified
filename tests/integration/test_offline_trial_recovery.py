from __future__ import annotations

from dataclasses import replace

import pytest
from grading.benchmark.recovery import (
    OfflineRecoveryDisposition as D, OfflineTrialRecoveryFact as Fact,
    ReadOnlyOfflineTrialRecovery,
)
from grading.benchmark.offline_trial import (
    OfflineTrialClaim as Claim, TrialClaimDisposition as C,
    OfflineTrialReceipt as Receipt, OfflineTrialDenied, OfflineTrialIndeterminate,
)
from test_offline_trial import REQ

CLAIM = Claim(REQ,C.FRESH,'trial','event','grant','policy','1')
GOOD = Fact(REQ,D.RECORDED,CLAIM,'TRIAL_OBSERVED','a'*64,
            Receipt('event','trial','TRIAL_OBSERVED','a'*64))

class Store:
    def __init__(self,result=GOOD,error=None):self.calls=0;self.result=result;self.error=error
    def reconcile_trial_request(self, *, request):
        self.calls+=1
        if self.error:raise self.error
        return self.result

def reader(store):
    return ReadOnlyOfflineTrialRecovery(request=REQ,store=store,max_identifier_characters=100)


def test_positive_backend_report_is_digest_only_no_provider_or_grade():
    s=Store(); proof=reader(s).reconcile()
    assert proof.disposition is D.RECORDED and proof.output_sha256=='a'*64
    assert s.calls==1 and not hasattr(proof,'grade') and not hasattr(proof,'raw_output')

@pytest.mark.parametrize('kind',[D.NOT_FOUND,D.CONFLICT,D.UNKNOWN])
def test_unresolved_outcomes_are_never_retry_permission(kind):
    proof=reader(Store(Fact(REQ,kind,None,None,None,None))).reconcile()
    assert proof.disposition is kind and proof.claim is None


def test_claimed_but_not_recorded_does_not_invent_a_result():
    proof=reader(Store(Fact(REQ,D.CLAIMED,CLAIM,None,None,None))).reconcile()
    assert proof.disposition is D.CLAIMED and proof.receipt is None

@pytest.mark.parametrize('fact',[
    replace(GOOD,request=replace(REQ,tenant_ref='foreign')),
    replace(GOOD,claim=replace(CLAIM,trial_ref='another')),
    replace(GOOD,receipt=Receipt('foreign','trial','TRIAL_OBSERVED','a'*64)),
    replace(GOOD,recorded_status='TRIAL_UNKNOWN'),
    replace(GOOD,output_sha256=False),
    replace(GOOD,disposition=D.NOT_FOUND),
    Fact(REQ,D.CLAIMED,CLAIM,'TRIAL_OBSERVED',None,None),
])
def test_corrupted_recovery_cannot_be_admitted(fact):
    with pytest.raises(OfflineTrialDenied):reader(Store(fact)).reconcile()


def test_callback_mutate_then_exception_prioritizes_integrity_over_outage():
    class Mutate(Store):
        def reconcile_trial_request(self, *, request):
            object.__setattr__(request,'run_ref','foreign-run')
            raise TimeoutError('PRIVATE_SOURCE')
    with pytest.raises(OfflineTrialDenied) as exc:
        reader(Mutate()).reconcile()
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_callback_timeout_sanitized_and_does_not_return_not_found():
    with pytest.raises(OfflineTrialIndeterminate) as exc:
        reader(Store(error=TimeoutError('PRIVATE_STORE'))).reconcile()
    assert exc.value.__context__ is None


def test_installed_operation_cannot_be_swapped_after_initialization():
    s=Store(); recovery=reader(s)
    s.reconcile_trial_request=lambda **kw: (_ for _ in ()).throw(AssertionError('wrong'))
    assert recovery.reconcile().disposition is D.RECORDED


def test_reentry_rejected_and_outer_fact_unmodified():
    class Reenter(Store):
        def reconcile_trial_request(self, *, request):
            with pytest.raises(OfflineTrialDenied):self.recovery.reconcile()
            return GOOD
    s=Reenter();s.recovery=reader(s)
    assert s.recovery.reconcile().disposition is D.RECORDED


def test_recovery_constructor_cannot_expose_private_ambient_exception():
    try:
        raise RuntimeError('PRIVATE_AMBIENT_RECOVERY')
    except RuntimeError:
        with pytest.raises(OfflineTrialDenied) as exc:
            ReadOnlyOfflineTrialRecovery(request=REQ,store=Store(),max_identifier_characters=0)
    assert exc.value.__context__ is None and exc.value.__cause__ is None
