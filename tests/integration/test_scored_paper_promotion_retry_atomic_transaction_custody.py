"""Independent historical retry inventory attacks; governed scored-paper handoff must re-check authorized retry claim invariants.

These cases run through the genuine two-question CHOICE graded retry fixture.
The only manipulated values are fixed-origin historical snapshots, not an
issuer or an executable service installation. No production backend guarantee
is assumed by this suite.
"""
from dataclasses import replace

import pytest

from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState, ProductionPaperPromotion
from grading.integration.paper_retry_grading import GradedRetryState
from grading.integration.paper_accounting import ProductionPaperAccounting
from grading.integration.whole_paper_cas import ProductionPaperCASDurableRecovery
from tests.integration.test_scored_paper_retry_handoff import make
from tests.integration.test_authorized_retry_graded_retry_real import graded_rig
from tests.integration.test_original_recovery_complete_paper_gate import FixedLifecycleOriginal, FixedPaperOriginal
from tests.integration.test_paper_lifecycle_pre_effect import POLICY
from tests.integration.test_authorized_retry_claim import RETRY_PURPOSE


@pytest.mark.parametrize('bad', ('duplicate', 'none', 'integer', 'empty', 'too_long', 'whitespace', 'foreign_record'))
def test_fixed_history_rejects_malformed_retry_atomic_transaction_before_audit_read(bad):
    gate, fixed, history, store, physical, unused_f25 = make()
    claims = history.physical.claimed
    assert len(claims) == 2 and claims[0].transaction_ref != claims[1].transaction_ref
    wrong = {
        'duplicate': claims[0].transaction_ref,
        'none': None,
        'integer': 1,
        'empty': '',
        'too_long': 'X' * 129,
        'whitespace': ' MISMATCH ',
    }
    if bad == 'foreign_record':
        changed = (claims[0], object())
    else:
        changed = (claims[0], replace(claims[1], transaction_ref=wrong[bad]))
    fixed.original = replace(history, physical=replace(history.physical, claimed=changed))
    before_reads, before_commits, before_claims = store.reads, store.commits, physical.claims
    outcome = gate.assess()
    assert outcome.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == before_reads, 'Unvalidated retry history caused an avoidable CAS read'
    assert store.commits == before_commits and physical.claims == before_claims
    assert not outcome.authorizes_retry and not outcome.authorizes_publication
    assert unused_f25.claims == 0


@pytest.mark.parametrize('bad', ('duplicate', 'none', 'foreign_record'))
def test_lost_cas_response_rejects_malformed_retry_inventory_before_recovery(bad):
    graded, plan, physical, auth, academic, atomic, store, unused_f25, source, fresh = graded_rig()
    store.mode = 'CRASH'
    history = graded.execute_and_commit(plan=plan)
    assert history.state is GradedRetryState.UNKNOWN and history.cas.transaction is not None
    claims = history.physical.claimed
    changed = (claims[0], object()) if bad == 'foreign_record' else (
        claims[0], replace(claims[1], transaction_ref=(claims[0].transaction_ref if bad == 'duplicate' else None)))
    fixed = FixedLifecycleOriginal(replace(history, physical=replace(history.physical, claimed=changed)))
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(history.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    accounts = ProductionPaperAccounting(operations=(), max_identifier_characters=128)
    gate = ProductionPaperPromotion(
        original_source=fixed, audit_recovery=durable, accounting=accounts,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10,
        retry_purpose_policy=RETRY_PURPOSE,
        retry_original_recovery=graded._claims._recovery)
    before_reads, before_commits, before_claims = store.reads, store.commits, physical.claims
    outcome = gate.assess()
    assert outcome.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == before_reads
    assert store.commits == before_commits and physical.claims == before_claims
    assert unused_f25.claims == 0
    assert not outcome.authorizes_retry and not outcome.authorizes_publication


def test_valid_acknowledged_retry_still_eligible_for_governed_handoff():
    gate, fixed, history, store, physical, unused_f25 = make()
    outcome = gate.assess()
    assert outcome.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert physical.claims == 2 and unused_f25.claims == 0 and store.commits == 1
    assert not outcome.authorizes_retry and not outcome.authorizes_publication


def test_valid_lost_ack_retry_still_eligible_with_genuine_original_cas_recovery():
    graded, plan, physical, auth, academic, atomic, store, unused_f25, source, fresh = graded_rig()
    store.mode = 'CRASH'
    history = graded.execute_and_commit(plan=plan)
    assert history.state is GradedRetryState.UNKNOWN
    fixed = FixedLifecycleOriginal(history)
    durable = ProductionPaperCASDurableRecovery(
        original_source=FixedPaperOriginal(history.cas.transaction), store=store,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    accounts = ProductionPaperAccounting(operations=(), max_identifier_characters=128)
    gate = ProductionPaperPromotion(
        original_source=fixed, audit_recovery=durable, accounting=accounts,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10,
        retry_purpose_policy=RETRY_PURPOSE,
        retry_original_recovery=graded._claims._recovery)
    outcome = gate.assess()
    assert outcome.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims, unused_f25.claims, store.commits) == (2, 0, 1)
    assert not outcome.authorizes_retry and not outcome.authorizes_publication

@pytest.mark.parametrize('field', ('family', 'request_ref', 'session_scope',
                                   'predecessor_result_ref', 'regrade_approval_ref',
                                   'policy_version', 'runtime_id'))
def test_recovered_retry_reservation_must_match_entire_original_f25_request(field):
    gate, fixed, history, store, physical, unused_f25 = make()
    claims = history.physical.claimed
    original = claims[1].reservation
    if field == 'session_scope':
        changed = replace(original, scope=replace(original.scope, session_ref='OTHER-SESSION'))
    elif field == 'family':
        changed = replace(original, family='DIRECT')
    elif field == 'request_ref':
        changed = replace(original, request_ref='FOREIGN-REQUEST')
    elif field == 'predecessor_result_ref':
        changed = replace(original, predecessor_result_ref='FOREIGN-RESULT')
    elif field == 'regrade_approval_ref':
        changed = replace(original, regrade_approval_ref='FOREIGN-F57')
    elif field == 'policy_version':
        changed = replace(original, eligibility_policy_version=original.eligibility_policy_version + 1)
    elif field == 'runtime_id':
        changed = replace(original, runtime_id='FOREIGN-RUNTIME')
    fixed.original = replace(history, physical=replace(history.physical, claimed=(
        claims[0], replace(claims[1], reservation=changed))))
    before_reads, before_commits, before_claims = store.reads, store.commits, physical.claims
    outcome = gate.assess()
    assert outcome.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == before_reads
    assert (store.commits, physical.claims, unused_f25.claims) == (
        before_commits, before_claims, 0)
    assert not outcome.authorizes_retry and not outcome.authorizes_publication
