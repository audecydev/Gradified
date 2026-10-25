"""Read-only composition: original-CAS/teacher/policy + three readiness views.

This is a source-consuming nonpublishing eligibility observation. Actual
school/tenant authorization, backend compare-and-commit and public result
publication remain separate official workflow responsibilities.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from grading.integration.assessment_readiness_views import (
    ProductionAssessmentReadiness, AssessmentOrigin, ReadinessState, AssessmentReadiness,
)
from grading.integration.governed_original_assessment import (
    ProductionGovernedOriginalAssessment, GovernedOriginalKey,
)
from grading.integration.governed_result_disposition import (
    ResultDisposition, GovernedResultDecision,
)

@dataclass(frozen=True, slots=True)
class GovernedPaperHandoff:
    decision: GovernedResultDecision
    readiness: AssessmentReadiness
    @property
    def authorizes_publication(self) -> bool: return False
    @property
    def authorizes_retry(self) -> bool: return False

class ProductionGovernedPaperHandoff:
    __slots__=('_original','_readiness')
    def __init__(self, *, original: ProductionGovernedOriginalAssessment,
                 readiness: ProductionAssessmentReadiness):
        if (type(original) is not ProductionGovernedOriginalAssessment
            or type(readiness) is not ProductionAssessmentReadiness):
            raise ValueError('Qualified original-key and three-view readers required.')
        object.__setattr__(self,'_original',original)
        object.__setattr__(self,'_readiness',readiness)
    def __setattr__(self,name,value): raise AttributeError('Handoff installation is immutable.')
    def assess(self, *, original: GovernedOriginalKey) -> GovernedPaperHandoff:
        installed_original=self._original
        installed_readiness=self._readiness
        decision=installed_original.assess(original=original)
        view=installed_readiness.assess(origin=AssessmentOrigin(
            decision.tenant_ref,decision.grading_run_id,
            decision.original_scored_result_ref,decision.source_revision))
        if (getattr(self, '_original', None) is not installed_original
                or getattr(self, '_readiness', None) is not installed_readiness):
            # A callback may not substitute a governing reader between the
            # independently recovered original and the returned handoff.
            view=AssessmentReadiness(view.origin,ReadinessState.UNKNOWN,(None,None,None))
            state=ResultDisposition.UNKNOWN
        elif view.state is ReadinessState.UNKNOWN:
            state=ResultDisposition.UNKNOWN
        elif decision.disposition is ResultDisposition.UNKNOWN:
            state=ResultDisposition.UNKNOWN
        elif view.state is ReadinessState.REVIEW_REQUIRED:
            state=ResultDisposition.REVIEW
        else:
            state=decision.disposition
        if state is not decision.disposition:
            decision=replace(decision,disposition=state,
                             reason_codes=decision.reason_codes+('THREE_VIEW_READINESS',))
        return GovernedPaperHandoff(decision,view)
