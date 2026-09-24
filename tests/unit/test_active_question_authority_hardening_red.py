from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, replace

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
from grading.rubric.errors import RubricLifecycleError
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    activate_version,
    approve_version,
    create_initial_version,
    retire_version,
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
    """Test-local source double; this is not a trust/authentication credential."""

    def __init__(self, selected: object) -> None:
        self.selected = selected
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        self.calls.append((grading_spec_ref, question_id))
        return self.selected


def _active(
    *,
    question_id: str = "Q1",
    rubric_id: str = "R-Q1",
    policy_id: str = "P-Q1",
) -> RubricAuthoringVersion:
    content = replace(
        simple_content(),
        rubric_id=rubric_id,
        policy_id=policy_id,
    )
    draft = create_initial_version(
        simple_basis(question_id=question_id),
        content,
    )
    validated = validate_version(draft, limits=authoring_test_limits())
    approved = approve_version(validated, teacher_ref="teacher-42")
    return activate_version(approved, limits=authoring_test_limits())


def _validated(*, question_id: str = "Q1") -> RubricAuthoringVersion:
    draft = create_initial_version(
        simple_basis(question_id=question_id),
        simple_content(),
    )
    return validate_version(draft, limits=authoring_test_limits())


def _paper(
    *,
    spec_id: str = "SPEC-1",
    spec_version: int = 1,
    question_id: str = "Q1",
    rubric_id: str = "R-Q1",
    rubric_version: int = 1,
    policy_id: str = "P-Q1",
    policy_version: int = 1,
) -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id=spec_id, version=spec_version),
        expected_questions=(
            ExpectedQuestionResult(
                question_id=question_id,
                rubric_ref=RubricRef(id=rubric_id, version=rubric_version),
                scoring_policy_ref=ScoringPolicyRef(
                    id=policy_id,
                    version=policy_version,
                    scoring_semantics_version=SCORING_SEMANTICS_V1,
                ),
            ),
        ),
        minimum_score=ScoringDecimal.from_raw("0"),
        maximum_score=ScoringDecimal.from_raw("5"),
    )


def _source_for(
    paper: ResolvedPaperScoringAuthority,
    rubric: RubricAuthoringVersion,
    *,
    spec: object | None = None,
    question: object | None = None,
) -> _Source:
    expected = paper.expected_questions[0]
    return _Source(
        _Selection(
            grading_spec_ref=paper.grading_spec_ref if spec is None else spec,
            question_id=expected.question_id if question is None else question,
            question_text="Explain the required result.",
            context_policy=ContextPolicy.DIRECT,
            active_rubric=rubric,
        )
    )


def _resolve(
    *,
    paper: ResolvedPaperScoringAuthority | None = None,
    source: object | None = None,
    question_id: str = "Q1",
):
    effective_paper = paper or _paper()
    effective_source = source or _source_for(effective_paper, _active())
    return resolve_active_question_authority(
        paper_authority=effective_paper,
        question_id=question_id,
        source=effective_source,
    )


def test_h01_rejects_source_selected_wrong_spec_id() -> None:
    paper = _paper()
    source = _source_for(
        paper,
        _active(),
        spec=GradingSpecRef("SPEC-2", 1),
    )
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h02_rejects_source_selected_stale_spec_version() -> None:
    paper = _paper()
    source = _source_for(
        paper,
        _active(),
        spec=GradingSpecRef("SPEC-1", 2),
    )
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h03_rejects_source_selected_wrong_question() -> None:
    paper = _paper()
    source = _source_for(paper, _active(), question="Q2")
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h04_rejects_rubric_bound_to_different_finalized_question() -> None:
    paper = _paper()
    source = _source_for(paper, _active(question_id="Q2"))
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h05_rejects_wrong_rubric_id() -> None:
    paper = _paper()
    source = _source_for(paper, _active(rubric_id="R-OTHER"))
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h06_rejects_wrong_rubric_version() -> None:
    paper = _paper(rubric_version=2)
    source = _source_for(paper, _active())
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h07_rejects_wrong_policy_id() -> None:
    paper = _paper()
    source = _source_for(paper, _active(policy_id="P-OTHER"))
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h08_rejects_wrong_policy_version() -> None:
    paper = _paper(policy_version=2)
    source = _source_for(paper, _active())
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h09_non_active_lifecycle_failure_remains_native() -> None:
    paper = _paper()
    source = _source_for(paper, _validated())
    with pytest.raises(RubricLifecycleError):
        _resolve(paper=paper, source=source)


