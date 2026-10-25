from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, fields, replace
import importlib
import inspect
import json
from types import (
    BuiltinFunctionType,
    FunctionType,
    GetSetDescriptorType,
    MemberDescriptorType,
    MethodDescriptorType,
    ModuleType,
)

import pytest

from grading.active_question_authority import (
    ContextPolicy,
    ResolvedQuestionAuthority,
    resolve_active_question_authority,
)
from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.evidence import (
    EvidenceBlockState,
    EvidenceBlockType,
    EvidenceConfidenceStatus,
    EvidenceLocationStatus,
)
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult,
    GradingSpecRef,
    ResolvedPaperScoringAuthority,
)
from grading.contracts.policy import SCORING_SEMANTICS_V1
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import GradingExecutionContext
from grading.integration.evidence_ingress import (
    AdmittedNormalizedEvidence,
    NormalizedEvidenceAdmissionPolicy,
    parse_normalized_evidence_payload,
)
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    activate_version,
    approve_version,
    create_initial_version,
    revise_version,
    validate_version,
)
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterion,
    AuthoringCriterionCondition,
    AuthoringDeductionRule,
    AuthoringGateRule,
    AuthoringPerformanceLevel,
    AuthoringPositiveCreditDependencyRule,
    AuthoringRoundingRule,
    QuestionRubricAuthoringContent,
)
from tests.support.rubric_authoring import (
    authoring_test_limits,
    simple_basis,
    simple_content,
)


MODULE_NAME = "grading.integration.evaluation_binding"

_STUDENT_SENTINEL = "P0B_PRIVATE_STUDENT_ANSWER_7F31"
_QUESTION_SENTINEL = "P0B_CONFIDENTIAL_QUESTION_4D92"
_RUBRIC_SENTINEL = "P0B_PRIVATE_RUBRIC_DESCRIPTION_B8A6"
_RUBRIC_EVIDENCE_SENTINEL = "P0B_PRIVATE_RUBRIC_EVIDENCE_63D1"
_RUBRIC_LEVEL_SENTINEL = "P0B_PRIVATE_RUBRIC_LEVEL_27A4"
_RUBRIC_LEVEL_NOT_MET_SENTINEL = "P0B_PRIVATE_RUBRIC_LEVEL_NOT_MET_71B2"
_RUBRIC_SECOND_SENTINEL = "P0B_PRIVATE_RUBRIC_SECOND_418C"
_RUBRIC_SECOND_EVIDENCE_SENTINEL = "P0B_PRIVATE_RUBRIC_SECOND_EVIDENCE_7B3F"
_RUBRIC_SECOND_LEVEL_FULL_SENTINEL = "P0B_PRIVATE_RUBRIC_LEVEL_SECOND_FULL_53C8"
_RUBRIC_SECOND_LEVEL_NOT_MET_SENTINEL = "P0B_PRIVATE_RUBRIC_LEVEL_SECOND_NOT_MET_A143"
_RUBRIC_EQUIVALENT_SENTINEL = "P0B_PRIVATE_ACCEPTED_EQUIVALENT_D6E2"
_RUBRIC_SECOND_EQUIVALENT_SENTINEL = "P0B_PRIVATE_ACCEPTED_EQUIVALENT_SECOND_29E5"
_LEVEL_SCORE_ONE_SENTINEL = "2.113"
_LEVEL_SCORE_TWO_SENTINEL = "2.887"
_SCORING_MIN_SENTINEL = "913.271"
_SCORING_MAX_SENTINEL = "927.441"
_GATE_SCORE_SENTINEL = "4.321"
_CAP_SCORE_SENTINEL = "4.654"
_DEDUCTION_SCORE_SENTINEL = "0.271"
_ROUNDING_SCORE_SENTINEL = "0.125"
_FOREIGN_SENTINEL = "P0B_PRIVATE_FOREIGN_NESTED_91C4"

_PRIVACY_SENTINELS = (
    _STUDENT_SENTINEL,
    _QUESTION_SENTINEL,
    _RUBRIC_SENTINEL,
    _RUBRIC_EVIDENCE_SENTINEL,
    _RUBRIC_LEVEL_SENTINEL,
    _RUBRIC_LEVEL_NOT_MET_SENTINEL,
    _RUBRIC_SECOND_SENTINEL,
    _RUBRIC_SECOND_EVIDENCE_SENTINEL,
    _RUBRIC_SECOND_LEVEL_FULL_SENTINEL,
    _RUBRIC_SECOND_LEVEL_NOT_MET_SENTINEL,
    _RUBRIC_EQUIVALENT_SENTINEL,
    _RUBRIC_SECOND_EQUIVALENT_SENTINEL,
    _LEVEL_SCORE_ONE_SENTINEL,
    _LEVEL_SCORE_TWO_SENTINEL,
    _SCORING_MIN_SENTINEL,
    _SCORING_MAX_SENTINEL,
    _GATE_SCORE_SENTINEL,
    _CAP_SCORE_SENTINEL,
    _DEDUCTION_SCORE_SENTINEL,
    _ROUNDING_SCORE_SENTINEL,
    _FOREIGN_SENTINEL,
)
_DIAGNOSTIC_MAX_DEPTH = 8
_DIAGNOSTIC_MAX_ITEMS = 256
_SAFE_DIAGNOSTIC_CONTAINER_TYPES = (tuple, list, dict, set, frozenset)

_ALLOWED_BOUND_PUBLIC_DATA_NAMES = frozenset(
    {
        "context",
        "admitted_evidence",
        "paper_authority",
        "question_authority",
    }
)


@dataclass(frozen=True, slots=True)
class _StaticPublicSurface:
    ordinary_data_names: frozenset[str]
    opaque_descriptor_names: frozenset[str]


def _type_has_descriptor_protocol(value: object) -> bool:
    """Inspect descriptor metadata without invoking application behavior."""

    value_type = type(value)
    for base in type.__getattribute__(value_type, "__mro__"):
        namespace = type.__getattribute__(base, "__dict__")
        if any(name in namespace for name in ("__get__", "__set__", "__delete__")):
            return True
    return False


def _ordinary_instance_storage(value: object) -> dict[str, object] | None:
    """Return ordinary instance-dict storage only when its descriptor is built-in."""

    value_type = type(value)
    for base in type.__getattribute__(value_type, "__mro__"):
        namespace = type.__getattribute__(base, "__dict__")
        if "__dict__" not in namespace:
            continue
        descriptor = namespace["__dict__"]
        if type(descriptor) is not GetSetDescriptorType:
            return None
        try:
            storage = object.__getattribute__(value, "__dict__")
        except AttributeError:
            return None
        return storage if type(storage) is dict else None
    return None


def _classify_static_public_surface(value: object) -> _StaticPublicSurface:
    """Classify only ordinary statically observable public data surfaces.

    The helper deliberately bypasses user-defined attribute discovery and never
    invokes properties or arbitrary descriptors. Unknown descriptor mechanisms
    are returned as explicit source-review debt rather than treated as safe.
    """

    value_type = type(value)
    namespace = type.__getattribute__(value_type, "__dict__")
    ordinary_data_names: set[str] = set()
    opaque_descriptor_names: set[str] = set()

    method_storage_types = (
        FunctionType,
        BuiltinFunctionType,
        MethodDescriptorType,
        staticmethod,
        classmethod,
    )
    ordinary_descriptor_types = (
        property,
        MemberDescriptorType,
        GetSetDescriptorType,
    )

    for name, stored in namespace.items():
        if not isinstance(name, str) or name.startswith("_"):
            continue

        stored_type = type(stored)
        if stored_type in method_storage_types or isinstance(stored, type):
            continue
        if stored_type in ordinary_descriptor_types:
            ordinary_data_names.add(name)
            continue
        if _type_has_descriptor_protocol(stored):
            opaque_descriptor_names.add(name)
            continue

        # Plain public class storage is data even when someone labels it a
        # "constant". It is therefore inside the v1 four-name data contract.
        ordinary_data_names.add(name)

    storage = _ordinary_instance_storage(value)
    if storage is not None:
        ordinary_data_names.update(
            name
            for name in storage
            if isinstance(name, str) and not name.startswith("_")
        )

    return _StaticPublicSurface(
        ordinary_data_names=frozenset(ordinary_data_names),
        opaque_descriptor_names=frozenset(opaque_descriptor_names),
    )


class _DiagnosticTraversalExhausted(AssertionError):
    pass


def _assert_diagnostic_value_safe(
    value: object,
    *,
    protected_objects: tuple[object, ...] = (),
    confidential_sentinels: tuple[str, ...] = _PRIVACY_SENTINELS,
    max_depth: int = _DIAGNOSTIC_MAX_DEPTH,
    max_items: int = _DIAGNOSTIC_MAX_ITEMS,
) -> None:
    if type(max_depth) is not int or max_depth < 0:
        raise ValueError("max_depth must be a non-negative exact int")
    if type(max_items) is not int or max_items < 0:
        raise ValueError("max_items must be a non-negative exact int")

    visited: set[int] = set()
    remaining_items = [max_items]

    def walk(current: object, depth_remaining: int) -> None:
        if any(current is protected for protected in protected_objects):
            raise AssertionError("diagnostic state retained a protected domain object")

        if type(current) is str:
            for sentinel in confidential_sentinels:
                if sentinel in current:
                    raise AssertionError(
                        f"diagnostic state exposed confidential sentinel {sentinel!r}"
                    )
            return

        if type(current) is bytes:
            for sentinel in confidential_sentinels:
                if sentinel.encode("utf-8") in current:
                    raise AssertionError(
                        f"diagnostic state exposed encoded confidential sentinel {sentinel!r}"
                    )
            return

        if type(current) is bytearray:
            for sentinel in confidential_sentinels:
                if sentinel.encode("utf-8") in current:
                    raise AssertionError(
                        f"diagnostic state exposed encoded confidential sentinel {sentinel!r}"
                    )
            return

        current_type = type(current)
        if current_type not in _SAFE_DIAGNOSTIC_CONTAINER_TYPES:
            return

        current_id = id(current)
        if current_id in visited:
            return
        # Register cycles before any attempted descent.
        visited.add(current_id)

        if current_type is dict:
            child_count = 2 * len(current)
        else:
            child_count = len(current)

        if child_count == 0:
            return
        if depth_remaining == 0:
            raise _DiagnosticTraversalExhausted(
                "diagnostic traversal depth budget exhausted"
            )
        if child_count > remaining_items[0]:
            raise _DiagnosticTraversalExhausted(
                "diagnostic traversal item budget exhausted"
            )
        remaining_items[0] -= child_count

        if current_type is dict:
            for key, nested in current.items():
                walk(key, depth_remaining - 1)
                walk(nested, depth_remaining - 1)
            return

        for nested in current:
            walk(nested, depth_remaining - 1)

    walk(value, max_depth)


