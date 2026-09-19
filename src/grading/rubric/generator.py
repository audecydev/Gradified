from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.fingerprint import authoring_content_fingerprint
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterion,
    AuthoringDeductionRule,
    AuthoringGateRule,
    AuthoringPositiveCreditDependencyRule,
    AuthoringRoundingRule,
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
)


__all__ = [
    "RubricGenerationInput",
    "RubricGenerationProposal",
    "GeneratedRubricCandidate",
    "generate_rubric_candidate",
]

_GENERATOR_PROFILE_VERSION = "1"


class _InvalidRubricGenerationInputError(ValueError):
    """Raised when deterministic generator-composition input has an invalid runtime shape."""


def _require_exact_type(value: object, expected_type: type, field_name: str) -> None:
    if type(value) is not expected_type:
        raise _InvalidRubricGenerationInputError(
            f"{field_name} must be an exact {expected_type.__name__}."
        )


def _require_exact_str(value: object, field_name: str) -> None:
    _require_exact_type(value, str, field_name)


def _require_tuple_of_exact_type(
    value: object,
    expected_type: type,
    field_name: str,
) -> None:
    if type(value) is not tuple:
        raise _InvalidRubricGenerationInputError(f"{field_name} must be a tuple.")
    if any(type(item) is not expected_type for item in value):
        raise _InvalidRubricGenerationInputError(
            f"{field_name} contains an invalid item."
        )


def _encode_payload(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_encode_payload(payload)).hexdigest()


def _rounding_payload(rounding: AuthoringRoundingRule | None) -> dict[str, str] | None:
    if rounding is None:
        return None
    return {
        "rule_id": rounding.rule_id,
        "increment": rounding.increment.to_canonical_string(),
        "mode": rounding.mode,
    }


def _condition_payload(condition: object) -> dict[str, Any]:
    return {
        "criterion_id": condition.criterion_id,
        "allowed_level_ids": list(condition.allowed_level_ids),
    }


def _criterion_payload(criterion: AuthoringCriterion) -> dict[str, Any]:
    return {
        "criterion_id": criterion.criterion_id,
        "operational_description": criterion.operational_description,
        "evidence_requirement": criterion.evidence_requirement,
        "performance_levels": [
            {
                "level_id": level.level_id,
                "operational_description": level.operational_description,
                "contribution": level.contribution.to_canonical_string(),
            }
            for level in criterion.performance_levels
        ],
        "accepted_equivalents": list(criterion.accepted_equivalents),
    }


def _dependency_payload(rule: AuthoringPositiveCreditDependencyRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "target_criterion_id": rule.target_criterion_id,
        "prerequisite_conditions": [
            _condition_payload(condition) for condition in rule.prerequisite_conditions
        ],
    }


def _gate_payload(rule: AuthoringGateRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "required_conditions": [
            _condition_payload(condition) for condition in rule.required_conditions
        ],
        "failure_ceiling": rule.failure_ceiling.to_canonical_string(),
    }


def _cap_payload(rule: AuthoringCapRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "trigger_conditions": [
            _condition_payload(condition) for condition in rule.trigger_conditions
        ],
        "ceiling": rule.ceiling.to_canonical_string(),
    }


def _deduction_payload(rule: AuthoringDeductionRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "trigger_conditions": [
            _condition_payload(condition) for condition in rule.trigger_conditions
        ],
        "amount": rule.amount.to_canonical_string(),
    }


@dataclass(frozen=True, slots=True)
class RubricGenerationInput:
    """Trusted normalized inputs used to compose one rubric-generation candidate.

    The object binds the exact school-authorized question/model-answer text and
    trusted scoring/policy inputs used by this deterministic G1 composition
    boundary. It does not authenticate where those inputs came from.
    """

    finalized_question: FinalizedQuestionScoringBasis
    question_text: str
    model_answer_text: str
    rubric_id: str
    policy_id: str
    minimum_score: ScoringDecimal
    rounding: AuthoringRoundingRule | None

    def __post_init__(self) -> None:
        _require_exact_type(
            self.finalized_question,
            FinalizedQuestionScoringBasis,
            "finalized_question",
        )
        _require_exact_str(self.question_text, "question_text")
        _require_exact_str(self.model_answer_text, "model_answer_text")
        _require_exact_str(self.rubric_id, "rubric_id")
        _require_exact_str(self.policy_id, "policy_id")
        _require_exact_type(self.minimum_score, ScoringDecimal, "minimum_score")
        if self.rounding is not None:
            _require_exact_type(self.rounding, AuthoringRoundingRule, "rounding")


