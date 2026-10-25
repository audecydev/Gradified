"""physical attempt claim engine seam checks; mocked issuers and stores are NOT production authority."""
from dataclasses import replace
from threading import Lock, Thread
import pytest

from grading.integration.attempt_authority import (
    ClaimedAttemptAllocator, AttemptClaimRequest, AttemptClaim, AttemptClaimDisposition,
    AttemptClaimRecoveryFact, AttemptClaimRecoveryDisposition,
)
from grading.integration.evaluator_invocation import (
    AttemptReservation, InvocationDenied, InvocationUnavailable,
    AttemptReservationRejected, AttemptReservationUnavailable,
)
from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls


class Issuer:
    def __init__(self):
        self.calls = 0
        self.mode = 'valid'
    def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                     implementation_ref, eligibility_policy_id,
                                     eligibility_policy_version):
        self.calls += 1
        req = AttemptClaimRequest('BACKEND-STABLE-REQUEST-REF', scope, family,
                 runtime_id, runtime_version, implementation_ref, eligibility_policy_id,
                 eligibility_policy_version)
        if self.mode == 'wrong':
            return replace(req, runtime_id='FOREIGN-RUNTIME')
        if self.mode == 'bad':
            return replace(req, request_ref=True)
        return req


class AtomicStore:
    def __init__(self):
        self.claims = 0
        self.reconciliations = 0
        self.claimed = set()
        self.lock = Lock()
        self.mode = None
        self.last_reservation = None

    def claim_fresh_attempt(self, *, request):
        with self.lock:
            self.claims += 1
            if self.mode == 'raise_after_commit':
                self.claimed.add(request.request_ref)
                raise RuntimeError('SECRET_F25_LOST_RESPONSE')
            if self.mode == 'mutate_then_raise':
                object.__setattr__(request, 'request_ref', 'CHANGED')
                raise RuntimeError('SECRET_F25_FAILURE')
            if self.mode == 'unknown':
                return AttemptClaim(request, AttemptClaimDisposition.INDETERMINATE, None)
            if self.mode == 'replay_with_reservation':
                claimed = AttemptReservation(request.scope,'FORGED-ATT','FORGED-RES',
                    request.family,request.runtime_id,request.runtime_version,
                    request.implementation_ref,request.eligibility_policy_id,
                    request.eligibility_policy_version,request.request_ref,
                request.predecessor_result_ref,request.regrade_approval_ref)
                return AttemptClaim(request,AttemptClaimDisposition.REPLAY,claimed)
            if request.request_ref in self.claimed:
                return AttemptClaim(request, AttemptClaimDisposition.REPLAY, None)
            if self.mode in ('conflict', 'revoked', 'expired'):
                disposition = {'conflict': AttemptClaimDisposition.CONFLICT,
                               'revoked': AttemptClaimDisposition.REVOKED,
                               'expired': AttemptClaimDisposition.EXPIRED}[self.mode]
                return AttemptClaim(request, disposition, None)
            self.claimed.add(request.request_ref)
            self.last_reservation = AttemptReservation(request.scope, 'BACKEND-ATT-1',
                'BACKEND-RES-1', request.family, request.runtime_id,
                request.runtime_version, request.implementation_ref,
                request.eligibility_policy_id, request.eligibility_policy_version,
                request.request_ref,request.predecessor_result_ref,
                request.regrade_approval_ref)
            if self.mode == 'wrong_scope':
                return AttemptClaim(request, AttemptClaimDisposition.FRESH,
                                replace(self.last_reservation, runtime_id='FOREIGN'))
            if self.mode == 'wrong_request_ref':
                return AttemptClaim(request, AttemptClaimDisposition.FRESH,
                                replace(self.last_reservation,request_ref='FOREIGN-REQUEST'))
            if self.mode == 'missing_request_ref':
                return AttemptClaim(request, AttemptClaimDisposition.FRESH,
                                replace(self.last_reservation,request_ref=None))
            if self.mode == 'no_reservation':
                return AttemptClaim(request, AttemptClaimDisposition.FRESH, None)
            return AttemptClaim(request, AttemptClaimDisposition.FRESH, self.last_reservation)

    def reconcile_reservation(self, *, request):
        with self.lock:
            self.reconciliations += 1
            if request.request_ref in self.claimed:
                if self.last_reservation is None:
                    return AttemptClaimRecoveryFact(request, AttemptClaimRecoveryDisposition.INDETERMINATE, None)
                return AttemptClaimRecoveryFact(request, AttemptClaimRecoveryDisposition.RESERVED, self.last_reservation)
            return AttemptClaimRecoveryFact(request, AttemptClaimRecoveryDisposition.NOT_RESERVED, None)


def setup(*, store=None, issuer=None):
    store = AtomicStore() if store is None else store
    issuer = Issuer() if issuer is None else issuer
    adapter = ClaimedAttemptAllocator(issuer=issuer, store=store, max_identifier_characters=64)
    invoker, request, _, _ = assembled_invoker(adapter)
    return invoker, request, store, issuer, adapter


def test_fresh_backend_claim_is_consumed_inside_b56_no_duplicate_reservation():
    invoker, request, store, issuer, _ = setup()
    with _track_choice_and_s2a_calls() as calls:
        candidate = invoker.run_one_question(request=request)
    assert candidate.reservation.attempt_id == 'BACKEND-ATT-1'
    assert candidate.reservation.request_ref == 'BACKEND-STABLE-REQUEST-REF'
    assert calls == {'choice': 1, 's2a': 1}
    assert issuer.calls == 1 and store.claims == 1


def test_second_sequential_claim_for_same_issuer_request_does_not_execute_again():
    invoker, request, store, _, _ = setup()
    with _track_choice_and_s2a_calls() as calls:
        invoker.run_one_question(request=request)
        with pytest.raises(InvocationDenied):
            invoker.run_one_question(request=request)
    assert calls == {'choice': 1, 's2a': 1}
    assert store.claims == 2  # both contact backend; only one FRESH is issued


