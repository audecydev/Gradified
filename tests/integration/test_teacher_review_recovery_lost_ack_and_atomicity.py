"""Connected source-shaped journal simulation (not a real database conformance pass)."""
from dataclasses import replace
from threading import Event
from concurrent.futures import ThreadPoolExecutor

from grading.integration.teacher_review_journal import (
    ProductionTeacherReviewJournal, ProductionTeacherReviewRecovery,
    TeacherReviewAction, TeacherReviewState, TeacherReviewAppendReply,
    TeacherReviewAppendReceipt, TeacherReviewRecoveryState,
    TeacherReviewJournalRecovery,
)
from tests.integration.test_teacher_review_original_append import setup_review, POLICY
from tests.integration.test_teacher_review_durable_recovery import OriginalDecision


class AtomicSimulatedJournal:
    """In-memory compare-and-write fixture; NOT evidence of backend atomicity.

    The same original receipt and teacher approval are checked within the
    simulated write lock before the event is created. Used to test that the
    engine's read-only recovery can find an actual earlier simulated effect.
    """
    def __init__(self, historical):
        from threading import Lock
        self._lock=Lock()
        self.historical=historical
        self.recorded=None
        self.append_calls=0
        self.read_calls=0
        self.lose_ack=True
    def append_teacher_review_if_current(self, *, request):
        with self._lock:
            self.append_calls+=1
            if (type(request.decision.approval_version) is not int
                    or request.decision.approval_version != self.historical.approval_version
                    or request.decision.decision_ref != self.historical.decision_ref
                    or request.original.original_cas.commit_ref != self.historical.original_commit_ref):
                return TeacherReviewAppendReply(TeacherReviewState.BLOCKED)
            if self.recorded is None:
                self.recorded = TeacherReviewAppendReceipt(request.decision.decision_ref,
                    request.original.original_cas.transaction.result_ref,
                    request.original.original_cas.commit_ref, 'DURABLE-SIM-EVENT')
            receipt=self.recorded
            if self.lose_ack:
                raise TimeoutError('ack lost after simulated append')
            return TeacherReviewAppendReply(TeacherReviewState.COMMITTED, receipt)
    def reconcile_teacher_review(self, *, request):
        with self._lock:
            self.read_calls+=1
            state=(TeacherReviewRecoveryState.COMMITTED if self.recorded is not None
                   else TeacherReviewRecoveryState.ABSENCE_REPORTED)
            return TeacherReviewJournalRecovery(state, request, self.recorded)


def test_lost_ack_after_effect_then_independent_fixed_original_read_recovers_without_reappend():
    review,original,teacher,ignored,physical,store,score=setup_review()
    journal=AtomicSimulatedJournal(teacher.value)
    writer=ProductionTeacherReviewJournal(original_source=original,teacher_source=teacher,
        journal=journal,legal_policy=POLICY,max_identifier_characters=128)
    original_decision=OriginalDecision(teacher.value)
    reader=ProductionTeacherReviewRecovery(
        original_source=original,original_decision_source=original_decision,
        journal_reader=journal,legal_policy=POLICY,max_identifier_characters=128)
    prev=(physical.claims,store.commits)
    assert writer.record().state is TeacherReviewState.UNKNOWN
    assert journal.recorded is not None and journal.append_calls==1
    assert writer.record().state is TeacherReviewState.UNKNOWN
    assert reader.reconcile().state is TeacherReviewRecoveryState.COMMITTED
    assert reader.reconcile().journal_event_ref == 'DURABLE-SIM-EVENT'
    assert journal.append_calls==1 and journal.read_calls==2
    assert (physical.claims,store.commits)==prev


def test_atomic_journal_fixture_refuses_transiently_invalid_approval_at_effect_time():
    review,original,teacher,ignored,*_=setup_review()
    journal=AtomicSimulatedJournal(teacher.value)
    from grading.integration.teacher_review_journal import _admit
    request=_admit(original.value,teacher.value,POLICY,128)
    object.__setattr__(request.decision, 'approval_version', True)
    assert journal.append_teacher_review_if_current(request=request).state is TeacherReviewState.BLOCKED
    assert journal.recorded is None
    # Simulates how the effect-side adapter MUST compare current valid values;
    # does not prove a real journal implements this check.


def test_read_concurrency_never_creates_extra_append():
    review,original,teacher,ignored,*_=setup_review()
    journal=AtomicSimulatedJournal(teacher.value)
    historical=OriginalDecision(teacher.value)
    reader=ProductionTeacherReviewRecovery(
        original_source=original,original_decision_source=historical,
        journal_reader=journal,legal_policy=POLICY,max_identifier_characters=128)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:reader.reconcile().state,range(12)))
    assert all(x in (TeacherReviewRecoveryState.ABSENCE_REPORTED,
                     TeacherReviewRecoveryState.UNKNOWN) for x in results)
    assert journal.append_calls==0 and journal.recorded is None
