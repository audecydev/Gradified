"""teacher review original-key recovery: no append, no new authority and no speculative replay.

All journal fixtures here are simulated; real backend read/append atomicity needs
separate adapter conformance on the installed implementation.
"""
from dataclasses import replace
import pytest

from grading.integration.teacher_review_journal import (
    ConditionalTeacherReviewAppend, OriginalTeacherReviewCase,
    SchoolTeacherReviewDecision, TeacherReviewAppendReceipt,
    TeacherReviewRecoveryState, TeacherReviewJournalRecovery,
    ProductionTeacherReviewRecovery,
)
from tests.integration.test_teacher_review_original_append import setup_review, POLICY


class OriginalDecision:
    def __init__(self, value): self.value, self.calls = value, 0
    def resolve_original_teacher_review_decision(self):
        self.calls += 1
        return self.value


class HistoricalJournal:
    def __init__(self, state=TeacherReviewRecoveryState.COMMITTED):
        self.state, self.calls, self.requests, self.alter = state, 0, [], None
    def reconcile_teacher_review(self, *, request):
        self.calls += 1
        self.requests.append(request)
        if self.alter == 'timeout': raise TimeoutError('private read failure')
        receipt = TeacherReviewAppendReceipt(request.decision.decision_ref,
            request.original.original_cas.transaction.result_ref,
            request.original.original_cas.commit_ref, 'ORIGINAL-EVENT-1')
        if self.alter == 'wrong-decision':
            receipt = replace(receipt, decision_ref='DIFFERENT-DECISION')
        if self.alter == 'wrong-original':
            receipt = replace(receipt, original_commit_ref='DIFFERENT-COMMIT')
        if self.alter == 'mutate-original':
            object.__setattr__(request.original, 'question_id', 'CHANGED')
        if self.alter == 'mutate-decision':
            object.__setattr__(request.decision, 'approval_version', True)
        if self.alter == 'unbound':
            return TeacherReviewJournalRecovery(self.state, replace(request), receipt)
        if self.alter == 'receipt-on-negative':
            return TeacherReviewJournalRecovery(TeacherReviewRecoveryState.ABSENCE_REPORTED,
                request, receipt)
        if self.alter == 'foreign-state':
            return TeacherReviewJournalRecovery('COMMITTED', request, receipt)
        return TeacherReviewJournalRecovery(self.state, request,
            receipt if self.state is TeacherReviewRecoveryState.COMMITTED else None)


def installed(state=TeacherReviewRecoveryState.COMMITTED):
    review, original, current_teacher, append, physical, store, score=setup_review()
    historical_decision = OriginalDecision(current_teacher.value)
    reader = HistoricalJournal(state)
    recovery = ProductionTeacherReviewRecovery(
        original_source=original, original_decision_source=historical_decision,
        journal_reader=reader, legal_policy=POLICY, max_identifier_characters=128)
    return recovery, original, historical_decision, reader, append, physical, store, review


def test_positive_lost_ack_restarted_reader_fixed_original_and_never_reappends():
    recovery, original, historical, reader, append, physical, store, review=installed()
    append.action='THROW'
    assert review.record().state.value=='UNKNOWN'
    before = (len(append.requests), physical.claims, store.commits)
    observed=recovery.reconcile()
    assert observed.state is TeacherReviewRecoveryState.COMMITTED
    assert observed.decision_ref == historical.value.decision_ref
    assert observed.journal_event_ref == 'ORIGINAL-EVENT-1'
    assert not observed.authorizes_reappend and not observed.authorizes_retry
    assert not observed.changes_official_grade and not observed.authorizes_publication
    assert len(reader.requests) == 1 and reader.calls == 1
    assert (len(append.requests),physical.claims,store.commits) == before
    assert original.calls == 2 and historical.calls == 1
    # A second read is allowed but cannot create or reissue an effect.
    assert recovery.reconcile().state is TeacherReviewRecoveryState.COMMITTED
    assert len(reader.requests) == 2 and len(append.requests) == 1


@pytest.mark.parametrize('state',(
    TeacherReviewRecoveryState.ABSENCE_REPORTED,
    TeacherReviewRecoveryState.CONFLICT,
    TeacherReviewRecoveryState.UNKNOWN,
))
def test_negative_or_unknown_never_grants_reappend_or_changes_grade(state):
    recovery, original, hist, reader, append, physical, store, review=installed(state)
    before=(physical.claims, store.commits)
    result=recovery.reconcile()
    assert result.state is state
    assert result.decision_ref is None and result.journal_event_ref is None
    assert not result.authorizes_reappend and not result.changes_official_grade
    assert (physical.claims,store.commits)==before
    assert len(append.requests)==0


@pytest.mark.parametrize('alter', ('timeout','wrong-decision','wrong-original','mutate-original',
                                   'mutate-decision','unbound','receipt-on-negative','foreign-state'))
def test_malformed_or_mutating_journal_read_never_creates_positive_observation(alter):
    recovery, original, historical, reader, append, physical, store, review=installed()
    reader.alter=alter
    result=recovery.reconcile()
    assert result.state is TeacherReviewRecoveryState.UNKNOWN
    assert result.decision_ref is None and result.journal_event_ref is None
    assert append.requests == []
    assert reader.calls==1


@pytest.mark.parametrize('field', ('original_result_ref','original_commit_ref','question_id',
                                   'original_rubric_ref','approval_version','tenant_ref'))
def test_foreign_or_malformed_historical_source_rejected_before_journal(field):
    recovery,original,historical,reader,append,physical,store,review=installed()
    value = True if field == 'approval_version' else 'WRONG'
    historical.value=replace(historical.value, **{field:value})
    assert recovery.reconcile().state is TeacherReviewRecoveryState.UNKNOWN
    assert reader.calls==0 and append.requests==[]


def test_unchanged_original_during_decision_source_is_mandatory():
    recovery, original, historical, reader, append, physical, store, review=installed()
    class SideEffectDecision:
        def resolve_original_teacher_review_decision(self):
            object.__setattr__(original.value,'question_id','FOREIGN')
            return historical.value
    foreign=ProductionTeacherReviewRecovery(
        original_source=original,original_decision_source=SideEffectDecision(),
        journal_reader=reader,legal_policy=POLICY,max_identifier_characters=128)
    assert foreign.reconcile().state is TeacherReviewRecoveryState.UNKNOWN
    assert reader.calls==0


def test_recovery_interface_rejects_unbound_positional_or_foreign_callback():
    recovery, original, historical, reader, append, physical, store, review=installed()
    class Invalid:
        def reconcile_teacher_review(self, request): raise RuntimeError('unreachable')
    with pytest.raises(ValueError):
        ProductionTeacherReviewRecovery(
            original_source=original, original_decision_source=historical,
            journal_reader=Invalid(), legal_policy=POLICY, max_identifier_characters=128)
