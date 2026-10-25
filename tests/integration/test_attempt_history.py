"""Engine-owned failure/recovery/regrade grammar; fixtures are not authenticated issuers."""
from dataclasses import replace
import pytest
from grading.integration.attempt_history import (
    AttemptStage, AttemptEffect, CorrelatedAttemptEvent,
    AttemptEventAcknowledgment, AttemptHistoryCustody,
    AttemptHistoryDenied, AttemptHistoryUnavailable,
    AuthorizedRegrade, AuthorizedRegradeCustody, CorrelatedHistoryRecorder,
    RegradeScopedAttemptClaimRequestIssuer,
)
from tests.integration.test_evaluator_invocation import assembled_invoker


def scope_fixture():
    invoker, request, _, _ = assembled_invoker()
    return invoker._installation.handoff.prepare_choice_runtime(request=request).eligibility.scope


class Writer:
    def __init__(self): self.events=[];self.mode='ok'
    def append_attempt_event(self, *, event):
        self.events.append(event)
        if self.mode=='timeout': raise TimeoutError('PRIVATE_DURABLE_STATUS_UNKNOWN')
        if self.mode=='mutate_then_raise':
            object.__setattr__(event,'request_ref','FOREIGN')
            raise RuntimeError('PRIVATE_EVENT_ERROR')
        if self.mode=='foreign':return AttemptEventAcknowledgment(event.event_ref,'FOREIGN','RECEIPT')
        return AttemptEventAcknowledgment(event.event_ref,event.request_ref,'RECEIPT')


def test_pre_and_uncertain_f25_event_do_not_manufacture_attempt_id():
    scope=scope_fixture(); writer=Writer()
    adapter=AttemptHistoryCustody(writer=writer,max_identifier_characters=64)
    for stage,effect in ((AttemptStage.PRE,AttemptEffect.CONFIRMED),
                         (AttemptStage.ATTEMPT,AttemptEffect.UNKNOWN),
                         (AttemptStage.RECOVERY,AttemptEffect.UNKNOWN)):
        evt=CorrelatedAttemptEvent('EVENT-1','STABLE-REQUEST',scope,stage,effect)
        receipt=adapter.record(event=evt)
        assert receipt.event_ref==evt.event_ref and evt.attempt_id is None
    assert len(writer.events)==3


def test_verify_event_requires_actual_f25_identity():
    scope=scope_fixture();writer=Writer()
    adapter=AttemptHistoryCustody(writer=writer,max_identifier_characters=64)
    with pytest.raises(AttemptHistoryDenied):
        adapter.record(event=CorrelatedAttemptEvent('EV','REQUEST',scope,
            AttemptStage.VERIFY,AttemptEffect.CONFIRMED))
    assert not writer.events
    evt=CorrelatedAttemptEvent('EV','REQUEST',scope,AttemptStage.VERIFY,
        AttemptEffect.CONFIRMED,attempt_id='ATT',reservation_ref='RES',result_ref='RESULT')
    adapter.record(event=evt)
    assert len(writer.events)==1


@pytest.mark.parametrize('mode,exc',[
    ('timeout',AttemptHistoryUnavailable),('mutate_then_raise',AttemptHistoryDenied),
    ('foreign',AttemptHistoryDenied),
])
def test_event_backend_failure_privacy_and_no_false_ack(mode,exc):
    scope=scope_fixture();writer=Writer();writer.mode=mode
    adapter=AttemptHistoryCustody(writer=writer,max_identifier_characters=64)
    evt=CorrelatedAttemptEvent('EV','REQUEST',scope,AttemptStage.FAILURE,AttemptEffect.UNKNOWN)
    with pytest.raises(exc) as caught:
        adapter.record(event=evt)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert len(writer.events)==1  # commit might have happened; no rollback claim


