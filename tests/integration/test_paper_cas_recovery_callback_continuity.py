"""Verify post-admission callback changes do not compromise CAS recovery outcomes."""
from dataclasses import replace

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.attempt_history import _private_constructor
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import (
    PaperCASState, ProductionPaperCASDurableRecovery, ProductionWholePaperCAS,
)
from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY, Permissions
from tests.integration.test_original_recovery_complete_paper_gate import FixedPaperOriginal
from tests.integration.test_whole_paper_cas import Store, OriginalSource, Issuer
from tests.integration.test_academic_effect_preclaim import setup_bound
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests

class DriftingOriginal:
    def __init__(self, tx):
        self.tx = tx
        self.target = None
        self.reads = 0
    def resolve_owned_original_paper_transaction(self):
        self.reads += 1
        # The original-source call happens AFTER the consumer's initial
        # exact CAS outcome-field validation. Adversarial drift under callback.
        object.__setattr__(self.target, 'academic_binding_verified', 'yes')
        return self.tx

class DriftingOriginalTransaction(OriginalSource):
    def __init__(self):
        super().__init__()
        self.target = None
    def resolve_original_paper_transaction(self, *, plan, request_ref):
        if self.target is not None:
            object.__setattr__(self.target, 'state', 'COMMITTED')
        return super().resolve_original_paper_transaction(plan=plan, request_ref=request_ref)


