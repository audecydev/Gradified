"""Independent whole-paper score commit review contract defects: pre-effect strictness and uncertainty."""
from dataclasses import replace
from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.whole_paper_cas import (
    ProductionWholePaperCAS, PaperCASState,
)
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from tests.integration.test_whole_paper_cas import setup, Store, OriginalSource, Issuer
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_academic_effect_preclaim import setup_bound
import pytest

POLICY = LegalGradingTransitionPolicy('TEST-F57', 1,
    ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))


def test_strict_cas_rejects_unbound_configuration_before_first_physical_f25_effect():
    root, plan, _, _, _, physical = _setup_two()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    with pytest.raises(ValueError, match='Strict paper CAS requires a bound'):
        ProductionWholePaperCAS(custody=custody, issuer=Issuer(),
            original_source=OriginalSource(), store=Store(), legal_policy=POLICY,
            max_identifier_characters=128, max_questions=10, require_academic_preclaim=True)
    assert physical.claims == 0


@pytest.mark.parametrize('malform', ('foreign_intent','wrong_edge'))
def test_issuer_malformed_after_possible_persistence_is_unknown_not_definite(malform):
    original, plan, _, store, physical = setup()
    class PersistThenMalformed(Issuer):
        def __init__(self):
            super().__init__()
            self.issued = []
        def identify_paper_transaction(self, *, intent):
            good = super().identify_paper_transaction(intent=intent)
            self.issued.append(good)
            if malform == 'foreign_intent':
                return replace(good, intent=replace(intent, question_claims=intent.question_claims[:1]))
            return replace(good, target_state=GradingJobState.COMPLETED)
    issuer = PersistThenMalformed()
    service = ProductionWholePaperCAS(custody=original._custody, issuer=issuer,
        original_source=OriginalSource(), store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    result = service.execute_and_commit(plan=plan)
    assert len(issuer.issued) == 1 and physical.claims == 2 and store.commits == 0
    assert result.state is PaperCASState.UNKNOWN and result.transaction is None
    assert result.receipt is None and not result.authorizes_retry


def test_callback_cannot_release_cas_lease_to_enter_nested_physical_execution():
    original, plan, _, _, physical = setup()
    class HostileStore(Store):
        def __init__(self):
            super().__init__(); self.nested = None; self.release_rejected = False
        def commit_whole_paper(self, *, transaction, custody):
            try:
                self.service._gate.release()
            except AttributeError:
                self.release_rejected = True
            try:
                self.nested = self.service.execute_and_commit(plan=plan)
            except ValueError:
                self.nested = 'DENIED'
            return super().commit_whole_paper(transaction=transaction, custody=custody)
    store = HostileStore()
    service = ProductionWholePaperCAS(custody=original._custody, issuer=Issuer(),
        original_source=OriginalSource(), store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    store.service = service
    result = service.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.COMMITTED
    assert store.release_rejected and store.nested == 'DENIED'
    assert physical.claims == 2 and store.commits == 1


def test_positive_bound_strict_paper_execution_still_claims_twice():
    root, plan, physical, backend = setup_bound()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    source=OriginalSource(); issuer=Issuer(source); store=Store()
    service=ProductionWholePaperCAS(custody=custody, issuer=issuer, original_source=source,
        store=store, legal_policy=POLICY, max_identifier_characters=128,
        max_questions=10, require_academic_preclaim=True)
    result=service.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.COMMITTED and result.academic_binding_verified
    assert physical.claims == 2 and len(backend.prepares)==2 and store.commits==1


def test_durable_source_reconciles_lost_issuer_transaction_only_under_fixed_origin():
    from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
    from grading.integration.whole_paper_cas import PaperCASReceipt, PaperCASRecovery, PaperCASDisposition
    from dataclasses import replace
    service, plan, _, store, _ = setup()
    completed = service.execute_and_commit(plan=plan)
    original = completed.transaction
    class BoundOriginal:
        def resolve_owned_original_paper_transaction(self):
            return original
    class ReadOnly:
        def __init__(self): self.reads=[]
        def reconcile_whole_paper(self, *, transaction):
            self.reads.append(transaction)
            return PaperCASRecovery(transaction, PaperCASDisposition.COMMITTED,
                PaperCASReceipt(transaction, 'ORIGINAL-RECEIPT', 'REV-NEW'))
    backend=ReadOnly()
    recovery=ProductionPaperCASDurableRecovery(original_source=BoundOriginal(),
        store=backend, legal_policy=POLICY, max_identifier_characters=128,
        max_questions=10)
    unknown=replace(completed, state=PaperCASState.UNKNOWN, transaction=None, receipt=None)
    assert recovery.reconcile(outcome=unknown) is PaperCASState.COMMITTED
    assert backend.reads == [original]
    backend.reads.clear()
    foreign=replace(unknown, custody=replace(unknown.custody,
        plan=replace(unknown.custody.plan, approval_revision='FOREIGN')))
    assert recovery.reconcile(outcome=foreign) is PaperCASState.UNKNOWN
    assert backend.reads == []


def test_academic_binding_reference_alone_never_allows_cross_question_claim_swap():
    from dataclasses import replace
    from grading.integration.academic_claim_binding import (
        AcademicallyBoundClaim, validate_bound_claim,
    )
    import pytest
    root, plan, _, backend=setup_bound()
    outcome=root.execute(plan=plan)
    assert outcome.state == 'COMPLETE'
    q1,q2=backend.bound_claims
    assert q1.intent.original_request.request_ref != q2.intent.original_request.request_ref
    # Qualified stores may define a shared paper-level binding_ref namespace;
    # authorization remains the COMPLETE request+academic intent, not its label.
    shared=replace(q2, binding_ref=q1.binding_ref)
    claim_q2=backend.claimed[q2.intent.original_request.request_ref]
    with pytest.raises(ValueError, match='grading-attempt claim not bound'):
        validate_bound_claim(AcademicallyBoundClaim(shared, claim_q2), q1, 128)
