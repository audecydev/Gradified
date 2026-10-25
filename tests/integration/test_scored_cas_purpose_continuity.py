"""Source-issued legal operation transition original operation reaches the actual scored CAS callback.

In-process fixture models atomicity; it is NOT backend conformance proof.
The actual DB must authenticate current source and compare it in its write lock.
"""
from threading import Lock

import pytest

from grading.integration.whole_paper_cas import (
    PaperCASDecision, PaperCASDisposition, PaperCASState, ScoredPaperPurpose,
)
from grading.integration.paper_lifecycle import PaperLifecycleState
from grading.integration.paper_retry_grading import GradedRetryState
from tests.integration.test_joint_regrade_connected_execution import connected_regrade
from tests.integration.test_joint_retry_connected_execution import connected_retry


class PurposeAwareAtomicCAS:
    def __init__(self, store, approval, runtime, source, kind):
        self.lock=Lock()
        self.store=store
        self.approval=approval
        self.runtime=runtime
        self.source=source
        self.kind=kind
        self.contacts=0
        self.revoked_during_commit=False
        self.lost_ack=False

    def commit_scored_paper_if_authorized(self, *, transaction, custody, authorities, purpose):
        with self.lock:
            self.contacts+=1
            if self.revoked_during_commit:
                self.source.mode=('UNAVAILABLE' if self.kind=='REGRADE' else 'FOREIGN_POLICY')
            # This fixture checks current source as part of its modeled CAS
            # consistency boundary. Production must do this atomically.
            valid=(type(purpose) is ScoredPaperPurpose
                   and purpose.kind==self.kind
                   and len(authorities)==len(custody.questions)==2
                   and all(a.academic.issued_paper.approval_revision==self.approval
                           and a.runtime.approval_ref==self.runtime for a in authorities))
            if self.kind=='FIRST':
                valid=(valid and self.source.mode=='FIRST'
                       and purpose.permission.approval_ref=='F57-FIRST-APPROVAL'
                       and purpose.permission.predecessor is None)
            elif self.kind=='REGRADE':
                valid=(valid and self.source.mode=='REGRADE'
                       and purpose.permission.approval_ref=='F57-REGRADE-APPROVAL'
                       and purpose.permission.predecessor is not None
                       and purpose.permission.predecessor.result_ref ==
                       transaction.intent.original_claim_requests[0].predecessor_result_ref)
            else:
                valid=(valid and self.source.mode=='OK'
                       and purpose.retry_grant is self.source.approval
                       and purpose.retry_original is not None
                       and purpose.retry_grant.original_request_refs is not None)
            if not valid:
                return PaperCASDecision(transaction,PaperCASDisposition.STALE,None)
            result=self.store.commit_whole_paper(transaction=transaction,custody=custody)
            if self.lost_ack:
                raise RuntimeError('Lost scored CAS acknowledgment after effect')
            return result


def test_regrade_real_positive_requires_current_purpose(monkeypatch):
    svc,plan,physical,store,claim,cas,source=connected_regrade(monkeypatch,purpose_aware=True)
    out=svc.execute_regrade(plan=plan)
    assert out.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==2 and cas.contacts==1 and store.commits==2


def test_regrade_revoked_after_last_claim_has_no_new_scored_commit(monkeypatch):
    from tests.integration.test_joint_regrade_connected_execution import ConditionalRegradeFixture
    original=ConditionalRegradeFixture.claim_if_current
    def revoke(self, *, request):
        answer=original(self,request=request)
        if self.contacts==2:self.source.mode='UNAVAILABLE'
        return answer
    monkeypatch.setattr(ConditionalRegradeFixture,'claim_if_current',revoke)
    svc,plan,physical,store,claim,cas,source=connected_regrade(monkeypatch,purpose_aware=True)
    out=svc.execute_regrade(plan=plan)
    assert physical.claims==2 and cas.contacts==1
    assert store.commits==1 and out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED


def test_regrade_revoked_within_scored_effect_has_no_new_commit(monkeypatch):
    svc,plan,physical,store,claim,cas,source=connected_regrade(monkeypatch,purpose_aware=True)
    cas.revoked_during_commit=True
    out=svc.execute_regrade(plan=plan)
    assert physical.claims==2 and cas.contacts==1
    assert store.commits==1 and out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED


def test_retry_real_positive_without_scored_predecessor(monkeypatch):
    svc,plan,physical,atomic,store,claim,cas,legacy=connected_retry(purpose_aware=True)
    out=svc.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.CAS_ACKNOWLEDGED
    assert atomic.calls==2 and cas.contacts==1 and store.commits==1


