from __future__ import annotations

from dataclasses import replace

import pytest

from grading.rubric.errors import RubricResourceLimitError
from grading.rubric.linter import lint_rubric_collection, lint_rubric_content
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterion,
    AuthoringCriterionCondition,
    AuthoringDeductionRule,
    AuthoringGateRule,
    AuthoringPerformanceLevel,
    AuthoringPositiveCreditDependencyRule,
    AuthoringRoundingRule,
    QuestionRubricAuthoringContent,
)
from tests.support.rubric_authoring import (
    criterion,
    sd,
    simple_basis,
    simple_content,
    authoring_test_limits,
)


def codes(result) -> set[str]:
    return {issue.code for issue in result.errors}


def full(criterion_id: str) -> AuthoringCriterionCondition:
    return AuthoringCriterionCondition(criterion_id, ("FULL",))


def lint(content, *, basis=None, limits=None):
    return lint_rubric_content(
        content,
        finalized_question=basis or simple_basis(),
        version=1,
        limits=limits or authoring_test_limits(),
    )


def test_valid_simple_rubric_lints_cleanly() -> None:
    result = lint(simple_content())
    assert result.is_valid
    assert result.issues == ()


def test_unexpected_projection_value_error_remains_a_technical_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grading.rubric.linter as linter_module

    def unexpected_projection_failure(*args, **kwargs):
        raise ValueError("injected unexpected projection defect")

    monkeypatch.setattr(
        linter_module,
        "_build_reducer_authority",
        unexpected_projection_failure,
    )

    with pytest.raises(ValueError, match="injected unexpected projection defect"):
        lint(simple_content())


def test_collection_rejects_duplicate_rubric_ids() -> None:
    first = simple_content()
    second = replace(first, policy_id="P-Q2")

    result = lint_rubric_collection((first, second))

    assert codes(result) == {"DUPLICATE_RUBRIC_ID"}


def test_linter_rejects_duplicate_criterion_level_and_rule_ids() -> None:
    duplicate_levels = AuthoringCriterion(
        criterion_id="C1",
        operational_description="criterion",
        evidence_requirement="evidence",
        performance_levels=(
            AuthoringPerformanceLevel("FULL", "full one", sd(1)),
            AuthoringPerformanceLevel("FULL", "full two", sd(0)),
        ),
    )
    duplicate_criteria = (duplicate_levels, duplicate_levels)
    content = QuestionRubricAuthoringContent(
        "R1",
        "P1",
        sd(0),
        duplicate_criteria,
        gates=(AuthoringGateRule("RULE", (full("C1"),), sd(1)),),
        caps=(AuthoringCapRule("RULE", (full("C1"),), sd(1)),),
    )

    result = lint(content, basis=simple_basis(max_marks=1))

    assert {
        "DUPLICATE_CRITERION_ID",
        "DUPLICATE_LEVEL_ID",
        "DUPLICATE_RULE_ID",
    } <= codes(result)


def test_linter_rejects_unknown_criterion_and_level_references() -> None:
    unknown_criterion = replace(
        simple_content(),
        caps=(AuthoringCapRule("CAP", (full("MISSING"),), sd(4)),),
    )
    assert codes(lint(unknown_criterion)) == {"UNKNOWN_CRITERION_REFERENCE"}

    unknown_level = replace(
        simple_content(),
        gates=(
            AuthoringGateRule(
                "GATE",
                (AuthoringCriterionCondition("C1", ("UNKNOWN",)),),
                sd(4),
            ),
        ),
    )
    assert codes(lint(unknown_level)) == {"UNKNOWN_LEVEL_REFERENCE"}


def test_linter_rejects_positive_credit_dependency_cycles() -> None:
    content = replace(
        simple_content(),
        positive_credit_dependencies=(
            AuthoringPositiveCreditDependencyRule("D1", "C1", (full("C2"),)),
            AuthoringPositiveCreditDependencyRule("D2", "C2", (full("C1"),)),
        ),
    )

    assert codes(lint(content)) == {"DEPENDENCY_CYCLE"}


