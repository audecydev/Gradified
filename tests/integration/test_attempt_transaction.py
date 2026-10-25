"""Atomic legal operation transition/result/audit port consumer tests; backend fixture is not durable."""
from dataclasses import replace
import pytest

from grading.integration.attempt_transaction import (
    AtomicResultStateAudit, CASDecision, CASRecovery,
    TransactionDisposition, TransactionReconciliation,
    TransactionDenied, TransactionUnavailable, RequestCASRecovery,
)
from grading.integration.attempt_lineage import (
    ProductionChoiceAttemptLifecycle, AttemptLineageUnavailable,
    AttemptLineageContractError, AttemptLineageDenied, AuditedOneQuestionCandidate, AuditCommitReceipt,
)
from tests.integration.test_attempt_lineage import (
    FixtureLedger, FixtureTransitions, fixture_policy,
)
from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls
from tests.integration.test_attempt_authority import Issuer, AtomicStore
from grading.integration.attempt_authority import ClaimedAttemptAllocator


class Store:
    def __init__(self):
        self.effects=[];self.recon=[];self.mode='commit';self.last=None
    def commit_result_state_audit(self, *, transaction, candidate):
        self.effects.append(transaction)
        if self.mode=='timeout_after_commit':
            self.last=transaction
            raise TimeoutError('SECRET_TRANSACTION_COMMITTED')
        if self.mode=='mutate_then_raise':
            object.__setattr__(transaction,'f57_approval_ref','FOREIGN')
            raise RuntimeError('SECRET_BACKEND_ERROR')
        if self.mode=='stale':
            return CASDecision(transaction,TransactionDisposition.STALE_REVISION,None)
        if self.mode=='unknown':
            return CASDecision(transaction,TransactionDisposition.INDETERMINATE,None)
        if self.mode=='wrong_approval':
            receipt=self.receipt(transaction)
            return CASDecision(transaction,TransactionDisposition.COMMITTED,
                replace(receipt,approval_ref='FOREIGN'))
        self.last=transaction
        return CASDecision(transaction,TransactionDisposition.COMMITTED,self.receipt(transaction))
    def receipt(self,tx):
        return AuditCommitReceipt(tx.event_ref,tx.expected_ledger_revision,tx.attempt_id,
            tx.result_ref,'BACKEND-TX-1',tx.target_state,tx.f57_approval_ref,
            tx.request_ref,tx.predecessor_result_ref,tx.regrade_approval_ref)
    def reconcile_result_state_audit(self, *, transaction):
        self.recon.append(transaction)
        if self.last == transaction:
            return CASRecovery(transaction,TransactionReconciliation.COMMITTED,self.receipt(transaction))
        return CASRecovery(transaction,TransactionReconciliation.UNKNOWN,None)
    def reconcile_request_state_audit(self, *, scope, request_ref):
        self.recon.append(request_ref)
        if self.last is not None and self.last.request_ref==request_ref and self.last.scope==scope:
            return RequestCASRecovery(request_ref,scope,TransactionReconciliation.COMMITTED,
                                      self.last,self.receipt(self.last))
        return RequestCASRecovery(request_ref,scope,TransactionReconciliation.UNKNOWN,None,None)


