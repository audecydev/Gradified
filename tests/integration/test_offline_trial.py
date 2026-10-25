from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
import pytest

from grading.benchmark.offline_trial import (
    OfflineResourceLimits as Caps, OfflineTrialRequest as Req,
    OfflineTrialClaim as Claim, TrialClaimDisposition as D,
    OfflineTrialOutput as Output, OfflineTrialReceipt as Receipt,
    ClaimedOfflineReplayTrial as Trial, OfflineTrialDenied, OfflineTrialIndeterminate,
)

DATA = b'controlled-offline-fixture-v1'
CAPS = Caps(1024,1024,1,1,0)
REQ = Req('tenant','benchmark-run','trusted-request-1','case-1',
          'dataset-A','rev-1',sha256(DATA).hexdigest(),'scope','fixture-evaluator',
          'fixture-config','OFFLINE_REPLAY',CAPS)

class Backend:
    def __init__(self, *, disposition=D.FRESH, mutate=None, error=None):
        self.calls=0; self.disposition=disposition; self.mutate=mutate; self.error=error
    def authorize_and_claim(self, *, request):
        self.calls+=1
        if self.mutate:self.mutate(request)
        if self.error:raise self.error
        if self.disposition is D.FRESH:
            return Claim(request,D.FRESH,'backend-trial','backend-event','read-grant','policy','v1')
        return Claim(request,self.disposition,None,None,None,None,None)
class Reader:
    def __init__(self, data=DATA, *, error=None, mutate=None):
        self.calls=0;self.data=data;self.error=error;self.mutate=mutate
    def read_dataset(self, *, request, claim, max_bytes):
        self.calls+=1
        assert max_bytes == CAPS.max_dataset_bytes
        if self.mutate:self.mutate(request,claim)
        if self.error:raise self.error
        return self.data
class Replay:
    def __init__(self, *, error=None, mutate=None):
        self.calls=0;self.error=error;self.mutate=mutate
    def execute_replay(self, *, request, claim, dataset_bytes, max_output_bytes):
        self.calls+=1
        assert dataset_bytes == DATA and max_output_bytes == CAPS.max_output_bytes
        if self.mutate:self.mutate(request,claim)
        if self.error:raise self.error
        return Output(b'fixture-response')
class Audit:
    def __init__(self, *, error=None, mutate=None):
        self.events=[];self.error=error;self.mutate=mutate
    def record_trial(self, *, event):
        self.events.append(event)
        if self.mutate:self.mutate(event)
        if self.error:raise self.error
        return Receipt(event.event_ref,event.trial_ref,event.status,event.output_sha256)

def make(*, req=REQ, backend=None, reader=None, replay=None, audit=None):
    b=backend or Backend();d=reader or Reader();e=replay or Replay();a=audit or Audit()
    return (Trial(request=req,claims=b,reader=d,executor=e,history=a,
                  max_identifier_characters=100), b,d,e,a)


def test_valid_offline_replay_is_digest_only_no_grade_or_teacher_claim():
    trial,b,d,e,a=make()
    result=trial.run()
    assert (b.calls,d.calls,e.calls,len(a.events)) == (1,1,1,1)
    assert result.evidence_type=='NON_AUTHORITATIVE_OFFLINE_REPLAY'
    assert result.output_sha256==sha256(b'fixture-response').hexdigest()
    assert result.request == REQ and not hasattr(result,'grade')
    assert not hasattr(result,'raw_output') and a.events[0].status=='TRIAL_OBSERVED'
    with pytest.raises(OfflineTrialDenied):trial.run()
    assert e.calls==1

@pytest.mark.parametrize('disposition',[D.REPLAY,D.CONFLICT,D.REVOKED,D.UNKNOWN])
def test_nonfresh_claim_never_reads_or_executes(disposition):
    t,b,d,e,a=make(backend=Backend(disposition=disposition))
    with pytest.raises(OfflineTrialIndeterminate if disposition is D.UNKNOWN else OfflineTrialDenied):t.run()
    assert (b.calls,d.calls,e.calls,len(a.events))==(1,0,0,0)

