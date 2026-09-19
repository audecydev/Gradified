from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import inspect
import os
import subprocess
import sys

import pytest

import grading.rubric as rubric_api
import grading.rubric.errors as rubric_errors
import grading.rubric.projection as rubric_projection
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import InvalidScoringAuthorityError
from grading.contracts.judgment import CriterionJudgment
from grading.rubric.errors import RubricCompilationError, RubricLifecycleError
from grading.rubric.fingerprint import compiled_authority_fingerprint
from grading.scoring.reducer import reduce_question
from tests._rubric_authoring_support import criterion, level, sd, simple_content


_REQUIRED_PUBLIC_API = (
    "FinalizedQuestionScoringBasis",
    "RubricCompilationLimits",
    "CompiledRubricCandidate",
    "get_active_scoring_authority",
)


def _require_public_api(*names: str) -> None:
    missing = [name for name in names if not hasattr(rubric_api, name)]
    if missing:
        pytest.skip("blocked by missing prerequisite public API: " + ", ".join(missing))


def _require_resource_error() -> None:
    if not hasattr(rubric_errors, "RubricResourceLimitError"):
        pytest.skip("blocked by missing prerequisite RubricResourceLimitError")


def _basis(question_id: str = "Q1", max_marks: object = 5):
    _require_public_api("FinalizedQuestionScoringBasis")
    return rubric_api.FinalizedQuestionScoringBasis(question_id, sd(max_marks))


def _limits(
    *,
    max_criteria: int = 20,
    max_levels_per_criterion: int = 10,
    max_accepted_equivalents_per_criterion: int = 20,
    max_rules: int = 50,
    max_conditions_per_rule: int = 20,
    max_allowed_level_ids_per_condition: int = 10,
    max_text_characters_per_field: int = 1000,
    max_serialized_authority_bytes: int = 100000,
    max_reconciliation_states: int = 1000,
):
    _require_public_api("RubricCompilationLimits")
    return rubric_api.RubricCompilationLimits(
        max_criteria=max_criteria,
        max_levels_per_criterion=max_levels_per_criterion,
        max_accepted_equivalents_per_criterion=max_accepted_equivalents_per_criterion,
        max_rules=max_rules,
        max_conditions_per_rule=max_conditions_per_rule,
        max_allowed_level_ids_per_condition=max_allowed_level_ids_per_condition,
        max_text_characters_per_field=max_text_characters_per_field,
        max_serialized_authority_bytes=max_serialized_authority_bytes,
        max_reconciliation_states=max_reconciliation_states,
    )


@pytest.mark.parametrize("name", _REQUIRED_PUBLIC_API)
def test_required_boundary_public_api_exists(name: str) -> None:
    assert hasattr(rubric_api, name), name


def test_resource_limit_error_is_a_distinct_authoring_domain_failure() -> None:
    assert hasattr(rubric_errors, "RubricResourceLimitError")
    assert issubclass(
        rubric_errors.RubricResourceLimitError,
        rubric_errors.RubricAuthoringError,
    )


@pytest.mark.parametrize(
    ("callable_name", "required_parameters"),
    (
        ("compile_rubric_content", ("finalized_question", "limits")),
        ("lint_rubric_content", ("finalized_question", "limits")),
        ("create_initial_version", ("finalized_question",)),
        ("validate_version", ("limits",)),
        ("activate_version", ("limits",)),
    ),
)
def test_release1_boundary_requires_explicit_resource_policy(
    callable_name: str,
    required_parameters: tuple[str, ...],
) -> None:
    signature = inspect.signature(getattr(rubric_api, callable_name))
    for parameter_name in required_parameters:
        assert parameter_name in signature.parameters, (
            callable_name,
            parameter_name,
        )
        assert (
            signature.parameters[parameter_name].default is inspect.Parameter.empty
        ), (callable_name, parameter_name)