class RegradeSource:
    def __init__(self,prior_scope,mode='ok'):
        self.scope=prior_scope;self.mode=mode;self.calls=[]
    def resolve_authorized_regrade(self, *, prior_result_ref):
        self.calls.append(prior_result_ref)
        original=self.scope
        new=replace(original,grading_run_id='NEW-AUTHORIZED-GRADING-RUN')
        grant=AuthorizedRegrade('BACKEND-APPROVAL',prior_result_ref,original,new,'BACKEND-NEW-REQUEST')
        if self.mode=='same_run':return replace(grant,new_scope=original)
        if self.mode=='other_tenant':return replace(grant,new_scope=replace(new,tenant_ref='FOREIGN'))
        if self.mode=='other_result':return replace(grant,predecessor_result_ref='OTHER-RESULT')
        if self.mode=='unavailable':raise RuntimeError('PRIVATE_BACKEND_ERROR')
        return grant


def test_regrade_requires_new_run_and_backend_original_link_without_score_mutation():
    source=RegradeSource(scope_fixture())
    custody=AuthorizedRegradeCustody(source=source,max_identifier_characters=64)
    grant=custody.resolve(prior_result_ref='REAL-PRIOR-RESULT')
    assert grant.predecessor_result_ref=='REAL-PRIOR-RESULT'
    assert grant.new_scope.grading_run_id != grant.predecessor_scope.grading_run_id
    assert source.calls==['REAL-PRIOR-RESULT']


@pytest.mark.parametrize('mode,exception',[
    ('same_run',AttemptHistoryDenied),('other_tenant',AttemptHistoryDenied),
    ('other_result',AttemptHistoryDenied),('unavailable',AttemptHistoryUnavailable),
])
def test_foreign_or_absent_regrade_issuer_never_grants_new_history(mode,exception):
    source=RegradeSource(scope_fixture(),mode=mode)
    custody=AuthorizedRegradeCustody(source=source,max_identifier_characters=64)
    with pytest.raises(exception):custody.resolve(prior_result_ref='REAL-PRIOR-RESULT')


class EventIssuer:
    """Non-authoritative fixture. Production event IDs must come from backend."""
    def __init__(self):self.issued=[];self.mode='ok'
    def issue_correlated_event(self, *, request_ref, scope, stage, effect,
                               attempt_id, reservation_ref, result_ref,
                               predecessor_result_ref):
        record=CorrelatedAttemptEvent('BACKEND-EVENT-'+str(len(self.issued)+1),request_ref,
            scope,stage,effect,attempt_id,reservation_ref,result_ref,
            predecessor_result_ref)
        self.issued.append(record)
        if self.mode=='foreign':return replace(record,request_ref='FOREIGN')
        if self.mode=='mutate_scope':
            object.__setattr__(scope,'tenant_ref','FOREIGN')
        return record


def test_correlated_event_issuer_owns_event_identity_and_wrong_issuer_fails_before_write():
    from grading.integration.attempt_history import CorrelatedHistoryRecorder
    issuer=EventIssuer();writer=Writer()
    adapter=CorrelatedHistoryRecorder(issuer=issuer,writer=writer,max_identifier_characters=64)
    evt=adapter.record_phase(request_ref='BACKEND-REQUEST',scope=scope_fixture(),
        stage=AttemptStage.PRE,effect=AttemptEffect.CONFIRMED)
    assert evt.receipt_ref=='RECEIPT' and len(writer.events)==1
    issuer.mode='foreign'
    with pytest.raises(AttemptHistoryDenied):
        adapter.record_phase(request_ref='BACKEND-REQUEST',scope=scope_fixture(),
            stage=AttemptStage.PRE,effect=AttemptEffect.CONFIRMED)
    assert len(writer.events)==1


def test_event_issuer_mutation_never_writes_a_foreign_scope():
    from grading.integration.attempt_history import CorrelatedHistoryRecorder
    issuer=EventIssuer();issuer.mode='mutate_scope';writer=Writer()
    gate=CorrelatedHistoryRecorder(issuer=issuer,writer=writer,max_identifier_characters=64)
    with pytest.raises(AttemptHistoryDenied):
        gate.record_phase(request_ref='BACKEND-REQUEST',scope=scope_fixture(),
            stage=AttemptStage.PRE,effect=AttemptEffect.CONFIRMED)
    assert writer.events==[]


