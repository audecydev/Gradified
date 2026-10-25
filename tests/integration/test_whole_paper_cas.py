"""paper execution integrity whole-paper score commit paper-scoped CAS: genuine two-question path and hostile post-effect replies."""
from dataclasses import replace

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import (
    PaperCASState, PaperCASDisposition, PaperCASDecision, PaperCASRecovery,
    PaperCASReceipt, PaperCASTransaction, ProductionWholePaperCAS,
)
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests


class OriginalSource:
    def __init__(self, original=None):
        self.original = original
        self.reads = 0
        self.mode = 'GOOD'
    def resolve_original_paper_transaction(self, *, plan, request_ref):
        self.reads += 1
        if self.mode == 'UNAVAILABLE':
            raise RuntimeError('PRIVATE-ORIGINAL-SOURCE')
        if self.mode == 'FOREIGN':
            return replace(self.original, result_ref='FOREIGN')
        return self.original


class Issuer:
    def __init__(self, original_source=None):
        self.calls = 0
        self.foreign = False
        self.original_source = original_source
    def identify_paper_transaction(self, *, intent):
        self.calls += 1
        transaction = PaperCASTransaction(intent, 'CAS-REQUEST', 'EVENT-PAPER',
            'RESULT-PAPER', 'LEDGER-ORIGINAL', GradingJobState.SCORING,
            GradingJobState.REVIEW_REQUIRED, 'TEST-F57', 1, 'F57-APPROVAL')
        if self.foreign:
            transaction = replace(transaction, intent=replace(intent,
                question_claims=intent.question_claims[:-1]))
        if self.original_source is not None:
            self.original_source.original = transaction
        return transaction


class Store:
    def __init__(self):
        self.commits = 0
        self.reads = 0
        self.mode = 'COMMITTED'
        self.last = None
    def commit_whole_paper(self, *, transaction, custody):
        self.commits += 1
        self.last = transaction
        if self.mode == 'CRASH':
            raise RuntimeError('backend might have committed')
        receipt = PaperCASReceipt(transaction, 'WHOLE-PAPER-COMMIT', 'LEDGER-NEW')
        if self.mode == 'FOREIGN':
            receipt = replace(receipt, transaction=replace(transaction, request_ref='WRONG'))
        if self.mode == 'CONFLICT':
            return PaperCASDecision(transaction, PaperCASDisposition.CONFLICT, None)
        if self.mode == 'CONTRADICT':
            return PaperCASDecision(transaction, PaperCASDisposition.CONFLICT, receipt)
        if self.mode == 'QUESTION':
            receipt = replace(receipt, transaction=replace(transaction,
                intent=replace(transaction.intent, question_claims=transaction.intent.question_claims[:1])))
        return PaperCASDecision(transaction, PaperCASDisposition.COMMITTED, receipt)
    def reconcile_whole_paper(self, *, transaction):
        self.reads += 1
        receipt = PaperCASReceipt(transaction, 'WHOLE-PAPER-COMMIT', 'LEDGER-NEW')
        return PaperCASRecovery(transaction, PaperCASDisposition.COMMITTED, receipt)


def setup():
    root, plan, _, _, _, physical_store = _setup_two()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    original_source = OriginalSource()
    issuer = Issuer(original_source)
    store = Store()
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    c3 = ProductionWholePaperCAS(custody=custody, issuer=issuer,
        original_source=original_source, store=store,
        legal_policy=policy, max_identifier_characters=128, max_questions=10)
    return c3, plan, issuer, store, physical_store


def test_positive_exact_two_question_cas_executed_and_one_real_paper_commit():
    c3, plan, issuer, store, physical = setup()
    result = c3.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.COMMITTED
    assert physical.claims == 2 and issuer.calls == 1 and store.commits == 1
    assert tuple(q[0] for q in result.transaction.intent.question_claims) == ('Q1','Q2')
    assert result.receipt.transaction == result.transaction
    assert not result.authorizes_publication and not result.authorizes_retry


def test_unknown_later_f25_claim_never_contacts_cas_or_issuer():
    c3, plan, issuer, store, physical = setup()
    physical.timeout_second = True
    result = c3.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.NOT_ELIGIBLE
    assert physical.claims == 2 and issuer.calls == 0 and store.commits == 0
    assert result.custody.outcome.result is None


def test_foreign_issued_paper_contract_rejected_before_cas_commit():
    c3, plan, issuer, store, physical = setup()
    issuer.foreign = True
    result = c3.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.UNKNOWN and issuer.calls == 1
    assert store.commits == 0 and physical.claims == 2


