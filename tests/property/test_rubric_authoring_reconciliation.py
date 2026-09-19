from __future__ import annotations

from hypothesis import given, strategies as st

from grading.rubric.compiler import compile_rubric_content
from grading.rubric.linter import lint_rubric_content
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterionCondition,
    QuestionRubricAuthoringContent,
)
from tests._rubric_authoring_support import criterion, sd, simple_basis, authoring_test_limits


def lint(content, *, max_marks: object):
    return lint_rubric_content(
        content,
        finalized_question=simple_basis(max_marks=max_marks),
        version=1,
        limits=authoring_test_limits(),
    )


@given(
    first=st.integers(min_value=1, max_value=20),
    second=st.integers(min_value=1, max_value=20),
)
def test_plain_additive_rubric_reconciles_exactly_to_sum_of_independent_maxima(
    first: int,
    second: int,
) -> None:
    maximum = first + second
    content = QuestionRubricAuthoringContent(
        "R-PROP",
        "P-PROP",
        sd(0),
        (criterion("C1", first), criterion("C2", second)),
    )

    result = lint(content, max_marks=maximum)
    assert result.is_valid
    compiled = compile_rubric_content(
        content,
        finalized_question=simple_basis(max_marks=maximum),
        version=1,
        limits=authoring_test_limits(),
    )
    assert compiled.finalized_question.max_marks == sd(maximum)


@given(
    first=st.integers(min_value=1, max_value=20),
    second=st.integers(min_value=1, max_value=20),
)
def test_policy_cap_can_reconcile_raw_criterion_maxima_above_question_maximum(
    first: int,
    second: int,
) -> None:
    maximum = max(first, second)
    content = QuestionRubricAuthoringContent(
        "R-CAP-PROP",
        "P-CAP-PROP",
        sd(0),
        (criterion("C1", first), criterion("C2", second)),
        caps=(
            AuthoringCapRule(
                "CAP-BOTH",
                (
                    AuthoringCriterionCondition("C1", ("FULL",)),
                    AuthoringCriterionCondition("C2", ("FULL",)),
                ),
                sd(maximum),
            ),
        ),
    )

    assert lint(content, max_marks=maximum).is_valid


@given(mark=st.integers(min_value=1, max_value=20))
def test_reconciliation_rejects_unreachable_trusted_maximum(mark: int) -> None:
    content = QuestionRubricAuthoringContent(
        "R-UNREACHABLE",
        "P-UNREACHABLE",
        sd(0),
        (criterion("C1", mark),),
    )

    result = lint(content, max_marks=mark + 1)
    assert {issue.code for issue in result.errors} == {"MARKS_DO_NOT_RECONCILE"}