@pytest.mark.parametrize('mode,expected', [
    ('conflict', InvocationDenied), ('replay_with_reservation', InvocationDenied), ('revoked', InvocationDenied),
    ('expired', InvocationDenied), ('unknown', InvocationUnavailable),
    ('no_reservation', InvocationDenied),
    ('missing_request_ref', InvocationDenied),
    ('wrong_request_ref', InvocationDenied), ('wrong_scope', InvocationDenied),
    ('raise_after_commit', InvocationUnavailable),
    ('mutate_then_raise', InvocationDenied),
])
def test_nonfresh_unknown_mutated_claim_never_calls_choice(mode, expected):
    store = AtomicStore(); store.mode = mode
    invoker, request, _, _, _ = setup(store=store)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(expected) as caught:
            invoker.run_one_question(request=request)
    assert calls == {'choice': 0, 's2a': 0}
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'SECRET' not in str(caught.value)


@pytest.mark.parametrize('mode', ['wrong', 'bad'])
def test_foreign_issuer_result_never_reaches_claim_or_choice(mode):
    issuer=Issuer();issuer.mode=mode
    invoker,request,store,_,_=setup(issuer=issuer)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(InvocationDenied):
            invoker.run_one_question(request=request)
    assert store.claims==0 and calls=={'choice':0,'s2a':0}


def test_uncertain_claim_must_reconcile_without_a_second_claim_or_execution():
    store = AtomicStore(); store.mode='raise_after_commit'
    invoker, request, _, _, adapter=setup(store=store)
    with pytest.raises(InvocationUnavailable):
        invoker.run_one_question(request=request)
    assert store.claims==1
    # Fixture does not know reservation identity after a simulated lost response.
    scope = invoker._installation.handoff.prepare_choice_runtime(request=request).eligibility.scope
    # Scope alone is not enough to authorize a retry; the query remains read-only.
    runtime = invoker._installation.handoff.prepare_choice_runtime(request=request)
    approved=runtime.approved_runtime
    policy=runtime.eligibility.policy
    fact = adapter.reconcile_request(scope=scope, family='CHOICE',
        runtime_id=approved.runtime_id, runtime_version=approved.runtime_version,
        implementation_ref=approved.implementation_ref,
        eligibility_policy_id=policy.policy_id,
        eligibility_policy_version=policy.policy_version)
    assert fact.disposition is AttemptClaimRecoveryDisposition.INDETERMINATE
    assert store.claims==1 and store.reconciliations==1


def test_atomic_store_handles_two_parallel_claims_one_fresh_per_shared_identity():
    store = AtomicStore()
    inv1, req1, _, _, _ = setup(store=store)
    inv2, req2, _, _, _ = setup(store=store)
    out=[]
    def run(inv,req):
        try:
            inv.run_one_question(request=req)
            out.append('FRESH')
        except InvocationDenied:
            out.append('REPLAY')
    t1=Thread(target=run,args=(inv1,req1));t2=Thread(target=run,args=(inv2,req2))
    t1.start();t2.start();t1.join(5);t2.join(5)
    assert sorted(out)==['FRESH','REPLAY'] and store.claims==2


def test_single_installed_root_f25_before_actual_choice_then_versioned_cas():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger,FixtureTransitions,fixture_policy
    from grading.integration.attempt_lineage import AttemptLineageDenied
    from grading.integration.attempt_transaction import AtomicResultStateAudit
    from tests.integration.test_attempt_history import EventIssuer, Writer
    regular, request, _, _=assembled_invoker()
    store=AtomicStore();tx_store=Store();history_writer=Writer()
    owned=assemble_controlled_choice_root(
        handoff=regular._installation.handoff,
        request_issuer=Issuer(),f25_store=store,ledger=FixtureLedger(),
        transitions=FixtureTransitions(),transaction_store=tx_store,
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=history_writer)
    with _track_choice_and_s2a_calls() as calls:
        first=owned.run_choice(request=request)
        with pytest.raises(AttemptLineageDenied):
            owned.run_choice(request=request)
    assert calls=={'choice':1,'s2a':1}
    assert store.claims==2 and len(tx_store.effects)==1
    assert first.audit_receipt.approval_ref==tx_store.effects[0].f57_approval_ref
    assert first.audit_receipt.result_ref==tx_store.effects[0].result_ref
    assert [e.stage.value for e in history_writer.events[:4]]==[
        'PRE','ATTEMPT','EVALUATION','VERIFY']
    assert history_writer.events[2].effect.value=='DISPATCH_AUTHORIZED'
    assert history_writer.events[-1].stage.value=='FAILURE'
    assert len(tx_store.effects)==1


def test_full_composition_without_authoritative_installed_ports_fails_closed():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    normal, request, _, _=assembled_invoker()
    with pytest.raises(ValueError):
        assemble_controlled_choice_root(
            handoff=normal._installation.handoff,request_issuer=Issuer(),
            f25_store=AtomicStore(),ledger=None,transitions=None,
            transaction_store=None,approved_f57_policy=None,
            max_identifier_characters=64)



def test_history_PRE_failure_blocks_F25_and_evaluator_before_claim():
    from grading.integration.attempt_history import CorrelatedHistoryRecorder
    from tests.integration.test_attempt_history import EventIssuer, Writer
    writer=Writer();writer.mode='timeout';store=AtomicStore()
    hist=CorrelatedHistoryRecorder(issuer=EventIssuer(),writer=writer,max_identifier_characters=64)
    adapter=ClaimedAttemptAllocator(issuer=Issuer(),store=store,
                                    max_identifier_characters=64,history=hist)
    invoker,request,_,_=assembled_invoker(adapter)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(InvocationUnavailable):invoker.run_one_question(request=request)
    assert store.claims==0 and calls=={'choice':0,'s2a':0}


