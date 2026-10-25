from __future__ import annotations

from dataclasses import replace

import pytest
from grading.providers.operational_policy import (
    OperationalPolicy,ProviderStepFact,StepDisposition as D,PolicyBoundDirectTransport,
)
from grading.providers.attempt_accounting import (
    ProviderAccountingDenied,ProviderAccountingIndeterminate,ProviderTransportOutcome,
    ProviderPhysicalObservation,
)
from test_attempt_accounting import request,identity

IDENTITY=identity()
UNKNOWN=ProviderPhysicalObservation(None,None,None,None,None,None,None,None)

class Issuer:
    def __init__(self, *, plan=None,error=None):self.calls=0;self.plan=plan;self.error=error
    def authorize_execution_policy(self, *, identity):
        self.calls+=1
        if self.error:raise self.error
        return self.plan or OperationalPolicy(identity,'approved-policy','v1',2,5000,1,None)

class Step:
    def __init__(self, answers=None):self.calls=[];self.answers=list(answers or [ProviderStepFact(D.RESPONSE,ProviderTransportOutcome(b'ok',UNKNOWN))])
    def execute_step(self, *, request,identity,policy,attempt_index,deadline_milliseconds):
        self.calls.append((attempt_index,deadline_milliseconds))
        return self.answers[len(self.calls)-1]

class Wait:
    def __init__(self):self.calls=[]
    def wait_before_retry(self, *, identity,attempt_index,milliseconds):
        self.calls.append((attempt_index,milliseconds))

def make(issuer=None,step=None,wait=None):
    issuer=issuer or Issuer();step=step or Step();wait=wait or Wait()
    return PolicyBoundDirectTransport(identity=IDENTITY,authority=issuer,transport_step=step,
           backoff_clock=wait,max_identifier_characters=100,max_dispatches=3,
           max_deadline_milliseconds=10000,max_backoff_milliseconds=100),issuer,step,wait


def test_original_success_with_explicit_approved_policy_once():
    transport,issuer,step,wait=make()
    assert transport.execute_once(request=request(),identity=IDENTITY).raw_payload==b'ok'
    assert (issuer.calls,len(step.calls),len(wait.calls))==(1,1,0)
    with pytest.raises(ProviderAccountingDenied):transport.execute_once(request=request(),identity=IDENTITY)


def test_definitive_no_effect_can_retry_with_bounded_authorized_wait():
    no=ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None)
    yes=ProviderStepFact(D.RESPONSE,ProviderTransportOutcome(b'ok',UNKNOWN))
    transport,issuer,step,wait=make(step=Step([no,yes]))
    assert transport.execute_once(request=request(),identity=IDENTITY).raw_payload==b'ok'
    assert step.calls==[(1,5000),(2,5000)] and wait.calls==[(1,1)]

@pytest.mark.parametrize('first',[ProviderStepFact(D.UNKNOWN,None),
                                  ProviderStepFact(D.DEFINITIVE_NO_EFFECT,ProviderTransportOutcome(b'bad',UNKNOWN))])
def test_ambiguous_or_inconsistent_step_does_not_retry(first):
    t,issuer,step,wait=make(step=Step([first]))
    with pytest.raises(ProviderAccountingIndeterminate):t.execute_once(request=request(),identity=IDENTITY)
    assert len(step.calls)==1 and wait.calls==[]


def test_no_effect_until_bounded_attempts_exhausted():
    no=ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None)
    t,issuer,step,wait=make(step=Step([no,no,no]))
    with pytest.raises(ProviderAccountingIndeterminate):t.execute_once(request=request(),identity=IDENTITY)
    assert len(step.calls)==2 and len(wait.calls)==1

@pytest.mark.parametrize('wrong',[
    lambda p:replace(p,fallback_ref='ANY'),
    lambda p:replace(p,max_dispatches=4),
    lambda p:replace(p,backoff_milliseconds=101),
    lambda p:replace(p,deadline_milliseconds=0),
    lambda p:replace(p,identity=replace(p.identity,provider_id='foreign')),
])
def test_policy_outside_installed_caps_denied_before_transport(wrong):
    approved=OperationalPolicy(IDENTITY,'policy','v1',2,5000,1,None)
    t,issuer,step,wait=make(issuer=Issuer(plan=wrong(approved)))
    with pytest.raises(ProviderAccountingDenied):t.execute_once(request=request(),identity=IDENTITY)
    assert issuer.calls==1 and step.calls==[]


def test_no_policy_callback_denies_positive_provider_dispatch():
    t,issuer,step,wait=make(issuer=Issuer(error=ProviderAccountingDenied('private provider-policy denial')))
    with pytest.raises(ProviderAccountingDenied) as e:t.execute_once(request=request(),identity=IDENTITY)
    assert e.value.__context__ is None and step.calls==[]


def test_policy_timeout_never_assumed_to_be_denial_or_no_effect():
    t,issuer,step,wait=make(issuer=Issuer(error=TimeoutError('private')))
    with pytest.raises(ProviderAccountingIndeterminate):t.execute_once(request=request(),identity=IDENTITY)
    assert step.calls==[]


def test_mismatched_provider_request_before_policy_contact():
    t,issuer,step,wait=make()
    with pytest.raises(ProviderAccountingDenied):
        t.execute_once(request=replace(request(),question_id='other'),identity=IDENTITY)
    assert issuer.calls==0 and step.calls==[]