def setup(mode='commit'):
    claims=ClaimedAttemptAllocator(issuer=Issuer(), store=AtomicStore(),
                                   max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claims)
    store=Store();store.mode=mode
    root=ProductionChoiceAttemptLifecycle(invoker=invoker, ledger=FixtureLedger(),
        transitions=FixtureTransitions(), audit=AtomicResultStateAudit(
            store=store,max_identifier_characters=64),
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    return root,request,store


def test_atomic_cas_receipt_binds_exact_f57_approval_and_revision():
    owner,request,store=setup()
    with _track_choice_and_s2a_calls() as calls:
        output=owner.run_choice(request=request)
    assert type(output) is AuditedOneQuestionCandidate
    assert calls=={'choice':1,'s2a':1}
    tx=store.effects[0]
    assert tx.f57_approval_ref == output.approval.approval_ref
    assert tx.expected_ledger_revision == output.approval.ledger_revision
    assert output.audit_receipt.approval_ref == tx.f57_approval_ref
    assert len(store.effects)==1


@pytest.mark.parametrize('mode,exception',[
    ('stale',AttemptLineageDenied),
    ('unknown',AttemptLineageUnavailable),
    ('wrong_approval',AttemptLineageDenied),
    ('mutate_then_raise',AttemptLineageDenied),
    ('timeout_after_commit',AttemptLineageUnavailable),
])
def test_commit_non_success_never_returns_audited_candidate(mode,exception):
    owner,request,store=setup(mode)
    with pytest.raises(exception) as caught:
        owner.run_choice(request=request)
    assert len(store.effects)==1
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'SECRET' not in str(caught.value)


def test_commit_then_timeout_requires_read_only_reconciliation_not_recommit():
    owner,request,store=setup('timeout_after_commit')
    with pytest.raises(AttemptLineageUnavailable):
        owner.run_choice(request=request)
    assert len(store.effects)==1 and store.last is not None
    tx=store.last
    # The event/tx was captured by installed store; reconstruct a matching event
    # from actual execution authority, never use a made-up id to claim publication.
    from grading.integration.attempt_lineage import AttemptAuditEvent
    event=AttemptAuditEvent(tx.event_ref,tx.expected_ledger_revision,tx.result_ref,
        tx.scope,tx.attempt_id,tx.reservation_ref,tx.event_kind,
        tx.f57_policy_id,tx.f57_policy_version,tx.source_state,
        tx.target_state,tx.f57_approval_ref,tx.request_ref,
        tx.predecessor_result_ref,tx.regrade_approval_ref)
    port=AtomicResultStateAudit(store=store,max_identifier_characters=64)
    recovery=port.reconcile_event(event=event)
    assert recovery.disposition is TransactionReconciliation.COMMITTED
    assert len(store.effects)==1 and len(store.recon)==1


def test_approval_revision_or_identifier_mutation_is_rejected_before_atomic_store():
    from dataclasses import replace
    class WrongRevision(FixtureTransitions):
        def authorize_result_transition(self, *, observation,candidate):
            return replace(super().authorize_result_transition(
                observation=observation,candidate=candidate), ledger_revision='STALE-REV')
    claims=ClaimedAttemptAllocator(issuer=Issuer(),store=AtomicStore(),
                                   max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claims)
    store=Store()
    owner=ProductionChoiceAttemptLifecycle(invoker=invoker,ledger=FixtureLedger(),
        transitions=WrongRevision(),audit=AtomicResultStateAudit(
            store=store,max_identifier_characters=64),
        approved_f57_policy=fixture_policy(),max_identifier_characters=64)
    with pytest.raises((AttemptLineageDenied,)):
        owner.run_choice(request=request)
    assert store.effects==[]


def test_atomic_adapter_rejects_event_correlation_to_different_claim_before_store():
    from grading.integration.attempt_lineage import AttemptAuditEvent
    claim=ClaimedAttemptAllocator(issuer=Issuer(),store=AtomicStore(),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claim)
    candidate=invoker.run_one_question(request=request)
    store=Store();audit=AtomicResultStateAudit(store=store,max_identifier_characters=64)
    scope=candidate.reservation.scope
    event=AttemptAuditEvent('EV','REV','RESULT',scope,candidate.reservation.attempt_id,
        candidate.reservation.reservation_ref,'ATTEMPT_RESULT_CANDIDATE',
        'POLICY',1,__import__('grading.contracts.job_state',fromlist=['GradingJobState']).GradingJobState.SCORING,
        __import__('grading.contracts.job_state',fromlist=['GradingJobState']).GradingJobState.RISK_EVALUATION,
        'F57-APPROVAL',candidate.reservation.request_ref)
    with pytest.raises(TransactionDenied):
        audit.commit_event(event=replace(event,request_ref='FOREIGN-REQUEST'),candidate=candidate)
    with pytest.raises(TransactionDenied):
        audit.commit_event(event=replace(event,predecessor_result_ref='FOREIGN-PRIOR',
            regrade_approval_ref='FOREIGN-REGRANT'),candidate=candidate)
    assert store.effects==[]


def test_backend_cannot_mutate_scored_candidate_and_return_committed_success():
    from grading.integration.attempt_lineage import AttemptAuditEvent
    from grading.contracts.job_state import GradingJobState
    claim=ClaimedAttemptAllocator(issuer=Issuer(),store=AtomicStore(),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claim)
    candidate=invoker.run_one_question(request=request)
    event=AttemptAuditEvent('EV','REV','RESULT',candidate.reservation.scope,
        candidate.reservation.attempt_id,candidate.reservation.reservation_ref,
        'ATTEMPT_RESULT_CANDIDATE','POLICY',1,
        GradingJobState.SCORING,GradingJobState.RISK_EVALUATION,
        'F57-APPROVAL',candidate.reservation.request_ref)
    class Alter(Store):
        def commit_result_state_audit(self, *, transaction, candidate):
            output=super().commit_result_state_audit(transaction=transaction,candidate=candidate)
            object.__setattr__(candidate.execution.questions[0].score,'final_score','FOREIGN-SCORE')
            return output
    store=Alter();audit=AtomicResultStateAudit(store=store,max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as err:
        audit.commit_event(event=event,candidate=candidate)
    assert err.value.__cause__ is None and err.value.__context__ is None
    assert len(store.effects)==1  # possible external commit; NOT rollback


def test_direct_atomic_adapter_rejects_wrong_f57_receipt_even_without_lifecycle_wrapper():
    """CAS boundary must reject wrong approval independently of attempt provenance's second check."""
    from grading.integration.attempt_lineage import AttemptAuditEvent
    from grading.contracts.job_state import GradingJobState
    claim=ClaimedAttemptAllocator(issuer=Issuer(),store=AtomicStore(),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claim)
    candidate=invoker.run_one_question(request=request)
    reservation=candidate.reservation
    event=AttemptAuditEvent('EVENT-1','REV-1','RESULT-1',reservation.scope,
        reservation.attempt_id,reservation.reservation_ref,'ATTEMPT_RESULT_CANDIDATE',
        'APPROVED-POLICY',1,GradingJobState.SCORING,GradingJobState.RISK_EVALUATION,
        'APPROVAL-EXPECTED',reservation.request_ref)
    store=Store();store.mode='wrong_approval'
    port=AtomicResultStateAudit(store=store,max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as captured:
        port.commit_event(event=event,candidate=candidate)
    assert type(captured.value) is TransactionDenied
    assert captured.value.__context__ is None and captured.value.__cause__ is None
    assert len(store.effects)==1  # backend may have committed: never imply rollback


def test_installed_cas_operation_cannot_be_swapped_before_commit_or_reconciliation():
    """A callback's arbitrary alias must not authorize a foreign transaction store."""
    installed, foreign = Store(), Store()
    adapter = AtomicResultStateAudit(store=installed,max_identifier_characters=64)
    with pytest.raises(AttributeError):
        adapter._commit=foreign.commit_result_state_audit
    with pytest.raises(AttributeError):
        adapter._reconcile=foreign.reconcile_result_state_audit
    with pytest.raises(AttributeError):
        adapter._reconcile_request=foreign.reconcile_request_state_audit
    for field in ('_commit','_reconcile','_reconcile_request'):
        with pytest.raises(AttributeError):
            delattr(adapter,field)
    # Real installed source is still used on the existing positive path.
    from tests.integration.test_attempt_lineage import build
    owner,request,ledger,f57,audit,_=build()
    candidate=owner.run_choice(request=request)
    assert candidate.audit_receipt is not None


def _recovery_event_for(tx):
    from grading.integration.attempt_lineage import AttemptAuditEvent
    return AttemptAuditEvent(
        tx.event_ref, tx.expected_ledger_revision, tx.result_ref, tx.scope,
        tx.attempt_id, tx.reservation_ref, tx.event_kind, tx.f57_policy_id,
        tx.f57_policy_version, tx.source_state, tx.target_state,
        tx.f57_approval_ref, tx.request_ref, tx.predecessor_result_ref,
        tx.regrade_approval_ref)


def test_recovery_transaction_mutation_then_backend_timeout_is_integrity_denial():
    class Corrupt(Store):
        def reconcile_result_state_audit(self, *, transaction):
            self.recon.append(transaction)
            object.__setattr__(transaction, 'result_ref', 'FOREIGN-RESULT')
            raise TimeoutError('CONFIDENTIAL_RECOVERY_TIMEOUT')
    owner, request, store = setup()
    owner.run_choice(request=request)
    backend = Corrupt()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as caught:
        port.reconcile_event(event=_recovery_event_for(store.effects[0]))
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(backend.recon) == 1 and backend.effects == []


@pytest.mark.parametrize('exceptional', [False, True])
def test_recovery_checks_original_event_drift_on_normal_or_exceptional_callback(exceptional):
    owner, request, store = setup()
    owner.run_choice(request=request)
    event = _recovery_event_for(store.effects[0])
    class EventMutator(Store):
        def reconcile_result_state_audit(self, *, transaction):
            self.recon.append(transaction)
            object.__setattr__(event, 'result_ref', 'FOREIGN-RESULT')
            if exceptional:
                raise TimeoutError('CONFIDENTIAL_RECOVERY_TIMEOUT')
            return CASRecovery(transaction, TransactionReconciliation.UNKNOWN, None)
    backend = EventMutator()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as caught:
        port.reconcile_event(event=event)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(backend.recon) == 1 and backend.effects == []


def test_recovery_request_scope_mutation_then_backend_timeout_is_integrity_denial():
    class Corrupt(Store):
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            object.__setattr__(scope, 'grading_run_id', 'FOREIGN-RUN')
            raise TimeoutError('CONFIDENTIAL_RECOVERY_TIMEOUT')
    owner, request, store = setup()
    owner.run_choice(request=request)
    tx = store.effects[0]
    backend = Corrupt()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as caught:
        port.reconcile_owned_request(scope=tx.scope, request_ref=tx.request_ref)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert backend.recon == [tx.request_ref] and backend.effects == []


def test_recovery_original_caller_scope_drift_is_denied():
    owner, request, store = setup()
    owner.run_choice(request=request)
    tx = store.effects[0]
    scope = replace(tx.scope)
    class CorruptOriginal(Store):
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            object.__setattr__(original_scope, 'question_id', 'FOREIGN-QUESTION')
            return RequestCASRecovery(request_ref, scope, TransactionReconciliation.UNKNOWN, None, None)
    original_scope = scope
    backend = CorruptOriginal()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionDenied):
        port.reconcile_owned_request(scope=original_scope, request_ref=tx.request_ref)
    assert backend.recon == [tx.request_ref] and backend.effects == []


@pytest.mark.parametrize('kind', ['event', 'request'])
def test_recovery_explicit_typed_denial_preserves_denial_family(kind):
    class SubclassDenial(TransactionDenied):
        pass
    class Refusing(Store):
        def reconcile_result_state_audit(self, *, transaction):
            self.recon.append(transaction)
            raise SubclassDenial('CONFIDENTIAL_STORE_REFUSAL')
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            raise SubclassDenial('CONFIDENTIAL_STORE_REFUSAL')
    owner, request, store = setup()
    owner.run_choice(request=request)
    tx = store.effects[0]
    backend = Refusing()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as caught:
        if kind == 'event':
            port.reconcile_event(event=_recovery_event_for(tx))
        else:
            port.reconcile_owned_request(scope=tx.scope, request_ref=tx.request_ref)
    assert type(caught.value) is TransactionDenied
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'CONFIDENTIAL' not in str(caught.value)
    assert len(backend.recon) == 1


@pytest.mark.parametrize('kind', ['event', 'request'])
def test_recovery_unchanged_backend_timeout_remains_unavailable(kind):
    class Timeout(Store):
        def reconcile_result_state_audit(self, *, transaction):
            self.recon.append(transaction)
            raise TimeoutError('CONFIDENTIAL_TIMEOUT')
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            raise TimeoutError('CONFIDENTIAL_TIMEOUT')
    owner, request, store = setup()
    owner.run_choice(request=request)
    tx = store.effects[0]
    backend = Timeout()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionUnavailable) as caught:
        if kind == 'event':
            port.reconcile_event(event=_recovery_event_for(tx))
        else:
            port.reconcile_owned_request(scope=tx.scope, request_ref=tx.request_ref)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(backend.recon) == 1


# R8: independent R7 falsification — direct commit must preserve its original
# submitted event, even when the backend has potentially already committed.
@pytest.mark.parametrize('field', ('result_ref', 'request_ref', 'approval_ref', 'ledger_revision'))
@pytest.mark.parametrize('backend_raises', (False, True))
def test_original_event_cannot_drift_across_direct_commit(field, backend_raises):
    from grading.integration.attempt_lineage import AttemptAuditEvent
    from grading.contracts.job_state import GradingJobState
    allocator = ClaimedAttemptAllocator(issuer=Issuer(), store=AtomicStore(),
                                        max_identifier_characters=64)
    invoker, request, _, _ = assembled_invoker(allocator)
    with _track_choice_and_s2a_calls() as calls:
        candidate = invoker.run_one_question(request=request)
    assert calls == {'choice': 1, 's2a': 1}
    reservation = candidate.reservation
    event = AttemptAuditEvent('EVENT-1', 'REV-1', 'RESULT-1', reservation.scope,
        reservation.attempt_id, reservation.reservation_ref, 'ATTEMPT_RESULT_CANDIDATE',
        'POLICY', 1, GradingJobState.SCORING, GradingJobState.RISK_EVALUATION,
        'F57-APPROVAL', reservation.request_ref)

    class Tamper(Store):
        def commit_result_state_audit(self, *, transaction, candidate):
            object.__setattr__(event, field, 'FOREIGN-CORRELATION')
            if backend_raises:
                self.effects.append(transaction)
                raise TimeoutError('PRIVATE_AFTER_POSSIBLE_COMMIT')
            return super().commit_result_state_audit(transaction=transaction, candidate=candidate)

    store = Tamper()
    adapter = AtomicResultStateAudit(store=store, max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as caught:
        adapter.commit_event(event=event, candidate=candidate)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(store.effects) == 1  # not evidence of backend rollback


class ForeignLineageEquality:
    def __init__(self): self.calls = 0
    def __eq__(self, other):
        self.calls += 1
        return True
    def __ne__(self, other):
        self.calls += 1
        return False


@pytest.mark.parametrize('field', ('predecessor_result_ref', 'regrade_approval_ref'))
@pytest.mark.parametrize('bad_value', ('foreign', 'string_subclass', 'overlong', 'bool'))
def test_cas_receipt_optional_lineage_requires_canonical_primitive(field, bad_value):
    class SubString(str): pass
    foreign = ForeignLineageEquality()
    bad = {'foreign': foreign, 'string_subclass': SubString('PRIOR'),
           'overlong': 'X' * 65, 'bool': True}[bad_value]

    class MalformedReceipt(Store):
        def commit_result_state_audit(self, *, transaction, candidate):
            self.effects.append(transaction)
            return CASDecision(transaction, TransactionDisposition.COMMITTED,
                replace(self.receipt(transaction), **{field: bad}))

    # Use the concrete CAS adapter with the malicious *result*, not a fixture
    # that skips CAS admission.
    malicious = MalformedReceipt()
    claims = ClaimedAttemptAllocator(issuer=Issuer(), store=AtomicStore(), max_identifier_characters=64)
    invoker, request, _, _ = assembled_invoker(claims)
    lifecycle = ProductionChoiceAttemptLifecycle(invoker=invoker, ledger=FixtureLedger(),
        transitions=FixtureTransitions(),
        audit=AtomicResultStateAudit(store=malicious, max_identifier_characters=64),
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)) as caught:
        lifecycle.run_choice(request=request)
    assert len(malicious.effects) == 1
    assert foreign.calls == 0
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize('field', ('predecessor_result_ref', 'regrade_approval_ref'))
def test_generic_audit_port_must_also_reject_foreign_optional_receipt_lineage(field):
    from tests.integration.test_attempt_lineage import build
    foreign = ForeignLineageEquality()
    owner, request, ledger, f57, audit, attempts = build()
    audit.replacement = lambda r: replace(r, **{field: foreign})
    with pytest.raises(AttemptLineageContractError):
        owner.run_choice(request=request)
    assert foreign.calls == 0 and len(audit.events) == 1


@pytest.mark.parametrize('recovery_mode', ('event', 'request'))
def test_read_only_committed_recovery_rejects_foreign_optional_lineage(recovery_mode):
    from grading.integration.attempt_lineage import AttemptAuditEvent
    foreign = ForeignLineageEquality()

    class WrongRecovery(Store):
        def reconcile_result_state_audit(self, *, transaction):
            self.recon.append(transaction)
            return CASRecovery(transaction, TransactionReconciliation.COMMITTED,
                replace(self.receipt(transaction), predecessor_result_ref=foreign))
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            return RequestCASRecovery(request_ref, scope, TransactionReconciliation.COMMITTED,
                self.last, replace(self.receipt(self.last), predecessor_result_ref=foreign))

    store = WrongRecovery()
    # Obtain one genuine installed candidate and committed fixture transaction.
    claims = ClaimedAttemptAllocator(issuer=Issuer(), store=AtomicStore(), max_identifier_characters=64)
    invoker, request, _, _ = assembled_invoker(claims)
    candidate = invoker.run_one_question(request=request)
    from grading.contracts.job_state import GradingJobState
    r = candidate.reservation
    event = AttemptAuditEvent('EVENT','REV','RESULT',r.scope,r.attempt_id,r.reservation_ref,
         'ATTEMPT_RESULT_CANDIDATE','POLICY',1,GradingJobState.SCORING,
         GradingJobState.RISK_EVALUATION,'APPROVAL',r.request_ref)
    audit = AtomicResultStateAudit(store=store, max_identifier_characters=64)
    audit.commit_event(event=event,candidate=candidate)
    if recovery_mode == 'event':
        with pytest.raises(TransactionDenied): audit.reconcile_event(event=event)
    else:
        with pytest.raises(TransactionDenied):
            audit.reconcile_owned_request(scope=r.scope, request_ref=r.request_ref)
    assert foreign.calls == 0 and len(store.effects) == 1


@pytest.mark.parametrize('backend_raises', (False, True))
def test_unchanged_direct_event_retains_normal_commit_or_uncertain_outcome(backend_raises):
    from grading.integration.attempt_lineage import AttemptAuditEvent
    from grading.contracts.job_state import GradingJobState
    claims = ClaimedAttemptAllocator(issuer=Issuer(),store=AtomicStore(),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claims)
    candidate=invoker.run_one_question(request=request)
    r=candidate.reservation
    event=AttemptAuditEvent('EV','REV','RESULT',r.scope,r.attempt_id,r.reservation_ref,
       'ATTEMPT_RESULT_CANDIDATE','POLICY',1,GradingJobState.SCORING,
       GradingJobState.RISK_EVALUATION,'APPROVAL',r.request_ref)
    store=Store();store.mode='timeout_after_commit' if backend_raises else 'commit'
    port=AtomicResultStateAudit(store=store,max_identifier_characters=64)
    if backend_raises:
        with pytest.raises(TransactionUnavailable): port.commit_event(event=event,candidate=candidate)
    else:
        assert port.commit_event(event=event,candidate=candidate).result_ref == event.result_ref
    assert len(store.effects)==1

@pytest.mark.parametrize('bad_field', ('predecessor_result_ref','regrade_approval_ref'))
def test_direct_cas_receipt_independently_refuses_foreign_paired_lineage(bad_field):
    """Standalone CAS must not rely on the lifecycle's second receipt guard."""
    from grading.integration.attempt_lineage import AttemptAuditEvent
    from grading.contracts.job_state import GradingJobState
    claim = ClaimedAttemptAllocator(issuer=Issuer(),store=AtomicStore(),max_identifier_characters=64)
    invoker,request,_,_=assembled_invoker(claim)
    candidate=invoker.run_one_question(request=request)
    r=candidate.reservation
    event=AttemptAuditEvent('EV','REV','RESULT',r.scope,r.attempt_id,r.reservation_ref,
        'ATTEMPT_RESULT_CANDIDATE','POLICY',1,GradingJobState.SCORING,
        GradingJobState.RISK_EVALUATION,'APPROVAL',r.request_ref)
    foreign=ForeignLineageEquality()
    class BadStore(Store):
        def commit_result_state_audit(self, *, transaction, candidate):
            self.effects.append(transaction)
            # Both references look present, but one uses hostile equality.
            data=dict(predecessor_result_ref='VALID-PRIOR', regrade_approval_ref='VALID-GRANT')
            data[bad_field]=foreign
            return CASDecision(transaction,TransactionDisposition.COMMITTED,
                               replace(self.receipt(transaction),**data))
    store=BadStore()
    with pytest.raises(TransactionDenied):
        AtomicResultStateAudit(store=store,max_identifier_characters=64).commit_event(
            event=event,candidate=candidate)
    assert len(store.effects)==1 and foreign.calls==0


@pytest.mark.parametrize('bad_field', ('predecessor_result_ref','regrade_approval_ref'))
def test_generic_audit_receipt_independently_refuses_foreign_paired_lineage(bad_field):
    from tests.integration.test_attempt_lineage import build
    foreign=ForeignLineageEquality()
    owner,request,ledger,f57,audit,attempts=build()
    def bad_receipt(receipt):
        data=dict(predecessor_result_ref='VALID-PRIOR',regrade_approval_ref='VALID-GRANT')
        data[bad_field]=foreign
        return replace(receipt,**data)
    audit.replacement=bad_receipt
    with pytest.raises(AttemptLineageContractError):
        owner.run_choice(request=request)
    assert len(audit.events)==1 and foreign.calls==0


# R10 — independent R9 recovery-falsification regression. Request-keyed
# COMMITTED recovery must enforce the same event type as forward CAS and
# event-keyed recovery, before treating a matching receipt as an admission.
@pytest.mark.parametrize('foreign_kind', ('OTHER_EVENT_KIND', 'DELETE_RESULT'))
def test_committed_request_recovery_rejects_unsupported_event_kind(foreign_kind):
    owner, request, committed = setup()
    with _track_choice_and_s2a_calls() as calls:
        owner.run_choice(request=request)
    tx = committed.last
    assert tx.event_kind == 'ATTEMPT_RESULT_CANDIDATE'

    class ForeignKindRecovery(Store):
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            foreign = replace(tx, event_kind=foreign_kind)
            return RequestCASRecovery(request_ref, scope, TransactionReconciliation.COMMITTED,
                                      foreign, self.receipt(foreign))

    backend = ForeignKindRecovery()
    port = AtomicResultStateAudit(store=backend, max_identifier_characters=64)
    with pytest.raises(TransactionDenied) as caught:
        port.reconcile_owned_request(scope=tx.scope, request_ref=tx.request_ref)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert backend.recon == [tx.request_ref] and backend.effects == []
    assert calls == {'choice': 1, 's2a': 1}
    assert len(committed.effects) == 1  # neither re-claim nor re-commit


def test_valid_committed_request_recovery_retains_original_event_kind():
    owner, request, backend = setup()
    owner.run_choice(request=request)
    tx = backend.last
    response = AtomicResultStateAudit(store=backend, max_identifier_characters=64) \
        .reconcile_owned_request(scope=tx.scope, request_ref=tx.request_ref)
    assert response.disposition is TransactionReconciliation.COMMITTED
    assert response.transaction.event_kind == 'ATTEMPT_RESULT_CANDIDATE'
    assert response.receipt is not None
    assert len(backend.effects) == 1 and backend.recon == [tx.request_ref]


def test_controlled_root_request_recovery_rejects_unsupported_event_kind():
    from grading.integration.attempt_authority import assemble_controlled_choice_root
    from tests.integration.test_attempt_history import EventIssuer, Writer

    class ForeignKindRecovery(Store):
        def reconcile_request_state_audit(self, *, scope, request_ref):
            self.recon.append(request_ref)
            foreign = replace(self.last, event_kind='OTHER-VALID-HISTORY-EVENT')
            return RequestCASRecovery(request_ref, scope, TransactionReconciliation.COMMITTED,
                                      foreign, self.receipt(foreign))

    invoker, request, _, _ = assembled_invoker()
    claims, backend = AtomicStore(), ForeignKindRecovery()
    owner = assemble_controlled_choice_root(
        handoff=invoker._installation.handoff, request_issuer=Issuer(), f25_store=claims,
        ledger=FixtureLedger(), transitions=FixtureTransitions(), transaction_store=backend,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
        history_issuer=EventIssuer(), history_writer=Writer())
    with _track_choice_and_s2a_calls() as calls:
        owner.run_choice(request=request)
        with pytest.raises(TransactionDenied) as caught:
            owner.reconcile_owned_transaction(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert calls == {'choice': 1, 's2a': 1}
    assert claims.claims == 1 and len(backend.effects) == 1 and len(backend.recon) == 1
