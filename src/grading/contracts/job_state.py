from __future__ import annotations

from enum import Enum


__all__ = (
    "GRADING_JOB_STATE_SCHEMA_VERSION",
    "GradingJobState",
    "GRADING_JOB_PROGRESS_STATES",
    "GRADING_JOB_TERMINAL_STATES",
    "is_terminal_grading_job_state",
)


GRADING_JOB_STATE_SCHEMA_VERSION = "1"


class GradingJobState(str, Enum):
    """Canonical Release-1 grading-job state vocabulary."""

    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    GRADING = "GRADING"
    VERIFYING = "VERIFYING"
    SCORING = "SCORING"
    RISK_EVALUATION = "RISK_EVALUATION"
    COMPLETED = "COMPLETED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNASSESSABLE_EVIDENCE = "UNASSESSABLE_EVIDENCE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    FAILED_TECHNICALLY = "FAILED_TECHNICALLY"


GRADING_JOB_PROGRESS_STATES = (
    GradingJobState.QUEUED,
    GradingJobState.VALIDATING,
    GradingJobState.GRADING,
    GradingJobState.VERIFYING,
    GradingJobState.SCORING,
    GradingJobState.RISK_EVALUATION,
)

GRADING_JOB_TERMINAL_STATES = (
    GradingJobState.COMPLETED,
    GradingJobState.REVIEW_REQUIRED,
    GradingJobState.UNASSESSABLE_EVIDENCE,
    GradingJobState.UNSUPPORTED_CAPABILITY,
    GradingJobState.FAILED_TECHNICALLY,
)


def is_terminal_grading_job_state(state: GradingJobState) -> bool:
    """Return whether an exact grading-job state is terminal."""

    if type(state) is not GradingJobState:
        raise TypeError("state must be an exact GradingJobState")
    return state in GRADING_JOB_TERMINAL_STATES
