from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from grading.contracts.errors import (
    DependencyCycleError,
    InvalidRuleError,
    InvalidScoringAuthorityError,
    UnknownAuthorityCriterionError,
    UnknownAuthorityPerformanceLevelError,
)
from grading.contracts.policy import (
    CapRule,
    CriterionCondition,
    DeductionRule,
    GateRule,
    QuestionScoringPolicy,
)
from grading.contracts.rubric import AtomicCriterion, CompiledQuestionRubric


@dataclass(frozen=True, slots=True)
class QuestionScoringAuthority:
    """Immutable reducer input with defensive structural/reference validation.

    This boundary validates shape, question/max alignment, rule references and
    dependency acyclicity. It deliberately does not replace the Slice 2 rubric
    linter/compiler, which owns global marks reconciliation and activation-time
    semantic validation. The reducer still enforces final score bounds at run
    time as defense in depth.
    """

    rubric: CompiledQuestionRubric
    policy: QuestionScoringPolicy

    def __post_init__(self) -> None:
        if type(self.rubric) is not CompiledQuestionRubric:
            raise InvalidScoringAuthorityError(
                "QuestionScoringAuthority.rubric must be a CompiledQuestionRubric."
            )
        if type(self.policy) is not QuestionScoringPolicy:
            raise InvalidScoringAuthorityError(
                "QuestionScoringAuthority.policy must be a QuestionScoringPolicy."
            )
        if self.rubric.question_id != self.policy.question_id:
            raise InvalidScoringAuthorityError(
                "Rubric and scoring policy must reference the same question_id."
            )
        if self.rubric.max_marks != self.policy.maximum_score:
            raise InvalidScoringAuthorityError(
                "Rubric max_marks must equal policy maximum_score."
            )

        criteria_by_id = self.rubric.criteria_by_id()
        for dependency in self.policy.positive_credit_dependencies:
            if dependency.target_criterion_id not in criteria_by_id:
                raise UnknownAuthorityCriterionError(
                    f"Dependency {dependency.rule_id!r} targets unknown criterion "
                    f"{dependency.target_criterion_id!r}."
                )
            self._validate_conditions(
                dependency.prerequisite_conditions,
                criteria_by_id,
                dependency.rule_id,
            )

        for rule in (*self.policy.gates, *self.policy.caps, *self.policy.deductions):
            self._validate_conditions(
                _conditions_for_rule(rule),
                criteria_by_id,
                rule.rule_id,
            )

        self._reject_dependency_cycles()

    @staticmethod
    def _validate_conditions(
        conditions: tuple[CriterionCondition, ...],
        criteria_by_id: dict[str, AtomicCriterion],
        rule_id: str,
    ) -> None:
        for condition in conditions:
            criterion = criteria_by_id.get(condition.criterion_id)
            if criterion is None:
                raise UnknownAuthorityCriterionError(
                    f"Rule {rule_id!r} references unknown criterion "
                    f"{condition.criterion_id!r}."
                )

            known_level_ids = criterion.level_ids()
            for level_id in condition.allowed_level_ids:
                if level_id not in known_level_ids:
                    raise UnknownAuthorityPerformanceLevelError(
                        f"Rule {rule_id!r} references unknown level {level_id!r} "
                        f"for criterion {condition.criterion_id!r}."
                    )

    def _reject_dependency_cycles(self) -> None:
        # Use an iterative topological check rather than recursive DFS. The
        # scoring contract does not define a criterion-count limit, so Python's
        # recursion limit must not become an accidental hidden authority limit.
        indegree: dict[str, int] = {
            criterion.criterion_id: 0
            for criterion in self.rubric.criteria
        }
        dependents: dict[str, set[str]] = {
            criterion.criterion_id: set()
            for criterion in self.rubric.criteria
        }

        for dependency in self.policy.positive_credit_dependencies:
            target = dependency.target_criterion_id
            prerequisites = {
                condition.criterion_id
                for condition in dependency.prerequisite_conditions
            }
            for prerequisite in prerequisites:
                if target not in dependents[prerequisite]:
                    dependents[prerequisite].add(target)
                    indegree[target] += 1

        ready = deque(
            criterion_id
            for criterion_id, degree in indegree.items()
            if degree == 0
        )
        visited_count = 0

        while ready:
            criterion_id = ready.popleft()
            visited_count += 1

            for dependent in dependents[criterion_id]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)

        if visited_count != len(indegree):
            raise DependencyCycleError(
                "Positive-credit dependency graph must be acyclic."
            )


def _conditions_for_rule(
    rule: GateRule | CapRule | DeductionRule,
) -> tuple[CriterionCondition, ...]:
    if type(rule) is GateRule:
        return rule.required_conditions
    if type(rule) is CapRule:
        return rule.trigger_conditions
    if type(rule) is DeductionRule:
        return rule.trigger_conditions
    raise InvalidRuleError("Unsupported rule type in scoring authority.")
