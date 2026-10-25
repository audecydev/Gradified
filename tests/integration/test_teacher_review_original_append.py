"""teacher review teacher decision: actual original scored-CAS -> approved decision -> conditional journal.

The fixture is NOT a school authenticator or durable backend. Test the first
forbidden write, original/rubric/mark lineage, and post-contact UNKNOWN.
"""
from dataclasses import replace
import pytest

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.teacher_review_journal import (
    OriginalTeacherReviewCase, SchoolTeacherReviewDecision, TeacherReviewAction,
    TeacherReviewState, TeacherReviewAppendReply, TeacherReviewAppendReceipt,
    ProductionTeacherReviewJournal,
)
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle, POLICY


class Original:
    def __init__(self, value): self.value, self.calls = value, 0
    def resolve_original_teacher_review_case(self):
        self.calls += 1
        return self.value


class Teacher:
    def __init__(self, value): self.value, self.calls = value, 0
    def resolve_current_teacher_review_decision(self):
        self.calls += 1
        return self.value


class Journal:
    def __init__(self, *, action='COMMITTED'):
        self.action = action
        self.requests = []
    def append_teacher_review_if_current(self, *, request):
        self.requests.append(request)
        if self.action == 'THROW':
            raise TimeoutError('PRIVATE postwrite uncertainty')
        if self.action == 'MUTATE':
            object.__setattr__(request.decision, 'approval_version', 999)
        if self.action == 'FOREIGN':
            return TeacherReviewAppendReply(TeacherReviewState.COMMITTED,
                TeacherReviewAppendReceipt('WRONG',request.original.original_cas.transaction.result_ref,
                                           request.original.original_cas.commit_ref,'EVENT'))
        original = request.original.original_cas
        return TeacherReviewAppendReply(TeacherReviewState.COMMITTED,
            TeacherReviewAppendReceipt(request.decision.decision_ref, original.transaction.result_ref,
                                       original.commit_ref, 'REVIEW-EVENT'))


def setup_review():
    engine, plan, physical, cas_store, _ = setup_lifecycle()
    observed = engine.execute_first(plan=plan)
    assert observed.state.value == 'CAS_ACKNOWLEDGED'
    case = OriginalTeacherReviewCase(observed.cas.receipt,
        observed.cas.transaction.intent.plan.questions[0].request.question_id)
    tx = case.original_cas.transaction
    score = next(item for item in tx.intent.result.paper_score.question_results
                 if item.question_id == case.question_id)
    directive = SchoolTeacherReviewDecision(
        'DECISION-1', 'AUTHORIZED-TEACHER', tx.intent.plan.request.tenant_ref,
        tx.intent.plan.request.grading_run_id, tx.intent.plan.request.submission_ref,
        case.question_id, tx.result_ref, case.original_cas.commit_ref,
        score.rubric_ref.id, score.rubric_ref.version, 'TEACHER-APPROVAL', 1,
        TeacherReviewAction.ACCEPT_ORIGINAL)
    source,teacher,journal=Original(case),Teacher(directive),Journal()
    review=ProductionTeacherReviewJournal(original_source=source,teacher_source=teacher,
        journal=journal, legal_policy=POLICY,max_identifier_characters=128)
    return review,source,teacher,journal,physical,cas_store,score


def test_actual_scored_original_teacher_acceptance_only_appends_no_grading_or_publication():
    review,source,teacher,journal,physical,cas_store,score=setup_review()
    before=(physical.claims,cas_store.commits)
    result=review.record()
    assert result.state is TeacherReviewState.COMMITTED
    assert result.decision_ref == 'DECISION-1'
    assert len(journal.requests)==1 and source.calls==teacher.calls==1
    assert (physical.claims,cas_store.commits)==before
    assert not result.authorizes_publication and not result.authorizes_retry
    assert not result.changes_official_grade


def test_source_approved_bounded_teacher_override_is_recorded_without_mutating_frozen_score():
    review,source,teacher,journal,physical,store,score=setup_review()
    previous=score.final_score.to_canonical_string()
    teacher.value=replace(teacher.value,action=TeacherReviewAction.OVERRIDE_MARK,
                          proposed_mark=score.minimum_score, reason_ref='REASON-1')
    result=review.record()
    assert result.state is TeacherReviewState.COMMITTED
    assert score.final_score.to_canonical_string()==previous
    assert journal.requests[0].decision.proposed_mark==score.minimum_score
    assert not result.changes_official_grade


