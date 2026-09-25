from __future__ import annotations

from dataclasses import replace
import os
import subprocess
import sys

import pytest

from grading.rubric.compiler import CompiledRubricCandidate, compile_rubric_content
from grading.rubric.errors import RubricCompilationError
from grading.rubric.models import AuthoringCapRule, AuthoringCriterionCondition
from grading.rubric.profile import RUBRIC_COMPILER_PROFILE_VERSION
from tests.support.rubric_authoring import (
    sd,
    simple_basis,
    simple_content,
    authoring_test_limits,
)


def full(criterion_id: str) -> AuthoringCriterionCondition:
    return AuthoringCriterionCondition(criterion_id, ("FULL",))


def compile_content(content, *, basis=None, version=1, limits=None):
    return compile_rubric_content(
        content,
        finalized_question=basis or simple_basis(),
        version=version,
        limits=limits or authoring_test_limits(),
    )


def test_compiler_output_is_candidate_not_direct_reducer_authority() -> None:
    compiled = compile_content(simple_content(), version=3)

    assert type(compiled) is CompiledRubricCandidate
    assert not hasattr(compiled, "authority")
    assert not hasattr(compiled, "rubric")
    assert not hasattr(compiled, "policy")
    assert compiled.finalized_question == simple_basis()
    assert compiled.source_content == simple_content()
    assert compiled.version == 3


def test_compilation_is_deterministic_and_canonicalizes_rule_condition_order() -> None:
    base = simple_content()
    first = replace(
        base,
        caps=(
            AuthoringCapRule("Z-CAP", (full("C2"), full("C1")), sd(5)),
            AuthoringCapRule("A-CAP", (full("C1"),), sd(5)),
        ),
    )
    second = replace(
        base,
        caps=(
            AuthoringCapRule("A-CAP", (full("C1"),), sd(5)),
            AuthoringCapRule("Z-CAP", (full("C1"), full("C2")), sd(5)),
        ),
    )

    compiled_one = compile_content(first, version=7)
    compiled_two = compile_content(second, version=7)

    assert compiled_one.source_content_hash == compiled_two.source_content_hash
    assert compiled_one.compiled_authority_hash == compiled_two.compiled_authority_hash
    assert compiled_one.finalized_question == compiled_two.finalized_question
    assert compiled_one.version == compiled_two.version


def test_compiler_same_exact_input_repeats_bit_stable_fingerprints() -> None:
    content = simple_content()

    first = compile_content(content)
    second = compile_content(content)

    assert first == second
    assert len(first.source_content_hash) == 64
    assert len(first.finalized_question_hash) == 64
    assert len(first.compiled_authority_hash) == 64
    assert len(first.compilation_limits_hash) == 64
    assert first.compiler_profile_version == RUBRIC_COMPILER_PROFILE_VERSION
    assert first.reconciliation_state_count == 4


def test_compiler_refuses_lint_errors_and_preserves_result_for_diagnostics() -> None:
    with pytest.raises(RubricCompilationError) as exc_info:
        compile_content(simple_content(), basis=simple_basis(max_marks=6))

    lint_result = exc_info.value.lint_result
    assert lint_result is not None
    assert {issue.code for issue in lint_result.errors} == {"MARKS_DO_NOT_RECONCILE"}


def test_compiler_fingerprints_are_stable_across_hash_seeds() -> None:
    code = r'''
import grading.rubric as r
from tests.support.rubric_authoring import simple_content, simple_basis, authoring_test_limits
c = r.compile_rubric_content(simple_content(), finalized_question=simple_basis(), version=7, limits=authoring_test_limits())
print(c.source_content_hash)
print(c.finalized_question_hash)
print(c.compiled_authority_hash)
print(c.compilation_limits_hash)
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
