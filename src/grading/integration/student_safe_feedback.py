"""Evidence-grounded student feedback; no invented error diagnosis or marks.

An external academic source must explicitly attest each classified error and
its original rubric/evidence relation. Unclassified answers remain UNKNOWN;
no arbitrary rationale or provider exception is returned to a student.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum

class FeedbackCategory(str, Enum):
    CONCEPTUAL_ERROR='CONCEPTUAL_ERROR'
    CALCULATION_ERROR='CALCULATION_ERROR'
    FORMULA_ERROR='FORMULA_ERROR'
    INCOMPLETE_SOLUTION='INCOMPLETE_SOLUTION'
    UNKNOWN='UNKNOWN'
    NOT_APPLICABLE='NOT_APPLICABLE'

@dataclass(frozen=True, slots=True)
class ConfirmedErrorEvidence:
    category: FeedbackCategory
    rubric_criterion_ref: str | None
    admitted_evidence_ref: str | None
    academic_confirmation_ref: str | None

@dataclass(frozen=True, slots=True)
class StudentSafeFeedback:
    question_id: str
    category: FeedbackCategory
    criterion_ref: str | None
    evidence_ref: str | None
    # Short, categorical phrasing, not a generated explanation of academic intent.
    message: str
    # Verified local identity for production handoff; not issuer authentication.
    # Standalone formatting remains original-free.
    original: FeedbackOriginal | None = None

    @property
    def authorizes_publication(self): return False

def _make_feedback_formatter(result_type):
    """Bind the output constructor before any installed source can execute."""
    def student_safe_feedback(*, question_id: str, error: ConfirmedErrorEvidence,
                              admitted_criterion_refs: tuple[str,...],
                              admitted_evidence_refs: tuple[str,...],
                              max_identifier_characters: int) -> StudentSafeFeedback:
        if (type(max_identifier_characters) is not int or not 0<max_identifier_characters<=4096
            or type(question_id) is not str or not question_id or question_id.strip()!=question_id
            or len(question_id)>max_identifier_characters or type(error) is not ConfirmedErrorEvidence
            or type(error.category) is not FeedbackCategory
            or type(admitted_criterion_refs) is not tuple or type(admitted_evidence_refs) is not tuple
            or any(type(v) is not str or not v or v.strip()!=v or len(v)>max_identifier_characters
                   for v in admitted_criterion_refs+admitted_evidence_refs)
            or len(set(admitted_criterion_refs))!=len(admitted_criterion_refs)
            or len(set(admitted_evidence_refs))!=len(admitted_evidence_refs)):
            raise ValueError('Malformed feedback authority or admissible inventory.')
        ids=(error.rubric_criterion_ref,error.admitted_evidence_ref,error.academic_confirmation_ref)
        if any(v is not None and (type(v) is not str or not v or v.strip()!=v or
                                 len(v)>max_identifier_characters) for v in ids):
            raise ValueError('Foreign feedback evidence.')
        # Construct fixed Gradified-owned wording only after the external read. A
        # source callback never receives this mapping and cannot alter a shared
        # module table to inject student-visible content.
        messages = {
            FeedbackCategory.CONCEPTUAL_ERROR: 'A verified conceptual issue was identified for review.',
            FeedbackCategory.CALCULATION_ERROR: 'A verified calculation issue was identified for review.',
            FeedbackCategory.FORMULA_ERROR: 'A verified formula issue was identified for review.',
            FeedbackCategory.INCOMPLETE_SOLUTION: 'The admitted evidence confirms an incomplete solution.',
            FeedbackCategory.UNKNOWN: 'No evidence-grounded error classification is available.',
            FeedbackCategory.NOT_APPLICABLE: 'An error classification does not apply to this answer.',
        }
        if error.category in (FeedbackCategory.UNKNOWN,FeedbackCategory.NOT_APPLICABLE):
            if any(v is not None for v in ids):
                raise ValueError('Unclassified answer cannot claim confirmed academic proof.')
            return result_type(question_id,error.category,None,None,messages[error.category])
        if (error.rubric_criterion_ref not in admitted_criterion_refs
            or error.admitted_evidence_ref not in admitted_evidence_refs
            or error.academic_confirmation_ref is None):
            raise ValueError('Specific error requires approved criterion, evidence and independent academic confirmation.')
        return result_type(question_id,error.category,error.rubric_criterion_ref,
                                   error.admitted_evidence_ref,messages[error.category])

    return student_safe_feedback

student_safe_feedback = _make_feedback_formatter(StudentSafeFeedback)

@dataclass(frozen=True, slots=True)
class FeedbackOriginal:
    tenant_ref: str
    grading_run_id: str
    original_scored_result_ref: str
    source_revision: str
    question_id: str

@dataclass(frozen=True, slots=True)
class IssuedErrorAssessment:
    original: FeedbackOriginal
    error: ConfirmedErrorEvidence


@dataclass(frozen=True, slots=True)
class IssuedFeedbackInventory:
    """Original-bound criterion/evidence references from an installed source.

    This record does not authenticate the external issuer: the integration
    adapter must independently prove its original rubric and scored evidence.
    """
    original: FeedbackOriginal
    criterion_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]


class ProductionStudentFeedback:
    """Resolve original-bound academic classification before safe formatting.

    Read-only issuer qualification belongs to the integration adapter. Missing,
    foreign or failed reads cannot yield a specific academic diagnosis.
    """
    __slots__ = ('_read', '_inventory', '_limit', '_format')

    def __init__(self, *, source, max_identifier_characters: int, inventory_source=None):
        from grading.integration.execution_eligibility import _capture
        if type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 4096:
            raise ValueError('Bounded feedback installation required.')
        object.__setattr__(self, '_read', _capture(source, 'read_confirmed_error', ('original',)))
        object.__setattr__(self, '_inventory', None if inventory_source is None else
            _capture(inventory_source, 'read_feedback_inventory', ('original',)))
        object.__setattr__(self, '_limit', max_identifier_characters)
        object.__setattr__(self, '_format', student_safe_feedback)

    def __setattr__(self, name, value):
        raise AttributeError('Student feedback installation is immutable.')

    def assess(self, *, original: FeedbackOriginal, admitted_criterion_refs: tuple[str, ...],
               admitted_evidence_refs: tuple[str, ...]) -> StudentSafeFeedback:
        if type(original) is not FeedbackOriginal:
            raise ValueError('Exact question original required.')
        values = (original.tenant_ref, original.grading_run_id,
                  original.original_scored_result_ref, original.source_revision,
                  original.question_id)
        if any(type(v) is not str or not v or v.strip() != v or len(v) > self._limit
               for v in values):
            raise ValueError('Complete bounded feedback original required.')
        key = FeedbackOriginal(*values)
        # Capture actual installed operations before either external reader runs.
        inventory_reader = self._inventory
        error_reader = self._read
        formatter = self._format
        len_limit = self._limit
        bind_original = replace
        # Preflight both inventories before even an academic-source read.
        formatter(question_id=key.question_id,
            error=ConfirmedErrorEvidence(FeedbackCategory.UNKNOWN, None, None, None),
            admitted_criterion_refs=admitted_criterion_refs,
            admitted_evidence_refs=admitted_evidence_refs,
            max_identifier_characters=len_limit)
        unknown = ConfirmedErrorEvidence(FeedbackCategory.UNKNOWN, None, None, None)
        # Caller tuples are requests for filtering, never evidence of admission.
        # A production positive must be independently joined to the original
        # question/rubric/scored-result revision by an installed reader.
        def unresolved():
            # Use the captured installation even after a hostile/failed read.
            safe = formatter(question_id=key.question_id, error=unknown,
                admitted_criterion_refs=(), admitted_evidence_refs=(),
                max_identifier_characters=len_limit)
            return bind_original(safe, original=key)
        if inventory_reader is None:
            return unresolved()
        try:
            inventory=inventory_reader(original=FeedbackOriginal(*values))
            if (type(inventory) is not IssuedFeedbackInventory
                    or type(inventory.original) is not FeedbackOriginal
                    or any(type(getattr(inventory.original, name)) is not str
                           or getattr(inventory.original, name) != expected
                           for name, expected in zip((
                               'tenant_ref', 'grading_run_id', 'original_scored_result_ref',
                               'source_revision', 'question_id'), values))
                    or type(inventory.criterion_refs) is not tuple
                    or type(inventory.evidence_refs) is not tuple):
                return unresolved()
            # Exact copies of primitive tuples only; a mutable callback result
            # cannot change which sources are admitted after the read.
            criteria=tuple(inventory.criterion_refs)
            evidence=tuple(inventory.evidence_refs)
            formatter(question_id=key.question_id, error=unknown,
                admitted_criterion_refs=criteria, admitted_evidence_refs=evidence,
                max_identifier_characters=len_limit)
            if (self._read is not error_reader or self._inventory is not inventory_reader
                    or self._format is not formatter or self._limit != len_limit
                    or criteria!=admitted_criterion_refs
                    or evidence!=admitted_evidence_refs):
                return unresolved()
        except Exception:
            return unresolved()
        try:
            fact = error_reader(original=FeedbackOriginal(*values))
            if (type(fact) is not IssuedErrorAssessment
                    or type(fact.original) is not FeedbackOriginal
                    or any(type(getattr(fact.original, name)) is not str
                           or getattr(fact.original, name) != expected
                           for name, expected in zip((
                               'tenant_ref', 'grading_run_id', 'original_scored_result_ref',
                               'source_revision', 'question_id'), values))
                    or type(fact.error) is not ConfirmedErrorEvidence):
                error = unknown
            else:
                error = ConfirmedErrorEvidence(
                    fact.error.category, fact.error.rubric_criterion_ref,
                    fact.error.admitted_evidence_ref, fact.error.academic_confirmation_ref)
            if (self._read is not error_reader or self._inventory is not inventory_reader
                    or self._format is not formatter or self._limit != len_limit):
                error = unknown
        except Exception:
            error = unknown
        try:
            formatted = formatter(question_id=key.question_id, error=error,
                admitted_criterion_refs=criteria,
                admitted_evidence_refs=evidence,
                max_identifier_characters=len_limit)
            return bind_original(formatted, original=key)
        except ValueError:
            return unresolved()
