from __future__ import annotations

import hashlib
import json
from typing import Any

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.policy import (
    CapRule,
    CriterionCondition,
    DeductionRule,
    GateRule,
    PositiveCreditDependencyRule,
    QuestionScoringPolicy,
)
from grading.contracts.rubric import CompiledQuestionRubric
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


def _authoring_condition_payload(condition: AuthoringCriterionCondition) -> dict[str, Any]:
    return {
        "criterion_id": condition.criterion_id,
        "allowed_level_ids": sorted(condition.allowed_level_ids),
    }


def _authoring_conditions_payload(
    conditions: tuple[AuthoringCriterionCondition, ...],
) -> list[dict[str, Any]]:
    return sorted(
        (_authoring_condition_payload(condition) for condition in conditions),
        key=lambda item: (item["criterion_id"], tuple(item["allowed_level_ids"])),
    )


def _dependency_payload(rule: AuthoringPositiveCreditDependencyRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "target_criterion_id": rule.target_criterion_id,
        "prerequisite_conditions": _authoring_conditions_payload(
            rule.prerequisite_conditions
        ),
    }


def _gate_payload(rule: AuthoringGateRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "required_conditions": _authoring_conditions_payload(rule.required_conditions),
        "failure_ceiling": rule.failure_ceiling.to_canonical_string(),
    }


def _cap_payload(rule: AuthoringCapRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "trigger_conditions": _authoring_conditions_payload(rule.trigger_conditions),
        "ceiling": rule.ceiling.to_canonical_string(),
    }


def _deduction_payload(rule: AuthoringDeductionRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "trigger_conditions": _authoring_conditions_payload(rule.trigger_conditions),
        "amount": rule.amount.to_canonical_string(),
    }