def test_compilation_limit_contract_has_no_hidden_numeric_defaults_and_is_immutable() -> None:
    _require_public_api("RubricCompilationLimits")
    signature = inspect.signature(rubric_api.RubricCompilationLimits)
    for parameter in signature.parameters.values():
        assert parameter.default is inspect.Parameter.empty, parameter.name

    limits = _limits()
    with pytest.raises(FrozenInstanceError):
        limits.max_rules = 999  # type: ignore[misc]


@pytest.mark.parametrize(
    "forbidden_field",
    ("question_id", "max_marks", "scoring_semantics_version"),
)
def test_authoring_content_cannot_establish_trusted_or_system_authority(
    forbidden_field: str,
) -> None:
    # QuestionRubricAuthoringContent is deliberately the generated/teacher-edited
    # rubric-policy DTO. Trusted finalized-question identity/maximum and system
    # execution semantics are separate inputs, not authored candidate fields.
    names = {field.name for field in fields(rubric_api.QuestionRubricAuthoringContent)}
    assert forbidden_field not in names


def test_legacy_compiled_authority_shortcut_is_not_part_of_public_rubric_api() -> None:
    assert "CompiledRubricAuthority" not in rubric_api.__all__


def test_public_projection_builder_does_not_bypass_activation_boundary() -> None:
    assert not hasattr(rubric_projection, "build_reducer_authority")


def test_finalized_question_scoring_basis_is_narrow_and_immutable() -> None:
    _require_public_api("FinalizedQuestionScoringBasis")
    assert {field.name for field in fields(rubric_api.FinalizedQuestionScoringBasis)} == {
        "question_id",
        "max_marks",
    }
    basis = _basis("Q7", 11)
    assert basis.question_id == "Q7"
    assert basis.max_marks == sd(11)
    with pytest.raises(FrozenInstanceError):
        basis.question_id = "Q8"  # type: ignore[misc]


def test_active_authority_projects_only_the_trusted_question_identity_and_maximum() -> None:
    _require_public_api(
        "FinalizedQuestionScoringBasis",
        "RubricCompilationLimits",
        "get_active_scoring_authority",
    )
    limits = _limits()
    draft = rubric_api.create_initial_version(
        _basis("Q7", 5),
        simple_content(),
    )
    validated = rubric_api.validate_version(draft, limits=limits)
    approved = rubric_api.approve_version(validated, teacher_ref="teacher-42")
    active = rubric_api.activate_version(approved, limits=limits)
    authority = rubric_api.get_active_scoring_authority(active)

    assert authority.rubric.question_id == "Q7"
    assert authority.rubric.max_marks == sd(5)
    assert authority.policy.question_id == "Q7"
    assert authority.policy.maximum_score == sd(5)


def test_internally_consistent_candidate_cannot_redefine_trusted_question_maximum() -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    content = replace(
        simple_content(),
        criteria=(criterion("C1", 10), criterion("C2", 10)),
    )

    with pytest.raises(RubricCompilationError) as exc_info:
        rubric_api.compile_rubric_content(
            content,
            finalized_question=_basis("Q1", 5),
            version=1,
            limits=_limits(),
        )

    assert exc_info.value.lint_result is not None
    assert {issue.code for issue in exc_info.value.lint_result.errors} == {
        "REACHABLE_SCORE_OUT_OF_RANGE"
    }
    assert not hasattr(exc_info.value, "authority")


def test_compiled_candidate_regression_has_no_public_authority_shortcut() -> None:
    _require_public_api(
        "FinalizedQuestionScoringBasis",
        "RubricCompilationLimits",
        "CompiledRubricCandidate",
    )
    compiled = rubric_api.compile_rubric_content(
        simple_content(),
        finalized_question=_basis(),
        version=1,
        limits=_limits(),
    )

    assert type(compiled) is rubric_api.CompiledRubricCandidate
    assert not isinstance(compiled, QuestionScoringAuthority)
    exposed_fields = {field.name for field in fields(compiled)}
    assert {"authority", "rubric", "policy"}.isdisjoint(exposed_fields)
    assert not hasattr(compiled, "authority")
    assert not hasattr(compiled, "rubric")
    assert not hasattr(compiled, "policy")
    assert "CompiledRubricAuthority" not in rubric_api.__all__

    with pytest.raises(InvalidScoringAuthorityError):
        reduce_question(
            compiled,  # type: ignore[arg-type]
            (CriterionJudgment("C1", "FULL"), CriterionJudgment("C2", "FULL")),
        )


