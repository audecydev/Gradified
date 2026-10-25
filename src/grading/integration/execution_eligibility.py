"""execution eligibility: admit versioned eligibility facts, never infer permission from evaluator capability resolution status.

Only an installed, separately authorized policy source can supply evaluator eligibility policy decisions.
Fixtures are not an approved production policy. No evaluator is invoked here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.capability_registry import _snapshot_record, _snapshot_ref
from grading.contracts.capability import (
    EvaluatorCapabilityRef, EvaluatorCapabilityRecord, validate_evaluator_capability_record,
    validate_evaluator_capability_ref,
)
from grading.contracts.evaluator_selection import (
    QuestionEvaluationClassification, EvaluatorSelectionPolicyRef,
    validate_question_evaluation_classification,
)
from grading.evaluator_selection import (
    ResolvedQuestionEvaluatorSelection, _snapshot_classification, _snapshot_policy_ref,
)
from grading.integration.choice_authority_admission import (
    AdmittedChoice, ChoiceAdmissionScope, _scope_copy,
)
from grading.integration.choice_binding import (
    BoundChoiceEvaluationInputs, _snapshot_authority, _snapshot_selection,
)
from grading.active_question_authority import ContextPolicy
from grading.contracts.choice import ChoiceEvaluationAuthority, CanonicalChoiceSelection
from grading.integration.evaluation_binding import BoundQuestionEvaluationInputs


class ExecutionEligibilityDenied(ValueError):
    """No exact approved evidence/policy permits this execution candidate."""


class ExecutionEligibilityUnavailable(Exception):
    """An installed authority did not supply a required fact."""


class ExecutionEligibilityContractError(ValueError):
    """A required authority record or installed interface is malformed."""


class FactOrigin(str, Enum):
    DIRECT = "DIRECT"
    DERIVED = "DERIVED"


@dataclass(frozen=True, slots=True, repr=False)
class EligibilityFact:
    name: str
    value: str
    origin: FactOrigin
    source_ref: str
    source_revision: str
    derivation_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class EligibilityFactSet:
    scope: ChoiceAdmissionScope
    capability_ref: EvaluatorCapabilityRef
    facts: tuple[EligibilityFact, ...]
    required_modalities: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class EligibilityRequirement:
    name: str
    expected_value: str
    allowed_origins: tuple[FactOrigin, ...]


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedEligibilityPolicy:
    scope: ChoiceAdmissionScope
    capability_ref: EvaluatorCapabilityRef
    policy_id: str
    policy_version: int
    approval_ref: str
    requirements: tuple[EligibilityRequirement, ...]
    required_modalities: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class AdmittedExecutionEligibility:
    """Verified comparison result. Constructible data, NOT an invocation credential."""
    scope: ChoiceAdmissionScope
    selection: ResolvedQuestionEvaluatorSelection
    facts: EligibilityFactSet
    policy: ApprovedEligibilityPolicy
    key_revision: str
    selection_revision: str
    admitted_choice: AdmittedChoice


@dataclass(frozen=True, slots=True, repr=False)
class AdmittedFamilyExecutionEligibility:
    """Current execution eligibility DIRECT/NUMERIC facts; NOT authority to claim physical attempt claim.

    The source scope must be checked against the exact issued paper question by
    the physical owner. No CHOICE key/selection is inferred for these families.
    """
    scope: ChoiceAdmissionScope
    family: str
    context_policy: ContextPolicy
    selection: ResolvedQuestionEvaluatorSelection
    facts: EligibilityFactSet
    policy: ApprovedEligibilityPolicy


class AdmittedSelectionSource(Protocol):
    def resolve_admitted_selection(self, *, scope: ChoiceAdmissionScope) -> ResolvedQuestionEvaluatorSelection: ...


class EligibilityFactSource(Protocol):
    def resolve_execution_facts(self, *, scope: ChoiceAdmissionScope,
                                capability_ref: EvaluatorCapabilityRef) -> EligibilityFactSet: ...


class ApprovedEligibilityPolicySource(Protocol):
    def resolve_approved_eligibility_policy(self, *, scope: ChoiceAdmissionScope,
                                            capability_ref: EvaluatorCapabilityRef) -> ApprovedEligibilityPolicy: ...


def _id(value: object, limit: int) -> str:
    if type(value) is not str or not value or len(value) > limit or value.strip() != value:
        raise ExecutionEligibilityContractError("Eligibility identifier is malformed.")
    return value


def _attr(value: object, name: str) -> object:
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        raise ExecutionEligibilityContractError("Eligibility record is incomplete.") from None


def _scope(value: object, limit: int) -> ChoiceAdmissionScope:
    try:
        return _scope_copy(value, limit)
    except (TypeError, ValueError):
        raise ExecutionEligibilityContractError("Eligibility scope is malformed.") from None


def _ref(value: object) -> EvaluatorCapabilityRef:
    if type(value) is not EvaluatorCapabilityRef:
        raise ExecutionEligibilityContractError("Evaluator capability reference is malformed.")
    try:
        validate_evaluator_capability_ref(value)
        return _snapshot_ref(value)
    except (TypeError, ValueError, AttributeError):
        raise ExecutionEligibilityContractError("Evaluator capability reference is malformed.") from None


def _selection(value: object, limit: int) -> ResolvedQuestionEvaluatorSelection:
    if type(value) is not ResolvedQuestionEvaluatorSelection:
        raise ExecutionEligibilityContractError("Admitted evaluator selection has invalid type.")
    try:
        classification = _attr(value, "classification")
        if type(classification) is not QuestionEvaluationClassification:
            raise ExecutionEligibilityContractError("evaluator selection classification is invalid.")
        validate_question_evaluation_classification(classification)
        item = _snapshot_classification(classification)
        for text in (item.grading_spec_ref.id, item.question_id, item.answer_type, item.language):
            _id(text, limit)
        policy = _attr(value, "policy_ref")
        if type(policy) is not EvaluatorSelectionPolicyRef:
            raise ExecutionEligibilityContractError("evaluator selection policy reference is invalid.")
        copied_policy = _snapshot_policy_ref(policy)
        _id(copied_policy.policy_id, limit)
        selected = _ref(_attr(value, "selected_capability_ref"))
        context = _attr(value, "context_policy")
        if type(context) is not ContextPolicy or context not in tuple(ContextPolicy):
            raise ExecutionEligibilityContractError("evaluator selection context policy is invalid.")
        resolved = _attr(value, "resolved_capability")
        from grading.capability_registry import ResolvedEvaluatorCapability
        if type(resolved) is not ResolvedEvaluatorCapability:
            raise ExecutionEligibilityContractError("evaluator capability resolution is invalid.")
        record = _attr(resolved, "record")
        validate_evaluator_capability_record(record)
        copy_record = _snapshot_record(record)
        if selected != copy_record.capability_ref:
            raise ExecutionEligibilityDenied("evaluator selection and evaluator capability references disagree.")
        for identifier in (selected.evaluator_metadata.evaluator_id,
                           selected.evaluator_metadata.version):
            _id(identifier, limit)
        if (item.answer_type not in copy_record.supported_answer_types
                or item.language not in copy_record.supported_languages):
            raise ExecutionEligibilityDenied("Selected capability does not support this classification.")
        return ResolvedQuestionEvaluatorSelection(
            item, context, copied_policy, selected, ResolvedEvaluatorCapability(copy_record),
        )
    except (ExecutionEligibilityDenied, ExecutionEligibilityContractError):
        raise
    except (AttributeError, ValueError, TypeError):
        raise ExecutionEligibilityContractError("Admitted evaluator selection is malformed.") from None


def _facts(value: object, scope: ChoiceAdmissionScope, ref: EvaluatorCapabilityRef,
           limit: int, maximum: int) -> EligibilityFactSet:
    if type(value) is not EligibilityFactSet:
        raise ExecutionEligibilityContractError("Eligibility fact authority returned invalid type.")
    returned_scope = _scope(_attr(value, "scope"), limit)
    returned_ref = _ref(_attr(value, "capability_ref"))
    if returned_scope != scope or returned_ref != ref:
        raise ExecutionEligibilityDenied("Eligibility facts are for another scope or evaluator.")
    values = _attr(value, "facts")
    modes = _attr(value, "required_modalities")
    if type(values) is not tuple or not 1 <= len(values) <= maximum:
        raise ExecutionEligibilityContractError("Eligibility fact collection is malformed or unbounded.")
    if type(modes) is not tuple or len(modes) > maximum:
        raise ExecutionEligibilityContractError("Eligibility modality collection is malformed or unbounded.")
    observed: set[str] = set()
    detached = []
    for fact in values:
        if type(fact) is not EligibilityFact:
            raise ExecutionEligibilityContractError("Eligibility fact has invalid type.")
        name, text = _id(_attr(fact, "name"), limit), _id(_attr(fact, "value"), limit)
        origin = _attr(fact, "origin")
        source_ref = _id(_attr(fact, "source_ref"), limit)
        revision = _id(_attr(fact, "source_revision"), limit)
        derivation_ref = _attr(fact, "derivation_ref")
        if type(origin) is not FactOrigin or origin not in tuple(FactOrigin):
            raise ExecutionEligibilityContractError("Fact provenance is invalid.")
        if (origin is FactOrigin.DIRECT and derivation_ref is not None
                or origin is FactOrigin.DERIVED and derivation_ref is None):
            raise ExecutionEligibilityContractError("Fact derivation provenance is incomplete.")
        if derivation_ref is not None:
            _id(derivation_ref, limit)
        if name in observed:
            raise ExecutionEligibilityContractError("Duplicate eligibility fact.")
        observed.add(name)
        detached.append(EligibilityFact(name, text, origin, source_ref, revision, derivation_ref))
    if any(type(mode) is not str or not mode or len(mode) > limit or mode.strip() != mode for mode in modes):
        raise ExecutionEligibilityContractError("Required modality is malformed.")
    if len(set(modes)) != len(modes):
        raise ExecutionEligibilityContractError("Duplicate required modality.")
    return EligibilityFactSet(scope, ref, tuple(detached), tuple(modes))


def _policy(value: object, scope: ChoiceAdmissionScope, ref: EvaluatorCapabilityRef,
            limit: int, maximum: int) -> ApprovedEligibilityPolicy:
    if type(value) is not ApprovedEligibilityPolicy:
        raise ExecutionEligibilityContractError("Eligibility policy authority returned invalid type.")
    returned_scope = _scope(_attr(value, "scope"), limit)
    returned_ref = _ref(_attr(value, "capability_ref"))
    if returned_scope != scope or returned_ref != ref:
        raise ExecutionEligibilityDenied("Eligibility policy is for another scope or evaluator.")
    policy_id = _id(_attr(value, "policy_id"), limit)
    version = _attr(value, "policy_version")
    approval = _id(_attr(value, "approval_ref"), limit)
    requirements = _attr(value, "requirements")
    modalities = _attr(value, "required_modalities")
    if (type(modalities) is not tuple or len(modalities) > maximum
            or any(type(x) is not str or not x or len(x) > limit or x.strip() != x for x in modalities)
            or len(set(modalities)) != len(modalities)):
        raise ExecutionEligibilityContractError("Approved eligibility modalities are malformed.")
    if type(version) is not int or version <= 0:
        raise ExecutionEligibilityContractError("Approved policy version is invalid.")
    if type(requirements) is not tuple or not 1 <= len(requirements) <= maximum:
        raise ExecutionEligibilityContractError("Approved policy has no bounded requirements.")
    copied = []
    names: set[str] = set()
    for requirement in requirements:
        if type(requirement) is not EligibilityRequirement:
            raise ExecutionEligibilityContractError("Eligibility requirement has invalid type.")
        name = _id(_attr(requirement, "name"), limit)
        expected = _id(_attr(requirement, "expected_value"), limit)
        origins = _attr(requirement, "allowed_origins")
        if (type(origins) is not tuple or not origins or len(origins) > len(FactOrigin)
                or any(type(x) is not FactOrigin for x in origins)
                or len(set(origins)) != len(origins)):
            raise ExecutionEligibilityContractError("Eligibility requirement provenance is malformed.")
        if name in names:
            raise ExecutionEligibilityContractError("Duplicate eligibility requirement.")
        names.add(name)
        copied.append(EligibilityRequirement(name, expected, tuple(origins)))
    return ApprovedEligibilityPolicy(scope, ref, policy_id, version, approval, tuple(copied), tuple(modalities))


def _choice_identity(value: object, limit: int) -> tuple[object, ...]:
    """Capture structural handoff identities; not proof of authentication."""
    if type(value) is not AdmittedChoice:
        raise ExecutionEligibilityContractError("An admitted CHOICE result is required.")
    scope = _scope(_attr(value, "scope"), limit)
    bound = _attr(value, "bound")
    if type(bound) is not BoundChoiceEvaluationInputs:
        raise ExecutionEligibilityContractError("CHOICE bound result is malformed.")
    try:
        original_authority = _attr(bound, "choice_authority")
        original_selection = _attr(bound, "selection")
        prepared = _attr(bound, "prepared")
        if (type(original_authority) is not ChoiceEvaluationAuthority
                or type(original_selection) is not CanonicalChoiceSelection
                or type(prepared) is not BoundQuestionEvaluationInputs):
            raise ExecutionEligibilityContractError("CHOICE handoff has an invalid domain type.")
        authority = _snapshot_authority(original_authority)
        selection = _snapshot_selection(original_selection)
        from grading.integration.choice_binding import _snapshot_prepared, ChoiceInputBindingError
        from grading.integration.choice_authority_admission import _pinned_roots
        # Detach/validate *all* PRE domain fields before equality can call a
        # foreign nested object's __eq__/__ne__.
        copied_prepared = _snapshot_prepared(prepared)
        context = copied_prepared.context
        question_authority = copied_prepared.question_authority
        from grading.active_question_authority import ResolvedQuestionAuthority
        from grading.execution import GradingExecutionContext
        if type(context) is not GradingExecutionContext or type(question_authority) is not ResolvedQuestionAuthority:
            raise ExecutionEligibilityContractError("CHOICE PRE context is invalid.")
        if (context.grading_run_id != scope.grading_run_id or context.submission_ref != scope.submission_ref
                or context.exam_ref != scope.exam_ref or context.grading_spec_ref != scope.grading_spec_ref
                or question_authority.question_id != scope.question_id
                or type(question_authority.context_policy) is not ContextPolicy):
            raise ExecutionEligibilityDenied("CHOICE admission scope is inconsistent.")
        if (authority.grading_spec_ref != scope.grading_spec_ref
                or authority.question_id != scope.question_id
                or selection.submission_ref != scope.submission_ref
                or selection.question_id != scope.question_id):
            raise ExecutionEligibilityDenied("CHOICE authority and scope disagree.")
        return (scope, authority, selection, question_authority.context_policy,
                _id(_attr(value, "key_revision"), limit),
                _id(_attr(value, "selection_revision"), limit),
                _id(_attr(value, "approval_ref"), limit),
                _id(_attr(value, "selection_origin_ref"), limit),
                _pinned_roots(copied_prepared))
    except (ExecutionEligibilityContractError, ExecutionEligibilityDenied):
        raise
    except (ChoiceInputBindingError, AttributeError, ValueError, TypeError):
        raise ExecutionEligibilityContractError("CHOICE admission is malformed.") from None


def _evaluate(policy: ApprovedEligibilityPolicy, facts: EligibilityFactSet,
              capability: EvaluatorCapabilityRecord) -> None:
    by_name = {fact.name: fact for fact in facts.facts}
    for requirement in policy.requirements:
        actual = by_name.get(requirement.name)
        if (actual is None or actual.value != requirement.expected_value
                or actual.origin not in requirement.allowed_origins):
            raise ExecutionEligibilityDenied("An approved eligibility requirement is not satisfied.")
    if set(facts.required_modalities) != set(policy.required_modalities):
        raise ExecutionEligibilityDenied("Eligibility modalities do not match approved evaluation eligibility policy.")
    if not set(policy.required_modalities).issubset(capability.supported_modalities):
        raise ExecutionEligibilityDenied("Required modalities are unsupported by the selected capability.")


def _strip(exc: Exception) -> Exception:
    exc.__cause__ = None
    exc.__context__ = None
    exc.__suppress_context__ = True
    return exc


def _capture(port: object, method: str, expected: tuple[str, ...]):
    """Bind a statically declared plain method, never a dynamic descriptor."""
    import inspect
    from types import FunctionType
    try:
        declared = inspect.getattr_static(type(port), method)
        actual = inspect.getattr_static(port, method)
    except (AttributeError, TypeError):
        raise ExecutionEligibilityContractError("Required eligibility backend method is missing.") from None
    if (type(declared) is not FunctionType or actual is not declared
            or '__signature__' in declared.__dict__ or '__wrapped__' in declared.__dict__):
        raise ExecutionEligibilityContractError("Eligibility backend operation must be a plain class method.")
    try:
        params = tuple(inspect.signature(declared, follow_wrapped=False).parameters.values())
        if (len(params) != len(expected) + 1
                or params[0].kind not in (inspect.Parameter.POSITIONAL_ONLY,
                                           inspect.Parameter.POSITIONAL_OR_KEYWORD)
                or tuple(x.name for x in params[1:]) != expected
                or any(x.kind is not inspect.Parameter.KEYWORD_ONLY or x.default is not inspect.Parameter.empty
                       for x in params[1:])):
            raise ValueError('bad signature')
    except (TypeError, ValueError):
        raise ExecutionEligibilityContractError("Eligibility backend method signature is invalid.") from None
    return declared.__get__(port, type(port))


def _call(operation, *, verify, **arguments):
    """Verify source and callback arguments before interpreting *any* callback outcome."""
    outcome = None
    denied = failed = False
    try:
        outcome = operation(**arguments)
    except ExecutionEligibilityDenied:
        denied = True
    except Exception:
        failed = True
    verify()
    if denied:
        raise ExecutionEligibilityDenied("Eligibility access was denied.") from None
    if failed:
        raise ExecutionEligibilityUnavailable("Eligibility backend is unavailable.") from None
    return outcome


@dataclass(frozen=True, slots=True, repr=False)
class _EligibilityInstallation:
    operations: tuple[object, object, object]
    identifier_limit: int
    fact_limit: int


class ProductionExecutionEligibilityComposer:
    __slots__ = ('_installation', '_operations')

    """Execution-eligibility composition. Returns verified facts, not an executable grant.

    All authority issuers are installed by the trusted application root; no
    source-controlled policy is silently selected or promoted here.
    """

    def __setattr__(self, name: str, value: object) -> None:
        if name == '_installation':
            try:
                object.__getattribute__(self, '_installation')
            except AttributeError:
                pass  # first installation only
            else:
                raise AttributeError('Installed execution eligibility configuration is immutable.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == '_installation':
            raise AttributeError('Installed execution eligibility configuration cannot be deleted.')
        object.__delattr__(self, name)

    @property
    def _pinned_operations(self):
        return self._installation.operations

    @property
    def _limit(self) -> int:
        return self._installation.identifier_limit

    @property
    def _maximum(self) -> int:
        return self._installation.fact_limit

    def _require_operations(self) -> None:
        original = self._installation.operations
        current = getattr(self, '_operations', None)  # diagnostic only; not a call target
        if (type(current) is not tuple or len(current) != len(original)
                or any(a is not b for a, b in zip(current, original))):
            raise ExecutionEligibilityDenied('Installed execution eligibility authority operations changed.')

    def __init__(self, *, selection: AdmittedSelectionSource,
                 facts: EligibilityFactSource, policy: ApprovedEligibilityPolicySource,
                 max_identifier_characters: int, max_facts: int) -> None:
        try:
            if (type(max_identifier_characters) is not int or max_identifier_characters <= 0
                    or type(max_facts) is not int or max_facts <= 0):
                raise ExecutionEligibilityContractError("Explicit eligibility resource limits are required.")
            operations = (
                _capture(selection, 'resolve_admitted_selection', ('scope',)),
                _capture(facts, 'resolve_execution_facts', ('scope', 'capability_ref')),
                _capture(policy, 'resolve_approved_eligibility_policy', ('scope', 'capability_ref')),
            )
        except ExecutionEligibilityContractError as exc:
            raise _strip(exc) from None
        self._installation = _EligibilityInstallation(operations, max_identifier_characters, max_facts)
        self._operations = operations  # checked diagnostic alias, not execution authority

    def admit_family(self, *, scope: ChoiceAdmissionScope, family: str,
                     context_policy: ContextPolicy) -> AdmittedFamilyExecutionEligibility:
        """Re-read installed evaluator selection, evaluator eligibility policy facts and policy for an exact family scope.

        The returned structural fact is not an effect permit. In particular, a
        caller-supplied scope cannot by itself establish official paper origin.
        """
        try:
            return self._admit_family(scope, family, context_policy)
        except (ExecutionEligibilityDenied, ExecutionEligibilityUnavailable,
                ExecutionEligibilityContractError) as exc:
            raise _strip(exc) from None

    def _admit_family(self, scope, family, context_policy):
        if (type(family) is not str or family not in ('DIRECT', 'NUMERIC')
                or type(context_policy) is not ContextPolicy):
            raise ExecutionEligibilityContractError('Exact supported family and context required.')
        installation = self._installation
        operations = installation.operations
        limit, maximum = installation.identifier_limit, installation.fact_limit
        original = _scope(scope, limit)

        def guard(argument_scope, argument_ref=None, expected_ref=None):
            if self._installation is not installation:
                raise ExecutionEligibilityDenied('Installed family eligibility changed.')
            self._require_operations()
            if (_scope(scope, limit) != original
                    or _scope(argument_scope, limit) != original
                    or (expected_ref is not None and _ref(argument_ref) != expected_ref)):
                raise ExecutionEligibilityDenied('Original family scope changed during admission.')

        self._require_operations()
        requested_scope = _scope(original, limit)
        selected = _selection(_call(operations[0], verify=lambda: guard(requested_scope),
                                    scope=requested_scope), limit)
        if (selected.classification.grading_spec_ref != original.grading_spec_ref
                or selected.classification.question_id != original.question_id
                or selected.classification.answer_type != family
                or selected.context_policy is not context_policy):
            raise ExecutionEligibilityDenied('Issued family scope and evaluator selection classification disagree.')
        ref = selected.selected_capability_ref
        requested_scope, requested_ref = _scope(original, limit), _ref(ref)
        facts = _facts(_call(operations[1], verify=lambda: guard(requested_scope, requested_ref, ref),
                             scope=requested_scope, capability_ref=requested_ref),
                       original, ref, limit, maximum)
        requested_scope, requested_ref = _scope(original, limit), _ref(ref)
        policy = _policy(_call(operations[2], verify=lambda: guard(requested_scope, requested_ref, ref),
                               scope=requested_scope, capability_ref=requested_ref),
                         original, ref, limit, maximum)
        _evaluate(policy, facts, selected.resolved_capability.record)
        guard(original)
        return AdmittedFamilyExecutionEligibility(original, family, context_policy,
                                                  selected, facts, policy)

    def admit_choice(self, *, admitted: AdmittedChoice) -> AdmittedExecutionEligibility:
        try:
            return self._admit_choice(admitted)
        except (ExecutionEligibilityDenied, ExecutionEligibilityUnavailable,
                ExecutionEligibilityContractError) as exc:
            raise _strip(exc) from None

    def _admit_choice(self, admitted: AdmittedChoice) -> AdmittedExecutionEligibility:
        installed = self._installation
        operations = installed.operations  # exact original dispatch targets for this call
        limit = installed.identifier_limit
        maximum = installed.fact_limit
        baseline = _choice_identity(admitted, limit)
        scope = baseline[0]

        def guard(*, argument_scope, argument_ref=None, expected_ref=None):
            if self._installation is not installed:
                raise ExecutionEligibilityDenied('Installed execution eligibility authority changed.')
            self._require_operations()
            try:
                if _choice_identity(admitted, limit) != baseline:
                    raise ExecutionEligibilityDenied("Previously admitted CHOICE source changed.")
            except ExecutionEligibilityContractError:
                raise ExecutionEligibilityDenied("Previously admitted CHOICE source changed.") from None
            try:
                if _scope(argument_scope, limit) != scope or (
                    expected_ref is not None and _ref(argument_ref) != expected_ref
                ):
                    raise ExecutionEligibilityDenied("Eligibility callback input changed.")
            except ExecutionEligibilityContractError:
                raise ExecutionEligibilityDenied("Eligibility callback input changed.") from None

        self._require_operations()
        callback_scope = _scope(scope, limit)
        chosen = _call(operations[0], verify=lambda: guard(argument_scope=callback_scope),
                       scope=callback_scope)
        selection = _selection(chosen, limit)
        if (selection.classification.grading_spec_ref != scope.grading_spec_ref
                or selection.classification.question_id != scope.question_id
                or selection.context_policy != baseline[3]):
            raise ExecutionEligibilityDenied("evaluator selection does not bind admitted CHOICE authority.")
        if selection.classification.answer_type != "CHOICE":
            raise ExecutionEligibilityDenied("evaluator selection classification is not CHOICE for this handoff.")
        ref = selection.selected_capability_ref
        lookup_scope, lookup_ref = _scope(scope, limit), _ref(ref)
        returned_facts = _call(operations[1],
                               verify=lambda: guard(argument_scope=lookup_scope,
                                                    argument_ref=lookup_ref, expected_ref=ref),
                               scope=lookup_scope, capability_ref=lookup_ref)
        fact_set = _facts(returned_facts, scope, ref, limit, maximum)
        lookup_scope, lookup_ref = _scope(scope, limit), _ref(ref)
        returned_policy = _call(operations[2],
                                verify=lambda: guard(argument_scope=lookup_scope,
                                                     argument_ref=lookup_ref, expected_ref=ref),
                                scope=lookup_scope, capability_ref=lookup_ref)
        approved = _policy(returned_policy, scope, ref, limit, maximum)
        _evaluate(approved, fact_set, selection.resolved_capability.record)
        # Never return an eligible result after a late mutation to the original.
        guard(argument_scope=scope)
        return AdmittedExecutionEligibility(scope, selection, fact_set, approved,
                                            baseline[4], baseline[5], admitted)
