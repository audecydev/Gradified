"""Fresh reviewer external test: never issue Q2 physical attempt claim after current academic issuance is revoked at Q1 contact."""
from dataclasses import replace
from grading.integration.paper_retry_grading import GradedRetryState
from tests.integration.test_authorized_retry_graded_retry_real import graded_rig


def test_revocation_between_claims_prevents_second_physical_f25_effect():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    first=physical.claim_fresh_attempt
    witnessed=[]
    def first_then_revoke(*, request):
        result=first(request=request)
        witnessed.append(request.scope.question_id)
        if len(witnessed)==1:
            source.relation=replace(source.relation,approval_revision='REVOKED-AFTER-Q1')
        return result
    physical.claim_fresh_attempt=first_then_revoke
    out=graded.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.UNKNOWN
    assert out.physical is not None
    assert len(out.physical.claimed) == 1
    assert out.physical.claimed[0].question_id == "Q1"
    assert not out.authorizes_publication and not out.authorizes_retry
    assert witnessed==['Q1'], ('Second attempt reservation after academic source changed',witnessed,atomic.calls,out.state)
    assert academic.prepares==1, ('Q2 academic preparation after issuer change',academic.prepares)
    assert store.commits==0


def test_issuer_change_inside_q2_academic_preparation_blocks_q2_claim():
    from grading.integration.paper_retry_grading import ProductionGradedPaperRetry
    from grading.integration.paper_retry_claim import ProductionAuthorizedPaperRetry
    from grading.integration.academic_claim_binding import AcademicClaimPreparation, AcademicPreclaimState
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    prior=graded._claims
    class IssuerChangesDuringPrepare:
        def __init__(self): self.prepares=0
        def prepare_original_binding(self, *, intent):
            self.prepares+=1
            if self.prepares==2:
                source.relation=replace(source.relation,approval_revision='INVALIDATED-IN-PREPARATION')
            return AcademicClaimPreparation(intent,'BIND-RETRY-'+intent.question_id,
                intent.issued_paper.approval_revision,AcademicPreclaimState.PREPARED)
    replacing=IssuerChangesDuringPrepare()
    claims=ProductionAuthorizedPaperRetry(recovery=prior._recovery,retry_authority=auth,
        academic_store=replacing,atomic_retry_store=atomic,legal_policy=prior._policy,
        retry_purpose_policy=prior._retry_purpose,
        max_identifier_characters=prior._max,max_questions=prior._questions)
    run=ProductionGradedPaperRetry(claims=claims,executor=graded._executor,cas=graded._cas)
    out=run.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.UNKNOWN
    assert out.physical is not None
    assert len(out.physical.claimed) == 1
    assert out.physical.claimed[0].question_id == "Q1"
    assert not out.authorizes_publication and not out.authorizes_retry
    assert physical.claims==1, ('Q2 attempt reserved after revocation during academic preparation',physical.claims, out.state)
    assert store.commits==0