def test_supported_reducer_authority_access_requires_active_teacher_approved_version() -> None:
    _require_public_api(
        "FinalizedQuestionScoringBasis",
        "RubricCompilationLimits",
        "get_active_scoring_authority",
    )
    limits = _limits()
    draft = rubric_api.create_initial_version(_basis(), simple_content())
    validated = rubric_api.validate_version(draft, limits=limits)
    approved = rubric_api.approve_version(validated, teacher_ref="teacher-42")
    active = rubric_api.activate_version(approved, limits=limits)
    retired = rubric_api.retire_version(active)

    for non_active in (draft, validated, approved, retired):
        with pytest.raises(RubricLifecycleError):
            rubric_api.get_active_scoring_authority(non_active)

    authority = rubric_api.get_active_scoring_authority(active)
    assert type(authority) is QuestionScoringAuthority
    assert compiled_authority_fingerprint(authority) == active.approval.compiled_authority_hash

    result = reduce_question(
        authority,
        (CriterionJudgment("C1", "FULL"), CriterionJudgment("C2", "FULL")),
    )
    assert result.final_score == sd(5)


def test_top_level_cardinality_limit_is_exact_typed_resource_failure() -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    _require_resource_error()
    content = replace(
        simple_content(),
        criteria=(criterion("C1", 1), criterion("C2", 1)),
    )

    with pytest.raises(rubric_errors.RubricResourceLimitError):
        rubric_api.lint_rubric_content(
            content,
            finalized_question=_basis(max_marks=2),
            version=1,
            limits=_limits(max_criteria=1),
        )




_RESOURCE_DIMENSION_CASES = (
    "max_criteria",
    "max_levels_per_criterion",
    "max_accepted_equivalents_per_criterion",
    "max_rules",
    "max_conditions_per_rule",
    "max_allowed_level_ids_per_condition",
    "max_text_characters_per_field",
)


def _resource_dimension_case(case_name: str):
    base = simple_content()
    c1, c2 = base.criteria
    two_conditions = (
        rubric_api.AuthoringCriterionCondition("C1", ("FULL",)),
        rubric_api.AuthoringCriterionCondition("C2", ("FULL",)),
    )
    if case_name == "max_criteria":
        return base, _limits(max_criteria=1), _basis(max_marks=5)
    if case_name == "max_levels_per_criterion":
        return (
            replace(
                base,
                criteria=(
                    replace(
                        c1,
                        performance_levels=(
                            *c1.performance_levels,
                            level("PARTIAL", 1),
                        ),
                    ),
                    c2,
                ),
            ),
            _limits(max_levels_per_criterion=2),
            _basis(max_marks=5),
        )
    if case_name == "max_accepted_equivalents_per_criterion":
        return (
            replace(
                base,
                criteria=(replace(c1, accepted_equivalents=("a", "b")), c2),
            ),
            _limits(max_accepted_equivalents_per_criterion=1),
            _basis(max_marks=5),
        )
    if case_name == "max_rules":
        return (
            replace(
                base,
                caps=(
                    rubric_api.AuthoringCapRule("CAP1", (), sd(5)),
                    rubric_api.AuthoringCapRule("CAP2", (), sd(5)),
                ),
            ),
            _limits(max_rules=1),
            _basis(max_marks=5),
        )
    if case_name == "max_conditions_per_rule":
        return (
            replace(
                base,
                caps=(rubric_api.AuthoringCapRule("CAP", two_conditions, sd(5)),),
            ),
            _limits(max_conditions_per_rule=1),
            _basis(max_marks=5),
        )
    if case_name == "max_allowed_level_ids_per_condition":
        return (
            replace(
                base,
                caps=(
                    rubric_api.AuthoringCapRule(
                        "CAP",
                        (
                            rubric_api.AuthoringCriterionCondition(
                                "C1", ("FULL", "NOT_MET")
                            ),
                        ),
                        sd(5),
                    ),
                ),
            ),
            _limits(max_allowed_level_ids_per_condition=1),
            _basis(max_marks=5),
        )
    if case_name == "max_text_characters_per_field":
        return base, _limits(max_text_characters_per_field=5), _basis(max_marks=5)
    raise AssertionError(case_name)


