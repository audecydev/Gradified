from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

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
from tests.support.rubric_authoring import (
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


def _resolve_with_text(question_text: object):
    paper = _paper_authority()
    active_rubric = _active_rubric()
    selected = _Selection(
        grading_spec_ref=paper.grading_spec_ref,
        question_id="Q1",
        question_text=question_text,
        context_policy=ContextPolicy.DIRECT,
        active_rubric=active_rubric,
    )
    return resolve_active_question_authority(
        paper_authority=paper,
        question_id="Q1",
        source=_Source(selected),
    )


def test_qt01_missing_question_text_fails_domain_safely() -> None:
    paper = _paper_authority()
    active_rubric = _active_rubric()

    @dataclass(frozen=True, slots=True)
    class _MissingTextSelection:
        grading_spec_ref: object
        question_id: object
        context_policy: object
        active_rubric: object

    source = _Source(
        _MissingTextSelection(
            grading_spec_ref=paper.grading_spec_ref,
            question_id="Q1",
            context_policy=ContextPolicy.DIRECT,
            active_rubric=active_rubric,
        )
    )

    with pytest.raises(ActiveQuestionAuthorityError):
        resolve_active_question_authority(
            paper_authority=paper,
            question_id="Q1",
            source=source,
        )


@pytest.mark.parametrize("bad_text", [None, 7, b"Explain Q1", object()])
def test_qt02_non_string_question_text_is_rejected(bad_text: object) -> None:
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve_with_text(bad_text)


class _StrSubclass(str):
    pass


def test_qt03_string_subclass_question_text_is_rejected() -> None:
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve_with_text(_StrSubclass("Explain Q1"))


def test_qt04_question_text_preserves_whitespace_and_newlines_exactly() -> None:
    text = "  Explain  why ΔE = 0.  \n\nGive two reasons.\t"
    resolved = _resolve_with_text(text)
    assert resolved.question_text == text


def test_qt05_question_text_preserves_unicode_code_points_exactly() -> None:
    text = "ΔE = 0 — कारण बताइए — ಕನ್ನಡ: ಕಾರಣವನ್ನು ವಿವರಿಸಿ 👩🏽‍🔬"
    resolved = _resolve_with_text(text)
    assert resolved.question_text == text
    assert tuple(map(ord, resolved.question_text)) == tuple(map(ord, text))


def test_qt06_question_text_projection_is_immutable() -> None:
    resolved = _resolve_with_text("Explain Q1")
    with pytest.raises(FrozenInstanceError):
        resolved.question_text = "changed"  # type: ignore[misc]