def test_history_ATTEMPT_failure_after_f25_claim_never_calls_evaluator():
    from grading.integration.attempt_history import CorrelatedHistoryRecorder
    from tests.integration.test_attempt_history import EventIssuer, Writer
    class FailAfterPre(Writer):
        def append_attempt_event(self, *, event):
            self.events.append(event)
            if event.stage.value=='ATTEMPT':raise RuntimeError('PRIVATE_WRITE_TIMEOUT')
            from grading.integration.attempt_history import AttemptEventAcknowledgment
            return AttemptEventAcknowledgment(event.event_ref,event.request_ref,'TEST-RECEIPT')
    store=AtomicStore();writer=FailAfterPre()
    hist=CorrelatedHistoryRecorder(issuer=EventIssuer(),writer=writer,max_identifier_characters=64)
    adapter=ClaimedAttemptAllocator(issuer=Issuer(),store=store,
                                    max_identifier_characters=64,history=hist)
    invoker,request,_,_=assembled_invoker(adapter)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(InvocationUnavailable) as err:
            invoker.run_one_question(request=request)
    assert store.claims==1 and len(store.claimed)==1
    assert calls=={'choice':0,'s2a':0}
    assert err.value.__cause__ is None and err.value.__context__ is None


def test_owned_transaction_reconciliation_after_commit_timeout_never_reexecutes():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from grading.integration.attempt_transaction import TransactionReconciliation
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger,FixtureTransitions,fixture_policy
    from tests.integration.test_attempt_history import EventIssuer,Writer
    from grading.integration.attempt_lineage import AttemptLineageUnavailable
    normal,request,_,_=assembled_invoker()
    claims=AtomicStore();store=Store();store.mode='timeout_after_commit'
    owned=assemble_controlled_choice_root(handoff=normal._installation.handoff,
        request_issuer=Issuer(),f25_store=claims,ledger=FixtureLedger(),
        transitions=FixtureTransitions(),transaction_store=store,
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=Writer())
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageUnavailable):
            owned.run_choice(request=request)
        fact=owned.reconcile_owned_transaction(request=request)
        reserved=owned.reconcile_owned_attempt(request=request)
    assert calls=={'choice':1,'s2a':1}
    assert fact.disposition is TransactionReconciliation.COMMITTED
    assert reserved.disposition is AttemptClaimRecoveryDisposition.RESERVED
    assert claims.claims==1 and len(store.effects)==1


def test_unacknowledged_backend_attempt_can_be_read_without_new_claim():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger,FixtureTransitions,fixture_policy
    from tests.integration.test_attempt_history import EventIssuer,Writer
    from grading.integration.attempt_lineage import AttemptLineageUnavailable
    normal,request,_,_=assembled_invoker()
    claims=AtomicStore();claims.mode='raise_after_commit';store=Store()
    owned=assemble_controlled_choice_root(handoff=normal._installation.handoff,
        request_issuer=Issuer(),f25_store=claims,ledger=FixtureLedger(),
        transitions=FixtureTransitions(),transaction_store=store,
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=Writer())
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageUnavailable):
            owned.run_choice(request=request)
        recovery=owned.reconcile_owned_attempt(request=request)
    assert calls=={'choice':0,'s2a':0}
    assert recovery.disposition is AttemptClaimRecoveryDisposition.INDETERMINATE
    assert claims.claims==1 and len(store.effects)==0


def test_history_dispatch_authorization_write_failure_prevents_choice_side_effect():
    from grading.integration.attempt_history import CorrelatedHistoryRecorder, AttemptEventAcknowledgment
    from tests.integration.test_attempt_history import EventIssuer, Writer
    class FailDispatch(Writer):
        def append_attempt_event(self, *, event):
            self.events.append(event)
            if event.stage.value=='EVALUATION':
                raise RuntimeError('PRIVATE_DISPATCH_HISTORY_TIMEOUT')
            return AttemptEventAcknowledgment(event.event_ref,event.request_ref,'BACKEND-RECEIPT')
    store=AtomicStore();writer=FailDispatch()
    history=CorrelatedHistoryRecorder(issuer=EventIssuer(),writer=writer,
                                     max_identifier_characters=64)
    claims=ClaimedAttemptAllocator(issuer=Issuer(),store=store,
                                  max_identifier_characters=64,history=history)
    invoker,request,_,_=assembled_invoker(claims)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(InvocationUnavailable) as raised:
            invoker.run_one_question(request=request)
    assert store.claims==1 and calls=={'choice':0,'s2a':0}
    assert [e.stage.value for e in writer.events[:3]]==['PRE','ATTEMPT','EVALUATION']
    assert raised.value.__context__ is None and raised.value.__cause__ is None


# Callbacks are not allowed to cause a second physical attempt claim or a write during read-only recovery.
class ReenteringStore:
    def __init__(self):
        self.adapter = None
        self.calls = 0
        self.nested_error = None
    def claim_fresh_attempt(self, *, request):
        self.calls += 1
        if self.calls == 1:
            try:
                raise RuntimeError('PRIVATE_F25_AMBIENT')
            except RuntimeError:
                try:
                    self.adapter.reserve_attempt(scope=request.scope, family=request.family,
                        runtime_id=request.runtime_id, runtime_version=request.runtime_version,
                        implementation_ref=request.implementation_ref,
                        eligibility_policy_id=request.eligibility_policy_id,
                        eligibility_policy_version=request.eligibility_policy_version)
                except AttemptReservationRejected as exc:
                    self.nested_error = exc
        res = AttemptReservation(request.scope,'BACKEND-ATT-1','BACKEND-RES-1',
            request.family,request.runtime_id,request.runtime_version,request.implementation_ref,
            request.eligibility_policy_id,request.eligibility_policy_version,
            request_ref=request.request_ref)
        return AttemptClaim(request,AttemptClaimDisposition.FRESH,res)
    def reconcile_reservation(self, *, request):
        raise AssertionError('no read needed')

def test_f25_claim_port_blocks_self_reentry_before_duplicate_backend_claim():
    store = ReenteringStore()
    adapter = ClaimedAttemptAllocator(issuer=Issuer(),store=store,max_identifier_characters=64)
    store.adapter=adapter
    invoker, request, _, _ = assembled_invoker(adapter)
    with _track_choice_and_s2a_calls() as calls:
        result=invoker.run_one_question(request=request)
    assert result.reservation.attempt_id=='BACKEND-ATT-1'
    assert store.calls == 1, 'One invocation may not cause a nested attempt reservation'
    assert isinstance(store.nested_error, AttemptReservationRejected)
    assert store.nested_error.__cause__ is None and store.nested_error.__context__ is None
    assert calls == {'choice':1,'s2a':1}