def test_h10_retired_lifecycle_failure_remains_native() -> None:
    paper = _paper()
    source = _source_for(paper, retire_version(_active()))
    with pytest.raises(RubricLifecycleError):
        _resolve(paper=paper, source=source)


def test_h11_missing_expected_question_fails_before_source_lookup() -> None:
    paper = _paper()
    source = _source_for(paper, _active())
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source, question_id="Q2")
    assert source.calls == []


def test_h12_malformed_source_result_missing_fields_fails_domain_safely() -> None:
    paper = _paper()
    source = _Source(object())
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


class _EqualSpecImpostor:
    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False


def test_h13_source_spec_must_be_exact_grading_spec_ref() -> None:
    paper = _paper()
    source = _source_for(paper, _active(), spec=_EqualSpecImpostor())
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


class _QuestionIdSubclass(str):
    pass


def test_h14_source_question_id_must_be_exact_string() -> None:
    paper = _paper()
    source = _source_for(
        paper,
        _active(),
        question=_QuestionIdSubclass("Q1"),
    )
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def _forge_spec_ref(*, id_value: object, version_value: object) -> GradingSpecRef:
    forged = object.__new__(GradingSpecRef)
    object.__setattr__(forged, "id", id_value)
    object.__setattr__(forged, "version", version_value)
    return forged


class _StrSubclass(str):
    pass


def test_h15_source_exact_spec_ref_rejects_forged_equal_leaf_types() -> None:
    paper = _paper()
    forged = _forge_spec_ref(
        id_value=_StrSubclass("SPEC-1"),
        version_value=True,
    )
    assert forged == paper.grading_spec_ref  # Python equality alone is insufficient.
    source = _source_for(paper, _active(), spec=forged)
    with pytest.raises(ActiveQuestionAuthorityError):
        _resolve(paper=paper, source=source)


def test_h16_projection_and_exposed_nested_graph_are_immutable() -> None:
    resolved = _resolve()

    with pytest.raises(FrozenInstanceError):
        resolved.question_id = "Q2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resolved.rubric_content.rubric_id = "R2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resolved.rubric_content.criteria[0].operational_description = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resolved.scoring_authority.policy.policy_id = "P2"  # type: ignore[misc]
    with pytest.raises(TypeError):
        resolved.rubric_content.criteria[0] = resolved.rubric_content.criteria[0]  # type: ignore[index]


class _ExplodingSource:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        self.calls.append((grading_spec_ref, question_id))
        raise self.failure


class _ExplodingQuestionTextSelection:
    def __init__(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
        context_policy: ContextPolicy,
        active_rubric: RubricAuthoringVersion,
        failure: Exception,
    ) -> None:
        self.grading_spec_ref = grading_spec_ref
        self.question_id = question_id
        self.context_policy = context_policy
        self.active_rubric = active_rubric
        self._failure = failure

    @property
    def question_text(self) -> str:
        raise self._failure


def test_h17_source_execution_failure_is_normalized_and_chained() -> None:
    paper = _paper()
    failure = RuntimeError("source exploded")
    source = _ExplodingSource(failure)

    with pytest.raises(ActiveQuestionAuthorityError) as excinfo:
        _resolve(paper=paper, source=source)

    assert type(excinfo.value).__name__ == "ActiveQuestionAuthoritySourceExecutionError"
    assert excinfo.value.__cause__ is failure
    assert source.calls == [(paper.grading_spec_ref, "Q1")]


def test_h18_selection_accessor_failure_is_normalized_and_chained() -> None:
    paper = _paper()
    failure = RuntimeError("selection exploded")
    selected = _ExplodingQuestionTextSelection(
        grading_spec_ref=paper.grading_spec_ref,
        question_id="Q1",
        context_policy=ContextPolicy.DIRECT,
        active_rubric=_active(),
        failure=failure,
    )
    source = _Source(selected)

    with pytest.raises(ActiveQuestionAuthorityError) as excinfo:
        _resolve(paper=paper, source=source)

    assert type(excinfo.value).__name__ == "ActiveQuestionAuthoritySourceExecutionError"
    assert excinfo.value.__cause__ is failure
    assert source.calls == [(paper.grading_spec_ref, "Q1")]
