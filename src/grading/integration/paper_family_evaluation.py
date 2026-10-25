"""Actual DIRECT and NUMERIC evaluation -> deterministic scoring -> frozen paper scoring.

This is the question-evaluation stage, not a source issuer, physical attempt claim allocator,
scored-CAS writer, grade decision, or publishing authority. The surrounding
production root MUST acquire qualified source/runtime authority and physical attempt
identity before using it in an effectful whole-paper execution. No caller may
supply the criterion judgments through this interface.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.contracts.evidence import AnswerEvidenceBundle
from grading.contracts.paper_aggregation import GradingSpecRef, ResolvedPaperScoringAuthority
from grading.execution import (
    GradingExecutionContext, GradingExecutionResult, QuestionExecutionInput,
    execute_grading_from_evaluations,
)
from grading.numeric_judgments import evaluate_numeric_question_to_judgments
from grading.semantic_evaluator import DirectTextSemanticEvaluator, SemanticEvaluationResult


class PaperFamilyEvaluationDenied(ValueError):
    """Unsupported family, inventory, or per-question identity."""



def _admitted_values(value: object, *, depth: int = 0, visiting: frozenset[int] = frozenset()) -> tuple:
    """Represent grading-owned values without invoking foreign copy/equality hooks.

    The canonical admitted structures are exact primitive values, enums, tuples
    and Gradified dataclasses. Reject anything else rather than interpreting an
    arbitrary Python object's equality/copy behavior as evidence of continuity.
    This is an in-process custody check, not issuer authentication.
    """
    kind = type(value)
    if depth > 40:
        raise PaperFamilyEvaluationDenied('Grading input nesting exceeds custody admission.')
    if value is None or kind in (str, int, bool, float):
        return (kind, value)
    if kind is Decimal:
        if not value.is_finite():
            raise PaperFamilyEvaluationDenied('Nonfinite grading input.')
        return (kind, value.as_tuple())
    if issubclass(kind, Enum) and kind.__module__.startswith('grading.'):
        return (kind, value.name)
    if kind is tuple:
        if id(value) in visiting:
            raise PaperFamilyEvaluationDenied('Cyclic grading inventory.')
        path = visiting | {id(value)}
        return (tuple, tuple(_admitted_values(item, depth=depth + 1, visiting=path) for item in value))
    if (is_dataclass(value) and kind.__module__.startswith('grading.')
            and id(value) not in visiting):
        path = visiting | {id(value)}
        return (kind, tuple(
            (field.name, _admitted_values(getattr(value, field.name), depth=depth + 1, visiting=path))
            for field in fields(value)
        ))
    raise PaperFamilyEvaluationDenied('Unsupported or cyclic nested grading input.')


def _detached_admitted(value: object) -> object:
    """Detach an already-admitted Gradified input graph without copy hooks.

    This deliberately excludes installed callbacks/providers. They remain the
    installation's responsibility, while all academic/evidence values handed to
    them are independent of the caller-owned source records.
    """
    kind = type(value)
    if value is None or kind in (str, int, bool, float, Decimal) or (
        issubclass(kind, Enum) and kind.__module__.startswith('grading.')
    ):
        return value
    if kind is tuple:
        return tuple(_detached_admitted(item) for item in value)
    if is_dataclass(value) and kind.__module__.startswith('grading.'):
        replica = object.__new__(kind)
        for field in fields(value):
            object.__setattr__(replica, field.name, _detached_admitted(getattr(value, field.name)))
        return replica
    raise PaperFamilyEvaluationDenied('Cannot detach an unadmitted grading input.')


def _selected_evidence_values(evidence: AnswerEvidenceBundle, question_ids: set[str]) -> tuple:
    """Only selected answer regions form this grading-operation custody record."""
    if type(evidence.questions) is not tuple:
        raise PaperFamilyEvaluationDenied('Invalid answer inventory.')
    # Check every inventory member's ID before set membership invokes equality.
    # Unselected evidence is permitted but cannot supply an arbitrary object
    # that executes code during the question-selection comparison.
    from grading.contracts.evidence import QuestionEvidence
    if any(type(q) is not QuestionEvidence or type(q.question_id) is not str
           for q in evidence.questions):
        raise PaperFamilyEvaluationDenied('Invalid evidence question identity.')
    selected = tuple(q for q in evidence.questions if q.question_id in question_ids)
    if len(selected) != len(question_ids):
        raise PaperFamilyEvaluationDenied('Missing or repeated selected question evidence.')
    return _admitted_values((evidence.schema_version, evidence.submission_ref,
                             evidence.ocr_provenance, selected))


@dataclass(frozen=True, slots=True, repr=False)
class DirectQuestionEvaluation:
    authority: ResolvedQuestionAuthority
    evaluator: DirectTextSemanticEvaluator
    evaluation_attempt_id: str


@dataclass(frozen=True, slots=True, repr=False)
class NumericQuestionEvaluation:
    authority: ResolvedQuestionAuthority
    binding_source: object
    authority_source: object


def evaluate_supported_paper_questions(
    *, context: GradingExecutionContext, evidence: AnswerEvidenceBundle,
    paper_authority: ResolvedPaperScoringAuthority,
    operations: tuple[DirectQuestionEvaluation | NumericQuestionEvaluation, ...],
) -> GradingExecutionResult:
    """Evaluate the *complete* selected DIRECT/NUMERIC inventory and score it.

    The configured evaluator/resolver sources must already be qualified by an
    independent production installation; their mere presence is not authority.
    Preflight every question before the first external provider call. Technical
    and academic-unsupported failures propagate, never become zero marks.
    """
    if (type(context) is not GradingExecutionContext
            or type(evidence) is not AnswerEvidenceBundle
            or type(paper_authority) is not ResolvedPaperScoringAuthority
            or type(operations) is not tuple or not 0 < len(operations) <= 1000):
        raise PaperFamilyEvaluationDenied('Exact bounded whole-paper inputs required.')
    # Structural admission MUST precede cross-record equality. Even exact
    # frozen dataclasses can have hostile nested values installed after init.
    admitted_context_values = _admitted_values(context)
    admitted_paper_values = _admitted_values(paper_authority)
    if (type(context.submission_ref) is not str
            or type(context.grading_spec_ref) is not GradingSpecRef
            or type(evidence.submission_ref) is not str
            or type(evidence.schema_version) is not str
            or type(evidence.ocr_provenance) is not str):
        raise PaperFamilyEvaluationDenied('Malformed grading/evidence origin.')
    try:
        GradingSpecRef(context.grading_spec_ref.id, context.grading_spec_ref.version)
    except (ValueError, TypeError, AttributeError) as exc:
        raise PaperFamilyEvaluationDenied('Malformed grading specification reference.') from exc
    if (type(paper_authority.grading_spec_ref) is not GradingSpecRef
            or context.submission_ref != evidence.submission_ref
            or _admitted_values(context.grading_spec_ref)
               != _admitted_values(paper_authority.grading_spec_ref)):
        raise PaperFamilyEvaluationDenied('Paper scoring and evidence origins differ.')
    expected = paper_authority.expected_questions
    if (type(expected) is not tuple or len(expected) != len(operations)):
        raise PaperFamilyEvaluationDenied('Question inventory is not complete.')
    if type(evidence.questions) is not tuple:
        raise PaperFamilyEvaluationDenied('Evidence inventory must be a tuple.')
    from grading.contracts.evidence import QuestionEvidence
    if any(type(q) is not QuestionEvidence or type(q.question_id) is not str
           for q in evidence.questions):
        raise PaperFamilyEvaluationDenied('Invalid evidence question identity.')
    evidence_ids = tuple(question.question_id for question in evidence.questions)
    ids = set()
    for expected_question, operation in zip(expected, operations, strict=True):
        kind = type(operation)
        if kind not in (DirectQuestionEvaluation, NumericQuestionEvaluation):
            raise PaperFamilyEvaluationDenied('Unsupported or foreign family operation.')
        authority = operation.authority
        if type(authority) is not ResolvedQuestionAuthority:
            raise PaperFamilyEvaluationDenied('Unresolved question authority.')
        qid = authority.question_id
        # Admit both nested graphs before comparing question/spec identity.
        _admitted_values(authority)
        _admitted_values(expected_question)
        if (type(qid) is not str or not qid or qid.strip() != qid
                or type(expected_question.question_id) is not str
                or qid in ids or qid != expected_question.question_id
                or _admitted_values(authority.grading_spec_ref)
                   != _admitted_values(context.grading_spec_ref)
                or evidence_ids.count(qid) != 1):
            raise PaperFamilyEvaluationDenied('Question/evidence selection mismatch.')
        ids.add(qid)
        scoring = authority.scoring_authority
        from grading.contracts.result import RubricRef, ScoringPolicyRef
        if (RubricRef(scoring.rubric.rubric_id, scoring.rubric.version)
                    != expected_question.rubric_ref
                or ScoringPolicyRef(scoring.policy.policy_id, scoring.policy.version,
                                    scoring.policy.scoring_semantics_version)
                    != expected_question.scoring_policy_ref):
            raise PaperFamilyEvaluationDenied('Question scoring authority differs from paper.')
        if kind is DirectQuestionEvaluation:
            if (type(operation.evaluator) is not DirectTextSemanticEvaluator
                    or authority.context_policy is not ContextPolicy.DIRECT
                    or type(operation.evaluation_attempt_id) is not str
                    or not operation.evaluation_attempt_id
                    or operation.evaluation_attempt_id.strip() != operation.evaluation_attempt_id):
                raise PaperFamilyEvaluationDenied('DIRECT runtime or attempt is invalid.')
        else:
            if (not callable(getattr(operation.binding_source, 'resolve_numeric_binding', None))
                    or not callable(getattr(operation.authority_source, 'materialize_numeric_authority', None))):
                raise PaperFamilyEvaluationDenied('NUMERIC sources are not installed.')

    # Capture original operation ownership and the exact academic/execution
    # context before invoking installed callbacks. Frozen wrappers can still be
    # mutated with object.__setattr__, so their immutability is NOT a custody
    # guarantee. Compare against the retained admission following every contact.
    # The evaluator consumes detached, already admitted academic and selected
    # OCR values. Comparing mutable originals after callbacks alone is not
    # enough: a callback may substitute and restore them in between reads.
    admitted_context = _detached_admitted(context)
    original_authorities = tuple(op.authority for op in operations)
    original_attempts = tuple(op.evaluation_attempt_id if type(op) is DirectQuestionEvaluation
                              else None for op in operations)
    admitted_operations = tuple(
        DirectQuestionEvaluation(_detached_admitted(op.authority), op.evaluator,
                                 op.evaluation_attempt_id)
        if type(op) is DirectQuestionEvaluation else
        NumericQuestionEvaluation(_detached_admitted(op.authority),
                                  op.binding_source, op.authority_source)
        for op in operations
    )
    admitted_authority_values = tuple(_admitted_values(authority) for authority in original_authorities)
    admitted_evidence_values = _selected_evidence_values(evidence, ids)
    selected_evidence = tuple(q for q in evidence.questions if q.question_id in ids)
    admitted_evidence = _detached_admitted(AnswerEvidenceBundle(
        evidence.schema_version, evidence.submission_ref,
        evidence.ocr_provenance, selected_evidence,
    ))
    admitted_paper = _detached_admitted(paper_authority)
    admitted_direct_installations = tuple(
        (op.evaluator, op.evaluator._model_answer_source, op.evaluator._provider,
         _admitted_values(op.evaluator._limits),
         _admitted_values(op.evaluator._evaluator_metadata))
        for op in operations if type(op) is DirectQuestionEvaluation
    )

    def require_continuity() -> None:
        if _admitted_values(context) != admitted_context_values:
            raise PaperFamilyEvaluationDenied('Original grading execution context changed.')
        if (_admitted_values(paper_authority) != admitted_paper_values
                or tuple(_admitted_values(authority) for authority in original_authorities)
                   != admitted_authority_values
                or _selected_evidence_values(evidence, ids) != admitted_evidence_values):
            raise PaperFamilyEvaluationDenied('Original grading operation inputs changed.')
        direct_installations = (op.evaluator for op in operations
                                if type(op) is DirectQuestionEvaluation)
        for evaluator, (original_evaluator, source, provider, limits, metadata) in zip(
                direct_installations, admitted_direct_installations, strict=True):
            if (evaluator is not original_evaluator
                    or evaluator._model_answer_source is not source
                    or evaluator._provider is not provider
                    or _admitted_values(evaluator._limits) != limits
                    or _admitted_values(evaluator._evaluator_metadata) != metadata):
                raise PaperFamilyEvaluationDenied('DIRECT provider installation changed.')
        for original, admitted, authority, attempt in zip(
                operations, admitted_operations, original_authorities,
                original_attempts, strict=True):
            if type(original) is not type(admitted) or original.authority is not authority:
                raise PaperFamilyEvaluationDenied('Original question operation changed.')
            if type(original) is DirectQuestionEvaluation:
                if (original.evaluator is not admitted.evaluator
                        or type(original.evaluation_attempt_id) is not str
                        or original.evaluation_attempt_id != attempt):
                    raise PaperFamilyEvaluationDenied('Original DIRECT attempt or evaluator changed.')
            elif (original.binding_source is not admitted.binding_source
                  or original.authority_source is not admitted.authority_source):
                raise PaperFamilyEvaluationDenied('Original NUMERIC installed sources changed.')

    # All cheap DIRECT evidence and bounded capability failures are checked for
    # every question before a provider can be contacted. Reuse the actual
    # evaluator's deterministic preflight, not a second approximation of it.
    for operation in admitted_operations:
        if type(operation) is DirectQuestionEvaluation:
            operation.evaluator.preflight_local(
                authority=operation.authority, evidence=admitted_evidence,
                execution_context=admitted_context,
                evaluation_attempt_id=operation.evaluation_attempt_id,
            )
    require_continuity()

    # Reject an unapproved NUMERIC authority before spending a DIRECT provider
    # invocation for an otherwise ungradable paper. Numeric N1–N4 still executes
    # once, with its real original evidence and approved projection. Preserve
    # official question order when deterministic scoring/scoring consumes the finished inventory.
    evaluated_by_question: dict[str, QuestionExecutionInput] = {}
    for operation in admitted_operations:
        require_continuity()
        if type(operation) is NumericQuestionEvaluation:
            authority = operation.authority
            judgments = evaluate_numeric_question_to_judgments(
                active_authority=authority, evidence=admitted_evidence,
                binding_source=operation.binding_source,
                authority_source=operation.authority_source,
            )
            require_continuity()
            evaluated_by_question[authority.question_id] = QuestionExecutionInput(
                question_id=authority.question_id, judgments=judgments,
                authority=authority.scoring_authority,
            )
    for operation in admitted_operations:
        require_continuity()
        if type(operation) is DirectQuestionEvaluation:
            authority = operation.authority
            result = operation.evaluator.evaluate(
                authority=authority, evidence=admitted_evidence,
                execution_context=admitted_context,
                evaluation_attempt_id=operation.evaluation_attempt_id,
            )
            require_continuity()
            if (type(result) is not SemanticEvaluationResult
                    or result.question_id != authority.question_id
                    or result.execution_context != admitted_context
                    or result.evaluation_attempt_id != operation.evaluation_attempt_id):
                raise PaperFamilyEvaluationDenied('DIRECT evaluation origin changed.')
            evaluated_by_question[authority.question_id] = QuestionExecutionInput(
                question_id=authority.question_id, judgments=result.judgments,
                authority=authority.scoring_authority,
            )
    require_continuity()
    result = execute_grading_from_evaluations(
        context=admitted_context, evidence=admitted_evidence,
        questions=tuple(evaluated_by_question[op.authority.question_id] for op in admitted_operations),
        paper_authority=admitted_paper,
    )
    require_continuity()
    return result