def test_durable_recovery_must_not_return_committed_after_issuer_callback_corrupts_outcome():
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    original = DriftingOriginal(actual.cas.transaction)
    reader = ProductionPaperCASDurableRecovery(original_source=original,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observation = replace(actual.cas,state=PaperCASState.UNKNOWN,
                          academic_binding_verified=True, receipt=None)
    original.target = observation
    before = store.reads
    result = reader.reconcile(outcome=observation)
    assert result is PaperCASState.UNKNOWN, ('incorrectly approved modified input',result)
    assert store.reads == before, 'must stop before CAS backend read after source changed input'


def test_durable_recovery_genuine_unchanged_lost_ack_remains_recoverable():
    svc, plan, physical, store, issuer = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    original = FixedPaperOriginal(actual.cas.transaction)
    reader = ProductionPaperCASDurableRecovery(original_source=original,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observation = replace(actual.cas,state=PaperCASState.UNKNOWN,
                          academic_binding_verified=True, receipt=None)
    before = store.reads
    result = reader.reconcile(outcome=observation)
    assert result is PaperCASState.COMMITTED
    assert store.reads == before+1


def test_same_process_cas_recovery_must_not_return_committed_after_original_source_corrupts_outcome():
    root, plan, physical, backend = setup_bound()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
       request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    original = DriftingOriginalTransaction()
    store = Store()
    cas = ProductionWholePaperCAS(custody=custody, issuer=Issuer(original),
        original_source=original, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10, require_academic_preclaim=True)
    svc=ProductionPaperLifecycle(cas=cas,permission_source=Permissions(),
       legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    actual=svc.execute_first(plan=plan)
    assert actual.cas.state is PaperCASState.COMMITTED
    assert id(actual.cas) in cas._issued
    original.target=actual.cas
    before=store.reads
    result=cas.reconcile(outcome=actual.cas)
    assert result is PaperCASState.UNKNOWN, ('incorrectly approved corrupted issued input',result)
    assert store.reads==before, 'must prevent backend read after corruption during original-source call'

class DriftingFieldOriginal:
    def __init__(self, tx, field, value):
        self.tx=tx;self.field=field;self.value=value;self.target=None;self.reads=0
    def resolve_owned_original_paper_transaction(self):
        self.reads+=1
        object.__setattr__(self.target,self.field,self.value)
        return self.tx


def test_durable_recovery_must_revalidate_correctly_typed_state_after_original_source():
    svc,plan,phys,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    source=DriftingFieldOriginal(actual.cas.transaction,'state',PaperCASState.COMMITTED)
    reader=ProductionPaperCASDurableRecovery(original_source=source,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observation=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=None)
    source.target=observation
    before=store.reads
    result=reader.reconcile(outcome=observation)
    assert result is PaperCASState.UNKNOWN,('changed typed state incorrectly accepted',result)
    assert store.reads==before


def test_durable_recovery_must_revalidate_transaction_identity_after_original_source():
    svc,plan,phys,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    source=DriftingFieldOriginal(actual.cas.transaction,'transaction',
                                replace(actual.cas.transaction,request_ref='FOREIGN-REQUEST'))
    reader=ProductionPaperCASDurableRecovery(original_source=source,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observation=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=None)
    source.target=observation
    before=store.reads
    result=reader.reconcile(outcome=observation)
    assert result is PaperCASState.UNKNOWN,('changed transaction identity accepted',result)
    assert store.reads==before


class CallbackMutatingStore(Store):
    def __init__(self):
        super().__init__();self.target=None
    def reconcile_whole_paper(self, *, transaction):
        assert self.target is not None
        object.__setattr__(self.target,'academic_binding_verified',0)
        return super().reconcile_whole_paper(transaction=transaction)


def test_durable_recovery_must_revalidate_outcome_after_backend_read():
    svc,plan,phys,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    malicious_store=CallbackMutatingStore()
    source=FixedPaperOriginal(actual.cas.transaction)
    reader=ProductionPaperCASDurableRecovery(original_source=source,store=malicious_store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observation=replace(actual.cas,state=PaperCASState.UNKNOWN,receipt=None)
    malicious_store.target=observation
    result=reader.reconcile(outcome=observation)
    assert result is PaperCASState.UNKNOWN,('changed flag at backend read accepted',result)
    assert malicious_store.reads==1

class DriftingReceiptOriginal:
    def __init__(self, transaction):
        self.transaction=transaction
        self.target=None
    def resolve_owned_original_paper_transaction(self):
        object.__setattr__(self.target.receipt,'commit_ref','FOREIGN-AFTER-PREFLIGHT')
        return self.transaction


def test_durable_recovery_must_detect_receipt_content_mutation_during_original_read():
    svc,plan,physical,store,_=setup_lifecycle()
    actual=svc.execute_first(plan=plan)
    source=DriftingReceiptOriginal(actual.cas.transaction)
    reader=ProductionPaperCASDurableRecovery(original_source=source,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    uncertain=replace(actual.cas,state=PaperCASState.UNKNOWN)
    source.target=uncertain
    before=store.reads
    result=reader.reconcile(outcome=uncertain)
    assert result is PaperCASState.UNKNOWN, ('changed receipt was accepted',result)
    assert store.reads==before

class MutatingPredecessorOriginal:
    def __init__(self, original):
        self.original = original
        self.predecessor = None
        self.reads = 0
    def resolve_owned_original_paper_transaction(self):
        self.reads += 1
        object.__setattr__(self.predecessor, 'request_ref', 'ALTERED-PREVIOUS-REQUEST')
        return self.original


def test_durable_recovery_rejects_changed_predecessor_before_backend():
    svc, plan, _, store, _ = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    original = MutatingPredecessorOriginal(actual.cas.transaction)
    reader = ProductionPaperCASDurableRecovery(original_source=original, store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    # Start from a genuinely distinct same-paper generation. The original
    # callback mutates it; the test must exercise post-callback continuity,
    # not be blocked by the earlier pre-source collision gate.
    from tests.integration.test_paper_cas_predecessor_paper_scope import prior_for
    prior = prior_for(actual.cas.transaction)
    original.predecessor = prior
    observed = replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    before = store.reads
    assert reader.reconcile(outcome=observed, disjoint_from=prior) is PaperCASState.UNKNOWN
    assert original.reads == 1
    assert store.reads == before


class MutatingPredecessorBackend:
    def __init__(self, backing, predecessor):
        self.backing = backing
        self.predecessor = predecessor
        self.reads = 0
    def reconcile_whole_paper(self, *, transaction):
        self.reads += 1
        object.__setattr__(self.predecessor, 'event_ref', transaction.event_ref)
        return self.backing.reconcile_whole_paper(transaction=transaction)


def test_durable_recovery_rejects_changed_predecessor_after_backend():
    svc, plan, _, store, _ = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    original = FixedPaperOriginal(actual.cas.transaction)
    # A genuinely distinct predecessor cannot reuse the current grading run
    # or current physical identities merely by changing CAS references.
    current = actual.cas.transaction
    earlier_request = replace(current.intent.plan.request, grading_run_id='PREVIOUS-RUN')
    old_intent = replace(current.intent,
        plan=replace(current.intent.plan, request=earlier_request,
            questions=tuple(replace(q,request=replace(q.request,
                grading_run_id=earlier_request.grading_run_id))
                for q in current.intent.plan.questions)),
        issued=replace(current.intent.issued, request=earlier_request),
        question_claims=tuple((qid, 'PREV-'+req, 'PREV-'+attempt, 'PREV-'+reservation)
                              for qid, req, attempt, reservation in current.intent.question_claims),
        original_claim_requests=tuple(replace(o, request_ref='PREV-'+o.request_ref,
            scope=replace(o.scope,grading_run_id='PREVIOUS-RUN'))
            for o in current.intent.original_claim_requests),
        result=replace(current.intent.result, context=replace(current.intent.result.context,
            grading_run_id='PREVIOUS-RUN')))
    prior = replace(current, intent=old_intent, request_ref='DISTINCT-REQUEST',
                    event_ref='DISTINCT-EVENT', result_ref='DISTINCT-RESULT')
    changing_store = MutatingPredecessorBackend(store, prior)
    reader = ProductionPaperCASDurableRecovery(original_source=original,store=changing_store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observed = replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    assert reader.reconcile(outcome=observed, disjoint_from=prior) is PaperCASState.UNKNOWN
    assert changing_store.reads == 1


class CountOriginalReads:
    def __init__(self, tx):
        self.tx = tx
        self.reads = 0
    def resolve_owned_original_paper_transaction(self):
        self.reads += 1
        return self.tx


def test_durable_recovery_rejects_invalid_predecessor_type_before_original_read():
    svc, plan, _, store, _ = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    original = CountOriginalReads(actual.cas.transaction)
    reader = ProductionPaperCASDurableRecovery(original_source=original,store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    observed = replace(actual.cas, state=PaperCASState.UNKNOWN, receipt=None)
    assert reader.reconcile(outcome=observed, disjoint_from='NOT-A-TRANSACTION') is PaperCASState.BLOCKED
    assert original.reads == 0