def _assert_expected_rejection_diagnostics_are_private(
    exc: BaseException,
    *,
    protected_objects: tuple[object, ...],
    confidential_sentinels: tuple[str, ...] = _PRIVACY_SENTINELS,
) -> None:
    # Public exception text/representation are themselves diagnostic surfaces.
    for rendered in (str(exc), repr(exc)):
        for sentinel in confidential_sentinels:
            assert sentinel not in rendered

    _assert_diagnostic_value_safe(
        exc.args,
        protected_objects=protected_objects,
        confidential_sentinels=confidential_sentinels,
    )
    _assert_diagnostic_value_safe(
        getattr(exc, "__notes__", ()),
        protected_objects=protected_objects,
        confidential_sentinels=confidential_sentinels,
    )
    try:
        custom_state = vars(exc)
    except TypeError:
        custom_state = {}
    _assert_diagnostic_value_safe(
        custom_state,
        protected_objects=protected_objects,
        confidential_sentinels=confidential_sentinels,
    )
    assert exc.__cause__ is None
    assert exc.__context__ is None


def _api() -> ModuleType:
    try:
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME:
            pytest.fail(
                "The one-question pre-evaluation binding boundary "
                "is absent; expected grading.integration.evaluation_binding",
                pytrace=False,
            )
        raise


def _policy(
    *,
    admission_policy_identity: str = "p0b-red-p0a-policy-v1",
    **overrides: int,
) -> NormalizedEvidenceAdmissionPolicy:
    values: dict[str, object] = {
        "admission_policy_identity": admission_policy_identity,
        "max_raw_bytes": 100_000,
        "max_json_depth": 32,
        "max_json_nodes": 10_000,
        "max_json_number_characters": 128,
        "max_identifier_characters": 256,
        "max_metadata_text_characters": 2_048,
        "max_block_content_characters": 8_192,
        "max_total_content_characters": 65_536,
        "max_questions": 100,
        "max_blocks_per_question": 200,
        "max_total_blocks": 5_000,
        "max_warnings_per_question": 100,
        "max_location_coordinates": 16,
    }
    values.update(overrides)
    return NormalizedEvidenceAdmissionPolicy(**values)  # type: ignore[arg-type]


def _wire_block(
    *,
    block_id: str = "Q1-B1",
    block_type: str = "TEXT",
    content: str = "Student answer for the bound question.",
    language: str | None = "en",
    confidence: int | float | None = None,
    confidence_status: str = "UNAVAILABLE",
    state: str = "ACTIVE",
    page: int = 1,
    location_status: str = "UNAVAILABLE",
    bbox: list[int | float] | None = None,
    reading_order: int = 1,
    asset_ref: str | None = None,
) -> dict[str, object]:
    return {
        "block_id": block_id,
        "type": block_type,
        "content": content,
        "language": language,
        "confidence": confidence,
        "confidence_status": confidence_status,
        "state": state,
        "page": page,
        "location": {"status": location_status, "bbox": bbox},
        "reading_order": reading_order,
        "asset_ref": asset_ref,
    }


