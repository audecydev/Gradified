from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import ScoreOutOfRangeError
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.contracts.policy import CriterionCondition, QuestionScoringPolicy
from grading.contracts.result import (
    CriterionEffect,
    QuestionScoreResult,
    RubricRef,
    RuleDecision,
    RuleType,
    ScoreStage,
    ScoreStageEffect,
    ScoringPolicyRef,
)
from grading.contracts.rubric import AtomicCriterion
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.contracts.validation import validate_criterion_judgments
from grading.scoring.arithmetic import (
    exact_compare,
    exact_minimum,
    exact_subtract,
    exact_sum,
)
from grading.scoring.rounding import _round_to_increment


def _conditions_satisfied(
    conditions: tuple[CriterionCondition, ...],
    selected_levels: Mapping[str, str],
) -> bool:
    """Evaluate one rule predicate against the original semantic judgments."""

    return all(
        selected_levels[condition.criterion_id] in condition.allowed_level_ids
        for condition in conditions
    )


def _selected_contribution(
    criterion: AtomicCriterion,
    selected_level: str,
) -> ScoringDecimal:
    """Return the rubric-authorized contribution for one validated level."""

    for level in criterion.performance_levels:
        if level.level_id == selected_level:
            return level.contribution

    raise RuntimeError(
        "Validated criterion judgment referenced a missing performance level."
    )


def _dependency_decisions_and_blockers(
    policy: QuestionScoringPolicy,
    selected_levels: Mapping[str, str],
) -> tuple[tuple[RuleDecision, ...], dict[str, tuple[str, ...]]]:
    """Evaluate each dependency once and derive canonical blocking-rule IDs."""

    decisions: list[RuleDecision] = []
    blocking_ids_by_target: dict[str, list[str]] = {}

    for dependency in policy.positive_credit_dependencies:
        decision = RuleDecision(
            rule_id=dependency.rule_id,
            rule_type=RuleType.DEPENDENCY,
            triggered=not _conditions_satisfied(
                dependency.prerequisite_conditions,
                selected_levels,
            ),
            configured_effect=None,
        )
        decisions.append(decision)

        if decision.triggered:
            blocking_ids_by_target.setdefault(
                dependency.target_criterion_id,
                [],
            ).append(decision.rule_id)

    canonical_decisions = tuple(
        sorted(
            decisions,
            key=lambda decision: decision.rule_id,
        )
    )

    canonical_blockers = {
        criterion_id: tuple(sorted(rule_ids))
        for criterion_id, rule_ids in blocking_ids_by_target.items()
    }

    return canonical_decisions, canonical_blockers


def _gate_stage(
    score: ScoringDecimal,
    policy: QuestionScoringPolicy,
    selected_levels: Mapping[str, str],
) -> tuple[ScoringDecimal, ScoreStageEffect, tuple[RuleDecision, ...]]:
    """Apply all failed essential-condition ceilings at question scope."""

    decisions: list[RuleDecision] = []
    triggered: list[RuleDecision] = []

    for rule in policy.gates:
        decision = RuleDecision(
            rule_id=rule.rule_id,
            rule_type=RuleType.GATE,
            triggered=not _conditions_satisfied(
                rule.required_conditions,
                selected_levels,
            ),
            configured_effect=rule.failure_ceiling,
        )
        decisions.append(decision)
        if decision.triggered:
            triggered.append(decision)

    after = score
    for decision in triggered:
        ceiling = decision.configured_effect
        if ceiling is None:
            raise RuntimeError(
                "Triggered gate decision is missing its configured ceiling."
            )
        after = exact_minimum(after, ceiling)

    source_rule_ids = tuple(
        sorted(decision.rule_id for decision in triggered)
    )
    return (
        after,
        ScoreStageEffect(
            stage=ScoreStage.GATES,
            before=score,
            after=after,
            source_rule_ids=source_rule_ids,
        ),
        tuple(sorted(decisions, key=lambda decision: decision.rule_id)),
    )


def _cap_stage(
    score: ScoringDecimal,
    policy: QuestionScoringPolicy,
    selected_levels: Mapping[str, str],
) -> tuple[ScoringDecimal, ScoreStageEffect, tuple[RuleDecision, ...]]:
    """Apply all triggered conditional ceilings at question scope."""

    decisions: list[RuleDecision] = []
    triggered: list[RuleDecision] = []

    for rule in policy.caps:
        decision = RuleDecision(
            rule_id=rule.rule_id,
            rule_type=RuleType.CAP,
            triggered=_conditions_satisfied(
                rule.trigger_conditions,
                selected_levels,
            ),
            configured_effect=rule.ceiling,
        )
        decisions.append(decision)
        if decision.triggered:
            triggered.append(decision)

    after = score
    for decision in triggered:
        ceiling = decision.configured_effect
        if ceiling is None:
            raise RuntimeError(
                "Triggered cap decision is missing its configured ceiling."
            )
        after = exact_minimum(after, ceiling)

    source_rule_ids = tuple(
        sorted(decision.rule_id for decision in triggered)
    )
    return (
        after,
        ScoreStageEffect(
            stage=ScoreStage.CAPS,
            before=score,
            after=after,
            source_rule_ids=source_rule_ids,
        ),
        tuple(sorted(decisions, key=lambda decision: decision.rule_id)),
    )


