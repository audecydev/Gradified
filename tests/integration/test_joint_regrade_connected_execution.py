"""Complete source-issued REGRADE -> joint physical attempt claim -> scored CAS owner route."""
from threading import Lock
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.academic_claim_binding import AcademicallyBoundClaim
from grading.integration.joint_effect_authority import (
    JointEffectAdmission, ConditionalEffectClaimResponse, EffectDecision,
    GradingEffectKind,
)
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from tests.integration.test_paper_lifecycle_pre_effect import Permissions
from tests.integration.test_paper_lifecycle_regrade import (
    setup_regrade, NewRunCASIssuer, POLICY,
)
from tests.integration.test_joint_first_claim_connected_execution import (
    AtomicConditionalCASFixture, ReadOnlyAcademicPort, ReadOnlyF25Port, ReadOnlyCASPort,
)
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import OriginalSource


class ConditionalRegradeFixture:
    def __init__(self, backend, permission_source):
        self.backend=backend
        self.source=permission_source
        self.lock=Lock()
        self.contacts=0
        self.revoke_inside=False
        self.revoke_after_first=False

    def claim_if_current(self, *, request):
        with self.lock:
            self.contacts+=1
            if self.revoke_inside:
                self.source.mode='UNAVAILABLE'
            grant=request.regrade_permission
            if (request.operation is not GradingEffectKind.REGRADE_F25
                    or self.source.mode != 'REGRADE'
                    or grant.approval_ref != request.authority.academic.original_request.regrade_approval_ref):
                return ConditionalEffectClaimResponse(request,EffectDecision.REJECTED)
            bound=self.backend.claim_bound_fresh(preparation=request.preparation)
            if self.revoke_after_first:
                self.source.mode='UNAVAILABLE'
            return ConditionalEffectClaimResponse(request,EffectDecision.COMMITTED,bound)

    def commit_if_current(self, *, request):
        raise AssertionError('Regrade physical owner does not commit scored CAS')


def connected_regrade(monkeypatch, *, purpose_aware=True):
    legacy,plan,physical,store,issuer,backend,old=setup_regrade(monkeypatch)
    previous=legacy._cas._custody._executor
    permissions=Permissions();permissions.mode='REGRADE';permissions.prior=old.transaction
    permissions.custody=old.custody
    conditional=ConditionalRegradeFixture(backend,permissions)
    attempts=ClaimedAttemptAllocator(
        issuer=issuer,store=ReadOnlyF25Port(physical),academic_store=ReadOnlyAcademicPort(backend),
        joint_effect=JointEffectAdmission(owner=conditional),
        academic_max_questions=10,max_identifier_characters=128)
    executor=ProductionWholePaperChoiceExecutor(
        contact=previous._contact,correlation=previous._correlation,
        handoff=previous._handoff,attempts=attempts,
        max_identifier_characters=128,max_questions=10)
    custody=ProductionPaperAttemptCustody(
        executor=executor,attempts=attempts,request_source=KnownRequests(),
        max_identifier_characters=128,max_questions=10)
    relation=executor._correlation.preflight(plan=plan).issuer_relation
    _,snapshot,_=executor._prepared(plan.questions[0].request,plan,relation.questions[0])
    conditional_cas=AtomicConditionalCASFixture(store,relation.approval_revision,snapshot[7].approval_ref)
    source=OriginalSource()
    if purpose_aware:
        from tests.integration.test_scored_cas_purpose_continuity import PurposeAwareAtomicCAS
        conditional_cas=PurposeAwareAtomicCAS(store,relation.approval_revision,
                                                snapshot[7].approval_ref,permissions,'REGRADE')
    cas=ProductionWholePaperCAS(custody=custody,issuer=NewRunCASIssuer(source),
        original_source=source,store=ReadOnlyCASPort(store),
        **({'purpose_scored_store': conditional_cas} if purpose_aware else
           {'joint_scored_store': conditional_cas}),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,
        require_academic_preclaim=True)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=permissions,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    return lifecycle,plan,physical,store,conditional,conditional_cas,permissions


def test_valid_regrade_uses_actual_conditional_f25_and_cas(monkeypatch):
    service,plan,physical,store,cond,cas,source=connected_regrade(monkeypatch)
    outcome=service.execute_regrade(plan=plan)
    assert outcome.state is PaperLifecycleState.CAS_ACKNOWLEDGED, outcome.state
    assert physical.claims==2 and cond.contacts==2
    assert cas.contacts==1 and store.commits==2


def test_source_purpose_revocation_inside_regrade_effect_blocks_without_new_claim(monkeypatch):
    service,plan,physical,store,cond,cas,source=connected_regrade(monkeypatch)
    cond.revoke_inside=True
    outcome=service.execute_regrade(plan=plan)
    assert outcome.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and store.commits==1
    assert cond.contacts==1 and cas.contacts==0


def test_regrade_revocation_after_q1_has_no_second_effect_or_cas(monkeypatch):
    service,plan,physical,store,cond,cas,source=connected_regrade(monkeypatch)
    cond.revoke_after_first=True
    outcome=service.execute_regrade(plan=plan)
    assert outcome.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and cond.contacts==2
    assert store.commits==1 and cas.contacts==0
