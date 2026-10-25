from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.capability_registry import (
    EvaluatorCapabilitySource,
    ResolvedEvaluatorCapability,
    resolve_evaluator_capability,
)
from grading.contracts.capability import EvaluatorCapabilityRef
from grading.contracts.evaluation import EvaluatorMetadata
from grading.contracts.evaluator_selection import (
    EvaluatorSelectionPolicy,
    EvaluatorSelectionPolicyContractError,
    EvaluatorSelectionPolicyRef,
    EvaluatorSelectionRule,
    QuestionEvaluationClassification,
    QuestionEvaluationClassificationContractError,
    validate_evaluator_selection_policy,
    validate_question_evaluation_classification,
)
from grading.contracts.paper_aggregation import GradingSpecRef, _validate_grading_spec_ref


class EvaluatorSelectionError(Exception):
    """Base class for expected evaluator selection exact-selection failures."""


class QuestionClassificationSourceExecutionError(EvaluatorSelectionError):
    """Configured classification source failed during exact lookup."""


class QuestionClassificationSourceResultError(EvaluatorSelectionError):
    """Configured classification source returned an inadmissible value."""


class QuestionClassificationBindingError(EvaluatorSelectionError):
    """Classification/question-authority identities do not bind exactly."""


class SelectionPolicySourceExecutionError(EvaluatorSelectionError):
    """Configured selection-policy source failed during materialization."""


class SelectionPolicySourceResultError(EvaluatorSelectionError):
    """Configured selection-policy source returned an inadmissible value."""


class EvaluatorSelectionMissingRuleError(EvaluatorSelectionError):
    """No exact policy rule exists for the bound classification/context tuple."""


class EvaluatorCapabilitySupportMismatchError(EvaluatorSelectionError):
    """Resolved evaluator capability resolution record lacks an exact required support claim."""


