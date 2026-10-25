"""Real PRE -> CHOICE evaluator -> deterministic scoring -> frozen whole-paper score -> one CAS,
using original authorized retry claim claims without ever issuing a second physical attempt claim.
"""
from dataclasses import replace
from grading.integration.paper_retry_grading import (
    ProductionGradedPaperRetry, GradedRetryState,
)
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS, PaperCASState
from tests.integration.test_academic_effect_preclaim import (
    PerQuestionF25Issuer, QualifiedShapeAcademicBackend,
)
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import Store,Issuer,OriginalSource
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_authorized_retry_claim import rig, POLICY


def graded_rig():
    claim_service, newplan, physical, auth, academic, atomic=rig()
    run_root, current_plan, paper_source, fresh, runtime, unused_f25=_setup_two(grading_run_id='RETRY-RUN')
    assert newplan == current_plan
    allocator=ClaimedAttemptAllocator(issuer=PerQuestionF25Issuer(),store=unused_f25,
        academic_store=QualifiedShapeAcademicBackend(unused_f25),
        academic_max_questions=10,max_identifier_characters=128)
    executor=ProductionWholePaperChoiceExecutor(contact=run_root._contact,
        correlation=run_root._correlation,handoff=run_root._handoff, attempts=allocator,
        max_identifier_characters=128,max_questions=10)
    custody=ProductionPaperAttemptCustody(executor=executor,attempts=allocator,
        request_source=KnownRequests(),max_identifier_characters=128,max_questions=10)
    original=OriginalSource();store=Store()
    cas=ProductionWholePaperCAS(custody=custody,issuer=Issuer(original),
        original_source=original,store=store,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,require_academic_preclaim=True)
    graded=ProductionGradedPaperRetry(claims=claim_service,executor=executor,cas=cas)
    return graded,newplan,physical,auth,academic,atomic,store,unused_f25,paper_source,fresh


def test_genuine_two_question_retry_graded_once_without_second_f25_claim():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.CAS_ACKNOWLEDGED, result.state
    assert result.cas.state is PaperCASState.COMMITTED
    assert len(result.custody.questions)==2
    assert result.custody.outcome.result.paper_score is not None
    assert str(result.custody.outcome.result.paper_score.final_score)=='10'
    assert physical.claims == 2 and atomic.calls == 2
    assert unused_f25.claims == 0, 'Ordinary attempt allocator was improperly contacted after physical claims.'
    assert store.commits==1
    assert [q.s1_verified for q in result.custody.questions]==[True,True]
    assert all(not getattr(result,perm) for perm in ('authorizes_retry','authorizes_publication'))
    replay=graded.execute_and_commit(plan=plan)
    assert replay.state is GradedRetryState.UNKNOWN
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,1)


def test_unqualified_current_preparations_block_before_retry_f25_claim():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    source.relation=replace(source.relation,questions=(replace(source.relation.questions[0],
        scoring_policy_ref='FOREIGN'),*source.relation.questions[1:]))
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,store.commits)==(0,0,0)


def test_retry_after_claim_lost_reply_never_grades_or_commits():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    atomic.mode='LOST_CLAIM'
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.UNKNOWN
    assert (physical.claims,unused_f25.claims,store.commits)==(1,0,0)
    assert graded.execute_and_commit(plan=plan).state is GradedRetryState.UNKNOWN
    assert physical.claims==1


def test_wrong_runtime_request_precludes_all_retry_physical_claims():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    auth.approval=replace(auth.approval,new_requests=(replace(
        auth.approval.new_requests[0],runtime_id='FORGED-RUNTIME'),
        auth.approval.new_requests[1]))
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,store.commits)==(0,0,0)


def test_cas_lost_response_does_not_reclaim_f25_or_report_success():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    store.mode='CRASH'
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.UNKNOWN
    assert result.cas is not None and result.cas.state is PaperCASState.UNKNOWN
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,1)


def test_s1_exception_after_real_claim_preserves_physical_custody_without_score(monkeypatch):
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    import grading.integration.paper_retry_grading as retry_module
    def fail_s1(**kwargs):
        raise RuntimeError('SYNTHETIC-POST-RESERVATION-VERIFICATION-FAULT')
    monkeypatch.setattr(retry_module,'verify_evaluated_judgments',fail_s1)
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.UNKNOWN
    assert result.custody is not None and result.custody.outcome.result is None
    assert result.custody.outcome.state=='INDETERMINATE'
    assert len(result.custody.questions)==2
    assert all(q.reservation_validated for q in result.custody.questions)
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,0)


def test_cas_definitive_conflict_does_not_turn_preclaimed_grade_into_publication():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    store.mode='CONFLICT'
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.CAS_BLOCKED
    assert result.custody.outcome.result is not None
    assert result.cas.state is PaperCASState.BLOCKED
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,1)
    assert not result.authorizes_publication and not result.authorizes_retry


def test_retry_cas_result_retains_same_process_original_read_custody():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    result=graded.execute_and_commit(plan=plan)
    assert result.state is GradedRetryState.CAS_ACKNOWLEDGED
    assert graded._cas.reconcile(outcome=result.cas) is PaperCASState.COMMITTED
    assert store.reads == 1 and store.commits == 1
    assert physical.claims == 2 and unused_f25.claims == 0


def test_retry_confirmation_callback_revokes_original_issuer_before_scored_cas():
    """Already claimed retry effects do not authorize grading a revoked paper."""
    graded, plan, physical, auth, academic, atomic, store, old_f25, issuer, fresh = graded_rig()
    seen = []
    def revoke(_paper, question, _scope):
        seen.append(question.question_id)
        if question.question_id == 'Q2':
            issuer.relation = replace(issuer.relation,
                approval_revision='REVOKED-DURING-Q2-RETRY-CONFIRMATION')
    fresh.action = revoke
    result = graded.execute_and_commit(plan=plan)
    assert 'Q2' in seen
    assert result.state is GradedRetryState.UNKNOWN
    assert physical.claims == 2 and store.commits == 0
    assert result.physical is not None and len(result.physical.claimed) == 2
    assert not result.authorizes_retry and not result.authorizes_publication