def _wire_question(
    question_id: str,
    *,
    content: str = "Student answer for the bound question.",
    with_block: bool = True,
    state: str = "ACTIVE",
    block_id: str | None = None,
    block_type: str = "TEXT",
    language: str | None = "en",
    confidence: int | float | None = None,
    confidence_status: str = "UNAVAILABLE",
    page: int = 1,
    location_status: str = "UNAVAILABLE",
    bbox: list[int | float] | None = None,
    reading_order: int = 1,
    asset_ref: str | None = None,
    answer_scope_ref: str | None = None,
    warnings: tuple[str, ...] = (),
    extra_blocks: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    blocks: list[dict[str, object]] = []
    if with_block:
        blocks.append(
            _wire_block(
                block_id=block_id or f"{question_id}-B1",
                block_type=block_type,
                content=content,
                language=language,
                confidence=confidence,
                confidence_status=confidence_status,
                state=state,
                page=page,
                location_status=location_status,
                bbox=bbox,
                reading_order=reading_order,
                asset_ref=asset_ref,
            )
        )
    blocks.extend(extra_blocks)
    return {
        "question_id": question_id,
        "answer_scope_ref": answer_scope_ref or f"scope-{question_id}",
        "blocks": blocks,
        "warnings": list(warnings),
    }


def _admit_questions(
    questions: list[dict[str, object]],
    *,
    submission_ref: str = "SUB-P0B-1",
    ocr_provenance: str = "ocr-p0b-red-1",
    policy: NormalizedEvidenceAdmissionPolicy | None = None,
    source_artifact_ref: str | None = "artifact://p0b-red/scan-1",
) -> AdmittedNormalizedEvidence:
    effective_policy = _policy() if policy is None else policy
    raw = json.dumps(
        {
            "schema_version": "1",
            "submission_ref": submission_ref,
            "ocr_provenance": ocr_provenance,
            "questions": questions,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return parse_normalized_evidence_payload(
        raw_payload=raw,
        policy=effective_policy,
        source_artifact_ref=source_artifact_ref,
    )


def _admitted_evidence(
    *question_ids: str,
    submission_ref: str = "SUB-P0B-1",
    zero_blocks_for: frozenset[str] = frozenset(),
    student_secret: str | None = None,
    first_content_override: str | None = None,
    first_state: str = "ACTIVE",
    policy: NormalizedEvidenceAdmissionPolicy | None = None,
    source_artifact_ref: str | None = "artifact://p0b-red/scan-1",
    ocr_provenance: str = "ocr-p0b-red-1",
) -> AdmittedNormalizedEvidence:
    questions = []
    for question_id in question_ids:
        if question_id == question_ids[0] and first_content_override is not None:
            content = first_content_override
        elif question_id == question_ids[0] and student_secret is not None:
            content = student_secret
        else:
            content = f"Student answer for {question_id}."
        questions.append(
            _wire_question(
                question_id,
                content=content,
                with_block=question_id not in zero_blocks_for,
                state=first_state if question_id == question_ids[0] else "ACTIVE",
            )
        )
    return _admit_questions(
        questions,
        submission_ref=submission_ref,
        ocr_provenance=ocr_provenance,
        policy=policy,
        source_artifact_ref=source_artifact_ref,
    )


def _admitted_single_question(
    *,
    question_id: str = "Q1",
    submission_ref: str = "SUB-P0B-1",
    ocr_provenance: str = "ocr-p0b-red-1",
    policy: NormalizedEvidenceAdmissionPolicy | None = None,
    source_artifact_ref: str | None = "artifact://p0b-red/scan-1",
    **question_kwargs: object,
) -> AdmittedNormalizedEvidence:
    return _admit_questions(
        [_wire_question(question_id, **question_kwargs)],
        submission_ref=submission_ref,
        ocr_provenance=ocr_provenance,
        policy=policy,
        source_artifact_ref=source_artifact_ref,
    )


def _content(
    *,
    rubric_id: str = "R-Q1",
    policy_id: str = "P-Q1",
    rubric_secret: str | None = None,
) -> QuestionRubricAuthoringContent:
    content = replace(
        simple_content(),
        rubric_id=rubric_id,
        policy_id=policy_id,
    )
    if rubric_secret is None:
        return content
    first = replace(
        content.criteria[0],
        operational_description=rubric_secret,
    )
    return replace(content, criteria=(first, *content.criteria[1:]))


def _active_rubric(
    *,
    question_id: str = "Q1",
    rubric_id: str = "R-Q1",
    policy_id: str = "P-Q1",
    rubric_secret: str | None = None,
    version: int = 1,
) -> RubricAuthoringVersion:
    if type(version) is not int or version <= 0:
        raise ValueError("test rubric version must be a positive exact integer")

    draft = create_initial_version(
        simple_basis(question_id=question_id),
        _content(
            rubric_id=rubric_id,
            policy_id=policy_id,
            rubric_secret=rubric_secret,
        ),
    )
    current = activate_version(
        approve_version(
            validate_version(draft, limits=authoring_test_limits()),
            teacher_ref="teacher-p0b-red-v1",
        ),
        limits=authoring_test_limits(),
    )
    while current.version < version:
        first = current.content.criteria[0]
        revised_content = replace(
            current.content,
            criteria=(
                replace(
                    first,
                    operational_description=(
                        first.operational_description
                        + f" revision-{current.version + 1}"
                    ),
                ),
                *current.content.criteria[1:],
            ),
        )
        revised = revise_version(
            current,
            current.finalized_question,
            revised_content,
        )
        current = activate_version(
            approve_version(
                validate_version(revised, limits=authoring_test_limits()),
                teacher_ref=f"teacher-p0b-red-v{revised.version}",
            ),
            limits=authoring_test_limits(),
        )
    return current


def _expected(
    question_id: str,
    *,
    rubric_id: str = "R-Q1",
    rubric_version: int = 1,
    policy_id: str = "P-Q1",
    policy_version: int = 1,
) -> ExpectedQuestionResult:
    return ExpectedQuestionResult(
        question_id=question_id,
        rubric_ref=RubricRef(id=rubric_id, version=rubric_version),
        scoring_policy_ref=ScoringPolicyRef(
            id=policy_id,
            version=policy_version,
            scoring_semantics_version=SCORING_SEMANTICS_V1,
        ),
    )


def _paper(
    *,
    spec_id: str = "SPEC-P0B",
    spec_version: int = 1,
    expected_questions: tuple[ExpectedQuestionResult, ...] | None = None,
    minimum_score: str = "0",
    maximum_score: str | None = None,
) -> ResolvedPaperScoringAuthority:
    effective_expected = expected_questions or (_expected("Q1"),)
    effective_maximum = (
        str(5 * len(effective_expected)) if maximum_score is None else maximum_score
    )
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef(id=spec_id, version=spec_version),
        expected_questions=effective_expected,
        minimum_score=ScoringDecimal.from_raw(minimum_score),
        maximum_score=ScoringDecimal.from_raw(effective_maximum),
    )


@dataclass(frozen=True, slots=True)
class _Selection:
    grading_spec_ref: object
    question_id: object
    question_text: object
    context_policy: object
    active_rubric: object


class _Source:
    def __init__(self, selection: _Selection) -> None:
        self.selection = selection

    def resolve_active_question(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> object:
        del grading_spec_ref, question_id
        return self.selection


def _question_authority(
    paper: ResolvedPaperScoringAuthority,
    *,
    question_id: str = "Q1",
    context_policy: ContextPolicy = ContextPolicy.DIRECT,
    question_text: str = "Explain the result.",
    rubric_id: str = "R-Q1",
    policy_id: str = "P-Q1",
    rubric_secret: str | None = None,
    rubric_version: int = 1,
) -> ResolvedQuestionAuthority:
    active = _active_rubric(
        question_id=question_id,
        rubric_id=rubric_id,
        policy_id=policy_id,
        rubric_secret=rubric_secret,
        version=rubric_version,
    )
    return resolve_active_question_authority(
        paper_authority=paper,
        question_id=question_id,
        source=_Source(
            _Selection(
                grading_spec_ref=paper.grading_spec_ref,
                question_id=question_id,
                question_text=question_text,
                context_policy=context_policy,
                active_rubric=active,
            )
        ),
    )


def _roots(
    *,
    question_id: str = "Q1",
    context_policy: ContextPolicy = ContextPolicy.DIRECT,
    evidence_question_ids: tuple[str, ...] | None = None,
    zero_blocks_for: frozenset[str] = frozenset(),
    student_secret: str | None = None,
    question_secret: str | None = None,
    rubric_secret: str | None = None,
    first_content_override: str | None = None,
    first_state: str = "ACTIVE",
):
    paper = _paper(expected_questions=(_expected(question_id),))
    authority = _question_authority(
        paper,
        question_id=question_id,
        context_policy=context_policy,
        question_text=(
            "Explain the result." if question_secret is None else question_secret
        ),
        rubric_id="R-Q1",
        policy_id="P-Q1",
        rubric_secret=rubric_secret,
    )
    effective_evidence_question_ids = (
        (question_id,) if evidence_question_ids is None else evidence_question_ids
    )
    admitted = _admitted_evidence(
        *effective_evidence_question_ids,
        zero_blocks_for=zero_blocks_for,
        student_secret=student_secret,
        first_content_override=first_content_override,
        first_state=first_state,
    )
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    return context, admitted, paper, authority


def _compatible_roots_for_admitted(
    admitted: AdmittedNormalizedEvidence,
    *,
    paper: ResolvedPaperScoringAuthority | None = None,
    authority: ResolvedQuestionAuthority | None = None,
    question_id: str = "Q1",
    grading_run_id: str = "RUN-P0B-1",
    exam_ref: str = "EXAM-P0B-1",
) -> tuple[
    GradingExecutionContext,
    AdmittedNormalizedEvidence,
    ResolvedPaperScoringAuthority,
    ResolvedQuestionAuthority,
]:
    effective_paper = _paper() if paper is None else paper
    effective_authority = (
        _question_authority(effective_paper, question_id=question_id)
        if authority is None
        else authority
    )
    context = GradingExecutionContext(
        grading_run_id=grading_run_id,
        submission_ref=admitted.evidence.submission_ref,
        exam_ref=exam_ref,
        grading_spec_ref=effective_paper.grading_spec_ref,
    )
    return context, admitted, effective_paper, effective_authority


def _bind(api: ModuleType, roots):
    context, admitted, paper, authority = roots
    return api.bind_question_evaluation_inputs(
        context=context,
        admitted_evidence=admitted,
        paper_authority=paper,
        question_authority=authority,
    )


def _assert_rejected(api: ModuleType, roots) -> None:
    context, admitted, paper, authority = roots
    with pytest.raises(api.QuestionEvaluationBindingError):
        api.bind_question_evaluation_inputs(
            context=context,
            admitted_evidence=admitted,
            paper_authority=paper,
            question_authority=authority,
        )


class _PrivacyForeignValue:
    def __init__(self) -> None:
        self.repr_calls = 0
        self.equal_calls = 0
        self.attribute_reads = 0
        self.iter_calls = 0

    def __repr__(self) -> str:
        self.repr_calls += 1
        return _FOREIGN_SENTINEL

    def __eq__(self, other: object) -> bool:
        del other
        self.equal_calls += 1
        raise AssertionError("privacy foreign value equality was invoked")

    @property
    def rubric_id(self) -> object:
        self.attribute_reads += 1
        raise AssertionError("privacy foreign value property was read")

    @property
    def policy_id(self) -> object:
        self.attribute_reads += 1
        raise AssertionError("privacy foreign value property was read")

    def __iter__(self):
        self.iter_calls += 1
        raise AssertionError("privacy foreign value iteration was invoked")


def _privacy_roots():
    paper = _paper(
        minimum_score=_SCORING_MIN_SENTINEL,
        maximum_score=_SCORING_MAX_SENTINEL,
    )
    authority = _question_authority(
        paper,
        question_text=_QUESTION_SENTINEL,
        rubric_secret=_RUBRIC_SENTINEL,
    )
    admitted = _admitted_evidence(
        "Q1",
        student_secret=_STUDENT_SENTINEL,
    )
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-PRIVACY",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-PRIVACY",
        grading_spec_ref=paper.grading_spec_ref,
    )
    return context, admitted, paper, authority


def _rich_privacy_content() -> QuestionRubricAuthoringContent:
    c1_full = AuthoringPerformanceLevel(
        "FULL",
        _RUBRIC_LEVEL_SENTINEL,
        ScoringDecimal.from_raw(_LEVEL_SCORE_ONE_SENTINEL),
    )
    c1_not_met = AuthoringPerformanceLevel(
        "NOT_MET",
        _RUBRIC_LEVEL_NOT_MET_SENTINEL,
        ScoringDecimal.from_raw("0"),
    )
    c2_full = AuthoringPerformanceLevel(
        "FULL",
        _RUBRIC_SECOND_LEVEL_FULL_SENTINEL,
        ScoringDecimal.from_raw(_LEVEL_SCORE_TWO_SENTINEL),
    )
    c2_not_met = AuthoringPerformanceLevel(
        "NOT_MET",
        _RUBRIC_SECOND_LEVEL_NOT_MET_SENTINEL,
        ScoringDecimal.from_raw("0"),
    )
    c1 = AuthoringCriterion(
        criterion_id="C1",
        operational_description=_RUBRIC_SENTINEL,
        evidence_requirement=_RUBRIC_EVIDENCE_SENTINEL,
        performance_levels=(c1_full, c1_not_met),
        accepted_equivalents=(_RUBRIC_EQUIVALENT_SENTINEL,),
    )
    c2 = AuthoringCriterion(
        criterion_id="C2",
        operational_description=_RUBRIC_SECOND_SENTINEL,
        evidence_requirement=_RUBRIC_SECOND_EVIDENCE_SENTINEL,
        performance_levels=(c2_full, c2_not_met),
        accepted_equivalents=(_RUBRIC_SECOND_EQUIVALENT_SENTINEL,),
    )
    c1_full_condition = AuthoringCriterionCondition("C1", ("FULL",))
    c1_full_for_cap = AuthoringCriterionCondition("C1", ("FULL",))
    c2_not_met_for_cap = AuthoringCriterionCondition("C2", ("NOT_MET",))
    c1_full_for_deduction = AuthoringCriterionCondition("C1", ("FULL",))
    c2_not_met_for_deduction = AuthoringCriterionCondition("C2", ("NOT_MET",))
    return QuestionRubricAuthoringContent(
        rubric_id="R-Q1",
        policy_id="P-Q1",
        minimum_score=ScoringDecimal.from_raw("0"),
        criteria=(c1, c2),
        positive_credit_dependencies=(
            AuthoringPositiveCreditDependencyRule(
                "DEP-RICH",
                "C2",
                (c1_full_condition,),
            ),
        ),
        gates=(
            AuthoringGateRule(
                "GATE-RICH",
                (AuthoringCriterionCondition("C1", ("FULL",)),),
                ScoringDecimal.from_raw(_GATE_SCORE_SENTINEL),
            ),
        ),
        caps=(
            AuthoringCapRule(
                "CAP-RICH",
                (c1_full_for_cap, c2_not_met_for_cap),
                ScoringDecimal.from_raw(_CAP_SCORE_SENTINEL),
            ),
        ),
        deductions=(
            AuthoringDeductionRule(
                "DED-RICH",
                (c1_full_for_deduction, c2_not_met_for_deduction),
                ScoringDecimal.from_raw(_DEDUCTION_SCORE_SENTINEL),
            ),
        ),
        rounding=AuthoringRoundingRule(
            "ROUND-RICH",
            ScoringDecimal.from_raw(_ROUNDING_SCORE_SENTINEL),
            "HALF_UP",
        ),
    )


def _active_rich_privacy_rubric() -> RubricAuthoringVersion:
    draft = create_initial_version(simple_basis(question_id="Q1"), _rich_privacy_content())
    return activate_version(
        approve_version(
            validate_version(draft, limits=authoring_test_limits()),
            teacher_ref="teacher-p0b-rich-privacy",
        ),
        limits=authoring_test_limits(),
    )


def _rich_privacy_roots():
    paper = _paper(
        minimum_score=_SCORING_MIN_SENTINEL,
        maximum_score=_SCORING_MAX_SENTINEL,
    )
    active = _active_rich_privacy_rubric()
    authority = resolve_active_question_authority(
        paper_authority=paper,
        question_id="Q1",
        source=_Source(
            _Selection(
                grading_spec_ref=paper.grading_spec_ref,
                question_id="Q1",
                question_text=_QUESTION_SENTINEL,
                context_policy=ContextPolicy.DIRECT,
                active_rubric=active,
            )
        ),
    )
    admitted = _admitted_evidence(
        "Q1",
        student_secret=_STUDENT_SENTINEL,
    )
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-RICH-PRIVACY",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-RICH-PRIVACY",
        grading_spec_ref=paper.grading_spec_ref,
    )
    return context, admitted, paper, authority


def _append_identity(values: list[object], value: object) -> None:
    if not any(value is existing for existing in values):
        values.append(value)


def _privacy_sensitive_identity_manifest(roots, *extra: object) -> tuple[object, ...]:
    """Explicit finite fixture-derived privacy identities; no generic graph walk."""

    context, admitted, paper, authority = roots
    protected: list[object] = []

    # Canonical supplied roots and evidence custody roots.
    for value in (context, admitted, admitted.evidence, paper, authority):
        _append_identity(protected, value)

    # Student-content-bearing evidence descendants and exact content leaves.
    for question in admitted.evidence.questions:
        _append_identity(protected, question)
        for block in question.blocks:
            _append_identity(protected, block)
            _append_identity(protected, block.content)

    # Question text is protected prose, not an opaque identifier.
    _append_identity(protected, authority.question_text)

    # Rich authoring rubric material and exact protected textual/scoring leaves.
    content = authority.rubric_content
    _append_identity(protected, content)
    if type(content) is QuestionRubricAuthoringContent:
        _append_identity(protected, content.minimum_score)
        _append_identity(protected, content.minimum_score.as_decimal())
        for criterion in content.criteria:
            _append_identity(protected, criterion)
            _append_identity(protected, criterion.operational_description)
            _append_identity(protected, criterion.evidence_requirement)
            for equivalent in criterion.accepted_equivalents:
                _append_identity(protected, equivalent)
            for level in criterion.performance_levels:
                _append_identity(protected, level)
                _append_identity(protected, level.operational_description)
                _append_identity(protected, level.contribution)
                _append_identity(protected, level.contribution.as_decimal())

        for dependency in content.positive_credit_dependencies:
            _append_identity(protected, dependency)
            for condition in dependency.prerequisite_conditions:
                _append_identity(protected, condition)
        for gate in content.gates:
            _append_identity(protected, gate)
            _append_identity(protected, gate.failure_ceiling)
            _append_identity(protected, gate.failure_ceiling.as_decimal())
            for condition in gate.required_conditions:
                _append_identity(protected, condition)
        for cap in content.caps:
            _append_identity(protected, cap)
            _append_identity(protected, cap.ceiling)
            _append_identity(protected, cap.ceiling.as_decimal())
            for condition in cap.trigger_conditions:
                _append_identity(protected, condition)
        for deduction in content.deductions:
            _append_identity(protected, deduction)
            _append_identity(protected, deduction.amount)
            _append_identity(protected, deduction.amount.as_decimal())
            for condition in deduction.trigger_conditions:
                _append_identity(protected, condition)
        if content.rounding is not None:
            _append_identity(protected, content.rounding)
            _append_identity(protected, content.rounding.increment)
            _append_identity(protected, content.rounding.increment.as_decimal())

    # Reducer-facing rubric/policy projections and exact scoring descendants.
    scoring = authority.scoring_authority
    _append_identity(protected, scoring)
    if type(scoring) is QuestionScoringAuthority:
        rubric = scoring.rubric
        _append_identity(protected, rubric)
        _append_identity(protected, rubric.max_marks)
        _append_identity(protected, rubric.max_marks.as_decimal())
        for criterion in rubric.criteria:
            _append_identity(protected, criterion)
            _append_identity(protected, criterion.operational_description)
            for level in criterion.performance_levels:
                _append_identity(protected, level)
                _append_identity(protected, level.contribution)
                _append_identity(protected, level.contribution.as_decimal())

        policy = scoring.policy
        _append_identity(protected, policy)
        for score in (policy.minimum_score, policy.maximum_score):
            _append_identity(protected, score)
            _append_identity(protected, score.as_decimal())
        for dependency in policy.positive_credit_dependencies:
            _append_identity(protected, dependency)
            for condition in dependency.prerequisite_conditions:
                _append_identity(protected, condition)
        for gate in policy.gates:
            _append_identity(protected, gate)
            _append_identity(protected, gate.failure_ceiling)
            _append_identity(protected, gate.failure_ceiling.as_decimal())
            for condition in gate.required_conditions:
                _append_identity(protected, condition)
        for cap in policy.caps:
            _append_identity(protected, cap)
            _append_identity(protected, cap.ceiling)
            _append_identity(protected, cap.ceiling.as_decimal())
            for condition in cap.trigger_conditions:
                _append_identity(protected, condition)
        for deduction in policy.deductions:
            _append_identity(protected, deduction)
            _append_identity(protected, deduction.amount)
            _append_identity(protected, deduction.amount.as_decimal())
            for condition in deduction.trigger_conditions:
                _append_identity(protected, condition)
        if policy.rounding is not None:
            _append_identity(protected, policy.rounding)
            _append_identity(protected, policy.rounding.increment)
            _append_identity(protected, policy.rounding.increment.as_decimal())

    # Paper-level scoring details are separately authoritative and protected.
    for score in (paper.minimum_score, paper.maximum_score):
        _append_identity(protected, score)
        _append_identity(protected, score.as_decimal())

    for value in extra:
        _append_identity(protected, value)

    return tuple(protected)


def _privacy_protected_objects(roots, *extra: object) -> tuple[object, ...]:
    return _privacy_sensitive_identity_manifest(roots, *extra)


def _privacy_rejection_case(case_name: str):
    context, admitted, paper, authority = _privacy_roots()
    extra: tuple[object, ...] = ()

    if case_name == "missing_evidence":
        admitted = _admitted_evidence(
            "Q-OTHER",
            student_secret=_STUDENT_SENTINEL,
        )
        context = replace(context, submission_ref=admitted.evidence.submission_ref)
        assert authority.question_id == "Q1"
        assert all(
            question.question_id != authority.question_id
            for question in admitted.evidence.questions
        )
    elif case_name == "submission_mismatch":
        context = replace(context, submission_ref="SUB-P0B-PRIVACY-OTHER")
        assert context.submission_ref != admitted.evidence.submission_ref
    elif case_name == "context_paper_spec_mismatch":
        context = replace(
            context,
            grading_spec_ref=GradingSpecRef(id="SPEC-P0B-PRIVACY-OTHER", version=1),
        )
        assert context.grading_spec_ref != paper.grading_spec_ref
        assert authority.grading_spec_ref == paper.grading_spec_ref
    elif case_name == "question_paper_spec_mismatch":
        authority = replace(
            authority,
            grading_spec_ref=GradingSpecRef(id="SPEC-P0B-PRIVACY-OTHER", version=1),
        )
        assert context.grading_spec_ref == paper.grading_spec_ref
        assert authority.grading_spec_ref != paper.grading_spec_ref
    elif case_name == "question_absent_from_paper":
        paper = _paper(
            expected_questions=(
                _expected("Q2", rubric_id="R-Q2", policy_id="P-Q2"),
            ),
            minimum_score=_SCORING_MIN_SENTINEL,
            maximum_score=_SCORING_MAX_SENTINEL,
        )
        context = replace(context, grading_spec_ref=paper.grading_spec_ref)
        authority = replace(authority, grading_spec_ref=paper.grading_spec_ref)
        assert authority.question_id == "Q1"
        assert all(
            expected.question_id != authority.question_id
            for expected in paper.expected_questions
        )
    elif case_name == "scoring_question_mismatch":
        q2_paper = _paper(
            expected_questions=(
                _expected("Q2", rubric_id="R-Q1", policy_id="P-Q1"),
            )
        )
        q2_authority = _question_authority(
            q2_paper,
            question_id="Q2",
            rubric_id="R-Q1",
            policy_id="P-Q1",
            rubric_secret=_RUBRIC_SENTINEL,
        )
        authority = replace(
            authority,
            scoring_authority=q2_authority.scoring_authority,
        )
        extra = (q2_authority.scoring_authority,)
        assert authority.question_id == "Q1"
        assert authority.scoring_authority.rubric.question_id == "Q2"
        assert authority.scoring_authority.policy.question_id == "Q2"
    elif case_name == "rubric_ref_mismatch":
        paper = _paper(
            expected_questions=(_expected("Q1", rubric_id="R-OTHER"),),
            minimum_score=_SCORING_MIN_SENTINEL,
            maximum_score=_SCORING_MAX_SENTINEL,
        )
        context = replace(context, grading_spec_ref=paper.grading_spec_ref)
        authority = replace(authority, grading_spec_ref=paper.grading_spec_ref)
        assert paper.expected_questions[0].rubric_ref != RubricRef(
            id=authority.scoring_authority.rubric.rubric_id,
            version=authority.scoring_authority.rubric.version,
        )
    elif case_name == "policy_ref_mismatch":
        paper = _paper(
            expected_questions=(_expected("Q1", policy_id="P-OTHER"),),
            minimum_score=_SCORING_MIN_SENTINEL,
            maximum_score=_SCORING_MAX_SENTINEL,
        )
        context = replace(context, grading_spec_ref=paper.grading_spec_ref)
        authority = replace(authority, grading_spec_ref=paper.grading_spec_ref)
        assert paper.expected_questions[0].scoring_policy_ref != ScoringPolicyRef(
            id=authority.scoring_authority.policy.policy_id,
            version=authority.scoring_authority.policy.version,
            scoring_semantics_version=(
                authority.scoring_authority.policy.scoring_semantics_version
            ),
        )
    elif case_name == "rubric_content_mismatch":
        mismatched_content = replace(
            authority.rubric_content,
            rubric_id="R-OTHER",
        )
        authority = replace(authority, rubric_content=mismatched_content)
        assert (
            authority.rubric_content.rubric_id
            != authority.scoring_authority.rubric.rubric_id
        )
    elif case_name == "policy_content_mismatch":
        mismatched_content = replace(
            authority.rubric_content,
            policy_id="P-OTHER",
        )
        authority = replace(authority, rubric_content=mismatched_content)
        assert (
            authority.rubric_content.policy_id
            != authority.scoring_authority.policy.policy_id
        )
    elif case_name == "foreign_root":
        hostile = _PrivacyForeignValue()
        context = hostile
        extra = (hostile,)
        assert type(context) is _PrivacyForeignValue
    elif case_name == "weak_projection":
        authority = replace(authority, question_text=123)
        assert type(authority.question_text) is int
    elif case_name == "foreign_nested_authority":
        hostile = _PrivacyForeignValue()
        authority = replace(authority, rubric_content=hostile)
        extra = (hostile,)
        assert type(authority.rubric_content) is _PrivacyForeignValue
        assert hostile.attribute_reads == 0
    else:
        raise AssertionError(f"unknown privacy rejection case {case_name!r}")

    roots = (context, admitted, paper, authority)
    return roots, _privacy_protected_objects(roots, *extra), extra


def test_prerequisite_frozen_fixtures_are_coherent_before_new_boundary() -> None:
    context, admitted, paper, authority = _roots(
        evidence_question_ids=("Q1", "Q-UNRELATED"),
    )
    assert type(context) is GradingExecutionContext
    assert type(admitted) is AdmittedNormalizedEvidence
    assert type(paper) is ResolvedPaperScoringAuthority
    assert type(authority) is ResolvedQuestionAuthority
    assert context.submission_ref == admitted.evidence.submission_ref
    assert context.grading_spec_ref == paper.grading_spec_ref == authority.grading_spec_ref
    assert authority.question_id == "Q1"
    assert paper.expected_questions[0].question_id == authority.question_id
    assert tuple(q.question_id for q in admitted.evidence.questions) == (
        "Q1",
        "Q-UNRELATED",
    )

    _, empty_admitted, _, _ = _roots(evidence_question_ids=())
    assert empty_admitted.evidence.questions == ()

    _, _, _, empty_text_authority = _roots(question_secret="")
    assert empty_text_authority.question_text == ""


def test_prerequisite_current_evidence_block_type_vocabulary_is_explicit() -> None:
    assert {member.value for member in EvidenceBlockType} == {
        "TEXT",
        "MATH",
        "TABLE",
        "FIGURE",
        "CODE",
        "OTHER",
    }


def test_prerequisite_current_evidence_block_state_vocabulary_is_explicit() -> None:
    assert {member.value for member in EvidenceBlockState} == {
        "ACTIVE",
        "CROSSED_OUT",
        "UNCERTAIN",
    }


def test_prerequisite_current_evidence_confidence_status_vocabulary_is_explicit() -> None:
    assert {member.value for member in EvidenceConfidenceStatus} == {
        "PRESENT",
        "UNAVAILABLE",
    }


def test_prerequisite_current_evidence_location_status_vocabulary_is_explicit() -> None:
    assert {member.value for member in EvidenceLocationStatus} == {
        "PRESENT",
        "PARTIAL",
        "UNAVAILABLE",
    }


def test_prerequisite_diagnostic_scanner_terminates_on_exact_builtin_cycle() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    _assert_diagnostic_value_safe(cycle, confidential_sentinels=("never-present",))


def test_prerequisite_diagnostic_scanner_fails_closed_on_depth_exhaustion() -> None:
    nested: object = "safe"
    for _ in range(4):
        nested = [nested]
    with pytest.raises(_DiagnosticTraversalExhausted, match="depth budget"):
        _assert_diagnostic_value_safe(
            nested,
            confidential_sentinels=("never-present",),
            max_depth=2,
            max_items=32,
        )


def test_prerequisite_diagnostic_scanner_fails_closed_on_item_exhaustion() -> None:
    with pytest.raises(_DiagnosticTraversalExhausted, match="item budget"):
        _assert_diagnostic_value_safe(
            ["a", "b", "c"],
            confidential_sentinels=("never-present",),
            max_depth=4,
            max_items=2,
        )


def test_prerequisite_diagnostic_scanner_does_not_introspect_unknown_objects() -> None:
    opaque = _PrivacyForeignValue()
    _assert_diagnostic_value_safe(
        opaque,
        confidential_sentinels=("never-present",),
    )
    assert opaque.repr_calls == 0
    assert opaque.equal_calls == 0
    assert opaque.attribute_reads == 0
    assert opaque.iter_calls == 0

    with pytest.raises(AssertionError, match="protected domain object"):
        _assert_diagnostic_value_safe(
            opaque,
            protected_objects=(opaque,),
            confidential_sentinels=("never-present",),
        )
    assert opaque.repr_calls == 0
    assert opaque.equal_calls == 0
    assert opaque.attribute_reads == 0
    assert opaque.iter_calls == 0



def _assert_manifest_contains_identity(manifest: tuple[object, ...], value: object) -> None:
    assert any(value is candidate for candidate in manifest)


def test_prerequisite_privacy_manifest_covers_exact_rich_fixture_identities() -> None:
    roots = _rich_privacy_roots()
    _, admitted, paper, authority = roots
    manifest = _privacy_sensitive_identity_manifest(roots)

    question = admitted.evidence.questions[0]
    block = question.blocks[0]
    content = authority.rubric_content
    criterion = content.criteria[0]
    authoring_level = criterion.performance_levels[0]
    compiled = authority.scoring_authority.rubric
    atomic = compiled.criteria[0]
    compiled_level = atomic.performance_levels[0]
    policy = authority.scoring_authority.policy

    exact_identities = (
        question,
        block,
        block.content,
        authority.question_text,
        content,
        content.minimum_score,
        content.minimum_score.as_decimal(),
        criterion,
        criterion.operational_description,
        criterion.evidence_requirement,
        criterion.accepted_equivalents[0],
        authoring_level,
        authoring_level.operational_description,
        authoring_level.contribution,
        authoring_level.contribution.as_decimal(),
        content.positive_credit_dependencies[0],
        content.positive_credit_dependencies[0].prerequisite_conditions[0],
        content.gates[0],
        content.gates[0].required_conditions[0],
        content.gates[0].failure_ceiling,
        content.gates[0].failure_ceiling.as_decimal(),
        content.caps[0],
        content.caps[0].trigger_conditions[0],
        content.caps[0].ceiling,
        content.caps[0].ceiling.as_decimal(),
        content.deductions[0],
        content.deductions[0].trigger_conditions[0],
        content.deductions[0].amount,
        content.deductions[0].amount.as_decimal(),
        content.rounding,
        content.rounding.increment,
        content.rounding.increment.as_decimal(),
        compiled,
        compiled.max_marks,
        compiled.max_marks.as_decimal(),
        atomic,
        atomic.operational_description,
        compiled_level,
        compiled_level.contribution,
        compiled_level.contribution.as_decimal(),
        policy,
        policy.minimum_score,
        policy.minimum_score.as_decimal(),
        policy.maximum_score,
        policy.maximum_score.as_decimal(),
        policy.positive_credit_dependencies[0],
        policy.positive_credit_dependencies[0].prerequisite_conditions[0],
        policy.gates[0],
        policy.gates[0].required_conditions[0],
        policy.gates[0].failure_ceiling,
        policy.gates[0].failure_ceiling.as_decimal(),
        policy.caps[0],
        policy.caps[0].trigger_conditions[0],
        policy.caps[0].ceiling,
        policy.caps[0].ceiling.as_decimal(),
        policy.deductions[0],
        policy.deductions[0].trigger_conditions[0],
        policy.deductions[0].amount,
        policy.deductions[0].amount.as_decimal(),
        policy.rounding,
        policy.rounding.increment,
        policy.rounding.increment.as_decimal(),
        paper.minimum_score,
        paper.minimum_score.as_decimal(),
        paper.maximum_score,
        paper.maximum_score.as_decimal(),
    )
    for value in exact_identities:
        _assert_manifest_contains_identity(manifest, value)


def test_prerequisite_privacy_diagnostic_state_rejects_every_manifest_identity() -> None:
    roots = _rich_privacy_roots()
    manifest = _privacy_sensitive_identity_manifest(roots)
    for protected in manifest:
        exc = RuntimeError("safe")
        exc.detail = {"nested": protected}  # type: ignore[attr-defined]
        with pytest.raises(AssertionError, match="protected domain object"):
            _assert_expected_rejection_diagnostics_are_private(
                exc,
                protected_objects=manifest,
            )


def test_prerequisite_privacy_diagnostic_state_rejects_bytes_key_and_value() -> None:
    roots = _rich_privacy_roots()
    manifest = _privacy_sensitive_identity_manifest(roots)
    encoded = _STUDENT_SENTINEL.encode("utf-8")
    for state in (
        {"payload": encoded},
        {encoded: "safe"},
    ):
        exc = RuntimeError("safe")
        exc.detail = state  # type: ignore[attr-defined]
        with pytest.raises(AssertionError, match="encoded confidential sentinel"):
            _assert_expected_rejection_diagnostics_are_private(
                exc,
                protected_objects=manifest,
            )


def test_prerequisite_privacy_diagnostic_state_rejects_bytearray_value() -> None:
    roots = _rich_privacy_roots()
    manifest = _privacy_sensitive_identity_manifest(roots)
    exc = RuntimeError("safe")
    exc.detail = {"payload": bytearray(_STUDENT_SENTINEL.encode("utf-8"))}  # type: ignore[attr-defined]
    with pytest.raises(AssertionError, match="encoded confidential sentinel"):
        _assert_expected_rejection_diagnostics_are_private(
            exc,
            protected_objects=manifest,
        )


def test_prerequisite_static_public_data_scanner_is_passive_and_syntactic() -> None:
    class _ExplodingDescriptor:
        def __init__(self) -> None:
            self.get_calls = 0

        def __get__(self, instance: object, owner: type[object]) -> object:
            del instance, owner
            self.get_calls += 1
            raise AssertionError("custom descriptor must not be invoked by source inspector")

    descriptor = _ExplodingDescriptor()

    class _Probe:
        __slots__ = ("slot_data", "__dict__")

        public_constant = "stored-public-data"
        opaque_descriptor = descriptor

        def __init__(self) -> None:
            self.slot_data = "slot"
            self.instance_data = "dict"

        @property
        def property_data(self) -> object:
            raise AssertionError("property getter must not be invoked by source inspector")

        def public_method(self) -> None:
            raise AssertionError("method must not be invoked by source inspector")

        @staticmethod
        def public_static_method() -> None:
            raise AssertionError("staticmethod must not be invoked by source inspector")

        @classmethod
        def public_class_method(cls) -> None:
            del cls
            raise AssertionError("classmethod must not be invoked by source inspector")

    probe = _Probe()
    surface = _classify_static_public_surface(probe)

    assert surface.ordinary_data_names == frozenset(
        {
            "instance_data",
            "property_data",
            "public_constant",
            "slot_data",
        }
    )
    assert surface.opaque_descriptor_names == frozenset({"opaque_descriptor"})
    assert descriptor.get_calls == 0


def test_red_bound_result_static_public_data_surface_is_exactly_four_roots() -> None:
    api = _api()
    roots = _roots()
    bound = _bind(api, roots)

    surface = _classify_static_public_surface(bound)
    assert surface.ordinary_data_names == _ALLOWED_BOUND_PUBLIC_DATA_NAMES
    # Opaque/custom descriptor names are deliberately not accepted as safe here;
    # their semantics must remain covered by the regression suite.


def test_red_public_surface_is_narrow_and_binding_function_has_four_roots() -> None:
    api = _api()
    assert set(api.__all__) == {
        "QuestionEvaluationBindingError",
        "BoundQuestionEvaluationInputs",
        "bind_question_evaluation_inputs",
    }
    signature = inspect.signature(api.bind_question_evaluation_inputs)
    assert tuple(signature.parameters) == (
        "context",
        "admitted_evidence",
        "paper_authority",
        "question_authority",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )


def test_red_valid_binding_retains_exact_four_canonical_roots() -> None:
    api = _api()
    roots = _roots()
    bound = _bind(api, roots)
    assert bound.context is roots[0]
    assert bound.admitted_evidence is roots[1]
    assert bound.paper_authority is roots[2]
    assert bound.question_authority is roots[3]
    assert bound.admitted_evidence.evidence is roots[1].evidence


def test_red_bound_result_has_no_ordinary_constructor_bypass() -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    constructor_attempts = (
        lambda: api.BoundQuestionEvaluationInputs(),
        lambda: api.BoundQuestionEvaluationInputs(
            context,
            admitted,
            paper,
            authority,
        ),
        lambda: api.BoundQuestionEvaluationInputs(
            context=context,
            admitted_evidence=admitted,
            paper_authority=paper,
            question_authority=authority,
        ),
    )
    for attempt in constructor_attempts:
        with pytest.raises(TypeError):
            attempt()


def test_red_bound_result_has_no_ordinary_subclass_bypass() -> None:
    api = _api()
    with pytest.raises(TypeError):
        type("ForgedBoundQuestionEvaluationInputs", (api.BoundQuestionEvaluationInputs,), {})


@pytest.mark.parametrize(
    "context_policy",
    tuple(ContextPolicy),
)
def test_red_p0b_is_capability_neutral_for_all_canonical_context_policies(
    context_policy: ContextPolicy,
) -> None:
    api = _api()
    roots = _roots(context_policy=context_policy)
    bound = _bind(api, roots)
    assert bound.question_authority.context_policy is context_policy


def test_red_unrelated_evidence_questions_are_permitted() -> None:
    api = _api()
    bound = _bind(api, _roots(evidence_question_ids=("Q1", "Q-UNRELATED")))
    assert tuple(
        question.question_id
        for question in bound.admitted_evidence.evidence.questions
    ) == ("Q1", "Q-UNRELATED")


def test_red_zero_blocks_for_bound_question_is_not_interpreted_as_missing_or_incorrect() -> None:
    api = _api()
    bound = _bind(api, _roots(zero_blocks_for=frozenset({"Q1"})))
    matching = tuple(
        question
        for question in bound.admitted_evidence.evidence.questions
        if question.question_id == "Q1"
    )
    assert len(matching) == 1
    assert matching[0].blocks == ()


def test_red_empty_evidence_universe_is_rejected_for_bound_question() -> None:
    api = _api()
    roots = _roots(evidence_question_ids=())
    assert roots[1].evidence.questions == ()
    _assert_rejected(api, roots)


@pytest.mark.parametrize(
    ("question_text", "whitespace_only"),
    (
        (" \tExplain the result exactly as supplied.\n  ", False),
        (" \t\n  ", True),
    ),
    ids=("meaningful-surrounding-whitespace", "non-empty-whitespace-only"),
)
def test_red_question_text_formatting_is_preserved_from_frozen_authority(
    question_text: str,
    whitespace_only: bool,
) -> None:
    roots = _roots(question_secret=question_text)

    # Establish the frozen upstream premise before crossing the absent/new question evidence binding boundary.
    assert roots[3].question_text == question_text
    assert question_text != ""
    if whitespace_only:
        assert question_text.isspace()
    else:
        assert question_text.strip() != question_text
        assert not question_text.isspace()

    api = _api()
    bound = _bind(api, roots)
    assert bound.question_authority is roots[3]
    assert bound.question_authority.question_text == question_text


def test_red_empty_question_text_is_structurally_accepted() -> None:
    roots = _roots(question_secret="")
    assert roots[3].question_text == ""
    api = _api()
    bound = _bind(api, roots)
    assert bound.question_authority is roots[3]


@pytest.mark.parametrize(
    ("student_content", "whitespace_only"),
    (
        (" \tStudent answer preserved exactly.\n  ", False),
        (" \t\n  ", True),
    ),
    ids=("meaningful-surrounding-whitespace", "non-empty-whitespace-only"),
)
def test_red_student_content_formatting_is_preserved_from_real_p0a(
    student_content: str,
    whitespace_only: bool,
) -> None:
    admitted = _admitted_single_question(content=student_content)
    upstream_block = admitted.evidence.questions[0].blocks[0]

    # Establish the real normalized OCR evidence admission premise before crossing the absent/new question evidence binding boundary.
    assert upstream_block.content == student_content
    assert student_content != ""
    if whitespace_only:
        assert student_content.isspace()
    else:
        assert student_content.strip() != student_content
        assert not student_content.isspace()

    roots = _compatible_roots_for_admitted(admitted)
    api = _api()
    bound = _bind(api, roots)
    assert bound.admitted_evidence is admitted
    assert (
        bound.admitted_evidence.evidence.questions[0].blocks[0].content
        == student_content
    )


def test_red_empty_uncertain_evidence_is_bound_without_academic_interpretation() -> None:
    api = _api()
    bound = _bind(
        api,
        _roots(
            first_content_override="",
            first_state="UNCERTAIN",
        ),
    )
    matching = next(
        question
        for question in bound.admitted_evidence.evidence.questions
        if question.question_id == "Q1"
    )
    assert matching.blocks[0].content == ""
    assert matching.blocks[0].state.value == "UNCERTAIN"
    assert matching.blocks[0].confidence is None
    assert matching.blocks[0].location.bbox is None


@pytest.mark.parametrize(
    "block_type",
    tuple(EvidenceBlockType),
)
def test_red_every_current_p0a_admitted_block_type_remains_bindable(
    block_type: EvidenceBlockType,
) -> None:
    admitted = _admitted_single_question(block_type=block_type.value)
    block = admitted.evidence.questions[0].blocks[0]
    assert block.type is block_type
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


@pytest.mark.parametrize(
    "state",
    tuple(EvidenceBlockState),
)
def test_red_every_current_p0a_admitted_block_state_remains_bindable(
    state: EvidenceBlockState,
) -> None:
    admitted = _admitted_single_question(state=state.value)
    block = admitted.evidence.questions[0].blocks[0]
    assert block.state is state
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


@pytest.mark.parametrize(
    ("status", "confidence"),
    [
        (EvidenceConfidenceStatus.UNAVAILABLE, None),
        (EvidenceConfidenceStatus.PRESENT, 2.5),
    ],
)
def test_red_every_current_p0a_admitted_confidence_status_remains_bindable(
    status: EvidenceConfidenceStatus,
    confidence: int | float | None,
) -> None:
    admitted = _admitted_single_question(
        confidence_status=status.value,
        confidence=confidence,
    )
    block = admitted.evidence.questions[0].blocks[0]
    assert block.confidence_status is status
    assert block.confidence == confidence
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


@pytest.mark.parametrize(
    ("status", "bbox"),
    [
        (EvidenceLocationStatus.PRESENT, None),
        (EvidenceLocationStatus.PARTIAL, [-9, 2, 3, 4, 5]),
        (EvidenceLocationStatus.UNAVAILABLE, [10, -10]),
    ],
)
def test_red_every_current_p0a_admitted_location_status_remains_bindable_without_geometry_policy(
    status: EvidenceLocationStatus,
    bbox: list[int | float] | None,
) -> None:
    admitted = _admitted_single_question(
        location_status=status.value,
        bbox=bbox,
    )
    block = admitted.evidence.questions[0].blocks[0]
    assert block.location.status is status
    assert block.location.bbox == (None if bbox is None else tuple(bbox))
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


@pytest.mark.parametrize("language", [None, "opaque-language-tag"])
def test_red_p0b_does_not_require_or_normalize_language_metadata(
    language: str | None,
) -> None:
    admitted = _admitted_single_question(language=language)
    assert admitted.evidence.questions[0].blocks[0].language == language
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_negative_page_is_p0a_admitted_and_not_reinterpreted_by_p0b() -> None:
    admitted = _admitted_single_question(page=-7)
    assert admitted.evidence.questions[0].blocks[0].page == -7
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_negative_reading_order_is_p0a_admitted_and_not_reinterpreted_by_p0b() -> None:
    admitted = _admitted_single_question(reading_order=-3)
    assert admitted.evidence.questions[0].blocks[0].reading_order == -3
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


@pytest.mark.parametrize(
    "reading_orders",
    [(7, 7), (9, -4)],
)
def test_red_multiple_blocks_do_not_create_p0b_reading_order_or_cardinality_policy(
    reading_orders: tuple[int, int],
) -> None:
    question = _wire_question(
        "Q1",
        block_id="opaque-block-a",
        reading_order=reading_orders[0],
        extra_blocks=(
            _wire_block(
                block_id="opaque-block-b",
                content="second admitted block",
                reading_order=reading_orders[1],
            ),
        ),
    )
    admitted = _admit_questions([question])
    blocks = admitted.evidence.questions[0].blocks
    assert len(blocks) == 2
    assert tuple(block.reading_order for block in blocks) == reading_orders
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_block_and_answer_scope_identifiers_remain_opaque_to_p0b() -> None:
    admitted = _admitted_single_question(
        block_id="opaque:block#beta",
        answer_scope_ref="opaque/scope@17",
    )
    question = admitted.evidence.questions[0]
    assert question.answer_scope_ref == "opaque/scope@17"
    assert question.blocks[0].block_id == "opaque:block#beta"
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_admitted_warnings_and_asset_reference_do_not_create_p0b_usability_policy() -> None:
    admitted = _admitted_single_question(
        warnings=("opaque warning alpha", "warning\nline two"),
        asset_ref="asset:opaque/17",
    )
    question = admitted.evidence.questions[0]
    assert question.warnings == ("opaque warning alpha", "warning\nline two")
    assert question.blocks[0].asset_ref == "asset:opaque/17"
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_non_ascii_multiline_student_content_remains_opaque_to_p0b() -> None:
    content = "答案 alpha\nsecond line\nthird line"
    admitted = _admitted_single_question(content=content)
    assert admitted.evidence.questions[0].blocks[0].content == content
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_bound_evidence_question_need_not_be_first() -> None:
    admitted = _admit_questions(
        [_wire_question("Q-UNRELATED"), _wire_question("Q1")]
    )
    assert tuple(q.question_id for q in admitted.evidence.questions) == (
        "Q-UNRELATED",
        "Q1",
    )
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_bound_expected_paper_question_need_not_be_first() -> None:
    paper = _paper(
        expected_questions=(
            _expected("Q2", rubric_id="R-Q2", policy_id="P-Q2"),
            _expected("Q1"),
        )
    )
    authority = _question_authority(paper, question_id="Q1")
    admitted = _admitted_evidence("Q1")
    roots = _compatible_roots_for_admitted(
        admitted,
        paper=paper,
        authority=authority,
        question_id="Q1",
    )
    assert tuple(q.question_id for q in paper.expected_questions) == ("Q2", "Q1")
    api = _api()
    bound = _bind(api, roots)
    assert bound.paper_authority is paper
    assert bound.question_authority is authority


def test_red_non_ascii_multiline_question_text_is_structurally_accepted() -> None:
    question_text = "問い alpha\nsecond line"
    roots = _roots(question_secret=question_text)
    assert roots[3].question_text == question_text
    api = _api()
    bound = _bind(api, roots)
    assert bound.question_authority is roots[3]


@pytest.mark.parametrize(
    "source_artifact_ref",
    [None, "opaque:artifact/beta-17"],
)
def test_red_p0a_source_artifact_provenance_remains_opaque_to_p0b(
    source_artifact_ref: str | None,
) -> None:
    admitted = _admitted_single_question(source_artifact_ref=source_artifact_ref)
    assert admitted.source_artifact_ref == source_artifact_ref
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_alternate_valid_p0a_policy_identity_and_limits_do_not_become_p0b_policy() -> None:
    alternate = _policy(
        admission_policy_identity="opaque-policy-beta",
        max_raw_bytes=120_000,
        max_json_depth=24,
        max_json_nodes=2_000,
        max_json_number_characters=64,
        max_identifier_characters=512,
        max_metadata_text_characters=1_024,
        max_block_content_characters=4_096,
        max_total_content_characters=16_384,
        max_questions=8,
        max_blocks_per_question=16,
        max_total_blocks=64,
        max_warnings_per_question=16,
        max_location_coordinates=9,
    )
    admitted = _admitted_single_question(policy=alternate)
    assert admitted.admission_policy_identity == "opaque-policy-beta"
    assert admitted.effective_policy_snapshot == alternate
    assert admitted.effective_policy_snapshot is not alternate
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_ocr_provenance_remains_an_opaque_p0a_admitted_identifier() -> None:
    provenance = "vendor/provenance:v7#opaque"
    admitted = _admitted_single_question(ocr_provenance=provenance)
    assert admitted.evidence.ocr_provenance == provenance
    api = _api()
    bound = _bind(api, _compatible_roots_for_admitted(admitted))
    assert bound.admitted_evidence is admitted


def test_red_same_submission_can_bind_two_independently_admitted_distinct_artifacts() -> None:
    admitted_a = _admitted_single_question(
        submission_ref="shared-submission",
        content="artifact A answer",
    )
    admitted_b = _admitted_single_question(
        submission_ref="shared-submission",
        content="artifact B answer",
    )
    assert admitted_a.evidence.submission_ref == admitted_b.evidence.submission_ref
    assert admitted_a.raw_payload_sha256 != admitted_b.raw_payload_sha256

    paper = _paper()
    authority = _question_authority(paper)
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref="shared-submission",
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    api = _api()
    bound_a = api.bind_question_evaluation_inputs(
        context=context,
        admitted_evidence=admitted_a,
        paper_authority=paper,
        question_authority=authority,
    )
    bound_b = api.bind_question_evaluation_inputs(
        context=context,
        admitted_evidence=admitted_b,
        paper_authority=paper,
        question_authority=authority,
    )
    assert bound_a.admitted_evidence is admitted_a
    assert bound_b.admitted_evidence is admitted_b


def test_red_opaque_non_prefix_identifiers_remain_exact_binding_identities() -> None:
    run_id = "alpha-17"
    exam_ref = "beta-23"
    submission_ref = "gamma-31"
    spec_id = "delta-47"
    question_id = "epsilon-59"
    rubric_id = "zeta-61"
    policy_id = "eta-73"

    paper = _paper(
        spec_id=spec_id,
        expected_questions=(
            _expected(
                question_id,
                rubric_id=rubric_id,
                policy_id=policy_id,
            ),
        ),
    )
    authority = _question_authority(
        paper,
        question_id=question_id,
        rubric_id=rubric_id,
        policy_id=policy_id,
    )
    admitted = _admitted_single_question(
        question_id=question_id,
        submission_ref=submission_ref,
        answer_scope_ref="theta-79",
        block_id="iota-83",
    )
    context = GradingExecutionContext(
        grading_run_id=run_id,
        submission_ref=submission_ref,
        exam_ref=exam_ref,
        grading_spec_ref=paper.grading_spec_ref,
    )
    assert context.grading_run_id == run_id
    assert authority.question_id == question_id
    assert authority.scoring_authority.rubric.rubric_id == rubric_id
    assert authority.scoring_authority.policy.policy_id == policy_id
    api = _api()
    bound = _bind(api, (context, admitted, paper, authority))
    assert bound.context is context
    assert bound.question_authority is authority


def test_red_positive_non_one_versions_remain_ordinary_exact_identities() -> None:
    paper = _paper(
        spec_version=2,
        expected_questions=(
            _expected("Q1", rubric_version=2, policy_version=2),
        ),
    )
    authority = _question_authority(
        paper,
        question_id="Q1",
        rubric_version=2,
    )
    admitted = _admitted_evidence("Q1")
    roots = _compatible_roots_for_admitted(
        admitted,
        paper=paper,
        authority=authority,
    )
    assert paper.grading_spec_ref.version == 2
    assert authority.scoring_authority.rubric.version == 2
    assert authority.scoring_authority.policy.version == 2
    api = _api()
    bound = _bind(api, roots)
    assert bound.paper_authority is paper
    assert bound.question_authority is authority


def test_red_non_default_paper_score_range_is_not_reinterpreted_by_p0b() -> None:
    paper = _paper(minimum_score="-3", maximum_score="17")
    authority = _question_authority(paper)
    admitted = _admitted_evidence("Q1")
    roots = _compatible_roots_for_admitted(
        admitted,
        paper=paper,
        authority=authority,
    )
    assert str(paper.minimum_score.as_decimal()) == "-3"
    assert str(paper.maximum_score.as_decimal()) == "17"
    api = _api()
    bound = _bind(api, roots)
    assert bound.paper_authority is paper


def test_red_paper_wide_evidence_completeness_is_not_required() -> None:
    api = _api()
    paper = _paper(
        expected_questions=(
            _expected("Q1"),
            _expected("Q2", rubric_id="R-Q2", policy_id="P-Q2"),
        )
    )
    authority = _question_authority(paper, question_id="Q1")
    admitted = _admitted_evidence("Q1")
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    bound = api.bind_question_evaluation_inputs(
        context=context,
        admitted_evidence=admitted,
        paper_authority=paper,
        question_authority=authority,
    )
    assert bound.question_authority.question_id == "Q1"


def test_red_missing_bound_question_evidence_is_rejected() -> None:
    api = _api()
    context, admitted, paper, authority = _roots(evidence_question_ids=("Q-OTHER",))
    _assert_rejected(api, (context, admitted, paper, authority))


def test_red_question_identity_is_exact_and_case_sensitive() -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    mismatched = replace(authority, question_id="q1")
    _assert_rejected(api, (context, admitted, paper, mismatched))


def test_red_evidence_question_identity_is_exact_and_case_sensitive() -> None:
    api = _api()
    context, admitted, paper, authority = _roots(
        evidence_question_ids=("q1",),
    )
    assert authority.question_id == "Q1"
    assert tuple(q.question_id for q in admitted.evidence.questions) == ("q1",)
    _assert_rejected(api, (context, admitted, paper, authority))


def test_red_submission_binding_is_exact_and_case_sensitive() -> None:
    api = _api()
    _, admitted, paper, authority = _roots()
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref="sub-p0b-1",
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    _assert_rejected(api, (context, admitted, paper, authority))


@pytest.mark.parametrize(
    "wrong_spec",
    [
        GradingSpecRef(id="SPEC-OTHER", version=1),
        GradingSpecRef(id="spec-p0b", version=1),
        GradingSpecRef(id="SPEC-P0B", version=2),
    ],
)
def test_red_context_spec_must_match_paper_spec(wrong_spec: GradingSpecRef) -> None:
    api = _api()
    _, admitted, paper, authority = _roots()
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=wrong_spec,
    )
    _assert_rejected(api, (context, admitted, paper, authority))


