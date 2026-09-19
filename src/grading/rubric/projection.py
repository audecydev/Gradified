from __future__ import annotations

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.policy import (
    SCORING_SEMANTICS_V1,
    CapRule,
    CriterionCondition,
    DeductionRule,
    GateRule,
    PositiveCreditDependencyRule,
    QuestionScoringPolicy,
    RoundingMode,
    RoundingRule,
)
from grading.contracts.rubric import (
    AtomicCriterion,
    CompiledQuestionRubric,
    PerformanceLevel,
)
from grading.rubric.models import (
    AuthoringCriterionCondition,
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
)


def _condition(condition: AuthoringCriterionCondition) -> CriterionCondition:
    return CriterionCondition(
        criterion_id=condition.criterion_id,
        allowed_level_ids=tuple(sorted(condition.allowed_level_ids)),
    )


def _conditions(
    conditions: tuple[AuthoringCriterionCondition, ...],
) -> tuple[CriterionCondition, ...]:
    compiled = tuple(_condition(condition) for condition in conditions)
    return tuple(
        sorted(
            compiled,
            key=lambda condition: (
                condition.criterion_id,
                condition.allowed_level_ids,
            ),
        )
    )


def _build_reducer_authority(
    content: QuestionRubricAuthoringContent,
    *,
    finalized_question: FinalizedQuestionScoringBasis,
    version: int,
) -> QuestionScoringAuthority:
    """Project candidate content against trusted finalized-question authority."""

    criteria = tuple(
        AtomicCriterion(
            criterion_id=criterion.criterion_id,
            operational_description=criterion.operational_description,
            performance_levels=tuple(
                PerformanceLevel(
                    level_id=level.level_id,
                    contribution=level.contribution,
                )
                for level in criterion.performance_levels
            ),
        )
        for criterion in content.criteria
    )

    rubric = CompiledQuestionRubric(
        rubric_id=content.rubric_id,
        version=version,
        question_id=finalized_question.question_id,
        max_marks=finalized_question.max_marks,
        criteria=criteria,
    )

    dependencies = tuple(
        sorted(
            (
                PositiveCreditDependencyRule(
                    rule_id=rule.rule_id,
                    target_criterion_id=rule.target_criterion_id,
                    prerequisite_conditions=_conditions(rule.prerequisite_conditions),
                )
                for rule in content.positive_credit_dependencies
            ),
            key=lambda rule: rule.rule_id,
        )
    )
    gates = tuple(
        sorted(
            (
                GateRule(
                    rule_id=rule.rule_id,
                    required_conditions=_conditions(rule.required_conditions),
                    failure_ceiling=rule.failure_ceiling,
                )
                for rule in content.gates
            ),
            key=lambda rule: rule.rule_id,
        )
    )
    caps = tuple(
        sorted(
            (
                CapRule(
                    rule_id=rule.rule_id,
                    trigger_conditions=_conditions(rule.trigger_conditions),
                    ceiling=rule.ceiling,
                )
                for rule in content.caps
            ),
            key=lambda rule: rule.rule_id,
        )
    )
    deductions = tuple(
        sorted(
            (
                DeductionRule(
                    rule_id=rule.rule_id,
                    trigger_conditions=_conditions(rule.trigger_conditions),
                    amount=rule.amount,
                )
                for rule in content.deductions
            ),
            key=lambda rule: rule.rule_id,
        )
    )

    rounding = None
    if content.rounding is not None:
        rounding = RoundingRule(
            rule_id=content.rounding.rule_id,
            increment=content.rounding.increment,
            mode=RoundingMode(content.rounding.mode),
        )

    policy = QuestionScoringPolicy(
        policy_id=content.policy_id,
        version=version,
        question_id=finalized_question.question_id,
        scoring_semantics_version=SCORING_SEMANTICS_V1,
        minimum_score=content.minimum_score,
        maximum_score=finalized_question.max_marks,
        positive_credit_dependencies=dependencies,
        gates=gates,
        caps=caps,
        deductions=deductions,
        rounding=rounding,
    )

    return QuestionScoringAuthority(rubric=rubric, policy=policy)
