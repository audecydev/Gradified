from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import (
    DependencyCycleError,
    InvalidScoringAuthorityError,
    UnknownAuthorityCriterionError,
    UnknownAuthorityPerformanceLevelError,
    UnknownCriterionError,
    UnknownPerformanceLevelError,
)
from grading.contracts.policy import (
    SCORING_SEMANTICS_V1,
    CapRule,
    CriterionCondition,
    DeductionRule,
    GateRule,
    PositiveCreditDependencyRule,
    QuestionScoringPolicy,
)
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric, PerformanceLevel
from grading.contracts.scoring_decimal import ScoringDecimal


def sd(raw: object) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


def criterion(criterion_id: str, full_marks: object) -> AtomicCriterion:
    return AtomicCriterion(
        criterion_id,
        f"Assess criterion {criterion_id}.",
        (
            PerformanceLevel("FULL", sd(full_marks)),
            PerformanceLevel("PARTIAL", sd("0.5")),
            PerformanceLevel("NONE", sd(0)),
        ),
    )


def rubric(question_id: str = "Q1", max_marks: object = 5) -> CompiledQuestionRubric:
    return CompiledQuestionRubric(
        "R1",
        1,
        question_id,
        sd(max_marks),
        (criterion("C1", 2), criterion("C2", 3)),
    )


def policy(
    question_id: str = "Q1",
    maximum_score: object = 5,
    **overrides: object,
) -> QuestionScoringPolicy:
    values: dict[str, object] = {
        "policy_id": "P1",
        "version": 1,
        "question_id": question_id,
        "scoring_semantics_version": SCORING_SEMANTICS_V1,
        "minimum_score": sd(0),
        "maximum_score": sd(maximum_score),
    }
    values.update(overrides)
    return QuestionScoringPolicy(**values)  # type: ignore[arg-type]


def test_valid_rubric_and_policy_form_question_scoring_authority() -> None:
    authority = QuestionScoringAuthority(rubric(), policy())
    assert authority.rubric.question_id == "Q1"


def test_authority_rejects_question_id_mismatch() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        QuestionScoringAuthority(rubric("Q1"), policy("Q2"))


def test_authority_rejects_maximum_mismatch() -> None:
    with pytest.raises(InvalidScoringAuthorityError):
        QuestionScoringAuthority(rubric(max_marks=5), policy(maximum_score=4))


def test_authority_rejects_dependency_targeting_unknown_criterion() -> None:
    dependency = PositiveCreditDependencyRule(
        "DEP-1",
        "MISSING",
        (CriterionCondition("C1", ("FULL",)),),
    )
    with pytest.raises(UnknownAuthorityCriterionError):
        QuestionScoringAuthority(
            rubric(),
            policy(positive_credit_dependencies=(dependency,)),
        )


def _dependency(condition: CriterionCondition) -> dict[str, object]:
    rule = PositiveCreditDependencyRule("DEP-1", "C2", (condition,))
    return {"positive_credit_dependencies": (rule,)}


def _gate(condition: CriterionCondition) -> dict[str, object]:
    return {"gates": (GateRule("GATE-1", (condition,), sd(4)),)}


def _cap(condition: CriterionCondition) -> dict[str, object]:
    return {"caps": (CapRule("CAP-1", (condition,), sd(4)),)}


def _deduction(condition: CriterionCondition) -> dict[str, object]:
    return {"deductions": (DeductionRule("DED-1", (condition,), sd("0.25")),)}


RULE_FACTORIES: tuple[Callable[[CriterionCondition], dict[str, object]], ...] = (
    _dependency,
    _gate,
    _cap,
    _deduction,
)


@pytest.mark.parametrize("factory", RULE_FACTORIES)
def test_every_condition_bearing_rule_rejects_unknown_criterion(
    factory: Callable[[CriterionCondition], dict[str, object]],
) -> None:
    overrides = factory(CriterionCondition("MISSING", ("FULL",)))
    with pytest.raises(UnknownAuthorityCriterionError):
        QuestionScoringAuthority(rubric(), policy(**overrides))


@pytest.mark.parametrize("factory", RULE_FACTORIES)
def test_every_condition_bearing_rule_rejects_unknown_level(
    factory: Callable[[CriterionCondition], dict[str, object]],
) -> None:
    overrides = factory(CriterionCondition("C1", ("UNKNOWN",)))
    with pytest.raises(UnknownAuthorityPerformanceLevelError):
        QuestionScoringAuthority(rubric(), policy(**overrides))


