from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.errors import InvalidCriterionJudgmentError
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlockState,
    EvidenceBlockType,
)
from grading.contracts.judgment import CriterionJudgment
from grading.contracts.paper_aggregation import (
    GradingSpecRef,
    _validate_grading_spec_ref,
    _validate_identifier,
)
from grading.contracts.validation import validate_criterion_judgments
from grading.execution import GradingExecutionContext
from grading.rubric.models import QuestionRubricAuthoringContent


_RESPONSE_SCHEMA_VERSION = "1"


class DirectTextSemanticError(Exception):
    """Base class for expected DIRECT-text semantic-evaluation failures."""


class DirectTextSemanticUnsupportedInputError(DirectTextSemanticError):
    """The supplied question/evidence is outside the supported DIRECT-text slice."""


class DirectTextSemanticBindingError(DirectTextSemanticError):
    """Required execution, authority, evidence, or model-answer identities disagree."""


class DirectTextSemanticModelAnswerSourceExecutionError(DirectTextSemanticError):
    """The configured model-answer source failed during materialization."""


class DirectTextSemanticProviderExecutionError(DirectTextSemanticError):
    """The configured provider failed before an admissible response was returned."""


class DirectTextSemanticProviderResponseError(DirectTextSemanticError):
    """Provider bytes failed strict response admission."""


class MaterializedModelAnswer(Protocol):
    """Structural output of an already-admitted model-answer materialization source.

    Conformance does not authenticate the value. The evaluator cross-checks only
    deterministic bindings owned by this boundary.
    """

    grading_spec_ref: GradingSpecRef
    question_id: str
    content: str