class QuestionEvaluationClassificationSource(Protocol):
    """Already-admitted source seam for one exact question classification.

    Protocol conformance does not authenticate the source or establish policy
    authority. The composition root owns source admission.
    """

    def resolve_question_evaluation_classification(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> QuestionEvaluationClassification:
        ...


class EvaluatorSelectionPolicySource(Protocol):
    """Already-admitted source seam for the active versioned selection policy.

    Protocol conformance does not authenticate policy provenance or authorize a
    policy merely because the returned value validates structurally.
    """

    def resolve_evaluator_selection_policy(self) -> EvaluatorSelectionPolicy:
        ...


@dataclass(frozen=True, slots=True)
class ResolvedQuestionEvaluatorSelection:
    """Immutable routing-identity snapshot produced by evaluator selection selection.

    Object/class identity is not proof that this resolver ran, that the supplied
    sources were authenticated, or that evaluator execution is authorized.
    """

    classification: QuestionEvaluationClassification
    context_policy: ContextPolicy
    policy_ref: EvaluatorSelectionPolicyRef
    selected_capability_ref: EvaluatorCapabilityRef
    resolved_capability: ResolvedEvaluatorCapability


def _required_field(
    value: object,
    field_name: str,
    *,
    owner_name: str,
) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise QuestionClassificationBindingError(
            f"{owner_name}.{field_name} is missing."
        ) from exc


def _snapshot_grading_spec_ref(value: GradingSpecRef) -> GradingSpecRef:
    return GradingSpecRef(
        id=object.__getattribute__(value, "id"),
        version=object.__getattribute__(value, "version"),
    )


def _snapshot_capability_ref(value: EvaluatorCapabilityRef) -> EvaluatorCapabilityRef:
    metadata = object.__getattribute__(value, "evaluator_metadata")
    return EvaluatorCapabilityRef(
        evaluator_metadata=EvaluatorMetadata(
            evaluator_id=object.__getattribute__(metadata, "evaluator_id"),
            version=object.__getattribute__(metadata, "version"),
        ),
        record_version=object.__getattribute__(value, "record_version"),
    )


def _snapshot_classification(
    value: QuestionEvaluationClassification,
) -> QuestionEvaluationClassification:
    return QuestionEvaluationClassification(
        schema_version=object.__getattribute__(value, "schema_version"),
        grading_spec_ref=_snapshot_grading_spec_ref(
            object.__getattribute__(value, "grading_spec_ref")
        ),
        question_id=object.__getattribute__(value, "question_id"),
        answer_type=object.__getattribute__(value, "answer_type"),
        language=object.__getattribute__(value, "language"),
    )


def _snapshot_policy_ref(value: EvaluatorSelectionPolicyRef) -> EvaluatorSelectionPolicyRef:
    return EvaluatorSelectionPolicyRef(
        policy_id=object.__getattribute__(value, "policy_id"),
        version=object.__getattribute__(value, "version"),
    )


def _snapshot_rule(value: EvaluatorSelectionRule) -> EvaluatorSelectionRule:
    return EvaluatorSelectionRule(
        answer_type=object.__getattribute__(value, "answer_type"),
        language=object.__getattribute__(value, "language"),
        context_policy=object.__getattribute__(value, "context_policy"),
        capability_ref=_snapshot_capability_ref(
            object.__getattribute__(value, "capability_ref")
        ),
    )


def _snapshot_policy(value: EvaluatorSelectionPolicy) -> EvaluatorSelectionPolicy:
    return EvaluatorSelectionPolicy(
        schema_version=object.__getattribute__(value, "schema_version"),
        policy_ref=_snapshot_policy_ref(object.__getattribute__(value, "policy_ref")),
        rules=tuple(
            _snapshot_rule(rule)
            for rule in object.__getattribute__(value, "rules")
        ),
    )


def _validate_question_authority(
    value: object,
) -> tuple[GradingSpecRef, str, ContextPolicy]:
    if type(value) is not ResolvedQuestionAuthority:
        raise QuestionClassificationBindingError(
            "question_authority must be an exact ResolvedQuestionAuthority."
        )

    grading_spec_ref = _required_field(
        value,
        "grading_spec_ref",
        owner_name="question_authority",
    )
    question_id = _required_field(
        value,
        "question_id",
        owner_name="question_authority",
    )
    context_policy = _required_field(
        value,
        "context_policy",
        owner_name="question_authority",
    )

    _validate_grading_spec_ref(
        grading_spec_ref,
        field_name="question_authority.grading_spec_ref",
        error_type=QuestionClassificationBindingError,
    )
    if (
        type(question_id) is not str
        or not question_id
        or question_id.strip() != question_id
    ):
        raise QuestionClassificationBindingError(
            "question_authority.question_id must be a non-empty exact string without surrounding whitespace."
        )
    if type(context_policy) is not ContextPolicy or not any(
        context_policy is member for member in ContextPolicy
    ):
        raise QuestionClassificationBindingError(
            "question_authority.context_policy must be a canonical ContextPolicy member."
        )

    return (
        _snapshot_grading_spec_ref(grading_spec_ref),
        question_id,
        context_policy,
    )


def resolve_question_evaluator_selection(
    *,
    question_authority: ResolvedQuestionAuthority,
    classification_source: QuestionEvaluationClassificationSource,
    policy_source: EvaluatorSelectionPolicySource,
    capability_source: EvaluatorCapabilitySource,
) -> ResolvedQuestionEvaluatorSelection:
    """Resolve one exact routing identity without authorizing evaluator execution."""

    grading_spec_ref, question_id, context_policy = _validate_question_authority(
        question_authority
    )

    # The source receives a detached lookup identity so it cannot mutate the
    # already-resolved question authority through a nested reference alias.
    try:
        source_classification = (
            classification_source.resolve_question_evaluation_classification(
                grading_spec_ref=_snapshot_grading_spec_ref(grading_spec_ref),
                question_id=question_id,
            )
        )
    except Exception as exc:
        raise QuestionClassificationSourceExecutionError(
            "Question-evaluation classification source failed during exact lookup."
        ) from exc

    if type(source_classification) is not QuestionEvaluationClassification:
        raise QuestionClassificationSourceResultError(
            "Question-evaluation classification source returned a non-contract value."
        )

    try:
        validate_question_evaluation_classification(source_classification)
        classification = _snapshot_classification(source_classification)
    except QuestionEvaluationClassificationContractError as exc:
        raise QuestionClassificationSourceResultError(
            "Question-evaluation classification source returned an invalid contract value."
        ) from exc

    if classification.grading_spec_ref != grading_spec_ref:
        raise QuestionClassificationBindingError(
            "Question-evaluation classification does not bind the exact grading_spec_ref."
        )
    if classification.question_id != question_id:
        raise QuestionClassificationBindingError(
            "Question-evaluation classification does not bind the exact question_id."
        )

    try:
        source_policy = policy_source.resolve_evaluator_selection_policy()
    except Exception as exc:
        raise SelectionPolicySourceExecutionError(
            "Evaluator-selection policy source failed during materialization."
        ) from exc

    if type(source_policy) is not EvaluatorSelectionPolicy:
        raise SelectionPolicySourceResultError(
            "Evaluator-selection policy source returned a non-policy value."
        )

    try:
        validate_evaluator_selection_policy(source_policy)
        policy = _snapshot_policy(source_policy)
    except EvaluatorSelectionPolicyContractError as exc:
        raise SelectionPolicySourceResultError(
            "Evaluator-selection policy source returned an invalid policy value."
        ) from exc

    selected_rule: EvaluatorSelectionRule | None = None
    for rule in policy.rules:
        if (
            rule.answer_type == classification.answer_type
            and rule.language == classification.language
            and rule.context_policy is context_policy
        ):
            selected_rule = rule
            break

    if selected_rule is None:
        raise EvaluatorSelectionMissingRuleError(
            "No exact evaluator-selection rule exists for the bound classification/context tuple."
        )

    selected_capability_ref = _snapshot_capability_ref(selected_rule.capability_ref)

    # evaluator capability resolution owns exact capability lookup and all of its native failure categories.
    # Do not translate evaluator capability resolution errors into evaluator selection routing errors.
    resolved_capability = resolve_evaluator_capability(
        capability_ref=selected_capability_ref,
        source=capability_source,
    )

    capability_record = resolved_capability.record
    if classification.answer_type not in capability_record.supported_answer_types:
        raise EvaluatorCapabilitySupportMismatchError(
            "Resolved evaluator capability does not claim the exact selected answer_type."
        )
    if classification.language not in capability_record.supported_languages:
        raise EvaluatorCapabilitySupportMismatchError(
            "Resolved evaluator capability does not claim the exact selected language."
        )

    return ResolvedQuestionEvaluatorSelection(
        classification=classification,
        context_policy=context_policy,
        policy_ref=_snapshot_policy_ref(policy.policy_ref),
        selected_capability_ref=_snapshot_capability_ref(selected_capability_ref),
        resolved_capability=resolved_capability,
    )
