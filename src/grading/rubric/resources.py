from __future__ import annotations

from dataclasses import dataclass

from grading.rubric.errors import RubricResourceLimitError
from grading.rubric.fingerprint import authoring_content_canonical_bytes
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterionCondition,
    AuthoringDeductionRule,
    AuthoringGateRule,
    AuthoringPositiveCreditDependencyRule,
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
    RubricCompilationLimits,
)


@dataclass(frozen=True, slots=True)
class RubricResourceIssue:
    code: str
    path: str
    message: str


def _rule_conditions(rule: object) -> tuple[AuthoringCriterionCondition, ...]:
    if type(rule) is AuthoringPositiveCreditDependencyRule:
        return rule.prerequisite_conditions
    if type(rule) is AuthoringGateRule:
        return rule.required_conditions
    if type(rule) is AuthoringCapRule:
        return rule.trigger_conditions
    if type(rule) is AuthoringDeductionRule:
        return rule.trigger_conditions
    raise TypeError("Unsupported authoring rule type.")


def _single(code: str, path: str, message: str) -> tuple[RubricResourceIssue, ...]:
    return (RubricResourceIssue(code, path, message),)


def _bounded_reconciliation_state_count(
    content: QuestionRubricAuthoringContent,
    limit: int,
) -> tuple[int, bool]:
    """Return (count, exceeded) without materializing an integer above ``limit``.

    Empty criteria/level sets are semantic-invalidity cases for the linter, not
    resource failures, so they report a count of zero here and are diagnosed by
    ordinary linting later.
    """

    if not content.criteria:
        return 0, False

    count = 1
    for criterion in content.criteria:
        level_count = len(criterion.performance_levels)
        if level_count == 0:
            return 0, False
        if count > limit // level_count:
            return limit, True
        count *= level_count
    return count, False