@pytest.mark.parametrize("case_name", _RESOURCE_DIMENSION_CASES)
def test_each_declared_structural_resource_dimension_is_actually_enforced(
    case_name: str,
) -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    _require_resource_error()
    content, limits, basis = _resource_dimension_case(case_name)
    with pytest.raises(rubric_errors.RubricResourceLimitError):
        rubric_api.lint_rubric_content(
            content,
            finalized_question=basis,
            version=1,
            limits=limits,
        )


def test_serialized_authority_size_limit_is_enforced_without_a_module_layout_contract() -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    _require_resource_error()
    with pytest.raises(rubric_errors.RubricResourceLimitError):
        rubric_api.compile_rubric_content(
            simple_content(),
            finalized_question=_basis(),
            version=1,
            limits=_limits(max_serialized_authority_bytes=1),
        )


def test_reconciliation_limit_rejects_pathological_state_space_before_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    _require_resource_error()

    # 40 binary criteria imply ~1.1e12 combinations. Resource admission must
    # reject before the reconciliation Cartesian product is even constructed.
    content = replace(
        simple_content(),
        criteria=tuple(criterion(f"C{i}", 1) for i in range(40)),
    )
    basis = _basis(max_marks=40)
    limits = _limits(
        max_criteria=100,
        max_serialized_authority_bytes=1000000,
        max_reconciliation_states=1000,
    )

    import grading.rubric.linter as linter_module

    def forbidden_product(*args, **kwargs):
        raise AssertionError(
            "Reconciliation enumeration started before resource admission rejected the candidate."
        )

    monkeypatch.setattr(linter_module, "product", forbidden_product)

    with pytest.raises(rubric_errors.RubricResourceLimitError) as exc_info:
        rubric_api.lint_rubric_content(
            content,
            finalized_question=basis,
            version=1,
            limits=limits,
        )

    assert exc_info.value.issues
    assert exc_info.value.issues[0].code == "RECONCILIATION_STATE_LIMIT_EXCEEDED"


def test_compilation_records_validation_profile_resource_policy_and_state_space_provenance() -> None:
    _require_public_api(
        "FinalizedQuestionScoringBasis",
        "RubricCompilationLimits",
    )
    limits = _limits()
    compiled = rubric_api.compile_rubric_content(
        simple_content(),
        finalized_question=_basis(),
        version=1,
        limits=limits,
    )

    assert type(compiled.compiler_profile_version) is str
    assert compiled.compiler_profile_version
    assert compiled.compilation_limits == limits
    assert len(compiled.compilation_limits_hash) == 64
    assert compiled.reconciliation_state_count == 4


def test_resource_policy_hash_is_canonical_and_sensitive_to_meaningful_change() -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    first_limits = _limits()
    equivalent_limits = _limits()
    changed_limits = _limits(max_rules=51)

    first = rubric_api.compile_rubric_content(
        simple_content(),
        finalized_question=_basis(),
        version=1,
        limits=first_limits,
    )
    equivalent = rubric_api.compile_rubric_content(
        simple_content(),
        finalized_question=_basis(),
        version=1,
        limits=equivalent_limits,
    )
    changed = rubric_api.compile_rubric_content(
        simple_content(),
        finalized_question=_basis(),
        version=1,
        limits=changed_limits,
    )

    assert first.compilation_limits_hash == equivalent.compilation_limits_hash
    assert first.compilation_limits_hash != changed.compilation_limits_hash


