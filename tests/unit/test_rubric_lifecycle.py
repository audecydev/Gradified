from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.judgment import CriterionJudgment
from grading.rubric.errors import (
    NoMeaningfulRubricChangeError,
    RubricLifecycleError,
)
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    RubricLifecycleState,
    TeacherApproval,
    activate_version,
    approve_version,
    create_initial_version,
    get_active_scoring_authority,
    retire_version,
    revise_version,
    validate_version,
)
from grading.rubric.profile import RUBRIC_COMPILER_PROFILE_VERSION
from grading.scoring.reducer import reduce_question
from tests._rubric_authoring_support import (
    criterion,
    simple_basis,
    simple_content,
    authoring_test_limits,
)


def draft(content=None, *, basis=None):
    return create_initial_version(
        basis or simple_basis(),
        content or simple_content(),
    )


def validated(content=None, *, basis=None):
    return validate_version(
        draft(content, basis=basis),
        limits=authoring_test_limits(),
    )


def test_release1_lifecycle_requires_validation_then_teacher_approval_before_active() -> None:
    initial = draft()

    with pytest.raises(RubricLifecycleError):
        activate_version(initial, limits=authoring_test_limits())

    checked = validate_version(initial, limits=authoring_test_limits())
    with pytest.raises(RubricLifecycleError):
        activate_version(checked, limits=authoring_test_limits())

    approved = approve_version(checked, teacher_ref="teacher-42")
    active = activate_version(approved, limits=authoring_test_limits())

    assert initial.state is RubricLifecycleState.DRAFT
    assert checked.state is RubricLifecycleState.VALIDATED
    assert approved.state is RubricLifecycleState.APPROVED
    assert active.state is RubricLifecycleState.ACTIVE
    assert active.approval is not None
    assert active.approval.teacher_ref == "teacher-42"


def test_only_active_version_exposes_reducer_authority() -> None:
    initial = draft()
    checked = validate_version(initial, limits=authoring_test_limits())
    approved = approve_version(checked, teacher_ref="teacher-42")

    for non_active in (initial, checked, approved):
        with pytest.raises(RubricLifecycleError):
            get_active_scoring_authority(non_active)

    active = activate_version(approved, limits=authoring_test_limits())
    authority = get_active_scoring_authority(active)
    assert type(authority) is QuestionScoringAuthority

    result = reduce_question(
        authority,
        (CriterionJudgment("C1", "FULL"), CriterionJudgment("C2", "FULL")),
    )
    assert result.final_score == simple_basis().max_marks


def test_approval_is_bound_to_exact_question_version_content_authority_and_profile() -> None:
    checked = validated()
    assert checked.compilation is not None

    with pytest.raises(RubricLifecycleError):
        RubricAuthoringVersion(
            finalized_question=checked.finalized_question,
            content=checked.content,
            version=checked.version,
            state=RubricLifecycleState.ACTIVE,
            finalized_question_hash=checked.finalized_question_hash,
            source_content_hash=checked.source_content_hash,
            compilation=checked.compilation,
            approval=None,
        )

    with pytest.raises(RubricLifecycleError):
        TeacherApproval(
            teacher_ref="teacher-42",
            rubric_id=checked.content.rubric_id,
            question_id=checked.finalized_question.question_id,
            version=True,  # type: ignore[arg-type]
            finalized_question_hash=checked.finalized_question_hash,
            source_content_hash=checked.source_content_hash,
            compiled_authority_hash=checked.compilation.compiled_authority_hash,
            compiler_profile_version=RUBRIC_COMPILER_PROFILE_VERSION,
        )

    forged_wrong_question_hash = TeacherApproval(
        teacher_ref="teacher-42",
        rubric_id=checked.content.rubric_id,
        question_id=checked.finalized_question.question_id,
        version=checked.version,
        finalized_question_hash="0" * 64,
        source_content_hash=checked.source_content_hash,
        compiled_authority_hash=checked.compilation.compiled_authority_hash,
        compiler_profile_version=RUBRIC_COMPILER_PROFILE_VERSION,
    )
    with pytest.raises(RubricLifecycleError):
        RubricAuthoringVersion(
            finalized_question=checked.finalized_question,
            content=checked.content,
            version=checked.version,
            state=RubricLifecycleState.APPROVED,
            finalized_question_hash=checked.finalized_question_hash,
            source_content_hash=checked.source_content_hash,
            compilation=checked.compilation,
            approval=forged_wrong_question_hash,
        )

    forged_wrong_content_hash = replace(
        forged_wrong_question_hash,
        finalized_question_hash=checked.finalized_question_hash,
        source_content_hash="0" * 64,
    )
    with pytest.raises(RubricLifecycleError):
        RubricAuthoringVersion(
            finalized_question=checked.finalized_question,
            content=checked.content,
            version=checked.version,
            state=RubricLifecycleState.APPROVED,
            finalized_question_hash=checked.finalized_question_hash,
            source_content_hash=checked.source_content_hash,
            compilation=checked.compilation,
            approval=forged_wrong_content_hash,
        )

    with pytest.raises(RubricLifecycleError):
        replace(
            forged_wrong_question_hash,
            finalized_question_hash=checked.finalized_question_hash,
            compiler_profile_version="999",
        )


