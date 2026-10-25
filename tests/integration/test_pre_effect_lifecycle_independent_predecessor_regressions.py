"""Independent pre-effect paper lifecycle adversarial lifecycle/receipt and identity tests.

Runs against the submitted candidate; never alters source or protected Git.
"""
from dataclasses import replace

from grading.integration.paper_lifecycle import PaperLifecycleState
from grading.integration.whole_paper_cas import (
    PaperCASRecovery, PaperCASDisposition, PaperCASReceipt,
)
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle
from tests.integration.test_whole_paper_cas import Store


def _new_plan(old, **changes):
    update = {'grading_run_id': 'OTHER-REVIEW-RUN', **changes}
    return replace(old,
        request=replace(old.request, **update),
        questions=tuple(replace(q, request=replace(q.request, **update)) for q in old.questions))


def _approved_regrade(store_class=Store):
    service, old_plan, physical, backend, source = setup_lifecycle(store_class=store_class)
    first = service.execute_first(plan=old_plan)
    assert first.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    source.mode = 'REGRADE'
    source.prior = first.cas.transaction
    source.custody = first.cas.custody
    return service, old_plan, physical, backend, source


class FalseOriginal:
    """Foreign backend datum asserts equality with arbitrary original transaction."""
    def __eq__(self, other):
        return True
    def __ne__(self, other):
        return False


class ForeignTransactionStore(Store):
    def reconcile_whole_paper(self, *, transaction):
        self.reads += 1
        return PaperCASRecovery(FalseOriginal(), PaperCASDisposition.COMMITTED,
            PaperCASReceipt(transaction, 'AUTHENTIC-RECEIPT', 'REVISION-NEXT'))


class WrongRecordStore(Store):
    def reconcile_whole_paper(self, *, transaction):
        self.reads += 1
        return PaperCASRecovery(replace(transaction, result_ref='FOREIGN-RESULT'),
            PaperCASDisposition.COMMITTED,
            PaperCASReceipt(transaction, 'AUTHENTIC-RECEIPT', 'REVISION-NEXT'))


def test_foreign_equal_to_everything_transaction_cannot_verify_predecessor():
    service, plan, physical, backend, _ = _approved_regrade(ForeignTransactionStore)
    prior_claims = physical.claims
    outcome = service.admit_regrade(plan=_new_plan(plan))
    assert outcome.state is not PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
    assert physical.claims == prior_claims
    assert backend.reads == 1


def test_typed_foreign_transaction_is_rejected_control():
    service, plan, physical, backend, _ = _approved_regrade(WrongRecordStore)
    outcome = service.admit_regrade(plan=_new_plan(plan))
    assert outcome.state is not PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
    assert backend.reads == 1


def test_authentic_predecessor_recovers_readonly_control():
    service, plan, physical, backend, _ = _approved_regrade()
    prior_claims, prior_commits = physical.claims, backend.commits
    outcome = service.admit_regrade(plan=_new_plan(plan))
    assert outcome.state is PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
    assert physical.claims == prior_claims and backend.commits == prior_commits
    assert outcome.authorizes_retry is False and outcome.authorizes_publication is False


def test_cross_session_predecessor_is_not_sufficient_for_regrade_lineage():
    service, plan, physical, backend, _ = _approved_regrade()
    prior_claims = physical.claims
    outcome = service.admit_regrade(plan=_new_plan(plan, session_ref='OTHER-SESSION'))
    assert outcome.state is not PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
    assert physical.claims == prior_claims


def test_cross_tenant_lineage_rejected_control():
    service, plan, physical, backend, _ = _approved_regrade()
    outcome = service.admit_regrade(plan=_new_plan(plan, tenant_ref='FOREIGN-TENANT'))
    assert outcome.state is PaperLifecycleState.PRE_EFFECT_BLOCKED
    assert physical.claims == 2

class NestedFalseOriginalStore(Store):
    """Exact PaperCASTransaction wrapper, but invalid primitive ref defines equality."""
    def reconcile_whole_paper(self, *, transaction):
        self.reads += 1
        return PaperCASRecovery(replace(transaction, result_ref=FalseOriginal()),
            PaperCASDisposition.COMMITTED,
            PaperCASReceipt(transaction, 'AUTHENTIC-RECEIPT', 'REVISION-NEXT'))


def test_exact_transaction_with_foreign_equal_field_must_not_verify_lineage():
    service, plan, physical, backend, _ = _approved_regrade(NestedFalseOriginalStore)
    outcome = service.admit_regrade(plan=_new_plan(plan))
    assert outcome.state is not PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
    assert backend.reads == 1 and physical.claims == 2
