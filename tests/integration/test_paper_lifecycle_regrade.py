"""Effectful effectful regrade lifecycle regrade: real two-question claims under qualified fixtures only."""
from dataclasses import replace

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS, PaperCASTransaction
from grading.integration.paper_lifecycle import (
    ProductionPaperLifecycle, PaperLifecycleKind, PaperLifecycleState,
)
from tests.integration.test_paper_lifecycle_pre_effect import Permissions
from tests.integration.test_academic_effect_preclaim import (
    QualifiedShapeAcademicBackend, PerQuestionF25Issuer, setup_bound,
)
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import Store, Issuer, OriginalSource
import tests.integration.test_trusted_preparation as trusted_fixture

POLICY = LegalGradingTransitionPolicy('TEST-F57', 1, (
    (GradingJobState.QUEUED, GradingJobState.GRADING),
    (GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),
))


class RegradeF25Issuer(PerQuestionF25Issuer):
    def __init__(self, prior, approval):
        super().__init__()
        self.prior = prior
        self.approval = approval
        self.foreign = False
        self.reuse_request = False
    def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                     implementation_ref, eligibility_policy_id,
                                     eligibility_policy_version):
        request = super().identify_reservation_request(
            scope=scope, family=family, runtime_id=runtime_id,
            runtime_version=runtime_version, implementation_ref=implementation_ref,
            eligibility_policy_id=eligibility_policy_id,
            eligibility_policy_version=eligibility_policy_version)
        return replace(request, request_ref=('REQUEST-' if self.reuse_request else 'REGR-REQUEST-')+request.scope.question_id, predecessor_result_ref=(
            'FOREIGN-PREDECESSOR' if self.foreign else self.prior),
            regrade_approval_ref=self.approval)


class NewRunCASIssuer(Issuer):
    def __init__(self, source):
        super().__init__(source)
        self.reuse_transaction = False
    def identify_paper_transaction(self, *, intent):
        old = super().identify_paper_transaction(intent=intent)
        if self.reuse_transaction:
            return old
        return replace(old, request_ref='CAS-REGRADE-REQUEST',
                       event_ref='CAS-REGRADE-EVENT', result_ref='CAS-REGRADE-RESULT')


def _renamed_bound():
    from grading.integration.evaluation_binding import bind_question_evaluation_inputs
    original = _saved_prepared()
    return bind_question_evaluation_inputs(
        context=replace(original.context, grading_run_id='NEW-REVIEW-RUN'),
        admitted_evidence=original.admitted_evidence,
        paper_authority=original.paper_authority,
        question_authority=original.question_authority,
    )

_saved_prepared = trusted_fixture._prepared


