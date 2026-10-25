"""Genuine graded-RETRY claim and scored-CAS route through conditional owners.

The authority and atomicity implemented by these fixtures are *test assumptions*;
no institutional issuer or durable database is inferred from their success.
"""
from threading import Lock
from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.joint_effect_authority import (
    JointEffectAdmission, ConditionalEffectClaimResponse, ConditionalCASResponse,
    EffectDecision, GradingEffectKind,
)
from grading.integration.paper_retry_claim import ProductionAuthorizedPaperRetry
from grading.integration.paper_retry_grading import ProductionGradedPaperRetry, GradedRetryState
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS, PaperCASState
from tests.integration.test_authorized_retry_claim import rig, POLICY
from tests.integration.test_academic_effect_preclaim import PerQuestionF25Issuer, QualifiedShapeAcademicBackend
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import OriginalSource, Issuer, Store
from tests.integration.test_joint_first_claim_connected_execution import (
    AtomicConditionalCASFixture, ReadOnlyAcademicPort, ReadOnlyF25Port, ReadOnlyCASPort,
)


class ConditionalRetryFixture:
    def __init__(self, atomic, source):
        self.atomic = atomic
        self.source = source
        self.contacts = 0
        self.before_effect_revoke = False
        self.runtime_revoked = False
        self.lost_ack = False
        self.revoke_after_first = False
        self.lock = Lock()

    def claim_if_current(self, *, request):
        with self.lock:
            self.contacts += 1
            if self.before_effect_revoke:
                self.source.mode = 'FOREIGN_POLICY'
            if (request.operation is not GradingEffectKind.RETRY_F25
                    or self.source.mode != 'OK'
                    or self.runtime_revoked
                    or request.retry_grant is not self.source.approval):
                return ConditionalEffectClaimResponse(request, EffectDecision.REJECTED)
            answer = self.atomic.claim_authorized_retry(
                original=request.original_retry, authorization=request.retry_grant,
                question_id=request.authority.academic.question_id,
                preparation=request.preparation)
            if self.revoke_after_first:
                self.source.mode = 'FOREIGN_POLICY'
            if self.lost_ack:
                raise RuntimeError('lost joint physical claim reply')
            return ConditionalEffectClaimResponse(request, EffectDecision.COMMITTED,
                                          answer.bound_claim, answer)

    def commit_if_current(self, *, request):
        raise AssertionError('RETRY physical-claim owner does not commit CAS')


class NeverClaimLegacy:
    def claim_fresh_attempt(self, *, request):
        raise AssertionError('legacy physical attempt branch was contacted')
    def reconcile_reservation(self, *, request):
        raise AssertionError('legacy grading-attempt recovery not used in this test')


