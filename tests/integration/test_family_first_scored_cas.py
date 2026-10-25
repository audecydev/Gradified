"""Causal family FIRST -> original physical attempt claim -> deterministic scoring/scorer -> existing purpose-aware CAS."""
from threading import Lock

import pytest

from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import (
    ProductionWholePaperCAS, PaperCASState, PaperCASDecision,
    PaperCASDisposition, ScoredPaperPurpose,
)
from tests.integration.test_whole_paper_family_execution import rig, rig_family
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import Issuer, OriginalSource, Store
from tests.integration.test_joint_first_claim_connected_execution import ReadOnlyCASPort
from tests.integration.test_paper_lifecycle_pre_effect import POLICY


class ConditionalFamilyScoredBackend:
    """Atomic simulated source-state+CAS, NOT a real durable backend conformance proof."""
    def __init__(self, storage, authority, permission_issuer, kind='FIRST'):
        self.lock = Lock()
        self.storage = storage
        self.authority = authority
        self.permission_issuer = permission_issuer
        self.contacts = 0
        self.kind = kind
        self.revoke_at_commit = False
        self.lost_ack = False

    def commit_scored_paper_if_authorized(self, *, transaction, custody, authorities, purpose):
        with self.lock:
            self.contacts += 1
            if self.revoke_at_commit:
                self.permission_issuer.mode = 'DENY'
            valid = (
                type(purpose) is ScoredPaperPurpose
                and purpose.kind == self.kind
                and ((self.kind == 'FIRST' and purpose.permission.predecessor is None
                     and purpose.permission.approval_ref == 'F57-FIRST-APPROVAL')
                     or (self.kind == 'REGRADE' and purpose.permission.predecessor is not None
                         and purpose.permission.approval_ref == 'F57-REGRADE-APPROVAL'
                         and purpose.permission.predecessor.result_ref ==
                            transaction.intent.original_claim_requests[0].predecessor_result_ref))
                and self.permission_issuer.mode == self.kind
                and len(authorities) == len(custody.questions) == len(transaction.intent.question_claims)
                and all(a.academic.issued_paper.approval_revision == self.authority.approval_revision
                        and a.runtime.approval_ref == self.authority.runtime_approval
                        for a in authorities)
            )
            if not valid:
                return PaperCASDecision(transaction, PaperCASDisposition.STALE, None)
            result = self.storage.commit_whole_paper(transaction=transaction, custody=custody)
            if self.lost_ack:
                raise RuntimeError('Simulated scored CAS lost reply after write')
            return result


def connected(kind='DIRECT'):
    root, plan, permission, physical, backend, f25, provider, _ = (rig() if kind == 'DIRECT' else rig_family(kind))
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    source, store = OriginalSource(), Store()
    conditional = ConditionalFamilyScoredBackend(store, f25, f25.f57_source)
    service = ProductionWholePaperCAS(custody=custody, issuer=Issuer(source),
        original_source=source, store=ReadOnlyCASPort(store), legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10,
        require_academic_preclaim=True, purpose_scored_store=conditional)
    return service, plan, permission, physical, backend, f25, provider, store, conditional


@pytest.mark.parametrize('kind,quantity', [('DIRECT',1), ('NUMERIC',1), ('MIXED',2)])
def test_installed_family_first_authentic_claim_score_and_scored_cas(kind, quantity):
    service, plan, permission, physical, backend, f25, provider, store, conditional = connected(kind)
    out = service.execute_and_commit(plan=plan, permission=permission)
    assert out.state is PaperCASState.COMMITTED, (out.state, out.custody.outcome.state)
    assert len(out.transaction.intent.question_claims) == quantity
    assert tuple(req.family for req in out.transaction.intent.original_claim_requests) == tuple(
        q.family for q in plan.questions)
    assert physical.claims == quantity and f25.claim_contacts == quantity
    assert store.commits == 1 and conditional.contacts == 1
    assert out.custody.outcome.result is not None
    assert not out.authorizes_retry and not out.authorizes_publication


def test_revoked_f57_inside_scored_cas_blocks_without_second_commit():
    svc, plan, permission, physical, _, _, _, store, conditional = connected()
    conditional.revoke_at_commit=True
    out=svc.execute_and_commit(plan=plan, permission=permission)
    assert out.state is PaperCASState.BLOCKED
    assert physical.claims==1 and conditional.contacts==1 and store.commits==0


