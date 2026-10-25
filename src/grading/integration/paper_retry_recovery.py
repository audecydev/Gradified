"""original-operation recovery: original-operation-only paper recovery for legal retry decisions.

A positive backend assertion of NOT_RESERVED is NOT retry permission. No
approved legal operation transition retry policy is invented here. This seam preserves original
physical facts for an independently approved, atomic new-run transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.integration.execution_eligibility import _capture
from grading.integration.attempt_lineage import _snapshot_owned
from grading.integration.whole_paper_attempt_custody import (
    ProductionPaperAttemptCustody, PaperAttemptCustody, PaperAttemptClaimRecovery,
    PaperRecoveryState, _admit,
)


class OriginalPaperRecoveryState(str, Enum):
    OBSERVED_RESERVED = 'OBSERVED_RESERVED'
    ABSENCE_REPORTED = 'ABSENCE_REPORTED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class OriginalPaperRecovery:
    state: OriginalPaperRecoveryState
    paper: PaperAttemptCustody | None = None
    details: PaperAttemptClaimRecovery | None = None

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def authorizes_publication(self) -> bool:
        return False


class QualifiedOriginalPaperAttemptSource(Protocol):
    """Durable authenticated original run selection; ZERO caller selectors."""
    def resolve_original_paper_attempt(self) -> PaperAttemptCustody: ...


class ProductionPaperOriginalRecovery:
    """Read-only reconciliation; never creates an attempt, CAS write or grant."""
    __slots__ = ('_original', '_reader', '_maximum', '_questions', '_gate')

    def __init__(self, *, original_source: QualifiedOriginalPaperAttemptSource,
                 custody_reader: ProductionPaperAttemptCustody,
                 max_identifier_characters: int, max_questions: int):
        if (type(custody_reader) is not ProductionPaperAttemptCustody
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000):
            raise ValueError('An installed original-run custody reader is required.')
        object.__setattr__(self, '_original', _capture(original_source,
            'resolve_original_paper_attempt', ()))
        object.__setattr__(self, '_reader', custody_reader)
        object.__setattr__(self, '_maximum', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Original grading-attempt recovery installation is fixed.')

    def reconcile(self) -> OriginalPaperRecovery:
        if not self._gate.acquire(blocking=False):
            return OriginalPaperRecovery(OriginalPaperRecoveryState.UNKNOWN)
        try:
            try:
                original = self._original()  # Never caller-selected
            except Exception:
                return OriginalPaperRecovery(OriginalPaperRecoveryState.UNKNOWN)
            try:
                if type(original) is not PaperAttemptCustody:
                    return OriginalPaperRecovery(OriginalPaperRecoveryState.CONFLICT)
                admitted = _admit(original.plan, original.outcome,
                                 self._questions, self._maximum)
                if admitted != original:
                    return OriginalPaperRecovery(OriginalPaperRecoveryState.CONFLICT)
                baseline = _snapshot_owned(original)
            except Exception:
                return OriginalPaperRecovery(OriginalPaperRecoveryState.CONFLICT)
            try:
                read = self._reader.reconcile(record=original)
                if (_snapshot_owned(original) != baseline
                        or type(read) is not PaperAttemptClaimRecovery
                        or len(read.questions) != len(original.questions)
                        or any(q.question_id != r.question_id
                               or q.request_ref != r.request_ref and r.state is not PaperRecoveryState.NOT_CONTACTED
                               for q, r in zip(original.questions, read.questions, strict=True))):
                    return OriginalPaperRecovery(OriginalPaperRecoveryState.CONFLICT, original)
            except Exception:
                return OriginalPaperRecovery(OriginalPaperRecoveryState.UNKNOWN, original)
            statuses = tuple(q.state for q in read.questions)
            if any(s is PaperRecoveryState.CONFLICT for s in statuses):
                state = OriginalPaperRecoveryState.CONFLICT
            elif any(s is PaperRecoveryState.UNKNOWN for s in statuses):
                state = OriginalPaperRecoveryState.UNKNOWN
            elif any(s is PaperRecoveryState.RESERVED for s in statuses):
                state = OriginalPaperRecoveryState.OBSERVED_RESERVED
            elif all(s in (PaperRecoveryState.NOT_RESERVED,
                           PaperRecoveryState.NOT_CONTACTED) for s in statuses):
                # This is a read-only negative assertion; a concurrent claim
                # can still race without backend CAS/lease and legal operation transition approval.
                state = OriginalPaperRecoveryState.ABSENCE_REPORTED
            else:
                state = OriginalPaperRecoveryState.UNKNOWN
            return OriginalPaperRecovery(state, original, read)
        finally:
            self._gate.release()