class NewRunIssuer:
    def __init__(self, grant):
        self.grant=grant;self.calls=0;self.mode='ok'
    def identify_reservation_request(self, *, scope,family,runtime_id,runtime_version,
                                     implementation_ref,eligibility_policy_id,
                                     eligibility_policy_version):
        from grading.integration.attempt_authority import AttemptClaimRequest
        self.calls+=1
        record=AttemptClaimRequest(self.grant.new_request_ref,scope,family,
            runtime_id,runtime_version,implementation_ref,
            eligibility_policy_id,eligibility_policy_version,
            self.grant.predecessor_result_ref,self.grant.approval_ref)
        if self.mode=='foreign_prior':
            return replace(record,predecessor_result_ref='OTHER-PRIOR')
        if self.mode=='foreign_key':
            return replace(record,request_ref='FOREIGN')
        return record


def test_regrade_scope_gate_preserves_new_run_id_before_F25():
    from grading.integration.attempt_history import (
        establish_authorized_regrade_history, RegradeScopedAttemptClaimRequestIssuer,
    )
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    from grading.integration.evaluator_invocation import AttemptReservationRejected
    from tests.integration.test_attempt_authority import AtomicStore
    from tests.integration.test_evaluator_invocation import assembled_invoker
    source=RegradeSource(scope_fixture());events=Writer()
    grant=establish_authorized_regrade_history(source=source,
        prior_result_ref='PRIOR-RESULT',issuer=EventIssuer(),writer=events,
        max_identifier_characters=64)
    assert len(events.events)==1 and events.events[0].stage is AttemptStage.REGRADE
    assert events.events[0].predecessor_result_ref=='PRIOR-RESULT'
    issuer=NewRunIssuer(grant)
    guarded=RegradeScopedAttemptClaimRequestIssuer(grant=grant,issuer=issuer,max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker()
    bound=invoker._installation.handoff.prepare_choice_runtime(request=request)
    scope=bound.eligibility.scope
    approved=bound.approved_runtime
    policy=bound.eligibility.policy
    store=AtomicStore()
    gate=ClaimedAttemptAllocator(issuer=guarded,store=store,max_identifier_characters=64)
    kwargs=dict(scope=scope,family='CHOICE',runtime_id=approved.runtime_id,
        runtime_version=approved.runtime_version,
        implementation_ref=approved.implementation_ref,
        eligibility_policy_id=policy.policy_id,
        eligibility_policy_version=policy.policy_version)
    with pytest.raises(AttemptReservationRejected):
        gate.reserve_attempt(**kwargs)
    assert store.claims==0 and issuer.calls==0
    # A distinct owner-issued run with matching scope and request identity
    # is permitted structurally, without claiming academic/regrade approval.
    reservation=gate.reserve_attempt(**{**kwargs,'scope':grant.new_scope})
    assert reservation.request_ref==grant.new_request_ref
    assert reservation.predecessor_result_ref=='PRIOR-RESULT'
    assert reservation.regrade_approval_ref==grant.approval_ref
    assert store.claims==1


@pytest.mark.parametrize('mode',['foreign_prior','foreign_key'])
def test_regrade_issuer_cannot_relabel_prior_history(mode):
    from grading.integration.attempt_history import RegradeScopedAttemptClaimRequestIssuer
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    from grading.integration.evaluator_invocation import AttemptReservationRejected
    from tests.integration.test_attempt_authority import AtomicStore
    invoker,request,_,_=assembled_invoker()
    bound=invoker._installation.handoff.prepare_choice_runtime(request=request)
    scope=bound.eligibility.scope
    new=replace(scope,grading_run_id='NEW-RUN')
    grant=AuthorizedRegrade('APPROVAL','PRIOR-RESULT',scope,new,'NEW-REQUEST')
    source=NewRunIssuer(grant);source.mode=mode
    issuer=RegradeScopedAttemptClaimRequestIssuer(grant=grant,issuer=source,
                                        max_identifier_characters=64)
    store=AtomicStore()
    gate=ClaimedAttemptAllocator(issuer=issuer,store=store,max_identifier_characters=64)
    approved=bound.approved_runtime;policy=bound.eligibility.policy
    with pytest.raises(AttemptReservationRejected):
        gate.reserve_attempt(scope=new,family='CHOICE',runtime_id=approved.runtime_id,
            runtime_version=approved.runtime_version,
            implementation_ref=approved.implementation_ref,
            eligibility_policy_id=policy.policy_id,
            eligibility_policy_version=policy.policy_version)
    assert store.claims==0


@pytest.mark.parametrize('constructor', [
    lambda: AttemptHistoryCustody(writer=None,max_identifier_characters=0),
    lambda: AttemptHistoryCustody(writer=None,max_identifier_characters=16),
    lambda: CorrelatedHistoryRecorder(issuer=None,writer=None,max_identifier_characters=0),
    lambda: AuthorizedRegradeCustody(source=None,max_identifier_characters=0),
    lambda: RegradeScopedAttemptClaimRequestIssuer(grant=None,issuer=None,max_identifier_characters=0),
])
def test_new_history_installer_errors_do_not_retain_ambient_or_nested_context(constructor):
    try:
        raise RuntimeError('PRIVATE_AMBIENT_GRADING_AUTHORITY')
    except RuntimeError:
        with pytest.raises(ValueError) as failure:
            constructor()
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None


def test_installed_history_writers_and_regrade_issuer_cannot_be_retarged():
    writer=Writer()
    gate=AttemptHistoryCustody(writer=writer,max_identifier_characters=64)
    with pytest.raises(AttributeError):
        gate._append = Writer().append_attempt_event
    with pytest.raises(AttributeError):
        del gate._append
    recorder=CorrelatedHistoryRecorder(issuer=EventIssuer(),writer=writer,
                                      max_identifier_characters=64)
    with pytest.raises(AttributeError):
        recorder._issue = EventIssuer().issue_correlated_event
    with pytest.raises(AttributeError):
        del recorder._custody


def test_regrade_history_returns_detached_grant_when_writer_does_not_mutate_it():
    from grading.integration.attempt_history import establish_authorized_regrade_history
    source=RegradeSource(scope_fixture())
    original=source.resolve_authorized_regrade(prior_result_ref='PRIOR-RESULT')
    writer=Writer()
    class ConstantSource:
        def resolve_authorized_regrade(self, *, prior_result_ref): return original
    grant=establish_authorized_regrade_history(
        source=ConstantSource(),prior_result_ref='PRIOR-RESULT',
        issuer=EventIssuer(),writer=writer,max_identifier_characters=64)
    assert type(grant) is AuthorizedRegrade and grant == original and grant is not original
    assert grant.new_scope is not original.new_scope
    assert len(writer.events)==1 and writer.events[0].request_ref==grant.new_request_ref


def test_regrade_grant_corruption_plus_callback_exception_is_sanitized():
    from grading.integration.attempt_history import establish_authorized_regrade_history
    source=RegradeSource(scope_fixture())
    class CapturingSource:
        grant=None
        def resolve_authorized_regrade(self, *, prior_result_ref):
            self.grant=source.resolve_authorized_regrade(prior_result_ref=prior_result_ref)
            return self.grant
    authority=CapturingSource()
    class MutatingWriter(Writer):
        def append_attempt_event(self, *, event):
            object.__setattr__(authority.grant,'new_request_ref','FOREIGN-REQUEST')
            raise RuntimeError('PRIVATE_HISTORY_WRITE')
    try:
        raise RuntimeError('PRIVATE_AMBIENT')
    except RuntimeError:
        with pytest.raises(AttemptHistoryDenied) as caught:
            establish_authorized_regrade_history(
                source=authority,prior_result_ref='PRIOR-RESULT',
                issuer=EventIssuer(),writer=MutatingWriter(),max_identifier_characters=64)
    assert caught.value.__cause__ is None and caught.value.__context__ is None

# Independent attempt-history regression cases retained without weakening
# their original expectations. Fixture records are not a durable backend.
"""Independent source-level adversarial tests using real R5 modules and inherited Gradified fixtures.
Run from accepted-PB+R5 disposable checkout with PYTHONPATH=src:.
These assertions represent proposed contract expectations, not preapproved policy changes.
"""
import pytest
from grading.integration.attempt_history import (AttemptHistoryDenied, AttemptHistoryUnavailable,
    AttemptHistoryCustody,CorrelatedHistoryRecorder,CorrelatedAttemptEvent,
    AttemptStage,AttemptEffect)
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.evaluator_invocation import AttemptReservationRejected,AttemptReservationUnavailable
from tests.integration.test_attempt_history import scope_fixture, EventIssuer, Writer
from tests.integration.test_attempt_authority import AtomicStore, Issuer, setup

class DefiniteRefusal(AttemptHistoryDenied): pass

class ExplicitDenyWriter(Writer):
    def append_attempt_event(self, *, event):
        self.events.append(event)
        raise DefiniteRefusal('EXPLICIT_HISTORY_DENIAL')

def test_a_writer_explicit_integrity_refusal_is_not_uncertain():
    scope=scope_fixture()
    writer=ExplicitDenyWriter()
    port=AttemptHistoryCustody(writer=writer,max_identifier_characters=64)
    event=CorrelatedAttemptEvent('EV','REQ',scope,AttemptStage.PRE,AttemptEffect.CONFIRMED)
    with pytest.raises(AttemptHistoryDenied) as caught:
        port.record(event=event)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(writer.events)==1

class ExplicitDenyIssuer(EventIssuer):
    def issue_correlated_event(self, *, request_ref, scope, stage, effect, attempt_id, reservation_ref, result_ref, predecessor_result_ref):
        self.issued.append((request_ref, scope, stage))
        raise DefiniteRefusal('EXPLICIT_ISSUER_DENIAL')

def test_b_issuer_explicit_refusal_preserved_no_history_append():
    scope=scope_fixture()
    issuer=ExplicitDenyIssuer();writer=Writer()
    port=CorrelatedHistoryRecorder(issuer=issuer,writer=writer,max_identifier_characters=64)
    with pytest.raises(AttemptHistoryDenied) as caught:
        port.record_phase(request_ref='REQ',scope=scope,stage=AttemptStage.PRE,effect=AttemptEffect.CONFIRMED)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert not writer.events

class MutatingFailedRecovery(AtomicStore):
    def reconcile_reservation(self, *, request):
        self.reconciliations += 1
        object.__setattr__(request,'request_ref','FOREIGN')
        raise RuntimeError('PRIVATE_RECOVERY_FAILURE')

def test_c_f25_recovery_mutates_owned_request_then_raises_integrity_denied():
    store=MutatingFailedRecovery()
    invoker, request, store, issuer, adapter=setup(store=store)
    bound=invoker._installation.handoff.prepare_choice_runtime(request=request)
    scope=bound.eligibility.scope; runtime=bound.approved_runtime;policy=bound.eligibility.policy
    with pytest.raises(AttemptReservationRejected) as caught:
        adapter.reconcile_request(scope=scope,family='CHOICE',runtime_id=runtime.runtime_id,
            runtime_version=runtime.runtime_version,implementation_ref=runtime.implementation_ref,
            eligibility_policy_id=policy.policy_id,eligibility_policy_version=policy.policy_version)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert store.reconciliations==1


def test_d_complete_owned_call_explicit_pre_history_refusal_no_f25_or_evaluator():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy,AttemptLineageDenied,AttemptLineageUnavailable
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    regular, request, _, _=assembled_invoker()
    store=AtomicStore(); writer=ExplicitDenyWriter()
    owned=assemble_controlled_choice_root(
        handoff=regular._installation.handoff,request_issuer=Issuer(),f25_store=store,
        ledger=FixtureLedger(),transitions=FixtureTransitions(),transaction_store=Store(),
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=writer)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageDenied) as caught:
            owned.run_choice(request=request)
    assert store.claims==0 and calls=={'choice':0,'s2a':0}
    assert caught.value.__cause__ is None and caught.value.__context__ is None

