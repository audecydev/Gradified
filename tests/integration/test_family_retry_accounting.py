"""Connected family RETRY through the existing authorized retry claim original-absence/legal operation transition claim owner."""
from dataclasses import replace
import pytest

from grading.integration.attempt_authority import ClaimedAttemptAllocator, AttemptClaimRequest
from grading.integration.joint_effect_authority import JointEffectAdmission
from grading.integration.paper_retry_recovery import ProductionPaperOriginalRecovery, OriginalPaperRecoveryState
from grading.integration.paper_retry_claim import ProductionAuthorizedPaperRetry
from grading.integration.paper_retry_grading import ProductionGradedPaperRetry, GradedRetryState
from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS, PaperCASState
from tests.integration.test_whole_paper_family_execution import rig, rig_family
from tests.integration.test_family_first_scored_cas import ConditionalFamilyScoredBackend
from tests.integration.test_authorized_retry_claim import (
    FixedOriginal, Authority, AcademicBackend, AtomicRetryBackend,
    RETRY_PURPOSE, POLICY,
)
from tests.integration.test_joint_retry_connected_execution import ConditionalRetryFixture
from tests.integration.test_joint_first_claim_connected_execution import ReadOnlyAcademicPort, ReadOnlyF25Port, ReadOnlyCASPort
from tests.integration.test_academic_effect_preclaim import PerQuestionF25Issuer
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import OriginalSource, Issuer, Store
from tests.integration.test_scored_cas_purpose_continuity import PurposeAwareAtomicCAS



class FamilyRetryCAS:
    """Simulated conditional CAS fixture, never evidence of backend atomicity."""
    def __init__(self, store, source):
        self.store, self.source = store, source
        self.contacts=0
        self.revoke=False
        self.lost_ack=False

    def commit_scored_paper_if_authorized(self, *, transaction, custody, authorities, purpose):
        from grading.integration.whole_paper_cas import (
            PaperCASDecision, PaperCASDisposition, ScoredPaperPurpose)
        self.contacts+=1
        if self.revoke:
            self.source.mode='FOREIGN_POLICY'
        if not (type(purpose) is ScoredPaperPurpose and purpose.kind=='RETRY'
                and self.source.mode=='OK'
                and purpose.retry_grant is self.source.approval
                and purpose.retry_original is not None
                and len(authorities)==len(custody.questions)==len(transaction.intent.question_claims)
                and all(a.academic.issued_paper.approval_revision=='APPROVAL-REV'
                        and a.runtime.approval_ref=='RUNTIME-APPROVAL'
                        for a in authorities)):
            return PaperCASDecision(transaction,PaperCASDisposition.STALE,None)
        reply=self.store.commit_whole_paper(transaction=transaction,custody=custody)
        if self.lost_ack:
            raise RuntimeError('lost CAS reply after commit')
        return reply

