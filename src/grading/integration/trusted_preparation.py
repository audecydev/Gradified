"""Trusted-root-owned PRE source/policy custody before evidence materialization.

The installed backend supplies the trusted source port. A matching ID, Python type,
source reference, or the returned result is not authentication or execution permission.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import BinaryIO, Callable, Protocol

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.contracts.errors import ScoringError
from grading.rubric.errors import InvalidRubricAuthoringInputError
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.contracts.paper_aggregation import _validate_scoring_decimal_structure
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts import policy as scoring_policy
from grading.contracts import rubric as scoring_rubric
from grading.rubric import models as rubric_authoring
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult, GradingSpecRef, ResolvedPaperScoringAuthority,
)
from grading.execution import GradingExecutionContext
from grading.integration.evaluation_binding import BoundQuestionEvaluationInputs
from grading.integration.evidence_ingress import NormalizedEvidenceAdmissionPolicy
from grading.integration.question_evaluation_preparation import prepare_question_evaluation_inputs


__all__ = (
    "PreparationScopeRejected", "PreparationSourceUnavailable",
    "PreparationSourceContractError", "PreparationResourceLimitError",
    "PreparationRequest", "PreparationSourceSnapshot", "TrustedPreparationSource",
    "PreparedWithSourceCustody", "prepare_from_trusted_source",
)


class PreparationScopeRejected(ValueError):
    """The returned authoritative scope does not match this request."""


class PreparationSourceUnavailable(Exception):
    """Trusted source access or evidence stream failed."""


class PreparationSourceContractError(ValueError):
    """Trusted source returned an invalid preparation record."""


class PreparationResourceLimitError(ValueError):
    """A source exceeded the independently admitted normalized OCR evidence admission byte limit."""


def _field(value: object, field_name: str) -> object:
    """Read a required field from an exact domain record, including damaged frozen instances."""
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError:
        raise PreparationSourceContractError("Trusted preparation record is missing a required field.") from None


def _identifier(value: object, field_name: str, maximum: int | None = None) -> str:
    if (type(value) is not str or not value or
            (maximum is not None and len(value) > maximum) or value.strip() != value):
        raise PreparationSourceContractError(f"{field_name} must be a bounded exact nonempty identifier.")
    return value


def _identifier_limit(value: object) -> int:
    """A finite ceiling supplied by the separately trusted workflow root, not this request."""
    if type(value) is not int or value <= 0:
        raise PreparationSourceContractError("A positive trusted identifier limit is required.")
    return value


def _spec_snapshot(ref: object, maximum: int | None = None) -> GradingSpecRef:
    if type(ref) is not GradingSpecRef:
        raise PreparationSourceContractError("grading_spec_ref must be an exact GradingSpecRef.")
    try:
        return GradingSpecRef(id=_identifier(_field(ref, "id"), "grading_spec_ref.id", maximum),
                              version=_field(ref, "version"))
    except (TypeError, ValueError, ScoringError):
        raise PreparationSourceContractError("grading_spec_ref is malformed.") from None


@dataclass(frozen=True, slots=True)
class PreparationRequest:
    """Opaque scope requested by workflow; identifiers alone confer no authority."""

    tenant_ref: str
    session_ref: str
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    grading_spec_ref: GradingSpecRef
    question_id: str

    def __post_init__(self) -> None:
        for name in ("tenant_ref", "session_ref", "grading_run_id", "submission_ref", "exam_ref", "question_id"):
            _identifier(getattr(self, name), name)
        _spec_snapshot(self.grading_spec_ref)


def _request_snapshot(request: object, maximum: int) -> PreparationRequest:
    if type(request) is not PreparationRequest:
        raise PreparationSourceContractError("request must be an exact PreparationRequest.")
    values = {
        name: _identifier(_field(request, name), name, maximum)
        for name in ("tenant_ref", "session_ref", "grading_run_id", "submission_ref", "exam_ref", "question_id")
    }
    return PreparationRequest(**values,
        grading_spec_ref=_spec_snapshot(_field(request, "grading_spec_ref"), maximum))


@dataclass(frozen=True, slots=True)
class PreparationSourceSnapshot:
    """Returned by the separately trusted, root-owned source resolver.

    ``open_evidence`` must provide a fresh binary reader. It is not opened until
    source-scope, policy and authority identity checks have succeeded.
    """

    tenant_ref: str
    session_ref: str
    context: GradingExecutionContext
    paper_authority: ResolvedPaperScoringAuthority
    question_authority: ResolvedQuestionAuthority
    admission_policy: NormalizedEvidenceAdmissionPolicy
    source_artifact_ref: str | None
    open_evidence: Callable[[], BinaryIO]


class TrustedPreparationSource(Protocol):
    """Must be injected by the backend's authenticated composition root.

    The source itself owns tenant/session authorization and artifact access.
    Do not expose this interface for callers to inject arbitrary source objects.
    """

    def resolve_preparation(self, *, request: PreparationRequest) -> PreparationSourceSnapshot:
        ...


class PreparedWithSourceCustody:
    """Result of PRE composition; neither a trust token nor execution permit."""

    __slots__ = ("request", "bound")

    def __new__(cls, *args: object, **kwargs: object) -> PreparedWithSourceCustody:
        raise TypeError("Use prepare_from_trusted_source() to construct this result.")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("PreparedWithSourceCustody cannot be subclassed.")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("PreparedWithSourceCustody is immutable.")

    def __repr__(self) -> str:
        return "PreparedWithSourceCustody(<bound>)"


def _policy_snapshot(policy: object) -> NormalizedEvidenceAdmissionPolicy:
    if type(policy) is not NormalizedEvidenceAdmissionPolicy:
        raise PreparationSourceContractError("Trusted normalized evidence admission policy has the wrong type.")
    try:
        return NormalizedEvidenceAdmissionPolicy(
            **{field.name: _field(policy, field.name) for field in fields(NormalizedEvidenceAdmissionPolicy)}
        )
    except (TypeError, ValueError):
        raise PreparationSourceContractError("Trusted normalized evidence admission policy is malformed.") from None


# These are inert, constructor-validated authority records, not arbitrary
# source-controlled objects. Never run caller-defined __deepcopy__ callbacks.
_AUTHORITY_RECORDS = (
    GradingSpecRef, ExpectedQuestionResult, ResolvedPaperScoringAuthority,
    RubricRef, ScoringPolicyRef, ResolvedQuestionAuthority,
    QuestionScoringAuthority, scoring_rubric.CompiledQuestionRubric,
    scoring_rubric.AtomicCriterion, scoring_rubric.PerformanceLevel,
    scoring_policy.QuestionScoringPolicy,
    scoring_policy.PositiveCreditDependencyRule, scoring_policy.CriterionCondition,
    scoring_policy.GateRule, scoring_policy.CapRule, scoring_policy.DeductionRule,
    scoring_policy.RoundingRule,
    rubric_authoring.QuestionRubricAuthoringContent,
    rubric_authoring.AuthoringCriterion, rubric_authoring.AuthoringPerformanceLevel,
    rubric_authoring.AuthoringCriterionCondition,
    rubric_authoring.AuthoringPositiveCreditDependencyRule,
    rubric_authoring.AuthoringGateRule, rubric_authoring.AuthoringCapRule,
    rubric_authoring.AuthoringDeductionRule, rubric_authoring.AuthoringRoundingRule,
)
_AUTHORITY_ENUMS = (ContextPolicy, scoring_policy.RoundingMode)


def _copy_authority_data(value: object, depth: int = 0) -> object:
    """Reconstruct known immutable domain data through its frozen constructors."""
    if depth > 32:
        raise PreparationSourceContractError("Trusted authority nesting is too deep.")
    kind = type(value)
    if value is None or kind in (str, int, float, bool):
        return value
    if kind is tuple:
        return tuple(_copy_authority_data(item, depth + 1) for item in value)
    if kind is ScoringDecimal:
        _validate_scoring_decimal_structure(
            value, field_name="trusted.scoring_amount", error_type=ScoringError,
        )
        return ScoringDecimal(object.__getattribute__(value, "_value"))
    if kind in _AUTHORITY_ENUMS:
        if not any(value is member for member in kind):
            raise PreparationSourceContractError("Trusted authority enum is malformed.")
        return value
    if kind not in _AUTHORITY_RECORDS:
        raise PreparationSourceContractError("Trusted authority contains unsupported data.")
    return kind(**{
        f.name: _copy_authority_data(_field(value, f.name), depth + 1)
        for f in fields(kind)
    })


def _authority_snapshots(
    paper: ResolvedPaperScoringAuthority,
    question: ResolvedQuestionAuthority,
) -> tuple[ResolvedPaperScoringAuthority, ResolvedQuestionAuthority]:
    """Pin and validate both complete authority graphs before any evidence IO."""
    failed = False
    result = None
    try:
        result = (_copy_authority_data(paper), _copy_authority_data(question))
    except (
        AttributeError, TypeError, ValueError, OverflowError, ScoringError,
        InvalidRubricAuthoringInputError,
    ):
        failed = True
    if failed or result is None:
        raise PreparationSourceContractError("Trusted paper/question authority is malformed.") from None
    return result


def _snapshot_sources(source: object, request: PreparationRequest, maximum: int) -> tuple[
    GradingExecutionContext, ResolvedPaperScoringAuthority,
    ResolvedQuestionAuthority, NormalizedEvidenceAdmissionPolicy,
    str | None, Callable[[], BinaryIO],
]:
    if type(source) is not PreparationSourceSnapshot:
        raise PreparationSourceContractError("Trusted resolver returned a noncanonical source record.")
    source_tenant = _identifier(_field(source, "tenant_ref"), "source.tenant_ref", maximum)
    source_session = _identifier(_field(source, "session_ref"), "source.session_ref", maximum)
    if source_tenant != request.tenant_ref or source_session != request.session_ref:
        raise PreparationScopeRejected("Preparation tenant/session does not match admitted scope.")
    context = _field(source, "context")
    paper = _field(source, "paper_authority")
    question = _field(source, "question_authority")
    if (type(context) is not GradingExecutionContext or
            type(paper) is not ResolvedPaperScoringAuthority or
            type(question) is not ResolvedQuestionAuthority):
        raise PreparationSourceContractError("Trusted resolver returned invalid authority roots.")
    # Detached context/spec before any deferred evidence IO or decoder execution.
    try:
        context_snapshot = GradingExecutionContext(
            grading_run_id=_identifier(_field(context, "grading_run_id"), "context.grading_run_id", maximum),
            submission_ref=_identifier(_field(context, "submission_ref"), "context.submission_ref", maximum),
            exam_ref=_identifier(_field(context, "exam_ref"), "context.exam_ref", maximum),
            grading_spec_ref=_spec_snapshot(_field(context, "grading_spec_ref"), maximum),
        )
    except (TypeError, ValueError, ScoringError):
        raise PreparationSourceContractError("Trusted context is malformed.") from None
    paper_spec = _spec_snapshot(_field(paper, "grading_spec_ref"), maximum)
    question_spec = _spec_snapshot(_field(question, "grading_spec_ref"), maximum)
    question_id = _identifier(_field(question, "question_id"), "source.question_id", maximum)
    if (
        context_snapshot.grading_run_id != request.grading_run_id
        or context_snapshot.submission_ref != request.submission_ref
        or context_snapshot.exam_ref != request.exam_ref
        or context_snapshot.grading_spec_ref != request.grading_spec_ref
        or paper_spec != request.grading_spec_ref
        or question_spec != request.grading_spec_ref
        or question_id != request.question_id
    ):
        raise PreparationScopeRejected("Trusted preparation identity does not match requested scope.")

    # Snapshot every nested authority value before protected evidence IO. The
    # frozen constructors reject duplicate paper questions, contradictory marks
    # and malformed scoring rules, rather than only checking the selected ID.
    paper, question = _authority_snapshots(paper, question)
    # ResolvedQuestionAuthority has no runtime field validator. Match the
    # frozen question evidence binding shape requirements before any protected evidence is opened.
    if type(question.question_text) is not str:
        raise PreparationSourceContractError("Trusted question text has invalid type.")
    if type(question.context_policy) is not ContextPolicy or not any(
        question.context_policy is member for member in ContextPolicy
    ):
        raise PreparationSourceContractError("Trusted question context policy is not canonical.")
    if (
        paper.grading_spec_ref != request.grading_spec_ref
        or question.grading_spec_ref != request.grading_spec_ref
        or question.question_id != request.question_id
    ):
        raise PreparationScopeRejected("Trusted authority changed during source snapshotting.")
    expected_questions = paper.expected_questions
    for item in expected_questions:
        _identifier(item.question_id, "paper.expected_question.question_id", maximum)
        _identifier(item.rubric_ref.id, "paper.rubric_ref.id", maximum)
        _identifier(item.scoring_policy_ref.id, "paper.scoring_policy_ref.id", maximum)
    if sum(item.question_id == request.question_id for item in expected_questions) != 1:
        raise PreparationScopeRejected("Trusted paper does not select exactly one requested question.")

    # Known selected-question authority references must agree before opening
    # private evidence; question evidence binding still performs full post-normalized OCR evidence admission binding.
    expected = next(item for item in expected_questions if item.question_id == request.question_id)
    scoring = question.scoring_authority
    rubric = scoring.rubric
    scoring_policy = scoring.policy
    if (
        expected.rubric_ref != RubricRef(id=rubric.rubric_id, version=rubric.version)
        or expected.scoring_policy_ref != ScoringPolicyRef(
            id=scoring_policy.policy_id, version=scoring_policy.version,
            scoring_semantics_version=scoring_policy.scoring_semantics_version)
        or rubric.question_id != request.question_id
        or scoring_policy.question_id != request.question_id
        or question.rubric_content.rubric_id != rubric.rubric_id
        or question.rubric_content.policy_id != scoring_policy.policy_id
    ):
        raise PreparationScopeRejected("Trusted question authority references do not match paper scope.")

    policy = _policy_snapshot(_field(source, "admission_policy"))
    artifact_ref = _field(source, "source_artifact_ref")
    if artifact_ref is not None and (
        type(artifact_ref) is not str or not artifact_ref
        or len(artifact_ref) > min(policy.max_identifier_characters, maximum)
        or artifact_ref.strip() != artifact_ref
    ):
        raise PreparationSourceContractError("Trusted source artifact reference is invalid.")
    reader = _field(source, "open_evidence")
    if not callable(reader):
        raise PreparationSourceContractError("Trusted evidence opener is not callable.")
    return context_snapshot, paper, question, policy, artifact_ref, reader


def _read_bounded(open_evidence: Callable[[], BinaryIO], max_bytes: int) -> bytes:
    """Bound first-party materialization; never call unbounded read()."""
    chunks: list[bytes] = []
    count = 0
    failed = False
    exceeded = False
    reader: object = None
    try:
        reader = open_evidence()
        while True:
            wanted = min(65_536, max_bytes - count + 1)
            chunk = reader.read(wanted)  # type: ignore[union-attr]
            if type(chunk) is not bytes:
                failed = True
                break
            if len(chunk) > wanted or count + len(chunk) > max_bytes:
                exceeded = True
                break
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
    except Exception:
        failed = True
    finally:
        if reader is not None:
            try:
                reader.close()  # type: ignore[union-attr]
            except Exception:
                failed = True
    # Raise outside exception handlers: do not chain student/private source errors.
    if exceeded:
        raise PreparationResourceLimitError("Trusted evidence source exceeded approved byte limit.") from None
    if failed:
        raise PreparationSourceUnavailable("Trusted evidence source read failed.") from None
    return b"".join(chunks)


def _prepare_impl(
    *, request: PreparationRequest, source: TrustedPreparationSource,
    max_identifier_characters: int,
) -> PreparedWithSourceCustody:
    maximum = _identifier_limit(max_identifier_characters)
    expected = _request_snapshot(request, maximum)
    if source is None:
        raise PreparationSourceUnavailable("No trusted preparation source was configured.")
    unavailable = False
    resolved: object = None
    try:
        resolved = source.resolve_preparation(request=_request_snapshot(expected, maximum))
    except Exception:
        unavailable = True
    if unavailable:
        raise PreparationSourceUnavailable("Trusted preparation source resolution failed.") from None
    context, paper, question, policy, artifact_ref, opener = _snapshot_sources(resolved, expected, maximum)
    raw = _read_bounded(opener, policy.max_raw_bytes)
    bound = prepare_question_evaluation_inputs(
        raw_payload=raw, admission_policy=policy, source_artifact_ref=artifact_ref,
        context=context, paper_authority=paper, question_authority=question,
    )
    # The admitted policy is derived from our own private snapshot, never from
    # a caller-selected prepared object or a re-read of the source's policy.
    if bound.admitted_evidence.effective_policy_snapshot != policy:
        raise PreparationSourceContractError("Admission policy custody changed.")
    result = object.__new__(PreparedWithSourceCustody)
    object.__setattr__(result, "request", expected)
    object.__setattr__(result, "bound", bound)
    return result


def prepare_from_trusted_source(
    *, request: PreparationRequest, source: TrustedPreparationSource,
    max_identifier_characters: int,
) -> PreparedWithSourceCustody:
    """Compose normalized OCR evidence admission→question evidence binding using externally authorized source-owned facts.

    The trusted backend must protect ``source`` itself and enforce authorization
    while resolving it. This function cannot authenticate a caller-supplied port.
    """
    try:
        return _prepare_impl(request=request, source=source,
                             max_identifier_characters=max_identifier_characters)
    except (PreparationScopeRejected, PreparationSourceUnavailable,
            PreparationSourceContractError, PreparationResourceLimitError) as caught:
        caught.__cause__ = None
        caught.__context__ = None
        caught.__suppress_context__ = True
        raise caught from None