class ForeignVerifyWriter(Writer):
    def append_attempt_event(self, *, event):
        self.events.append(event)
        from grading.integration.attempt_history import AttemptEventAcknowledgment, AttemptStage
        if event.stage is AttemptStage.VERIFY:
            return AttemptEventAcknowledgment(event.event_ref,'OTHER-REQUEST','RECEIPT')
        return AttemptEventAcknowledgment(event.event_ref,event.request_ref,'RECEIPT')

def test_e_full_owned_verify_foreign_receipt_is_definitive_integrity_denial():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy,AttemptLineageDenied
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    regular, request, _, _=assembled_invoker()
    store=AtomicStore(); writer=ForeignVerifyWriter(); tx=Store()
    owned=assemble_controlled_choice_root(
        handoff=regular._installation.handoff,request_issuer=Issuer(),f25_store=store,
        ledger=FixtureLedger(),transitions=FixtureTransitions(),transaction_store=tx,
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=writer)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageDenied) as caught:
            owned.run_choice(request=request)
    assert store.claims==1 and calls=={'choice':1,'s2a':1}
    assert not tx.effects and caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(writer.events)>=4

class RegradeExplicitRefusal:
    def __init__(self): self.calls=0
    def resolve_authorized_regrade(self, *, prior_result_ref):
        self.calls+=1
        raise DefiniteRefusal('NO_REGRADING_GRANT')

