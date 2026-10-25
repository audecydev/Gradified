from __future__ import annotations

from typing import NoReturn as _NoReturn

from grading.active_question_authority import (
    ContextPolicy as _ContextPolicy,
    ResolvedQuestionAuthority as _ResolvedQuestionAuthority,
)
from grading.contracts.authority import QuestionScoringAuthority as _QuestionScoringAuthority
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult as _ExpectedQuestionResult,
    GradingSpecRef as _GradingSpecRef,
    ResolvedPaperScoringAuthority as _ResolvedPaperScoringAuthority,
)
from grading.contracts.result import (
    RubricRef as _RubricRef,
    ScoringPolicyRef as _ScoringPolicyRef,
)
from grading.execution import GradingExecutionContext as _GradingExecutionContext
from grading.integration.evidence_ingress import (
    AdmittedNormalizedEvidence as _AdmittedNormalizedEvidence,
)
from grading.rubric.models import (
    QuestionRubricAuthoringContent as _QuestionRubricAuthoringContent,
)


__all__ = (
    "QuestionEvaluationBindingError",
    "BoundQuestionEvaluationInputs",
    "bind_question_evaluation_inputs",
)


class QuestionEvaluationBindingError(ValueError):
    """Expected question evidence binding structural or cross-object binding rejection."""

    __slots__ = ()