@pytest.mark.parametrize('req',[
    replace(REQ,execution_mode='LIVE_PROVIDER'),
    replace(REQ,limits=replace(CAPS,max_external_provider_requests=1)),
    replace(REQ,limits=replace(CAPS,max_trial_invocations=2)),
    replace(REQ,limits=replace(CAPS,max_parallel_invocations=2)),
    replace(REQ,limits=replace(CAPS,max_dataset_bytes=0)),
    replace(REQ,limits=replace(CAPS,max_output_bytes=True)),
    replace(REQ,dataset_sha256='bad'),
])
def test_invalid_or_live_profile_rejected_before_grants_and_protected_read(req):
    b,d,e=Backend(),Reader(),Replay()
    with pytest.raises(OfflineTrialDenied):make(req=req,backend=b,reader=d,replay=e)
    assert (b.calls,d.calls,e.calls)==(0,0,0)


def test_claim_issuer_mutates_request_scope_then_returns_is_indeterminate_before_read():
    t,b,d,e,a=make(backend=Backend(mutate=lambda req:object.__setattr__(req,'tenant_ref','foreign')))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,d.calls,e.calls)==(1,0,0)


def test_claim_backend_exception_is_indeterminate_without_read():
    t,b,d,e,a=make(backend=Backend(error=TimeoutError('PRIVATE_CLAIM')))
    with pytest.raises(OfflineTrialIndeterminate) as caught:t.run()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert (b.calls,d.calls,e.calls)==(1,0,0)


def test_protected_read_returns_foreign_digest_does_not_execute_replay():
    t,b,d,e,a=make(reader=Reader(data=b'unapproved-other-dataset'))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,d.calls,e.calls,len(a.events))==(1,1,0,1)
    assert a.events[0].status=='TRIAL_UNKNOWN'


def test_reader_mutates_claim_then_restores_matching_ack_is_denied():
    def change(req,claim):object.__setattr__(claim,'trial_ref','foreign-trial')
    t,b,d,e,a=make(reader=Reader(mutate=change))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert e.calls==0 and a.events[0].trial_ref=='backend-trial'
    assert a.events[0].status=='TRIAL_UNKNOWN'


def test_replay_exception_writes_unknown_history_no_grade():
    t,b,d,e,a=make(replay=Replay(error=TimeoutError('PRIVATE_REPLAY')))
    with pytest.raises(OfflineTrialIndeterminate) as caught:t.run()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(a.events)==1 and a.events[0].status=='TRIAL_UNKNOWN'


def test_audit_mutated_status_and_foreign_receipt_are_not_accepted():
    def change(event):object.__setattr__(event,'status','TRIAL_FOREIGN')
    t,b,d,e,a=make(audit=Audit(mutate=change))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,d.calls,e.calls)==(1,1,1)


def test_history_lost_ack_is_indeterminate_with_one_replay():
    t,b,d,e,a=make(audit=Audit(error=TimeoutError('PRIVATE_COMMIT')))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,d.calls,e.calls,len(a.events)) == (1,1,1,1)
    with pytest.raises(OfflineTrialDenied):t.run()
    assert e.calls==1


def test_same_adapter_concurrent_calls_execute_replay_only_once():
    trial,b,d,e,a=make()
    def go():
        try:
            trial.run()
            return 'ok'
        except OfflineTrialDenied:return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda x:go(), range(2))) == ['denied','ok']
    assert (b.calls,d.calls,e.calls)==(1,1,1)


def test_installed_operations_remain_original_after_reconfiguring_owner():
    backend=Backend(); trial,b,d,e,a=make(backend=backend)
    backend.authorize_and_claim = lambda **kw: (_ for _ in ()).throw(AssertionError('replaced'))
    assert trial.run().evidence_type=='NON_AUTHORITATIVE_OFFLINE_REPLAY'


def test_foreign_claim_scope_stops_before_dataset_reader():
    class Foreign(Backend):
        def authorize_and_claim(self, *, request):
            self.calls+=1
            return Claim(replace(request,tenant_ref='other-tenant'),D.FRESH,
                         'backend-trial','backend-event','read-grant','policy','v1')
    t,b,d,e,a=make(backend=Foreign())
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,d.calls,e.calls)==(1,0,0)


def test_foreign_equality_receipt_field_never_executes_comparison_or_returns_evidence():
    class Malicious:
        def __eq__(self, other):
            raise AssertionError('foreign equality executed')
    class EvilAudit(Audit):
        def record_trial(self, *, event):
            self.events.append(event)
            return Receipt(event.event_ref,Malicious(),event.status,event.output_sha256)
    t,b,d,e,a=make(audit=EvilAudit())
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,d.calls,e.calls)==(1,1,1)