def test_f_explicit_regrade_refusal_remains_denial_not_retryable_outage():
    from grading.integration.attempt_history import AuthorizedRegradeCustody
    source=RegradeExplicitRefusal()
    custody=AuthorizedRegradeCustody(source=source,max_identifier_characters=64)
    with pytest.raises(AttemptHistoryDenied) as caught:
        custody.resolve(prior_result_ref='VALID-PRIOR-RESULT')
    assert source.calls==1 and caught.value.__cause__ is None and caught.value.__context__ is None


# Independent R8 rejection campaign: permanent regrade-to-attempt claim scope custody.
from dataclasses import replace
import pytest
from tests.integration.test_attempt_history import scope_fixture
from tests.integration.test_attempt_authority import AtomicStore
from grading.integration.attempt_history import AuthorizedRegrade, RegradeScopedAttemptClaimRequestIssuer
from grading.integration.attempt_authority import ClaimedAttemptAllocator, AttemptClaimRequest
from grading.integration.evaluator_invocation import AttemptReservationRejected


def test_regrade_issuer_mutation_must_not_result_in_f25_claim():
    old=scope_fixture()
    new=replace(old,grading_run_id='NEW-AUTH-RUN')
    grant=AuthorizedRegrade('GRANT','PREV',old,new,'REQ-NEW')
    class Issuer:
        def __init__(self): self.calls=0
        def identify_reservation_request(self, *, scope,family,runtime_id,runtime_version,
                                         implementation_ref,eligibility_policy_id,
                                         eligibility_policy_version):
            self.calls += 1
            # Cross-boundary data drift during a cooperative installed callback.
            object.__setattr__(scope,'tenant_ref','FOREIGN-TENANT')
            # Return *correct* data to try to conceal the mutation.
            return AttemptClaimRequest(grant.new_request_ref,grant.new_scope,family,runtime_id,
                runtime_version,implementation_ref,eligibility_policy_id,
                eligibility_policy_version,grant.predecessor_result_ref,grant.approval_ref)
    issuer=Issuer();store=AtomicStore()
    scoped=RegradeScopedAttemptClaimRequestIssuer(grant=grant,issuer=issuer,max_identifier_characters=64)
    allocator=ClaimedAttemptAllocator(issuer=scoped,store=store,max_identifier_characters=64)
    kwargs=dict(scope=new,family='CHOICE',runtime_id='RUNTIME',runtime_version='1',
        implementation_ref='IMPL',eligibility_policy_id='POLICY',eligibility_policy_version=1)
    with pytest.raises(AttemptReservationRejected):
        allocator.reserve_attempt(**kwargs)
    assert issuer.calls==1
    assert store.claims==0, f'FOREIGN SCOPE CALLBACK PRECEDED A REAL F25 CLAIM: {store.claims}'

