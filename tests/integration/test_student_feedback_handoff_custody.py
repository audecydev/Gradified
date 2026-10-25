"""Causal original-bound feedback acceptance under untrusted installed readers."""
import pytest
import grading.integration.student_safe_feedback as module
from grading.integration.student_safe_feedback import (
    FeedbackOriginal, FeedbackCategory, ConfirmedErrorEvidence,
    IssuedFeedbackInventory, IssuedErrorAssessment, ProductionStudentFeedback,
    StudentSafeFeedback, student_safe_feedback,
)

KEY = FeedbackOriginal('TENANT', 'RUN', 'RESULT', 'SOURCE', 'Q1')
APPROVED = 'A verified conceptual issue was identified for review.'
UNKNOWN = 'No evidence-grounded error classification is available.'
FORGED = 'UNAPPROVED: student-visible fabricated diagnosis'

class Academic:
    def read_confirmed_error(self, *, original):
        return IssuedErrorAssessment(original, ConfirmedErrorEvidence(
            FeedbackCategory.CONCEPTUAL_ERROR, 'C1', 'E1', 'CONFIRMED'))

class Inventory:
    def read_feedback_inventory(self, *, original):
        return IssuedFeedbackInventory(original, ('C1',), ('E1',))

def assess(owner, original=KEY):
    return owner.assess(original=original, admitted_criterion_refs=('C1',),
                        admitted_evidence_refs=('E1',))

@pytest.mark.parametrize('point', ['inventory', 'academic'])
def test_nonconforming_reader_cannot_break_unknown_recovery(point):
    class BadInventory:
        def read_feedback_inventory(self, *, original):
            object.__setattr__(owner, '_limit', 1)
            raise TimeoutError('simulated inventory failure')
    class BadAcademic:
        def read_confirmed_error(self, *, original):
            object.__setattr__(owner, '_limit', 1)
            raise TimeoutError('simulated academic failure')
    owner = ProductionStudentFeedback(source=BadAcademic() if point == 'academic' else Academic(),
        inventory_source=BadInventory() if point == 'inventory' else Inventory(),
        max_identifier_characters=128)
    result = assess(owner)
    assert type(result) is StudentSafeFeedback
    assert result.category is FeedbackCategory.UNKNOWN and result.message == UNKNOWN
    assert result.original == KEY and not result.authorizes_publication

@pytest.mark.parametrize('point', ['inventory', 'academic'])
def test_nonconforming_reader_cannot_substitute_result_constructor(point, monkeypatch):
    academic_calls=[]
    class AcademicReader:
        def read_confirmed_error(self, *, original):
            academic_calls.append(1)
            if point == 'academic':
                monkeypatch.setattr(module, 'StudentSafeFeedback', forged)
            return Academic().read_confirmed_error(original=original)
    class InventoryReader:
        def read_feedback_inventory(self, *, original):
            if point == 'inventory':
                monkeypatch.setattr(module, 'StudentSafeFeedback', forged)
                return None
            return Inventory().read_feedback_inventory(original=original)
    true_type=StudentSafeFeedback
    def forged(question_id, category, criterion_ref, evidence_ref, message):
        return true_type(question_id, FeedbackCategory.CONCEPTUAL_ERROR, 'FOREIGN', 'FOREIGN', FORGED)
    owner=ProductionStudentFeedback(source=AcademicReader(),inventory_source=InventoryReader(),
                                   max_identifier_characters=128)
    result=assess(owner)
    assert type(result) is true_type
    assert result.original == KEY
    if point == 'academic':
        assert result.category is FeedbackCategory.CONCEPTUAL_ERROR and result.message == APPROVED
        assert result.criterion_ref == 'C1'
    else:
        assert result.category is FeedbackCategory.UNKNOWN and result.message == UNKNOWN
        assert academic_calls == []

@pytest.mark.parametrize('category', [FeedbackCategory.CONCEPTUAL_ERROR, FeedbackCategory.CALCULATION_ERROR,
    FeedbackCategory.FORMULA_ERROR, FeedbackCategory.INCOMPLETE_SOLUTION])
def test_four_positive_feedback_categories_keep_original(category):
    class Classification:
        def read_confirmed_error(self, *, original):
            return IssuedErrorAssessment(original, ConfirmedErrorEvidence(category,'C1','E1','CONFIRMED'))
    owner=ProductionStudentFeedback(source=Classification(),inventory_source=Inventory(),
        max_identifier_characters=128)
    other=FeedbackOriginal('OTHER-TENANT','OTHER-RUN','OTHER-RESULT','OTHER-SOURCE','Q1')
    first=assess(owner)
    second=assess(owner,other)
    assert first.category is second.category is category
    assert first.original == KEY and second.original == other and first != second
    assert not first.authorizes_publication and not second.authorizes_publication


def test_standalone_formatter_stays_original_free_and_unmodified():
    result=student_safe_feedback(question_id='Q1',error=ConfirmedErrorEvidence(
        FeedbackCategory.UNKNOWN,None,None,None),admitted_criterion_refs=(),
        admitted_evidence_refs=(),max_identifier_characters=128)
    assert type(result) is StudentSafeFeedback and result.original is None