def _deduction_stage(
    score: ScoringDecimal,
    policy: QuestionScoringPolicy,
    selected_levels: Mapping[str, str],
) -> tuple[ScoringDecimal, ScoreStageEffect, tuple[RuleDecision, ...]]:
    """Subtract each independently triggered configured deduction once."""

    decisions: list[RuleDecision] = []
    triggered: list[RuleDecision] = []

    for rule in policy.deductions:
        decision = RuleDecision(
            rule_id=rule.rule_id,
            rule_type=RuleType.DEDUCTION,
            triggered=_conditions_satisfied(
                rule.trigger_conditions,
                selected_levels,
            ),
            configured_effect=rule.amount,
        )
        decisions.append(decision)
        if decision.triggered:
            triggered.append(decision)

    if triggered:
        amounts: list[ScoringDecimal] = []
        for decision in triggered:
            amount = decision.configured_effect
            if amount is None:
                raise RuntimeError(
                    "Triggered deduction decision is missing its configured amount."
                )
            amounts.append(amount)

        total_deduction = exact_sum(tuple(amounts))
        after = exact_subtract(score, total_deduction)
    else:
        after = score

    source_rule_ids = tuple(
        sorted(decision.rule_id for decision in triggered)
    )
    return (
        after,
        ScoreStageEffect(
            stage=ScoreStage.DEDUCTIONS,
            before=score,
            after=after,
            source_rule_ids=source_rule_ids,
        ),
        tuple(sorted(decisions, key=lambda decision: decision.rule_id)),
    )


def _rounding_stage(
    score: ScoringDecimal,
    policy: QuestionScoringPolicy,
) -> tuple[ScoringDecimal, ScoreStageEffect]:
    """Round exactly once at the frozen question-boundary stage."""

    if policy.rounding is None:
        after = score
        source_rule_ids: tuple[str, ...] = ()
    else:
        after = _round_to_increment(score, policy.rounding)
        source_rule_ids = (policy.rounding.rule_id,)

    return (
        after,
        ScoreStageEffect(
            stage=ScoreStage.ROUNDING,
            before=score,
            after=after,
            source_rule_ids=source_rule_ids,
        ),
    )


def _require_final_score_in_range(
    score: ScoringDecimal,
    policy: QuestionScoringPolicy,
) -> None:
    """Reject, rather than clamp, a final score outside academic policy bounds."""

    if (
        exact_compare(score, policy.minimum_score) < 0
        or exact_compare(score, policy.maximum_score) > 0
    ):
        raise ScoreOutOfRangeError(
            "Final question score lies outside the permitted academic range."
        )


def reduce_question(
    authority: QuestionScoringAuthority,
    judgments: tuple[CriterionJudgment, ...],
) -> QuestionScoreResult:
    """Reduce semantic judgments using immutable scoring authority."""

    canonical_judgments = validate_criterion_judgments(
        authority,
        judgments,
    )

    policy = authority.policy
    selected_levels: Mapping[str, str] = MappingProxyType(
        {
            judgment.criterion_id: judgment.selected_level
            for judgment in canonical_judgments
        }
    )

    dependency_decisions, blockers_by_target = (
        _dependency_decisions_and_blockers(
            policy,
            selected_levels,
        )
    )

    zero = ScoringDecimal.from_raw("0")
    criterion_effects: list[CriterionEffect] = []

    for criterion, judgment in zip(
        authority.rubric.criteria,
        canonical_judgments,
        strict=True,
    ):
        base_contribution = _selected_contribution(
            criterion,
            judgment.selected_level,
        )

        blocking_rule_ids = blockers_by_target.get(
            criterion.criterion_id,
            (),
        )

        if (
            blocking_rule_ids
            and exact_compare(base_contribution, zero) > 0
        ):
            effective_contribution = zero
        else:
            effective_contribution = base_contribution

        criterion_effects.append(
            CriterionEffect(
                criterion_id=criterion.criterion_id,
                selected_level=judgment.selected_level,
                base_contribution=base_contribution,
                effective_contribution=effective_contribution,
                blocking_dependency_rule_ids=blocking_rule_ids,
            )
        )

    immutable_effects = tuple(criterion_effects)
    base_subtotal = exact_sum(
        tuple(
            effect.effective_contribution
            for effect in immutable_effects
        )
    )

    after_gates, gate_effect, gate_decisions = _gate_stage(
        base_subtotal,
        policy,
        selected_levels,
    )
    after_caps, cap_effect, cap_decisions = _cap_stage(
        after_gates,
        policy,
        selected_levels,
    )
    after_deductions, deduction_effect, deduction_decisions = _deduction_stage(
        after_caps,
        policy,
        selected_levels,
    )
    final_score, rounding_effect = _rounding_stage(
        after_deductions,
        policy,
    )

    _require_final_score_in_range(final_score, policy)

    rule_decisions = tuple(
        sorted(
            (
                *dependency_decisions,
                *gate_decisions,
                *cap_decisions,
                *deduction_decisions,
            ),
            key=lambda decision: decision.rule_id,
        )
    )

    return QuestionScoreResult(
        question_id=authority.rubric.question_id,
        rubric_ref=RubricRef(
            id=authority.rubric.rubric_id,
            version=authority.rubric.version,
        ),
        scoring_policy_ref=ScoringPolicyRef(
            id=policy.policy_id,
            version=policy.version,
            scoring_semantics_version=policy.scoring_semantics_version,
        ),
        numeric_profile_version=NUMERIC_PROFILE_VERSION,
        criterion_effects=immutable_effects,
        rule_decisions=rule_decisions,
        stage_effects=(
            gate_effect,
            cap_effect,
            deduction_effect,
            rounding_effect,
        ),
        base_subtotal=base_subtotal,
        score_before_rounding=after_deductions,
        final_score=final_score,
        minimum_score=policy.minimum_score,
        maximum_score=policy.maximum_score,
    )
