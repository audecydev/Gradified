"""Cross-boundary benchmark source to actual claimed trial integration checks."""
from dataclasses import replace
from hashlib import sha256
import pytest

from grading.benchmark.offline_trial import OfflineTrialDenied, OfflineTrialIndeterminate
from grading.benchmark.source_bound_trial import SourceBoundOfflineReplayTrial
from grading.benchmark.qualification import BenchmarkCaseReference, BenchmarkSourceManifest
from test_offline_trial import Backend, Reader, Replay, Audit, DATA, REQ


def manifest():
    case=lambda n: BenchmarkCaseReference(f'case-{n}',f'label-{n}','label-v1',f'{n:064x}')
    return BenchmarkSourceManifest('tenant','benchmark-run','source-policy','policy-v1',
        'dataset-A','rev-1',sha256(DATA).hexdigest(),
        'fixture-evaluator','fixture-config',
        (case(1),),(case(2),),(case(3),))


def install(*, source=None, request=REQ, split='development', backend=None,
            reader=None, executor=None, history=None):
    b=backend if backend is not None else Backend()
    r=reader if reader is not None else Reader()
    e=executor if executor is not None else Replay()
    h=history if history is not None else Audit()
    t=SourceBoundOfflineReplayTrial(source=source if source is not None else manifest(),
        request=request, split=split, claims=b, reader=r, executor=e, history=h,
        max_identifier_characters=100, max_cases=12)
    return t,b,r,e,h


def test_source_bound_replay_is_digest_only_and_teacher_label_not_certified():
    trial,b,r,e,h=install()
    observed=trial.run()
    assert (b.calls,r.calls,e.calls,len(h.events))==(1,1,1,1)
    assert observed.evidence_type=='STRUCTURALLY_BOUND_UNVERIFIED_OFFLINE_REPLAY'
    assert observed.teacher_annotation_ref=='label-1'
    assert observed.teacher_annotation_sha256==f'{1:064x}'
    assert observed.observation.output_sha256==sha256(b'fixture-response').hexdigest()
    assert not hasattr(observed,'grade') and not hasattr(observed,'raw_output')
    with pytest.raises(OfflineTrialDenied):trial.run()
    assert e.calls==1


@pytest.mark.parametrize('field,wrong',[
    ('tenant_ref','foreign'),('benchmark_run_ref','other-run'),
    ('dataset_ref','other'),('dataset_revision','other'),
    ('dataset_sha256','b'*64),('evaluator_ref','other'),
    ('configuration_ref','other'),
])
def test_wrong_source_never_claims_or_reads(field,wrong):
    b,r,e,h=Backend(),Reader(),Replay(),Audit()
    with pytest.raises(OfflineTrialDenied):
        install(source=replace(manifest(),**{field:wrong}),backend=b,reader=r,executor=e,history=h)
    assert (b.calls,r.calls,e.calls,len(h.events))==(0,0,0,0)


@pytest.mark.parametrize('trial_request,split',[
    (replace(REQ,case_ref='case-3'),'development'),
    (REQ,'heldout'),(REQ,'unknown'),
    (replace(REQ,execution_mode='LIVE_PROVIDER_ONLY'),'development'),
    (replace(REQ,case_ref='not-in-manifest'),'development'),
])
def test_foreign_case_split_and_live_mode_denied_before_effects(trial_request,split):
    b,r,e,h=Backend(),Reader(),Replay(),Audit()
    with pytest.raises(OfflineTrialDenied):
        install(request=trial_request,split=split,backend=b,reader=r,executor=e,history=h)
    assert (b.calls,r.calls,e.calls,len(h.events))==(0,0,0,0)


def test_does_not_reuse_caller_mutated_teacher_annotation_after_admission():
    given=manifest()
    t,b,r,e,h=install(source=given)
    object.__setattr__(given.development[0],'teacher_annotation_ref','foreign')
    result=t.run()
    assert result.teacher_annotation_ref=='label-1'


def test_unknown_claim_does_not_read_or_emit_source_bound_evidence():
    t,b,r,e,h=install(backend=Backend(error=TimeoutError('PRIVATE CLAIM')))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,r.calls,e.calls,len(h.events))==(1,0,0,0)


def test_history_ack_lost_yields_uncertainty_and_no_second_replay():
    t,b,r,e,h=install(history=Audit(error=TimeoutError('PRIVATE AUDIT')))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,r.calls,e.calls,len(h.events))==(1,1,1,1)
    with pytest.raises(OfflineTrialDenied):t.run()
    assert e.calls==1


def test_immutable_owned_installation_and_sanitized_ambient_error():
    t,*_=install()
    with pytest.raises(AttributeError): del t._trial
    with pytest.raises(AttributeError):t._trial=object()
    try:
        raise RuntimeError('PRIVATE ambient source')
    except RuntimeError:
        with pytest.raises(OfflineTrialDenied) as caught:
            install(split='foreign')
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_valid_heldout_case_replays_only_when_explicitly_selected():
    heldout_request=replace(REQ,case_ref='case-3',trial_request_ref='heldout-trial-1')
    t,b,r,e,h=install(request=heldout_request,split='heldout')
    result=t.run()
    assert result.split=='heldout' and result.case_ref=='case-3'
    assert result.teacher_annotation_ref=='label-3'
    assert (b.calls,r.calls,e.calls,len(h.events))==(1,1,1,1)


def test_foreign_reader_data_never_yields_source_bound_evidence():
    t,b,r,e,h=install(reader=Reader(data=b'foreign-dataset'))
    with pytest.raises(OfflineTrialIndeterminate):t.run()
    assert (b.calls,r.calls,e.calls,len(h.events))==(1,1,0,1)
    assert h.events[0].status=='TRIAL_UNKNOWN'


def test_cross_split_teacher_reference_alias_denied_before_backend():
    given=manifest()
    heldout=(replace(given.heldout[0],teacher_annotation_ref='label-1'),)
    b,r,e,h=Backend(),Reader(),Replay(),Audit()
    with pytest.raises(OfflineTrialDenied):
        install(source=replace(given,heldout=heldout),backend=b,reader=r,executor=e,history=h)
    assert (b.calls,r.calls,e.calls,len(h.events))==(0,0,0,0)


def test_callback_attempts_runtime_rebind_does_not_change_installed_claim():
    b=Backend()
    t,b,r,e,h=install(backend=b)
    b.authorize_and_claim=lambda **kw: (_ for _ in ()).throw(AssertionError('REPLACED'))
    evidence=t.run()
    assert evidence.evidence_type=='STRUCTURALLY_BOUND_UNVERIFIED_OFFLINE_REPLAY'
    assert (b.calls,r.calls,e.calls,len(h.events))==(1,1,1,1)
