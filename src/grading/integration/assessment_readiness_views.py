"""Three-view original assessment facts; no guessed numerical confidence.

OCR, rubric and grading verification are distinct sources. The engine owns the
exact join and fail-closed interpretation. Issuer qualification and thresholds
remain external approved policy, not defaults hidden in this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from grading.integration.execution_eligibility import _capture

class ReadinessState(str, Enum):
    READY = 'READY'
    REVIEW_REQUIRED = 'REVIEW_REQUIRED'
    UNKNOWN = 'UNKNOWN'

class EvidenceView(str, Enum):
    OCR = 'OCR'
    RUBRIC = 'RUBRIC'
    GRADING = 'GRADING'

@dataclass(frozen=True, slots=True)
class AssessmentOrigin:
    tenant_ref: str
    grading_run_id: str
    scored_result_ref: str
    source_revision: str

@dataclass(frozen=True, slots=True)
class AssessmentViewFact:
    origin: AssessmentOrigin
    view: EvidenceView
    issuer_ref: str
    issuer_revision: str
    satisfactory: bool | None

@dataclass(frozen=True, slots=True)
class AssessmentReadiness:
    origin: AssessmentOrigin
    state: ReadinessState
    views: tuple[AssessmentViewFact | None, ...]

    @property
    def authorizes_publication(self): return False

class ProductionAssessmentReadiness:
    """Independent three-port read; absence/foreign data never means READY."""
    __slots__=('_readers','_limit')
    def __init__(self, *, ocr, rubric, grading, max_identifier_characters: int):
        if (type(max_identifier_characters) is not int or
            not 0 < max_identifier_characters <= 4096 or
            len({id(ocr),id(rubric),id(grading)}) != 3):
            raise ValueError('Three distinct approved-source ports required.')
        methods=('read_ocr_view','read_rubric_view','read_grading_view')
        object.__setattr__(self,'_readers',tuple(_capture(p,n,('origin',)) for p,n in zip((ocr,rubric,grading),methods)))
        object.__setattr__(self,'_limit',max_identifier_characters)
    def __setattr__(self,name,value): raise AttributeError('Readiness installation is immutable.')
    def assess(self, *, origin: AssessmentOrigin) -> AssessmentReadiness:
        if type(origin) is not AssessmentOrigin: raise ValueError('Exact result origin required.')
        strings=(origin.tenant_ref,origin.grading_run_id,origin.scored_result_ref,origin.source_revision)
        if any(type(v) is not str or not v or v.strip()!=v or len(v)>self._limit for v in strings):
            raise ValueError('Invalid original identity.')
        snap=AssessmentOrigin(*strings)
        installed_readers=self._readers
        installed_limit=self._limit
        facts=[]
        for method,view in zip(installed_readers, EvidenceView):
            try:
                fact=method(origin=AssessmentOrigin(*strings))
                if (type(fact) is not AssessmentViewFact or type(fact.origin) is not AssessmentOrigin
                    or (fact.origin.tenant_ref,fact.origin.grading_run_id,fact.origin.scored_result_ref,fact.origin.source_revision)!=strings
                    or fact.view is not view or type(fact.issuer_ref) is not str
                    or not fact.issuer_ref or fact.issuer_ref.strip()!=fact.issuer_ref
                    or len(fact.issuer_ref)>installed_limit or type(fact.issuer_revision) is not str
                    or not fact.issuer_revision or fact.issuer_revision.strip()!=fact.issuer_revision
                    or len(fact.issuer_revision)>installed_limit
                    or (fact.satisfactory is not None and type(fact.satisfactory) is not bool)):
                    facts.append(None)
                else:
                    facts.append(AssessmentViewFact(snap,view,fact.issuer_ref,fact.issuer_revision,fact.satisfactory))
            except Exception:
                facts.append(None)
        if (getattr(self, '_readers', None) is not installed_readers
                or getattr(self, '_limit', None) != installed_limit):
            # The three admitted observations alone cannot certify READY
            # after a source callback changes the installation itself.
            state=ReadinessState.UNKNOWN
        elif any(f is None or f.satisfactory is None for f in facts): state=ReadinessState.UNKNOWN
        elif any(not f.satisfactory for f in facts): state=ReadinessState.REVIEW_REQUIRED
        else: state=ReadinessState.READY
        return AssessmentReadiness(AssessmentOrigin(*strings),state,tuple(facts))
