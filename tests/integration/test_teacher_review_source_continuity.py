"""Original teacher-review selection must survive current-decision resolution.

Causal regression for the independently reproduced wrong-question journal effect.
"""
from dataclasses import replace

from grading.integration.teacher_review_journal import (
    OriginalTeacherReviewCase, SchoolTeacherReviewDecision,
    ProductionTeacherReviewJournal, ProductionTeacherReviewRecovery,
    TeacherReviewState, TeacherReviewRecoveryState,
)
from tests.integration.test_teacher_review_original_append import setup_review, POLICY
from tests.integration.test_teacher_review_durable_recovery import OriginalDecision, HistoricalJournal


def _second_decision(case, original_decision):
    t = case.original_cas.transaction
    rows = t.intent.result.paper_score.question_results
    assert len(rows) == 2, 'requires genuine two-question scored paper'
    q2 = next(q for q in rows if q.question_id != case.question_id)
    return replace(original_decision, question_id=q2.question_id,
                   original_rubric_ref=q2.rubric_ref.id,
                   original_rubric_version=q2.rubric_ref.version)


class MutateOriginalInTeacherRead:
    def __init__(self, original_source, substitute):
        self.original_source, self.substitute, self.calls = original_source, substitute, 0

    def resolve_current_teacher_review_decision(self):
        self.calls += 1
        object.__setattr__(self.original_source.value, 'question_id', self.substitute.question_id)
        return self.substitute


def test_original_selection_substitution_during_teacher_read_never_contacts_journal():
    _, source, teacher, journal, *_ = setup_review()
    first_id = source.value.question_id
    q2_decision = _second_decision(source.value, teacher.value)
    hostile = MutateOriginalInTeacherRead(source, q2_decision)
    owner = ProductionTeacherReviewJournal(original_source=source, teacher_source=hostile,
        journal=journal, legal_policy=POLICY, max_identifier_characters=128)
    observed = owner.record()
    assert first_id != q2_decision.question_id
    assert not journal.requests, 'FORBIDDEN FIRST EFFECT: substituted original journal append'
    assert observed.state is TeacherReviewState.BLOCKED


def test_original_teacher_accept_commits_once_without_grade_change():
    review, source, teacher, journal, physical, store, score = setup_review()
    prev = physical.claims, store.commits, score.final_score.to_canonical_string()
    answer = review.record()
    assert answer.state is TeacherReviewState.COMMITTED
    assert len(journal.requests) == 1
    assert (physical.claims, store.commits, score.final_score.to_canonical_string()) == prev
    assert not answer.authorizes_publication and not answer.changes_official_grade


def test_original_changed_during_historical_decision_read_no_journal_read():
    _, source, teacher, append_journal, *_ = setup_review()
    reader = HistoricalJournal()
    class MutatingHistorical:
        def resolve_original_teacher_review_decision(self):
            object.__setattr__(source.value, 'question_id', 'Q-UNAUTHORIZED')
            return teacher.value
    owner = ProductionTeacherReviewRecovery(original_source=source,
        original_decision_source=MutatingHistorical(), journal_reader=reader,
        legal_policy=POLICY, max_identifier_characters=128)
    answer = owner.reconcile()
    assert answer.state is TeacherReviewRecoveryState.UNKNOWN
    assert reader.calls == 0


def test_historical_read_only_committed_no_append():
    _, source, teacher, append_journal, physical, store, _ = setup_review()
    reader = HistoricalJournal()
    owner = ProductionTeacherReviewRecovery(original_source=source,
        original_decision_source=OriginalDecision(teacher.value), journal_reader=reader,
        legal_policy=POLICY, max_identifier_characters=128)
    before = physical.claims, store.commits
    answer = owner.reconcile()
    assert answer.state is TeacherReviewRecoveryState.COMMITTED
    assert reader.calls == 1 and append_journal.requests == []
    assert (physical.claims, store.commits) == before
    assert not answer.authorizes_reappend and not answer.changes_official_grade
