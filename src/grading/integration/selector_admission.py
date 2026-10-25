"""Admit bounded classification and policy inputs before evaluator selection.

This module consumes authority from a trusted composition root; neither source IDs,
configuration strings, Python object identity, nor a boolean response authenticate
that root. The root MUST retain custody of the selected sources and admission port.
Concrete adapters MUST bound their own network/serialization ingestion before
materializing typed classification/policy records; see ``bounded_source_bytes``.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from inspect import getattr_static
from typing import BinaryIO, Callable, Protocol

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.capability_registry import EvaluatorCapabilitySource
from grading.contracts.capability import EvaluatorCapabilityRef
from grading.contracts.evaluation import EvaluatorMetadata
from grading.contracts.evaluator_selection import (
    EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION,
    EvaluatorSelectionPolicy,
    EvaluatorSelectionPolicyRef,
    EvaluatorSelectionRule,
    QuestionEvaluationClassification,
    validate_question_evaluation_classification,
)
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.evaluator_selection import (
    QuestionClassificationBindingError,
    QuestionEvaluationClassificationSource,
    ResolvedQuestionEvaluatorSelection,
    _validate_question_authority,
    resolve_question_evaluator_selection,
)


# Hard ceilings for this versioned *engineering* envelope, not academic policy.
# Deployed selections MUST supply an approved stricter/equal limit set explicitly.
_MAX_RULES = 256
_MAX_FIELD_CODEPOINTS = 256
_MAX_TEXT_CODEPOINTS = 65_536
_MAX_SOURCE_BYTES = 1_048_576
# Version *representation* envelope for this admission boundary only. This
# is not a change to the positive-integer semantics of frozen evaluator capability resolution / evaluator selection.
_MAX_VERSION_BITS = 256


class SelectionAdmissionDenied(Exception):
    """The trusted composition authority did not admit these exact bindings."""


class SelectionAdmissionUnavailable(Exception):
    """The separately trusted admission authority could not decide."""


class SelectionSourceContractError(Exception):
    """A previously admitted source did not satisfy its structural contract."""


class SelectionSourceReadError(Exception):
    """An admitted upstream selection-source read failed."""


class SelectorResourceLimitError(Exception):
    """The selected engineering envelope is invalid or has been exhausted."""


@dataclass(frozen=True, slots=True)
class SelectorResourceLimits:
    schema_version: str
    max_policy_rules: int
    max_identifier_codepoints: int
    max_total_text_codepoints: int
    max_source_bytes: int


@dataclass(frozen=True, slots=True)
class ConfiguredSelectionSources:
    """Configuration *references*, NOT self-authenticating provenance tokens."""

    grading_spec_ref: GradingSpecRef
    question_id: str
    classification_source_id: str
    selection_policy_source_id: str
    capability_source_id: str
    configuration_ref: str
    expected_policy_ref: EvaluatorSelectionPolicyRef


@dataclass(frozen=True, slots=True)
class SelectionAdmissionContext:
    grading_spec_ref: GradingSpecRef
    question_id: str
    context_policy: ContextPolicy


class SelectionSourceAdmissionAuthority(Protocol):
    """Trusted root-owned decision, not arbitrary caller-provided approval data."""

    def authorize_selection_sources(
        self, *, context: SelectionAdmissionContext, config: ConfiguredSelectionSources,
        limits: SelectorResourceLimits,
        classification_source: QuestionEvaluationClassificationSource | DeferredBinaryClassificationSource,
        policy_stream_source: SelectionPolicyStreamSource | DeferredBinaryPolicySource,
        capability_source: EvaluatorCapabilitySource,
    ) -> bool:
        ...


class SelectionPolicyStreamSource(Protocol):
    """Adapter must yield one rule at a time, without pre-buffering all rules.

    Production-facing source methods must be statically discoverable on their
    objects; methods synthesized only via __getattr__ are unsupported.
    """

    def read_policy_header(self) -> tuple[str, EvaluatorSelectionPolicyRef]:
        ...

    def iter_policy_rules(self) -> Iterator[EvaluatorSelectionRule]:
        ...


@dataclass(frozen=True, slots=True)
class DeferredBinaryClassificationSource:
    """A trusted-root-selected *deferred* raw ingress adapter description.

    The factory is not invoked by construction. After selection-source admission,
    the private operation budget reads bytes before invoking the supplied decoder.
    Concrete production decoders remain independently trusted/qualified; this is
    intentionally not a vendor serialization format or a source authenticator.
    """

    open_reader: Callable[[], BinaryIO]
    decode: Callable[[bytes], QuestionEvaluationClassification]


@dataclass(frozen=True, slots=True)
class DeferredBinaryPolicySource:
    """Deferred bytes with strictly separated header decode and rule acquisition.

    ``decode_header`` MUST parse only the header. Rule-side work is allowed
    only in ``iter_rules``, after exact header/revision admission. Decoders are
    trusted adapter code requiring separate concrete qualification.
    """

    open_reader: Callable[[], BinaryIO]
    decode_header: Callable[[bytes], tuple[str, EvaluatorSelectionPolicyRef]]
    iter_rules: Callable[[bytes], Iterator[EvaluatorSelectionRule]]


def _close_deferred_reader(reader: object) -> None:
    """Close an admitted reader if it declares close; never hide a broken descriptor.

    Optional absence is supported. A declared but broken/non-callable close is
    not equivalent to absence. This uses the same explicit-method rule as read().
    """
    missing = object()
    try:
        declared = getattr_static(reader, "close", missing)
    except Exception as exc:
        raise SelectionSourceReadError("Deferred binary reader close inspection failed.") from exc
    if declared is missing:
        return
    close = _source_method(reader, "close", "Deferred binary reader close")
    try:
        close()
    except Exception as exc:
        raise SelectionSourceReadError("Deferred admitted binary source close failed.") from exc


class _OperationByteBudget:
    """Per-selection aggregate of admitted raw bytes across deferred sources."""

    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0

    def read(self, opener: Callable[[], BinaryIO]) -> bytes:
        try:
            reader = opener()
        except Exception as exc:
            raise SelectionSourceReadError("Deferred admitted binary source could not be opened.") from exc
        try:
            # The +1 detection probe is not permission to admit an extra byte.
            result = _read_binary_with_budget(reader, self.maximum - self.used)
        except BaseException as primary:
            # Never replace a primary read/contract/resource failure with a
            # secondary cleanup failure; record that cleanup also failed.
            try:
                _close_deferred_reader(reader)
            except Exception as cleanup:
                primary.add_note(
                    "Secondary deferred-reader cleanup failure: "
                    + type(cleanup).__name__
                )
            raise
        _close_deferred_reader(reader)
        self.used += len(result)
        return result


@dataclass(slots=True)
class _AdmittedClassificationBinaryPort:
    opener: Callable[[], BinaryIO]
    decoder: Callable[[bytes], QuestionEvaluationClassification]
    budget: _OperationByteBudget

    def resolve_question_evaluation_classification(
        self, *, grading_spec_ref: GradingSpecRef, question_id: str
    ) -> QuestionEvaluationClassification:
        data = self.budget.read(self.opener)
        try:
            return self.decoder(data)
        except Exception as exc:
            raise SelectionSourceReadError("Admitted binary classification decoder failed.") from exc


@dataclass(slots=True)
class _AdmittedPolicyBinaryPort:
    opener: Callable[[], BinaryIO]
    header_decoder: Callable[[bytes], tuple[str, EvaluatorSelectionPolicyRef]]
    rules_decoder: Callable[[bytes], Iterator[EvaluatorSelectionRule]]
    budget: _OperationByteBudget
    _data: bytes | None = None

    def read_policy_header(self) -> tuple[str, EvaluatorSelectionPolicyRef]:
        if self._data is None:
            self._data = self.budget.read(self.opener)
        try:
            # Crucial: never acquire/construct the iterator at this stage.
            return self.header_decoder(self._data)
        except Exception as exc:
            raise SelectionSourceReadError("Admitted binary policy header decoding failed.") from exc

    def iter_policy_rules(self) -> Iterator[EvaluatorSelectionRule]:
        if self._data is None:
            raise SelectionSourceContractError("Policy header was not admitted before rule access.")
        try:
            return self.rules_decoder(self._data)
        except Exception as exc:
            raise SelectionSourceReadError("Admitted binary policy rule decoding failed.") from exc


@dataclass(slots=True)
class _FixedClassificationSource:
    value: QuestionEvaluationClassification

    def resolve_question_evaluation_classification(
        self, *, grading_spec_ref: GradingSpecRef, question_id: str
    ) -> QuestionEvaluationClassification:
        if (grading_spec_ref != self.value.grading_spec_ref or
                question_id != self.value.question_id):
            raise QuestionClassificationBindingError("Pre-admitted classification identity changed.")
        return self.value


@dataclass(slots=True)
class _FixedPolicySource:
    value: EvaluatorSelectionPolicy

    def resolve_evaluator_selection_policy(self) -> EvaluatorSelectionPolicy:
        return self.value


@dataclass(slots=True)
class _AdmittedCapabilitySource:
    """Retains one declared, admitted lookup callable for frozen evaluator capability resolution.

    evaluator capability resolution continues to own all lookup/record result and exception semantics.
    """

    lookup: Callable[..., object]

    def find_exact_capabilities(self, *, capability_ref: EvaluatorCapabilityRef):
        return self.lookup(capability_ref=capability_ref)


def _exact_fields(value: object, names: tuple[str, ...],
                  error_type: type[Exception], owner: str) -> dict[str, object]:
    """Read exact-contract fields without executing a foreign nested property.

    Dataclass instances can be damaged after construction with object.__delattr__.
    Missing fields are malformed at their owning boundary, not raw AttributeError.
    The owner must check exact type before calling this helper.
    """
    try:
        return {name: object.__getattribute__(value, name) for name in names}
    except AttributeError as exc:
        raise error_type(f"{owner} is missing a required field.") from exc


def _validate_limits(limits: SelectorResourceLimits) -> None:
    if type(limits) is not SelectorResourceLimits:
        raise SelectorResourceLimitError("An explicitly selected version-1 resource profile is required.")
    fields = _exact_fields(
        limits, ("schema_version", "max_policy_rules", "max_identifier_codepoints",
                 "max_total_text_codepoints", "max_source_bytes"),
        SelectorResourceLimitError, "Selected resource profile",
    )
    if type(fields["schema_version"]) is not str or fields["schema_version"] != "1":
        raise SelectorResourceLimitError("An explicitly selected version-1 resource profile is required.")
    ceilings = (
        (fields["max_policy_rules"], _MAX_RULES),
        (fields["max_identifier_codepoints"], _MAX_FIELD_CODEPOINTS),
        (fields["max_total_text_codepoints"], _MAX_TEXT_CODEPOINTS),
        (fields["max_source_bytes"], _MAX_SOURCE_BYTES),
    )
    if any(type(value) is not int or not 0 < value <= ceiling for value, ceiling in ceilings):
        raise SelectorResourceLimitError("Selected limits must be finite positive integers within hard ceilings.")


def _bounded_identifier(
    value: object, *, name: str, maximum: int,
    invalid_error: type[Exception] = SelectionSourceContractError,
) -> int:
    """Separate malformed data from a well-formed identifier over the budget.

    Exact type/emptiness are cheap to check before any string scan. The length
    check precedes whitespace validation to bound the latter's work.
    """
    if type(value) is not str or not value:
        raise invalid_error(f"{name} is not a valid identifier.")
    if len(value) > maximum:
        raise SelectorResourceLimitError(f"{name} exceeds the admitted identifier budget.")
    if value.strip() != value:
        raise invalid_error(f"{name} has disallowed surrounding whitespace.")
    return len(value)


def _bounded_version(
    value: object, *, name: str, invalid_error: type[Exception] = SelectionSourceContractError
) -> int:
    """Bound transport representation, not the frozen positive-version domain."""
    if type(value) is not int or value < 1:
        raise invalid_error(f"{name} must be a positive exact integer.")
    if value.bit_length() > _MAX_VERSION_BITS:
        raise SelectorResourceLimitError(f"{name} exceeds the admitted version representation limit.")
    return value


def _snapshot_spec_ref(
    value: GradingSpecRef, *, invalid_error: type[Exception] = SelectionSourceContractError,
) -> GradingSpecRef:
    if type(value) is not GradingSpecRef:
        raise invalid_error("An exact grading-spec reference is required.")
    fields = _exact_fields(value, ("id", "version"), invalid_error, "Grading-spec reference")
    _bounded_version(fields["version"], name="grading_spec_ref.version", invalid_error=invalid_error)
    return GradingSpecRef(id=fields["id"], version=fields["version"])


def _snapshot_config(
    value: ConfiguredSelectionSources, limits: SelectorResourceLimits
) -> ConfiguredSelectionSources:
    if type(value) is not ConfiguredSelectionSources:
        raise SelectionAdmissionDenied("Configured selection-source record is invalid.")
    fields = _exact_fields(
        value, ("grading_spec_ref", "question_id", "classification_source_id",
                "selection_policy_source_id", "capability_source_id", "configuration_ref",
                "expected_policy_ref"),
        SelectionAdmissionDenied, "Configured source record",
    )
    spec = fields["grading_spec_ref"]
    policy = fields["expected_policy_ref"]
    if type(spec) is not GradingSpecRef or type(policy) is not EvaluatorSelectionPolicyRef:
        raise SelectionAdmissionDenied("Configured source identities must be exact references.")
    spec_fields = _exact_fields(spec, ("id", "version"), SelectionAdmissionDenied, "Configured spec reference")
    policy_fields = _exact_fields(policy, ("policy_id", "version"), SelectionAdmissionDenied,
                                  "Configured policy reference")
    for name in ("question_id", "classification_source_id", "selection_policy_source_id",
                 "capability_source_id", "configuration_ref"):
        _bounded_identifier(fields[name], name=name, maximum=limits.max_identifier_codepoints,
                            invalid_error=SelectionAdmissionDenied)
    _bounded_identifier(spec_fields["id"], name="configured grading_spec_ref.id",
                        maximum=limits.max_identifier_codepoints, invalid_error=SelectionAdmissionDenied)
    _bounded_identifier(policy_fields["policy_id"], name="configured expected_policy_ref.policy_id",
                        maximum=limits.max_identifier_codepoints, invalid_error=SelectionAdmissionDenied)
    _bounded_version(spec_fields["version"], name="configured grading_spec_ref.version",
                     invalid_error=SelectionAdmissionDenied)
    _bounded_version(policy_fields["version"], name="expected_policy_ref.version",
                     invalid_error=SelectionAdmissionDenied)
    return ConfiguredSelectionSources(
        grading_spec_ref=_snapshot_spec_ref(spec, invalid_error=SelectionAdmissionDenied),
        question_id=fields["question_id"],
        classification_source_id=fields["classification_source_id"],
        selection_policy_source_id=fields["selection_policy_source_id"],
        capability_source_id=fields["capability_source_id"],
        configuration_ref=fields["configuration_ref"],
        expected_policy_ref=EvaluatorSelectionPolicyRef(
            policy_fields["policy_id"], policy_fields["version"],
        ),
    )


def _snapshot_limits(value: SelectorResourceLimits) -> SelectorResourceLimits:
    fields = _exact_fields(
        value, ("schema_version", "max_policy_rules", "max_identifier_codepoints",
                "max_total_text_codepoints", "max_source_bytes"),
        SelectorResourceLimitError, "Resource profile",
    )
    return SelectorResourceLimits(**fields)


def _source_method(source: object, name: str, label: str):
    """Acquire an explicitly declared port method exactly once.

    Dynamic __getattr__ methods are intentionally unsupported. Static
    inspection is done before ordinary attribute acquisition to prevent
    executing a dynamic getter simply to discover a missing interface.
    Raising descriptors on declared methods are source operation failures.
    """
    missing = object()
    try:
        declared = getattr_static(source, name, missing)
    except Exception as exc:
        raise SelectionSourceReadError(
            f"{label} method declaration inspection failed."
        ) from exc
    if declared is missing:
        raise SelectionSourceContractError(f"{label} has no declared method.")
    try:
        method = getattr(source, name)
    except Exception as exc:
        raise SelectionSourceReadError(f"{label} method lookup failed.") from exc
    if not callable(method):
        raise SelectionSourceContractError(f"{label} method is not callable.")
    return method


def _admit_rule_iterator(candidate: object) -> object:
    """Verify the actual Python iterator protocol, not an instance shadow.

    Special methods are dispatched on the type by Python itself. The structural
    inspection runs before the one real iter() call, and method declarations
    are checked again afterward to reject detectable init-time mutation.
    This is contract admission, not a sandbox for malicious in-process code.
    """
    missing = object()
    candidate_type = type(candidate)
    declared_methods = []
    for special in ("__iter__", "__next__"):
        try:
            declared = getattr_static(candidate_type, special, missing)
        except Exception as exc:
            raise SelectionSourceContractError("Cannot inspect policy iterator contract.") from exc
        if declared is missing or not callable(declared):
            raise SelectionSourceContractError("Policy source returned an invalid iterator contract.")
        declared_methods.append(declared)

    try:
        actual = iter(candidate)
    except Exception as exc:
        # The class had the expected shape; its executable iterator
        # initialization failed. Preserve this source-origin error/cause.
        raise SelectionSourceReadError("Admitted policy iterator initialization failed.") from exc
    if actual is not candidate:
        raise SelectionSourceContractError("Policy iterator must return itself from __iter__.")
    if type(candidate) is not candidate_type:
        raise SelectionSourceContractError("Policy iterator type changed during initialization.")
    for special, original in zip(("__iter__", "__next__"), declared_methods, strict=True):
        try:
            current = getattr_static(candidate_type, special, missing)
        except Exception as exc:
            raise SelectionSourceContractError("Cannot inspect policy iterator after initialization.") from exc
        if current is not original:
            raise SelectionSourceContractError("Policy iterator protocol changed during initialization.")
    return candidate


def _static_method_identity(source: object, method_name: str) -> object:
    """Non-executing lookup for *detectable* method swaps during callbacks.

    This is defense-in-depth for a trusted composition root, not source
    authentication or an immutable-session guarantee. No descriptor is bound.
    """
    try:
        return getattr_static(source, method_name, None)
    except Exception as exc:
        raise SelectionSourceContractError("Cannot inspect selected source method identity.") from exc


def _assert_method_unchanged(source: object, name: str, original: object) -> None:
    if _static_method_identity(source, name) is not original:
        raise SelectionSourceContractError("Selected source method changed after admission.")


def _configured_identity_check(
    config: ConfiguredSelectionSources, question: SelectionAdmissionContext, limits: SelectorResourceLimits
) -> None:
    if type(config) is not ConfiguredSelectionSources or type(config.grading_spec_ref) is not GradingSpecRef:
        raise SelectionAdmissionDenied("Exact configured source bindings are missing.")
    if type(config.expected_policy_ref) is not EvaluatorSelectionPolicyRef:
        raise SelectionAdmissionDenied("Exact configured policy reference is missing.")
    for name in ("question_id", "classification_source_id", "selection_policy_source_id",
                 "capability_source_id", "configuration_ref"):
        _bounded_identifier(getattr(config, name), name=name, maximum=limits.max_identifier_codepoints,
                            invalid_error=SelectionAdmissionDenied)
    _bounded_identifier(config.grading_spec_ref.id, name="grading_spec_ref.id", maximum=limits.max_identifier_codepoints,
                        invalid_error=SelectionAdmissionDenied)
    _bounded_identifier(config.expected_policy_ref.policy_id, name="expected_policy_ref.policy_id",
                        maximum=limits.max_identifier_codepoints, invalid_error=SelectionAdmissionDenied)
    _bounded_version(config.grading_spec_ref.version, name="configured grading_spec_ref.version")
    _bounded_version(config.expected_policy_ref.version, name="expected_policy_ref.version")
    if config.grading_spec_ref != question.grading_spec_ref or config.question_id != question.question_id:
        raise SelectionAdmissionDenied("Configured source scope does not bind the exact question.")


def _count_field(total: int, value: object, *, name: str, limits: SelectorResourceLimits) -> int:
    size = _bounded_identifier(value, name=name, maximum=limits.max_identifier_codepoints)
    total += size
    if total > limits.max_total_text_codepoints:
        raise SelectorResourceLimitError("Selector total text envelope exceeded.")
    return total


def _read_classification(source: QuestionEvaluationClassificationSource,
                         question: SelectionAdmissionContext,
                         limits: SelectorResourceLimits) -> tuple[QuestionEvaluationClassification, int]:
    lookup = _source_method(source, "resolve_question_evaluation_classification", "Classification source")
    try:
        original = lookup(
            grading_spec_ref=_snapshot_spec_ref(question.grading_spec_ref),
            question_id=question.question_id,
        )
    except Exception as exc:
        # Only our privately constructed, post-admission raw wrapper may
        # originate a Gradified-owned limit/contract result. A foreign source
        # throwing the same Python class is always a source read failure.
        if type(source) is _AdmittedClassificationBinaryPort and type(exc) in (
            SelectionSourceReadError, SelectionSourceContractError, SelectorResourceLimitError
        ):
            raise
        raise SelectionSourceReadError("Admitted classification source failed.") from exc
    if type(original) is not QuestionEvaluationClassification:
        raise SelectionSourceContractError("Classification source returned the wrong contract type.")
    # Reject large fields BEFORE validating/snapshotting their values. A concrete
    # byte adapter must separately bound its raw ingestion before decoding.
    total = 0
    # Dataclass instances are mutable using object.__setattr__. Never dereference
    # a foreign nested reference before exact-type admission, even to count it.
    spec_ref = _exact_fields(original, ("grading_spec_ref",),
                             SelectionSourceContractError, "Classification")["grading_spec_ref"]
    if type(spec_ref) is not GradingSpecRef:
        raise SelectionSourceContractError("Classification contains an invalid grading-spec reference.")
    try:
        for name, value in (("question_id", original.question_id), ("answer_type", original.answer_type),
                            ("language", original.language), ("grading_spec_id", spec_ref.id)):
            total = _count_field(total, value, name=name, limits=limits)
        _bounded_version(spec_ref.version, name="classification.grading_spec_ref.version")
        validate_question_evaluation_classification(original)
        detached = QuestionEvaluationClassification(
            schema_version=original.schema_version,
            grading_spec_ref=_snapshot_spec_ref(spec_ref),
            question_id=original.question_id, answer_type=original.answer_type, language=original.language,
        )
    except (ValueError, AttributeError, TypeError) as exc:
        raise SelectionSourceContractError("Invalid classified source state.") from exc
    if detached.grading_spec_ref != question.grading_spec_ref or detached.question_id != question.question_id:
        raise SelectionSourceContractError("Classification does not match the admitted question scope.")
    return detached, total


def _read_policy(source: SelectionPolicyStreamSource, config: ConfiguredSelectionSources,
                 limits: SelectorResourceLimits, total: int,
                 rules_method_pin: object | None = None) -> EvaluatorSelectionPolicy:
    header_reader = _source_method(source, "read_policy_header", "Policy header source")
    try:
        header = header_reader()
    except Exception as exc:
        if type(source) is _AdmittedPolicyBinaryPort and type(exc) in (
            SelectionSourceReadError, SelectionSourceContractError, SelectorResourceLimitError
        ):
            raise
        raise SelectionSourceReadError("Admitted policy header source failed.") from exc
    if (type(header) is not tuple or len(header) != 2 or type(header[0]) is not str or
            header[0] != EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION or
            type(header[1]) is not EvaluatorSelectionPolicyRef):
        raise SelectionSourceContractError("Policy header is invalid or unsupported.")
    original_ref = header[1]
    ref_fields = _exact_fields(original_ref, ("policy_id", "version"),
                               SelectionSourceContractError, "Policy header reference")
    _bounded_identifier(ref_fields["policy_id"], name="policy_id", maximum=limits.max_identifier_codepoints)
    _bounded_version(ref_fields["version"], name="policy_ref.version")
    try:
        ref = EvaluatorSelectionPolicyRef(ref_fields["policy_id"], ref_fields["version"])
    except (ValueError, AttributeError, TypeError) as exc:
        raise SelectionSourceContractError("Policy header has malformed identity fields.") from exc
    if ref != config.expected_policy_ref:
        raise SelectionSourceContractError("Materialized policy is not the exact admitted policy revision.")
    total = _count_field(total, ref.policy_id, name="policy_id", limits=limits)
    # Even acquiring an attribute can run source code (descriptor/metaclass).
    # Never bind a rule descriptor until the admitted revision is validated.
    # A header-read callback must not swap the previously approved rule method.
    if rules_method_pin is not None:
        _assert_method_unchanged(source, "iter_policy_rules", rules_method_pin)
    rules_reader = _source_method(source, "iter_policy_rules", "Policy rule source")
    try:
        rules_iterator = rules_reader()
    except Exception as exc:
        if type(source) is _AdmittedPolicyBinaryPort and type(exc) in (
            SelectionSourceReadError, SelectionSourceContractError, SelectorResourceLimitError
        ):
            raise
        raise SelectionSourceReadError("Admitted policy rule source failed.") from exc
    rules_iterator = _admit_rule_iterator(rules_iterator)
    rules: list[EvaluatorSelectionRule] = []
    while True:
        # Source.next() has its own exception provenance boundary: even an
        # exception matching a Gradified-owned class is still source-origin.
        try:
            item = next(rules_iterator)
        except StopIteration:
            break
        except Exception as exc:
            raise SelectionSourceReadError("Admitted policy rule iterator failed.") from exc
        try:
            if len(rules) >= limits.max_policy_rules:
                raise SelectorResourceLimitError("Policy rule count exceeded before evaluator selection invocation.")
            if type(item) is not EvaluatorSelectionRule:
                raise SelectionSourceContractError("Stream yielded a non-rule value.")
            original_cap = item.capability_ref
            if type(original_cap) is not EvaluatorCapabilityRef:
                raise SelectionSourceContractError("Rule has an invalid capability reference.")
            original_metadata = original_cap.evaluator_metadata
            if type(original_metadata) is not EvaluatorMetadata:
                raise SelectionSourceContractError("Rule has invalid evaluator metadata.")
            for name, value in (
                ("rule.answer_type", item.answer_type),
                ("rule.language", item.language),
                ("rule.evaluator_id", original_metadata.evaluator_id),
                ("rule.evaluator_version", original_metadata.version),
            ):
                total = _count_field(total, value, name=name, limits=limits)
            _bounded_version(original_cap.record_version, name="capability_ref.record_version")
            rule = EvaluatorSelectionRule(
                answer_type=item.answer_type, language=item.language, context_policy=item.context_policy,
                capability_ref=EvaluatorCapabilityRef(
                    evaluator_metadata=EvaluatorMetadata(
                        evaluator_id=original_metadata.evaluator_id, version=original_metadata.version,
                    ), record_version=original_cap.record_version,
                ),
            )
            rules.append(rule)
        except (SelectionSourceContractError, SelectorResourceLimitError):
            raise
        except (ValueError, TypeError, AttributeError) as exc:
            raise SelectionSourceContractError("Invalid streamed policy rule contract.") from exc
    try:
        return EvaluatorSelectionPolicy("1", ref, tuple(rules))
    except ValueError as exc:
        raise SelectionSourceContractError("Admitted policy failed final validation.") from exc


def select_with_admitted_sources(
    *, question_authority: ResolvedQuestionAuthority,
    configured_sources: ConfiguredSelectionSources,
    admission_authority: SelectionSourceAdmissionAuthority,
    classification_source: QuestionEvaluationClassificationSource | DeferredBinaryClassificationSource,
    policy_stream_source: SelectionPolicyStreamSource | DeferredBinaryPolicySource,
    capability_source: EvaluatorCapabilitySource,
    limits: SelectorResourceLimits,
) -> ResolvedQuestionEvaluatorSelection:
    """Trusted-root operation; does not grant evaluator execution permission.

    All sources and the admission authority MUST be injected by the same trusted
    composition root. Exposing arbitrary replacement of this authority to an
    untrusted caller defeats source authentication and is not supported.
    """
    _validate_limits(limits)
    # Snapshot finite limits and reject huge question IDs before invoking the
    # inherited question-authority validator, which performs string operations.
    limits = _snapshot_limits(limits)
    _validate_limits(limits)
    if type(question_authority) is not ResolvedQuestionAuthority:
        raise QuestionClassificationBindingError("Question authority must be an exact resolved question authority.")
    question_fields = _exact_fields(
        question_authority, ("grading_spec_ref", "question_id", "context_policy", "question_text",
                             "rubric_content", "scoring_authority"),
        QuestionClassificationBindingError, "Question authority",
    )
    _bounded_identifier(question_fields["question_id"], name="question_authority.question_id",
                        maximum=limits.max_identifier_codepoints,
                        invalid_error=QuestionClassificationBindingError)
    if type(question_fields["grading_spec_ref"]) is GradingSpecRef:
        spec_fields = _exact_fields(question_fields["grading_spec_ref"], ("id", "version"),
                                    QuestionClassificationBindingError, "Question spec reference")
        _bounded_identifier(spec_fields["id"], name="question_authority.grading_spec_ref.id",
                            maximum=limits.max_identifier_codepoints,
                            invalid_error=QuestionClassificationBindingError)
    grading_spec_ref, question_id, _context_policy = _validate_question_authority(question_authority)
    _bounded_version(grading_spec_ref.version, name="question_authority.grading_spec_ref.version")
    grading_spec_ref = _snapshot_spec_ref(grading_spec_ref)
    context = SelectionAdmissionContext(grading_spec_ref, question_id, _context_policy)
    configured_sources = _snapshot_config(configured_sources, limits)
    _configured_identity_check(configured_sources, context, limits)
    # Preserve the ACTIVE context and original academic values before all callbacks.
    if2_authority = ResolvedQuestionAuthority(
        grading_spec_ref=_snapshot_spec_ref(grading_spec_ref), question_id=question_id,
        context_policy=_context_policy,
        question_text=question_fields["question_text"],
        rubric_content=question_fields["rubric_content"],
        scoring_authority=question_fields["scoring_authority"],
    )
    # Never acquire any admitted reader/decoder or invoke source callbacks before
    # the exact context/configuration and finite envelope are retained privately.
    classification_deferred = None
    policy_deferred = None
    if type(classification_source) is DeferredBinaryClassificationSource:
        classification_deferred = _exact_fields(
            classification_source, ("open_reader", "decode"),
            SelectionSourceContractError, "Deferred classification adapter",
        )
        classification_deferred = (
            classification_deferred["open_reader"], classification_deferred["decode"],
        )
        if not all(callable(part) for part in classification_deferred):
            raise SelectionSourceContractError("Deferred classification reader/decoder must be callable.")
    if type(policy_stream_source) is DeferredBinaryPolicySource:
        policy_deferred = _exact_fields(
            policy_stream_source, ("open_reader", "decode_header", "iter_rules"),
            SelectionSourceContractError, "Deferred policy adapter",
        )
        policy_deferred = (policy_deferred["open_reader"], policy_deferred["decode_header"],
                           policy_deferred["iter_rules"])
        if not all(callable(part) for part in policy_deferred):
            raise SelectionSourceContractError("Deferred policy reader/decoder must be callable.")
    method_pins = (
        (classification_source, "resolve_question_evaluation_classification",
         _static_method_identity(classification_source, "resolve_question_evaluation_classification"))
        if classification_deferred is None else None,
        (policy_stream_source, "read_policy_header",
         _static_method_identity(policy_stream_source, "read_policy_header"))
        if policy_deferred is None else None,
        (policy_stream_source, "iter_policy_rules",
         _static_method_identity(policy_stream_source, "iter_policy_rules"))
        if policy_deferred is None else None,
        (capability_source, "find_exact_capabilities",
         _static_method_identity(capability_source, "find_exact_capabilities")),
    )
    if admission_authority is None:
        raise SelectionAdmissionUnavailable("A separately trusted source-admission decision is unavailable.")
    try:
        approved = admission_authority.authorize_selection_sources(
            context=SelectionAdmissionContext(_snapshot_spec_ref(context.grading_spec_ref), context.question_id,
                                             context.context_policy),
            config=_snapshot_config(configured_sources, limits), limits=_snapshot_limits(limits),
            classification_source=classification_source,
            policy_stream_source=policy_stream_source,
            capability_source=capability_source,
        )
    except Exception as exc:
        raise SelectionAdmissionUnavailable("Trusted admission authority was unavailable.") from exc
    if approved is not True:
        raise SelectionAdmissionDenied("Source bindings were not admitted for this exact operation.")
    # One exact selected envelope, *aggregated across every first-party raw
    # classification/policy reader for this operation*; no authorization or
    # network/decoder side effect has occurred prior to this point.
    ingress_budget = _OperationByteBudget(limits.max_source_bytes)
    admitted_classification_source = (
        _AdmittedClassificationBinaryPort(*classification_deferred, ingress_budget)
        if classification_deferred is not None else classification_source
    )
    admitted_policy_source = (
        _AdmittedPolicyBinaryPort(*policy_deferred, ingress_budget)
        if policy_deferred is not None else policy_stream_source
    )
    # Materialize under selected, finite structural limits BEFORE invoking evaluator selection.
    for pin in method_pins:
        if pin is not None:
            _assert_method_unchanged(*pin)
    classification, total = _read_classification(admitted_classification_source, context, limits)
    # Source callbacks may replace other methods after approval; check again.
    for pin in method_pins:
        if pin is not None:
            _assert_method_unchanged(*pin)
    policy = _read_policy(
        admitted_policy_source, configured_sources, limits, total,
        method_pins[2][2] if method_pins[2] is not None else None,
    )
    _assert_method_unchanged(*method_pins[-1])
    # evaluator capability resolution's own direct lookup remains frozen. Supply an already-acquired,
    # statically declared callable, so its second attribute lookup cannot
    # silently bind a different method after the source-admission decision.
    admitted_capability = _AdmittedCapabilitySource(
        _source_method(capability_source, "find_exact_capabilities", "Capability source")
    )
    return resolve_question_evaluator_selection(
        question_authority=if2_authority,
        classification_source=_FixedClassificationSource(classification),
        policy_source=_FixedPolicySource(policy),
        capability_source=admitted_capability,
    )


def bounded_source_bytes(reader: BinaryIO, *, limits: SelectorResourceLimits) -> bytes:
    """Bound a Gradified-controlled binary read BEFORE storing/decoding bytes.

    Source adapters must bind the exact approved ``limits`` to raw-ingress reads;
    this does not limit allocations performed *before* a third-party reader is
    handed to Gradified or enforce the trustworthiness of that reader.
    """
    _validate_limits(limits)
    return _read_binary_with_budget(reader, limits.max_source_bytes)


def _read_binary_with_budget(reader: BinaryIO, max_bytes: int) -> bytes:
    """Enforce a budget even at EOF and against reader over-return."""
    # Validate the returned reader independently of I/O failures. A missing
    # or non-callable read() is a source-contract defect; a callable whose
    # lookup or invocation raises is a source-operation failure. Capture the
    # method once so a stateful reader cannot swap it during this operation.
    read = _source_method(reader, "read", "Deferred binary reader")
    chunks: list[bytes] = []
    total = 0
    while True:
        requested = min(8192, max_bytes + 1 - total)
        if requested <= 0:
            raise SelectorResourceLimitError("Binary source exceeded its permitted byte budget.")
        try:
            chunk = read(requested)
        except Exception as exc:
            raise SelectionSourceReadError("Bounded binary-source read failed.") from exc
        if type(chunk) is not bytes or len(chunk) > requested:
            raise SelectionSourceContractError("Binary source violated its bounded-read contract.")
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise SelectorResourceLimitError("Binary source exceeded its permitted byte budget.")
        chunks.append(chunk)
