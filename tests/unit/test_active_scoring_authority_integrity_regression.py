from __future__ import annotations

from dataclasses import replace

import pytest

from grading.rubric.errors import RubricAuthoringError, RubricLifecycleError
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    activate_version,
    approve_version,
    create_initial_version,
    get_active_scoring_authority,
    validate_version,
)
from tests.support.rubric_authoring import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


def _active() -> RubricAuthoringVersion:
    draft = create_initial_version(simple_basis(), simple_content())
    validated = validate_version(draft, limits=authoring_test_limits())
    approved = approve_version(validated, teacher_ref="teacher-42")
    return activate_version(approved, limits=authoring_test_limits())


def _non_scoring_authoring_change(active: RubricAuthoringVersion):
    first_criterion = active.content.criteria[0]
    changed_level = replace(
        first_criterion.performance_levels[0],
        operational_description="Post-approval semantic substitution.",
    )
    changed_criterion = replace(
        first_criterion,
        performance_levels=(changed_level, *first_criterion.performance_levels[1:]),
    )
    return replace(
        active.content,
        criteria=(changed_criterion, *active.content.criteria[1:]),
    )


def test_active_exposure_rejects_post_construction_non_scoring_authoring_semantic_change() -> None:
    active = _active()
    get_active_scoring_authority(active)  # prove the legitimate fixture first

    object.__setattr__(active, "content", _non_scoring_authoring_change(active))

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    (
        ("teacher_ref", ""),
        ("rubric_id", "R-FORGED"),
        ("question_id", "Q-FORGED"),
        ("version", 999),
        ("finalized_question_hash", "0" * 64),
        ("source_content_hash", "0" * 64),
        ("compiled_authority_hash", "0" * 64),
        ("compiler_profile_version", "999"),
    ),
)
def test_active_exposure_rejects_each_approval_binding_mutation(
    field_name: str,
    forged_value: object,
) -> None:
    active = _active()
    assert active.approval is not None
    object.__setattr__(active.approval, field_name, forged_value)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    (
        ("source_content_hash", "0" * 64),
        ("finalized_question_hash", "0" * 64),
        ("compiled_authority_hash", "0" * 64),
        ("version", 999),
        ("compiler_profile_version", "999"),
    ),
)
def test_active_exposure_rejects_compilation_binding_or_provenance_mutation(
    field_name: str,
    forged_value: object,
) -> None:
    active = _active()
    assert active.compilation is not None
    object.__setattr__(active.compilation, field_name, forged_value)

    with pytest.raises(RubricAuthoringError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_missing_activation_limits() -> None:
    active = _active()
    object.__setattr__(active, "activation_limits", None)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_wrong_activation_limits_hash() -> None:
    active = _active()
    object.__setattr__(active, "activation_limits_hash", "0" * 64)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_coordinated_forged_source_hash_claims() -> None:
    active = _active()
    assert active.compilation is not None
    assert active.approval is not None
    forged = "0" * 64
    object.__setattr__(active, "source_content_hash", forged)
    object.__setattr__(active.compilation, "source_content_hash", forged)
    object.__setattr__(active.approval, "source_content_hash", forged)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_coordinated_forged_finalized_question_hash_claims() -> None:
    active = _active()
    assert active.compilation is not None
    assert active.approval is not None
    forged = "0" * 64
    object.__setattr__(active, "finalized_question_hash", forged)
    object.__setattr__(active.compilation, "finalized_question_hash", forged)
    object.__setattr__(active.approval, "finalized_question_hash", forged)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_coordinated_forged_compiled_authority_hash_claims() -> None:
    active = _active()
    assert active.compilation is not None
    assert active.approval is not None
    forged = "0" * 64
    object.__setattr__(active.compilation, "compiled_authority_hash", forged)
    object.__setattr__(active.approval, "compiled_authority_hash", forged)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_compilation_source_content_substitution() -> None:
    active = _active()
    assert active.compilation is not None
    object.__setattr__(
        active.compilation,
        "source_content",
        _non_scoring_authoring_change(active),
    )

    with pytest.raises(RubricAuthoringError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_compilation_finalized_question_substitution() -> None:
    active = _active()
    assert active.compilation is not None
    object.__setattr__(
        active.compilation,
        "finalized_question",
        simple_basis(max_marks=6),
    )

    with pytest.raises(RubricAuthoringError):
        get_active_scoring_authority(active)


@pytest.mark.parametrize("field_name", ("approval", "compilation"))
def test_active_exposure_rejects_wrong_type_nested_substitution_without_incidental_exception(
    field_name: str,
) -> None:
    active = _active()
    object.__setattr__(active, field_name, object())

    with pytest.raises(RubricAuthoringError) as exc_info:
        get_active_scoring_authority(active)

    assert not isinstance(exc_info.value, (AttributeError, TypeError))


def test_active_exposure_rejects_mutated_actual_finalized_question() -> None:
    active = _active()
    object.__setattr__(active, "finalized_question", simple_basis(max_marks=6))

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_normalizes_deep_nested_corruption_to_lifecycle_failure() -> None:
    active = _active()
    level = active.content.criteria[0].performance_levels[0]
    object.__setattr__(level, "contribution", object())

    with pytest.raises(RubricLifecycleError) as exc_info:
        get_active_scoring_authority(active)

    assert isinstance(exc_info.value.__cause__, AttributeError)


def test_semantically_identical_reinstantiated_approval_is_not_rejected_by_object_identity() -> None:
    active = _active()
    assert active.approval is not None
    replacement = replace(active.approval)
    assert replacement == active.approval
    assert replacement is not active.approval
    object.__setattr__(active, "approval", replacement)

    get_active_scoring_authority(active)


def test_active_exposure_rejects_semantically_mismatched_approval_replacement() -> None:
    active = _active()
    assert active.approval is not None
    replacement = replace(active.approval, rubric_id="R-OTHER")
    object.__setattr__(active, "approval", replacement)

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)


def test_active_exposure_rejects_wrong_type_activation_policy_substitution() -> None:
    active = _active()
    object.__setattr__(active, "activation_limits", object())

    with pytest.raises(RubricLifecycleError):
        get_active_scoring_authority(active)
