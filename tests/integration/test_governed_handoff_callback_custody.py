"""Verify governor and readiness callbacks cannot silently replace admitted handoff authority.

These in-memory tests do not establish real backend authentication."""
import pytest
from grading.integration.governed_original_assessment import (
    GovernedOriginalKey, GovernedOriginalFact, ProductionGovernedOriginalAssessment)
from grading.integration.governed_result_disposition import (
    GovernedResultDecision, ResultDisposition)
from grading.integration.assessment_readiness_views import (
    AssessmentOrigin, AssessmentViewFact, EvidenceView, ProductionAssessmentReadiness, ReadinessState)

KEY=GovernedOriginalKey('TENANT','RUN','RESULT','REV','POLICY','POLREV')
ORIGIN=AssessmentOrigin('TENANT','RUN','RESULT','REV')

class Source:
    def __init__(self, method, value=True): self.method=method;self.value=value
    def read_scored_original(self,*,original): return GovernedOriginalFact(original,self.value)
    def read_academic_original(self,*,original): return GovernedOriginalFact(original,self.value)
    def read_teacher_original(self,*,original): return GovernedOriginalFact(original,self.value)
    def read_adverse_policy(self,*,original): return GovernedOriginalFact(original,self.value)

class ForgedInterpreter:
    def evaluate(self, *, evidence):
        return GovernedResultDecision(ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF,
            KEY.tenant_ref, KEY.grading_run_id, KEY.source_revision,
            KEY.original_scored_result_ref, KEY.policy_ref, KEY.policy_revision, ())

def owner(scored):
    return ProductionGovernedOriginalAssessment(scored=scored,academic=Source('academic'),
        teacher=Source('teacher'),adverse_policy=Source('adverse'),max_identifier_characters=128)

def test_control_all_true_is_accepted_for_handoff_only():
    o=owner(Source('scored'))
    decision=o.assess(original=KEY)
    assert decision.disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
    assert not decision.authorizes_publication

def test_control_missing_scored_evidence_remains_unknown():
    o=owner(Source('scored',None))
    assert o.assess(original=KEY).disposition is ResultDisposition.UNKNOWN

@pytest.mark.parametrize('source_state', ['missing','foreign'])
def test_source_callback_cannot_replace_governed_interpreter(source_state):
    class HostileScored:
        def read_scored_original(self, *, original):
            object.__setattr__(o,'_interpret',ForgedInterpreter())
            if source_state=='missing': return GovernedOriginalFact(original,None)
            return GovernedOriginalFact(GovernedOriginalKey('FOREIGN','RUN','RESULT','REV','POLICY','POLREV'),True)
    o=owner(HostileScored())
    decision=o.assess(original=KEY)
    assert decision.disposition is ResultDisposition.UNKNOWN, 'Unresolved/foreign original must not become governed accepted after source callback'

class Ocr:
    def read_ocr_view(self, *, origin):
        object.__setattr__(r,'_readers',('replaced',))
        return AssessmentViewFact(origin,EvidenceView.OCR,'OCRISSUER','REV1',True)
class Rubric:
    def read_rubric_view(self, *, origin):return AssessmentViewFact(origin,EvidenceView.RUBRIC,'RUBRICISSUER','REV1',True)
class Grading:
    def read_grading_view(self, *, origin):return AssessmentViewFact(origin,EvidenceView.GRADING,'GRADEISSUER','REV1',True)

def test_readiness_source_cannot_change_installed_ports_and_still_be_ready():
    global r
    r=ProductionAssessmentReadiness(ocr=Ocr(),rubric=Rubric(),grading=Grading(),max_identifier_characters=128)
    result=r.assess(origin=ORIGIN)
    assert result.state is ReadinessState.UNKNOWN, 'Readiness installation substitution must not yield READY'

class CleanOcr:
    def read_ocr_view(self, *, origin):
        return AssessmentViewFact(origin,EvidenceView.OCR,'OCRISSUER','REV1',True)

class BogusReadiness:
    def assess(self, *, origin):
        from grading.integration.assessment_readiness_views import AssessmentReadiness
        return AssessmentReadiness(origin,ReadinessState.READY,())

@pytest.mark.parametrize('substitute',[False,True])
def test_governed_handoff_refuses_owner_substitution_between_original_and_readiness(substitute):
    from grading.integration.governed_paper_handoff import ProductionGovernedPaperHandoff
    class ScoredWithHandoffMutation:
        def read_scored_original(self, *, original):
            if substitute:
                object.__setattr__(handoff,'_readiness',BogusReadiness())
            return GovernedOriginalFact(original,True)
    original_owner=owner(ScoredWithHandoffMutation())
    readiness=ProductionAssessmentReadiness(
        ocr=CleanOcr(),rubric=Rubric(),grading=Grading(),max_identifier_characters=128)
    handoff=ProductionGovernedPaperHandoff(original=original_owner,readiness=readiness)
    result=handoff.assess(original=KEY)
    assert (result.decision.disposition is (
        ResultDisposition.UNKNOWN if substitute else ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF))
    assert (result.readiness.state is (ReadinessState.UNKNOWN if substitute else ReadinessState.READY))
    assert not result.authorizes_publication