@pytest.mark.parametrize(
    "wrong_spec",
    [
        GradingSpecRef(id="SPEC-OTHER", version=1),
        GradingSpecRef(id="spec-p0b", version=1),
        GradingSpecRef(id="SPEC-P0B", version=2),
    ],
)
def test_red_question_authority_spec_must_match_paper_spec(
    wrong_spec: GradingSpecRef,
) -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    mismatched = replace(authority, grading_spec_ref=wrong_spec)
    _assert_rejected(api, (context, admitted, paper, mismatched))


def test_red_bound_question_must_exist_in_paper_authority() -> None:
    api = _api()
    context, admitted, _, authority = _roots()
    paper = _paper(expected_questions=(_expected("Q2"),))
    context = replace(context, grading_spec_ref=paper.grading_spec_ref)
    authority = replace(authority, grading_spec_ref=paper.grading_spec_ref)
    _assert_rejected(api, (context, admitted, paper, authority))


def test_red_scoring_authority_question_identity_must_match_bound_question() -> None:
    api = _api()
    paper = _paper(expected_questions=(_expected("Q2"),))
    q1_authority = _question_authority(
        _paper(expected_questions=(_expected("Q1"),)),
        question_id="Q1",
    )
    authority = replace(
        q1_authority,
        grading_spec_ref=paper.grading_spec_ref,
        question_id="Q2",
    )
    admitted = _admitted_evidence("Q2")
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    _assert_rejected(api, (context, admitted, paper, authority))