@dataclass(frozen=True, slots=True)
class RubricGenerationProposal:
    """Untrusted structured academic/scoring proposal produced upstream.

    It intentionally contains no finalized question authority, trusted policy
    identity, approval, lifecycle state, or reducer authority.
    """

    criteria: tuple[AuthoringCriterion, ...]
    positive_credit_dependencies: tuple[AuthoringPositiveCreditDependencyRule, ...]
    gates: tuple[AuthoringGateRule, ...]
    caps: tuple[AuthoringCapRule, ...]
    deductions: tuple[AuthoringDeductionRule, ...]

    def __post_init__(self) -> None:
        _require_tuple_of_exact_type(self.criteria, AuthoringCriterion, "criteria")
        _require_tuple_of_exact_type(
            self.positive_credit_dependencies,
            AuthoringPositiveCreditDependencyRule,
            "positive_credit_dependencies",
        )
        _require_tuple_of_exact_type(self.gates, AuthoringGateRule, "gates")
        _require_tuple_of_exact_type(self.caps, AuthoringCapRule, "caps")
        _require_tuple_of_exact_type(
            self.deductions,
            AuthoringDeductionRule,
            "deductions",
        )


def _source_fingerprint(source: RubricGenerationInput) -> str:
    return _hash_payload(
        {
            "schema": "gradified-rubric-generation-source-v1",
            "finalized_question": {
                "question_id": source.finalized_question.question_id,
                "max_marks": source.finalized_question.max_marks.to_canonical_string(),
            },
            "question_text": source.question_text,
            "model_answer_text": source.model_answer_text,
            "rubric_id": source.rubric_id,
            "policy_id": source.policy_id,
            "minimum_score": source.minimum_score.to_canonical_string(),
            "rounding": _rounding_payload(source.rounding),
        }
    )


def _proposal_fingerprint(proposal: RubricGenerationProposal) -> str:
    return _hash_payload(
        {
            "schema": "gradified-rubric-generation-proposal-v1",
            "criteria": [_criterion_payload(criterion) for criterion in proposal.criteria],
            "positive_credit_dependencies": [
                _dependency_payload(rule)
                for rule in proposal.positive_credit_dependencies
            ],
            "gates": [_gate_payload(rule) for rule in proposal.gates],
            "caps": [_cap_payload(rule) for rule in proposal.caps],
            "deductions": [_deduction_payload(rule) for rule in proposal.deductions],
        }
    )


def _compose_content(
    source: RubricGenerationInput,
    proposal: RubricGenerationProposal,
) -> QuestionRubricAuthoringContent:
    return QuestionRubricAuthoringContent(
        rubric_id=source.rubric_id,
        policy_id=source.policy_id,
        minimum_score=source.minimum_score,
        criteria=proposal.criteria,
        positive_credit_dependencies=proposal.positive_credit_dependencies,
        gates=proposal.gates,
        caps=proposal.caps,
        deductions=proposal.deductions,
        rounding=source.rounding,
    )


@dataclass(frozen=True, slots=True)
class GeneratedRubricCandidate:
    """Deterministically composed, still-unapproved rubric-generation candidate."""

    source: RubricGenerationInput
    proposal: RubricGenerationProposal
    content: QuestionRubricAuthoringContent
    source_fingerprint: str
    proposal_fingerprint: str
    content_fingerprint: str
    generator_profile_version: str

    def __post_init__(self) -> None:
        _require_exact_type(self.source, RubricGenerationInput, "source")
        _require_exact_type(self.proposal, RubricGenerationProposal, "proposal")
        _require_exact_type(
            self.content,
            QuestionRubricAuthoringContent,
            "content",
        )
        _require_exact_str(self.source_fingerprint, "source_fingerprint")
        _require_exact_str(self.proposal_fingerprint, "proposal_fingerprint")
        _require_exact_str(self.content_fingerprint, "content_fingerprint")
        _require_exact_str(self.generator_profile_version, "generator_profile_version")

        if self.generator_profile_version != _GENERATOR_PROFILE_VERSION:
            raise _InvalidRubricGenerationInputError(
                "Unsupported generator_profile_version."
            )
        if self.content != _compose_content(self.source, self.proposal):
            raise _InvalidRubricGenerationInputError(
                "content does not match the deterministic source/proposal projection."
            )
        if self.source_fingerprint != _source_fingerprint(self.source):
            raise _InvalidRubricGenerationInputError(
                "source_fingerprint does not match source."
            )
        if self.proposal_fingerprint != _proposal_fingerprint(self.proposal):
            raise _InvalidRubricGenerationInputError(
                "proposal_fingerprint does not match proposal."
            )
        if self.content_fingerprint != authoring_content_fingerprint(self.content):
            raise _InvalidRubricGenerationInputError(
                "content_fingerprint does not match content."
            )


def generate_rubric_candidate(
    *,
    source: RubricGenerationInput,
    proposal: RubricGenerationProposal,
) -> GeneratedRubricCandidate:
    """Compose trusted generation inputs and one untrusted proposal.

    This function intentionally performs no linting, compilation, approval, or
    activation. The frozen Rubric Authoring boundary remains responsible for
    those later authority transitions.
    """

    _require_exact_type(source, RubricGenerationInput, "source")
    _require_exact_type(proposal, RubricGenerationProposal, "proposal")

    content = _compose_content(source, proposal)

    return GeneratedRubricCandidate(
        source=source,
        proposal=proposal,
        content=content,
        source_fingerprint=_source_fingerprint(source),
        proposal_fingerprint=_proposal_fingerprint(proposal),
        content_fingerprint=authoring_content_fingerprint(content),
        generator_profile_version=_GENERATOR_PROFILE_VERSION,
    )
