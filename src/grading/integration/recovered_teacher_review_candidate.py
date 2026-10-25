"""Nonpublishing, fixed-original teacher review teacher-journal continuation.

The scored original is independently recovered and governed scored-paper handoff-qualified, then the
existing historical teacher-review journal is compared against exactly that
original. There is no new grading, journal append, mark override, or disclosure.
Authentic school decisions, durable history and official transitions remain
requirements for independently qualified external adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock

from grading.integration.governed_operation_consumer import (
    GovernedOperationState, ScoredOperationIdentity,
)
from grading.integration.recovered_original_governance import (
    ProductionRecoveredOriginalGovernance, RecoveredOriginalGovernance,
)
from grading.integration.teacher_review_journal import (
    ProductionTeacherReviewRecovery, TeacherReviewRecoveryObservation,
    TeacherReviewRecoveryState,
)


class RecoveredTeacherReviewState(str, Enum):
    RECORDED_CANDIDATE = 'RECORDED_CANDIDATE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class RecoveredTeacherReviewCandidate:
    state: RecoveredTeacherReviewState
    original: ScoredOperationIdentity | None = None
    review: TeacherReviewRecoveryObservation | None = None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_official_mark_change(self) -> bool:
        return False

    @property
    def authorizes_reappend(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class ProductionRecoveredTeacherReviewCandidate:
    """Join fixed, historical teacher review decision with one independently recovered governed scored-paper handoff original.

    A positive candidate means that the installed historical journal reports an
    admitted decision for that original. It is NOT a current school approval or
    any permission to apply a mark change, publish or notify a student.
    """
    __slots__ = ('_recovery', '_teacher', '_gate')

    def __init__(self, *, recovery: ProductionRecoveredOriginalGovernance,
                 teacher_recovery: ProductionTeacherReviewRecovery):
        if (type(recovery) is not ProductionRecoveredOriginalGovernance
                or type(teacher_recovery) is not ProductionTeacherReviewRecovery
                or teacher_recovery._policy != recovery._c5._policy
                or teacher_recovery._limit != recovery._limit):
            raise ValueError('Original and teacher journal must share exact legal authority profile.')
        object.__setattr__(self, '_recovery', recovery)
        object.__setattr__(self, '_teacher', teacher_recovery)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Recovered teacher review installation is immutable.')

    def assess(self) -> RecoveredTeacherReviewCandidate:
        unknown = RecoveredTeacherReviewCandidate(RecoveredTeacherReviewState.UNKNOWN)
        if not self._gate.acquire(blocking=False):
            return unknown
        try:
            recovery, teacher = self._recovery, self._teacher
            first = recovery.recover()
            if (type(first) is not RecoveredOriginalGovernance
                    or first.state is not GovernedOperationState.HANDOFF_ELIGIBLE
                    or type(first.operation) is not ScoredOperationIdentity
                    or first.original_c5 is None or first.handoff is None):
                return unknown
            review = teacher.reconcile(expected_original=first.operation)
            if (type(review) is not TeacherReviewRecoveryObservation
                    or review.state is not TeacherReviewRecoveryState.COMMITTED
                    or type(review.decision_ref) is not str or not review.decision_ref
                    or type(review.journal_event_ref) is not str or not review.journal_event_ref
                    or self._recovery is not recovery or self._teacher is not teacher):
                return unknown
            last = recovery.recover()
            if (type(last) is not RecoveredOriginalGovernance
                    or last.state is not GovernedOperationState.HANDOFF_ELIGIBLE
                    or last.operation != first.operation
                    or last.original_c5 != first.original_c5
                    or last.handoff != first.handoff
                    or last.scored_question_ids != first.scored_question_ids
                    or self._recovery is not recovery or self._teacher is not teacher):
                return unknown
            return RecoveredTeacherReviewCandidate(
                RecoveredTeacherReviewState.RECORDED_CANDIDATE, first.operation, review)
        except Exception:
            return unknown
        finally:
            self._gate.release()
