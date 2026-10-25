"""original attempt accounting/governed scored-paper handoff genuine backend-read controls with first-forbidden-effect assertions."""
from dataclasses import replace

from grading.contracts.job_state import GradingJobState
from grading.integration.paper_lifecycle import PaperLifecycleState, PaperLifecycleKind
from grading.integration.whole_paper_cas import (
    ProductionPaperCASDurableRecovery, PaperCASState, PaperCASOutcome,
)
from grading.integration.paper_accounting import (
    ProductionPaperAccounting, PaperAccountingState,
)
from grading.integration.scored_paper_promotion import ProductionPaperPromotion, PaperHandoffEligibilityState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY
from tests.integration.test_paper_lifecycle_regrade import setup_regrade


class FixedPaperOriginal:
    def __init__(self, original):
        self.original = original
        self.calls = 0
    def resolve_owned_original_paper_transaction(self):
        self.calls += 1
        return self.original


class FixedLifecycleOriginal:
    def __init__(self, original):
        self.original = original
        self.calls = 0
    def resolve_original_paper_lifecycle(self):
        self.calls += 1
        if self.original is None:
            raise RuntimeError('PRIVATE-SCHOOL-RECORD-UNAVAILABLE')
        return self.original


def _gate(record, store, *, prior=None):
    source = FixedLifecycleOriginal(record)
    current = FixedPaperOriginal(record.cas.transaction)
    recovery = ProductionPaperCASDurableRecovery(
        original_source=current, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    previous = None
    if prior is not None:
        orig_prev = FixedPaperOriginal(prior.transaction)
        previous = ProductionPaperCASDurableRecovery(
            original_source=orig_prev, store=store, legal_policy=POLICY,
            max_identifier_characters=128, max_questions=10)
    accounting = ProductionPaperAccounting(operations=(), max_identifier_characters=128)
    gate = ProductionPaperPromotion(original_source=source, audit_recovery=recovery,
        predecessor_audit_recovery=previous, accounting=accounting, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    return gate, source, current


def test_native_two_question_paper_requires_actual_original_audit_and_no_provider_receipts():
    service, plan, physical, store, _ = setup_lifecycle()
    record = service.execute_first(plan=plan)
    assert record.state is PaperLifecycleState.CAS_ACKNOWLEDGED and record.permission is not None
    gate, source, current = _gate(record, store)
    claims, commits, reads = physical.claims, store.commits, store.reads
    decision = gate.assess()
    assert decision.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert not decision.authorizes_publication and not decision.authorizes_retry
    assert physical.claims == claims and store.commits == commits
    assert store.reads == reads + 1 and source.calls == current.calls == 1
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert physical.claims == claims and store.commits == commits


def test_missing_original_history_returns_unknown_without_backend_read():
    svc, plan, physical, store, _ = setup_lifecycle()
    record = svc.execute_first(plan=plan)
    gate, src, origin = _gate(record, store)
    src.original = None
    old_reads = store.reads
    assert gate.assess().state is PaperHandoffEligibilityState.UNKNOWN
    assert store.reads == old_reads and origin.calls == 0


def test_caller_cannot_select_an_alternative_original_paper_transaction():
    svc, plan, physical, store, _ = setup_lifecycle()
    record = svc.execute_first(plan=plan)
    gate, _, original = _gate(record, store)
    from dataclasses import replace
    original.original = replace(record.cas.transaction, request_ref='FOREIGN-REQUEST')
    before = store.reads
    assert gate.assess().state in (PaperHandoffEligibilityState.UNKNOWN, PaperHandoffEligibilityState.CONFLICT)
    # A fixed-origin source may return an invalid transaction, but it must
    # never authorize reading that alternative from the backend.
    assert store.reads == before


def test_c5_refuses_legacy_unbound_commit_and_missing_f57_observation_before_reads():
    svc, plan, physical, store, _ = setup_lifecycle()
    actual = svc.execute_first(plan=plan)
    for forged in (
        replace(actual, cas=replace(actual.cas, academic_binding_verified=False)),
        replace(actual, permission=None),
        replace(actual, permission=replace(actual.permission, policy_id='WRONG-F57')),
        replace(actual, permission=replace(actual.permission, plan=replace(plan, approval_ref='WRONG'))),
        replace(actual, permission=replace(actual.permission, target_state=GradingJobState.COMPLETED)),
    ):
        gate, _, original = _gate(forged, store)
        before = store.reads
        assert gate.assess().state is PaperHandoffEligibilityState.BLOCKED
        assert store.reads == before and original.calls == 0


def test_unknown_and_conflicting_original_cas_receipts_block_promotion():
    from grading.integration.whole_paper_cas import PaperCASRecovery, PaperCASDisposition
    from tests.integration.test_whole_paper_cas import Store
    class BadReadStore(Store):
        def reconcile_whole_paper(self, *, transaction):
            self.reads += 1
            if self.mode == 'FAIL_READ':
                raise RuntimeError('PRIVATE CAS BACKEND UNAVAILABLE')
            return PaperCASRecovery(transaction, PaperCASDisposition.CONFLICT, None)
    svc, plan, physical, store, _ = setup_lifecycle(store_class=BadReadStore)
    actual = svc.execute_first(plan=plan)
    assert actual.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    gate, _, _ = _gate(actual, store)
    before = physical.claims, store.commits, store.reads
    store.mode = 'FAIL_READ'
    assert gate.assess().state is PaperHandoffEligibilityState.UNKNOWN
    store.mode = 'CONFLICT_READ'
    assert gate.assess().state is PaperHandoffEligibilityState.CONFLICT
    assert (physical.claims, store.commits) == before[:2]
    assert store.reads == before[2] + 2


def test_genuine_regrade_checks_both_original_paper_generations(monkeypatch):
    svc, plan, physical, store, _, backend, prior = setup_regrade(monkeypatch)
    observation = svc.execute_regrade(plan=plan)
    assert observation.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert observation.permission is not None
    gate, _, _ = _gate(observation, store, prior=prior.cas if hasattr(prior,'cas') else prior)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert physical.claims == 2 and store.commits == 2


def test_regrade_without_fixed_predecessor_source_cannot_promote(monkeypatch):
    svc, plan, physical, store, _, backend, old = setup_regrade(monkeypatch)
    observation = svc.execute_regrade(plan=plan)
    assert observation.kind is PaperLifecycleKind.REGRADE
    gate, _, _ = _gate(observation, store)
    reads = store.reads
    assert gate.assess().state is PaperHandoffEligibilityState.BLOCKED
    assert store.reads == reads


def test_choice_accounting_has_no_fake_provider_receipts():
    svc, plan, physical, store, _ = setup_lifecycle()
    observed = svc.execute_first(plan=plan)
    accounting = ProductionPaperAccounting(operations=(), max_identifier_characters=128)
    actual = accounting.reconcile(intent=observed.cas.transaction.intent)
    assert actual.state is PaperAccountingState.NOT_APPLICABLE
    assert not actual.authorizes_publication

class FakeProviderReadStore:
    def __init__(self):
        self.mode = 'RECORDED'
        self.reads = 0
    def reconcile_outcome(self, *, identity):
        from grading.providers.accounting_recovery import (
            AccountingRecoveryFact, AccountingRecoveryDisposition,
        )
        from grading.providers.attempt_accounting import ProviderAccountingReceipt
        self.reads += 1
        if self.mode == 'THROW':
            raise RuntimeError('PRIVATE-ACCOUNTING-STORE-ERROR')
        if self.mode == 'CONFLICT':
            return AccountingRecoveryFact(identity, AccountingRecoveryDisposition.CONFLICT, None, None)
        if self.mode == 'NOT_FOUND':
            return AccountingRecoveryFact(identity, AccountingRecoveryDisposition.NOT_FOUND, None, None)
        if self.mode == 'FOREIGN':
            return AccountingRecoveryFact(replace(identity, operation_ref='FOREIGN'),
               AccountingRecoveryDisposition.RECORDED, 'RESULT_RETURNED',
               ProviderAccountingReceipt(identity.event_ref, identity.operation_ref, 'RESULT_RETURNED'))
        return AccountingRecoveryFact(identity, AccountingRecoveryDisposition.RECORDED,
           'RESULT_RETURNED', ProviderAccountingReceipt(identity.event_ref,
                                                       identity.operation_ref, 'RESULT_RETURNED'))


class FakeApplicability:
    def __init__(self, fact):
        self.fact = fact
        self.mode = 'OK'
    def resolve_original_provider_applicability(self):
        if self.mode == 'FAIL':
            raise RuntimeError('PRIVATE-SCHOOL-APPLICABILITY-FAIL')
        return self.fact


def _provider_accounting_fixture():
    from grading.providers.attempt_accounting import ProviderAttemptIdentity
    from grading.providers.accounting_recovery import ReadOnlyAccountingReconciler
    from grading.integration.paper_accounting import (
        OriginalProviderOperation, PaperProviderApplicability,
    )
    svc, plan, physical, store, _ = setup_lifecycle()
    record = svc.execute_first(plan=plan)
    intent = record.cas.transaction.intent
    # This is a contract-only DIRECT applicability test. It is deliberately
    # NOT a claim that CHOICE actually dispatched a provider request.
    question = intent.plan.questions[0]
    candidate = replace(intent,
        plan=replace(intent.plan, questions=(
            replace(question, family='DIRECT'), *intent.plan.questions[1:])),
        issued=replace(intent.issued, questions=(
            replace(intent.issued.questions[0], family='DIRECT'),
            *intent.issued.questions[1:])))
    # Synthetic family-admission fixture must not carry an original CHOICE
    # request for a question it now declares DIRECT. This is NOT real DIRECT execution.
    candidate = replace(candidate, original_claim_requests=(
        replace(candidate.original_claim_requests[0], family='DIRECT'),
        *candidate.original_claim_requests[1:]))
    claim = candidate.question_claims[0]
    operation = ProviderAttemptIdentity('PROVIDER-OP', 'PROVIDER-EVENT', 'LOGICAL-1',
        claim[2], claim[1], 'PROVIDER-1', 'MODEL-1', 'CONFIG-1', 'a'*64)
    read_store = FakeProviderReadStore()
    reader = ReadOnlyAccountingReconciler(identity=operation, store=read_store,
                                         max_identifier_characters=128)
    source = FakeApplicability(PaperProviderApplicability(
        candidate.plan.request, candidate.plan.approval_revision, (claim[0],)))
    class FixedOriginalPaperAccounting:
        def __init__(self, original):
            self.original = original
        def resolve_original_paper_accounting_intent(self):
            return self.original
    consumer = ProductionPaperAccounting(operations=(
        OriginalProviderOperation(claim[0], operation, reader),),
        max_identifier_characters=128, applicability_source=source,
        original_intent_source=FixedOriginalPaperAccounting(candidate))
    return consumer, candidate, source, read_store


def test_provider_receipt_correlation_with_original_f25_and_no_transport_reexecution():
    c, intent, _, store = _provider_accounting_fixture()
    assert c.reconcile(intent=intent).state is PaperAccountingState.REPORTED_RECORDED
    assert store.reads == 1


def test_provider_applicability_unavailable_is_unknown_before_any_accounting_read():
    c, intent, source, store = _provider_accounting_fixture()
    source.mode = 'FAIL'
    assert c.reconcile(intent=intent).state is PaperAccountingState.UNKNOWN
    assert store.reads == 0


def test_provider_accounting_mismatch_blocks_before_read():
    c, intent, source, store = _provider_accounting_fixture()
    damaged = replace(intent, question_claims=((
        intent.question_claims[0][0], 'FOREIGN-ORIGINAL', *intent.question_claims[0][2:]),
        *intent.question_claims[1:]))
    assert c.reconcile(intent=damaged).state is PaperAccountingState.CONFLICT
    assert store.reads == 0


def test_provider_wrong_physical_attempt_blocks_before_read():
    consumer, intent, source, store = _provider_accounting_fixture()
    damaged = replace(intent, question_claims=((
        intent.question_claims[0][0], intent.question_claims[0][1],
        'FOREIGN-PHYSICAL-ATTEMPT', *intent.question_claims[0][3:]),
        *intent.question_claims[1:]))
    assert consumer.reconcile(intent=damaged).state is PaperAccountingState.CONFLICT
    assert store.reads == 0


def test_missing_or_conflicting_provider_accounting_never_reports_recorded():
    for condition, expected in (('NOT_FOUND', PaperAccountingState.UNKNOWN),
                                ('CONFLICT', PaperAccountingState.CONFLICT),
                                ('THROW', PaperAccountingState.UNKNOWN),
                                ('FOREIGN', PaperAccountingState.UNKNOWN)):
        c, intent, source, store = _provider_accounting_fixture()
        store.mode = condition
        assert c.reconcile(intent=intent).state is expected
        assert store.reads == 1

class FixedAttemptOriginal:
    def __init__(self, record):
        self.record = record
    def resolve_original_paper_attempt(self):
        if self.record is None:
            raise RuntimeError('PRIVATE ORIGINAL RECORD UNAVAILABLE')
        return self.record


def test_original_f25_recovery_never_grants_retry_even_after_reserved_fact():
    from tests.integration.test_whole_paper_choice_execution import _setup_one
    from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
    from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
    from grading.integration.paper_retry_recovery import (
        ProductionPaperOriginalRecovery, OriginalPaperRecoveryState,
    )
    from grading.integration.attempt_authority import AttemptClaimRequest
    root, plan, _, _, _, store = _setup_one()
    request_source = KnownRequests()
    reader = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=request_source, max_identifier_characters=128, max_questions=10)
    record = reader.execute_and_capture(plan=plan)
    q = record.questions[0]
    assert q.original_f25_request is not None
    request_source.requests = {'Q1': q.original_f25_request}
    original = FixedAttemptOriginal(record)
    recovery = ProductionPaperOriginalRecovery(original_source=original,
        custody_reader=reader, max_identifier_characters=128, max_questions=10)
    before = store.claims
    result = recovery.reconcile()
    assert result.state is OriginalPaperRecoveryState.OBSERVED_RESERVED
    assert not result.authorizes_retry and not result.authorizes_publication
    assert store.claims == before and result.paper is record
    original.record = None
    assert recovery.reconcile().state is OriginalPaperRecoveryState.UNKNOWN
    assert store.claims == before


def test_cas_lost_reply_can_be_reconciled_from_original_durable_paper_source():
    svc, plan, physical, store, _ = setup_lifecycle()
    store.mode = 'CRASH'  # Actual backend may have persisted its paper-CAS.
    observed = svc.execute_first(plan=plan)
    assert observed.state is PaperLifecycleState.UNKNOWN and observed.cas is not None
    # This fixture's read-only backend independently reports COMMITTED.
    gate, _, _ = _gate(observed, store)
    before = (physical.claims, store.commits)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims, store.commits) == before