class DirectTextModelAnswerSource(Protocol):
    """Composition-owned access seam for ACTIVE-authorized model-answer material."""

    def resolve_model_answer(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> MaterializedModelAnswer:
        ...


class DirectTextSemanticProvider(Protocol):
    """Composition-owned semantic provider returning untrusted raw response bytes."""

    def evaluate(self, *, request: "DirectTextSemanticRequest") -> bytes:
        ...


def _require_positive_exact_int(value: object, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise TypeError(f"{field_name} must be a positive exact int.")


def _require_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be a non-empty exact string without surrounding whitespace."
        )
    return value


@dataclass(frozen=True, slots=True)
class DirectTextSemanticLimits:
    """Composition-owned request/response resource limits with no implicit defaults."""

    max_model_answer_characters: int
    max_evidence_blocks: int
    max_evidence_characters: int
    max_total_request_characters: int
    max_raw_response_bytes: int
    max_json_depth: int
    max_json_nodes: int
    max_evidence_refs_per_judgment: int
    max_rationale_characters: int
    max_uncertainties_per_judgment: int
    max_uncertainty_characters: int

    def __post_init__(self) -> None:
        for field_name in (
            "max_model_answer_characters",
            "max_evidence_blocks",
            "max_evidence_characters",
            "max_total_request_characters",
            "max_raw_response_bytes",
            "max_json_depth",
            "max_json_nodes",
            "max_evidence_refs_per_judgment",
            "max_rationale_characters",
            "max_uncertainties_per_judgment",
            "max_uncertainty_characters",
        ):
            _require_positive_exact_int(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class DirectTextSemanticLevel:
    level_id: str
    operational_description: str


@dataclass(frozen=True, slots=True)
class DirectTextSemanticCriterion:
    criterion_id: str
    operational_description: str
    evidence_requirement: str
    performance_levels: tuple[DirectTextSemanticLevel, ...]
    accepted_equivalents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DirectTextSemanticEvidenceBlock:
    block_id: str
    content: str


@dataclass(frozen=True, slots=True)
class DirectTextSemanticRequest:
    """Narrow provider-facing semantic projection; contains no scoring machinery."""

    question_id: str
    question_text: str
    model_answer_text: str
    criteria: tuple[DirectTextSemanticCriterion, ...]
    evidence_blocks: tuple[DirectTextSemanticEvidenceBlock, ...]


@dataclass(frozen=True, slots=True)
class SemanticEvaluationResult:
    """Attempt-bound semantic result; not persistence/idempotency proof."""

    evaluation_attempt_id: str
    execution_context: GradingExecutionContext
    question_id: str
    judgments: tuple[EvaluatedCriterionJudgment, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.evaluation_attempt_id, "evaluation_attempt_id")
        if type(self.execution_context) is not GradingExecutionContext:
            raise TypeError(
                "SemanticEvaluationResult.execution_context must be an exact "
                "GradingExecutionContext."
            )
        _require_identifier(self.question_id, "question_id")
        if type(self.judgments) is not tuple or any(
            type(judgment) is not EvaluatedCriterionJudgment
            for judgment in self.judgments
        ):
            raise TypeError(
                "SemanticEvaluationResult.judgments must be a tuple of exact "
                "EvaluatedCriterionJudgment values."
            )


@dataclass(frozen=True, slots=True)
class _ProviderJudgmentPayload:
    criterion_id: str
    selected_level: str
    evidence_refs: tuple[str, ...]
    concise_rationale: str
    uncertainties: tuple[str, ...]


class _DuplicateKeyError(Exception):
    pass


class _NonStandardConstantError(Exception):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise _NonStandardConstantError(value)


def _require_exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise DirectTextSemanticProviderResponseError(
            f"{path} has missing or unknown fields."
        )


def _require_json_object(value: object, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DirectTextSemanticProviderResponseError(
            f"{path} must be a JSON object."
        )
    return value


def _require_json_array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise DirectTextSemanticProviderResponseError(
            f"{path} must be a JSON array."
        )
    return value


def _require_json_string(value: object, path: str) -> str:
    if type(value) is not str:
        raise DirectTextSemanticProviderResponseError(
            f"{path} must be a JSON string."
        )
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise DirectTextSemanticProviderResponseError(
            f"{path} contains an invalid Unicode surrogate code point."
        )
    return value


def _validate_json_resources(
    value: object,
    *,
    max_depth: int,
    max_nodes: int,
) -> None:
    """Bound parsed JSON structure deterministically after raw-byte admission.

    The raw byte ceiling is enforced before parsing. This traversal additionally
    rejects excessive nesting/node count without creating trusted domain values.
    """

    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise DirectTextSemanticProviderResponseError(
                "Provider response exceeds the JSON depth limit."
            )
        nodes += 1
        if nodes > max_nodes:
            raise DirectTextSemanticProviderResponseError(
                "Provider response exceeds the JSON node limit."
            )
        if type(current) is dict:
            stack.extend((child, depth + 1) for child in current.values())
        elif type(current) is list:
            stack.extend((child, depth + 1) for child in current)


def _decode_provider_response(
    raw_response: object,
    *,
    limits: DirectTextSemanticLimits,
) -> dict[str, Any]:
    if type(raw_response) is not bytes:
        raise DirectTextSemanticProviderResponseError(
            "semantic provider must return exact bytes."
        )
    if len(raw_response) > limits.max_raw_response_bytes:
        raise DirectTextSemanticProviderResponseError(
            "Provider response exceeds max_raw_response_bytes."
        )
    try:
        text = raw_response.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DirectTextSemanticProviderResponseError(
            "Provider response is not strict UTF-8."
        ) from exc

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except _DuplicateKeyError as exc:
        raise DirectTextSemanticProviderResponseError(
            "Provider response contains a duplicate JSON object key."
        ) from exc
    except _NonStandardConstantError as exc:
        raise DirectTextSemanticProviderResponseError(
            "Provider response contains a non-standard JSON constant."
        ) from exc
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise DirectTextSemanticProviderResponseError(
            "Provider response is not one valid JSON document."
        ) from exc

    _validate_json_resources(
        decoded,
        max_depth=limits.max_json_depth,
        max_nodes=limits.max_json_nodes,
    )
    return _require_json_object(decoded, "provider_response")


def _semantic_criteria(
    authority: ResolvedQuestionAuthority,
) -> tuple[DirectTextSemanticCriterion, ...]:
    rich_content = authority.rubric_content
    scoring_authority = authority.scoring_authority
    if type(rich_content) is not QuestionRubricAuthoringContent:
        raise DirectTextSemanticBindingError(
            "authority.rubric_content must be an exact QuestionRubricAuthoringContent."
        )
    if type(scoring_authority) is not QuestionScoringAuthority:
        raise DirectTextSemanticBindingError(
            "authority.scoring_authority must be an exact QuestionScoringAuthority."
        )

    scoring_ids = tuple(
        criterion.criterion_id for criterion in scoring_authority.rubric.criteria
    )
    rich_ids = tuple(criterion.criterion_id for criterion in rich_content.criteria)
    if rich_ids != scoring_ids:
        raise DirectTextSemanticBindingError(
            "Rich rubric criterion order/identity does not match scoring authority."
        )

    projected: list[DirectTextSemanticCriterion] = []
    for rich, scoring in zip(rich_content.criteria, scoring_authority.rubric.criteria):
        rich_level_ids = tuple(level.level_id for level in rich.performance_levels)
        scoring_level_ids = tuple(level.level_id for level in scoring.performance_levels)
        if rich_level_ids != scoring_level_ids:
            raise DirectTextSemanticBindingError(
                f"Rich rubric levels do not match scoring authority for {rich.criterion_id!r}."
            )
        projected.append(
            DirectTextSemanticCriterion(
                criterion_id=rich.criterion_id,
                operational_description=rich.operational_description,
                evidence_requirement=rich.evidence_requirement,
                performance_levels=tuple(
                    DirectTextSemanticLevel(
                        level_id=level.level_id,
                        operational_description=level.operational_description,
                    )
                    for level in rich.performance_levels
                ),
                accepted_equivalents=rich.accepted_equivalents,
            )
        )
    return tuple(projected)


def _semantic_request_character_count(request: DirectTextSemanticRequest) -> int:
    total = len(request.question_id) + len(request.question_text) + len(
        request.model_answer_text
    )
    for criterion in request.criteria:
        total += len(criterion.criterion_id)
        total += len(criterion.operational_description)
        total += len(criterion.evidence_requirement)
        total += sum(len(value) for value in criterion.accepted_equivalents)
        for level in criterion.performance_levels:
            total += len(level.level_id)
            total += len(level.operational_description)
    for block in request.evidence_blocks:
        total += len(block.block_id) + len(block.content)
    return total


def _admit_provider_payloads(
    *,
    decoded: dict[str, Any],
    authority: ResolvedQuestionAuthority,
    visible_evidence_ids: frozenset[str],
    limits: DirectTextSemanticLimits,
) -> tuple[_ProviderJudgmentPayload, ...]:
    _require_exact_keys(decoded, {"schema_version", "judgments"}, "provider_response")
    schema_version = _require_json_string(
        decoded["schema_version"], "provider_response.schema_version"
    )
    if schema_version != _RESPONSE_SCHEMA_VERSION:
        raise DirectTextSemanticProviderResponseError(
            "Unsupported semantic provider response schema_version."
        )

    items = _require_json_array(decoded["judgments"], "provider_response.judgments")
    max_expected = len(authority.scoring_authority.rubric.criteria)
    if len(items) > max_expected:
        raise DirectTextSemanticProviderResponseError(
            "Provider returned more judgments than the authoritative criterion universe."
        )

    candidates: list[CriterionJudgment] = []
    payload_by_id: dict[str, _ProviderJudgmentPayload] = {}
    seen_ids: set[str] = set()

    for index, item in enumerate(items):
        path = f"provider_response.judgments[{index}]"
        obj = _require_json_object(item, path)
        _require_exact_keys(
            obj,
            {
                "criterion_id",
                "selected_level",
                "evidence_refs",
                "concise_rationale",
                "uncertainties",
            },
            path,
        )
        criterion_id = _require_json_string(obj["criterion_id"], f"{path}.criterion_id")
        selected_level = _require_json_string(
            obj["selected_level"], f"{path}.selected_level"
        )
        if criterion_id in seen_ids:
            raise DirectTextSemanticProviderResponseError(
                f"Provider response contains duplicate criterion_id {criterion_id!r}."
            )
        seen_ids.add(criterion_id)

        refs_raw = _require_json_array(obj["evidence_refs"], f"{path}.evidence_refs")
        if not refs_raw:
            raise DirectTextSemanticProviderResponseError(
                f"{path}.evidence_refs must be non-empty."
            )
        if len(refs_raw) > limits.max_evidence_refs_per_judgment:
            raise DirectTextSemanticProviderResponseError(
                f"{path}.evidence_refs exceeds the configured limit."
            )
        refs: list[str] = []
        seen_refs: set[str] = set()
        for ref_index, raw_ref in enumerate(refs_raw):
            evidence_ref = _require_json_string(
                raw_ref, f"{path}.evidence_refs[{ref_index}]"
            )
            if evidence_ref in seen_refs:
                raise DirectTextSemanticProviderResponseError(
                    f"{path}.evidence_refs contains a duplicate reference."
                )
            seen_refs.add(evidence_ref)
            if evidence_ref not in visible_evidence_ids:
                raise DirectTextSemanticProviderResponseError(
                    f"{path}.evidence_refs references evidence not visible to the provider."
                )
            refs.append(evidence_ref)

        rationale = _require_json_string(
            obj["concise_rationale"], f"{path}.concise_rationale"
        )
        if len(rationale) > limits.max_rationale_characters:
            raise DirectTextSemanticProviderResponseError(
                f"{path}.concise_rationale exceeds the configured limit."
            )

        uncertainties_raw = _require_json_array(
            obj["uncertainties"], f"{path}.uncertainties"
        )
        if len(uncertainties_raw) > limits.max_uncertainties_per_judgment:
            raise DirectTextSemanticProviderResponseError(
                f"{path}.uncertainties exceeds the configured limit."
            )
        uncertainties: list[str] = []
        for uncertainty_index, raw_uncertainty in enumerate(uncertainties_raw):
            uncertainty = _require_json_string(
                raw_uncertainty,
                f"{path}.uncertainties[{uncertainty_index}]",
            )
            if not uncertainty.strip():
                raise DirectTextSemanticProviderResponseError(
                    f"{path}.uncertainties entries must contain non-whitespace text."
                )
            if len(uncertainty) > limits.max_uncertainty_characters:
                raise DirectTextSemanticProviderResponseError(
                    f"{path}.uncertainties entry exceeds the configured limit."
                )
            uncertainties.append(uncertainty)

        try:
            candidate = CriterionJudgment(
                criterion_id=criterion_id,
                selected_level=selected_level,
            )
        except InvalidCriterionJudgmentError as exc:
            raise DirectTextSemanticProviderResponseError(
                f"{path} contains an invalid criterion/level identifier."
            ) from exc

        payload = _ProviderJudgmentPayload(
            criterion_id=criterion_id,
            selected_level=selected_level,
            evidence_refs=tuple(refs),
            concise_rationale=rationale,
            uncertainties=tuple(uncertainties),
        )
        candidates.append(candidate)
        payload_by_id[criterion_id] = payload

    try:
        canonical = validate_criterion_judgments(
            authority.scoring_authority,
            tuple(candidates),
        )
    except InvalidCriterionJudgmentError as exc:
        raise DirectTextSemanticProviderResponseError(
            "Provider criterion selections do not match the authoritative rubric."
        ) from exc

    # Canonicalize rich provider fields by admitted criterion identity, never by
    # response position. Duplicate IDs were rejected before this mapping existed.
    return tuple(payload_by_id[judgment.criterion_id] for judgment in canonical)


@dataclass(frozen=True, slots=True, init=False)
class DirectTextSemanticEvaluator:
    """DIRECT-only semantic evaluator with immutable composition-owned dependencies."""

    _model_answer_source: DirectTextModelAnswerSource
    _provider: DirectTextSemanticProvider
    _limits: DirectTextSemanticLimits
    _evaluator_metadata: EvaluatorMetadata

    def __init__(
        self,
        *,
        model_answer_source: DirectTextModelAnswerSource,
        provider: DirectTextSemanticProvider,
        limits: DirectTextSemanticLimits,
        evaluator_metadata: EvaluatorMetadata,
    ) -> None:
        if not callable(getattr(model_answer_source, "resolve_model_answer", None)):
            raise TypeError(
                "model_answer_source must provide resolve_model_answer(...)."
            )
        if not callable(getattr(provider, "evaluate", None)):
            raise TypeError("provider must provide evaluate(...).")
        if type(limits) is not DirectTextSemanticLimits:
            raise TypeError("limits must be an exact DirectTextSemanticLimits.")
        if type(evaluator_metadata) is not EvaluatorMetadata:
            raise TypeError("evaluator_metadata must be an exact EvaluatorMetadata.")
        object.__setattr__(self, "_model_answer_source", model_answer_source)
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_limits", limits)
        object.__setattr__(self, "_evaluator_metadata", evaluator_metadata)

    def evaluate(
        self,
        *,
        authority: ResolvedQuestionAuthority,
        evidence: AnswerEvidenceBundle,
        execution_context: GradingExecutionContext,
        evaluation_attempt_id: str,
    ) -> SemanticEvaluationResult:
        if type(authority) is not ResolvedQuestionAuthority:
            raise TypeError("authority must be an exact ResolvedQuestionAuthority.")
        if type(evidence) is not AnswerEvidenceBundle:
            raise TypeError("evidence must be an exact AnswerEvidenceBundle.")
        if type(execution_context) is not GradingExecutionContext:
            raise TypeError(
                "execution_context must be an exact GradingExecutionContext."
            )
        try:
            _require_identifier(evaluation_attempt_id, "evaluation_attempt_id")
        except (TypeError, ValueError) as exc:
            raise DirectTextSemanticBindingError(
                "evaluation_attempt_id must be a non-empty exact string without surrounding whitespace."
            ) from exc

        try:
            _validate_grading_spec_ref(
                authority.grading_spec_ref,
                field_name="authority.grading_spec_ref",
                error_type=DirectTextSemanticBindingError,
            )
            _validate_identifier(
                authority.question_id,
                field_name="authority.question_id",
                error_type=DirectTextSemanticBindingError,
            )
        except DirectTextSemanticBindingError:
            raise

        if execution_context.grading_spec_ref != authority.grading_spec_ref:
            raise DirectTextSemanticBindingError(
                "execution_context.grading_spec_ref must match authority.grading_spec_ref."
            )
        if execution_context.submission_ref != evidence.submission_ref:
            raise DirectTextSemanticBindingError(
                "execution_context.submission_ref must match evidence.submission_ref."
            )
        if authority.context_policy is not ContextPolicy.DIRECT:
            raise DirectTextSemanticUnsupportedInputError(
                "DIRECT text semantic evaluation requires ContextPolicy.DIRECT."
            )
        if type(authority.question_text) is not str or not authority.question_text.strip():
            raise DirectTextSemanticUnsupportedInputError(
                "DIRECT text semantic evaluation requires non-whitespace question text."
            )

        matching_questions = tuple(
            question
            for question in evidence.questions
            if question.question_id == authority.question_id
        )
        if len(matching_questions) != 1:
            raise DirectTextSemanticBindingError(
                "Evidence bundle must contain exactly one matching question."
            )
        question_evidence = matching_questions[0]

        visible_blocks: list[DirectTextSemanticEvidenceBlock] = []
        evidence_characters = 0
        has_nonblank_evidence = False
        for block in question_evidence.blocks:
            if block.state is EvidenceBlockState.CROSSED_OUT:
                continue
            if block.state is EvidenceBlockState.UNCERTAIN:
                raise DirectTextSemanticUnsupportedInputError(
                    "UNCERTAIN evidence is unsupported by the DIRECT text v1 capability."
                )
            if block.state is not EvidenceBlockState.ACTIVE:
                raise DirectTextSemanticUnsupportedInputError(
                    "Evidence block has an unsupported state."
                )
            if block.type is not EvidenceBlockType.TEXT:
                raise DirectTextSemanticUnsupportedInputError(
                    "ACTIVE non-TEXT evidence is unsupported by the DIRECT text v1 capability."
                )
            if len(visible_blocks) >= self._limits.max_evidence_blocks:
                raise DirectTextSemanticUnsupportedInputError(
                    "Provider-visible evidence exceeds max_evidence_blocks."
                )
            evidence_characters += len(block.content)
            if evidence_characters > self._limits.max_evidence_characters:
                raise DirectTextSemanticUnsupportedInputError(
                    "Provider-visible evidence exceeds max_evidence_characters."
                )
            if block.content.strip():
                has_nonblank_evidence = True
            visible_blocks.append(
                DirectTextSemanticEvidenceBlock(
                    block_id=block.block_id,
                    content=block.content,
                )
            )

        if not visible_blocks or not has_nonblank_evidence:
            raise DirectTextSemanticUnsupportedInputError(
                "DIRECT text evaluation requires at least one non-whitespace ACTIVE TEXT block."
            )

        semantic_criteria = _semantic_criteria(authority)

        pre_materialization_request = DirectTextSemanticRequest(
            question_id=authority.question_id,
            question_text=authority.question_text,
            model_answer_text="",
            criteria=semantic_criteria,
            evidence_blocks=tuple(visible_blocks),
        )
        if (
            _semantic_request_character_count(pre_materialization_request)
            > self._limits.max_total_request_characters
        ):
            raise DirectTextSemanticUnsupportedInputError(
                "Semantic request exceeds max_total_request_characters before model-answer materialization."
            )

        # Resolve model-answer material only after cheap deterministic capability
        # and binding checks have succeeded. No fallback/source search exists here.
        try:
            materialized = self._model_answer_source.resolve_model_answer(
                grading_spec_ref=authority.grading_spec_ref,
                question_id=authority.question_id,
            )
        except Exception as exc:
            raise DirectTextSemanticModelAnswerSourceExecutionError(
                "Model-answer source execution failed."
            ) from exc
        try:
            materialized_spec_ref = materialized.grading_spec_ref
            materialized_question_id = materialized.question_id
            model_answer_text = materialized.content
        except AttributeError as exc:
            raise DirectTextSemanticBindingError(
                "model-answer source returned an invalid materialized answer."
            ) from exc
        except Exception as exc:
            raise DirectTextSemanticModelAnswerSourceExecutionError(
                "Model-answer materialization failed during field access."
            ) from exc

        _validate_grading_spec_ref(
            materialized_spec_ref,
            field_name="model_answer.grading_spec_ref",
            error_type=DirectTextSemanticBindingError,
        )
        validated_model_question_id = _validate_identifier(
            materialized_question_id,
            field_name="model_answer.question_id",
            error_type=DirectTextSemanticBindingError,
        )
        if materialized_spec_ref != authority.grading_spec_ref:
            raise DirectTextSemanticBindingError(
                "Materialized model answer is bound to a different grading spec."
            )
        if validated_model_question_id != authority.question_id:
            raise DirectTextSemanticBindingError(
                "Materialized model answer is bound to a different question."
            )
        if type(model_answer_text) is not str or not model_answer_text.strip():
            raise DirectTextSemanticUnsupportedInputError(
                "DIRECT text evaluation requires non-whitespace model-answer text."
            )
        if len(model_answer_text) > self._limits.max_model_answer_characters:
            raise DirectTextSemanticUnsupportedInputError(
                "Model-answer text exceeds max_model_answer_characters."
            )

        request = DirectTextSemanticRequest(
            question_id=authority.question_id,
            question_text=authority.question_text,
            model_answer_text=model_answer_text,
            criteria=semantic_criteria,
            evidence_blocks=tuple(visible_blocks),
        )
        if _semantic_request_character_count(request) > self._limits.max_total_request_characters:
            raise DirectTextSemanticUnsupportedInputError(
                "Semantic request exceeds max_total_request_characters."
            )

        try:
            raw_response = self._provider.evaluate(request=request)
        except Exception as exc:
            raise DirectTextSemanticProviderExecutionError(
                "Semantic provider execution failed."
            ) from exc

        decoded = _decode_provider_response(raw_response, limits=self._limits)
        canonical_payloads = _admit_provider_payloads(
            decoded=decoded,
            authority=authority,
            visible_evidence_ids=frozenset(block.block_id for block in visible_blocks),
            limits=self._limits,
        )

        judgments = tuple(
            EvaluatedCriterionJudgment(
                criterion_id=payload.criterion_id,
                selected_level=payload.selected_level,
                evidence_refs=payload.evidence_refs,
                reason_codes=(),
                concise_rationale=payload.concise_rationale,
                uncertainties=payload.uncertainties,
                evaluator_metadata=self._evaluator_metadata,
            )
            for payload in canonical_payloads
        )

        return SemanticEvaluationResult(
            evaluation_attempt_id=evaluation_attempt_id,
            execution_context=execution_context,
            question_id=authority.question_id,
            judgments=judgments,
        )
