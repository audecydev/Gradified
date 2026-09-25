from __future__ import annotations

from dataclasses import dataclass

from grading.active_question_authority import (
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
from tests.support.rubric_authoring import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


_AUTHORITATIVE_QUESTION_TEXT = "Explain  why ΔE = 0.\nGive two reasons."


@dataclass(frozen=True, slots=True)
class _SelectedActiveQuestion:
    grading_spec_ref: GradingSpecRef
    question_id: str
    question_text: str
    context_policy: ContextPolicy
    active_rubric: RubricAuthoringVersion


class _ConfiguredActiveSpecSourceDouble:
    """Test-local stand-in for an already-admitted ACTIVE-spec source.

    The source double does not authenticate backend provenance. RED2 tests only
    exact preservation of authoritative question text already selected upstream.
    """

    def __init__(self, selected: _SelectedActiveQuestion) -> None:
        self._selected = selected
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> _SelectedActiveQuestion:
        self.calls.append((grading_spec_ref, question_id))
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


def test_preserves_exact_authoritative_question_text_from_active_source() -> None:
    paper_authority = _paper_authority()
    expected_question = paper_authority.expected_questions[0]
    active_rubric = _active_rubric()
    selected = _SelectedActiveQuestion(
        grading_spec_ref=paper_authority.grading_spec_ref,
        question_id=expected_question.question_id,
        question_text=_AUTHORITATIVE_QUESTION_TEXT,
        context_policy=ContextPolicy.DIRECT,
        active_rubric=active_rubric,
    )
    source = _ConfiguredActiveSpecSourceDouble(selected)

    resolved = resolve_active_question_authority(
        paper_authority=paper_authority,
        question_id=expected_question.question_id,
        source=source,
    )

    assert source.calls == [
        (paper_authority.grading_spec_ref, expected_question.question_id)
    ]
    assert resolved.question_text == _AUTHORITATIVE_QUESTION_TEXT