@pytest.mark.parametrize('field',('tenant_ref','grading_run_id','question_id','submission_ref'))
@pytest.mark.parametrize('issuer_raises',(False, True))
def test_regrade_issuer_scope_continuity_on_callback_exception(field, issuer_raises):
    from grading.integration.evaluator_invocation import AttemptReservationUnavailable
    old=scope_fixture();new=replace(old,grading_run_id='NEW-AUTH-RUN')
    grant=AuthorizedRegrade('GRANT','PREV',old,new,'REQ-NEW')
    class Issuer:
        def identify_reservation_request(self, *, scope,family,runtime_id,runtime_version,
                                         implementation_ref,eligibility_policy_id,eligibility_policy_version):
            object.__setattr__(scope,field,'FOREIGN-IDENTITY')
            if issuer_raises:raise TimeoutError('PRIVATE_BACKEND_AFTER_SCOPE_MUTATION')
            return AttemptClaimRequest(grant.new_request_ref,grant.new_scope,family,runtime_id,
                runtime_version,implementation_ref,eligibility_policy_id,
                eligibility_policy_version,grant.predecessor_result_ref,grant.approval_ref)
    store=AtomicStore()
    scoped=RegradeScopedAttemptClaimRequestIssuer(grant=grant,issuer=Issuer(),max_identifier_characters=64)
    allocator=ClaimedAttemptAllocator(issuer=scoped,store=store,max_identifier_characters=64)
    kwargs=dict(scope=new,family='CHOICE',runtime_id='RUNTIME',runtime_version='1',
        implementation_ref='IMPL',eligibility_policy_id='POLICY',eligibility_policy_version=1)
    with pytest.raises(AttemptReservationRejected) as err:
        allocator.reserve_attempt(**kwargs)
    assert store.claims==0
    assert err.value.__context__ is None and err.value.__cause__ is None


# Independent R8 direct issuer privacy campaign.
from dataclasses import replace
import pytest
from tests.integration.test_attempt_history import scope_fixture
from grading.integration.attempt_history import (
    AuthorizedRegrade, RegradeScopedAttemptClaimRequestIssuer, AttemptHistoryUnavailable,
)

def test_direct_scoped_regrade_port_sanitizes_private_backend_exception():
    old=scope_fixture();new=replace(old,grading_run_id='NEW-RUN')
    grant=AuthorizedRegrade('APPROVAL','PRIOR',old,new,'NEW-REQ')
    class SecretBackend:
        def identify_reservation_request(self, *, scope,family,runtime_id,runtime_version,
                  implementation_ref,eligibility_policy_id,eligibility_policy_version):
            raise RuntimeError('PRIVATE_REGRADING_ISSUER_DETAILS')
    gate=RegradeScopedAttemptClaimRequestIssuer(grant=grant,issuer=SecretBackend(),max_identifier_characters=64)
    with pytest.raises(AttemptHistoryUnavailable) as caught:
        gate.identify_reservation_request(scope=new,family='CHOICE',runtime_id='R',runtime_version='1',
            implementation_ref='IMPL',eligibility_policy_id='POLICY',eligibility_policy_version=1)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
