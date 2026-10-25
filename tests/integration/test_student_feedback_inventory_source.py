"""Independent admitted rubric/evidence inventory before student diagnosis."""
from dataclasses import replace
import pytest
from grading.integration.student_safe_feedback import (
    FeedbackOriginal, FeedbackCategory, ConfirmedErrorEvidence,
    IssuedErrorAssessment, IssuedFeedbackInventory, ProductionStudentFeedback,
)

KEY=FeedbackOriginal('TENANT','RUN','SCORED','SOURCE','Q1')

class Academic:
    def __init__(self, category=FeedbackCategory.CONCEPTUAL_ERROR):
        self.calls=0;self.category=category
    def read_confirmed_error(self, *, original):
        self.calls+=1
        return IssuedErrorAssessment(original,
            ConfirmedErrorEvidence(self.category,'C1','E1','CONFIRMATION'))

class Inventories:
    def __init__(self,original=KEY,criteria=('C1',),evidence=('E1',)):
        self.calls=0;self.original=original;self.criteria=criteria;self.evidence=evidence
    def read_feedback_inventory(self, *, original):
        self.calls+=1
        return IssuedFeedbackInventory(self.original,self.criteria,self.evidence)

@pytest.mark.parametrize('category', [
    FeedbackCategory.CONCEPTUAL_ERROR, FeedbackCategory.CALCULATION_ERROR,
    FeedbackCategory.FORMULA_ERROR, FeedbackCategory.INCOMPLETE_SOLUTION,
])
def test_all_supported_positive_categories_need_independent_original_inventory(category):
    academic=Academic(category);inventory=Inventories()
    owner=ProductionStudentFeedback(source=academic,inventory_source=inventory,max_identifier_characters=128)
    result=owner.assess(original=KEY,admitted_criterion_refs=('C1',),admitted_evidence_refs=('E1',))
    assert result.category is category and result.criterion_ref=='C1' and result.evidence_ref=='E1'
    assert not result.authorizes_publication and inventory.calls==academic.calls==1

def test_caller_only_inventory_is_not_source_authority():
    academic=Academic();owner=ProductionStudentFeedback(source=academic,max_identifier_characters=128)
    result=owner.assess(original=KEY,admitted_criterion_refs=('C1',),admitted_evidence_refs=('E1',))
    assert result.category is FeedbackCategory.UNKNOWN and academic.calls==0

@pytest.mark.parametrize('wrong',[
    replace(KEY,tenant_ref='OTHER'),replace(KEY,grading_run_id='OTHER'),
    replace(KEY,original_scored_result_ref='OTHER'),replace(KEY,source_revision='OTHER'),
    replace(KEY,question_id='OTHER'),
])
def test_inventory_must_be_bound_to_every_original_identity(wrong):
    academic=Academic();owner=ProductionStudentFeedback(source=academic,
        inventory_source=Inventories(original=wrong),max_identifier_characters=128)
    out=owner.assess(original=KEY,admitted_criterion_refs=('C1',),admitted_evidence_refs=('E1',))
    assert out.category is FeedbackCategory.UNKNOWN and academic.calls==0

@pytest.mark.parametrize('criteria,evidence',[
    (('C2',),('E1',)),(('C1',),('E2',)),(('C1','C2'),('E1',)),
    (('C1',),()),((),('E1',)),(('C1','C1'),('E1',)),
    (('C1',),(object(),)),
])
def test_false_criterion_or_evidence_inventory_rejected(criteria,evidence):
    owner=ProductionStudentFeedback(source=Academic(),
        inventory_source=Inventories(criteria=criteria,evidence=evidence),max_identifier_characters=128)
    assert owner.assess(original=KEY,admitted_criterion_refs=('C1',),
        admitted_evidence_refs=('E1',)).category is FeedbackCategory.UNKNOWN

def test_inventory_exception_remains_unknown_without_academic_contact():
    class Broken:
        def read_feedback_inventory(self, *, original): raise TimeoutError('no original ledger')
    academic=Academic();owner=ProductionStudentFeedback(source=academic,
        inventory_source=Broken(),max_identifier_characters=128)
    assert owner.assess(original=KEY,admitted_criterion_refs=('C1',),
        admitted_evidence_refs=('E1',)).category is FeedbackCategory.UNKNOWN
    assert academic.calls==0

def test_inventory_reader_cannot_redirect_following_academic_reader():
    academic=Academic()
    owner=ProductionStudentFeedback(source=academic,
        inventory_source=Inventories(),max_identifier_characters=128)
    class Mutating:
        def read_feedback_inventory(self, *, original):
            object.__setattr__(owner,'_read', lambda **kw: IssuedErrorAssessment(kw['original'],
                ConfirmedErrorEvidence(FeedbackCategory.CALCULATION_ERROR,'C1','E1','FORGED')))
            return IssuedFeedbackInventory(original,('C1',),('E1',))
    object.__setattr__(owner,'_inventory', Mutating().read_feedback_inventory)
    out=owner.assess(original=KEY,admitted_criterion_refs=('C1',),admitted_evidence_refs=('E1',))
    assert out.category is FeedbackCategory.UNKNOWN and academic.calls==0

def test_academic_reader_cannot_redirect_fixed_feedback_formatter():
    academic=Academic();inventory=Inventories()
    owner=ProductionStudentFeedback(source=academic,inventory_source=inventory,max_identifier_characters=128)
    class Mutating:
        def read_confirmed_error(self, *, original):
            object.__setattr__(owner,'_format', lambda **kw: (_ for _ in ()).throw(AssertionError('foreign formatter')))
            return IssuedErrorAssessment(original,ConfirmedErrorEvidence(
                FeedbackCategory.CONCEPTUAL_ERROR,'C1','E1','FORGED'))
    object.__setattr__(owner,'_read', Mutating().read_confirmed_error)
    out=owner.assess(original=KEY,admitted_criterion_refs=('C1',),admitted_evidence_refs=('E1',))
    assert out.category is FeedbackCategory.UNKNOWN
