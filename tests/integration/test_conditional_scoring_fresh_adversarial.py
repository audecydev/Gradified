"""whole-paper score commit exact original CAS and academic-bound physical claim read-only authority failure seams."""
from dataclasses import replace
from threading import Thread
from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.whole_paper_cas import (
    ProductionWholePaperCAS, PaperCASState, PaperCASDecision,
    PaperCASReceipt, PaperCASDisposition,
)
from grading.integration.academic_claim_binding import (
    AcademicPreclaimState, ProductionPaperAcademicBindingRecovery,
)
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from tests.integration.test_whole_paper_cas import setup, Issuer, OriginalSource, Store
from tests.integration.test_academic_effect_preclaim import setup_bound, QualifiedShapeAcademicBackend
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests

POLICY = LegalGradingTransitionPolicy('TEST-F57', 1,
    ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))


class ManyOriginals(OriginalSource):
    def __init__(self):
        super().__init__()
        self.records = {}
        self.lookups = []
    def resolve_original_paper_transaction(self, *, plan, request_ref):
        self.lookups.append(request_ref)
        return self.records[request_ref]


class MultipleCommits(Store):
    def __init__(self):
        super().__init__()
        self.reads_by_ref = []
    def reconcile_whole_paper(self, *, transaction):
        self.reads_by_ref.append(transaction.request_ref)
        return super().reconcile_whole_paper(transaction=transaction)


def test_two_valid_commits_cannot_redirect_local_original_recovery():
    parent, plan, _, _, physical = setup()
    source, backend = ManyOriginals(), MultipleCommits()
    service = ProductionWholePaperCAS(custody=parent._custody, issuer=Issuer(source),
        original_source=source, store=backend, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    actual = service.execute_and_commit(plan=plan)
    assert actual.state is PaperCASState.COMMITTED
    foreign = replace(actual.transaction, request_ref='CAS-OTHER',
                      event_ref='EVENT-OTHER', result_ref='RESULT-OTHER')
    source.records = {'CAS-REQUEST': actual.transaction, 'CAS-OTHER': foreign}
    # Real separate operation is recorded, not a made-up receipt.
    backend.commit_whole_paper(transaction=foreign, custody=actual.custody)
    suspicious = replace(actual, transaction=foreign)
    assert service.reconcile(outcome=suspicious) is not PaperCASState.COMMITTED
    assert backend.reads_by_ref == [] and source.lookups == []
    assert service.reconcile(outcome=actual) is PaperCASState.COMMITTED
    assert backend.reads_by_ref == ['CAS-REQUEST']


def test_caller_cannot_rehydrate_outcome_as_original_after_restart():
    service, plan, _, store, _ = setup()
    actual = service.execute_and_commit(plan=plan)
    recreated = replace(actual)
    assert service.reconcile(outcome=recreated) is PaperCASState.UNKNOWN
    assert store.reads == 0


def test_issuer_failure_is_uncertain_not_definitive_denial():
    service, plan, _, store, physical = setup()
    class FailingIssuer:
        def identify_paper_transaction(self, *, intent):
            raise RuntimeError('durable issuer event persisted, reply lost')
    candidate = ProductionWholePaperCAS(custody=service._custody,
        issuer=FailingIssuer(), original_source=OriginalSource(),
        store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    result = candidate.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.UNKNOWN
    assert result.transaction is None and not result.authorizes_retry
    assert store.commits == 0 and physical.claims == 2


def test_cross_thread_reentry_rejected_before_second_physical_effect():
    service, plan, _, _, physical = setup()
    outcomes = []
    class ConcurrentStore(Store):
        def commit_whole_paper(self, *, transaction, custody):
            def competing():
                try:
                    self.owner.execute_and_commit(plan=plan)
                except ValueError as exc:
                    outcomes.append(str(exc))
            t = Thread(target=competing)
            t.start(); t.join(timeout=3)
            assert not t.is_alive()
            return super().commit_whole_paper(transaction=transaction, custody=custody)
    store = ConcurrentStore()
    owner = ProductionWholePaperCAS(custody=service._custody, issuer=Issuer(),
        original_source=OriginalSource(), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    store.owner = owner
    result = owner.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.COMMITTED
    assert outcomes and 'Nested paper CAS' in outcomes[0]
    assert store.commits == 1 and physical.claims == 2


def test_readonly_academic_recovery_is_bound_and_does_not_claim_again():
    root, plan, physical, backend = setup_bound()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    record = custody.execute_and_capture(plan=plan)
    recovery = ProductionPaperAcademicBindingRecovery(store=backend,
        max_identifier_characters=128, max_questions=10)
    before = physical.claims
    states = recovery.reconcile(custody=record)
    assert [s.state for s in states] == [AcademicPreclaimState.PREPARED]*2
    assert len(backend.recovery_reads) == 2 and physical.claims == before
    assert not any(s.authorizes_retry or s.authorizes_publication for s in states)


def test_readonly_academic_recovery_lost_reply_remains_indeterminate():
    root, plan, physical, backend = setup_bound()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    record = custody.execute_and_capture(plan=plan)
    class UnavailableBackend(QualifiedShapeAcademicBackend):
        def reconcile_original_binding(self, *, intent):
            raise RuntimeError('private backend failure')
    recovery = ProductionPaperAcademicBindingRecovery(store=UnavailableBackend(physical),
        max_identifier_characters=128, max_questions=10)
    states = recovery.reconcile(custody=record)
    assert all(s.state is AcademicPreclaimState.INDETERMINATE for s in states)
    assert physical.claims == 2


def test_durable_qualified_original_source_enables_restart_without_caller_selection():
    from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
    service, plan, _, _, physical = setup()
    outcome = service.execute_and_commit(plan=plan)
    original = outcome.transaction
    alternative = replace(original, request_ref='CAS-SUBSTITUTE')
    class OwnedOriginal:
        def __init__(self, fixed):
            self.fixed = fixed
            self.calls = 0
        def resolve_owned_original_paper_transaction(self):
            self.calls += 1
            return self.fixed
    source = OwnedOriginal(original)
    store = MultipleCommits()
    # A second service can safely recover ONLY because this original-operation
    # source was bound to the authenticated execution, not by the outcome ref.
    recovery = ProductionPaperCASDurableRecovery(original_source=source,
        store=store, legal_policy=POLICY, max_identifier_characters=128,
        max_questions=10)
    assert recovery.reconcile(outcome=replace(outcome)) is PaperCASState.COMMITTED
    assert store.reads_by_ref == ['CAS-REQUEST']
    # Exercise fixed-original source selection rather than the independently
    # detectable local receipt/transaction contradiction. A caller with a
    # foreign transaction and no retained receipt still must not choose a
    # different backend recovery target.
    altered = replace(outcome, transaction=alternative, receipt=None)
    assert recovery.reconcile(outcome=altered) is not PaperCASState.COMMITTED
    assert store.reads_by_ref == ['CAS-REQUEST']
    assert source.calls == 2 and physical.claims == 2


def test_durable_source_missing_original_never_reads_backend():
    from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
    service, plan, _, _, _ = setup()
    outcome = service.execute_and_commit(plan=plan)
    class Missing:
        def resolve_owned_original_paper_transaction(self):
            raise RuntimeError('Original durable ownership is unknown')
    store = MultipleCommits()
    recovery = ProductionPaperCASDurableRecovery(original_source=Missing(),
        store=store, legal_policy=POLICY, max_identifier_characters=128,
        max_questions=10)
    assert recovery.reconcile(outcome=outcome) is PaperCASState.UNKNOWN
    assert store.reads_by_ref == []