def test_authority_rejects_self_dependency_cycle() -> None:
    dependency = PositiveCreditDependencyRule(
        "DEP-1",
        "C1",
        (CriterionCondition("C1", ("FULL",)),),
    )
    with pytest.raises(DependencyCycleError):
        QuestionScoringAuthority(
            rubric(),
            policy(positive_credit_dependencies=(dependency,)),
        )


def test_authority_rejects_multi_criterion_dependency_cycle() -> None:
    dependencies = (
        PositiveCreditDependencyRule(
            "DEP-1",
            "C1",
            (CriterionCondition("C2", ("FULL",)),),
        ),
        PositiveCreditDependencyRule(
            "DEP-2",
            "C2",
            (CriterionCondition("C1", ("FULL",)),),
        ),
    )
    with pytest.raises(DependencyCycleError):
        QuestionScoringAuthority(
            rubric(),
            policy(positive_credit_dependencies=dependencies),
        )


def test_independent_steps_do_not_gain_implicit_dependency() -> None:
    authority = QuestionScoringAuthority(rubric(), policy())
    assert authority.policy.positive_credit_dependencies == ()


def test_authority_reference_failures_preserve_authority_origin_and_reference_kind() -> None:
    dependency = PositiveCreditDependencyRule(
        "DEP-1",
        "MISSING",
        (CriterionCondition("C1", ("FULL",)),),
    )

    with pytest.raises(UnknownAuthorityCriterionError) as exc_info:
        QuestionScoringAuthority(
            rubric(),
            policy(positive_credit_dependencies=(dependency,)),
        )

    assert isinstance(exc_info.value, InvalidScoringAuthorityError)
    assert isinstance(exc_info.value, UnknownCriterionError)

    bad_gate = GateRule(
        "GATE-1",
        (CriterionCondition("C1", ("UNKNOWN",)),),
        sd(4),
    )
    with pytest.raises(UnknownAuthorityPerformanceLevelError) as level_exc:
        QuestionScoringAuthority(rubric(), policy(gates=(bad_gate,)))

    assert isinstance(level_exc.value, InvalidScoringAuthorityError)
    assert isinstance(level_exc.value, UnknownPerformanceLevelError)


def test_authority_graph_is_deeply_immutable() -> None:
    cap = CapRule(
        "CAP-1",
        (CriterionCondition("C1", ("FULL",)),),
        sd(4),
    )
    item = QuestionScoringAuthority(rubric(), policy(caps=(cap,)))

    with pytest.raises(FrozenInstanceError):
        item.policy = policy()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        item.rubric.criteria[0].operational_description = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        item.policy.caps += (cap,)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        item.policy.caps[0].trigger_conditions += (
            CriterionCondition("C2", ("FULL",)),
        )  # type: ignore[misc]

    index = item.rubric.criteria_by_id()
    index.clear()
    assert tuple(c.criterion_id for c in item.rubric.criteria) == ("C1", "C2")


def test_authority_wrapper_does_not_replace_slice2_marks_reconciliation() -> None:
    # Batch A validates structural/cross-reference safety only. The Slice 2
    # linter/compiler must reject impossible authoring-time mark allocations
    # before activation; the reducer independently enforces final bounds.
    high_contribution_rubric = CompiledQuestionRubric(
        "R1",
        1,
        "Q1",
        sd(5),
        (
            AtomicCriterion(
                "C1",
                "Synthetic high contribution used to document validation scope.",
                (PerformanceLevel("FULL", sd(100)),),
            ),
        ),
    )

    item = QuestionScoringAuthority(high_contribution_rubric, policy())
    assert item.rubric.criteria[0].performance_levels[0].contribution == sd(100)


def test_deep_acyclic_dependency_chain_does_not_depend_on_python_recursion_limit() -> None:
    criterion_count = 1200
    criteria = tuple(
        AtomicCriterion(
            f"C{index}",
            f"Synthetic criterion {index}.",
            (PerformanceLevel("FULL", sd(0)),),
        )
        for index in range(criterion_count)
    )
    deep_rubric = CompiledQuestionRubric("R-DEEP", 1, "Q1", sd(5), criteria)
    dependencies = tuple(
        PositiveCreditDependencyRule(
            f"DEP-{index}",
            f"C{index}",
            (CriterionCondition(f"C{index - 1}", ("FULL",)),),
        )
        for index in range(1, criterion_count)
    )
    deep_policy = policy(positive_credit_dependencies=dependencies)

    item = QuestionScoringAuthority(deep_rubric, deep_policy)
    assert len(item.rubric.criteria) == criterion_count
