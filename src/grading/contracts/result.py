from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.contracts.scoring_decimal import ScoringDecimal


class RuleType(str, Enum):
    """Conditional scoring-rule categories represented in provenance."""

    DEPENDENCY = "DEPENDENCY"
    GATE = "GATE"
    CAP = "CAP"
    DEDUCTION = "DEDUCTION"


class ScoreStage(str, Enum):
    """Question-level numerical transformation stages recorded in provenance."""

    GATES = "GATES"
    CAPS = "CAPS"
    DEDUCTIONS = "DEDUCTIONS"
    ROUNDING = "ROUNDING"


def _require_exact_type(
    value: object,
    expected_type: type,
    field_name: str,
) -> None:
    """Require exactly the declared closed runtime type."""

    if type(value) is not expected_type:
        raise TypeError(f"{field_name} must be a {expected_type.__name__}.")


def _require_tuple_of(
    values: object,
    item_type: type,
    field_name: str,
) -> None:
    """Require an exact immutable tuple containing only the declared item type."""

    if type(values) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")

    if any(type(value) is not item_type for value in values):
        raise TypeError(f"{field_name} contains an invalid item.")


@dataclass(frozen=True, slots=True)
class RubricRef:
    """Immutable identity of the rubric used for reduction."""

    id: str
    version: int

    def __post_init__(self) -> None:
        _require_exact_type(self.id, str, "RubricRef.id")
        _require_exact_type(self.version, int, "RubricRef.version")


@dataclass(frozen=True, slots=True)
class ScoringPolicyRef:
    """Immutable identity of the scoring policy used for reduction."""

    id: str
    version: int
    scoring_semantics_version: str

    def __post_init__(self) -> None:
        _require_exact_type(self.id, str, "ScoringPolicyRef.id")
        _require_exact_type(self.version, int, "ScoringPolicyRef.version")
        _require_exact_type(
            self.scoring_semantics_version,
            str,
            "ScoringPolicyRef.scoring_semantics_version",
        )


@dataclass(frozen=True, slots=True)
class CriterionEffect:
    """Numerical effect of one original semantic criterion judgment."""

    criterion_id: str
    selected_level: str
    base_contribution: ScoringDecimal
    effective_contribution: ScoringDecimal
    blocking_dependency_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_exact_type(
            self.criterion_id,
            str,
            "CriterionEffect.criterion_id",
        )
        _require_exact_type(
            self.selected_level,
            str,
            "CriterionEffect.selected_level",
        )
        _require_exact_type(
            self.base_contribution,
            ScoringDecimal,
            "CriterionEffect.base_contribution",
        )
        _require_exact_type(
            self.effective_contribution,
            ScoringDecimal,
            "CriterionEffect.effective_contribution",
        )
        _require_tuple_of(
            self.blocking_dependency_rule_ids,
            str,
            "CriterionEffect.blocking_dependency_rule_ids",
        )


@dataclass(frozen=True, slots=True)
class RuleDecision:
    """Deterministic decision for one configured conditional scoring rule."""

    rule_id: str
    rule_type: RuleType
    triggered: bool
    configured_effect: ScoringDecimal | None

    def __post_init__(self) -> None:
        _require_exact_type(self.rule_id, str, "RuleDecision.rule_id")
        _require_exact_type(self.rule_type, RuleType, "RuleDecision.rule_type")
        _require_exact_type(self.triggered, bool, "RuleDecision.triggered")

        if self.configured_effect is not None:
            _require_exact_type(
                self.configured_effect,
                ScoringDecimal,
                "RuleDecision.configured_effect",
            )


@dataclass(frozen=True, slots=True)
class ScoreStageEffect:
    """Before/after provenance for one numerical transformation stage."""

    stage: ScoreStage
    before: ScoringDecimal
    after: ScoringDecimal
    source_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_exact_type(self.stage, ScoreStage, "ScoreStageEffect.stage")
        _require_exact_type(
            self.before,
            ScoringDecimal,
            "ScoreStageEffect.before",
        )
        _require_exact_type(
            self.after,
            ScoringDecimal,
            "ScoreStageEffect.after",
        )
        _require_tuple_of(
            self.source_rule_ids,
            str,
            "ScoreStageEffect.source_rule_ids",
        )