@pytest.mark.parametrize(
    "expected",
    [
        _expected("Q1", rubric_id="R-OTHER"),
        _expected("Q1", rubric_id="r-q1"),
        _expected("Q1", rubric_version=2),
    ],
)
def test_red_paper_expected_rubric_ref_must_match_scoring_authority(
    expected: ExpectedQuestionResult,
) -> None:
    api = _api()
    paper = _paper(expected_questions=(expected,))
    authority = _question_authority(
        _paper(expected_questions=(_expected("Q1"),)),
        question_id="Q1",
    )
    authority = replace(authority, grading_spec_ref=paper.grading_spec_ref)
    admitted = _admitted_evidence("Q1")
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    _assert_rejected(api, (context, admitted, paper, authority))


@pytest.mark.parametrize(
    "expected",
    [
        _expected("Q1", policy_id="P-OTHER"),
        _expected("Q1", policy_id="p-q1"),
        _expected("Q1", policy_version=2),
    ],
)
def test_red_paper_expected_policy_ref_must_match_scoring_authority(
    expected: ExpectedQuestionResult,
) -> None:
    api = _api()
    paper = _paper(expected_questions=(expected,))
    authority = _question_authority(
        _paper(expected_questions=(_expected("Q1"),)),
        question_id="Q1",
    )
    authority = replace(authority, grading_spec_ref=paper.grading_spec_ref)
    admitted = _admitted_evidence("Q1")
    context = GradingExecutionContext(
        grading_run_id="RUN-P0B-1",
        submission_ref=admitted.evidence.submission_ref,
        exam_ref="EXAM-P0B-1",
        grading_spec_ref=paper.grading_spec_ref,
    )
    _assert_rejected(api, (context, admitted, paper, authority))