def test_lost_scored_cas_reply_unknown_does_not_duplicate_commit():
    svc,plan,permission,physical,_,_,_,store,conditional=connected()
    conditional.lost_ack=True
    out=svc.execute_and_commit(plan=plan,permission=permission)
    assert out.state is PaperCASState.UNKNOWN and out.transaction is not None
    assert store.commits==1 and conditional.contacts==1
    assert svc.reconcile(outcome=out) is PaperCASState.COMMITTED
    assert store.commits==1 and store.reads==1


def test_no_family_cas_without_exact_first_purpose_no_f25_or_scored_contact():
    svc,plan,permission,physical,_,_,_,store,conditional=connected()
    with pytest.raises(ValueError):
        svc.execute_and_commit(plan=plan)
    assert physical.claims==0 and conditional.contacts==0 and store.commits==0

@pytest.mark.parametrize('kind', ['DIRECT', 'NUMERIC', 'MIXED'])
def test_family_first_through_original_f57_c4_lifecycle(kind):
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
    svc,plan,_,physical,_,f25,provider,store,conditional=connected(kind)
    lifecycle=ProductionPaperLifecycle(cas=svc, permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    out=lifecycle.execute_first(plan=plan)
    assert out.state is PaperLifecycleState.CAS_ACKNOWLEDGED, out.state
    assert out.cas.state is PaperCASState.COMMITTED and store.commits==1
    assert not out.authorizes_publication and not out.authorizes_retry


def connected_regrade(kind="DIRECT"):
    from tests.integration.test_whole_paper_family_execution import MultiPhysical
    from tests.integration.test_paper_lifecycle_pre_effect import Permissions
    from tests.integration.test_paper_lifecycle_regrade import NewRunCASIssuer
    prior_service, old_plan, old_permission, _, _, _, _, storage, _ = connected(kind)
    old=prior_service.execute_and_commit(plan=old_plan, permission=old_permission)
    assert old.state is PaperCASState.COMMITTED

    f57=Permissions()
    f57.mode='REGRADE'
    f57.prior=old.transaction
    f57.custody=old.custody
    class DistinctRegradePhysical(MultiPhysical):
        def claim_fresh_attempt(self, *, request):
            from dataclasses import replace
            from grading.integration.attempt_authority import AttemptClaim
            claim=super().claim_fresh_attempt(request=request)
            if claim.reservation is None:
                return claim
            return AttemptClaim(claim.request,claim.disposition,
                replace(claim.reservation,attempt_id='REGR-'+claim.reservation.attempt_id,
                        reservation_ref='REGR-'+claim.reservation.reservation_ref))
    family_fixture = rig if kind == 'DIRECT' else lambda **kw: rig_family(kind, **kw)
    new_executor,plan,permission,physical,backend,f25,provider,_=family_fixture(
        grading_run_id='NEW-FAMILY-REVIEW-RUN',
        predecessor_ref=old.transaction.result_ref,
        permission_source=f57, physical_store=DistinctRegradePhysical())
    custody=ProductionPaperAttemptCustody(executor=new_executor, attempts=new_executor._attempts,
        request_source=KnownRequests(), max_identifier_characters=128,max_questions=10)
    origin=OriginalSource()
    f25.approval_revision=plan.approval_revision
    f25.runtime_approval='RUNTIME-APPROVAL'
    conditional=ConditionalFamilyScoredBackend(storage, f25, f57, 'REGRADE')
    cas=ProductionWholePaperCAS(custody=custody, issuer=NewRunCASIssuer(origin),
        original_source=origin, store=ReadOnlyCASPort(storage), legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10,
        require_academic_preclaim=True, purpose_scored_store=conditional)
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f57,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    return lifecycle,plan,physical,backend,f25,provider,storage,conditional,old, f57


def test_genuine_family_regrade_prior_cas_read_f25_new_ids_and_scored_cas():
    from grading.integration.paper_lifecycle import PaperLifecycleState
    lifecycle,plan,physical,backend,f25,provider,storage,conditional,old,_=connected_regrade()
    out=lifecycle.execute_regrade(plan=plan)
    assert out.state is PaperLifecycleState.CAS_ACKNOWLEDGED, out.state
    assert out.cas.state is PaperCASState.COMMITTED
    assert physical.claims==1 and storage.commits==2 and conditional.contacts==1
    assert out.cas.transaction.request_ref != old.transaction.request_ref
    assert out.cas.transaction.result_ref != old.transaction.result_ref
    assert out.cas.transaction.intent.question_claims[0][1] != old.transaction.intent.question_claims[0][1]
    assert out.cas.transaction.intent.question_claims[0][2] != old.transaction.intent.question_claims[0][2]
    assert not out.authorizes_retry and not out.authorizes_publication


def test_family_regrade_revoked_effect_cannot_contact_scored_cas():
    from grading.integration.paper_lifecycle import PaperLifecycleState
    svc,plan,physical,backend,f25,provider,storage,conditional,_,f57=connected_regrade()
    f25.revoke_inside=True
    out=svc.execute_regrade(plan=plan)
    assert out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and conditional.contacts==0 and storage.commits==1


def test_family_regrade_wrong_predecessor_request_denies_before_claim():
    from grading.integration.paper_lifecycle import PaperLifecycleState
    svc,plan,physical,backend,f25,provider,storage,conditional,_,_=connected_regrade()
    allocator=svc._cas._custody._executor._attempts
    # Installed source deliberately returns a foreign predecessor physical attempt request;
    # the physical attempt claim allocator's own original regrade gate must reject it before effect.
    allocator._identify.__self__.foreign=True
    out=svc.execute_regrade(plan=plan)
    assert out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and conditional.contacts==0 and storage.commits==1

@pytest.mark.parametrize('kind', ['DIRECT', 'NUMERIC', 'MIXED'])
def test_c5_family_source_without_qualified_provider_accounting_stays_unknown(kind):
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
    from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
    from tests.integration.test_original_recovery_complete_paper_gate import _gate
    svc,plan,_,physical,_,f25,_,store,conditional=connected(kind)
    lifecycle=ProductionPaperLifecycle(cas=svc, permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    record=lifecycle.execute_first(plan=plan)
    assert record.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    gate,_,_= _gate(record,store)
    before=(physical.claims,store.commits,store.reads)
    observation=gate.assess()
    assert observation.state is PaperHandoffEligibilityState.UNKNOWN
    assert not observation.authorizes_publication and not observation.authorizes_retry
    assert (physical.claims,store.commits)==before[:2]


def test_mixed_second_physical_revocation_is_unknown_and_never_scores_or_commits():
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
    svc, plan, _, physical, _, f25, provider, store, conditional = connected('MIXED')
    f25.revoke_after_first = True
    lifecycle = ProductionPaperLifecycle(cas=svc, permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    out = lifecycle.execute_first(plan=plan)
    assert out.state is PaperLifecycleState.UNKNOWN
    assert out.cas is not None and out.cas.custody.outcome.state == 'INDETERMINATE'
    assert out.cas.custody.outcome.result is None
    assert len(out.cas.custody.outcome.observed_reservations) == 1
    assert physical.claims == 1 and store.commits == 0 and conditional.contacts == 0
    assert not out.authorizes_publication and not out.authorizes_retry

def test_mixed_later_question_missing_evidence_cannot_consume_first_f25():
    from tests.integration.test_whole_paper_family_execution import rig_family
    from dataclasses import replace
    executor,plan,permission,physical,backend,f25,provider,source=rig_family('MIXED')
    old=source.inputs
    # Invalid later-question evidence belongs to the already-admitted paper:
    # even the first physical attempt claim must not start.
    # Source-returned explicit paper operation mismatch is a legitimate
    # full-paper preflight rejection independent of any provider output.
    source.inputs=replace(old,operations=(old.operations[0],old.operations[0]))
    outcome=executor.execute_first(plan=plan,permission=permission)
    assert outcome.state=='DENIED' and outcome.result is None
    assert physical.claims==0 and f25.claim_contacts==0 and len(provider.requests)==0


@pytest.mark.parametrize('kind', ['NUMERIC','MIXED'])
def test_numeric_and_mixed_regrade_reuses_real_predecessor_and_new_cas(kind):
    from grading.integration.paper_lifecycle import PaperLifecycleState
    lifecycle,plan,physical,backend,f25,provider,storage,conditional,old,_=connected_regrade(kind)
    result=lifecycle.execute_regrade(plan=plan)
    assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED, result.state
    assert result.cas.state is PaperCASState.COMMITTED
    assert physical.claims==len(plan.questions) and storage.commits==2
    assert result.cas.transaction.intent.plan.request.grading_run_id != old.transaction.intent.plan.request.grading_run_id
    assert not result.authorizes_publication and not result.authorizes_retry


def test_mixed_regrade_revoked_after_first_original_claim_no_second_effect():
    from grading.integration.paper_lifecycle import PaperLifecycleState
    svc,plan,physical,backend,f25,provider,storage,cas,old,_=connected_regrade('MIXED')
    f25.revoke_after_first=True
    out=svc.execute_regrade(plan=plan)
    assert out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and cas.contacts==0 and storage.commits==1
    assert not out.authorizes_publication and not out.authorizes_retry
