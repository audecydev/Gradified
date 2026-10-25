"""The actual CHOICE/physical attempt claim consumer must use a qualified joint effect owner.

These tests prove the installed synchronous *routing* contract, not real-world
identity authenticity or cross-process atomicity of a deployed provider.
"""
from threading import Lock

from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.academic_claim_binding import AcademicallyBoundClaim
from grading.integration.joint_effect_authority import (
    ConditionalCASResponse, ConditionalEffectClaimResponse, EffectDecision,
    JointEffectAdmission, GradingEffectKind,
)
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from tests.integration.test_academic_effect_preclaim import (
    setup_bound, PerQuestionF25Issuer, QualifiedShapeAcademicBackend,
)


class ReadOnlyAcademicPort:
    """Installed positive FIRST owner exposes no legacy physical method."""
    def __init__(self, backend):
        self.backend = backend

    def prepare_original_binding(self, *, intent):
        return self.backend.prepare_original_binding(intent=intent)

    def reconcile_original_binding(self, *, intent):
        return self.backend.reconcile_original_binding(intent=intent)

    def reconcile_bound_attempt(self, *, request):
        return self.backend.reconcile_bound_attempt(request=request)


class ReadOnlyF25Port:
    def __init__(self, store):
        self.store = store

    def reconcile_reservation(self, *, request):
        return self.store.reconcile_reservation(request=request)


class ReadOnlyCASPort:
    def __init__(self, store):
        self.store = store

    def reconcile_whole_paper(self, *, transaction):
        return self.store.reconcile_whole_paper(transaction=transaction)


class AtomicConditionalAcademicFixture:
    """Explicit test double; atomic compare is a simulated backend obligation."""
    def __init__(self, backend, approval_revision, runtime_approval):
        self.lock = Lock()
        self.backend = backend
        self.approval_revision = approval_revision
        self.runtime_approval = runtime_approval
        self.claim_contacts = 0
        self.commits = 0
        self.lost_ack = False
        self.revoke_after_first = False
        self.f57_source = None

    def claim_if_current(self, *, request):
        with self.lock:
            assert request.operation is GradingEffectKind.FIRST_F25
            self.claim_contacts += 1
            from grading.integration.paper_lifecycle import PaperLifecyclePermission, PaperLifecycleKind
            purpose = request.first_permission
            if (type(purpose) is not PaperLifecyclePermission
                    or purpose.kind is not PaperLifecycleKind.FIRST
                    or purpose.approval_ref != 'F57-FIRST-APPROVAL'
                    or self.f57_source is None or self.f57_source.mode != 'FIRST'
                    or request.authority.academic.issued_paper.approval_revision != self.approval_revision
                    or request.authority.runtime.approval_ref != self.runtime_approval):
                return ConditionalEffectClaimResponse(request, EffectDecision.REJECTED)
            bound = self.backend.claim_bound_fresh(preparation=request.preparation)
            if self.revoke_after_first:
                self.approval_revision = 'revoked-after-first'
            if self.lost_ack:
                raise RuntimeError('lost grading-attempt response after physical claim')
            return ConditionalEffectClaimResponse(request, EffectDecision.COMMITTED, bound)

    def commit_if_current(self, *, request):
        self.commits += 1
        raise AssertionError('FIRST-only allocator may not score or commit CAS')


def connected_first():
    old, plan, physical, backend = setup_bound()
    relation = old._correlation.preflight(plan=plan).issuer_relation
    _, snap, _ = old._prepared(plan.questions[0].request, plan, relation.questions[0])
    conditional = AtomicConditionalAcademicFixture(
        backend, relation.approval_revision, snap[7].approval_ref)
    allocator = ClaimedAttemptAllocator(
        issuer=PerQuestionF25Issuer(), store=ReadOnlyF25Port(physical),
        academic_store=ReadOnlyAcademicPort(backend), academic_max_questions=10,
        max_identifier_characters=128,
        joint_effect=JointEffectAdmission(owner=conditional),
    )
    engine = ProductionWholePaperChoiceExecutor(
        contact=old._contact, correlation=old._correlation,
        handoff=old._handoff, attempts=allocator,
        max_identifier_characters=128, max_questions=10,
    )
    return engine, plan, physical, backend, conditional


def execute_authorized_first(engine, plan, conditional):
    from tests.integration.test_paper_lifecycle_pre_effect import Permissions
    issuer = Permissions()
    conditional.f57_source = issuer
    permission = issuer.resolve_paper_execution_permission(plan=plan)
    token = engine._attempts.begin_authorized_first(plan=plan, permission=permission)
    try:
        return engine.execute(plan=plan)
    finally:
        engine._attempts.finish_authorized_first(token=token)


def test_actual_first_two_question_positive_uses_only_conditional_effect_port():
    engine, plan, physical, backend, conditional = connected_first()
    result = execute_authorized_first(engine, plan, conditional)
    assert result.state == 'COMPLETE', result.state
    assert len(result.completed) == 2
    assert physical.claims == 2
    assert conditional.claim_contacts == 2
    assert len(backend.bound_claims) == 2
    assert conditional.commits == 0


def test_revocation_before_actual_first_effect_denies_without_physical_claim():
    engine, plan, physical, backend, conditional = connected_first()
    conditional.runtime_approval = 'revoked'
    result = execute_authorized_first(engine, plan, conditional)
    assert result.result is None and result.state != 'COMPLETE'
    assert physical.claims == 0 and conditional.claim_contacts == 1
    assert len(backend.bound_claims) == 0


