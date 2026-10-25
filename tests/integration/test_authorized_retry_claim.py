"""authorized retry claim original-to-new atomic physical retry boundary (no invented scoring/approval)."""
from dataclasses import replace

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_authority import AttemptClaimRequest
from grading.integration.academic_claim_binding import AcademicClaimPreparation, AcademicallyBoundClaim, AcademicPreclaimState
from grading.integration.paper_retry_claim import (
    ProductionAuthorizedPaperRetry, AuthorizedPaperRetry,
    AtomicRetryClaimReceipt, RetryClaimState,
)
from grading.integration.paper_retry_recovery import (
    ProductionPaperOriginalRecovery, OriginalPaperRecoveryState,
)
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from tests.integration.test_academic_effect_preclaim import setup_bound
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_paper_lifecycle_pre_effect import POLICY
from grading.integration.retry_purpose_authorization import RetryPurposeTransitionPolicy, RETRY_CLAIM_PURPOSE
RETRY_PURPOSE = RetryPurposeTransitionPolicy(RETRY_CLAIM_PURPOSE,
    'TEST-F57-RETRY-PURPOSE', 1, POLICY.policy_id, POLICY.policy_version,
    ((GradingJobState.QUEUED, GradingJobState.GRADING),))


class FixedOriginal:
    def __init__(self, original): self.original=original
    def resolve_original_paper_attempt(self): return self.original


class Authority:
    def __init__(self, original, new_plan, issued, scoring, requests):
        self.approval = AuthorizedPaperRetry(original.plan.request.grading_run_id,
            new_plan, issued, scoring, tuple(q.request_ref for q in original.questions),
            requests, 'F57-RETRY-NEW-RUN', POLICY.policy_id, POLICY.policy_version,
            GradingJobState.QUEUED, GradingJobState.GRADING,
            RETRY_PURPOSE.approval_policy_id, RETRY_PURPOSE.approval_policy_version)
        self.mode = 'OK'; self.calls = 0
    def resolve_authorized_retry(self, *, original, new_plan):
        self.calls += 1
        if self.mode == 'FOREIGN_POLICY':
            return replace(self.approval,policy_id='FOREIGN-F57')
        if self.mode == 'FOREIGN_RUN':
            return replace(self.approval,original_run_id='WRONG')
        return self.approval


class AcademicBackend:
    def __init__(self): self.prepares=0
    def prepare_original_binding(self, *, intent):
        self.prepares+=1
        return AcademicClaimPreparation(intent, 'BIND-RETRY-'+intent.question_id,
            intent.issued_paper.approval_revision, AcademicPreclaimState.PREPARED)


class AtomicRetryBackend:
    def __init__(self, physical):
        from threading import Lock
        self.physical=physical; self.calls=0; self.mode='OK'
        self._guard=Lock(); self._accepted=set(); self.original_late_reserved=False
    def claim_authorized_retry(self, *, original, authorization, question_id, preparation):
        # Qualified-backend *contract fixture*: one atomic successor per
        # original/question. Real cross-worker enforcement needs a real store.
        from grading.integration.attempt_authority import AttemptClaim, AttemptClaimDisposition
        with self._guard:
            self.calls += 1
            scope=(original.paper.plan.request.grading_run_id, question_id)
            if self.original_late_reserved or scope in self._accepted:
                return AtomicRetryClaimReceipt(None,
                    preparation.intent.original_request.request_ref,
                    authorization.approval_ref,'REPLAY-'+question_id,
                    AcademicallyBoundClaim(preparation,AttemptClaim(
                        preparation.intent.original_request,AttemptClaimDisposition.CONFLICT,None)))
            self._accepted.add(scope)
        if self.mode == 'LOST_CLAIM':
            self.physical.claim_fresh_attempt(request=preparation.intent.original_request)
            raise RuntimeError('PRIVATE-PHYSICAL-CLAIM-REPLY-LOST')
        claim=self.physical.claim_fresh_attempt(request=preparation.intent.original_request)
        if self.mode == 'FOREIGN':
            return AtomicRetryClaimReceipt(original_request_ref='WRONG',
                new_request_ref=preparation.intent.original_request.request_ref,
                approval_ref=authorization.approval_ref,transaction_ref='TX-'+question_id,
                bound_claim=AcademicallyBoundClaim(preparation,claim))
        old=next((q.request_ref for q in original.paper.questions if q.question_id==question_id),None)
        return AtomicRetryClaimReceipt(old, preparation.intent.original_request.request_ref,
            authorization.approval_ref, 'TX-'+question_id,
            AcademicallyBoundClaim(preparation,claim))