def test_backend_missing_ack_is_uncertain_not_clean_denial():
    c3, plan, _, store, _ = setup()
    store.mode = 'CRASH'
    result = c3.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.UNKNOWN and store.commits == 1
    assert result.transaction is not None and result.receipt is None
    assert not result.authorizes_retry
    assert c3.reconcile(outcome=result) is PaperCASState.COMMITTED
    assert store.reads == 1 and store.commits == 1


def test_foreign_and_one_question_receipts_not_paper_commit():
    for mode in ('FOREIGN', 'QUESTION', 'CONTRADICT'):
        c3, plan, _, store, physical = setup()
        store.mode = mode
        result = c3.execute_and_commit(plan=plan)
        assert result.state is PaperCASState.UNKNOWN and result.receipt is None
        assert store.commits == 1 and physical.claims == 2


def test_definite_cas_conflict_blocks_without_retry_or_publication():
    c3, plan, _, store, _ = setup()
    store.mode = 'CONFLICT'
    result = c3.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.BLOCKED
    assert not result.authorizes_retry and not result.authorizes_publication


def test_recovery_without_known_original_transaction_is_unknown_and_read_free():
    c3, plan, _, store, _ = setup()
    result = c3.execute_and_commit(plan=plan)
    assert c3.reconcile(outcome=replace(result, transaction=None)) is PaperCASState.UNKNOWN
    assert store.reads == 0


def test_captured_issuer_dispatch_is_not_overridden_by_late_method_assignment():
    c3, plan, issuer, store, physical = setup()
    issuer.identify_paper_transaction = lambda *, intent: replace(
        Issuer().identify_paper_transaction(intent=intent),
        target_state=GradingJobState.COMPLETED)
    # The issuer operation was captured at installation, so changing its
    # exposed method cannot replace the installed callable.
    result = c3.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.COMMITTED
    assert store.commits == 1


def test_invalid_state_edge_from_issuer_is_rejected_before_cas():
    class UnsupportedIssuer(Issuer):
        def identify_paper_transaction(self, *, intent):
            return replace(super().identify_paper_transaction(intent=intent),
                target_state=GradingJobState.COMPLETED)
    c3, plan, _, store, physical = setup()
    invalid = UnsupportedIssuer()
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    direct = ProductionWholePaperCAS(custody=c3._custody, issuer=invalid,
        original_source=OriginalSource(), store=store,
        legal_policy=policy, max_identifier_characters=128, max_questions=10)
    result = direct.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.UNKNOWN and store.commits == 0
    assert physical.claims == 2


def test_commit_callback_mutation_does_not_report_committed():
    c3, plan, issuer, _, _ = setup()
    class MutatingStore(Store):
        def commit_whole_paper(self, *, transaction, custody):
            self.commits += 1
            object.__setattr__(custody.plan, 'approval_revision', 'ALTERED')
            return PaperCASDecision(transaction, PaperCASDisposition.COMMITTED,
                PaperCASReceipt(transaction, 'ACK', 'NEW-LEDGER'))
    hostile = MutatingStore()
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    service = ProductionWholePaperCAS(custody=c3._custody, issuer=issuer,
        original_source=OriginalSource(), store=hostile,
        legal_policy=policy, max_identifier_characters=128, max_questions=10)
    result = service.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.UNKNOWN and result.receipt is None
    assert hostile.commits == 1 and not result.authorizes_publication


def test_backend_wrong_transaction_recovery_cannot_claim_commit():
    c3, plan, _, store, physical = setup()
    result = c3.execute_and_commit(plan=plan)
    class ForeignRecovery:
        def reconcile_whole_paper(self, *, transaction):
            return PaperCASRecovery(replace(transaction, result_ref='FOREIGN'),
                PaperCASDisposition.COMMITTED, PaperCASReceipt(transaction, 'ACK', 'NEW'))
        def commit_whole_paper(self, *, transaction, custody):
            raise AssertionError('read-only recovery must never commit')
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    malicious = ProductionWholePaperCAS(custody=c3._custody, issuer=Issuer(),
        original_source=OriginalSource(result.transaction), store=ForeignRecovery(), legal_policy=policy,
        max_identifier_characters=128, max_questions=10)
    assert malicious.reconcile(outcome=result) is PaperCASState.UNKNOWN
    assert physical.claims == 2


def test_backend_recovery_exception_cannot_claim_clean_absence():
    c3, plan, _, store, physical = setup()
    record = c3.execute_and_commit(plan=plan)
    def broken(*, transaction):
        raise RuntimeError('PRIVATE-STORE-DETAIL')
    object.__setattr__(c3, '_recover', broken)  # privileged fixture injection
    assert c3.reconcile(outcome=record) is PaperCASState.UNKNOWN
    assert store.commits == 1 and physical.claims == 2


