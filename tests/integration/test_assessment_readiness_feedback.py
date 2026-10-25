from dataclasses import replace
import pytest
from grading.integration.assessment_readiness_views import (
    AssessmentOrigin, AssessmentViewFact, EvidenceView, ReadinessState, ProductionAssessmentReadiness,
)
from grading.integration.student_safe_feedback import (
    ConfirmedErrorEvidence,FeedbackCategory, student_safe_feedback,
)
O=AssessmentOrigin('T','RUN','RESULT','SRC')
class OCR:
    value=True
    def read_ocr_view(self, *, origin):return AssessmentViewFact(origin,EvidenceView.OCR,'OCR-ISSUER','1',self.value)
class Rubric:
    value=True
    def read_rubric_view(self, *, origin):return AssessmentViewFact(origin,EvidenceView.RUBRIC,'RUBRIC-ISSUER','1',self.value)
class Grading:
    value=True
    def read_grading_view(self, *, origin):return AssessmentViewFact(origin,EvidenceView.GRADING,'GRADING-ISSUER','1',self.value)
def rig():
    sources=(OCR(),Rubric(),Grading());return ProductionAssessmentReadiness(
        ocr=sources[0],rubric=sources[1],grading=sources[2],max_identifier_characters=128),sources

def test_independent_three_view_positive_nonpublishing():
    owner,_=rig(); r=owner.assess(origin=O)
    assert r.state is ReadinessState.READY and len(r.views)==3 and not r.authorizes_publication
@pytest.mark.parametrize('i',range(3))
def test_each_missing_view_is_unknown(i):
    owner,sources=rig();sources[i].value=None
    assert owner.assess(origin=O).state is ReadinessState.UNKNOWN
@pytest.mark.parametrize('i',range(3))
def test_each_adverse_view_is_review(i):
    owner,sources=rig();sources[i].value=False
    assert owner.assess(origin=O).state is ReadinessState.REVIEW_REQUIRED

def test_unknown_precedes_known_adverse():
    owner,sources=rig(); sources[0].value=False;sources[1].value=None
    assert owner.assess(origin=O).state is ReadinessState.UNKNOWN

def test_foreign_bool_or_mismatched_origin_cannot_be_ready():
    owner,sources=rig();sources[2].value=1
    assert owner.assess(origin=O).state is ReadinessState.UNKNOWN
    owner,sources=rig()
    class Foreign(OCR):
        def read_ocr_view(self, *, origin):
            return AssessmentViewFact(replace(origin,tenant_ref='OTHER'),EvidenceView.OCR,'OCR-ISSUER','1',True)
    foreign=ProductionAssessmentReadiness(ocr=Foreign(),rubric=Rubric(),grading=Grading(),max_identifier_characters=128)
    assert foreign.assess(origin=O).state is ReadinessState.UNKNOWN

@pytest.mark.parametrize('category', [FeedbackCategory.CONCEPTUAL_ERROR,FeedbackCategory.CALCULATION_ERROR,
    FeedbackCategory.FORMULA_ERROR,FeedbackCategory.INCOMPLETE_SOLUTION])
def test_four_categories_only_with_confirmed_admitted_evidence(category):
    feedback=student_safe_feedback(question_id='Q',error=ConfirmedErrorEvidence(category,'CRIT','BLOCK','SCHOOL-CHECK'),
        admitted_criterion_refs=('CRIT',),admitted_evidence_refs=('BLOCK',),max_identifier_characters=128)
    assert feedback.category is category and feedback.evidence_ref=='BLOCK'
    assert not feedback.authorizes_publication

@pytest.mark.parametrize('category', [FeedbackCategory.UNKNOWN,FeedbackCategory.NOT_APPLICABLE])
def test_no_invented_diagnosis(category):
    feedback=student_safe_feedback(question_id='Q',error=ConfirmedErrorEvidence(category,None,None,None),
        admitted_criterion_refs=(),admitted_evidence_refs=(),max_identifier_characters=128)
    assert feedback.category is category and feedback.evidence_ref is None

@pytest.mark.parametrize('bad', [ConfirmedErrorEvidence(FeedbackCategory.CALCULATION_ERROR,'WRONG','BLOCK','CONFIRM'),
    ConfirmedErrorEvidence(FeedbackCategory.CONCEPTUAL_ERROR,'CRIT','BLOCK',None),
    ConfirmedErrorEvidence(FeedbackCategory.UNKNOWN,'CRIT',None,None),
    ConfirmedErrorEvidence(FeedbackCategory.NOT_APPLICABLE,None,None,'FAKE')])