@dataclass(frozen=True, slots=True)
class QuestionScoreResult:
    """Immutable authoritative result of one successful question reduction."""

    question_id: str
    rubric_ref: RubricRef
    scoring_policy_ref: ScoringPolicyRef
    numeric_profile_version: str
    criterion_effects: tuple[CriterionEffect, ...]
    rule_decisions: tuple[RuleDecision, ...]
    stage_effects: tuple[ScoreStageEffect, ...]
    base_subtotal: ScoringDecimal
    score_before_rounding: ScoringDecimal
    final_score: ScoringDecimal
    minimum_score: ScoringDecimal
    maximum_score: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_type(
            self.question_id,
            str,
            "QuestionScoreResult.question_id",
        )
        _require_exact_type(
            self.rubric_ref,
            RubricRef,
            "QuestionScoreResult.rubric_ref",
        )
        _require_exact_type(
            self.scoring_policy_ref,
            ScoringPolicyRef,
            "QuestionScoreResult.scoring_policy_ref",
        )
        _require_exact_type(
            self.numeric_profile_version,
            str,
            "QuestionScoreResult.numeric_profile_version",
        )
        _require_tuple_of(
            self.criterion_effects,
            CriterionEffect,
            "QuestionScoreResult.criterion_effects",
        )
        _require_tuple_of(
            self.rule_decisions,
            RuleDecision,
            "QuestionScoreResult.rule_decisions",
        )
        _require_tuple_of(
            self.stage_effects,
            ScoreStageEffect,
            "QuestionScoreResult.stage_effects",
        )
        _require_exact_type(
            self.base_subtotal,
            ScoringDecimal,
            "QuestionScoreResult.base_subtotal",
        )
        _require_exact_type(
            self.score_before_rounding,
            ScoringDecimal,
            "QuestionScoreResult.score_before_rounding",
        )
        _require_exact_type(
            self.final_score,
            ScoringDecimal,
            "QuestionScoreResult.final_score",
        )
        _require_exact_type(
            self.minimum_score,
            ScoringDecimal,
            "QuestionScoreResult.minimum_score",
        )
        _require_exact_type(
            self.maximum_score,
            ScoringDecimal,
            "QuestionScoreResult.maximum_score",
        )


# Resolve the scoring aggregation provenance type only after the criterion scoring result contracts needed by
# paper_aggregation have been defined.  paper_aggregation defines GradingSpecRef
# before importing RubricRef/ScoringPolicyRef, making both clean import orders safe.
from grading.contracts.paper_aggregation import GradingSpecRef


@dataclass(frozen=True, slots=True)
class PaperScoreResult:
    """Immutable numerical result of successful scoring aggregation paper aggregation."""

    grading_spec_ref: GradingSpecRef
    numeric_profile_version: str
    question_results: tuple[QuestionScoreResult, ...]
    final_score: ScoringDecimal
    minimum_score: ScoringDecimal
    maximum_score: ScoringDecimal

    def __post_init__(self) -> None:
        _require_exact_type(
            self.grading_spec_ref,
            GradingSpecRef,
            "PaperScoreResult.grading_spec_ref",
        )
        _require_exact_type(
            self.numeric_profile_version,
            str,
            "PaperScoreResult.numeric_profile_version",
        )
        if self.numeric_profile_version != NUMERIC_PROFILE_VERSION:
            raise TypeError(
                "PaperScoreResult.numeric_profile_version must be the supported profile."
            )
        _require_tuple_of(
            self.question_results,
            QuestionScoreResult,
            "PaperScoreResult.question_results",
        )
        _require_exact_type(
            self.final_score,
            ScoringDecimal,
            "PaperScoreResult.final_score",
        )
        _require_exact_type(
            self.minimum_score,
            ScoringDecimal,
            "PaperScoreResult.minimum_score",
        )
        _require_exact_type(
            self.maximum_score,
            ScoringDecimal,
            "PaperScoreResult.maximum_score",
        )
