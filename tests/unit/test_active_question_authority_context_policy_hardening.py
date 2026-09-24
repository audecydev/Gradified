from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from enum import Enum

import pytest

from grading.active_question_authority import (
    ActiveQuestionAuthorityError,
    ContextPolicy,
    resolve_active_question_authority,
)
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult,
    GradingSpecRef,
    ResolvedPaperScoringAuthority,
)
from grading.contracts.policy import SCORING_SEMANTICS_V1
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    activate_version,
    approve_version,
    create_initial_version,
    validate_version,
)
from tests._rubric_authoring_support import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


@dataclass(frozen=True, slots=True)
class _Selection:
    grading_spec_ref: object
    question_id: object
    question_text: object
    context_policy: object
    active_rubric: object


class _Source:
    """Test-local stand-in for an already-admitted ACTIVE-spec source."""

    def __init__(self, selected: object) -> None:
        self._selected = selected

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        return self._selected


def _active_rubric() -> RubricAuthoringVersion:
    draft = create_initial_version(simple_basis(), simple_content())
    validated = validate_version(draft, limits=authoring_test_limits())
    approved = approve_version(validated, teacher_ref="teacher-42")
    return activate_version(approved, limits=authoring_test_limits())


def _paper_authority() -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id="SPEC-1", version=1),
        expected_questions=(
            ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=RubricRef(id="R-Q1", version=1),
                scoring_policy_ref=ScoringPolicyRef(
                    id="P-Q1",
                    version=1,
                    scoring_semantics_version=SCORING_SEMANTICS_V1,
                ),
            ),
        ),
        minimum_score=ScoringDecimal.from_raw("0"),
        maximum_score=ScoringDecimal.from_raw("5"),
    )


def _resolve_with_policy(policy: object):
    paper = _paper_authority()
    selected = _Selection(
        grading_spec_ref=paper.grading_spec_ref,
        question_id="Q1",
        question_text="Explain the required result.",
        context_policy=policy,
        active_rubric=_active_rubric(),
    )
    return resolve_active_question_authority(
        paper_authority=paper,
        question_id="Q1",
        source=_Source(selected),
    )


def test_cp01_missing_context_policy_fails_domain_safely() -> None:
    paper = _paper_authority()

    @dataclass(frozen=True, slots=True)
    class _MissingPolicySelection:
        grading_spec_ref: object
        question_id: object
        question_text: object
        active_rubric: object

    source = _Source(
        _MissingPolicySelection(
            grading_spec_ref=paper.grading_spec_ref,
            question_id="Q1",
            question_text="Explain the required result.",
            active_rubric=_active_rubric(),
        )
    )

    with pytest.raises(ActiveQuestionAuthorityError):
        resolve_active_question_authority(
            paper_authority=paper,
            question_id="Q1",
            source=source,
        )


class _StrSubclass(str):
    pass


class _OtherPolicy(str, Enum):
    DIRECT = "DIRECT"


@pytest.mark.parametrize(
    "bad_policy",
    [
        None,
        "DIRECT",
        "HYBRID_RETRIEVAL",
        _StrSubclass("DIRECT"),
        _OtherPolicy.DIRECT,
        object(),
    ],
)
def test_cp02_noncanonical_context_policy_values_are_rejected(
    bad_policy: object,
) -> None:
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve_with_policy(bad_policy)


@pytest.mark.parametrize("policy", tuple(ContextPolicy))
def test_cp03_all_canonical_context_policies_preserve_identity(
    policy: ContextPolicy,
) -> None:
    resolved = _resolve_with_policy(policy)
    assert resolved.context_policy is policy


@pytest.mark.parametrize("raw_value", ["DIRECT", "NOT_A_POLICY"])
def test_cp04_forged_exact_context_policy_instances_are_rejected(
    raw_value: str,
) -> None:
    # str.__new__ can manufacture an exact ContextPolicy instance without
    # Enum's canonical-member construction. Exact runtime type alone is not
    # sufficient admission for an authority-bearing enum value.
    forged = str.__new__(ContextPolicy, raw_value)
    assert type(forged) is ContextPolicy
    assert all(forged is not member for member in ContextPolicy)

    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve_with_policy(forged)


def test_cp05_context_policy_projection_is_immutable() -> None:
    resolved = _resolve_with_policy(ContextPolicy.REFERENCE_ONLY)
    with pytest.raises(FrozenInstanceError):
        resolved.context_policy = ContextPolicy.DIRECT  # type: ignore[misc]
