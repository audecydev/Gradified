"""Single governed scored-paper handoff read-only predicate for genuine graded retry, never publication."""
from dataclasses import replace
from grading.integration.paper_retry_grading import GradedRetryState
from grading.integration.scored_paper_promotion import ProductionPaperPromotion,PaperHandoffEligibilityState
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery,PaperCASState
from grading.integration.paper_accounting import ProductionPaperAccounting
from grading.integration.paper_provider_inventory import (
    ProductionProviderInventory,OriginalProviderInventory,PhysicalAttemptObservation)
from tests.integration.test_authorized_retry_graded_retry_real import graded_rig
from tests.integration.test_original_recovery_complete_paper_gate import FixedLifecycleOriginal,FixedPaperOriginal
from tests.integration.test_scored_paper_promotion_physical_inventory_join import Original as InventorySource
from tests.integration.test_paper_lifecycle_pre_effect import POLICY
from tests.integration.test_authorized_retry_claim import RETRY_PURPOSE


def make():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    history=graded.execute_and_commit(plan=plan)
    assert history.cas is not None
    fixed=FixedLifecycleOriginal(history)
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(history.cas.transaction),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    accounting=ProductionPaperAccounting(operations=(),max_identifier_characters=128)
    paper=history.custody
    fact=OriginalProviderInventory(paper.plan,paper.outcome.issued_paper,
        tuple(PhysicalAttemptObservation(q.question_id,q.f25_call_started,
            q.original_f25_request,q.reservation) for q in paper.questions),
        'NATIVE-RETRY-CHOICE',(),(),True)
    physical_inventory=ProductionProviderInventory(
        original_source=InventorySource(fact),max_identifier_characters=128,max_questions=10)
    gate=ProductionPaperPromotion(original_source=fixed,audit_recovery=durable,
        accounting=accounting,legal_policy=POLICY,max_identifier_characters=128,
        max_questions=10,retry_purpose_policy=RETRY_PURPOSE,
        retry_original_recovery=graded._claims._recovery,
        physical_accounting=physical_inventory)
    return gate,fixed,history,store,physical,unused_f25


def test_genuine_preclaimed_graded_retry_current_and_original_read_only_join():
    gate,fixed,history,store,physical,unused_f25=make()
    reads=store.reads
    result=gate.assess()
    assert result.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, result.state
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,1)
    assert store.reads==reads+1
    assert not result.authorizes_publication and not result.authorizes_retry


def test_foreign_original_run_and_f57_grant_block_before_current_cas_read():
    gate,fixed,history,store,physical,unused_f25=make()
    fixed.original=replace(history,authorization=replace(
        history.authorization,policy_id='FOREIGN-RETRY-F57'))
    before=store.reads
    assert gate.assess().state is PaperHandoffEligibilityState.BLOCKED
    assert store.reads==before


def test_conflicting_retry_physical_reservation_prevents_handoff():
    gate,fixed,history,store,physical,unused_f25=make()
    forged=replace(history.physical.claimed[0],new_request_ref='FOREIGN-REQUEST')
    fixed.original=replace(history,physical=replace(history.physical,claimed=(
        forged,*history.physical.claimed[1:])))
    before=store.reads
    assert gate.assess().state is PaperHandoffEligibilityState.BLOCKED
    assert store.reads==before


def test_missing_independently_sourced_original_is_not_eligible():
    gate,fixed,history,store,physical,unused_f25=make()
    # Validate absent configured source at construction instead: this exact
    # consumer requires installed retry original recovery.
    second=ProductionPaperPromotion(original_source=fixed,
        audit_recovery=gate._audit,accounting=gate._accounting,legal_policy=POLICY,
        max_identifier_characters=128,max_questions=10)
    assert second.assess().state is PaperHandoffEligibilityState.BLOCKED


def test_lost_cas_reply_uses_only_fixed_original_read_to_restore_handoff():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,source,fresh=graded_rig()
    store.mode='CRASH'
    history=graded.execute_and_commit(plan=plan)
    assert history.state is GradedRetryState.UNKNOWN
    assert history.cas.transaction is not None
    source=FixedLifecycleOriginal(history)
    durable=ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(history.cas.transaction),store=store,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    acc=ProductionPaperAccounting(operations=(),max_identifier_characters=128)
    gate=ProductionPaperPromotion(original_source=source,audit_recovery=durable,
        accounting=acc,legal_policy=POLICY,max_identifier_characters=128,
        max_questions=10,retry_purpose_policy=RETRY_PURPOSE,
        retry_original_recovery=graded._claims._recovery)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims,unused_f25.claims,store.commits)==(2,0,1)
