"""Fixed-original teacher review recorded decision conformance; no journal writes or publication."""
from dataclasses import replace
import pytest

from grading.integration.recovered_teacher_review_candidate import (
    ProductionRecoveredTeacherReviewCandidate, RecoveredTeacherReviewState,
)
from grading.integration.teacher_review_journal import (
    OriginalTeacherReviewCase, SchoolTeacherReviewDecision, TeacherReviewAction,
    ProductionTeacherReviewRecovery, TeacherReviewRecoveryState,
)
from tests.integration.test_teacher_review_original_append import Original
from tests.integration.test_teacher_review_durable_recovery import OriginalDecision, HistoricalJournal
from tests.integration.test_recovered_original_governance import setup_scored


def rig():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    history = qualified._c5._original.__self__.original
    cas = history.cas
    tx = cas.transaction
    receipt = cas.receipt
    qid = tx.intent.plan.questions[0].request.question_id
    case = OriginalTeacherReviewCase(receipt, qid)
    score = next(q for q in tx.intent.result.paper_score.question_results if q.question_id == qid)
    decision = SchoolTeacherReviewDecision(
        'G3-DECISION-1', 'SCHOOL-TEACHER', tx.intent.plan.request.tenant_ref,
        tx.intent.plan.request.grading_run_id, tx.intent.plan.request.submission_ref,
        qid, tx.result_ref, receipt.commit_ref, score.rubric_ref.id,
        score.rubric_ref.version, 'APPROVAL-1', 1, TeacherReviewAction.ACCEPT_ORIGINAL)
    original_source = Original(case)
    teacher_source = OriginalDecision(decision)
    journal = HistoricalJournal()
    recovery_teacher = ProductionTeacherReviewRecovery(
        original_source=original_source,
        original_decision_source=teacher_source,
        journal_reader=journal,
        legal_policy=qualified._c5._policy,
        max_identifier_characters=qualified._c5._maximum,
    )
    candidate = ProductionRecoveredTeacherReviewCandidate(
        recovery=recovery, teacher_recovery=recovery_teacher)
    return candidate, recovery, original_source, teacher_source, journal, before, physical, store, conditional


def test_same_scored_original_historical_teacher_review_candidate_is_read_only():
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    result = owner.assess()
    assert result.state is RecoveredTeacherReviewState.RECORDED_CANDIDATE
    assert result.original == recovery._target.__self__.identity
    assert result.review.state is TeacherReviewRecoveryState.COMMITTED
    assert len(journal.requests) == 1
    assert (physical.claims, store.commits, conditional.contacts) == before
    assert not result.authorizes_official_mark_change
    assert not result.authorizes_publication and not result.authorizes_retry
    assert not result.authorizes_reappend


@pytest.mark.parametrize('field', ('tenant_ref','grading_run_id',
    'original_scored_result_ref', 'source_revision','transaction_ref',
    'transaction_event_ref','commit_ref'))
def test_foreign_fixed_teacher_original_must_not_reach_journal(field):
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    selected = recovery._target.__self__.identity
    # Independent pending-original source remains a valid confirmed governed scored-paper handoff original.
    # The historical teacher original is for a DIFFERENT result / journal.
    receipt = original.value.original_cas
    tx = receipt.transaction
    if field == 'commit_ref':
        original.value = replace(original.value, original_cas=replace(receipt,
            commit_ref='OTHER-COMMIT'))
    elif field in ('transaction_ref','transaction_event_ref','original_scored_result_ref'):
        txfield={'transaction_ref':'request_ref', 'transaction_event_ref':'event_ref',
                 'original_scored_result_ref':'result_ref'}[field]
        other = replace(tx, **{txfield:'OTHER'})
        original.value = replace(original.value, original_cas=replace(receipt,transaction=other))
    else:
        plan = tx.intent.plan
        req = plan.request
        if field=='source_revision':
            otherplan = replace(plan,source_revision='OTHER')
        else:
            otherplan = replace(plan,request=replace(req,**{field:'OTHER'}))
        otherintent = replace(tx.intent,plan=otherplan)
        original.value = replace(original.value, original_cas=replace(receipt,
            transaction=replace(tx,intent=otherintent)))
    assert owner.assess().state is RecoveredTeacherReviewState.UNKNOWN
    assert journal.calls == 0
    assert (physical.claims, store.commits, conditional.contacts) == before


@pytest.mark.parametrize('status',(TeacherReviewRecoveryState.ABSENCE_REPORTED,
    TeacherReviewRecoveryState.CONFLICT,TeacherReviewRecoveryState.UNKNOWN))
def test_unconfirmed_journal_is_not_a_recorded_candidate(status):
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    journal.state = status
    assert owner.assess().state is RecoveredTeacherReviewState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_recovered_original_changes_during_journal_read_refuses_recorded_candidate():
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    pending=recovery._target.__self__
    prior=pending.identity
    def move():
        pending.identity = replace(prior, original_scored_result_ref='OTHER')
    original_reconcile=journal.reconcile_teacher_review
    class MovingJournal:
        def reconcile_teacher_review(self, *, request):
            move()
            return original_reconcile(request=request)
    # Use a fresh, separately installed reader. Do not mutate production owner.
    altered=ProductionTeacherReviewRecovery(
        original_source=original, original_decision_source=teacher,
        journal_reader=MovingJournal(), legal_policy=recovery._c5._policy,
        max_identifier_characters=recovery._c5._maximum)
    owner2=ProductionRecoveredTeacherReviewCandidate(recovery=recovery,teacher_recovery=altered)
    assert owner2.assess().state is RecoveredTeacherReviewState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_reader_unavailable_requires_unknown_without_reappend():
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    journal.alter='timeout'
    assert owner.assess().state is RecoveredTeacherReviewState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_wrong_comparison_target_is_rejected_before_fixed_journal_read():
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    with pytest.raises(ValueError):
        owner._teacher.reconcile(expected_original=object())
    assert journal.calls == 0


def test_standalone_committed_review_of_other_valid_original_cannot_qualify_recovery():
    # Both histories are individually valid. Prior unjoined API legitimately
    # reports COMMITTED for its own original; it is not a grant for this score.
    from tests.integration.test_teacher_review_durable_recovery import installed
    owner, recovery, original, teacher, journal, before, physical, store, conditional = rig()
    foreign, foreign_original, foreign_decision, foreign_journal, *_ = installed()
    assert foreign.reconcile().state is TeacherReviewRecoveryState.COMMITTED
    joined = ProductionRecoveredTeacherReviewCandidate(
        recovery=recovery, teacher_recovery=foreign)
    previous_reads = foreign_journal.calls
    assert joined.assess().state is RecoveredTeacherReviewState.UNKNOWN
    assert foreign_journal.calls == previous_reads  # different original refused pre-read
    assert (physical.claims, store.commits, conditional.contacts) == before