@pytest.mark.parametrize("wrong_rubric_id", ["R-OTHER", "r-q1"])
def test_red_rubric_content_rubric_id_must_match_scoring_rubric_id(
    wrong_rubric_id: str,
) -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    mismatched_content = replace(
        authority.rubric_content,
        rubric_id=wrong_rubric_id,
    )
    _assert_rejected(
        api,
        (context, admitted, paper, replace(authority, rubric_content=mismatched_content)),
    )


@pytest.mark.parametrize("wrong_policy_id", ["P-OTHER", "p-q1"])
def test_red_rubric_content_policy_id_must_match_scoring_policy_id(
    wrong_policy_id: str,
) -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    mismatched_content = replace(
        authority.rubric_content,
        policy_id=wrong_policy_id,
    )
    _assert_rejected(
        api,
        (context, admitted, paper, replace(authority, rubric_content=mismatched_content)),
    )


class _ContextSubclass(GradingExecutionContext):
    pass


class _QuestionAuthoritySubclass(ResolvedQuestionAuthority):
    pass


@pytest.mark.parametrize("which", ["context", "question_authority"])
def test_red_ordinary_constructible_root_subclasses_are_rejected(which: str) -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    if which == "context":
        context = _ContextSubclass(
            grading_run_id=context.grading_run_id,
            submission_ref=context.submission_ref,
            exam_ref=context.exam_ref,
            grading_spec_ref=context.grading_spec_ref,
        )
    else:
        authority = _QuestionAuthoritySubclass(
            grading_spec_ref=authority.grading_spec_ref,
            question_id=authority.question_id,
            question_text=authority.question_text,
            context_policy=authority.context_policy,
            rubric_content=authority.rubric_content,
            scoring_authority=authority.scoring_authority,
        )
    _assert_rejected(api, (context, admitted, paper, authority))