def _approved_version(*, limits=None):
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    effective_limits = limits or _limits()
    draft = rubric_api.create_initial_version(
        _basis(),
        simple_content(),
    )
    validated = rubric_api.validate_version(draft, limits=effective_limits)
    return rubric_api.approve_version(validated, teacher_ref="teacher-42")


def test_teacher_approval_binds_exact_question_version_content_authority_and_compiler_profile() -> None:
    approved = _approved_version()

    assert approved.approval is not None
    assert approved.compilation is not None
    assert approved.approval.rubric_id == approved.content.rubric_id
    assert approved.approval.question_id == approved.finalized_question.question_id
    assert approved.approval.version == approved.version
    assert approved.approval.finalized_question_hash == approved.finalized_question_hash
    assert approved.approval.source_content_hash == approved.source_content_hash
    assert approved.approval.compiled_authority_hash == approved.compilation.compiled_authority_hash
    assert (
        approved.approval.compiler_profile_version
        == approved.compilation.compiler_profile_version
    )


def test_approval_binding_rejects_finalized_question_tampering() -> None:
    approved = _approved_version()
    tampered_basis = replace(approved.finalized_question, max_marks=sd(6))

    with pytest.raises(RubricLifecycleError):
        replace(approved, finalized_question=tampered_basis)


def test_approval_binding_rejects_authored_content_tampering() -> None:
    approved = _approved_version()
    first_criterion = approved.content.criteria[0]
    tampered_criterion = replace(
        first_criterion,
        operational_description=first_criterion.operational_description + " tampered",
    )
    tampered_content = replace(
        approved.content,
        criteria=(tampered_criterion, *approved.content.criteria[1:]),
    )

    with pytest.raises(RubricLifecycleError):
        replace(approved, content=tampered_content)


def test_approval_binding_rejects_compiler_profile_tampering() -> None:
    approved = _approved_version()
    assert approved.approval is not None

    # Rejection may occur while constructing the forged approval itself or at
    # the enclosing lifecycle boundary. Either is safe; successful tampering is not.
    try:
        forged_approval = replace(
            approved.approval,
            compiler_profile_version="tampered-profile",
        )
    except RubricLifecycleError:
        return

    with pytest.raises(RubricLifecycleError):
        replace(approved, approval=forged_approval)


def test_activation_rechecks_current_resource_policy_with_exact_failure_type() -> None:
    _require_public_api("FinalizedQuestionScoringBasis", "RubricCompilationLimits")
    _require_resource_error()
    normal = _limits()
    approved = _approved_version(limits=normal)

    with pytest.raises(rubric_errors.RubricResourceLimitError):
        rubric_api.activate_version(approved, limits=_limits(max_criteria=1))

    active = rubric_api.activate_version(approved, limits=normal)
    assert active.activation_limits_hash == active.compilation.compilation_limits_hash


def test_compiler_fingerprints_are_stable_across_fresh_process_hash_seeds() -> None:
    _require_public_api(
        "FinalizedQuestionScoringBasis",
        "RubricCompilationLimits",
    )
    code = r'''
import grading.rubric as r
from tests._rubric_authoring_support import simple_content, sd
basis = r.FinalizedQuestionScoringBasis("Q1", sd(5))
limits = r.RubricCompilationLimits(
    max_criteria=20,
    max_levels_per_criterion=10,
    max_accepted_equivalents_per_criterion=20,
    max_rules=50,
    max_conditions_per_rule=20,
    max_allowed_level_ids_per_condition=10,
    max_text_characters_per_field=1000,
    max_serialized_authority_bytes=100000,
    max_reconciliation_states=1000,
)
c = r.compile_rubric_content(
    simple_content(),
    finalized_question=basis,
    version=7,
    limits=limits,
)
print(c.source_content_hash)
print(c.finalized_question_hash)
print(c.compiled_authority_hash)
print(c.compilation_limits_hash)
print(c.compiler_profile_version)
print(c.reconciliation_state_count)
'''
    outputs = []
    for seed in ("1", "777", "123456"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in ("src", ".", env.get("PYTHONPATH", "")) if part
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1] == outputs[2]