def test_step_changes_plan_after_dispatch_and_cannot_influence_retry():
    class Change(Step):
        def execute_step(self, *, request,identity,policy,attempt_index,deadline_milliseconds):
            self.calls.append((attempt_index,deadline_milliseconds))
            object.__setattr__(policy,'deadline_milliseconds',9000)
            return ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None)
    t,issuer,step,wait=make(step=Change())
    with pytest.raises(ProviderAccountingDenied):t.execute_once(request=request(),identity=IDENTITY)
    assert len(step.calls)==1 and wait.calls==[]


def test_step_mutates_identity_and_raises_integrity_dominates_timeout():
    class Change(Step):
        def execute_step(self, *, request,identity,policy,attempt_index,deadline_milliseconds):
            self.calls.append(1)
            object.__setattr__(identity,'attempt_id','foreign')
            raise TimeoutError('PRIVATE_SIDE_EFFECT')
    t,issuer,step,wait=make(step=Change())
    with pytest.raises(ProviderAccountingDenied) as e:t.execute_once(request=request(),identity=IDENTITY)
    assert e.value.__context__ is None and wait.calls==[]


def test_f36_transport_integrates_with_existing_b58_one_shot_accounting():
    from test_attempt_accounting import OneShotDirectTextAccountingProvider, Sink
    policy_transport, issuer, step, wait = make()
    sink = Sink()
    accounting = OneShotDirectTextAccountingProvider(
        identity=IDENTITY,transport=policy_transport,sink=sink,
        max_identifier_characters=100,max_raw_response_bytes=1024)
    assert accounting.evaluate(request=request())==b'ok'
    assert (issuer.calls,len(step.calls),len(sink.events))==(1,1,1)
    assert sink.events[0].status=='RESULT_RETURNED'
    assert sink.events[0].observation.physical_request_count is None
    with pytest.raises(ProviderAccountingDenied):accounting.evaluate(request=request())
    assert len(step.calls)==1


def test_backoff_mutates_query_then_raises_integrity_dominates_timeout():
    class MutateWait(Wait):
        def wait_before_retry(self, *, identity,attempt_index,milliseconds):
            self.calls.append((attempt_index,milliseconds))
            object.__setattr__(identity,'event_ref','foreign-event')
            raise TimeoutError('PRIVATE_BACKOFF')
    wait=MutateWait()
    no=ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None)
    t,issuer,step,wait=make(step=Step([no]),wait=wait)
    with pytest.raises(ProviderAccountingDenied) as e:
        t.execute_once(request=request(),identity=IDENTITY)
    assert e.value.__context__ is None and len(step.calls)==1


def test_f36_policy_constructor_sanitizes_private_ambient_context():
    try:
        raise RuntimeError('PRIVATE_AMBIENT_POLICY')
    except RuntimeError:
        with pytest.raises(ProviderAccountingDenied) as exc:
            PolicyBoundDirectTransport(identity=IDENTITY,authority=Issuer(),transport_step=Step(),
                 backoff_clock=Wait(),max_identifier_characters=0,
                 max_dispatches=3,max_deadline_milliseconds=5000,max_backoff_milliseconds=100)
    assert exc.value.__context__ is None and exc.value.__cause__ is None


def test_unknown_effect_must_not_try_second_step_even_if_second_would_succeed():
    uncertain=ProviderStepFact(D.UNKNOWN,None)
    success=ProviderStepFact(D.RESPONSE,ProviderTransportOutcome(b'forbidden-second-response',UNKNOWN))
    t,issuer,step,wait=make(step=Step([uncertain,success]))
    with pytest.raises(ProviderAccountingIndeterminate):
        t.execute_once(request=request(),identity=IDENTITY)
    assert len(step.calls)==1 and not wait.calls


def test_multistep_final_step_telemetry_not_silently_counted_as_total():
    # Step-local observations are not cumulative usage of the operation.
    reported = ProviderPhysicalObservation(1,0,50,20,100,17,'USD','step-two-only')
    t, _, step, wait = make(step=Step([
        ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None),
        ProviderStepFact(D.RESPONSE,ProviderTransportOutcome(b'ok',reported))]))
    outcome = t.execute_once(request=request(),identity=IDENTITY)
    assert outcome.raw_payload == b'ok'
    assert outcome.observation == UNKNOWN
    assert len(step.calls) == 2 and len(wait.calls) == 1


def test_explicit_cumulative_scope_retains_observation_for_qualified_adapter():
    reported = ProviderPhysicalObservation(2,1,50,20,100,17,'USD','cumulative-source')
    t, _, step, wait = make(step=Step([
        ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None),
        ProviderStepFact(D.RESPONSE,ProviderTransportOutcome(b'ok',reported),
                         'CUMULATIVE_OPERATION')]))
    outcome = t.execute_once(request=request(),identity=IDENTITY)
    assert outcome.observation == reported
    assert len(step.calls) == 2 and len(wait.calls) == 1


def test_invalid_telemetry_scope_never_admits_a_response():
    class Foreign:
        def __eq__(self, other):
            raise AssertionError('foreign equality must not be called')
    t, _, step, wait = make(step=Step([ProviderStepFact(D.RESPONSE,
        ProviderTransportOutcome(b'private',UNKNOWN),Foreign())]))
    with pytest.raises(ProviderAccountingIndeterminate):
        t.execute_once(request=request(),identity=IDENTITY)
    assert len(step.calls) == 1 and wait.calls == []


def test_no_effect_cannot_claim_cumulative_telemetry_scope():
    t, _, step, wait = make(step=Step([
        ProviderStepFact(D.DEFINITIVE_NO_EFFECT,None,'CUMULATIVE_OPERATION')]))
    with pytest.raises(ProviderAccountingIndeterminate):
        t.execute_once(request=request(),identity=IDENTITY)
    assert len(step.calls) == 1 and wait.calls == []
