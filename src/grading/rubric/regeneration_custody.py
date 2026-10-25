"""Qualified governed result checks regeneration-to-draft custody; never issues grading approval.

The source-of-record port must authenticate teacher role, original generated
ancestor, current rubric revision and finalized-question revision. The write
port MUST atomically compare all expected revisions at the durable write and
idempotently bind ``operation_ref`` to exactly one immutable request. These
external guarantees cannot be manufactured by repeated in-process reads.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Protocol

from grading.contracts.errors import ScoringError
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.errors import RubricAuthoringError
from grading.rubric.lifecycle import RubricAuthoringVersion, RubricLifecycleState, TeacherApproval
from grading.rubric.compiler import CompiledRubricCandidate
from grading.rubric.linter import RubricLintResult, RubricLintIssue, RubricLintSeverity
from grading.rubric.models import (
    FinalizedQuestionScoringBasis, QuestionRubricAuthoringContent,
    RubricCompilationLimits, AuthoringCriterion, AuthoringPerformanceLevel, AuthoringRoundingRule,
    AuthoringPositiveCreditDependencyRule, AuthoringGateRule,
    AuthoringCapRule, AuthoringDeductionRule, AuthoringCriterionCondition,
)
from grading.rubric.fingerprint import (
    authoring_content_fingerprint, finalized_question_fingerprint,
)
from grading.rubric.regeneration import (
    RegenerationDisposition, propose_regenerated_draft,
)
from grading.rubric.resources import require_resource_admission


def _ref(value: object) -> bool:
    return (type(value) is str and bool(value) and value.strip() == value)


def _same_exact_values(observed: object, original: object) -> bool:
    """Compare the exact typed original across an untrusted effect callback.

    Dataclass equality alone silently admits ``True == 1`` and ``2.0 == 2``.
    Only the declared bounded rubric request's nested values are compared.
    """
    if type(observed) is not type(original):
        return False
    if is_dataclass(original):
        return all(_same_exact_values(getattr(observed, f.name), getattr(original, f.name))
                   for f in fields(original))
    if type(original) in (tuple, list):
        return len(observed) == len(original) and all(
            _same_exact_values(a, b) for a, b in zip(observed, original))
    if type(original) is dict:
        return observed.keys() == original.keys() and all(
            _same_exact_values(observed[k], original[k]) for k in original)
    return observed == original


def _valid_limits(limits: object) -> bool:
    if type(limits) is not RubricCompilationLimits:
        return False
    try:
        return all(type(getattr(limits, f.name)) is int and getattr(limits, f.name) > 0
                   for f in fields(limits))
    except AttributeError:
        return False


def _prevalidate_compilation_lint(compilation: object, limits: RubricCompilationLimits) -> bool:
    """Finite nested lint shape before executing the frozen compiler validator."""
    if type(compilation) is not CompiledRubricCandidate:
        return False
    result = compilation.lint_result
    if type(result) is not RubricLintResult or type(result.issues) is not tuple:
        return False
    budget = limits.max_serialized_authority_bytes
    if len(result.issues) > budget:
        return False
    for issue in result.issues:
        if (type(issue) is not RubricLintIssue
                or type(issue.severity) is not RubricLintSeverity):
            return False
        for field in (issue.code, issue.path, issue.message):
            if type(field) is not str or len(field) > budget:
                return False
            budget -= len(field)
    return True



def _bounded_text(value: object, maximum: int) -> bool:
    return type(value) is str and len(value) <= maximum


def _admitted_scoring_decimal(value: object) -> bool:
    """Validate the interior of an exact numeric wrapper before any copy.

    Frozen dataclasses do not prevent mutation via object.__setattr__. Reuse
    Numeric Profile v1; never infer numeric validity from the outer type.
    """
    if type(value) is not ScoringDecimal:
        return False
    try:
        inner = value.as_decimal()
        normalized = ScoringDecimal.from_raw(inner)
        return normalized.as_decimal().as_tuple() == inner.as_tuple()
    except (ScoringError, AttributeError, TypeError, ValueError, OverflowError):
        return False


def _precopy_content_within_limits(content: object, limits: object) -> bool:
    """Bound and re-admit generated content *before* copying or source contact.

    Call only Gradified constructors after checking the finite shapes of all
    nested fields. This prevents foreign nested objects from executing their
    own copy hooks; it does not manufacture institutional authenticity.
    """
    if type(content) is not QuestionRubricAuthoringContent or not _valid_limits(limits):
        return False
    try:
        if (not _ref(content.rubric_id) or not _ref(content.policy_id)
                or len(content.rubric_id) > limits.max_text_characters_per_field
                or len(content.policy_id) > limits.max_text_characters_per_field):
            return False
        for name, maximum in (
            ("criteria", limits.max_criteria),
            ("positive_credit_dependencies", limits.max_rules),
            ("gates", limits.max_rules),
            ("caps", limits.max_rules),
            ("deductions", limits.max_rules),
        ):
            group = getattr(content, name)
            if type(group) is not tuple or len(group) > maximum:
                return False
        if (len(content.positive_credit_dependencies) + len(content.gates)
                + len(content.caps) + len(content.deductions)
                + (content.rounding is not None) > limits.max_rules):
            return False
        if content.rounding is not None and type(content.rounding) is not AuthoringRoundingRule:
            return False
        for criterion in content.criteria:
            if (type(criterion) is not AuthoringCriterion
                    or type(criterion.performance_levels) is not tuple
                    or len(criterion.performance_levels) > limits.max_levels_per_criterion
                    or type(criterion.accepted_equivalents) is not tuple
                    or len(criterion.accepted_equivalents) > limits.max_accepted_equivalents_per_criterion
                    or any(type(level) is not AuthoringPerformanceLevel for level in criterion.performance_levels)):
                return False
        for group, rule_type, condition_name in (
            (content.positive_credit_dependencies, AuthoringPositiveCreditDependencyRule, "prerequisite_conditions"),
            (content.gates, AuthoringGateRule, "required_conditions"),
            (content.caps, AuthoringCapRule, "trigger_conditions"),
            (content.deductions, AuthoringDeductionRule, "trigger_conditions"),
        ):
            for rule in group:
                if type(rule) is not rule_type:
                    return False
                conditions = getattr(rule, condition_name)
                if type(conditions) is not tuple or len(conditions) > limits.max_conditions_per_rule:
                    return False
                for condition in conditions:
                    if (type(condition) is not AuthoringCriterionCondition
                            or type(condition.allowed_level_ids) is not tuple
                            or len(condition.allowed_level_ids) > limits.max_allowed_level_ids_per_condition):
                        return False
        # All resource-policy text fields and scoring numeric interiors must be
        # admitted before deepcopy or resource serialization. The model's
        # __post_init__ checks types, but it does not enforce text budgets or
        # validate a ScoringDecimal whose frozen interior was later replaced.
        maximum = limits.max_text_characters_per_field
        for criterion in content.criteria:
            if not all(_bounded_text(value, maximum) for value in (
                    criterion.criterion_id, criterion.operational_description,
                    criterion.evidence_requirement, *criterion.accepted_equivalents)):
                return False
            for level in criterion.performance_levels:
                if (not _bounded_text(level.level_id, maximum)
                        or not _bounded_text(level.operational_description, maximum)
                        or not _admitted_scoring_decimal(level.contribution)):
                    return False
        for group, condition_name in (
            (content.positive_credit_dependencies, "prerequisite_conditions"),
            (content.gates, "required_conditions"),
            (content.caps, "trigger_conditions"),
            (content.deductions, "trigger_conditions"),
        ):
            for rule in group:
                if not _bounded_text(rule.rule_id, maximum):
                    return False
                if (type(rule) is AuthoringPositiveCreditDependencyRule
                        and not _bounded_text(rule.target_criterion_id, maximum)):
                    return False
                for condition in getattr(rule, condition_name):
                    if (not _bounded_text(condition.criterion_id, maximum)
                            or any(not _bounded_text(level_id, maximum)
                                   for level_id in condition.allowed_level_ids)):
                        return False
        if not _admitted_scoring_decimal(content.minimum_score):
            return False
        for rule in content.gates:
            if not _admitted_scoring_decimal(rule.failure_ceiling):
                return False
        for rule in content.caps:
            if not _admitted_scoring_decimal(rule.ceiling):
                return False
        for rule in content.deductions:
            if not _admitted_scoring_decimal(rule.amount):
                return False
        if content.rounding is not None:
            if (not _bounded_text(content.rounding.rule_id, maximum)
                    or not _bounded_text(content.rounding.mode, maximum)
                    or not _admitted_scoring_decimal(content.rounding.increment)):
                return False
        # Reuse the frozen model contracts, rather than duplicating academic
        # validation. All nested objects above are exact expected types.
        content.__post_init__()
        for criterion in content.criteria:
            criterion.__post_init__()
            for level in criterion.performance_levels:
                level.__post_init__()
        for group, condition_name in (
            (content.positive_credit_dependencies, "prerequisite_conditions"),
            (content.gates, "required_conditions"),
            (content.caps, "trigger_conditions"),
            (content.deductions, "trigger_conditions"),
        ):
            for rule in group:
                rule.__post_init__()
                for condition in getattr(rule, condition_name):
                    condition.__post_init__()
        if content.rounding is not None:
            content.rounding.__post_init__()
        return True
    except (RubricAuthoringError, TypeError, ValueError, AttributeError, OverflowError):
        return False


def _admitted_bounded_content(content: object, basis: object, limits: object) -> bool:
    """Check trusted-envelope size before validating nested model invariants."""
    if (not _precopy_content_within_limits(content, limits)
            or type(basis) is not FinalizedQuestionScoringBasis
            or type(basis.question_id) is not str
            or len(basis.question_id) > limits.max_text_characters_per_field
            or not _admitted_scoring_decimal(basis.max_marks)):
        return False
    try:
        # The resource checker examines cardinalities and text size before its
        # own canonical serialization. Malformed callback records are denied.
        require_resource_admission(content, finalized_question=basis, limits=limits)
        basis.__post_init__()
        content.__post_init__()
        return True
    except (RubricAuthoringError, TypeError, ValueError, AttributeError, OverflowError):
        return False


@dataclass(frozen=True, slots=True)
class AuthorizedRegenerationRead:
    """One *port-qualified* snapshot, not self-authenticating claims.

    Source MUST prove baseline-generated ancestry, actor authorization and
    authentic source revision identities; a content hash alone is insufficient.
    """
    actor_ref: str
    rubric_ref: str
    current_revision_ref: str
    baseline_revision_ref: str
    question_revision_ref: str
    baseline_generated: QuestionRubricAuthoringContent
    current_teacher: RubricAuthoringVersion
    finalized_question: FinalizedQuestionScoringBasis
    limits: RubricCompilationLimits


@dataclass(frozen=True, slots=True)
class ConditionalDraftWrite:
    """Atomic compare-and-persist request including all original custody.

    The adapter must compare live current version, finalized-question version,
    baseline ancestry and authorized actor at the durable effect. A repeated
    operation_ref with different bytes MUST NOT create another draft.
    """
    operation_ref: str
    authority: AuthorizedRegenerationRead
    draft: RubricAuthoringVersion
    approved_limits: RubricCompilationLimits


class DraftWriteState(str, Enum):
    COMMITTED = 'COMMITTED'
    STALE = 'STALE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class DraftWriteReceipt:
    state: DraftWriteState
    request: ConditionalDraftWrite


class AuthorizedRegenerationSource(Protocol):
    def read_authorized(self, *, actor_ref: str, rubric_ref: str) -> AuthorizedRegenerationRead | None: ...


class ConditionalDraftStore(Protocol):
    def compare_and_persist(self, request: ConditionalDraftWrite) -> DraftWriteReceipt: ...
    def lookup_operation(self, request: ConditionalDraftWrite) -> DraftWriteReceipt | None: ...


class CustodyState(str, Enum):
    STORED = 'STORED'
    CONFLICT = 'CONFLICT'
    UNCHANGED = 'UNCHANGED'
    BLOCKED = 'BLOCKED'
    UNKNOWN = 'UNKNOWN'
    SOURCE_UNAVAILABLE = 'SOURCE_UNAVAILABLE'


@dataclass(frozen=True, slots=True)
class CustodyOutcome:
    state: CustodyState
    request: ConditionalDraftWrite | None = None
    conflicts: tuple[str, ...] = ()

    @property
    def authorizes_activation(self) -> bool:
        return False

    @property
    def authorizes_grading(self) -> bool:
        return False


def _admitted_read(read: object, actor_ref: str, rubric_ref: str) -> bool:
    try:
        return _admitted_read_checked(read, actor_ref, rubric_ref)
    except (RubricAuthoringError, TypeError, ValueError, AttributeError, OverflowError):
        return False


def _admitted_read_checked(read: object, actor_ref: str, rubric_ref: str) -> bool:
    if type(read) is not AuthorizedRegenerationRead:
        return False
    if (not all(_ref(v) for v in (
            read.actor_ref, read.rubric_ref, read.current_revision_ref,
            read.baseline_revision_ref, read.question_revision_ref))
            or read.actor_ref != actor_ref or read.rubric_ref != rubric_ref
            or type(read.current_teacher) is not RubricAuthoringVersion
            or type(read.finalized_question) is not FinalizedQuestionScoringBasis
            or not _valid_limits(read.limits)):
        return False
    current = read.current_teacher
    if (type(current.content) is not QuestionRubricAuthoringContent
            or type(current.finalized_question) is not FinalizedQuestionScoringBasis
            or type(current.version) is not int
            or current.version <= 0):
        return False
    # In particular, the finalized-question ID must be admitted before the
    # first fingerprint, and both supplied rubrics must be bounded before the
    # lifecycle validator traverses or serializes them.
    if (not _admitted_bounded_content(read.baseline_generated, read.finalized_question, read.limits)
            or not _admitted_bounded_content(current.content, current.finalized_question, read.limits)):
        return False
    try:
        if current.compilation is not None:
            if not _prevalidate_compilation_lint(current.compilation, read.limits):
                return False
            current.compilation.__post_init__()
        if current.approval is not None:
            if type(current.approval) is not TeacherApproval:
                return False
            current.approval.__post_init__()
        current.__post_init__()
        return (current.content.rubric_id == rubric_ref
                and read.baseline_generated.rubric_id == rubric_ref
                and read.baseline_generated.policy_id == current.content.policy_id
                and _same_exact_values(current.finalized_question, read.finalized_question)
                and current.finalized_question_hash == finalized_question_fingerprint(read.finalized_question))
    except (RubricAuthoringError, TypeError, ValueError, AttributeError, OverflowError):
        return False



def _locally_admitted_original(request: object) -> bool:
    try:
        return _locally_admitted_original_checked(request)
    except (RubricAuthoringError, TypeError, ValueError, AttributeError, OverflowError):
        return False


def _locally_admitted_original_checked(request: object) -> bool:
    """Check locally determinable draft lineage before independent recovery.

    This is *not* institutional authentication of a recovered operation: the
    installed store remains responsible for original-key and byte identity.
    """
    if type(request) is not ConditionalDraftWrite or not _ref(request.operation_ref):
        return False
    authority = request.authority
    if (not _valid_limits(request.approved_limits)
            or type(authority) is not AuthorizedRegenerationRead
            or not _same_exact_values(authority.limits, request.approved_limits)):
        return False
    if (type(authority) is not AuthorizedRegenerationRead
            or not _admitted_read(authority, authority.actor_ref, authority.rubric_ref)):
        return False
    draft = request.draft
    previous = authority.current_teacher
    if (type(draft) is not RubricAuthoringVersion
            or type(draft.content) is not QuestionRubricAuthoringContent
            or type(draft.finalized_question) is not FinalizedQuestionScoringBasis):
        return False
    # Untrusted recovered requests may contain altered nested Python objects.
    # Admit the entire finite academic draft before any cross-record equality
    # (which could invoke a foreign __eq__ and escape the controlled outcome).
    if not _admitted_bounded_content(draft.content, draft.finalized_question, authority.limits):
        return False
    # The recovered draft is untrusted, including nominally frozen metadata.
    # Do not perform cross-record hash equality until both fingerprints are
    # exact primitives; the lifecycle validator checks their full SHA-256
    # syntax and correspondence to the admitted content below.
    if (type(draft.source_content_hash) is not str
            or type(draft.finalized_question_hash) is not str
            or len(draft.source_content_hash) != 64
            or len(draft.finalized_question_hash) != 64):
        return False
    if (draft.state is not RubricLifecycleState.DRAFT
            or type(draft.version) is not int
            or type(previous.version) is not int
            or draft.version != previous.version + 1
            or draft.approval is not None or draft.compilation is not None
            or draft.activation_limits is not None
            or draft.activation_limits_hash is not None
            or draft.content.rubric_id != authority.rubric_ref
            or draft.content.policy_id != previous.content.policy_id
            or draft.finalized_question != authority.finalized_question
            or (draft.source_content_hash == previous.source_content_hash
                and draft.finalized_question_hash == previous.finalized_question_hash)):
        return False
    try:
        for content in (authority.baseline_generated, previous.content, draft.content):
            require_resource_admission(content, finalized_question=authority.finalized_question,
                                       limits=authority.limits)
        if not _admitted_bounded_content(draft.content, draft.finalized_question, authority.limits):
            return False
        draft.__post_init__()
        # Re-admit nested compiled and teacher-approval evidence, not only
        # equal-valued links on the outer authoring version.
        if previous.compilation is not None:
            if type(previous.compilation) is not CompiledRubricCandidate:
                return False
            previous.compilation.__post_init__()
        if previous.approval is not None:
            if type(previous.approval) is not TeacherApproval:
                return False
            previous.approval.__post_init__()
        previous.__post_init__()
        return (previous.source_content_hash == authoring_content_fingerprint(previous.content)
                and previous.finalized_question_hash == finalized_question_fingerprint(previous.finalized_question)
                and draft.source_content_hash == authoring_content_fingerprint(draft.content)
                and draft.finalized_question_hash == finalized_question_fingerprint(draft.finalized_question))
    except (RubricAuthoringError, TypeError, ValueError, AttributeError):
        return False


def propose_and_persist_regeneration(*, source: AuthorizedRegenerationSource,
                                     store: ConditionalDraftStore,
                                     actor_ref: str, rubric_ref: str,
                                     operation_ref: str,
                                     newly_generated: QuestionRubricAuthoringContent,
                                     approved_limits: RubricCompilationLimits | None = None) -> CustodyOutcome:
    """One authorized read, one bounded pure merge, at most one conditional write.

    approved_limits MUST come from independent, reviewed system configuration.
    Missing/mismatched policy blocks before merge or durable write.

    UNKNOWN is never automatically retried. A lost response must be reconciled
    by the qualified store using the original operation_ref and request, never
    by synthesizing a second write or claiming an approval.
    """
    if (not _ref(actor_ref) or not _ref(rubric_ref) or not _ref(operation_ref)
            or type(newly_generated) is not QuestionRubricAuthoringContent
            or newly_generated.rubric_id != rubric_ref
            or not _precopy_content_within_limits(newly_generated, approved_limits)):
        return CustodyOutcome(CustodyState.BLOCKED)
    # The academic source cannot select an arbitrarily permissive system budget.
    # The caller must supply a separately qualified explicit engine policy.
    # It remains the deployment owner's duty to authenticate that policy.
    try:
        generated_original = deepcopy(newly_generated)
        limits_original = deepcopy(approved_limits)
    except Exception:
        return CustodyOutcome(CustodyState.BLOCKED)
    try:
        read = source.read_authorized(actor_ref=actor_ref, rubric_ref=rubric_ref)
    except Exception:
        # No draft-write contact has occurred, so this is not an ambiguous write.
        return CustodyOutcome(CustodyState.SOURCE_UNAVAILABLE)
    if (not _same_exact_values(newly_generated, generated_original)
            or not _same_exact_values(approved_limits, limits_original)):
        return CustodyOutcome(CustodyState.BLOCKED)
    if not _admitted_read(read, actor_ref, rubric_ref):
        return CustodyOutcome(CustodyState.BLOCKED)
    if not _same_exact_values(read.limits, limits_original):
        return CustodyOutcome(CustodyState.BLOCKED)
    # The adapter retains ownership of its record. Validate a bounded record
    # before copying, then re-admit and use ONLY the independently retained
    # snapshot: a later adapter-side mutation must not rewrite our draft.
    try:
        admitted_source = deepcopy(read)
    except Exception:
        return CustodyOutcome(CustodyState.BLOCKED)
    if (not _same_exact_values(read, admitted_source)
            or not _admitted_read(admitted_source, actor_ref, rubric_ref)):
        return CustodyOutcome(CustodyState.BLOCKED)
    read = admitted_source
    if not _admitted_bounded_content(newly_generated, read.finalized_question, limits_original):
        return CustodyOutcome(CustodyState.BLOCKED)
    try:
        # Resource limits are independently qualified; admission
        # precedes this function's fingerprinting, mapping and merging.
        for content in (read.baseline_generated, read.current_teacher.content, newly_generated):
            require_resource_admission(content, finalized_question=read.finalized_question,
                                       limits=read.limits)
        proposed = propose_regenerated_draft(
            baseline_generated=read.baseline_generated,
            current_teacher=read.current_teacher,
            newly_generated=newly_generated,
            finalized_question=read.finalized_question,
            expected_current_hash=read.current_teacher.source_content_hash,
            expected_baseline_hash=authoring_content_fingerprint(read.baseline_generated),
        )
        if proposed.disposition is RegenerationDisposition.CONFLICT:
            return CustodyOutcome(CustodyState.CONFLICT, conflicts=proposed.conflicts)
        if proposed.disposition is RegenerationDisposition.UNCHANGED:
            return CustodyOutcome(CustodyState.UNCHANGED)
        draft = proposed.draft
        if (type(draft) is not RubricAuthoringVersion
                or draft.state is not RubricLifecycleState.DRAFT
                or draft.version != read.current_teacher.version + 1
                or draft.approval is not None or draft.compilation is not None):
            return CustodyOutcome(CustodyState.BLOCKED)
        require_resource_admission(draft.content, finalized_question=draft.finalized_question,
                                   limits=read.limits)
    except (RubricAuthoringError, TypeError, ValueError, AttributeError, OverflowError):
        return CustodyOutcome(CustodyState.BLOCKED)
    # A source or merge callback may not substitute the originally supplied
    # generator content and still create a positive draft operation.
    if (not _same_exact_values(newly_generated, generated_original)
            or not _same_exact_values(approved_limits, limits_original)):
        return CustodyOutcome(CustodyState.BLOCKED)
    request = ConditionalDraftWrite(operation_ref, read, draft, limits_original)
    # Retain independent custody of original values before effectful callback.
    # A frozen dataclass is not sufficient when a Python callback can replace
    # fields by object.__setattr__, including on nested authority records.
    original = deepcopy(request)
    if not _locally_admitted_original(original):
        return CustodyOutcome(CustodyState.BLOCKED)
    # The potentially effectful adapter receives an isolated request, never
    # the retained original or the source-owned authority object. A dishonest
    # adapter can still forge a receipt: actual atomic storage is an external
    # conformance guarantee, not a fact inferred from Python object equality.
    effect_request = deepcopy(original)
    try:
        receipt = store.compare_and_persist(effect_request)
    except Exception:
        return CustodyOutcome(CustodyState.UNKNOWN, original)
    if (not _same_exact_values(effect_request, original)
            or type(receipt) is not DraftWriteReceipt
            or type(receipt.state) is not DraftWriteState
            or type(receipt.request) is not ConditionalDraftWrite
            or not _same_exact_values(receipt.request, original)):
        return CustodyOutcome(CustodyState.UNKNOWN, original)
    if receipt.state is DraftWriteState.COMMITTED:
        return CustodyOutcome(CustodyState.STORED, original)
    if receipt.state is DraftWriteState.STALE:
        return CustodyOutcome(CustodyState.BLOCKED, original)
    return CustodyOutcome(CustodyState.UNKNOWN, original)


def recover_regeneration_write(*, store: ConditionalDraftStore,
                               original: ConditionalDraftWrite) -> CustodyOutcome:
    """Read-only reconciliation of UNKNOWN by immutable original request.

    A missing/mismatched receipt proves neither abort nor commit. Never issue
    another compare_and_persist call as part of recovery.
    """
    if not _locally_admitted_original(original):
        return CustodyOutcome(CustodyState.BLOCKED)
    retained = deepcopy(original)
    # Lookup receives its own detached request so that a buggy store cannot
    # mutate the recovery identity retained by the engine or caller.
    lookup_request = deepcopy(retained)
    try:
        receipt = store.lookup_operation(lookup_request)
    except Exception:
        return CustodyOutcome(CustodyState.UNKNOWN, retained)
    if (not _same_exact_values(lookup_request, retained)
            or not _same_exact_values(original, retained)
            or type(receipt) is not DraftWriteReceipt
            or type(receipt.state) is not DraftWriteState
            or type(receipt.request) is not ConditionalDraftWrite
            or not _same_exact_values(receipt.request, retained)):
        return CustodyOutcome(CustodyState.UNKNOWN, retained)
    if receipt.state is DraftWriteState.COMMITTED:
        return CustodyOutcome(CustodyState.STORED, retained)
    if receipt.state is DraftWriteState.STALE:
        return CustodyOutcome(CustodyState.BLOCKED, retained)
    return CustodyOutcome(CustodyState.UNKNOWN, retained)