def test_meaningful_edit_creates_new_immutable_version_and_resets_approval() -> None:
    v1 = activate_version(
        approve_version(
            validated(),
            teacher_ref="teacher-42",
        ),
        limits=authoring_test_limits(),
    )
    changed = replace(
        simple_content(),
        criteria=(
            criterion("C1", 2, accepted_equivalents=("equivalent method",)),
            criterion("C2", 3),
        ),
    )

    v2 = revise_version(
        v1,
        simple_basis(),
        changed,
    )

    assert v1.state is RubricLifecycleState.ACTIVE
    assert v1.version == 1
    assert v2.version == 2
    assert v2.state is RubricLifecycleState.DRAFT
    assert v2.compilation is None
    assert v2.approval is None
    assert v2.source_content_hash != v1.source_content_hash

    with pytest.raises(FrozenInstanceError):
        v1.state = RubricLifecycleState.RETIRED  # type: ignore[misc]


def test_finalized_question_maximum_change_creates_new_version_and_resets_approval() -> None:
    v1 = activate_version(
        approve_version(validated(), teacher_ref="teacher-42"),
        limits=authoring_test_limits(),
    )
    changed_content = replace(
        simple_content(),
        criteria=(criterion("C1", 3), criterion("C2", 3)),
    )
    v2 = revise_version(
        v1,
        simple_basis(max_marks=6),
        changed_content,
    )

    assert v2.version == 2
    assert v2.state is RubricLifecycleState.DRAFT
    assert v2.finalized_question_hash != v1.finalized_question_hash
    assert v2.approval is None


def test_non_scoring_rubric_content_change_still_invalidates_approval_binding() -> None:
    v1 = draft()
    first_criterion = v1.content.criteria[0]
    changed_level = replace(
        first_criterion.performance_levels[0],
        operational_description="Teacher clarified the FULL-level meaning.",
    )
    changed_criterion = replace(
        first_criterion,
        performance_levels=(changed_level, *first_criterion.performance_levels[1:]),
    )
    changed_content = replace(
        v1.content,
        criteria=(changed_criterion, *v1.content.criteria[1:]),
    )

    v2 = revise_version(
        v1,
        simple_basis(),
        changed_content,
    )

    assert v2.version == 2
    assert v2.source_content_hash != v1.source_content_hash


def test_canonical_rule_reordering_is_not_a_meaningful_new_version() -> None:
    from grading.rubric.models import AuthoringCapRule, AuthoringCriterionCondition
    from tests._rubric_authoring_support import sd

    c1 = AuthoringCriterionCondition("C1", ("FULL",))
    c2 = AuthoringCriterionCondition("C2", ("FULL",))
    first_content = replace(
        simple_content(),
        caps=(AuthoringCapRule("CAP", (c1, c2), sd(5)),),
    )
    reordered = replace(
        first_content,
        caps=(AuthoringCapRule("CAP", (c2, c1), sd(5)),),
    )
    v1 = create_initial_version(
        simple_basis(),
        first_content,
    )

    with pytest.raises(NoMeaningfulRubricChangeError):
        revise_version(
            v1,
            simple_basis(),
            reordered,
        )


def test_retirement_is_immutable_and_preserves_exact_approved_candidate() -> None:
    active = activate_version(
        approve_version(
            validated(),
            teacher_ref="teacher-42",
        ),
        limits=authoring_test_limits(),
    )
    retired = retire_version(active)

    assert active.state is RubricLifecycleState.ACTIVE
    assert retired.state is RubricLifecycleState.RETIRED
    assert retired.compilation is active.compilation
    assert retired.approval is active.approval


def test_teacher_reference_must_be_explicit_but_role_authentication_is_not_invented_here() -> None:
    checked = validated()

    with pytest.raises(RubricLifecycleError):
        approve_version(checked, teacher_ref=" ")