def test_two_independent_trial_adapters_share_real_atomic_claim_fixture():
    from threading import Lock
    class AtomicBackend(Backend):
        def __init__(self):
            super().__init__();self._mutex=Lock();self._seen=set()
        def authorize_and_claim(self, *, request):
            with self._mutex:
                self.calls+=1
                if request.trial_request_ref in self._seen:
                    return Claim(request,D.REPLAY,None,None,None,None,None)
                self._seen.add(request.trial_request_ref)
                return Claim(request,D.FRESH,'backend-trial','backend-event','read-grant','policy','v1')
    backend=AtomicBackend();reader=Reader();replay=Replay();audit=Audit()
    trials=[make(backend=backend,reader=reader,replay=replay,audit=audit)[0] for _ in range(2)]
    def run(trial):
        try:return trial.run().evidence_type
        except OfflineTrialDenied:return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,trials))
    assert sorted(results)==['NON_AUTHORITATIVE_OFFLINE_REPLAY','denied']
    assert (backend.calls,reader.calls,replay.calls,len(audit.events))==(2,1,1,1)
    # This is a fixture guarantee, not proof the real backend uses durable CAS.


def test_replay_mutates_scope_before_return_and_cannot_release_evidence():
    class MutatingReplay(Replay):
        def execute_replay(self, *, request, claim, dataset_bytes, max_output_bytes):
            self.calls+=1
            object.__setattr__(request,'run_ref','another-run')
            return Output(b'valid-looking-output')
    t,b,d,e,a=make(replay=MutatingReplay())
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert a.events[0].status=='TRIAL_UNKNOWN'


def test_history_mutates_claim_scope_via_event_and_cannot_admit_evidence():
    def change(event):object.__setattr__(event.request,'run_ref','another-run')
    t,b,d,e,a=make(audit=Audit(mutate=change))
    with pytest.raises(OfflineTrialIndeterminate):t.run()


def test_trial_constructor_does_not_retain_private_ambient_exception():
    try:
        raise RuntimeError('PRIVATE_AMBIENT_TRIAL')
    except RuntimeError:
        with pytest.raises(OfflineTrialDenied) as exc:
            Trial(request=replace(REQ,execution_mode='LIVE'),claims=Backend(),reader=Reader(),
                  executor=Replay(),history=Audit(),max_identifier_characters=100)
    assert exc.value.__context__ is None and exc.value.__cause__ is None


def test_two_distinct_trials_one_run_respect_shared_atomic_claim_quota():
    """Conformance fixture: demonstrates the required backend mechanism, not
    engine-owned proof that an arbitrary installed backend is atomic.
    """
    from threading import Lock, Barrier
    barrier = Barrier(2)

    class SharedQuotaBackend(Backend):
        def __init__(self):
            super().__init__()
            self.lock = Lock()
            self.trials_by_run = set()

        def authorize_and_claim(self, *, request):
            with self.lock:
                self.calls += 1
                key = (request.tenant_ref, request.run_ref)
                if key in self.trials_by_run:
                    return Claim(request,D.CONFLICT,None,None,None,None,None)
                self.trials_by_run.add(key)
                return Claim(request,D.FRESH,'backend-trial','backend-event',
                             'read-grant','policy','v1')

    shared = SharedQuotaBackend()
    first = replace(REQ,trial_request_ref='trusted-1')
    second = replace(REQ,trial_request_ref='trusted-2',case_ref='case-2')
    readers = [Reader(),Reader()]
    replays = [Replay(),Replay()]
    audits = [Audit(),Audit()]
    trials = [make(req=req,backend=shared,reader=reader,replay=replay,audit=audit)[0]
              for req,reader,replay,audit in zip((first,second),readers,replays,audits)]

    def run(candidate):
        barrier.wait()
        try:
            candidate.run()
            return 'admitted'
        except OfflineTrialDenied:
            return 'denied'

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run,trials))
    assert sorted(outcomes) == ['admitted','denied']
    assert shared.calls == 2
    assert sum(r.calls for r in readers) == 1
    assert sum(r.calls for r in replays) == 1
    assert sum(len(a.events) for a in audits) == 1
