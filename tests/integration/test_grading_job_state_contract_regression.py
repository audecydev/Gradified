from __future__ import annotations

from enum import Enum
import importlib

import pytest

from grading.execution import GradingExecutionContext
from grading.contracts.paper_aggregation import GradingSpecRef


MODULE_NAME = "grading.contracts.job_state"
MISSING_MESSAGE = (
    "Release-1 grading job-state contract is absent; "
    "expected grading.contracts.job_state"
)
EXPECTED_PUBLIC = {
    "GRADING_JOB_STATE_SCHEMA_VERSION",
    "GradingJobState",
    "GRADING_JOB_PROGRESS_STATES",
    "GRADING_JOB_TERMINAL_STATES",
    "is_terminal_grading_job_state",
}
EXPECTED_STATE_NAMES = (
    "QUEUED",
    "VALIDATING",
    "GRADING",
    "VERIFYING",
    "SCORING",
    "RISK_EVALUATION",
    "COMPLETED",
    "REVIEW_REQUIRED",
    "UNASSESSABLE_EVIDENCE",
    "UNSUPPORTED_CAPABILITY",
    "FAILED_TECHNICALLY",
)
EXPECTED_PROGRESS_NAMES = EXPECTED_STATE_NAMES[:6]
EXPECTED_TERMINAL_NAMES = EXPECTED_STATE_NAMES[6:]


def _require_module():
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME:
            pytest.fail(MISSING_MESSAGE)
        raise


def test_prerequisite_grading_execution_context_remains_available() -> None:
    context = GradingExecutionContext(
        grading_run_id="run-1",
        submission_ref="submission-1",
        exam_ref="exam-1",
        grading_spec_ref=GradingSpecRef(id="spec-1", version=1),
    )
    assert context.grading_run_id == "run-1"
    assert context.submission_ref == "submission-1"


def test_red_public_surface_is_exact() -> None:
    module = _require_module()
    assert set(module.__all__) == EXPECTED_PUBLIC
    for name in EXPECTED_PUBLIC:
        assert hasattr(module, name)


def test_red_schema_version_is_exact_v1() -> None:
    module = _require_module()
    assert module.GRADING_JOB_STATE_SCHEMA_VERSION == "1"
    assert type(module.GRADING_JOB_STATE_SCHEMA_VERSION) is str


def test_red_job_state_vocabulary_is_exact_and_ordered() -> None:
    module = _require_module()
    state = module.GradingJobState
    assert issubclass(state, str)
    assert issubclass(state, Enum)
    assert tuple(member.name for member in state) == EXPECTED_STATE_NAMES
    assert tuple(member.value for member in state) == EXPECTED_STATE_NAMES


def test_red_job_state_enum_has_no_aliases() -> None:
    module = _require_module()
    state = module.GradingJobState
    assert tuple(state.__members__) == EXPECTED_STATE_NAMES
    assert len(state.__members__) == len(tuple(state)) == len(EXPECTED_STATE_NAMES)


def test_red_job_state_construction_is_exact_with_no_fallback_normalization() -> None:
    module = _require_module()
    state = module.GradingJobState

    for name in EXPECTED_STATE_NAMES:
        assert state(name) is getattr(state, name)

    assert "_missing_" not in state.__dict__
    assert state._missing_.__func__ is Enum._missing_.__func__
    for foreign in (
        "queued",
        "COMPLETED ",
        " completed",
        "AUTO_CANDIDATE",
        "UNKNOWN",
        "",
        1,
        None,
    ):
        with pytest.raises((TypeError, ValueError)):
            state(foreign)


def test_red_progress_states_are_exact_and_ordered() -> None:
    module = _require_module()
    assert type(module.GRADING_JOB_PROGRESS_STATES) is tuple
    assert tuple(member.name for member in module.GRADING_JOB_PROGRESS_STATES) == EXPECTED_PROGRESS_NAMES
    assert all(type(member) is module.GradingJobState for member in module.GRADING_JOB_PROGRESS_STATES)


def test_red_terminal_states_are_exact_and_ordered() -> None:
    module = _require_module()
    assert type(module.GRADING_JOB_TERMINAL_STATES) is tuple
    assert tuple(member.name for member in module.GRADING_JOB_TERMINAL_STATES) == EXPECTED_TERMINAL_NAMES
    assert all(type(member) is module.GradingJobState for member in module.GRADING_JOB_TERMINAL_STATES)


def test_red_progress_and_terminal_states_form_complete_disjoint_partition() -> None:
    module = _require_module()
    progress = module.GRADING_JOB_PROGRESS_STATES
    terminal = module.GRADING_JOB_TERMINAL_STATES
    assert set(progress).isdisjoint(terminal)
    assert progress + terminal == tuple(module.GradingJobState)


def test_red_terminal_helper_is_exact_membership_only() -> None:
    module = _require_module()
    helper = module.is_terminal_grading_job_state
    for state in module.GRADING_JOB_PROGRESS_STATES:
        assert helper(state) is False
    for state in module.GRADING_JOB_TERMINAL_STATES:
        assert helper(state) is True


@pytest.mark.parametrize("foreign", ["COMPLETED", "completed", 1, None, object()])
def test_red_terminal_helper_rejects_non_enum_inputs(foreign: object) -> None:
    module = _require_module()
    with pytest.raises(TypeError):
        module.is_terminal_grading_job_state(foreign)


def test_red_job_state_contract_does_not_absorb_recommendation_vocabulary() -> None:
    module = _require_module()
    names = set(member.name for member in module.GradingJobState)
    assert "AUTO_CANDIDATE" not in names
    assert "SECOND_CHECK" not in names
    assert "HUMAN_REVIEW" not in names


def test_red_public_contract_contains_no_workflow_or_authority_surface() -> None:
    module = _require_module()
    lowered = " ".join(module.__all__).lower()
    for forbidden in (
        "transition",
        "map",
        "retry",
        "idempot",
        "attempt",
        "persist",
        "publish",
        "grade_result",
        "candidate",
        "tenant",
        "auth",
        "risk",
        "recommend",
    ):
        assert forbidden not in lowered
