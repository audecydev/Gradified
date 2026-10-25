"""Permanent source-falsification regressions for exact effectful whole-paper.

These checks were derived from three separate reviews of tree 4528503d...;
reviewer failures were independently reproduced against its unchanged bytes.
Fixtures are not authenticated school or durable physical-attempt backends.
"""
from dataclasses import replace

import pytest

from grading.integration.attempt_authority import (
    ClaimedAttemptAllocator, AttemptClaim, AttemptClaimDisposition,
)
from grading.integration.evaluator_invocation import AttemptReservation
from tests.integration.test_attempt_authority import AtomicStore, Issuer
from tests.integration.test_whole_paper_choice_execution import _setup_one, _setup_two


@pytest.mark.parametrize("disposition", [
    AttemptClaimDisposition.REPLAY, AttemptClaimDisposition.CONFLICT,
    AttemptClaimDisposition.REVOKED, AttemptClaimDisposition.EXPIRED,
])
def test_post_commit_nonfresh_with_reservation_is_uncertain(disposition):
    root, plan, *_ = _setup_one()

    class ContradictoryStore(AtomicStore):
        def claim_fresh_attempt(self, *, request):
            real = super().claim_fresh_attempt(request=request)
            assert real.disposition is AttemptClaimDisposition.FRESH
            return AttemptClaim(request, disposition, real.reservation)

    store = ContradictoryStore()
    object.__setattr__(root, '_attempts', ClaimedAttemptAllocator(
        issuer=Issuer(), store=store, max_identifier_characters=128))
    result = root.execute(plan=plan)
    assert result.state == 'INDETERMINATE' and result.failure_kind == 'UNKNOWN'
    assert result.result is None and result.completed == ()
    assert store.claims == 1 and len(store.claimed) == 1
    assert len(result.contact_trace) == 1
    assert result.contact_trace[0].f25_call_started
    assert not result.contact_trace[0].evaluator_invoked
    assert result.contact_trace[0].request_ref == 'BACKEND-STABLE-REQUEST-REF'


def test_ordinary_allocator_class_swap_cannot_fake_a_physical_claim():
    root, plan, issuer, fresh, runtime, store = _setup_one()

    class ForgedAllocator(ClaimedAttemptAllocator):
        __slots__ = ()

        def begin_operation(self):
            return object()

        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id, eligibility_policy_version):
            return AttemptReservation(scope, 'FORGED-ATT', 'FORGED-RES', family,
                runtime_id, runtime_version, implementation_ref,
                eligibility_policy_id, eligibility_policy_version, 'FORGED-REQUEST')

        def finish_operation(self, *, token):
            return None

    attempted = []

    def swap(_plan):
        attempted.append(True)
        root._attempts.__class__ = ForgedAllocator

    issuer.action = swap
    outcome = root.execute(plan=plan)
    assert outcome.state != 'COMPLETE' and outcome.result is None, (
        'A forged allocator must never complete scoring without a genuine attempt reservation.')
    assert store.claims == 0 and outcome.completed == ()
    assert attempted
    assert type(root._attempts) is ClaimedAttemptAllocator


def test_original_f25_allocator_cannot_change_class_by_normal_assignment():
    root, *_ = _setup_one()

    class Forged(ClaimedAttemptAllocator):
        __slots__ = ()

    with pytest.raises(AttributeError):
        root._attempts.__class__ = Forged
    assert type(root._attempts) is ClaimedAttemptAllocator


def _q2_paper_refresh(*, change_question=None, change_paper=None):
    root, plan, issuer, fresh, runtime, store = _setup_two()
    def change(_plan):
        # Q1 must already be physically claimed AND the genuine Q2
        # confirmation must have occurred. A post-claim issuer recheck is
        # allowed between Q1 claim and Q1 grading; do not trigger there.
        # This preserves the original Q2-after-Q1 hostile case without
        # tying the test to issuer-read ordinals.
        if store.claims == 1 and fresh.calls == 2:
            current = issuer.relation
            if change_question is not None:
                updated_q1 = replace(current.questions[0], **change_question)
                current = replace(current, questions=(updated_q1, current.questions[1]))
            if change_paper is not None:
                current = replace(current, **change_paper)
            issuer.relation = current
    issuer.action = change
    return root.execute(plan=plan), store


@pytest.mark.parametrize('question_edit', [
    {'rubric_ref': 'NEW-Q1-RUBRIC'},
    {'scoring_policy_ref': 'NEW-Q1-POLICY'},
    {'answer_region_ref': 'NEW-Q1-REGION'},
    {'source_revision': 'NEW-Q1-SOURCE-REVISION'},
])
def test_late_issuer_change_to_already_graded_question_prevents_second_claim(question_edit):
    outcome, store = _q2_paper_refresh(change_question=question_edit)
    assert outcome.state != 'COMPLETE' and outcome.result is None
    assert len(outcome.completed) == 1 and store.claims == 1
    assert len(outcome.observed_reservations) == 1
    assert len(outcome.contact_trace) == 1
    assert outcome.contact_trace[0].s1_verified


@pytest.mark.parametrize('paper_edit', [
    {'issuer_ref': 'NEW-ISSUER'},
    {'issuance_ref': 'NEW-ISSUANCE'},
    {'approval_revision': 'NEW-APPROVAL-REVISION'},
    {'source_revision': 'NEW-SOURCE-REVISION'},
])
def test_late_issuer_change_to_whole_paper_blocks_second_claim(paper_edit):
    outcome, store = _q2_paper_refresh(change_paper=paper_edit)
    assert outcome.state != 'COMPLETE' and outcome.result is None
    assert len(outcome.completed) == 1 and store.claims == 1
    assert len(outcome.contact_trace) == 1 and outcome.contact_trace[0].s1_verified


def test_stable_paper_still_executes_both_real_claims_and_full_score():
    outcome, store = _q2_paper_refresh()
    assert outcome.state == 'COMPLETE' and outcome.result is not None
    assert len(outcome.completed) == 2 and store.claims == 2
    assert len(outcome.contact_trace) == 2
    assert all(x.f25_call_started and x.reservation_validated
               and x.evaluator_invoked and x.judgments_emitted and x.s1_verified
               for x in outcome.contact_trace)