def rig():
    root, old_plan, physical, original_academic = setup_bound()
    original_academic.mode = 'REJECT_PREPARE'  # no genuine claim committed
    issuer = KnownRequests()
    custody=ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=issuer, max_identifier_characters=128, max_questions=10)
    original=custody.execute_and_capture(plan=old_plan)
    issuer.requests={q.question_id:q.original_f25_request for q in original.questions
                    if q.original_f25_request is not None}
    recovery=ProductionPaperOriginalRecovery(original_source=FixedOriginal(original),
        custody_reader=custody, max_identifier_characters=128, max_questions=10)
    assert recovery.reconcile().state is OriginalPaperRecoveryState.ABSENCE_REPORTED
    new_plan=replace(old_plan, request=replace(old_plan.request,grading_run_id='RETRY-RUN'),
        questions=tuple(replace(q,request=replace(q.request,grading_run_id='RETRY-RUN'))
                        for q in old_plan.questions))
    original_scope=original.questions[0].original_f25_request.scope
    original_request=original.questions[0].original_f25_request
    requests=tuple(AttemptClaimRequest('RETRY-'+q.request.question_id,
        replace(original_scope, grading_run_id='RETRY-RUN',question_id=q.request.question_id,
            source_artifact_ref=q.source_artifact_ref, evidence_scope_ref=q.evidence_scope_ref,
            source_revision=q.source_revision, ocr_provenance=q.provenance_ref),
        q.family, original_request.runtime_id,original_request.runtime_version,
        original_request.implementation_ref,original_request.eligibility_policy_id,
        original_request.eligibility_policy_version)
        for q in new_plan.questions)
    issued=replace(original_academic.prepares[0].issued_paper,request=new_plan.request)
    scoring=original_academic.prepares[0].scoring
    authority=Authority(original,new_plan,issued,scoring,requests)
    academic=AcademicBackend(); atomic=AtomicRetryBackend(physical)
    svc=ProductionAuthorizedPaperRetry(recovery=recovery,retry_authority=authority,
        academic_store=academic,atomic_retry_store=atomic,legal_policy=POLICY,
        retry_purpose_policy=RETRY_PURPOSE,
        max_identifier_characters=128,max_questions=10)
    return svc,new_plan,physical,authority,academic,atomic


def test_authorized_atomic_retry_claims_original_to_new_scope_before_any_grading():
    svc, plan, physical, auth, academic, atomic=rig()
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.CLAIMED
    assert len(fact.claimed)==2 and len({q.new_request_ref for q in fact.claimed})==2
    assert physical.claims==2 and academic.prepares==2 and atomic.calls==2
    assert not fact.authorizes_publication and not fact.authorizes_retry


def test_foreign_legal_policy_denies_all_physical_and_academic_effects():
    svc,plan,physical,auth,academic,atomic=rig()
    auth.mode='FOREIGN_POLICY'
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)


def test_retry_cannot_use_same_run_or_original_request():
    svc,plan,physical,auth,academic,atomic=rig()
    auth.approval=replace(auth.approval,new_requests=(
        replace(auth.approval.new_requests[0], request_ref='REQUEST-Q1'),
        auth.approval.new_requests[1]))
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)


def test_claim_reply_lost_preserves_prior_claim_uncertainty_without_retry():
    svc,plan,physical,auth,academic,atomic=rig()
    atomic.mode='LOST_CLAIM'
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.UNKNOWN
    assert physical.claims==1 and atomic.calls==1
    assert len(fact.claimed)==0 and not fact.authorizes_retry


def test_malformed_postclaim_receipt_unknown_not_negative_claim():
    svc,plan,physical,auth,academic,atomic=rig()
    atomic.mode='FOREIGN'
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.UNKNOWN and physical.claims==1
    assert not fact.authorizes_retry


def test_foreign_approved_revision_never_prepares_or_claims():
    svc,plan,physical,auth,academic,atomic=rig()
    auth.approval=replace(auth.approval,issued_paper=replace(
        auth.approval.issued_paper,approval_revision='OLD-REVOKED-REVISION'))
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)


def test_duplicate_two_question_new_request_denied_before_any_preparation():
    svc,plan,physical,auth,academic,atomic=rig()
    prior=auth.approval.new_requests
    auth.approval=replace(auth.approval,new_requests=(prior[0],replace(prior[1],
        request_ref=prior[0].request_ref)))
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.PRE_EFFECT_BLOCKED
    assert (physical.claims,academic.prepares,atomic.calls)==(0,0,0)


def test_one_installed_retry_claim_cannot_be_repeated_after_possible_effect():
    svc,plan,physical,auth,academic,atomic=rig()
    assert svc.claim(plan=plan).state is RetryClaimState.CLAIMED
    before=physical.claims,academic.prepares,atomic.calls
    assert svc.claim(plan=plan).state is RetryClaimState.UNKNOWN
    assert (physical.claims,academic.prepares,atomic.calls)==before


def test_lost_original_retry_claim_reply_cannot_recontact_same_atomic_store():
    svc,plan,physical,auth,academic,atomic=rig()
    atomic.mode='LOST_CLAIM'
    assert svc.claim(plan=plan).state is RetryClaimState.UNKNOWN
    assert svc.claim(plan=plan).state is RetryClaimState.UNKNOWN
    assert (physical.claims,atomic.calls)==(1,1)


def test_late_original_reservation_race_is_denied_at_atomic_claim_not_retried():
    svc,plan,physical,auth,academic,atomic=rig()
    atomic.original_late_reserved=True
    fact=svc.claim(plan=plan)
    assert fact.state is RetryClaimState.UNKNOWN
    assert physical.claims==0 and atomic.calls==1


def test_two_independent_consumers_share_backend_atomic_predecessor_precondition():
    from grading.integration.paper_retry_claim import ProductionAuthorizedPaperRetry
    from concurrent.futures import ThreadPoolExecutor
    svc,plan,physical,auth,academic,atomic=rig()
    second=ProductionAuthorizedPaperRetry(recovery=svc._recovery,retry_authority=auth,
        academic_store=academic,atomic_retry_store=atomic,legal_policy=POLICY,
        retry_purpose_policy=RETRY_PURPOSE,
        max_identifier_characters=128,max_questions=10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(svc.claim,plan=plan)
        b=pool.submit(second.claim,plan=plan)
        states={a.result().state,b.result().state}
    assert RetryClaimState.CLAIMED in states and RetryClaimState.UNKNOWN in states
    # The backend either prevents a duplicate or processes one new run once.
    assert physical.claims==2