def setup_regrade(monkeypatch, *, store_class=Store):
    old_root, old_plan, _, old_physical = setup_bound()
    store = store_class()
    old_source=OriginalSource()
    old_custody = ProductionPaperAttemptCustody(executor=old_root, attempts=old_root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    old_cas=ProductionWholePaperCAS(custody=old_custody, issuer=Issuer(old_source),
        original_source=old_source, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10, require_academic_preclaim=True)
    old = old_cas.execute_and_commit(plan=old_plan)
    assert old.transaction is not None and old.receipt is not None

    with monkeypatch.context() as m:
        m.setattr(trusted_fixture, '_prepared', _renamed_bound)
        original, plan, _, _, _, physical = _setup_two()
    # Exact declared backend method, new physical identities per run.
    from grading.integration.attempt_authority import AttemptClaim, AttemptClaimDisposition
    class NewPhysicalStore(type(physical)):
        reuse_physical = False
        def claim_fresh_attempt(self, *, request):
            claim = super().claim_fresh_attempt(request=request)
            if claim.disposition is AttemptClaimDisposition.FRESH:
                distinct = replace(claim.reservation,
                    attempt_id=('ATT-' if self.reuse_physical else 'REGR-ATT-')+request.scope.question_id,
                    reservation_ref=('RES-' if self.reuse_physical else 'REGR-RES-')+request.scope.question_id)
                self.last_reservation = distinct
                return AttemptClaim(claim.request, claim.disposition, distinct)
            return claim
    physical = NewPhysicalStore()
    issuer = RegradeF25Issuer(old.transaction.result_ref, 'F57-REGRADE-APPROVAL')
    backend = QualifiedShapeAcademicBackend(physical)
    allocator = ClaimedAttemptAllocator(issuer=issuer, store=physical,
        academic_store=backend, academic_max_questions=10, max_identifier_characters=128)
    root = ProductionWholePaperChoiceExecutor(contact=original._contact,
        correlation=original._correlation, handoff=original._handoff, attempts=allocator,
        max_identifier_characters=128, max_questions=10)
    custody = ProductionPaperAttemptCustody(executor=root, attempts=allocator,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    source = OriginalSource()
    cas = ProductionWholePaperCAS(custody=custody, issuer=NewRunCASIssuer(source),
        original_source=source, store=store, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10, require_academic_preclaim=True)
    permission = Permissions()
    permission.mode = 'REGRADE'
    permission.prior = old.transaction
    permission.custody = old.custody
    service = ProductionPaperLifecycle(cas=cas, permission_source=permission,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    return service,plan,physical,store,issuer,backend,old


def test_real_regrade_two_new_bound_f25_attempts_distinct_from_old(monkeypatch):
    svc, plan, physical, store, issuer, backend, old = setup_regrade(monkeypatch)
    result = svc.execute_regrade(plan=plan)
    assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED, (result.state, result.cas)
    assert result.kind is PaperLifecycleKind.REGRADE
    assert result.predecessor is old.transaction
    assert physical.claims == 2 and store.commits == 2
    assert len(backend.prepares) == 2
    assert all(q.original_f25_request.predecessor_result_ref == old.transaction.result_ref
               and q.original_f25_request.regrade_approval_ref == 'F57-REGRADE-APPROVAL'
               for q in result.cas.custody.questions)
    assert result.cas.transaction.request_ref != old.transaction.request_ref
    assert result.cas.transaction.result_ref != old.transaction.result_ref
    assert not result.authorizes_retry and not result.authorizes_publication


def test_foreign_f25_predecessor_denied_before_durable_prepare_or_physical_claim(monkeypatch):
    svc, plan, physical, store, issuer, backend, _ = setup_regrade(monkeypatch)
    issuer.foreign=True
    result=svc.execute_regrade(plan=plan)
    assert result.state in (PaperLifecycleState.CAS_BLOCKED, PaperLifecycleState.UNKNOWN)
    assert physical.claims == 0 and backend.prepares == [] and store.commits == 1


def test_unknown_predecessor_receipt_never_authorizes_new_f25(monkeypatch):
    class UnknownReadStore(Store):
        def __init__(self):
            super().__init__()
            self.read_unknown = False
        def reconcile_whole_paper(self, *, transaction):
            if self.read_unknown:
                self.reads += 1
                raise RuntimeError('PRIVATE PREDECESSOR BACKEND UNAVAILABLE')
            return super().reconcile_whole_paper(transaction=transaction)
    svc,plan,physical,store,issuer,backend,_ = setup_regrade(
        monkeypatch, store_class=UnknownReadStore)
    store.read_unknown=True
    result=svc.execute_regrade(plan=plan)
    assert result.state is PaperLifecycleState.UNKNOWN
    assert physical.claims==0 and store.commits==1 and backend.prepares==[]
    assert not result.authorizes_retry and not result.authorizes_publication


def test_cross_session_regrade_unapproved_denied_before_backend_read(monkeypatch):
    svc,plan,physical,store,issuer,backend,_=setup_regrade(monkeypatch)
    candidate=replace(plan, request=replace(plan.request,session_ref='FOREIGN-SESSION'),
                      questions=tuple(replace(q, request=replace(q.request,session_ref='FOREIGN-SESSION'))
                                      for q in plan.questions))
    result=svc.execute_regrade(plan=candidate)
    assert result.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and store.commits==1


def test_lost_second_bound_regrade_response_retains_true_partial_custody(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    backend.mode='LOST_BOUND'
    outcome=svc.execute_regrade(plan=plan)
    assert outcome.state is PaperLifecycleState.UNKNOWN and outcome.cas is not None
    assert outcome.cas.state is not None and outcome.cas.custody.outcome.issued_paper is not None
    assert physical.claims==1 and store.commits==1
    q=outcome.cas.custody.questions[0]
    assert q.original_f25_request.predecessor_result_ref == old.transaction.result_ref
    assert q.academic_preparation is not None
    assert not outcome.authorizes_retry and not outcome.authorizes_publication


def test_original_paper_audit_recovery_is_readonly_and_never_publishes(monkeypatch):
    from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
    from grading.integration.paper_lifecycle import PaperLifecycleAuditState
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    observation=svc.execute_regrade(plan=plan)
    assert observation.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    class FixedOriginal:
        def resolve_owned_original_paper_transaction(self):
            return observation.cas.transaction
    recovery=ProductionPaperCASDurableRecovery(original_source=FixedOriginal(),
        store=store, legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    wrapped=ProductionPaperLifecycle(cas=svc._cas,
        permission_source=Permissions(), legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=store.reads; claims=physical.claims; commits=store.commits
    fact=wrapped.reconcile_audit(observation=observation)
    assert fact.state is PaperLifecycleAuditState.REPORTED_COMMITTED
    assert store.reads == before+1 and physical.claims == claims and store.commits==commits
    assert not fact.authorizes_retry and not fact.authorizes_publication


def test_foreign_audit_original_never_reads_backend_or_creates_retry(monkeypatch):
    from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
    from grading.integration.paper_lifecycle import PaperLifecycleAuditState
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    observed=svc.execute_regrade(plan=plan)
    class ForeignOriginal:
        def resolve_owned_original_paper_transaction(self):
            return old.transaction
    recovery=ProductionPaperCASDurableRecovery(original_source=ForeignOriginal(),
        store=store, legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    wrapped=ProductionPaperLifecycle(cas=svc._cas,
        permission_source=Permissions(), legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,audit_recovery=recovery)
    before=store.reads
    fact=wrapped.reconcile_audit(observation=observed)
    assert fact.state is PaperLifecycleAuditState.UNKNOWN
    assert store.reads == before
    assert not fact.authorizes_retry and not fact.authorizes_publication


def test_predecessor_f25_stable_request_reused_is_denied_before_claim(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    issuer.reuse_request=True
    result=svc.execute_regrade(plan=plan)
    assert result.state in (PaperLifecycleState.CAS_BLOCKED, PaperLifecycleState.UNKNOWN)
    assert physical.claims == 0 and backend.prepares == [] and store.commits == 1


def test_regrade_reused_physical_identity_cannot_commit_paper(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    physical.reuse_physical=True
    result=svc.execute_regrade(plan=plan)
    assert result.state is PaperLifecycleState.UNKNOWN
    assert result.cas is not None and result.cas.state.name == 'UNKNOWN'
    assert physical.claims==2 and store.commits==1
    assert not result.authorizes_retry and not result.authorizes_publication


def test_regrade_cas_cannot_reuse_predecessor_operation_refs(monkeypatch):
    svc,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    svc._cas._issue.__self__.reuse_transaction=True
    result=svc.execute_regrade(plan=plan)
    assert result.state is PaperLifecycleState.UNKNOWN
    assert physical.claims==2 and store.commits==1
    assert result.cas is not None and result.cas.state.name == 'UNKNOWN'


def test_mutated_original_plan_during_authorization_never_starts_f25():
    svc,plan,physical,store,_ = __import__(
        'tests.integration.test_paper_lifecycle_pre_effect', fromlist=['setup_lifecycle']).setup_lifecycle()
    class MutatingPermissions(Permissions):
        def __init__(self, supplied):
            super().__init__()
            self.supplied=supplied
        def resolve_paper_execution_permission(self, *, plan):
            original = super().resolve_paper_execution_permission(plan=plan)
            object.__setattr__(self.supplied,'approval_revision','MUTATED-DURING-PERMISSION')
            return original
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    replacement=ProductionPaperLifecycle(cas=svc._cas,
        permission_source=MutatingPermissions(plan),legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10)
    outcome=replacement.execute_first(plan=plan)
    assert outcome.state is PaperLifecycleState.PRE_EFFECT_BLOCKED
    assert physical.claims == 0 and store.commits == 0
