from __future__ import annotations

from dataclasses import dataclass

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
    get_active_scoring_authority,
    validate_version,
)
from tests._rubric_authoring_support import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


@dataclass(frozen=True, slots=True)
class _SelectedActiveQuestion:
    """Test-only snapshot returned by an already-admitted source double.

    This value does not authenticate a backend, tenant, caller, or source
    implementation. It represents the result of an upstream authority lookup
    so RED1 can exercise only the grading-core resolver boundary.
    """

    grading_spec_ref: GradingSpecRef
    question_id: str
    question_text: str
    context_policy: object
    active_rubric: RubricAuthoringVersion


class _ConfiguredActiveSpecSourceDouble:
    """Test representation of an upstream-configured ACTIVE-spec source.

    The double is intentionally local to this test. Its Python type is not a
    trust credential; production authorization/admission of a source remains
    outside the grading-core resolver.
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


def test_resolves_binding_core_from_paper_authority_and_source_selected_active_rubric() -> None:
    # Establish the real existing authority fixtures *before* importing the
    # missing resolver. If these assumptions are wrong, RED1 must fail here
    # rather than hiding a bad fixture behind ModuleNotFoundError.
    paper_authority = _paper_authority()
    active_rubric = _active_rubric()
    expected_question = paper_authority.expected_questions[0]
    expected_scoring_authority = get_active_scoring_authority(active_rubric)

    assert RubricRef(
        id=expected_scoring_authority.rubric.rubric_id,
        version=expected_scoring_authority.rubric.version,
    ) == expected_question.rubric_ref
    assert ScoringPolicyRef(
        id=expected_scoring_authority.policy.policy_id,
        version=expected_scoring_authority.policy.version,
        scoring_semantics_version=(
            expected_scoring_authority.policy.scoring_semantics_version
        ),
    ) == expected_question.scoring_policy_ref

    # Historical RED1 imported the then-missing resolver only after establishing
    # real authority fixtures. The fixture now also supplies the subsequently
    # authorized context-policy field; historical RED evidence remains recorded
    # by the earlier artifact hash/run.
    from grading.active_question_authority import (
        ContextPolicy,
        resolve_active_question_authority,
    )

    selected = _SelectedActiveQuestion(
        grading_spec_ref=paper_authority.grading_spec_ref,
        question_id=expected_question.question_id,
        question_text="Explain the required result.",
        context_policy=ContextPolicy.DIRECT,
        active_rubric=active_rubric,
    )
    source = _ConfiguredActiveSpecSourceDouble(selected)

    resolved = resolve_active_question_authority(
        paper_authority=paper_authority,
        question_id=expected_question.question_id,
        source=source,
    )

    # The resolver must query the configured source with the exact admitted
    # paper spec identity and requested question. No latest/fallback lookup.
    assert source.calls == [
        (paper_authority.grading_spec_ref, expected_question.question_id)
    ]

    # RED1 establishes only the positive binding core. Hostile mismatch,
    # lifecycle, source-selection, and aliasing cases follow immediately after
    # the minimum GREEN.
    assert resolved.grading_spec_ref == paper_authority.grading_spec_ref
    assert resolved.question_id == expected_question.question_id
    assert resolved.rubric_content == active_rubric.content
    assert resolved.scoring_authority == expected_scoring_authority