class ReenterDuringRecovery(Issuer):
    def __init__(self):
        super().__init__()
        self.owner = None
        self.request = None
        self.active = False
        self.inner = None
    def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                     implementation_ref, eligibility_policy_id,
                                     eligibility_policy_version):
        if self.active and self.inner is None:
            # An existing private exception must not escape in the nested
            # denial's implicit exception context.
            try:
                raise RuntimeError('PRIVATE_RECOVERY_AMBIENT')
            except RuntimeError:
                try:
                    self.owner.run_choice(request=self.request)
                except Exception as exc:
                    self.inner=exc
                else:
                    self.inner='EXECUTED'
        return super().identify_reservation_request(
            scope=scope,family=family,runtime_id=runtime_id,
            runtime_version=runtime_version,implementation_ref=implementation_ref,
            eligibility_policy_id=eligibility_policy_id,
            eligibility_policy_version=eligibility_policy_version)

def test_readonly_owned_f25_reconciliation_blocks_callback_reentrant_execution():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
    from tests.integration.test_attempt_history import EventIssuer, Writer
    standard, request, _, _ = assembled_invoker()
    issuer=ReenterDuringRecovery()
    claim=AtomicStore()
    audit=Store()
    root=assemble_controlled_choice_root(handoff=standard._installation.handoff,
        request_issuer=issuer, f25_store=claim, ledger=FixtureLedger(),
        transitions=FixtureTransitions(),transaction_store=audit,
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=Writer())
    issuer.owner=root; issuer.request=request; issuer.active=True
    with _track_choice_and_s2a_calls() as calls:
        fact=root.reconcile_owned_attempt(request=request)
    assert isinstance(issuer.inner, AttemptReservationRejected)
    assert issuer.inner.__cause__ is None and issuer.inner.__context__ is None
    assert calls == {'choice':0,'s2a':0}, 'Read-only recovery must not permit nested evaluation'
    assert claim.claims==0 and len(audit.effects)==0
    # The guard is released when recovery finishes: the read-only path still works.
    issuer.active=False
    recovery=root.reconcile_owned_attempt(request=request)
    assert recovery.disposition is AttemptClaimRecoveryDisposition.NOT_RESERVED
    assert claim.claims==0

# Independent P-C R2 review regressions: original operation custody and
# successful request A followed by rejected request B on the same owner/thread.
@pytest.mark.parametrize('changed', [
    {'question_id':'OTHER-QUESTION'}, {'tenant_ref':'OTHER-TENANT'},
    {'grading_run_id':'OTHER-RUN'}, {'submission_ref':'OTHER-SUBMISSION'},
])
def test_request_failure_never_reuses_earlier_attempt_history(changed):
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from grading.integration.attempt_lineage import AttemptLineageDenied
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
    from tests.integration.test_attempt_history import EventIssuer, Writer
    regular, request, _, _ = assembled_invoker()
    history, store, transaction = Writer(), AtomicStore(), Store()
    root = assemble_controlled_choice_root(
        handoff=regular._installation.handoff, request_issuer=Issuer(), f25_store=store,
        ledger=FixtureLedger(), transitions=FixtureTransitions(), transaction_store=transaction,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
        history_issuer=EventIssuer(), history_writer=history)
    with _track_choice_and_s2a_calls() as effects:
        success = root.run_choice(request=request)
        original = list(history.events)
        with pytest.raises(AttemptLineageDenied):
            root.run_choice(request=replace(request, **changed))
    assert success.execution.reservation.attempt_id == 'BACKEND-ATT-1'
    assert history.events == original
    assert effects == {'choice':1,'s2a':1}
    assert store.claims == 1 and len(transaction.effects) == 1


def test_issuer_cannot_replace_installed_f25_operation_during_identification():
    original, foreign = AtomicStore(), AtomicStore()
    class RetargetIssuer(Issuer):
        adapter = None
        def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                         implementation_ref, eligibility_policy_id,
                                         eligibility_policy_version):
            try:
                self.adapter._claim = foreign.claim_fresh_attempt
            except AttributeError:
                pass
            return super().identify_reservation_request(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version, implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version)
    issuer=RetargetIssuer()
    invoker, request, _, _, adapter=setup(store=original,issuer=issuer)
    issuer.adapter=adapter
    with _track_choice_and_s2a_calls() as effects:
        invoker.run_one_question(request=request)
    assert original.claims == 1 and foreign.claims == 0
    assert effects == {'choice':1,'s2a':1}
    with pytest.raises(AttributeError):
        del adapter._claim


def test_controlled_root_does_not_allow_delete_and_rebind_of_dispatch_or_handoff():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger,FixtureTransitions,fixture_policy
    from tests.integration.test_attempt_history import EventIssuer,Writer
    regular, request, _, _=assembled_invoker()
    root=assemble_controlled_choice_root(
        handoff=regular._installation.handoff,request_issuer=Issuer(),f25_store=AtomicStore(),
        ledger=FixtureLedger(),transitions=FixtureTransitions(),transaction_store=Store(),
        approved_f57_policy=fixture_policy(),max_identifier_characters=64,
        history_issuer=EventIssuer(),history_writer=Writer())
    original=root._managed
    for field in ('_managed','_handoff','_claim','_audit'):
        with pytest.raises(AttributeError):
            delattr(root,field)
        assert getattr(root,field) is not None
    assert root._managed is original
    with _track_choice_and_s2a_calls() as effects:
        root.run_choice(request=request)
    assert effects=={'choice':1,'s2a':1}


def test_explicit_issuer_denial_subclass_preserves_definitive_denial():
    from grading.integration.attempt_history import AttemptHistoryDenied
    class DerivedDenial(AttemptHistoryDenied):
        pass
    class DenyingIssuer(Issuer):
        def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                         implementation_ref, eligibility_policy_id,
                                         eligibility_policy_version):
            raise DerivedDenial('PRIVATE_BACKEND_DENIAL')
    invoker,request,store,_,_=setup(issuer=DenyingIssuer())
    with _track_choice_and_s2a_calls() as effects:
        with pytest.raises(InvocationDenied) as caught:
            invoker.run_one_question(request=request)
    assert store.claims==0 and effects=={'choice':0,'s2a':0}
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)