def test_unsupported_feedback_sources_cannot_forge_student_diagnosis(bad):
    with pytest.raises(ValueError):student_safe_feedback(question_id='Q',error=bad,
        admitted_criterion_refs=('CRIT',),admitted_evidence_refs=('BLOCK',),max_identifier_characters=128)

def test_ocr_reader_cannot_mutate_original_shared_with_other_views():
    class Evil(OCR):
        def read_ocr_view(self, *, origin):
            object.__setattr__(origin,'tenant_ref','WRONG')
            return AssessmentViewFact(origin,EvidenceView.OCR,'S','1',True)
    owner=ProductionAssessmentReadiness(ocr=Evil(),rubric=Rubric(),grading=Grading(),max_identifier_characters=128)
    result=owner.assess(origin=O)
    assert result.origin==O and result.state is ReadinessState.UNKNOWN
    assert result.views[1].origin==O

def test_connected_seven_independent_readers_required_for_positive_handoff():
    from grading.integration.governed_paper_handoff import ProductionGovernedPaperHandoff
    from tests.integration.test_governed_original_assessment import rig as original_rig, KEY
    owner,_=rig(); original,_=original_rig()
    whole=ProductionGovernedPaperHandoff(original=original,readiness=owner)
    outcome=whole.assess(original=KEY)
    assert outcome.decision.disposition.value=='ACCEPTED_FOR_GOVERNED_HANDOFF'
    assert outcome.readiness.state is ReadinessState.READY
    assert not outcome.authorizes_publication and not outcome.authorizes_retry


def test_connected_handoff_one_unavailable_ocr_blocks_positive():
    from grading.integration.governed_paper_handoff import ProductionGovernedPaperHandoff
    from tests.integration.test_governed_original_assessment import rig as original_rig, KEY
    owner,views=rig(); views[0].value=None
    original,_=original_rig()
    whole=ProductionGovernedPaperHandoff(original=original,readiness=owner)
    outcome=whole.assess(original=KEY)
    assert outcome.decision.disposition.value=='UNKNOWN'
    assert 'THREE_VIEW_READINESS' in outcome.decision.reason_codes


class FeedbackInventoryReader:
    def read_feedback_inventory(self, *, original):
        from grading.integration.student_safe_feedback import IssuedFeedbackInventory
        return IssuedFeedbackInventory(original, ('CRIT',), ('BLOCK',))

class AcademicClassifier:
    def __init__(self,category=FeedbackCategory.INCOMPLETE_SOLUTION):
        self.category=category;self.calls=0
    def read_confirmed_error(self, *, original):
        from grading.integration.student_safe_feedback import IssuedErrorAssessment, ConfirmedErrorEvidence
        self.calls+=1
        return IssuedErrorAssessment(original, ConfirmedErrorEvidence(self.category,'CRIT','BLOCK','APPROVED'))

def test_positive_academic_original_reader_students_get_only_grounded_category():
    from grading.integration.student_safe_feedback import ProductionStudentFeedback, FeedbackOriginal
    source=AcademicClassifier()
    owner=ProductionStudentFeedback(source=source,inventory_source=FeedbackInventoryReader(),max_identifier_characters=128)
    key=FeedbackOriginal('T','RUN','RESULT','SOURCE','Q')
    out=owner.assess(original=key,admitted_criterion_refs=('CRIT',),admitted_evidence_refs=('BLOCK',))
    assert out.category is FeedbackCategory.INCOMPLETE_SOLUTION
    assert source.calls==1 and not out.authorizes_publication

def test_inconsistent_or_unavailable_academic_original_cannot_announce_student_error():
    from grading.integration.student_safe_feedback import (
        ProductionStudentFeedback, FeedbackOriginal, IssuedErrorAssessment,
    )
    class Foreign(AcademicClassifier):
        def read_confirmed_error(self, *, original):
            item=super().read_confirmed_error(original=original)
            return replace(item,original=replace(original,tenant_ref='OTHER'))
    key=FeedbackOriginal('T','RUN','RESULT','SOURCE','Q')
    for source in (Foreign(),AcademicClassifier()):
        owner=ProductionStudentFeedback(source=source,inventory_source=FeedbackInventoryReader(),max_identifier_characters=128)
        inventory=('NO-MATCH',) if type(source) is AcademicClassifier else ('CRIT',)
        out=owner.assess(original=key,admitted_criterion_refs=inventory,admitted_evidence_refs=('BLOCK',))
        assert out.category is FeedbackCategory.UNKNOWN
