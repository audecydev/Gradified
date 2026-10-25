"""Adversarial tests for feedback candidate safety under hostile external callbacks."""
from grading.integration import student_safe_feedback as feedback_mod
from grading.integration.student_safe_feedback import (
    FeedbackOriginal, ConfirmedErrorEvidence, FeedbackCategory,
    IssuedErrorAssessment, ProductionStudentFeedback,
)
class FeedbackInventoryReader:
    def read_feedback_inventory(self, *, original):
        from grading.integration.student_safe_feedback import IssuedFeedbackInventory
        return IssuedFeedbackInventory(original, ('C',), ('E',))

KEY = FeedbackOriginal('TENANT','RUN','RESULT','REV','Q')
EXPECTED='A verified conceptual issue was identified for review.'
UNKNOWN='No evidence-grounded error classification is available.'

def test_mutable_global_message_source_cannot_inject_student_text():
    old = getattr(feedback_mod,'_TEXT',None)
    class Tampering:
        def read_confirmed_error(self,*,original):
            # Equivalent hostile activity on both candidate and proposed copy.
            if hasattr(feedback_mod,'_TEXT'):
                feedback_mod._TEXT[FeedbackCategory.CONCEPTUAL_ERROR]='INJECTED UNAPPROVED STUDENT MESSAGE'
            else:
                feedback_mod._TEXT={FeedbackCategory.CONCEPTUAL_ERROR:'INJECTED UNAPPROVED STUDENT MESSAGE'}
            return IssuedErrorAssessment(original,ConfirmedErrorEvidence(
                FeedbackCategory.CONCEPTUAL_ERROR,'C','E','CONFIRMED'))
    try:
        owner=ProductionStudentFeedback(source=Tampering(),inventory_source=FeedbackInventoryReader(),max_identifier_characters=128)
        result=owner.assess(original=KEY,admitted_criterion_refs=('C',),admitted_evidence_refs=('E',))
        print('MESSAGE_MUTATION_EFFECT',repr(result.message))
        assert result.message in (EXPECTED, UNKNOWN)
    finally:
        if old is None:
            if hasattr(feedback_mod,'_TEXT'):delattr(feedback_mod,'_TEXT')
        else:
            feedback_mod._TEXT=old
            old[FeedbackCategory.CONCEPTUAL_ERROR]=EXPECTED

def test_global_formatter_swap_cannot_inject_student_text():
    previous=feedback_mod.student_safe_feedback
    class Source:
        def read_confirmed_error(self,*,original):
            feedback_mod.student_safe_feedback=lambda **kw: feedback_mod.StudentSafeFeedback(
                original.question_id,FeedbackCategory.CONCEPTUAL_ERROR,'C','E','INJECTED BY CALLBACK')
            return IssuedErrorAssessment(original,ConfirmedErrorEvidence(
                FeedbackCategory.CONCEPTUAL_ERROR,'C','E','CONFIRMED'))
    try:
        owner=ProductionStudentFeedback(source=Source(),inventory_source=FeedbackInventoryReader(),max_identifier_characters=128)
        out=owner.assess(original=KEY,admitted_criterion_refs=('C',),admitted_evidence_refs=('E',))
        print('FORMATTER_SWAP_EFFECT',repr(out.message))
        assert out.message in (EXPECTED,UNKNOWN)
    finally: feedback_mod.student_safe_feedback=previous

def test_legitimate_positive_message_and_category_preserved():
    class Source:
        def read_confirmed_error(self,*,original):
            return IssuedErrorAssessment(original,ConfirmedErrorEvidence(
                FeedbackCategory.CONCEPTUAL_ERROR,'C','E','CONFIRMED'))
    owner=ProductionStudentFeedback(source=Source(),inventory_source=FeedbackInventoryReader(),max_identifier_characters=128)
    out=owner.assess(original=KEY,admitted_criterion_refs=('C',),admitted_evidence_refs=('E',))
    assert out.message == EXPECTED and out.category is FeedbackCategory.CONCEPTUAL_ERROR
    assert not out.authorizes_publication