def test_value_equal_backend_rehydrated_full_paper_receipt_admitted():
    c3, plan, _, _, _ = setup()
    class RehydratingStore(Store):
        def commit_whole_paper(self, *, transaction, custody):
            self.commits += 1
            separate_intent = replace(transaction.intent,
                issued=replace(transaction.intent.issued,
                    questions=tuple(replace(q) for q in transaction.intent.issued.questions)))
            separate = replace(transaction, intent=separate_intent)
            return PaperCASDecision(separate, PaperCASDisposition.COMMITTED,
                PaperCASReceipt(separate, 'ACK', 'LEDGER-NEW'))
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    rehydrated = ProductionWholePaperCAS(custody=c3._custody, issuer=Issuer(),
        original_source=OriginalSource(), store=RehydratingStore(), legal_policy=policy,
        max_identifier_characters=128, max_questions=10)
    assert rehydrated.execute_and_commit(plan=plan).state is PaperCASState.COMMITTED


def test_reentrant_commit_callback_does_not_trigger_second_claim_or_paper_cas():
    c3, plan, issuer, _, physical = setup()
    class ReenterStore(Store):
        def commit_whole_paper(self, *, transaction, custody):
            self.commits += 1
            import pytest
            with pytest.raises(ValueError, match='Nested paper CAS'):
                self.owner.execute_and_commit(plan=plan)
            return PaperCASDecision(transaction, PaperCASDisposition.COMMITTED,
                PaperCASReceipt(transaction, 'ACK', 'LEDGER-NEW'))
    store = ReenterStore()
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    owner = ProductionWholePaperCAS(custody=c3._custody, issuer=issuer,
        original_source=OriginalSource(), store=store, legal_policy=policy, max_identifier_characters=128, max_questions=10)
    store.owner = owner
    assert owner.execute_and_commit(plan=plan).state is PaperCASState.COMMITTED
    assert store.commits == 1 and physical.claims == 2


def test_substituted_caller_cas_transaction_never_selects_backend_read():
    c3, plan, issuer, store, physical = setup()
    outcome = c3.execute_and_commit(plan=plan)
    caller_forged = replace(outcome, transaction=replace(outcome.transaction,
        request_ref='CAS-FOREIGN-REQUEST'))
    assert c3.reconcile(outcome=caller_forged) is PaperCASState.UNKNOWN
    assert store.reads == 0 and store.commits == 1 and physical.claims == 2
    assert issuer.original_source.reads == 0


def test_original_cas_request_source_foreign_fact_blocks_backend_read():
    c3, plan, issuer, store, _ = setup()
    outcome = c3.execute_and_commit(plan=plan)
    issuer.original_source.mode = 'FOREIGN'
    assert c3.reconcile(outcome=outcome) is PaperCASState.BLOCKED
    assert store.reads == 0


def test_original_cas_request_lookup_failure_remains_unknown_no_backend_read():
    c3, plan, issuer, store, _ = setup()
    outcome = c3.execute_and_commit(plan=plan)
    issuer.original_source.mode = 'UNAVAILABLE'
    assert c3.reconcile(outcome=outcome) is PaperCASState.UNKNOWN
    assert store.reads == 0 and store.commits == 1


def test_absent_durable_cas_origin_fails_closed_after_local_commit():
    c3, plan, issuer, store, _ = setup()
    outcome = c3.execute_and_commit(plan=plan)
    issuer.original_source.original = None  # simulated missing durable source after process loss
    assert c3.reconcile(outcome=outcome) is PaperCASState.UNKNOWN
    assert store.reads == 0


def test_reentrant_read_only_recovery_does_not_duplicate_backend_reads():
    c3, plan, issuer, store, physical = setup()
    class ReenterOriginal(OriginalSource):
        def resolve_original_paper_transaction(self, *, plan, request_ref):
            import pytest
            with pytest.raises(ValueError, match='Nested paper CAS'):
                self.owner.reconcile(outcome=self.outcome)
            return self.original
    source = ReenterOriginal()
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    service = ProductionWholePaperCAS(custody=c3._custody, issuer=Issuer(source),
        original_source=source, store=store, legal_policy=policy,
        max_identifier_characters=128, max_questions=10)
    source.owner = service
    source.outcome = service.execute_and_commit(plan=plan)
    assert source.outcome.state is PaperCASState.COMMITTED
    assert service.reconcile(outcome=source.outcome) is PaperCASState.COMMITTED
    assert store.reads == 1 and store.commits == 1 and physical.claims == 2