class BoundQuestionEvaluationInputs:
    """Immutable four-root result of successful question evidence binding question binding."""

    context: _GradingExecutionContext
    admitted_evidence: _AdmittedNormalizedEvidence
    paper_authority: _ResolvedPaperScoringAuthority
    question_authority: _ResolvedQuestionAuthority

    __slots__ = (
        "context",
        "admitted_evidence",
        "paper_authority",
        "question_authority",
    )

    def __new__(cls, *args: object, **kwargs: object) -> BoundQuestionEvaluationInputs:
        del cls, args, kwargs
        raise TypeError(
            "BoundQuestionEvaluationInputs instances are created only by "
            "bind_question_evaluation_inputs()."
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("BoundQuestionEvaluationInputs cannot be subclassed.")

    def __setattr__(self, name: str, value: object) -> None:
        del self, name, value
        raise AttributeError("BoundQuestionEvaluationInputs is immutable.")

    def __delattr__(self, name: str) -> None:
        del self, name
        raise AttributeError("BoundQuestionEvaluationInputs is immutable.")

    def __repr__(self) -> str:
        return "BoundQuestionEvaluationInputs(<bound>)"

    __str__ = __repr__


def _reject(message: str) -> _NoReturn:
    raise QuestionEvaluationBindingError(message)


def _require_weak_question_authority_fields(
    question_authority: _ResolvedQuestionAuthority,
) -> tuple[
    _GradingSpecRef,
    str,
    str,
    _ContextPolicy,
    _QuestionRubricAuthoringContent,
    _QuestionScoringAuthority,
]:
    grading_spec_ref = question_authority.grading_spec_ref
    question_id = question_authority.question_id
    question_text = question_authority.question_text
    context_policy = question_authority.context_policy
    rubric_content = question_authority.rubric_content
    scoring_authority = question_authority.scoring_authority

    if type(grading_spec_ref) is not _GradingSpecRef:
        _reject("question_authority.grading_spec_ref has an invalid type.")
    if type(question_id) is not str or not question_id or question_id.strip() != question_id:
        _reject("question_authority.question_id has an invalid value.")
    if type(question_text) is not str:
        _reject("question_authority.question_text has an invalid type.")
    if type(context_policy) is not _ContextPolicy or not any(
        context_policy is member for member in _ContextPolicy
    ):
        _reject("question_authority.context_policy is not canonical.")
    if type(rubric_content) is not _QuestionRubricAuthoringContent:
        _reject("question_authority.rubric_content has an invalid type.")
    if type(scoring_authority) is not _QuestionScoringAuthority:
        _reject("question_authority.scoring_authority has an invalid type.")

    return (
        grading_spec_ref,
        question_id,
        question_text,
        context_policy,
        rubric_content,
        scoring_authority,
    )


def _find_expected_question(
    paper_authority: _ResolvedPaperScoringAuthority,
    question_id: str,
) -> _ExpectedQuestionResult:
    for expected in paper_authority.expected_questions:
        if expected.question_id == question_id:
            return expected
    _reject("question_authority.question_id is absent from paper_authority.")


def _require_bound_evidence_question(
    admitted_evidence: _AdmittedNormalizedEvidence,
    question_id: str,
) -> None:
    match_count = 0
    for question in admitted_evidence.evidence.questions:
        if question.question_id == question_id:
            match_count += 1
    if match_count != 1:
        _reject("admitted_evidence does not contain exactly one bound question.")


def _make_bound_result(
    *,
    context: _GradingExecutionContext,
    admitted_evidence: _AdmittedNormalizedEvidence,
    paper_authority: _ResolvedPaperScoringAuthority,
    question_authority: _ResolvedQuestionAuthority,
) -> BoundQuestionEvaluationInputs:
    bound = object.__new__(BoundQuestionEvaluationInputs)
    object.__setattr__(bound, "context", context)
    object.__setattr__(bound, "admitted_evidence", admitted_evidence)
    object.__setattr__(bound, "paper_authority", paper_authority)
    object.__setattr__(bound, "question_authority", question_authority)
    return bound


def _bind_question_evaluation_inputs_impl(
    *,
    context: _GradingExecutionContext,
    admitted_evidence: _AdmittedNormalizedEvidence,
    paper_authority: _ResolvedPaperScoringAuthority,
    question_authority: _ResolvedQuestionAuthority,
) -> BoundQuestionEvaluationInputs:
    """Bind one admitted question snapshot for later evaluation.

    This boundary performs only deterministic local structural and identity
    checks across the four supplied roots. It does not resolve authority,
    interpret evidence, select evaluators, verify judgments, or score work.
    """

    if type(context) is not _GradingExecutionContext:
        _reject("context must be an exact GradingExecutionContext.")
    if type(admitted_evidence) is not _AdmittedNormalizedEvidence:
        _reject("admitted_evidence must be an exact AdmittedNormalizedEvidence.")
    if type(paper_authority) is not _ResolvedPaperScoringAuthority:
        _reject("paper_authority must be an exact ResolvedPaperScoringAuthority.")
    if type(question_authority) is not _ResolvedQuestionAuthority:
        _reject("question_authority must be an exact ResolvedQuestionAuthority.")

    (
        question_spec_ref,
        question_id,
        _question_text,
        _context_policy,
        rubric_content,
        scoring_authority,
    ) = _require_weak_question_authority_fields(question_authority)

    if context.submission_ref != admitted_evidence.evidence.submission_ref:
        _reject("context and admitted_evidence submission identities do not match.")

    paper_spec_ref = paper_authority.grading_spec_ref
    if context.grading_spec_ref != paper_spec_ref:
        _reject("context and paper_authority grading-spec identities do not match.")
    if question_spec_ref != paper_spec_ref:
        _reject("question_authority and paper_authority grading-spec identities do not match.")

    expected = _find_expected_question(paper_authority, question_id)

    scoring_rubric = scoring_authority.rubric
    scoring_policy = scoring_authority.policy
    if scoring_rubric.question_id != question_id:
        _reject("scoring authority does not match the bound question identity.")

    derived_rubric_ref = _RubricRef(
        id=scoring_rubric.rubric_id,
        version=scoring_rubric.version,
    )
    if derived_rubric_ref != expected.rubric_ref:
        _reject("scoring rubric identity does not match paper_authority.")

    derived_policy_ref = _ScoringPolicyRef(
        id=scoring_policy.policy_id,
        version=scoring_policy.version,
        scoring_semantics_version=scoring_policy.scoring_semantics_version,
    )
    if derived_policy_ref != expected.scoring_policy_ref:
        _reject("scoring policy identity does not match paper_authority.")

    if rubric_content.rubric_id != scoring_rubric.rubric_id:
        _reject("rubric content identity does not match scoring authority.")
    if rubric_content.policy_id != scoring_policy.policy_id:
        _reject("rubric policy identity does not match scoring authority.")

    _require_bound_evidence_question(admitted_evidence, question_id)

    return _make_bound_result(
        context=context,
        admitted_evidence=admitted_evidence,
        paper_authority=paper_authority,
        question_authority=question_authority,
    )

def bind_question_evaluation_inputs(
    *,
    context: _GradingExecutionContext,
    admitted_evidence: _AdmittedNormalizedEvidence,
    paper_authority: _ResolvedPaperScoringAuthority,
    question_authority: _ResolvedQuestionAuthority,
) -> BoundQuestionEvaluationInputs:
    """Bind one admitted question snapshot for later evaluation.

    Expected question evidence binding rejections are re-raised with application-owned exception
    chaining state cleared. Unexpected technical/programming failures are not
    translated.
    """

    try:
        return _bind_question_evaluation_inputs_impl(
            context=context,
            admitted_evidence=admitted_evidence,
            paper_authority=paper_authority,
            question_authority=question_authority,
        )
    except QuestionEvaluationBindingError as exc:
        exc.__context__ = None
        exc.__cause__ = None
        exc.__suppress_context__ = True
        raise exc from None