def test_revocation_between_questions_preserves_one_real_effect_but_no_score():
    engine, plan, physical, backend, conditional = connected_first()
    conditional.revoke_after_first = True
    result = execute_authorized_first(engine, plan, conditional)
    assert result.result is None and result.state != 'COMPLETE'
    assert physical.claims == 1 and conditional.claim_contacts == 2
    assert len(backend.bound_claims) == 1


def test_lost_effect_ack_does_not_grade_or_repeat_physical_claim():
    engine, plan, physical, backend, conditional = connected_first()
    conditional.lost_ack = True
    result = execute_authorized_first(engine, plan, conditional)
    assert result.state == 'INDETERMINATE'
    assert result.result is None
    assert physical.claims == 1 and conditional.claim_contacts == 1
    assert len(backend.bound_claims) == 1

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import (
    ProductionWholePaperCAS, PaperCASDecision, PaperCASDisposition, PaperCASState,
)
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import Issuer, OriginalSource, Store


class AtomicConditionalCASFixture:
    """In-memory atomic model, NOT a qualified deployment adapter."""
    def __init__(self, store, approval, runtime):
        self.lock = Lock()
        self.store = store
        self.approval = approval
        self.runtime = runtime
        self.contacts = 0
        self.lost_ack = False
        self.revoke_inside = False

    def commit_scored_paper_if_current(self, *, transaction, custody, authorities):
        with self.lock:
            self.contacts += 1
            if self.revoke_inside:
                self.runtime = 'revoked-during-CAS-contact'
            assert len(authorities) == len(custody.questions) == 2
            assert transaction.intent.result is custody.outcome.result
            if any((a.academic.issued_paper.approval_revision != self.approval
                    or a.runtime.approval_ref != self.runtime) for a in authorities):
                return PaperCASDecision(transaction, PaperCASDisposition.STALE, None)
            result = self.store.commit_whole_paper(transaction=transaction, custody=custody)
            if self.lost_ack:
                raise RuntimeError('scored CAS response lost after write')
            return result


def connected_cas():
    engine, plan, physical, backend, conditional_first = connected_first()
    custody = ProductionPaperAttemptCustody(
        executor=engine, attempts=engine._attempts,
        request_source=KnownRequests(), max_identifier_characters=128,
        max_questions=10)
    legacy_store, source = Store(), OriginalSource()
    _, snap, _ = engine._prepared(plan.questions[0].request, plan,
        engine._correlation.preflight(plan=plan).issuer_relation.questions[0])
    from tests.integration.test_paper_lifecycle_pre_effect import Permissions
    from tests.integration.test_scored_cas_purpose_continuity import PurposeAwareAtomicCAS
    permissions = Permissions()
    conditional_first.f57_source = permissions
    conditional_cas = PurposeAwareAtomicCAS(
        legacy_store, conditional_first.approval_revision,
        snap[7].approval_ref, permissions, 'FIRST')
    from tests.integration.test_paper_lifecycle_pre_effect import POLICY
    cas = ProductionWholePaperCAS(
        custody=custody, issuer=Issuer(source), original_source=source,
        store=ReadOnlyCASPort(legacy_store), purpose_scored_store=conditional_cas,
        legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10,
        require_academic_preclaim=True,
    )
    return cas, plan, physical, legacy_store, conditional_first, conditional_cas


def test_actual_first_and_scored_cas_positive_use_conditional_owner():
    cas, plan, physical, store, first, conditional = connected_cas()
    output = cas.execute_and_commit(plan=plan,
        permission=conditional.source.resolve_paper_execution_permission(plan=plan))
    assert output.state is PaperCASState.COMMITTED
    assert output.academic_binding_verified is True
    assert physical.claims == 2 and first.claim_contacts == 2
    assert conditional.contacts == 1 and store.commits == 1


def test_scored_cas_denied_at_actual_conditional_commit_has_no_durable_effect():
    cas, plan, physical, store, first, conditional = connected_cas()
    conditional.runtime = 'revoked-before-cas'
    output = cas.execute_and_commit(plan=plan,
        permission=conditional.source.resolve_paper_execution_permission(plan=plan))
    assert output.state is PaperCASState.BLOCKED
    assert physical.claims == 2 and first.claim_contacts == 2
    assert conditional.contacts == 1 and store.commits == 0


def test_lost_scored_cas_response_never_retries_commit():
    cas, plan, physical, store, first, conditional = connected_cas()
    conditional.lost_ack = True
    output = cas.execute_and_commit(plan=plan,
        permission=conditional.source.resolve_paper_execution_permission(plan=plan))
    assert output.state is PaperCASState.UNKNOWN
    assert conditional.contacts == 1 and store.commits == 1
    assert output.transaction is not None and output.receipt is None


def test_joint_first_cannot_install_legacy_only_scored_cas():
    from pytest import raises
    engine, plan, *_ = connected_first()
    custody = ProductionPaperAttemptCustody(
        executor=engine, attempts=engine._attempts,
        request_source=KnownRequests(), max_identifier_characters=128,
        max_questions=10)
    with raises(ValueError, match='installed together'):
        ProductionWholePaperCAS(
            custody=custody, issuer=Issuer(OriginalSource()),
            original_source=OriginalSource(), store=Store(),
            legal_policy=LegalGradingTransitionPolicy('TEST-F57', 1,
                ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),)),
            max_identifier_characters=128, max_questions=10,
            require_academic_preclaim=True)


def test_scored_cas_revoked_within_conditional_effect_owner_does_not_commit():
    cas,plan,physical,store,first,conditional=connected_cas()
    conditional.revoked_during_commit=True
    output=cas.execute_and_commit(plan=plan,
        permission=conditional.source.resolve_paper_execution_permission(plan=plan))
    assert output.state is PaperCASState.BLOCKED
    assert physical.claims==2 and conditional.contacts==1
    assert store.commits==0