def resource_limit_issues(
    content: QuestionRubricAuthoringContent,
    *,
    finalized_question: FinalizedQuestionScoringBasis,
    limits: RubricCompilationLimits,
) -> tuple[RubricResourceIssue, ...]:
    """Return the first deterministic resource violation, cheapest checks first.

    Resource admission stops at the first known violation. Once a candidate is
    outside the trusted envelope, continuing to traverse/serialize it would add
    avoidable work and would weaken fail-closed behavior.
    """

    if len(content.criteria) > limits.max_criteria:
        return _single(
            "MAX_CRITERIA_EXCEEDED",
            "criteria",
            "Rubric criterion count exceeds the configured compilation limit.",
        )

    rule_groups = (
        content.positive_credit_dependencies,
        content.gates,
        content.caps,
        content.deductions,
    )
    total_rules = sum(len(group) for group in rule_groups) + (
        1 if content.rounding is not None else 0
    )
    if total_rules > limits.max_rules:
        return _single(
            "MAX_RULES_EXCEEDED",
            "scoring_policy",
            "Rubric scoring-rule count exceeds the configured compilation limit.",
        )

    # Materialize the combined tuple only after its total cardinality is admitted.
    all_rules = tuple(rule for group in rule_groups for rule in group)

    if len(finalized_question.question_id) > limits.max_text_characters_per_field:
        return _single(
            "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
            "finalized_question.question_id",
            "Text field exceeds the configured compilation character limit.",
        )
    for path, value in (("rubric_id", content.rubric_id), ("policy_id", content.policy_id)):
        if len(value) > limits.max_text_characters_per_field:
            return _single(
                "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                path,
                "Text field exceeds the configured compilation character limit.",
            )

    for criterion_index, criterion in enumerate(content.criteria):
        criterion_path = f"criteria[{criterion_index}]"
        if len(criterion.performance_levels) > limits.max_levels_per_criterion:
            return _single(
                "MAX_LEVELS_PER_CRITERION_EXCEEDED",
                f"{criterion_path}.performance_levels",
                "Performance-level count exceeds the configured compilation limit.",
            )
        if (
            len(criterion.accepted_equivalents)
            > limits.max_accepted_equivalents_per_criterion
        ):
            return _single(
                "MAX_ACCEPTED_EQUIVALENTS_EXCEEDED",
                f"{criterion_path}.accepted_equivalents",
                "Accepted-equivalent count exceeds the configured compilation limit.",
            )

        for path, value in (
            (f"{criterion_path}.criterion_id", criterion.criterion_id),
            (f"{criterion_path}.operational_description", criterion.operational_description),
            (f"{criterion_path}.evidence_requirement", criterion.evidence_requirement),
        ):
            if len(value) > limits.max_text_characters_per_field:
                return _single(
                    "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                    path,
                    "Text field exceeds the configured compilation character limit.",
                )

        for level_index, level in enumerate(criterion.performance_levels):
            level_path = f"{criterion_path}.performance_levels[{level_index}]"
            for path, value in (
                (f"{level_path}.level_id", level.level_id),
                (f"{level_path}.operational_description", level.operational_description),
            ):
                if len(value) > limits.max_text_characters_per_field:
                    return _single(
                        "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                        path,
                        "Text field exceeds the configured compilation character limit.",
                    )

        for equivalent_index, equivalent in enumerate(criterion.accepted_equivalents):
            if len(equivalent) > limits.max_text_characters_per_field:
                return _single(
                    "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                    f"{criterion_path}.accepted_equivalents[{equivalent_index}]",
                    "Text field exceeds the configured compilation character limit.",
                )

    for rule_index, rule in enumerate(all_rules):
        rule_path = f"scoring_policy.rules[{rule_index}]"
        conditions = _rule_conditions(rule)
        if len(conditions) > limits.max_conditions_per_rule:
            return _single(
                "MAX_CONDITIONS_PER_RULE_EXCEEDED",
                f"{rule_path}.conditions",
                "Rule condition count exceeds the configured compilation limit.",
            )
        if len(rule.rule_id) > limits.max_text_characters_per_field:
            return _single(
                "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                f"{rule_path}.rule_id",
                "Text field exceeds the configured compilation character limit.",
            )
        if type(rule) is AuthoringPositiveCreditDependencyRule:
            if len(rule.target_criterion_id) > limits.max_text_characters_per_field:
                return _single(
                    "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                    f"{rule_path}.target_criterion_id",
                    "Text field exceeds the configured compilation character limit.",
                )

        for condition_index, condition in enumerate(conditions):
            condition_path = f"{rule_path}.conditions[{condition_index}]"
            if (
                len(condition.allowed_level_ids)
                > limits.max_allowed_level_ids_per_condition
            ):
                return _single(
                    "MAX_ALLOWED_LEVEL_IDS_EXCEEDED",
                    f"{condition_path}.allowed_level_ids",
                    "Condition allowed-level count exceeds the configured compilation limit.",
                )
            if len(condition.criterion_id) > limits.max_text_characters_per_field:
                return _single(
                    "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                    f"{condition_path}.criterion_id",
                    "Text field exceeds the configured compilation character limit.",
                )
            for level_index, level_id in enumerate(condition.allowed_level_ids):
                if len(level_id) > limits.max_text_characters_per_field:
                    return _single(
                        "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                        f"{condition_path}.allowed_level_ids[{level_index}]",
                        "Text field exceeds the configured compilation character limit.",
                    )

    if content.rounding is not None:
        for path, value in (
            ("scoring_policy.rounding.rule_id", content.rounding.rule_id),
            ("scoring_policy.rounding.mode", content.rounding.mode),
        ):
            if len(value) > limits.max_text_characters_per_field:
                return _single(
                    "MAX_TEXT_FIELD_LENGTH_EXCEEDED",
                    path,
                    "Text field exceeds the configured compilation character limit.",
                )

    _state_count, state_limit_exceeded = _bounded_reconciliation_state_count(
        content,
        limits.max_reconciliation_states,
    )
    if state_limit_exceeded:
        return _single(
            "RECONCILIATION_STATE_LIMIT_EXCEEDED",
            "criteria.performance_levels",
            "Complete marks reconciliation would exceed the configured state-space limit.",
        )

    # All individual text/cardinality dimensions are admitted before canonical
    # serialization. This prevents serialization from being the first operation
    # over an otherwise structurally unbounded candidate.
    payload_size = len(authoring_content_canonical_bytes(content))
    if payload_size > limits.max_serialized_authority_bytes:
        return _single(
            "MAX_SERIALIZED_AUTHORITY_BYTES_EXCEEDED",
            "authoring_content",
            "Canonical authoring payload exceeds the configured serialized-authority byte limit.",
        )

    return ()


def require_resource_admission(
    content: QuestionRubricAuthoringContent,
    *,
    finalized_question: FinalizedQuestionScoringBasis,
    limits: RubricCompilationLimits,
) -> int:
    """Fail closed on resource-policy violation and return admitted state count."""

    issues = resource_limit_issues(
        content,
        finalized_question=finalized_question,
        limits=limits,
    )
    if issues:
        raise RubricResourceLimitError(
            "Rubric authoring content exceeds explicit compilation resource limits.",
            issues=issues,
        )

    count, exceeded = _bounded_reconciliation_state_count(
        content,
        limits.max_reconciliation_states,
    )
    if exceeded:  # Defensive: resource_limit_issues already rejects this state.
        raise RubricResourceLimitError(
            "Rubric reconciliation state space exceeds explicit compilation limits.",
            issues=_single(
                "RECONCILIATION_STATE_LIMIT_EXCEEDED",
                "criteria.performance_levels",
                "Complete marks reconciliation would exceed the configured state-space limit.",
            ),
        )
    return count
