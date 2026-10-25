"""pre-effect paper lifecycle real strict-paper execution with pre-claim legal operation transition and read-only regrade proof."""
from dataclasses import replace
from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS
from grading.integration.paper_lifecycle import (
    ProductionPaperLifecycle, PaperLifecyclePermission,
    PaperLifecycleKind, PaperLifecycleState,
)
from tests.integration.test_academic_effect_preclaim import setup_bound
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import Store, Issuer, OriginalSource

POLICY = LegalGradingTransitionPolicy('TEST-F57', 1, (
    (GradingJobState.QUEUED, GradingJobState.GRADING),
    (GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),
))


class Permissions:
    def __init__(self):
        self.mode = 'FIRST'; self.calls = 0; self.prior = None; self.custody = None
    def resolve_paper_execution_permission(self, *, plan):
        self.calls += 1
        if self.mode == 'UNAVAILABLE':
            raise RuntimeError('SYNTHETIC-AUTHORITY-FAULT')
        record = PaperLifecyclePermission(plan, PaperLifecycleKind.FIRST,
            'F57-FIRST-APPROVAL', POLICY.policy_id, POLICY.policy_version,
            GradingJobState.QUEUED, GradingJobState.GRADING)
        if self.mode == 'FOREIGN':
            return replace(record, plan=replace(plan, approval_revision='OTHER'))
        if self.mode == 'WRONG_EDGE':
            return replace(record, target_state=GradingJobState.COMPLETED)
        if self.mode == 'REGRADE':
            return replace(record, kind=PaperLifecycleKind.REGRADE,
                approval_ref='F57-REGRADE-APPROVAL', predecessor=self.prior,
                predecessor_custody=self.custody)
        return record


def setup_lifecycle(*, store_class=Store):
    root, plan, physical, backend = setup_bound()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    issuer_source=OriginalSource(); store=store_class()
    cas=ProductionWholePaperCAS(custody=custody, issuer=Issuer(issuer_source),
        original_source=issuer_source, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10,
        require_academic_preclaim=True)
    source=Permissions()
    service=ProductionPaperLifecycle(cas=cas, permission_source=source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    return service, plan, physical, store, source


def test_first_run_legal_permission_checked_before_two_genuine_f25_effects():
    svc, plan, physical, store, source=setup_lifecycle()
    result=svc.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert result.cas.academic_binding_verified and physical.claims == 2
    assert store.commits == 1 and source.calls == 1
    assert not result.authorizes_retry and not result.authorizes_publication


def test_missing_authority_unknown_before_any_physical_effect():
    svc, plan, physical, store, source=setup_lifecycle()
    source.mode='UNAVAILABLE'
    result=svc.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.UNKNOWN and result.cas is None
    assert physical.claims == 0 and store.commits == 0
    assert not result.authorizes_retry


def test_foreign_paper_authority_blocks_before_any_physical_effect():
    svc, plan, physical, store, source=setup_lifecycle()
    source.mode='FOREIGN'
    result=svc.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.PRE_EFFECT_BLOCKED
    assert physical.claims == 0 and store.commits == 0


def test_missing_f57_policy_edge_blocks_before_any_physical_effect():
    svc, plan, physical, store, source=setup_lifecycle()
    source.mode='WRONG_EDGE'
    result=svc.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.PRE_EFFECT_BLOCKED
    assert physical.claims == 0 and store.commits == 0


def test_actual_regrade_request_is_never_executed_by_first_run_api():
    svc, plan, physical, store, source=setup_lifecycle()
    source.mode='REGRADE'
    result=svc.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.PRE_EFFECT_BLOCKED
    assert physical.claims == 0 and store.commits == 0


def test_regrade_checks_original_predecessor_receipt_readonly_before_any_new_claim():
    svc, old_plan, physical, store, source=setup_lifecycle()
    old=svc.execute_first(plan=old_plan)
    assert old.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    source.mode='REGRADE'; source.prior=old.cas.transaction; source.custody=old.cas.custody
    new=replace(old_plan,
        request=replace(old_plan.request, grading_run_id='NEW-REVIEW-RUN'),
        questions=tuple(replace(q,
            request=replace(q.request, grading_run_id='NEW-REVIEW-RUN'))
            for q in old_plan.questions))
    prior_reads=store.reads; before=physical.claims
    result=svc.admit_regrade(plan=new)
    assert result.state is PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
    assert result.predecessor is old.cas.transaction
    assert store.reads == prior_reads+1 and physical.claims == before
    assert not result.authorizes_retry and not result.authorizes_publication


def test_regrade_same_run_or_wrong_subject_denied_before_backend_read():
    svc, old_plan, physical, store, source=setup_lifecycle()
    old=svc.execute_first(plan=old_plan)
    source.mode='REGRADE'; source.prior=old.cas.transaction; source.custody=old.cas.custody
    before=store.reads; claims=physical.claims
    # Even a real previously committed CAS does not authorize repeating its run.
    result=svc.admit_regrade(plan=old_plan)
    assert result.state is PaperLifecycleState.PRE_EFFECT_BLOCKED
    assert physical.claims == claims and store.reads == before


def test_unbound_c3_cas_refused_at_c4_install():
    from tests.integration.test_whole_paper_cas import setup
    old_cas, _, _, _, _ = setup()
    try:
        ProductionPaperLifecycle(cas=old_cas, permission_source=Permissions(),
            legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    except ValueError:
        pass
    else:
        raise AssertionError('paper lifecycle accepted a legacy unbound CAS execution path')


def test_audit_commit_lost_response_never_grants_retry_or_publishing():
    svc, plan, physical, store, _=setup_lifecycle()
    store.mode='CRASH'
    result=svc.execute_first(plan=plan)
    assert result.state is PaperLifecycleState.UNKNOWN and result.cas is not None
    assert store.commits == 1 and physical.claims == 2
    assert not result.authorizes_retry and not result.authorizes_publication


def test_regrade_original_audit_unavailable_never_starts_a_new_claim():
    class UnknownReadStore(Store):
        def reconcile_whole_paper(self, *, transaction):
            self.reads += 1
            raise RuntimeError('PRIVATE AUDIT SERVICE UNAVAILABLE')
    svc, old_plan, physical, store, source=setup_lifecycle(store_class=UnknownReadStore)
    old=svc.execute_first(plan=old_plan)
    assert old.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    source.mode='REGRADE';source.prior=old.cas.transaction;source.custody=old.cas.custody
    new=replace(old_plan,request=replace(old_plan.request, grading_run_id='NEW-RUN'),
        questions=tuple(replace(q,request=replace(q.request,grading_run_id='NEW-RUN'))
            for q in old_plan.questions))
    before=physical.claims
    decision=svc.admit_regrade(plan=new)
    assert decision.state is PaperLifecycleState.UNKNOWN and decision.predecessor is None
    assert physical.claims==before and store.commits==1
    assert not decision.authorizes_retry
