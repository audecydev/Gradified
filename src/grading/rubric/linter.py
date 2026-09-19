from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import product

from grading.contracts.errors import (
    DependencyCycleError,
    InvalidRuleError,
    InvalidScoringAuthorityError,
    ScoreOutOfRangeError,
    ScoringError,
    UnknownAuthorityCriterionError,
    UnknownAuthorityPerformanceLevelError,
    UnsupportedScoringSemanticsError,
)
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.policy import RoundingMode
from grading.scoring.arithmetic import exact_compare
from grading.scoring.reducer import reduce_question
from grading.rubric.errors import InvalidRubricAuthoringInputError, RubricResourceLimitError
from grading.rubric.fingerprint import compiled_authority_canonical_bytes
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
from grading.rubric.projection import _build_reducer_authority
from grading.rubric.resources import RubricResourceIssue, require_resource_admission


class RubricLintSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class RubricLintIssue:
    severity: RubricLintSeverity
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class RubricLintResult:
    issues: tuple[RubricLintIssue, ...]

    @property
    def errors(self) -> tuple[RubricLintIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity is RubricLintSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[RubricLintIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity is RubricLintSeverity.WARNING
        )

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _error(code: str, path: str, message: str) -> RubricLintIssue:
    return RubricLintIssue(RubricLintSeverity.ERROR, code, path, message)


def _valid_identifier(value: str) -> bool:
    return bool(value) and value.strip() == value


def _validate_conditions_shape(
    conditions: tuple[AuthoringCriterionCondition, ...],
    *,
    path: str,
    issues: list[RubricLintIssue],
) -> None:
    if not conditions:
        issues.append(
            _error(
                "EMPTY_RULE_CONDITIONS",
                path,
                "Rule conditions must not be empty.",
            )
        )
        return

    criterion_ids: list[str] = []
    for index, condition in enumerate(conditions):
        condition_path = f"{path}[{index}]"
        if not _valid_identifier(condition.criterion_id):
            issues.append(
                _error(
                    "INVALID_IDENTIFIER",
                    f"{condition_path}.criterion_id",
                    "Condition criterion_id must be a non-empty trimmed identifier.",
                )
            )
        criterion_ids.append(condition.criterion_id)
        if not condition.allowed_level_ids:
            issues.append(
                _error(
                    "EMPTY_ALLOWED_LEVELS",
                    f"{condition_path}.allowed_level_ids",
                    "A condition must allow at least one level.",
                )
            )
        if len(condition.allowed_level_ids) != len(set(condition.allowed_level_ids)):
            issues.append(
                _error(
                    "DUPLICATE_ALLOWED_LEVEL_ID",
                    f"{condition_path}.allowed_level_ids",
                    "A condition cannot repeat an allowed level ID.",
                )
            )
        for level_index, level_id in enumerate(condition.allowed_level_ids):
            if not _valid_identifier(level_id):
                issues.append(
                    _error(
                        "INVALID_IDENTIFIER",
                        f"{condition_path}.allowed_level_ids[{level_index}]",
                        "Allowed level IDs must be non-empty trimmed identifiers.",
                    )
                )

    if len(criterion_ids) != len(set(criterion_ids)):
        issues.append(
            _error(
                "DUPLICATE_CONDITION_CRITERION",
                path,
                "A rule cannot contain multiple conditions for the same criterion.",
            )
        )


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


def _preflight(
    content: QuestionRubricAuthoringContent,
    finalized_question: FinalizedQuestionScoringBasis,
    version: int,
) -> list[RubricLintIssue]:
    issues: list[RubricLintIssue] = []

    if type(version) is not int or version <= 0:
        issues.append(
            _error("INVALID_VERSION", "version", "Version must be a positive integer.")
        )

    for field_name, value in (
        ("rubric_id", content.rubric_id),
        ("policy_id", content.policy_id),
        ("finalized_question.question_id", finalized_question.question_id),
    ):
        if not _valid_identifier(value):
            issues.append(
                _error(
                    "INVALID_IDENTIFIER",
                    field_name,
                    f"{field_name} must be a non-empty trimmed identifier.",
                )
            )

    if not content.criteria:
        issues.append(
            _error(
                "EMPTY_CRITERIA",
                "criteria",
                "A rubric must contain at least one criterion.",
            )
        )

    criterion_ids = tuple(criterion.criterion_id for criterion in content.criteria)
    if len(criterion_ids) != len(set(criterion_ids)):
        issues.append(
            _error(
                "DUPLICATE_CRITERION_ID",
                "criteria",
                "Criterion IDs must be unique within a rubric.",
            )
        )

    for criterion_index, criterion in enumerate(content.criteria):
        criterion_path = f"criteria[{criterion_index}]"
        if not _valid_identifier(criterion.criterion_id):
            issues.append(
                _error(
                    "INVALID_IDENTIFIER",
                    f"{criterion_path}.criterion_id",
                    "criterion_id must be a non-empty trimmed identifier.",
                )
            )
        if not criterion.operational_description.strip():
            issues.append(
                _error(
                    "EMPTY_OPERATIONAL_DESCRIPTION",
                    f"{criterion_path}.operational_description",
                    "Criterion operational_description must contain non-whitespace text.",
                )
            )
        if not criterion.evidence_requirement.strip():
            issues.append(
                _error(
                    "EMPTY_EVIDENCE_REQUIREMENT",
                    f"{criterion_path}.evidence_requirement",
                    "Criterion evidence_requirement must contain non-whitespace text.",
                )
            )
        if not criterion.performance_levels:
            issues.append(
                _error(
                    "EMPTY_PERFORMANCE_LEVELS",
                    f"{criterion_path}.performance_levels",
                    "A criterion must define at least one performance level.",
                )
            )

        level_ids = tuple(level.level_id for level in criterion.performance_levels)
        if len(level_ids) != len(set(level_ids)):
            issues.append(
                _error(
                    "DUPLICATE_LEVEL_ID",
                    f"{criterion_path}.performance_levels",
                    "Performance level IDs must be unique within a criterion.",
                )
            )
        for level_index, level in enumerate(criterion.performance_levels):
            level_path = f"{criterion_path}.performance_levels[{level_index}]"
            if not _valid_identifier(level.level_id):
                issues.append(
                    _error(
                        "INVALID_IDENTIFIER",
                        f"{level_path}.level_id",
                        "level_id must be a non-empty trimmed identifier.",
                    )
                )
            if not level.operational_description.strip():
                issues.append(
                    _error(
                        "EMPTY_LEVEL_DESCRIPTION",
                        f"{level_path}.operational_description",
                        "Performance level operational_description must contain non-whitespace text.",
                    )
                )

        if len(criterion.accepted_equivalents) != len(set(criterion.accepted_equivalents)):
            issues.append(
                _error(
                    "DUPLICATE_ACCEPTED_EQUIVALENT",
                    f"{criterion_path}.accepted_equivalents",
                    "Accepted equivalents must not contain exact duplicates.",
                )
            )
        for equivalent_index, equivalent in enumerate(criterion.accepted_equivalents):
            if not equivalent.strip():
                issues.append(
                    _error(
                        "EMPTY_ACCEPTED_EQUIVALENT",
                        f"{criterion_path}.accepted_equivalents[{equivalent_index}]",
                        "Accepted equivalents must contain non-whitespace text.",
                    )
                )

    all_rules: tuple[object, ...] = (
        *content.positive_credit_dependencies,
        *content.gates,
        *content.caps,
        *content.deductions,
    )
    rule_ids = [rule.rule_id for rule in all_rules]
    if content.rounding is not None:
        rule_ids.append(content.rounding.rule_id)
    if len(rule_ids) != len(set(rule_ids)):
        issues.append(
            _error(
                "DUPLICATE_RULE_ID",
                "scoring_policy",
                "Rule IDs must be unique across dependencies, gates, caps, deductions, and rounding.",
            )
        )

    for rule_index, rule in enumerate(all_rules):
        rule_path = f"scoring_policy.rules[{rule_index}]"
        if not _valid_identifier(rule.rule_id):
            issues.append(
                _error(
                    "INVALID_IDENTIFIER",
                    f"{rule_path}.rule_id",
                    "rule_id must be a non-empty trimmed identifier.",
                )
            )
        _validate_conditions_shape(
            _rule_conditions(rule),
            path=f"{rule_path}.conditions",
            issues=issues,
        )
        if type(rule) is AuthoringPositiveCreditDependencyRule and not _valid_identifier(
            rule.target_criterion_id
        ):
            issues.append(
                _error(
                    "INVALID_IDENTIFIER",
                    f"{rule_path}.target_criterion_id",
                    "Dependency target_criterion_id must be a non-empty trimmed identifier.",
                )
            )

    if content.rounding is not None:
        if not _valid_identifier(content.rounding.rule_id):
            issues.append(
                _error(
                    "INVALID_IDENTIFIER",
                    "scoring_policy.rounding.rule_id",
                    "rounding rule_id must be a non-empty trimmed identifier.",
                )
            )
        if content.rounding.mode not in {mode.value for mode in RoundingMode}:
            issues.append(
                _error(
                    "INVALID_ROUNDING_MODE",
                    "scoring_policy.rounding.mode",
                    "rounding mode must be one of the reducer-supported RoundingMode values.",
                )
            )

    return issues


def _projection_issue(exc: Exception) -> RubricLintIssue:
    if isinstance(exc, DependencyCycleError):
        code = "DEPENDENCY_CYCLE"
    elif isinstance(exc, UnknownAuthorityCriterionError):
        code = "UNKNOWN_CRITERION_REFERENCE"
    elif isinstance(exc, UnknownAuthorityPerformanceLevelError):
        code = "UNKNOWN_LEVEL_REFERENCE"
    elif isinstance(exc, UnsupportedScoringSemanticsError):
        code = "UNSUPPORTED_SCORING_SEMANTICS"
    elif isinstance(exc, InvalidRuleError):
        code = "INVALID_RULE"
    elif isinstance(exc, InvalidScoringAuthorityError):
        code = "INVALID_SCORING_AUTHORITY"
    else:
        raise TypeError("Unexpected projection error type.")
    return _error(code, "scoring_authority", str(exc))


def _reconciliation_issues(
    authority: object,
    *,
    state_count: int,
) -> list[RubricLintIssue]:
    from grading.contracts.authority import QuestionScoringAuthority

    if type(authority) is not QuestionScoringAuthority:
        raise TypeError("Reconciliation requires QuestionScoringAuthority.")
    if type(state_count) is not int or state_count <= 0:
        raise TypeError("Reconciliation requires a positive exact state count.")

    level_choices = tuple(
        tuple(level.level_id for level in criterion.performance_levels)
        for criterion in authority.rubric.criteria
    )
    highest = None
    visited = 0

    for selected_levels in product(*level_choices):
        visited += 1
        judgments = tuple(
            CriterionJudgment(criterion.criterion_id, selected_level)
            for criterion, selected_level in zip(
                authority.rubric.criteria,
                selected_levels,
                strict=True,
            )
        )
        try:
            result = reduce_question(authority, judgments)
        except ScoreOutOfRangeError:
            return [
                _error(
                    "REACHABLE_SCORE_OUT_OF_RANGE",
                    "scoring_authority",
                    "At least one valid rubric-level combination produces a final score outside the configured question range.",
                )
            ]
        except ScoringError as exc:
            return [
                _error(
                    "REACHABLE_SCORING_FAILURE",
                    "scoring_authority",
                    f"At least one valid rubric-level combination cannot be scored: {type(exc).__name__}.",
                )
            ]

        if highest is None or exact_compare(result.final_score, highest) > 0:
            highest = result.final_score

    if visited != state_count:
        raise RuntimeError(
            "Reconciliation enumeration count disagrees with pre-admitted state count."
        )

    if highest is None:
        return [
            _error(
                "NO_REACHABLE_SCORE",
                "scoring_authority",
                "No rubric-level combination could be evaluated for marks reconciliation.",
            )
        ]

    if exact_compare(highest, authority.rubric.max_marks) != 0:
        return [
            _error(
                "MARKS_DO_NOT_RECONCILE",
                "finalized_question.max_marks",
                "The maximum reachable final score under the complete scoring policy does not equal finalized question max_marks.",
            )
        ]

    return []


def lint_rubric_content(
    content: QuestionRubricAuthoringContent,
    *,
    finalized_question: FinalizedQuestionScoringBasis,
    version: int,
    limits: RubricCompilationLimits,
) -> RubricLintResult:
    """Lint one immutable authoring revision before compilation/activation."""

    if type(content) is not QuestionRubricAuthoringContent:
        raise InvalidRubricAuthoringInputError(
            "content must be QuestionRubricAuthoringContent."
        )
    if type(finalized_question) is not FinalizedQuestionScoringBasis:
        raise InvalidRubricAuthoringInputError(
            "finalized_question must be FinalizedQuestionScoringBasis."
        )
    if type(limits) is not RubricCompilationLimits:
        raise InvalidRubricAuthoringInputError(
            "limits must be RubricCompilationLimits; Release 1 has no implicit production defaults."
        )

    state_count = require_resource_admission(
        content,
        finalized_question=finalized_question,
        limits=limits,
    )

    issues = _preflight(content, finalized_question, version)

    if not issues:
        try:
            authority = _build_reducer_authority(
                content,
                finalized_question=finalized_question,
                version=version,
            )
        except (
            DependencyCycleError,
            UnknownAuthorityCriterionError,
            UnknownAuthorityPerformanceLevelError,
            UnsupportedScoringSemanticsError,
            InvalidRuleError,
            InvalidScoringAuthorityError,
        ) as exc:
            issues.append(_projection_issue(exc))
        else:
            compiled_size = len(compiled_authority_canonical_bytes(authority))
            if compiled_size > limits.max_serialized_authority_bytes:
                raise RubricResourceLimitError(
                    "Compiled authority exceeds explicit serialized-authority limits.",
                    issues=(
                        RubricResourceIssue(
                            "MAX_SERIALIZED_AUTHORITY_BYTES_EXCEEDED",
                            "compiled_authority",
                            "Canonical compiled authority exceeds the configured serialized-authority byte limit.",
                        ),
                    ),
                )
            issues.extend(_reconciliation_issues(authority, state_count=state_count))

    canonical = tuple(
        sorted(
            issues,
            key=lambda issue: (
                issue.severity.value,
                issue.code,
                issue.path,
                issue.message,
            ),
        )
    )
    return RubricLintResult(canonical)


def lint_rubric_collection(
    contents: tuple[QuestionRubricAuthoringContent, ...],
) -> RubricLintResult:
    """Check collection-scope rubric identity collisions without a backend schema."""

    if type(contents) is not tuple or any(
        type(content) is not QuestionRubricAuthoringContent for content in contents
    ):
        raise InvalidRubricAuthoringInputError(
            "contents must be a tuple of QuestionRubricAuthoringContent."
        )

    seen: set[str] = set()
    issues: list[RubricLintIssue] = []
    for index, content in enumerate(contents):
        if content.rubric_id in seen:
            issues.append(
                _error(
                    "DUPLICATE_RUBRIC_ID",
                    f"contents[{index}].rubric_id",
                    "Rubric IDs must be unique within one activation/compilation collection.",
                )
            )
        seen.add(content.rubric_id)

    return RubricLintResult(tuple(issues))