def test_forged_approval_with_wrong_compiled_authority_hash_is_rejected() -> None:
    limits = _limits()
    checked = rubric_api.validate_version(
        rubric_api.create_initial_version(_basis(), simple_content()),
        limits=limits,
    )
    assert checked.compilation is not None

    forged = rubric_api.TeacherApproval(
        teacher_ref="teacher-42",
        rubric_id=checked.content.rubric_id,
        question_id=checked.finalized_question.question_id,
        version=checked.version,
        finalized_question_hash=checked.finalized_question_hash,
        source_content_hash=checked.source_content_hash,
        compiled_authority_hash="0" * 64,
        compiler_profile_version=checked.compilation.compiler_profile_version,
    )

    with pytest.raises(RubricLifecycleError):
        rubric_api.RubricAuthoringVersion(
            finalized_question=checked.finalized_question,
            content=checked.content,
            version=checked.version,
            state=rubric_api.RubricLifecycleState.APPROVED,
            finalized_question_hash=checked.finalized_question_hash,
            source_content_hash=checked.source_content_hash,
            compilation=checked.compilation,
            approval=forged,
        )


def test_compiled_authority_byte_limit_is_independent_of_authoring_payload_limit() -> None:
    limits = _limits(
        max_text_characters_per_field=1000,
        max_serialized_authority_bytes=2000,
    )
    # The ordinary basis is admitted under the same byte policy.
    rubric_api.compile_rubric_content(
        simple_content(),
        finalized_question=_basis("Q1", 5),
        version=1,
        limits=limits,
    )

    # A long-but-admitted trusted question ID expands the reducer authority while
    # leaving authoring content unchanged. This must fail specifically at the
    # compiled-authority byte boundary.
    with pytest.raises(rubric_errors.RubricResourceLimitError) as exc_info:
        rubric_api.compile_rubric_content(
            simple_content(),
            finalized_question=_basis("Q" * 1000, 5),
            version=1,
            limits=limits,
        )
    assert exc_info.value.issues[0].path == "compiled_authority"


def test_activation_rechecks_compiled_authority_byte_limit_independently() -> None:
    basis = _basis("Q" * 1000, 5)
    validation_limits = _limits(
        max_text_characters_per_field=1000,
        max_serialized_authority_bytes=10000,
    )
    activation_limits = _limits(
        max_text_characters_per_field=1000,
        max_serialized_authority_bytes=2000,
    )
    checked = rubric_api.validate_version(
        rubric_api.create_initial_version(basis, simple_content()),
        limits=validation_limits,
    )
    approved = rubric_api.approve_version(checked, teacher_ref="teacher-42")

    with pytest.raises(rubric_errors.RubricResourceLimitError) as exc_info:
        rubric_api.activate_version(approved, limits=activation_limits)
    assert exc_info.value.issues[0].path == "compiled_authority"


def test_finalized_question_identifier_text_limit_is_independently_enforced() -> None:
    limits = _limits(
        max_text_characters_per_field=1000,
        max_serialized_authority_bytes=10000,
    )
    with pytest.raises(rubric_errors.RubricResourceLimitError) as exc_info:
        rubric_api.lint_rubric_content(
            simple_content(),
            finalized_question=_basis("Q" * 1001, 5),
            version=1,
            limits=limits,
        )
    assert exc_info.value.issues[0].path == "finalized_question.question_id"