@pytest.mark.parametrize('wrong',('tenant_ref','grading_run_id','submission_ref','question_id',
                                   'original_result_ref','original_commit_ref','original_rubric_ref',
                                   'original_rubric_version','approval_version'))
def test_foreign_original_or_approval_cannot_reach_journal(wrong):
    review,source,teacher,journal,physical,store,score=setup_review()
    change = True if wrong in ('original_rubric_version','approval_version') else 'FOREIGN'
    teacher.value=replace(teacher.value,**{wrong:change})
    assert review.record().state is TeacherReviewState.BLOCKED
    assert journal.requests==[]


def test_override_without_mark_and_accept_with_mark_rejected_before_contact():
    review,src,teacher,journal,*_=setup_review()
    teacher.value=replace(teacher.value,action=TeacherReviewAction.OVERRIDE_MARK)
    assert review.record().state is TeacherReviewState.BLOCKED
    review,src,teacher,journal,*_=setup_review()
    teacher.value=replace(teacher.value,action=TeacherReviewAction.ACCEPT_ORIGINAL,
                          proposed_mark=ScoringDecimal.from_raw(0))
    assert review.record().state is TeacherReviewState.BLOCKED
    assert not journal.requests


def test_out_of_bounds_override_rejected_before_effect():
    review,src,teacher,journal,physical,store,score=setup_review()
    teacher.value=replace(teacher.value,action=TeacherReviewAction.OVERRIDE_MARK,
                          proposed_mark=ScoringDecimal.from_raw(-1))
    assert review.record().state is TeacherReviewState.BLOCKED
    assert journal.requests==[]


def test_altered_original_receipt_fails_before_review_journal():
    review,src,teacher,journal,*_=setup_review()
    case=src.value
    src.value=replace(case,original_cas=replace(case.original_cas,
        committed_ledger_revision=case.original_cas.transaction.expected_ledger_revision))
    assert review.record().state is TeacherReviewState.BLOCKED
    assert not journal.requests


@pytest.mark.parametrize('outcome',('THROW','MUTATE','FOREIGN'))
def test_postcontact_timeout_mutation_or_wrong_ack_unknown_and_not_retried(outcome):
    review,src,teacher,journal,physical,store,score=setup_review()
    journal.action=outcome
    old=(physical.claims,store.commits)
    result=review.record()
    assert result.state is TeacherReviewState.UNKNOWN
    assert len(journal.requests)==1
    assert (physical.claims,store.commits)==old


def test_review_installation_rejects_wrong_callback_signature():
    review,src,teacher,journal,*_=setup_review()
    class InvalidJournal:
        def append_teacher_review_if_current(self, original, *, request):
            raise AssertionError('never')
    with pytest.raises(ValueError):
        ProductionTeacherReviewJournal(original_source=src,teacher_source=teacher,
            journal=InvalidJournal(),legal_policy=POLICY,max_identifier_characters=128)


def test_review_instance_is_one_shot_even_after_lost_journal_ack():
    review, src, teacher, journal, physical, store, score = setup_review()
    journal.action='THROW'
    assert review.record().state is TeacherReviewState.UNKNOWN
    assert review.record().state is TeacherReviewState.UNKNOWN
    assert len(journal.requests)==1
    assert src.calls==teacher.calls==1


def test_review_rejects_original_question_score_not_bound_to_issued_rubric():
    review, src, teacher, journal, physical, store, score=setup_review()
    original=src.value.original_cas
    tx=original.transaction
    revised_score=replace(score, rubric_ref=replace(score.rubric_ref,id='FOREIGN-RUBRIC'))
    old=tx.intent.result
    questions=tuple(revised_score if item.question_id == score.question_id else item
                    for item in old.paper_score.question_results)
    altered_paper=replace(old.paper_score, question_results=questions)
    altered=replace(old,paper_score=altered_paper)
    altered_tx=replace(tx,intent=replace(tx.intent,result=altered))
    src.value=replace(src.value, original_cas=replace(original,transaction=altered_tx))
    assert review.record().state is TeacherReviewState.BLOCKED
    assert journal.requests==[]