# Independent R3 history-to-effect hostile regressions (preserved attack intent).
"""Independent R3 attack: attempt cross-boundary effect checks with real inherited setup."""
from dataclasses import replace
import pytest
from grading.integration.attempt_authority import ClaimedAttemptAllocator, AttemptClaimRequest, AttemptClaim, AttemptClaimDisposition
from grading.integration.evaluator_invocation import AttemptReservation, InvocationDenied
from grading.integration.attempt_history import AttemptStage, AttemptEffect
from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls

class RetainingIssuer:
    def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                     implementation_ref, eligibility_policy_id, eligibility_policy_version):
        self.issued=AttemptClaimRequest('VALID-ORIGINAL-REF',scope,family,runtime_id,runtime_version,
                                         implementation_ref,eligibility_policy_id,eligibility_policy_version)
        return self.issued

class PREMutatingHistory:
    def __init__(self, issuer):self.issuer=issuer;self.events=[]
    def emit_phase(self, *, request_ref, scope, stage, effect, attempt_id, reservation_ref,
                   result_ref, predecessor_result_ref):
        self.events.append((stage,request_ref))
        if stage is AttemptStage.PRE:
            # This is a callback with access to a previously returned backend object.
            object.__setattr__(self.issuer.issued,'request_ref','FOREIGN-CLAIM-REF')
        return object()

class RecordingClaimStore:
    def __init__(self):self.claimed=[]
    def claim_fresh_attempt(self, *, request):
        self.claimed.append(request.request_ref)
        return AttemptClaim(request, AttemptClaimDisposition.FRESH,
                        AttemptReservation(request.scope,'A','R',request.family,request.runtime_id,
                        request.runtime_version,request.implementation_ref,
                        request.eligibility_policy_id,request.eligibility_policy_version,
                        request.request_ref,request.predecessor_result_ref,request.regrade_approval_ref))
    def reconcile_reservation(self, *, request):return None

