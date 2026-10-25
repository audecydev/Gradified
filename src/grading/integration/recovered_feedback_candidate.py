"""Nonpublishing student-safe feedback feedback candidate for one independently recovered original.

This consumer never executes grading or writes journal/result/publication state.
External sources must authenticate the pending original, its question, approved
criterion/evidence inventory and academic confirmation. Local equality and
read-only rechecks are not a database snapshot or authorization to disclose.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.integration.governed_operation_consumer import ScoredOperationIdentity

from grading.integration.execution_eligibility import _capture
from grading.integration.governed_operation_consumer import GovernedOperationState
from grading.integration.recovered_original_governance import (
    ProductionRecoveredOriginalGovernance, RecoveredOriginalGovernance,
)
from grading.integration.student_safe_feedback import (
    FeedbackCategory, FeedbackOriginal, ProductionStudentFeedback, StudentSafeFeedback,
)


class FeedbackCandidateState(str, Enum):
    CANDIDATE = 'CANDIDATE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class RecoveredFeedbackCandidate:
    state: FeedbackCandidateState
    feedback: StudentSafeFeedback | None = None
    # Preserve the complete exact-original CAS identity and the admitted
    # cross-source generation for downstream audit and effect-time comparison.
    # Neither field is issuer authentication or student-disclosure permission.
    operation: ScoredOperationIdentity | None = None
    binding_revision: str | None = None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_student_visibility(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class OriginalFeedbackQuestionSource(Protocol):
    """Independently issued question/inventory selection for the fixed original."""
    def read_feedback_question(self) -> tuple[FeedbackOriginal, tuple[str, ...], tuple[str, ...]]: ...


@dataclass(frozen=True, slots=True)
class CurrentFeedbackBinding:
    """One issuer-qualified, atomic current selection of the original and question.

    `snapshot_revision` is an opaque backend-issued generation, NOT local proof
    that a backend is atomic or that an issuer is authenticated. The installed
    adapter is responsible for authenticating and comparing the entire selection
    in one linearizable/snapshot-consistent read. The revision supports audit.
    """
    operation: ScoredOperationIdentity
    question: FeedbackOriginal
    criterion_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    snapshot_revision: str


class CurrentFeedbackBindingSource(Protocol):
    """Read all relevant current-selection facts in ONE backend consistency view.

    Must not independently read stale cached copies or compose several unguarded
    requests. Must bind the same pending original, selected question and admitted
    criterion/evidence IDs under authenticated/versioned issuer authority.
    """
    def read_current_feedback_binding(self) -> CurrentFeedbackBinding: ...


class ProductionRecoveredFeedbackCandidate:
    """Connect fixed-original governed scored-paper handoff recovery to independent student-safe feedback feedback admission.

    The question source, inventory source and academic classifier must all be
    trusted/issuer-qualified adapters. This surface exposes a *candidate* only;
    the backend must independently authorize audience and current disclosure.
    """
    __slots__ = ('_recovery', '_feedback', '_question', '_binding', '_gate')

    def __init__(self, *, recovery: ProductionRecoveredOriginalGovernance,
                 feedback: ProductionStudentFeedback,
                 question_source: OriginalFeedbackQuestionSource,
                 current_binding_source: CurrentFeedbackBindingSource | None = None):
        if (type(recovery) is not ProductionRecoveredOriginalGovernance
                or type(feedback) is not ProductionStudentFeedback
                or feedback._inventory is None):
            raise ValueError('Fixed-original recovery and independently inventoried feedback required.')
        object.__setattr__(self, '_recovery', recovery)
        object.__setattr__(self, '_feedback', feedback)
        object.__setattr__(self, '_question', _capture(question_source,
            'read_feedback_question', ()))
        # Source compatibility: older installations can still construct the
        # read-only owner. Without an installed cross-source consistency reader
        # it can never emit a positive CANDIDATE, only UNKNOWN.
        object.__setattr__(self, '_binding', None if current_binding_source is None
            else _capture(current_binding_source, 'read_current_feedback_binding', ()))
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Recovered feedback installation is immutable.')

    def assess(self) -> RecoveredFeedbackCandidate:
        unknown = RecoveredFeedbackCandidate(FeedbackCandidateState.UNKNOWN)
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            recovery, feedback, question, binding = (
                self._recovery, self._feedback, self._question, self._binding)
            if binding is None:
                return unknown
            first = recovery.recover()
            if (type(first) is not RecoveredOriginalGovernance
                    or first.state is not GovernedOperationState.HANDOFF_ELIGIBLE
                    or first.operation is None or first.handoff is None
                    or first.original_c5 is None):
                return unknown
            operation = first.operation
            fact = question()
            if type(fact) is not tuple or len(fact) != 3:
                return unknown
            original, criteria, evidence = fact
            if (type(original) is not FeedbackOriginal
                    or type(criteria) is not tuple or type(evidence) is not tuple
                    or original.question_id not in first.scored_question_ids
                    or (original.tenant_ref, original.grading_run_id,
                        original.original_scored_result_ref, original.source_revision)
                       != (operation.tenant_ref, operation.grading_run_id,
                           operation.original_scored_result_ref, operation.source_revision)):
                return unknown
            # The feedback owner independently re-admits exact original question,
            # criterion, evidence and confirmed error from its installed readers.
            observed = feedback.assess(original=original,
                admitted_criterion_refs=criteria, admitted_evidence_refs=evidence)
            if (type(observed) is not StudentSafeFeedback
                    or observed.original != original
                    or observed.question_id != original.question_id
                    or observed.category not in FeedbackCategory
                    or self._recovery is not recovery or self._feedback is not feedback
                    or self._question is not question):
                return unknown
            # The issued question/inventory may itself change while the
            # independent inventory/classifier callbacks execute. An earlier
            # positive question selection is not authority for a later one.
            if question() != fact or self._question is not question:
                return unknown
            # Independently recheck the fixed original after all academic callbacks;
            # no earlier governed scored-paper handoff/READY snapshot is a lasting permission to disclose.
            last = recovery.recover()
            if (type(last) is not RecoveredOriginalGovernance
                    or last.state is not GovernedOperationState.HANDOFF_ELIGIBLE
                    or last.operation != operation or last.handoff != first.handoff
                    or last.scored_question_ids != first.scored_question_ids
                    or last.original_c5 != first.original_c5
                    or self._recovery is not recovery or self._feedback is not feedback
                    or self._question is not question):
                return unknown
            # A pair of separately refreshed reads can NEVER prove joint
            # currentness. The final source operation must atomically observe
            # the *same* pending original AND selected question/inventory at
            # one authoritative backend generation. No local value equality
            # can establish the adapter's atomicity or issuer authenticity.
            current = binding()
            if (type(current) is not CurrentFeedbackBinding
                    or type(current.operation) is not ScoredOperationIdentity
                    or current.operation != operation
                    or type(current.question) is not FeedbackOriginal
                    or current.question != original
                    or type(current.criterion_refs) is not tuple
                    or current.criterion_refs != criteria
                    or type(current.evidence_refs) is not tuple
                    or current.evidence_refs != evidence
                    or type(current.snapshot_revision) is not str
                    or not current.snapshot_revision
                    or current.snapshot_revision.strip() != current.snapshot_revision
                    or len(current.snapshot_revision) > 4096
                    or self._recovery is not recovery or self._feedback is not feedback
                    or self._question is not question or self._binding is not binding):
                return unknown
            return RecoveredFeedbackCandidate(FeedbackCandidateState.CANDIDATE,
                observed, current.operation, current.snapshot_revision)
        except Exception:
            # No physical operation is retried, and no raw provider/error text is
            # disclosed. UNKNOWN is the only safe result of an uncertain read.
            return unknown
        finally:
            self._gate.release()