def connected_family_retry(family='DIRECT'):
    old_ex, old_plan, old_perm, _, _, old_effect, _, _ = (rig() if family == 'DIRECT' else rig_family(family))
    old_effect.runtime_approval='REVOKED'
    lookup=KnownRequests()
    old_custody=ProductionPaperAttemptCustody(executor=old_ex, attempts=old_ex._attempts,
        request_source=lookup, max_identifier_characters=128, max_questions=10)
    original=old_custody.execute_and_capture(plan=old_plan, permission=old_perm)
    lookup.requests={q.question_id:q.original_f25_request for q in original.questions if q.original_f25_request}
    recovery=ProductionPaperOriginalRecovery(original_source=FixedOriginal(original),
        custody_reader=old_custody, max_identifier_characters=128,max_questions=10)
    assert recovery.reconcile().state is OriginalPaperRecoveryState.ABSENCE_REPORTED

    # Use the real family issuer, evidence and installed runtime of the successor;
    # only this legal operation transition-scoped new run can consume the recovered original absence.
    if family == 'DIRECT':
        new_ex, new_plan, _, new_physical, new_backend, _, provider, inputs = rig(
            grading_run_id='RETRY-RUN')
    else:
        new_ex, new_plan, _, new_physical, new_backend, _, provider, inputs = rig_family(
            family, grading_run_id='RETRY-RUN')
    issued=new_ex._correlation.preflight(plan=new_plan).issuer_relation
    reqs=[]
    for question, operation, scope in zip(new_plan.questions, inputs.inputs.operations,
                                           inputs.inputs.scopes,strict=True):
        runtime=new_ex._binder.bind_family(scope=scope,family=question.family,
            context_policy=operation.authority.context_policy)
        approval=runtime.approved_runtime
        reqs.append(AttemptClaimRequest('RETRY-'+question.request.question_id,
            scope,question.family,approval.runtime_id,approval.runtime_version,
            approval.implementation_ref,runtime.eligibility.policy.policy_id,
            runtime.eligibility.policy.policy_version))
    auth=Authority(original, new_plan, issued,inputs.inputs.paper_authority,tuple(reqs))
    physical_backend=AtomicRetryBackend(new_physical)
    joint_fixture=ConditionalRetryFixture(physical_backend, auth)
    joint=JointEffectAdmission(owner=joint_fixture)
    attempts=ClaimedAttemptAllocator(issuer=PerQuestionF25Issuer(),
        store=ReadOnlyF25Port(new_physical),academic_store=ReadOnlyAcademicPort(new_backend),
        joint_effect=joint,academic_max_questions=10,max_identifier_characters=128)
    executor=ProductionWholePaperFamilyExecutor(correlation=new_ex._correlation,
        runtime=new_ex._binder,attempts=attempts, inputs=inputs,
        max_identifier_characters=128,max_questions=10)
    academic=AcademicBackend()
    claims=ProductionAuthorizedPaperRetry(recovery=recovery, retry_authority=auth,
        academic_store=academic,atomic_retry_store=object(),legal_policy=POLICY,
        retry_purpose_policy=RETRY_PURPOSE,max_identifier_characters=128,max_questions=10,
        joint_effect=joint,runtime_executor=executor)
    custody=ProductionPaperAttemptCustody(executor=executor,attempts=attempts,
        request_source=KnownRequests(),max_identifier_characters=128,max_questions=10)
    original_source, store=OriginalSource(), Store()
    cas_backend=FamilyRetryCAS(store,auth)
    cas=ProductionWholePaperCAS(custody=custody,issuer=Issuer(original_source),
        original_source=original_source,store=ReadOnlyCASPort(store),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10,
        require_academic_preclaim=True,purpose_scored_store=cas_backend)
    grade=ProductionGradedPaperRetry(claims=claims,executor=executor,cas=cas)
    return grade,new_plan,new_physical,physical_backend,store,joint_fixture,provider


@pytest.mark.parametrize('family', ['DIRECT', 'NUMERIC', 'MIXED'])
def test_family_retry_via_original_absence_and_purpose_f57(family):
    svc,plan,physical,atomic,store,conditional,provider=connected_family_retry(family)
    result=svc.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.CAS_ACKNOWLEDGED, (result.state,result.physical)
    assert result.cas.state is PaperCASState.COMMITTED
    assert physical.claims==len(plan.questions) and store.commits==1
    assert not result.authorizes_retry and not result.authorizes_publication


def test_mixed_retry_revoked_after_first_physical_preserves_first_claim_and_no_score():
    svc,plan,physical,atomic,store,joint,provider=connected_family_retry('MIXED')
    joint.revoke_after_first=True
    out=svc.execute_and_commit(plan=plan)
    assert out.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and atomic.calls==1 and store.commits==0
    assert not out.authorizes_retry
    repeat=svc.execute_and_commit(plan=plan)
    assert repeat.state is GradedRetryState.UNKNOWN and physical.claims==1


def test_retry_lost_physical_ack_never_resubmits_or_scores():
    svc,plan,physical,atomic,store,joint,provider=connected_family_retry('DIRECT')
    joint.lost_ack=True
    out=svc.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.UNKNOWN
    assert physical.claims==1 and store.commits==0
    assert svc.execute_and_commit(plan=plan).state is GradedRetryState.UNKNOWN
    assert physical.claims==1


def test_retry_scored_cas_revoked_after_physical_f25_cannot_commit():
    svc,plan,physical,atomic,store,joint,provider=connected_family_retry('NUMERIC')
    svc._cas._purpose_commit.__self__.revoke=True
    out=svc.execute_and_commit(plan=plan)
    assert out.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and store.commits==0


def test_retry_physical_callback_provider_substitution_never_scores_or_commits():
    from tests.integration.test_direct_text_semantic_evaluator_hostile import _Provider
    svc,plan,physical,atomic,store,joint,provider=connected_family_retry('DIRECT')
    evaluator=svc._executor._resolve(plan=plan).operations[0].evaluator
    replacement=_Provider()
    original=atomic.claim_authorized_retry
    observed=[]
    def swap(*, original, authorization, question_id, preparation):
        response=original_claim(original=original,authorization=authorization,
             question_id=question_id,preparation=preparation)
        object.__setattr__(evaluator, '_provider', replacement)
        observed.append(True)
        return response
    original_claim=original
    atomic.claim_authorized_retry=swap
    out=svc.execute_and_commit(plan=plan)
    assert observed and physical.claims==1
    assert replacement.requests==[] and provider.requests==[]
    assert store.commits==0 and out.state is GradedRetryState.UNKNOWN