@pytest.mark.parametrize(
    "content, expected_code",
    [
        (
            replace(
                simple_content(),
                gates=(AuthoringGateRule("G", (full("C1"),), sd(6)),),
            ),
            "INVALID_RULE",
        ),
        (
            replace(
                simple_content(),
                deductions=(AuthoringDeductionRule("D", (full("C1"),), sd(0)),),
            ),
            "INVALID_RULE",
        ),
        (
            replace(
                simple_content(),
                rounding=AuthoringRoundingRule("R", sd(1), "BANKERSISH"),
            ),
            "INVALID_ROUNDING_MODE",
        ),
        (
            replace(
                simple_content(),
                rounding=AuthoringRoundingRule("R", sd(0), "HALF_UP"),
            ),
            "INVALID_RULE",
        ),
    ],
)
def test_linter_rejects_invalid_gate_deduction_and_rounding_configuration(
    content: QuestionRubricAuthoringContent,
    expected_code: str,
) -> None:
    assert codes(lint(content)) == {expected_code}


def test_marks_reconciliation_uses_complete_policy_not_naive_criterion_sum() -> None:
    capped = QuestionRubricAuthoringContent(
        "R-CAP",
        "P-CAP",
        sd(0),
        (criterion("C1", 4), criterion("C2", 4)),
        caps=(AuthoringCapRule("CAP-BOTH", (full("C1"), full("C2")), sd(5)),),
    )
    assert lint(capped, basis=simple_basis(question_id="Q-CAP", max_marks=5)).is_valid

    rounded = QuestionRubricAuthoringContent(
        "R-ROUND",
        "P-ROUND",
        sd(0),
        (criterion("C1", "2.4"), criterion("C2", "2.4")),
        rounding=AuthoringRoundingRule("ROUND", sd(1), "HALF_UP"),
    )
    assert lint(rounded, basis=simple_basis(question_id="Q-ROUND", max_marks=5)).is_valid

    deducted = QuestionRubricAuthoringContent(
        "R-DED",
        "P-DED",
        sd(0),
        (criterion("C1", 3), criterion("C2", 3)),
        deductions=(
            AuthoringDeductionRule("DED-BOTH", (full("C1"), full("C2")), sd(1)),
        ),
    )
    assert lint(deducted, basis=simple_basis(question_id="Q-DED", max_marks=5)).is_valid


def test_linter_rejects_reachable_runtime_overflow_and_unreachable_question_maximum() -> None:
    overflow = QuestionRubricAuthoringContent(
        "R-OVER",
        "P-OVER",
        sd(0),
        (criterion("C1", 4), criterion("C2", 4)),
    )
    assert codes(lint(overflow, basis=simple_basis(question_id="Q-OVER", max_marks=5))) == {
        "REACHABLE_SCORE_OUT_OF_RANGE"
    }

    assert codes(lint(simple_content(), basis=simple_basis(max_marks=6))) == {
        "MARKS_DO_NOT_RECONCILE"
    }


def test_linter_rejects_reachable_deduction_below_minimum() -> None:
    content = QuestionRubricAuthoringContent(
        "R-NEG",
        "P-NEG",
        sd(0),
        (
            AuthoringCriterion(
                "C1",
                "criterion",
                "evidence",
                (
                    AuthoringPerformanceLevel("FULL", "full", sd(1)),
                    AuthoringPerformanceLevel("NOT_MET", "not met", sd(0)),
                ),
            ),
        ),
        deductions=(
            AuthoringDeductionRule(
                "DED",
                (AuthoringCriterionCondition("C1", ("NOT_MET",)),),
                sd(1),
            ),
        ),
    )

    assert codes(lint(content, basis=simple_basis(question_id="Q-NEG", max_marks=1))) == {
        "REACHABLE_SCORE_OUT_OF_RANGE"
    }


def test_reconciliation_state_limit_is_checked_before_enumeration(monkeypatch) -> None:
    content = replace(
        simple_content(),
        criteria=tuple(criterion(f"C{i}", 1) for i in range(8)),
    )

    import grading.rubric.linter as linter_module

    monkeypatch.setattr(
        linter_module,
        "product",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("product() must not run for rejected state spaces")
        ),
    )
    with pytest.raises(RubricResourceLimitError) as exc_info:
        lint(
            content,
            basis=simple_basis(max_marks=8),
            limits=authoring_test_limits(max_reconciliation_states=128),
        )
    assert {issue.code for issue in exc_info.value.issues} == {
        "RECONCILIATION_STATE_LIMIT_EXCEEDED"
    }