@pytest.mark.parametrize("which", ["context", "admitted_evidence", "paper", "question_authority"])
def test_red_foreign_root_objects_are_rejected(which: str) -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    roots = {
        "context": context,
        "admitted_evidence": admitted,
        "paper": paper,
        "question_authority": authority,
    }
    roots[which] = object()
    with pytest.raises(api.QuestionEvaluationBindingError):
        api.bind_question_evaluation_inputs(
            context=roots["context"],
            admitted_evidence=roots["admitted_evidence"],
            paper_authority=roots["paper"],
            question_authority=roots["question_authority"],
        )


class _ExplodingSpec:
    def __init__(self) -> None:
        self.equal_calls = 0

    def __eq__(self, other: object) -> bool:
        del other
        self.equal_calls += 1
        raise AssertionError("question evidence binding touched hostile spec equality before exact-type rejection")


class _ExplodingRubricContent:
    def __init__(self) -> None:
        self.attribute_reads = 0

    @property
    def rubric_id(self):
        self.attribute_reads += 1
        raise AssertionError("question evidence binding touched hostile rubric_content.rubric_id")

    @property
    def policy_id(self):
        self.attribute_reads += 1
        raise AssertionError("question evidence binding touched hostile rubric_content.policy_id")


class _ExplodingScoringAuthority:
    def __init__(self) -> None:
        self.attribute_reads = 0

    @property
    def rubric(self):
        self.attribute_reads += 1
        raise AssertionError("question evidence binding touched hostile scoring_authority.rubric")

    @property
    def policy(self):
        self.attribute_reads += 1
        raise AssertionError("question evidence binding touched hostile scoring_authority.policy")


def test_red_question_authority_spec_foreign_object_is_rejected_before_equality_dispatch() -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    hostile = _ExplodingSpec()
    # ResolvedQuestionAuthority has no constructor-time validator.
    malformed = replace(authority, grading_spec_ref=hostile)
    _assert_rejected(api, (context, admitted, paper, malformed))
    assert hostile.equal_calls == 0