def test_retry_revoked_after_last_claim_has_no_scored_commit(monkeypatch):
    from tests.integration.test_joint_retry_connected_execution import ConditionalRetryFixture
    original=ConditionalRetryFixture.claim_if_current
    def revoke(self, *, request):
        answer=original(self,request=request)
        if self.contacts==2:self.source.mode='FOREIGN_POLICY'
        return answer
    monkeypatch.setattr(ConditionalRetryFixture,'claim_if_current',revoke)
    svc,plan,physical,atomic,store,claim,cas,legacy=connected_retry(purpose_aware=True)
    out=svc.execute_and_commit(plan=plan)
    assert atomic.calls==2 and cas.contacts==1 and store.commits==0
    assert out.state is not GradedRetryState.CAS_ACKNOWLEDGED


def test_retry_revoked_within_scored_effect_has_no_commit():
    svc,plan,physical,atomic,store,claim,cas,legacy=connected_retry(purpose_aware=True)
    cas.revoked_during_commit=True
    out=svc.execute_and_commit(plan=plan)
    assert atomic.calls==2 and cas.contacts==1 and store.commits==0
    assert out.state is not GradedRetryState.CAS_ACKNOWLEDGED


def test_retry_lost_scored_ack_is_unknown_and_not_reissued():
    svc,plan,physical,atomic,store,claim,cas,legacy=connected_retry(purpose_aware=True)
    cas.lost_ack=True
    out=svc.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.UNKNOWN
    assert atomic.calls==2 and cas.contacts==1 and store.commits==1
    assert svc.execute_and_commit(plan=plan).state is GradedRetryState.UNKNOWN
    assert store.commits==1 and cas.contacts==1


def test_retry_scored_purpose_is_bound_to_recovered_original_run():
    """The scored CAS input must not select an unrelated absent physical attempt claim run."""
    from dataclasses import replace
    from grading.integration.paper_retry_recovery import OriginalPaperRecoveryState
    from grading.integration.whole_paper_cas import _admit_scored_purpose
    service, plan, physical, atomic, store, claim, cas, legacy = connected_retry(
        purpose_aware=True)
    observation = service.execute_and_commit(plan=plan)
    assert observation.state is GradedRetryState.CAS_ACKNOWLEDGED
    grant = service._claims._last_material[1]
    original = observation.physical.original
    transaction = observation.cas.transaction

    def admit(grant_value, original_value):
        return _admit_scored_purpose(
            ScoredPaperPurpose('RETRY', retry_grant=grant_value,
                               retry_original=original_value),
            transaction.intent, None, transaction, 128, 10)

    assert admit(grant, original).retry_grant is grant
    with pytest.raises(ValueError, match='RETRY'):
        admit(replace(grant, original_run_id='FOREIGN-RUN'), original)
    with pytest.raises(ValueError, match='RETRY'):
        admit(replace(grant, original_request_refs=('FOREIGN-REF',) *
                      len(grant.original_request_refs)), original)
    with pytest.raises(ValueError, match='RETRY'):
        admit(grant, replace(original, state=OriginalPaperRecoveryState.UNKNOWN))


def test_strict_first_must_have_source_issued_permission_before_any_f25_contact():
    from tests.integration.test_joint_first_claim_connected_execution import connected_cas
    cas, plan, physical, store, first, scored = connected_cas()
    with pytest.raises(ValueError, match='original FIRST/REGRADE authority'):
        cas.execute_and_commit(plan=plan)
    assert physical.claims == 0 and scored.contacts == 0 and store.commits == 0


def test_purpose_unaware_scored_cas_cannot_install_in_joint_first_root():
    from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
    from grading.integration.whole_paper_cas import ProductionWholePaperCAS
    from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
    from grading.contracts.job_state import GradingJobState
    from tests.integration.test_joint_first_claim_connected_execution import (
        connected_first, AtomicConditionalCASFixture, ReadOnlyCASPort,
    )
    from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
    from tests.integration.test_whole_paper_cas import Store, Issuer, OriginalSource
    engine, plan, physical, backend, first = connected_first()
    custody = ProductionPaperAttemptCustody(
        executor=engine, attempts=engine._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    source, store = OriginalSource(), Store()
    with pytest.raises(ValueError, match='Purpose-unaware scored CAS'):
        ProductionWholePaperCAS(
            custody=custody, issuer=Issuer(source), original_source=source,
            store=ReadOnlyCASPort(store), joint_scored_store=AtomicConditionalCASFixture(
                store, first.approval_revision, 'APPROVED-RUNTIME'),
            legal_policy=LegalGradingTransitionPolicy('TEST-F57', 1, (
                (GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),)),
            max_identifier_characters=128, max_questions=10,
            require_academic_preclaim=True)
    assert physical.claims == 0 and store.commits == 0
