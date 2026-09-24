from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.paper_aggregation import (
    GradingSpecRef,
    ResolvedPaperScoringAuthority,
    _validate_grading_spec_ref,
    _validate_identifier,
)
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.rubric.lifecycle import RubricAuthoringVersion, get_active_scoring_authority
from grading.rubric.models import QuestionRubricAuthoringContent


class ContextPolicy(str, Enum):
    """Authorized ACTIVE question context-policy vocabulary."""

    DIRECT = "DIRECT"
    DIRECT_PLUS_REFERENCE = "DIRECT_PLUS_REFERENCE"
    HYBRID_RETRIEVAL = "HYBRID_RETRIEVAL"
    REFERENCE_ONLY = "REFERENCE_ONLY"


class ActiveQuestionAuthorityError(Exception):
    """Expected failure while binding admitted ACTIVE question authority."""


class ActiveQuestionAuthoritySourceExecutionError(ActiveQuestionAuthorityError):
    """Configured ACTIVE-spec source failed during resolution/materialization."""


class ActiveQuestionSelection(Protocol):
    """Structural result returned by an upstream-admitted spec source.

    Conformance to this protocol is not proof of trust, authorization, tenant
    ownership, or backend provenance. Those are responsibilities of the caller
    that supplies the configured source implementation.
    """

    grading_spec_ref: GradingSpecRef
    question_id: str
    question_text: str
    context_policy: ContextPolicy
    active_rubric: RubricAuthoringVersion


class ActiveGradingSpecSource(Protocol):
    """Integration seam for an already-admitted ACTIVE-spec source.

    Implementing this protocol does not authenticate or authorize a source. The
    caller/composition root is responsible for supplying an admitted source
    implementation. The grading core only verifies deterministic relationships
    in the value returned by that source.
    """

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> ActiveQuestionSelection:
        ...


@dataclass(frozen=True, slots=True)
class ResolvedQuestionAuthority:
    """Read-only evaluator-facing projection of one admitted ACTIVE question."""

    grading_spec_ref: GradingSpecRef
    question_id: str
    question_text: str
    context_policy: ContextPolicy
    rubric_content: QuestionRubricAuthoringContent
    scoring_authority: QuestionScoringAuthority


def _expected_question(
    paper_authority: ResolvedPaperScoringAuthority,
    question_id: str,
):
    for expected in paper_authority.expected_questions:
        if expected.question_id == question_id:
            return expected
    raise ActiveQuestionAuthorityError(
        f"Question {question_id!r} is not part of the admitted paper authority."
    )


def resolve_active_question_authority(
    *,
    paper_authority: ResolvedPaperScoringAuthority,
    question_id: str,
    source: ActiveGradingSpecSource,
) -> ResolvedQuestionAuthority:
    """Resolve one evaluator-facing authority without creating authority.

    ``paper_authority`` and ``source`` are already-admitted upstream inputs.
    This function does not authenticate their backend origin, tenant ownership,
    or caller authorization. It cross-checks only the deterministic relationships
    owned by this grading-core boundary and derives reducer authority through the
    existing ACTIVE rubric lifecycle.
    """

    if type(paper_authority) is not ResolvedPaperScoringAuthority:
        raise TypeError(
            "paper_authority must be an exact ResolvedPaperScoringAuthority."
        )
    if (
        type(question_id) is not str
        or not question_id
        or question_id.strip() != question_id
    ):
        raise TypeError(
            "question_id must be a non-empty exact string without surrounding whitespace."
        )

    expected = _expected_question(paper_authority, question_id)

    try:
        selected = source.resolve_active_question(
            grading_spec_ref=paper_authority.grading_spec_ref,
            question_id=question_id,
        )
    except Exception as exc:
        raise ActiveQuestionAuthoritySourceExecutionError(
            "ACTIVE question source failed during question resolution."
        ) from exc

    try:
        selected_spec_ref = selected.grading_spec_ref
        selected_question_id = selected.question_id
        selected_question_text = selected.question_text
        selected_context_policy = selected.context_policy
        active_rubric = selected.active_rubric
    except AttributeError as exc:
        raise ActiveQuestionAuthorityError(
            "source returned an invalid ACTIVE-question selection."
        ) from exc
    except Exception as exc:
        raise ActiveQuestionAuthoritySourceExecutionError(
            "ACTIVE question source failed during selection materialization."
        ) from exc

    validated_selected_spec_ref = _validate_grading_spec_ref(
        selected_spec_ref,
        field_name="source_selection.grading_spec_ref",
        error_type=ActiveQuestionAuthorityError,
    )
    validated_selected_question_id = _validate_identifier(
        selected_question_id,
        field_name="source_selection.question_id",
        error_type=ActiveQuestionAuthorityError,
    )

    if validated_selected_spec_ref != paper_authority.grading_spec_ref:
        raise ActiveQuestionAuthorityError(
            "source-selected grading_spec_ref does not match the admitted paper authority."
        )
    if validated_selected_question_id != question_id:
        raise ActiveQuestionAuthorityError(
            "source-selected question_id does not match the requested question."
        )
    if type(selected_question_text) is not str:
        raise ActiveQuestionAuthorityError(
            "source-selected question_text must be an exact string."
        )
    if (
        type(selected_context_policy) is not ContextPolicy
        or not any(
            selected_context_policy is member
            for member in ContextPolicy
        )
    ):
        raise ActiveQuestionAuthorityError(
            "source-selected context_policy must be a canonical ContextPolicy member."
        )
    if type(active_rubric) is not RubricAuthoringVersion:
        raise ActiveQuestionAuthorityError(
            "source-selected active_rubric must be an exact RubricAuthoringVersion."
        )
    if active_rubric.finalized_question.question_id != question_id:
        raise ActiveQuestionAuthorityError(
            "source-selected rubric is bound to a different finalized question."
        )

    scoring_authority = get_active_scoring_authority(active_rubric)

    derived_rubric_ref = RubricRef(
        id=scoring_authority.rubric.rubric_id,
        version=scoring_authority.rubric.version,
    )
    if derived_rubric_ref != expected.rubric_ref:
        raise ActiveQuestionAuthorityError(
            "source-selected ACTIVE rubric does not match the paper's expected rubric reference."
        )

    derived_policy_ref = ScoringPolicyRef(
        id=scoring_authority.policy.policy_id,
        version=scoring_authority.policy.version,
        scoring_semantics_version=scoring_authority.policy.scoring_semantics_version,
    )
    if derived_policy_ref != expected.scoring_policy_ref:
        raise ActiveQuestionAuthorityError(
            "derived scoring policy does not match the paper's expected scoring-policy reference."
        )

    return ResolvedQuestionAuthority(
        grading_spec_ref=paper_authority.grading_spec_ref,
        question_id=question_id,
        question_text=selected_question_text,
        context_policy=selected_context_policy,
        rubric_content=active_rubric.content,
        scoring_authority=scoring_authority,
    )