def test_red_foreign_rubric_content_is_rejected_before_nested_property_access() -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    hostile = _ExplodingRubricContent()
    malformed = replace(authority, rubric_content=hostile)
    _assert_rejected(api, (context, admitted, paper, malformed))
    assert hostile.attribute_reads == 0


def test_red_foreign_scoring_authority_is_rejected_before_nested_property_access() -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    hostile = _ExplodingScoringAuthority()
    malformed = replace(authority, scoring_authority=hostile)
    _assert_rejected(api, (context, admitted, paper, malformed))
    assert hostile.attribute_reads == 0


class _RubricContentSubclass(QuestionRubricAuthoringContent):
    pass


class _ScoringAuthoritySubclass(QuestionScoringAuthority):
    pass


def test_red_nested_rubric_content_requires_exact_type_not_subclass() -> None:
    context, admitted, paper, authority = _roots()
    subclass_content = _RubricContentSubclass(
        **{
            field.name: getattr(authority.rubric_content, field.name)
            for field in fields(QuestionRubricAuthoringContent)
        }
    )
    assert type(subclass_content) is _RubricContentSubclass
    api = _api()
    malformed = replace(authority, rubric_content=subclass_content)
    _assert_rejected(api, (context, admitted, paper, malformed))


def test_red_nested_scoring_authority_requires_exact_type_not_subclass() -> None:
    context, admitted, paper, authority = _roots()
    subclass_authority = _ScoringAuthoritySubclass(
        rubric=authority.scoring_authority.rubric,
        policy=authority.scoring_authority.policy,
    )
    assert type(subclass_authority) is _ScoringAuthoritySubclass
    api = _api()
    malformed = replace(authority, scoring_authority=subclass_authority)
    _assert_rejected(api, (context, admitted, paper, malformed))


class _StrSubclass(str):
    pass


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("question_id", ""),
        ("question_id", " Q1"),
        ("question_id", "Q1 "),
        ("question_id", _StrSubclass("Q1")),
        ("question_text", 123),
        ("question_text", _StrSubclass("Explain the result.")),
        ("context_policy", "DIRECT"),
    ],
)
def test_red_question_authority_weak_projection_fields_require_exact_types_and_values(
    field_name: str,
    value: object,
) -> None:
    api = _api()
    context, admitted, paper, authority = _roots()
    malformed = replace(authority, **{field_name: value})
    _assert_rejected(api, (context, admitted, paper, malformed))


def test_red_safe_representation_does_not_leak_protected_domain_content() -> None:
    roots = _privacy_roots()
    assert str(roots[2].minimum_score.as_decimal()) == _SCORING_MIN_SENTINEL
    assert str(roots[2].maximum_score.as_decimal()) == _SCORING_MAX_SENTINEL
    api = _api()
    bound = _bind(api, roots)
    for rendered in (repr(bound), str(bound)):
        for sentinel in _PRIVACY_SENTINELS[:-1]:
            assert sentinel not in rendered


def test_red_rich_safe_representation_does_not_dump_nested_rubric_or_scoring_details() -> None:
    roots = _rich_privacy_roots()
    authority = roots[3]
    policy = authority.scoring_authority.policy
    assert str(policy.gates[0].failure_ceiling.as_decimal()) == _GATE_SCORE_SENTINEL
    assert str(policy.caps[0].ceiling.as_decimal()) == _CAP_SCORE_SENTINEL
    assert str(policy.deductions[0].amount.as_decimal()) == _DEDUCTION_SCORE_SENTINEL
    assert str(policy.rounding.increment.as_decimal()) == _ROUNDING_SCORE_SENTINEL
    api = _api()
    bound = _bind(api, roots)
    forbidden_nested_repr = (
        repr(authority.rubric_content.criteria[0]),
        repr(authority.rubric_content.criteria[0].performance_levels[0]),
        repr(authority.scoring_authority.rubric.criteria[0]),
        repr(authority.scoring_authority.rubric.criteria[0].performance_levels[0]),
        repr(policy),
        repr(policy.positive_credit_dependencies[0]),
        repr(policy.gates[0]),
        repr(policy.caps[0]),
        repr(policy.deductions[0]),
        repr(policy.rounding),
    )
    for rendered in (repr(bound), str(bound)):
        for sentinel in _PRIVACY_SENTINELS[:-1]:
            assert sentinel not in rendered
        for nested_repr in forbidden_nested_repr:
            assert nested_repr not in rendered


def test_red_rich_expected_rejection_diagnostics_cover_optional_policy_shapes() -> None:
    context, admitted, paper, authority = _rich_privacy_roots()
    context = replace(context, submission_ref="SUB-P0B-RICH-PRIVACY-OTHER")
    assert context.submission_ref != admitted.evidence.submission_ref
    roots = (context, admitted, paper, authority)
    manifest = _privacy_sensitive_identity_manifest(roots)
    api = _api()
    with pytest.raises(api.QuestionEvaluationBindingError) as exc_info:
        _bind(api, roots)
    _assert_expected_rejection_diagnostics_are_private(
        exc_info.value,
        protected_objects=manifest,
    )


@pytest.mark.parametrize(
    "case_name",
    (
        "missing_evidence",
        "submission_mismatch",
        "context_paper_spec_mismatch",
        "question_paper_spec_mismatch",
        "question_absent_from_paper",
        "scoring_question_mismatch",
        "rubric_ref_mismatch",
        "policy_ref_mismatch",
        "rubric_content_mismatch",
        "policy_content_mismatch",
        "foreign_root",
        "weak_projection",
        "foreign_nested_authority",
    ),
)
def test_red_principal_expected_rejections_have_private_diagnostic_state(
    case_name: str,
) -> None:
    # Construct and assert the targeted reachable rejection before importing question evidence binding.
    roots, protected_objects, extra = _privacy_rejection_case(case_name)
    api = _api()
    with pytest.raises(api.QuestionEvaluationBindingError) as exc_info:
        _bind(api, roots)

    _assert_expected_rejection_diagnostics_are_private(
        exc_info.value,
        protected_objects=protected_objects,
    )

    for value in extra:
        if type(value) is _PrivacyForeignValue:
            assert value.repr_calls == 0
            assert value.equal_calls == 0
            assert value.attribute_reads == 0
            assert value.iter_calls == 0


def test_red_binding_is_deterministic_for_same_exact_roots_and_generates_no_new_identity() -> None:
    api = _api()
    roots = _roots()
    first = _bind(api, roots)
    second = _bind(api, roots)
    for bound in (first, second):
        assert bound.context is roots[0]
        assert bound.admitted_evidence is roots[1]
        assert bound.paper_authority is roots[2]
        assert bound.question_authority is roots[3]


def _semantic_snapshot(roots) -> tuple[object, ...]:
    context, admitted, paper, authority = roots
    return (
        context.grading_run_id,
        context.submission_ref,
        context.exam_ref,
        context.grading_spec_ref.id,
        context.grading_spec_ref.version,
        admitted.raw_payload_sha256,
        admitted.wire_schema_version,
        admitted.admission_policy_identity,
        tuple(
            (field.name, getattr(admitted.effective_policy_snapshot, field.name))
            for field in fields(type(admitted.effective_policy_snapshot))
        ),
        admitted.source_artifact_ref,
        repr(admitted.evidence),
        admitted.evidence.submission_ref,
        admitted.evidence.ocr_provenance,
        tuple(
            (
                question.question_id,
                question.answer_scope_ref,
                tuple(
                    (
                        block.block_id,
                        block.type.value,
                        block.content,
                        block.state.value,
                        block.page,
                        block.reading_order,
                    )
                    for block in question.blocks
                ),
                question.warnings,
            )
            for question in admitted.evidence.questions
        ),
        paper.grading_spec_ref.id,
        paper.grading_spec_ref.version,
        tuple(
            (
                expected.question_id,
                expected.rubric_ref.id,
                expected.rubric_ref.version,
                expected.scoring_policy_ref.id,
                expected.scoring_policy_ref.version,
                expected.scoring_policy_ref.scoring_semantics_version,
            )
            for expected in paper.expected_questions
        ),
        str(paper.minimum_score.as_decimal()),
        str(paper.maximum_score.as_decimal()),
        repr(paper),
        authority.grading_spec_ref.id,
        authority.grading_spec_ref.version,
        authority.question_id,
        authority.question_text,
        authority.context_policy.value,
        authority.rubric_content.rubric_id,
        authority.rubric_content.policy_id,
        repr(authority.rubric_content),
        tuple(
            (
                criterion.criterion_id,
                criterion.operational_description,
                criterion.evidence_requirement,
            )
            for criterion in authority.rubric_content.criteria
        ),
        authority.scoring_authority.rubric.rubric_id,
        authority.scoring_authority.rubric.version,
        authority.scoring_authority.rubric.question_id,
        authority.scoring_authority.policy.policy_id,
        authority.scoring_authority.policy.version,
        authority.scoring_authority.policy.question_id,
        authority.scoring_authority.policy.scoring_semantics_version,
        repr(authority.scoring_authority),
    )


def test_red_binding_does_not_mutate_any_input_root_or_nested_public_contract() -> None:
    api = _api()
    roots = _roots(evidence_question_ids=("Q1", "Q-UNRELATED"))
    root_ids_before = tuple(id(root) for root in roots)
    snapshot_before = _semantic_snapshot(roots)
    bound = _bind(api, roots)
    snapshot_after = _semantic_snapshot(roots)
    root_ids_after = tuple(id(root) for root in roots)
    assert snapshot_after == snapshot_before
    assert root_ids_after == root_ids_before
    assert bound.context is roots[0]
    assert bound.admitted_evidence is roots[1]
    assert bound.paper_authority is roots[2]
    assert bound.question_authority is roots[3]


@pytest.mark.parametrize(
    "field_name",
    ("context", "admitted_evidence", "paper_authority", "question_authority"),
)
@pytest.mark.parametrize("operation", ("assign", "delete"))
def test_red_bound_result_roots_are_ordinary_api_immutable(
    field_name: str,
    operation: str,
) -> None:
    api = _api()
    bound = _bind(api, _roots())
    expected = getattr(bound, field_name)
    if operation == "assign":
        with pytest.raises((AttributeError, TypeError)):
            setattr(bound, field_name, object())
    else:
        with pytest.raises((AttributeError, TypeError)):
            delattr(bound, field_name)
    assert getattr(bound, field_name) is expected


def test_red_existing_public_contracts_are_ordinary_api_immutable() -> None:
    context, admitted, paper, authority = _roots()
    with pytest.raises(FrozenInstanceError):
        context.submission_ref = "OTHER"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        admitted.evidence = admitted.evidence  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        paper.grading_spec_ref = paper.grading_spec_ref  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        authority.question_id = "Q2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        authority.rubric_content.rubric_id = "R-OTHER"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        authority.scoring_authority.policy.policy_id = "P-OTHER"  # type: ignore[misc]
    with pytest.raises(TypeError):
        admitted.evidence.questions[0] = admitted.evidence.questions[0]  # type: ignore[index]