def _authoring_content_payload(content: QuestionRubricAuthoringContent) -> dict[str, Any]:
    return {
        "schema": "gradified-question-rubric-authoring-v2",
        "rubric_id": content.rubric_id,
        "policy_id": content.policy_id,
        "minimum_score": content.minimum_score.to_canonical_string(),
        "criteria": [
            {
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
            for criterion in content.criteria
        ],
        "positive_credit_dependencies": sorted(
            (_dependency_payload(rule) for rule in content.positive_credit_dependencies),
            key=lambda item: item["rule_id"],
        ),
        "gates": sorted(
            (_gate_payload(rule) for rule in content.gates),
            key=lambda item: item["rule_id"],
        ),
        "caps": sorted(
            (_cap_payload(rule) for rule in content.caps),
            key=lambda item: item["rule_id"],
        ),
        "deductions": sorted(
            (_deduction_payload(rule) for rule in content.deductions),
            key=lambda item: item["rule_id"],
        ),
        "rounding": None
        if content.rounding is None
        else {
            "rule_id": content.rounding.rule_id,
            "increment": content.rounding.increment.to_canonical_string(),
            "mode": content.rounding.mode,
        },
    }


def authoring_content_canonical_bytes(content: QuestionRubricAuthoringContent) -> bytes:
    return _encode_payload(_authoring_content_payload(content))


def authoring_content_fingerprint(content: QuestionRubricAuthoringContent) -> str:
    """Hash exact canonical candidate content for immutable approval binding."""

    return hashlib.sha256(authoring_content_canonical_bytes(content)).hexdigest()


def finalized_question_fingerprint(basis: FinalizedQuestionScoringBasis) -> str:
    return _hash_payload(
        {
            "schema": "gradified-finalized-question-scoring-basis-v1",
            "question_id": basis.question_id,
            "max_marks": basis.max_marks.to_canonical_string(),
        }
    )


def compilation_limits_fingerprint(limits: RubricCompilationLimits) -> str:
    return _hash_payload(
        {
            "schema": "gradified-rubric-compilation-limits-v1",
            "max_criteria": limits.max_criteria,
            "max_levels_per_criterion": limits.max_levels_per_criterion,
            "max_accepted_equivalents_per_criterion": limits.max_accepted_equivalents_per_criterion,
            "max_rules": limits.max_rules,
            "max_conditions_per_rule": limits.max_conditions_per_rule,
            "max_allowed_level_ids_per_condition": limits.max_allowed_level_ids_per_condition,
            "max_text_characters_per_field": limits.max_text_characters_per_field,
            "max_serialized_authority_bytes": limits.max_serialized_authority_bytes,
            "max_reconciliation_states": limits.max_reconciliation_states,
        }
    )


def _compiled_condition_payload(condition: CriterionCondition) -> dict[str, Any]:
    return {
        "criterion_id": condition.criterion_id,
        "allowed_level_ids": sorted(condition.allowed_level_ids),
    }


def _compiled_conditions_payload(
    conditions: tuple[CriterionCondition, ...],
) -> list[dict[str, Any]]:
    return sorted(
        (_compiled_condition_payload(condition) for condition in conditions),
        key=lambda item: (item["criterion_id"], tuple(item["allowed_level_ids"])),
    )


def _compiled_rule_payload(rule: object) -> dict[str, Any]:
    if type(rule) is PositiveCreditDependencyRule:
        return {
            "kind": "dependency",
            "rule_id": rule.rule_id,
            "target_criterion_id": rule.target_criterion_id,
            "conditions": _compiled_conditions_payload(rule.prerequisite_conditions),
        }
    if type(rule) is GateRule:
        return {
            "kind": "gate",
            "rule_id": rule.rule_id,
            "conditions": _compiled_conditions_payload(rule.required_conditions),
            "effect": rule.failure_ceiling.to_canonical_string(),
        }
    if type(rule) is CapRule:
        return {
            "kind": "cap",
            "rule_id": rule.rule_id,
            "conditions": _compiled_conditions_payload(rule.trigger_conditions),
            "effect": rule.ceiling.to_canonical_string(),
        }
    if type(rule) is DeductionRule:
        return {
            "kind": "deduction",
            "rule_id": rule.rule_id,
            "conditions": _compiled_conditions_payload(rule.trigger_conditions),
            "effect": rule.amount.to_canonical_string(),
        }
    raise TypeError("Unsupported compiled scoring rule type.")


def _compiled_authority_payload(authority: QuestionScoringAuthority) -> dict[str, Any]:
    rubric: CompiledQuestionRubric = authority.rubric
    policy: QuestionScoringPolicy = authority.policy
    return {
        "schema": "gradified-reducer-authority-v1",
        "rubric": {
            "rubric_id": rubric.rubric_id,
            "version": rubric.version,
            "question_id": rubric.question_id,
            "max_marks": rubric.max_marks.to_canonical_string(),
            "criteria": [
                {
                    "criterion_id": criterion.criterion_id,
                    "operational_description": criterion.operational_description,
                    "performance_levels": [
                        {
                            "level_id": level.level_id,
                            "contribution": level.contribution.to_canonical_string(),
                        }
                        for level in criterion.performance_levels
                    ],
                }
                for criterion in rubric.criteria
            ],
        },
        "policy": {
            "policy_id": policy.policy_id,
            "version": policy.version,
            "question_id": policy.question_id,
            "scoring_semantics_version": policy.scoring_semantics_version,
            "minimum_score": policy.minimum_score.to_canonical_string(),
            "maximum_score": policy.maximum_score.to_canonical_string(),
            "positive_credit_dependencies": [
                _compiled_rule_payload(rule)
                for rule in policy.positive_credit_dependencies
            ],
            "gates": [_compiled_rule_payload(rule) for rule in policy.gates],
            "caps": [_compiled_rule_payload(rule) for rule in policy.caps],
            "deductions": [
                _compiled_rule_payload(rule) for rule in policy.deductions
            ],
            "rounding": None
            if policy.rounding is None
            else {
                "rule_id": policy.rounding.rule_id,
                "increment": policy.rounding.increment.to_canonical_string(),
                "mode": policy.rounding.mode.value,
            },
        },
    }


def compiled_authority_canonical_bytes(authority: QuestionScoringAuthority) -> bytes:
    return _encode_payload(_compiled_authority_payload(authority))


def compiled_authority_fingerprint(authority: QuestionScoringAuthority) -> str:
    return hashlib.sha256(compiled_authority_canonical_bytes(authority)).hexdigest()