def test_pre_history_mutation_does_not_contact_foreign_claim_request():
    issuer=RetainingIssuer(); store=RecordingClaimStore(); hist=PREMutatingHistory(issuer)
    adapter=ClaimedAttemptAllocator(issuer=issuer,store=store,history=hist,max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(adapter)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(InvocationDenied): invoker.run_one_question(request=request)
    assert store.claimed==[],f'FOREIGN F25 CLAIM CALLED: {store.claimed}'
    assert calls=={'choice':0,'s2a':0}

@pytest.mark.parametrize('field,newvalue',[('request_ref','FOREIGN-REF'),('runtime_id','FOREIGN-RUNTIME'),('eligibility_policy_version',999)])
def test_pre_callback_must_revalidate_f25_request_before_claim(field,newvalue):
    issuer=RetainingIssuer();store=RecordingClaimStore()
    class Hist(PREMutatingHistory):
        def emit_phase(self, *, request_ref, scope, stage, effect, attempt_id, reservation_ref,
                       result_ref, predecessor_result_ref):
            if stage is AttemptStage.PRE:
                object.__setattr__(issuer.issued,field,newvalue)
            return object()
    adapter=ClaimedAttemptAllocator(issuer=issuer,store=store,history=Hist(issuer),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(adapter)
    with pytest.raises(InvocationDenied):invoker.run_one_question(request=request)
    assert store.claimed==[], 'Attempt reservation backend contacted with altered '+field


def test_pre_history_mutation_then_exception_takes_integrity_precedence():
    issuer=RetainingIssuer();store=RecordingClaimStore()
    class Hist(PREMutatingHistory):
        def emit_phase(self, *, request_ref, scope, stage, effect, attempt_id, reservation_ref,
                       result_ref, predecessor_result_ref):
            if stage is AttemptStage.PRE:
                object.__setattr__(issuer.issued,'request_ref','FOREIGN-REF')
                raise RuntimeError('PRIVATE_HISTORY_BACKEND_EXCEPTION')
    adapter=ClaimedAttemptAllocator(issuer=issuer,store=store,history=Hist(issuer),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(adapter)
    with pytest.raises(InvocationDenied) as info:invoker.run_one_question(request=request)
    assert info.value.__context__ is None and info.value.__cause__ is None
    assert store.claimed==[]


def test_pre_callback_cannot_erase_current_request_before_claim():
    issuer=RetainingIssuer();store=RecordingClaimStore()
    class Hist(PREMutatingHistory):
        def emit_phase(self, *, request_ref, scope, stage, effect, attempt_id, reservation_ref,
                       result_ref, predecessor_result_ref):
            if stage is AttemptStage.PRE:
                adapter.begin_operation() # accessible mutation of operation correlation during callback
            return object()
    adapter=ClaimedAttemptAllocator(issuer=issuer,store=store,history=Hist(issuer),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(adapter)
    with pytest.raises(InvocationDenied): invoker.run_one_question(request=request)
    assert store.claimed==[], 'Without current correlation, attempt reservation must not run'

@pytest.mark.parametrize('stage',[AttemptStage.ATTEMPT,AttemptStage.EVALUATION])
def test_history_callback_after_claim_cannot_corrupt_returned_request(stage):
    issuer=RetainingIssuer();store=RecordingClaimStore()
    class Hist(PREMutatingHistory):
        def emit_phase(self, *, request_ref, scope, stage, effect, attempt_id, reservation_ref,
                       result_ref, predecessor_result_ref):
            if stage is target_stage:
                object.__setattr__(issuer.issued,'request_ref','INVALID-POST-CLAIM-REF')
            return object()
    target_stage=stage
    adapter=ClaimedAttemptAllocator(issuer=issuer,store=store,history=Hist(issuer),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(adapter)
    with pytest.raises(InvocationDenied): invoker.run_one_question(request=request)
    assert store.claimed==['VALID-ORIGINAL-REF']

def test_regrade_history_append_cannot_change_returned_grant_after_event_binding():
    from grading.integration.attempt_history import (AuthorizedRegrade,AttemptStage,AttemptEffect,
        CorrelatedAttemptEvent,AttemptEventAcknowledgment,establish_authorized_regrade_history,AttemptHistoryDenied)
    from tests.integration.test_attempt_history import scope_fixture
    from dataclasses import replace
    original_scope=scope_fixture()
    class GrantSource:
        def resolve_authorized_regrade(self, *, prior_result_ref):
            self.grant=AuthorizedRegrade('APPROVAL-A',prior_result_ref,original_scope,
                        replace(original_scope,grading_run_id='AUTHORIZED-NEW-RUN'),'ORIGINAL-REQUEST')
            return self.grant
    source=GrantSource()
    class Emitter:
        def issue_correlated_event(self, *, request_ref,scope,stage,effect,attempt_id,reservation_ref,result_ref,predecessor_result_ref):
            return CorrelatedAttemptEvent('GRANT-EVENT',request_ref,scope,stage,effect,attempt_id,reservation_ref,result_ref,predecessor_result_ref)
    class Writer:
        def append_attempt_event(self, *, event):
            self.recorded=event.request_ref
            object.__setattr__(source.grant,'new_request_ref','FOREIGN-REQUEST')
            return AttemptEventAcknowledgment(event.event_ref,event.request_ref,'ACK')
    writer=Writer()
    with pytest.raises(AttemptHistoryDenied):
        grant=establish_authorized_regrade_history(source=source,prior_result_ref='PRIOR',issuer=Emitter(),writer=writer,max_identifier_characters=64)
    assert writer.recorded=='ORIGINAL-REQUEST'


def test_definitive_f25_refusal_and_lifecycle_failure_have_distinct_stage_meanings():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from grading.integration.attempt_history import AttemptStage, AttemptEffect
    from grading.integration.attempt_lineage import AttemptLineageDenied
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
    from tests.integration.test_attempt_history import EventIssuer, Writer
    standard, request, _, _ = assembled_invoker()
    physical = AtomicStore(); physical.mode = 'conflict'
    history = Writer(); transaction = Store()
    root = assemble_controlled_choice_root(
        handoff=standard._installation.handoff, request_issuer=Issuer(), f25_store=physical,
        ledger=FixtureLedger(), transitions=FixtureTransitions(), transaction_store=transaction,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
        history_issuer=EventIssuer(), history_writer=history)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageDenied): root.run_choice(request=request)
    assert physical.claims == 1 and calls == {'choice': 0, 's2a': 0}
    assert not transaction.effects
    assert [(e.stage,e.effect) for e in history.events] == [
        (AttemptStage.PRE, AttemptEffect.CONFIRMED),
        (AttemptStage.ATTEMPT, AttemptEffect.DENIED),
        (AttemptStage.FAILURE, AttemptEffect.UNKNOWN)]
    assert all(e.attempt_id is None and e.reservation_ref is None for e in history.events)
    assert len({e.request_ref for e in history.events}) == 1


def test_correlation_cleanup_requires_active_lifecycle_token():
    issuer=Issuer(); store=AtomicStore()
    adapter=ClaimedAttemptAllocator(issuer=issuer,store=store,max_identifier_characters=64)
    token=adapter.begin_operation()
    with pytest.raises(AttemptReservationRejected): adapter.begin_operation()
    with pytest.raises(AttemptReservationRejected): adapter.finish_operation(token=object())
    with pytest.raises(TypeError): adapter.finish_operation()
    assert adapter.current_request_context() is None
    adapter.finish_operation(token=token)
    renewed=adapter.begin_operation()
    adapter.finish_operation(token=renewed)

# Independent attempt-authority failure cases retained as permanent regressions.
from grading.integration.attempt_authority import assemble_controlled_choice_root
from grading.integration.attempt_lineage import AttemptLineageDenied, AttemptLineageUnavailable
from grading.integration.evaluator_invocation import InvocationDenied
from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
from tests.integration.test_attempt_history import EventIssuer, Writer
from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls

def _r5_make_root(*, ledger=None, transitions=None, store=None, writer=None):
    from tests.integration.test_attempt_transaction import Store
    baseline, request, _, _ = assembled_invoker()
    f25, tx = AtomicStore(), Store()
    root = assemble_controlled_choice_root(
        handoff=baseline._installation.handoff,
        request_issuer=Issuer(), f25_store=f25,
        ledger=ledger or FixtureLedger(), transitions=transitions or FixtureTransitions(),
        transaction_store=store or tx, approved_f57_policy=fixture_policy(),
        max_identifier_characters=64, history_issuer=EventIssuer(),
        history_writer=writer or Writer(),
    )
    return root, request, f25, tx


def _r5_reenter(root, reservation, outcomes):
    try:
        root._claim.reserve_attempt(
            scope=reservation.scope, family=reservation.family,
            runtime_id=reservation.runtime_id, runtime_version=reservation.runtime_version,
            implementation_ref=reservation.implementation_ref,
            eligibility_policy_id=reservation.eligibility_policy_id,
            eligibility_policy_version=reservation.eligibility_policy_version,
        )
        outcomes.append('UNEXPECTED_SECOND_PERMIT')
    except AttemptReservationRejected as e:
        outcomes.append(('REJECTED', e.__context__ is None, e.__cause__ is None))


@pytest.mark.parametrize('phase', ('ledger', 'f57', 'cas'))
def test_one_owned_lifecycle_must_not_issue_second_backend_claim(phase):
    from tests.integration.test_attempt_transaction import Store
    refs, attempts = {}, []
    class ReentryLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            if phase == 'ledger': _r5_reenter(refs['root'], reservation, attempts)
            return super().classify_owned_result(reservation=reservation, candidate=candidate)
    class ReentryF57(FixtureTransitions):
        def authorize_result_transition(self, *, observation, candidate):
            if phase == 'f57': _r5_reenter(refs['root'], candidate.reservation, attempts)
            return super().authorize_result_transition(observation=observation, candidate=candidate)
    class ReentryStore(Store):
        def commit_result_state_audit(self, *, transaction, candidate):
            if phase == 'cas': _r5_reenter(refs['root'], candidate.reservation, attempts)
            return super().commit_result_state_audit(transaction=transaction, candidate=candidate)
    root, request, f25, ignored = _r5_make_root(ledger=ReentryLedger(), transitions=ReentryF57(), store=ReentryStore())
    refs['root'] = root
    with _track_choice_and_s2a_calls() as calls:
        result = root.run_choice(request=request)
    assert attempts and attempts[0] == ('REJECTED', True, True), attempts
    assert calls == {'choice':1, 's2a':1}, calls
    assert f25.claims == 1, f'forbidden extra F25 claim at {phase}: {f25.claims}'
    assert result.audit_receipt is not None


@pytest.mark.parametrize("stage", ("ATTEMPT", "EVALUATION"))
@pytest.mark.parametrize("writer_raises", (False, True))
def test_corrupt_post_claim_correlation_must_never_be_emitted_as_history(stage, writer_raises):
    refs = {}
    class CorruptAttemptWriter(Writer):
        def append_attempt_event(self, *, event):
            if event.stage.value == stage and (event.effect.value == 'CONFIRMED' or event.effect.value == 'DISPATCH_AUTHORIZED'):
                allocator = refs['root']._claim
                record = allocator._current.record
                allocator._current.record = (record[0], 'FOREIGN-CORRELATION', record[2], record[3])
                if writer_raises:
                    self.events.append(event)
                    raise RuntimeError('PRIVATE_AFTER_EVENT_WRITE')
            return super().append_attempt_event(event=event)
    writer = CorruptAttemptWriter()
    root, request, f25, tx = _r5_make_root(writer=writer)
    refs['root'] = root
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises((AttemptLineageDenied, AttemptLineageUnavailable)):
            root.run_choice(request=request)
    assert f25.claims == 1
    assert calls == {'choice':0, 's2a':0}
    assert len(tx.effects) == 0
    assert all(e.request_ref == 'BACKEND-STABLE-REQUEST-REF' for e in writer.events), [
        (e.stage.value, e.effect.value, e.request_ref) for e in writer.events]

def test_invalid_pre_history_ack_is_denied_not_retryable_outage():
    from grading.integration.attempt_authority import ClaimedAttemptAllocator
    from grading.integration.attempt_history import CorrelatedHistoryRecorder
    from grading.integration.attempt_history import AttemptEventAcknowledgment
    class FalseAcknowledgingWriter(Writer):
        def append_attempt_event(self, *, event):
            self.events.append(event)
            return AttemptEventAcknowledgment(event.event_ref, 'FOREIGN-REQUEST', 'ACK')
    writer = FalseAcknowledgingWriter()
    history = CorrelatedHistoryRecorder(issuer=EventIssuer(), writer=writer, max_identifier_characters=64)
    store = AtomicStore()
    allocator = ClaimedAttemptAllocator(issuer=Issuer(), store=store,
                                        max_identifier_characters=64, history=history)
    invoker, request, _, _ = assembled_invoker(allocator)
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(InvocationDenied):
            invoker.run_one_question(request=request)
    assert store.claims == 0
    assert calls == {'choice':0,'s2a':0}

# R6: hostile callbacks may read ordinary diagnostic records but are not
# granted the owner's active lifecycle capability. Full-interpreter privileged
# introspection is not an isolation guarantee; the real physical attempt claim store still owns
# distributed idempotency.

def test_r6_callback_cannot_release_or_repeat_owned_f25_claim():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_history import EventIssuer, Writer
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
    from tests.integration.test_attempt_transaction import Store

    class PrematureReleaseLedger(FixtureLedger):
        claim = None
        observed = None
        def classify_owned_result(self, *, reservation, candidate):
            with pytest.raises(AttributeError):
                # This field was exposed in R5 and made premature release possible.
                self.claim._current.active_token
            with pytest.raises(AttemptReservationRejected):
                self.claim.finish_operation(token=object())
            with pytest.raises(AttemptReservationRejected) as denial:
                self.claim.reserve_attempt(
                    scope=reservation.scope, family=reservation.family,
                    runtime_id=reservation.runtime_id,
                    runtime_version=reservation.runtime_version,
                    implementation_ref=reservation.implementation_ref,
                    eligibility_policy_id=reservation.eligibility_policy_id,
                    eligibility_policy_version=reservation.eligibility_policy_version)
            self.observed = denial.value
            return super().classify_owned_result(reservation=reservation,candidate=candidate)

    invoker, request, _, _=assembled_invoker()
    store=AtomicStore(); ledger=PrematureReleaseLedger();tx=Store()
    root=assemble_controlled_choice_root(
        handoff=invoker._installation.handoff, request_issuer=Issuer(),
        f25_store=store, ledger=ledger, transitions=FixtureTransitions(),
        transaction_store=tx,approved_f57_policy=fixture_policy(),
        max_identifier_characters=64,history_issuer=EventIssuer(),history_writer=Writer())
    ledger.claim=root._claim
    with _track_choice_and_s2a_calls() as calls:
        outcome=root.run_choice(request=request)
    assert outcome.audit_receipt is not None
    assert store.claims==1 and len(tx.effects)==1 and calls=={'choice':1,'s2a':1}
    assert ledger.observed.__cause__ is None and ledger.observed.__context__ is None


def test_r6_diagnostic_copies_cannot_rewrite_original_history_after_denial():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_history import AttemptStage, AttemptEffect,EventIssuer,Writer
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
    from tests.integration.test_attempt_transaction import Store

    class MutatingWriter(Writer):
        claim=None
        def append_attempt_event(self, *, event):
            receipt=super().append_attempt_event(event=event)
            if event.stage is AttemptStage.ATTEMPT and event.effect is AttemptEffect.DENIED:
                old=self.claim._current.record
                wrong=(old[0],'FOREIGN-REQUEST',old[2],old[3])
                self.claim._current.record=wrong
                self.claim._current.original_record=wrong
            return receipt
    invoker,request,_,_=assembled_invoker()
    store=AtomicStore();store.mode='conflict';writer=MutatingWriter();tx=Store()
    root=assemble_controlled_choice_root(
        handoff=invoker._installation.handoff,request_issuer=Issuer(),
        f25_store=store,ledger=FixtureLedger(),transitions=FixtureTransitions(),
        transaction_store=tx,approved_f57_policy=fixture_policy(),
        max_identifier_characters=64,history_issuer=EventIssuer(),history_writer=writer)
    writer.claim=root._claim
    from grading.integration.attempt_lineage import AttemptLineageDenied
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises((AttemptReservationRejected,InvocationDenied,AttemptLineageDenied)):
            root.run_choice(request=request)
    assert store.claims==1 and calls=={'choice':0,'s2a':0} and not tx.effects
    assert all(evt.request_ref != 'FOREIGN-REQUEST' for evt in writer.events)

# The original R5 review's public-begin, stale-history and recovery control
# cases are retained unaltered; only the callback-private-owner test above
# adjusts its expectation to allow safe denial BEFORE further physical attempt effects.

# Original independent R5 high-value tests (except the callback-private-owner
# case which assumes a readable owner token and is replaced above).
import pytest
from grading.integration.attempt_authority import assemble_controlled_choice_root, AttemptReservationRejected
from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls
from tests.integration.test_attempt_authority import Issuer, AtomicStore
from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
from tests.integration.test_attempt_transaction import Store
from tests.integration.test_attempt_history import EventIssuer, Writer
from grading.integration.attempt_lineage import AttemptLineageDenied


def make_root():
    regular, request, _, _ = assembled_invoker()
    backend=AtomicStore()
    root=assemble_controlled_choice_root(
        handoff=regular._installation.handoff, request_issuer=Issuer(),
        f25_store=backend, ledger=FixtureLedger(), transitions=FixtureTransitions(),
        transaction_store=Store(), approved_f57_policy=fixture_policy(),
        max_identifier_characters=64,history_issuer=EventIssuer(),history_writer=Writer())
    return root,request,backend


def test_failed_begin_does_not_leak_lifecycle_busy_after_original_owner_releases():
    root, request, backend = make_root()
    token = root._claim.begin_operation()
    try:
        with pytest.raises((AttemptReservationRejected,AttemptLineageDenied)):
            root.run_choice(request=request)
    finally:
        root._claim.finish_operation(token=token)
    with _track_choice_and_s2a_calls() as calls:
        result = root.run_choice(request=request)
    assert calls == {'choice':1,'s2a':1}, 'Lifecycle remained poisoned by a failed correlation begin'
    assert backend.claims == 1

def test_correlation_begin_denial_does_not_leak_ambient_private_context():
    root, request, backend = make_root()
    token = root._claim.begin_operation()
    try:
        try:
            raise RuntimeError('PRIVATE_CALLBACK_SECRET')
        except RuntimeError:
            with pytest.raises(AttemptReservationRejected) as observed:
                root.run_choice(request=request)
        assert observed.value.__context__ is None, 'private exception captured in public denial'
        assert observed.value.__cause__ is None
        assert backend.claims == 0
    finally:
        root._claim.finish_operation(token=token)

def test_failed_f25_cannot_emit_failure_with_mutated_original_and_diagnostic():
    from grading.integration.attempt_history import AttemptStage, AttemptEffect
    class MutatingWriter(Writer):
        claim = None
        def append_attempt_event(self, *, event):
            receipt = super().append_attempt_event(event=event)
            if event.stage is AttemptStage.ATTEMPT and event.effect is AttemptEffect.DENIED:
                prior = self.claim._current.record
                altered = (prior[0],'FOREIGN-REQUEST',prior[2],prior[3])
                self.claim._current.record = altered
                self.claim._current.original_record = altered
            return receipt
    regular, request, _, _=assembled_invoker()
    store=AtomicStore();store.mode='conflict';writer=MutatingWriter()
    root=assemble_controlled_choice_root(
        handoff=regular._installation.handoff, request_issuer=Issuer(),
        f25_store=store, ledger=FixtureLedger(),transitions=FixtureTransitions(),
        transaction_store=Store(),approved_f57_policy=fixture_policy(),
        max_identifier_characters=64,history_issuer=EventIssuer(),history_writer=writer)
    writer.claim=root._claim
    with pytest.raises((AttemptReservationRejected,AttemptLineageDenied)):
        root.run_choice(request=request)
    assert store.claims==1
    assert all(e.request_ref != 'FOREIGN-REQUEST' for e in writer.events), [e.request_ref for e in writer.events]


def test_f25_reconciliation_explicit_refusal_subtype_not_uncertain():
    class Refused(AttemptReservationRejected):
        pass
    class RefusingStore(AtomicStore):
        def reconcile_reservation(self, *, request):
            self.reconciliations += 1
            raise Refused('PRIVATE_PROTECTED_REFUSAL')
    invoker, request, _, _, adapter = setup(store=RefusingStore())
    bound = invoker._installation.handoff.prepare_choice_runtime(request=request)
    approved = bound.approved_runtime
    policy = bound.eligibility.policy
    with pytest.raises(AttemptReservationRejected) as caught:
        adapter.reconcile_request(
            scope=bound.eligibility.scope, family='CHOICE',
            runtime_id=approved.runtime_id, runtime_version=approved.runtime_version,
            implementation_ref=approved.implementation_ref,
            eligibility_policy_id=policy.policy_id,
            eligibility_policy_version=policy.policy_version)
    assert type(caught.value) is AttemptReservationRejected
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)


# Independent R8 direct allocator exception privacy regression.
import pytest
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.evaluator_invocation import AttemptReservationUnavailable
from tests.integration.test_attempt_authority import AtomicStore
from tests.integration.test_attempt_history import scope_fixture

def test_direct_f25_unavailable_must_not_retain_private_callback_exception():
    class SecretIssuer:
        def identify_reservation_request(self, *, scope, family, runtime_id,runtime_version,
             implementation_ref,eligibility_policy_id,eligibility_policy_version):
            raise RuntimeError('PRIVATE_F25_ISSUER_SECRET')
    gate=ClaimedAttemptAllocator(issuer=SecretIssuer(),store=AtomicStore(),max_identifier_characters=64)
    with pytest.raises(AttemptReservationUnavailable) as caught:
        gate.reserve_attempt(scope=scope_fixture(),family='CHOICE',runtime_id='R',runtime_version='1',
                             implementation_ref='IMPL',eligibility_policy_id='P',eligibility_policy_version=1)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None, 'PRIVATE ERROR GRAPH RETAINED: '+repr(caught.value.__context__)