def connected_retry(*, purpose_aware=True):
    old, plan, physical, auth, academic, atomic = rig()
    base, _, _, _, _, unused_physical = _setup_two(grading_run_id='RETRY-RUN')
    legacy = QualifiedShapeAcademicBackend(unused_physical)
    retry = ConditionalRetryFixture(atomic, auth)
    condition = JointEffectAdmission(owner=retry)
    # This allocator is installed for the grading root's source binding, but
    # the RETRY physical claim is owned only by the conditional retry service.
    attempts = ClaimedAttemptAllocator(
        issuer=PerQuestionF25Issuer(), store=ReadOnlyF25Port(unused_physical),
        academic_store=ReadOnlyAcademicPort(legacy), joint_effect=condition,
        max_identifier_characters=128, academic_max_questions=10)
    executor = ProductionWholePaperChoiceExecutor(
        contact=base._contact, correlation=base._correlation,
        handoff=base._handoff, attempts=attempts,
        max_identifier_characters=128, max_questions=10)
    claims = ProductionAuthorizedPaperRetry(
        recovery=old._recovery, retry_authority=auth, academic_store=academic,
        atomic_retry_store=object(), legal_policy=POLICY,
        retry_purpose_policy=old._retry_purpose,
        max_identifier_characters=128, max_questions=10,
        joint_effect=condition, runtime_executor=executor)
    custody = ProductionPaperAttemptCustody(
        executor=executor, attempts=attempts,
        request_source=KnownRequests(), max_identifier_characters=128,
        max_questions=10)
    source, store = OriginalSource(), Store()
    relation=executor._correlation.preflight(plan=plan).issuer_relation
    _, runtime_snap, _ = executor._prepared(plan.questions[0].request,plan,relation.questions[0])
    cas_atomic = AtomicConditionalCASFixture(store, relation.approval_revision,
                                             runtime_snap[7].approval_ref)
    if purpose_aware:
        from tests.integration.test_scored_cas_purpose_continuity import PurposeAwareAtomicCAS
        cas_atomic=PurposeAwareAtomicCAS(store,relation.approval_revision,
                                         runtime_snap[7].approval_ref,auth,'RETRY')
    cas=ProductionWholePaperCAS(
        custody=custody, issuer=Issuer(source), original_source=source,
        store=ReadOnlyCASPort(store),
        **({"purpose_scored_store": cas_atomic} if purpose_aware else
           {"joint_scored_store": cas_atomic}),
        legal_policy=POLICY, max_identifier_characters=128,
        max_questions=10, require_academic_preclaim=True)
    grade=ProductionGradedPaperRetry(claims=claims, executor=executor, cas=cas)
    return grade,plan,physical,atomic,store,retry,cas_atomic,unused_physical


def test_joint_retry_real_two_question_positive_and_scored_cas():
    grade,plan,physical,atomic,store,cond,cas,unused=connected_retry()
    result=grade.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.CAS_ACKNOWLEDGED, result.state
    assert result.cas.state is PaperCASState.COMMITTED
    assert physical.claims==2 and atomic.calls==2 and cond.contacts==2
    assert store.commits==1 and cas.contacts==1 and unused.claims==0


def test_joint_retry_revoke_before_first_effect_blocks_physical_claim():
    grade,plan,physical,atomic,store,cond,cas,unused=connected_retry()
    cond.before_effect_revoke=True
    result=grade.execute_and_commit(plan=plan)
    assert result.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and atomic.calls==0 and store.commits==0


def test_joint_retry_lost_f25_ack_does_not_repeat_or_score():
    grade,plan,physical,atomic,store,cond,cas,unused=connected_retry()
    cond.lost_ack=True
    result=grade.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.UNKNOWN
    assert physical.claims==1 and atomic.calls==1 and store.commits==0
    assert grade.execute_and_commit(plan=plan).state is GradedRetryState.UNKNOWN
    assert physical.claims==1


def test_joint_retry_runtime_revoked_at_physical_contact_blocks_before_claim():
    grade,plan,physical,atomic,store,cond,cas,unused=connected_retry()
    cond.runtime_revoked=True
    result=grade.execute_and_commit(plan=plan)
    assert result.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and atomic.calls==0 and store.commits==0


def test_conditional_scored_cas_cannot_install_legacy_retry_f25_claim():
    import pytest
    grade, *_ = connected_retry()
    claims = grade._claims
    # Simulate a composition containing a legacy-only retry claimant. A
    # conditional CAS cannot repair an earlier unguarded physical effect.
    original = claims._joint_effect
    object.__setattr__(claims, '_joint_effect', None)
    try:
        with pytest.raises(ValueError, match='qualified retry'):
            ProductionGradedPaperRetry(claims=claims, executor=grade._executor,
                                          cas=grade._cas)
    finally:
        object.__setattr__(claims, '_joint_effect', original)


def test_joint_retry_revocation_after_first_effect_preserves_one_claim_not_score():
    grade,plan,physical,atomic,store,cond,cas,unused=connected_retry()
    cond.revoke_after_first=True
    outcome=grade.execute_and_commit(plan=plan)
    assert outcome.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and atomic.calls==1
    assert store.commits==0 and cas.contacts==0
