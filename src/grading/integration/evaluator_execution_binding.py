"""Bind an approved evaluator runtime to its exact installed handler without executing it.

A label or Python function alone does not prove production approval, executable
artifact digest or attempt origin. evaluator invocation must own actual invocation and custody.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import FunctionType
from typing import Callable, Protocol

from grading.active_question_authority import ContextPolicy
from grading.contracts.capability import EvaluatorCapabilityRef
from grading.contracts.choice import (
    DETERMINISTIC_CHOICE_EVALUATOR_ID, DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
)
from grading.choice_evaluator import evaluate_single_select_choice
from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.execution_eligibility import (
    _choice_identity, _evaluate,
    AdmittedExecutionEligibility, ExecutionEligibilityDenied,
    ExecutionEligibilityContractError, ExecutionEligibilityUnavailable,
    _id, _attr, _scope, _ref, _strip, _capture, _call,
    ProductionExecutionEligibilityComposer,
)


class RuntimeBindingDenied(ExecutionEligibilityDenied):
    """The exact requested runtime is not approved/installed."""


class RuntimeBindingUnavailable(ExecutionEligibilityUnavailable):
    """Approved runtime inventory backend was unavailable."""


class RuntimeBindingContractError(ExecutionEligibilityContractError):
    """Runtime inventory or configured handler has an invalid contract."""


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedRuntimeRecord:
    scope: ChoiceAdmissionScope
    capability_ref: EvaluatorCapabilityRef
    eligibility_policy_id: str
    eligibility_policy_version: int
    family: str
    runtime_id: str
    runtime_version: str
    implementation_ref: str
    approval_ref: str
    approved_modalities: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class InstalledRuntime:
    family: str
    runtime_id: str
    runtime_version: str
    implementation_ref: str
    handler: Callable


@dataclass(frozen=True, slots=True, repr=False)
class BoundEvaluatorRuntime:
    """handler-binding handoff, NOT an invocation, grade, or bearer credential."""
    eligibility: AdmittedExecutionEligibility
    approved_runtime: ApprovedRuntimeRecord
    installed: InstalledRuntime


class ApprovedRuntimeInventory(Protocol):
    def resolve_approved_runtime(self, *, scope: ChoiceAdmissionScope,
                                 capability_ref: EvaluatorCapabilityRef,
                                 policy_id: str, policy_version: int) -> ApprovedRuntimeRecord: ...


def _runtime_record(value: object, eligibility: AdmittedExecutionEligibility,
                    limit: int, maximum: int) -> ApprovedRuntimeRecord:
    if type(value) is not ApprovedRuntimeRecord:
        raise RuntimeBindingContractError("Approved runtime record has invalid type.")
    try:
        scope = _scope(_attr(value, 'scope'), limit)
        ref = _ref(_attr(value, 'capability_ref'))
        policy_id = _id(_attr(value, 'eligibility_policy_id'), limit)
        policy_version = _attr(value, 'eligibility_policy_version')
        family = _id(_attr(value, 'family'), limit)
        runtime_id = _id(_attr(value, 'runtime_id'), limit)
        version = _id(_attr(value, 'runtime_version'), limit)
        implementation = _id(_attr(value, 'implementation_ref'), limit)
        approval = _id(_attr(value, 'approval_ref'), limit)
        modalities = _attr(value, 'approved_modalities')
        if (type(policy_version) is not int or policy_version <= 0
                or type(modalities) is not tuple or len(modalities) > maximum
                or any(type(x) is not str or not x or x.strip() != x or len(x) > limit for x in modalities)
                or len(set(modalities)) != len(modalities)):
            raise RuntimeBindingContractError("Runtime policy or modality inventory is malformed.")
        if (scope != eligibility.scope or ref != eligibility.selection.selected_capability_ref
                or policy_id != eligibility.policy.policy_id
                or policy_version != eligibility.policy.policy_version):
            raise RuntimeBindingDenied("Approved runtime does not bind eligibility.")
        return ApprovedRuntimeRecord(scope, ref, policy_id, policy_version, family,
                                     runtime_id, version, implementation, approval, modalities)
    except (RuntimeBindingDenied, RuntimeBindingContractError):
        raise
    except (ExecutionEligibilityContractError, TypeError, AttributeError, ValueError):
        raise RuntimeBindingContractError("Approved runtime inventory is malformed.") from None


def _installed_snapshot(value: object, limit: int) -> InstalledRuntime:
    if type(value) is not InstalledRuntime:
        raise RuntimeBindingContractError("Installed runtime has invalid type.")
    family = _id(_attr(value, 'family'), limit)
    runtime_id = _id(_attr(value, 'runtime_id'), limit)
    version = _id(_attr(value, 'runtime_version'), limit)
    implementation = _id(_attr(value, 'implementation_ref'), limit)
    handler = _attr(value, 'handler')
    # Exact configured free function, not a descriptor/callable object. evaluator invocation
    # will validate the per-family ABI and actual invocation/result origin.
    if type(handler) is not FunctionType:
        raise RuntimeBindingContractError("Installed handler must be an exact function.")
    if '__signature__' in handler.__dict__ or '__wrapped__' in handler.__dict__:
        raise RuntimeBindingContractError("Handler signature metadata cannot be overridden.")
    from grading.integration.paper_family_evaluation import evaluate_supported_paper_questions
    accepted = (family == 'CHOICE' and handler is evaluate_single_select_choice) or (
        family in ('DIRECT', 'NUMERIC') and handler is evaluate_supported_paper_questions)
    if not accepted:
        raise RuntimeBindingContractError("Only the exact built-in family grading handlers may be installed.")
    return InstalledRuntime(family, runtime_id, version, implementation, handler)


@dataclass(frozen=True, slots=True, repr=False)
class _RuntimeInstallation:
    eligibility: ProductionExecutionEligibilityComposer
    inventory_operation: object
    installed_handlers: object
    identifier_limit: int
    modality_limit: int
    fact_limit: int


class ProductionEvaluatorRuntimeBinder:
    __slots__ = ('_installation', '_eligibility', '_installed_eligibility')

    """Configured runtime inventory + explicit installed immutable handler map.

    Does not infer execution approval from capability-status claims or a family name,
    or an installed handler. Does not run the handler or issue attempt identity.
    """
    def __setattr__(self, name: str, value: object) -> None:
        if name == '_installation':
            try:
                object.__getattribute__(self, '_installation')
            except AttributeError:
                pass  # first installation only
            else:
                raise AttributeError('Installed evaluator handoff configuration is immutable.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == '_installation':
            raise AttributeError('Installed evaluator handoff configuration cannot be deleted.')
        object.__delattr__(self, name)

    @property
    def _configured_eligibility(self):
        return self._installation.eligibility

    @property
    def _operation(self):
        return self._installation.inventory_operation

    @property
    def _installed(self):
        return self._installation.installed_handlers

    @property
    def _limit(self) -> int:
        return self._installation.identifier_limit

    @property
    def _max_modalities(self) -> int:
        return self._installation.modality_limit

    @property
    def _max_facts(self) -> int:
        return self._installation.fact_limit

    def __init__(self, *, inventory: ApprovedRuntimeInventory,
                 eligibility: ProductionExecutionEligibilityComposer,
                 installed: tuple[InstalledRuntime, ...],
                 max_identifier_characters: int, max_modalities: int,
                 max_installed_runtimes: int, max_facts: int) -> None:
        try:
            if type(eligibility) is not ProductionExecutionEligibilityComposer:
                raise RuntimeBindingContractError("An installed execution eligibility composer is required.")
            if (type(max_identifier_characters) is not int or max_identifier_characters <= 0
                    or type(max_modalities) is not int or max_modalities <= 0
                    or type(max_installed_runtimes) is not int or max_installed_runtimes <= 0
                    or type(max_facts) is not int or max_facts <= 0):
                raise RuntimeBindingContractError("Explicit runtime limits are required.")
            if (type(installed) is not tuple or not installed
                    or len(installed) > max_installed_runtimes):
                raise RuntimeBindingContractError("Installed runtime inventory must be nonempty.")
            captured = tuple(_installed_snapshot(x, max_identifier_characters) for x in installed)
            keys = [(x.family, x.runtime_id, x.runtime_version, x.implementation_ref) for x in captured]
            if len(keys) != len(set(keys)):
                raise RuntimeBindingContractError("Ambiguous installed runtime identity.")
            operation = _capture(inventory, 'resolve_approved_runtime',
                                 ('scope', 'capability_ref', 'policy_id', 'policy_version'))
        except (RuntimeBindingContractError, ExecutionEligibilityContractError) as exc:
            raise _strip(RuntimeBindingContractError(str(exc))) from None
        from types import MappingProxyType
        self._installation = _RuntimeInstallation(
            eligibility, operation, MappingProxyType(dict(zip(keys, captured))),
            max_identifier_characters, max_modalities, max_facts,
        )
        self._eligibility = eligibility  # checked diagnostic aliases, not call targets
        self._installed_eligibility = eligibility

    def _require_installed_eligibility(self) -> None:
        original = self._installation.eligibility
        if (getattr(self, '_eligibility', None) is not original
                or getattr(self, '_installed_eligibility', None) is not original):
            raise RuntimeBindingDenied("Installed execution eligibility authority changed.")
        try:
            original._require_operations()
        except ExecutionEligibilityDenied:
            raise RuntimeBindingDenied("Installed execution eligibility operations changed.") from None

    def bind_family(self, *, scope: ChoiceAdmissionScope, family: str,
                    context_policy: ContextPolicy) -> BoundEvaluatorRuntime:
        """Fresh installed execution eligibility -> evaluator handler binding family runtime binding, not physical attempt claim permission.

        The physical owner must revalidate this result against source-issued
        question scope and rebind immediately before every irreversible effect.
        """
        from grading.integration.execution_eligibility import (
            AdmittedFamilyExecutionEligibility, _facts, _policy, _selection,
        )
        from grading.integration.paper_family_evaluation import evaluate_supported_paper_questions
        try:
            installation = self._installation
            self._require_installed_eligibility()
            original_scope = _scope(scope, self._limit)
            if (type(family) is not str or family not in ('DIRECT', 'NUMERIC')
                    or type(context_policy) is not ContextPolicy):
                raise RuntimeBindingContractError('Invalid family runtime request.')
            try:
                admitted = installation.eligibility.admit_family(
                    scope=scope, family=family, context_policy=context_policy)
            finally:
                self._require_installed_eligibility()
            if type(admitted) is not AdmittedFamilyExecutionEligibility:
                raise RuntimeBindingContractError('Family eligibility is not admitted.')
            chosen = _selection(admitted.selection, self._limit)
            ref = chosen.selected_capability_ref
            facts = _facts(admitted.facts, original_scope, ref, self._limit, self._max_facts)
            policy = _policy(admitted.policy, original_scope, ref, self._limit, self._max_facts)
            _evaluate(policy, facts, chosen.resolved_capability.record)
            if (admitted.family != family or admitted.context_policy is not context_policy
                    or _scope(admitted.scope, self._limit) != original_scope
                    or chosen.classification.answer_type != family
                    or chosen.context_policy is not context_policy):
                raise RuntimeBindingDenied('Family eligibility binding changed.')

            def guard():
                self._require_installed_eligibility()
                if (self._installation is not installation
                        or _scope(scope, self._limit) != original_scope
                        or _scope(admitted.scope, self._limit) != original_scope
                        or _scope(arg_scope, self._limit) != original_scope
                        or _ref(arg_ref) != ref
                        or _selection(admitted.selection, self._limit) != chosen
                        or _facts(admitted.facts, original_scope, ref, self._limit, self._max_facts) != facts
                        or _policy(admitted.policy, original_scope, ref, self._limit, self._max_facts) != policy):
                    raise RuntimeBindingDenied('Family runtime source changed.')

            arg_scope, arg_ref = _scope(original_scope, self._limit), _ref(ref)
            try:
                raw = _call(installation.inventory_operation, verify=guard,
                            scope=arg_scope, capability_ref=arg_ref,
                            policy_id=policy.policy_id, policy_version=policy.policy_version)
            except ExecutionEligibilityDenied:
                raise RuntimeBindingDenied('Family runtime approval denied or changed.') from None
            except ExecutionEligibilityUnavailable:
                raise RuntimeBindingUnavailable('Family runtime approval unavailable.') from None
            approved = _runtime_record(raw, admitted, self._limit, self._max_modalities)
            if (approved.family != family
                    or not set(facts.required_modalities).issubset(approved.approved_modalities)):
                raise RuntimeBindingDenied('Approved family runtime or modalities disagree.')
            key = (approved.family, approved.runtime_id,
                   approved.runtime_version, approved.implementation_ref)
            handler = installation.installed_handlers.get(key)
            if (type(handler) is not InstalledRuntime
                    or handler.handler is not evaluate_supported_paper_questions
                    or (handler.family, handler.runtime_id, handler.runtime_version,
                        handler.implementation_ref) != key):
                raise RuntimeBindingDenied('Exact approved family runtime is not installed.')
            guard()
            return BoundEvaluatorRuntime(admitted, approved, handler)
        except (ExecutionEligibilityDenied, ExecutionEligibilityUnavailable,
                ExecutionEligibilityContractError) as exc:
            raise _strip(exc) from None

    def bind_choice(self, *, admitted: AdmittedChoice) -> BoundEvaluatorRuntime:
        """The public binding path *always* performs fresh execution eligibility admission.

        Caller-constructible eligibility records are not accepted at this
        trust boundary. evaluator invocation must start at a trusted composition root again,
        not treat BoundEvaluatorRuntime as a bearer execution credential.
        """
        try:
            installed = self._installation
            self._require_installed_eligibility()
            # Check continuity even when execution eligibility raises. A callback that changes
            # authority must not be reported merely as an ordinary outage.
            try:
                eligibility = installed.eligibility.admit_choice(admitted=admitted)
            finally:
                self._require_installed_eligibility()
            return self._bind_eligibility(eligibility)
        except (ExecutionEligibilityDenied, ExecutionEligibilityUnavailable,
                ExecutionEligibilityContractError) as exc:
            raise _strip(exc) from None

    def _bind_eligibility(self, eligibility: AdmittedExecutionEligibility) -> BoundEvaluatorRuntime:
        """Internal structural validator, never an authority-issuing public entry."""
        try:
            return self._bind_eligibility_impl(eligibility)
        except (ExecutionEligibilityDenied, ExecutionEligibilityUnavailable,
                ExecutionEligibilityContractError) as exc:
            raise _strip(exc) from None

    def _bind_eligibility_impl(self, eligibility: AdmittedExecutionEligibility) -> BoundEvaluatorRuntime:
        installed = self._installation
        self._require_installed_eligibility()
        if type(eligibility) is not AdmittedExecutionEligibility:
            raise RuntimeBindingContractError("Exact eligibility admission is required.")
        # Pin these known domain values before handing a detached copy to the backend.
        from grading.integration.execution_eligibility import _facts, _policy, _selection
        scope = _scope(_attr(eligibility, 'scope'), self._limit)
        selected = _selection(_attr(eligibility, 'selection'), self._limit)
        ref = selected.selected_capability_ref
        facts = _facts(_attr(eligibility, 'facts'), scope, ref, self._limit, self._max_facts)
        policy = _policy(_attr(eligibility, 'policy'), scope, ref, self._limit, self._max_facts)
        _evaluate(policy, facts, selected.resolved_capability.record)
        if selected.classification.answer_type != "CHOICE":
            raise RuntimeBindingDenied("evaluator selection classification is not CHOICE for this runtime.")
        if (ref.evaluator_metadata.evaluator_id != DETERMINISTIC_CHOICE_EVALUATOR_ID
                or ref.evaluator_metadata.version != DETERMINISTIC_CHOICE_EVALUATOR_VERSION):
            raise RuntimeBindingDenied("Selected evaluator does not match the frozen CHOICE implementation.")
        if policy.requirements == ():
            raise RuntimeBindingDenied("Execution policy does not authorize requirements.")
        choice = _attr(eligibility, 'admitted_choice')
        original_choice = _choice_identity(choice, self._limit)
        # Validate revisions *before* any comparison can dispatch foreign __eq__.
        key_revision = _id(_attr(eligibility, 'key_revision'), self._limit)
        selection_revision = _id(_attr(eligibility, 'selection_revision'), self._limit)
        if (original_choice[0] != scope
                or selected.classification.grading_spec_ref != scope.grading_spec_ref
                or selected.classification.question_id != scope.question_id
                or selected.context_policy is not original_choice[3]
                or original_choice[4] != key_revision
                or original_choice[5] != selection_revision):
            raise RuntimeBindingDenied("Eligibility/CHOICE identities disagree.")
        base = (scope, selected, facts, policy, key_revision, selection_revision)

        scope_arg, ref_arg = _scope(scope, self._limit), _ref(ref)
        pid_arg, pver_arg = policy.policy_id, policy.policy_version
        def guard():
            if self._installation is not installed:
                raise RuntimeBindingDenied("Installed evaluator handoff configuration changed.")
            self._require_installed_eligibility()
            try:
                now = (_scope(_attr(eligibility, 'scope'), self._limit),
                       _selection(_attr(eligibility, 'selection'), self._limit),
                       _facts(_attr(eligibility, 'facts'), scope, ref, self._limit, self._max_facts),
                       _policy(_attr(eligibility, 'policy'), scope, ref, self._limit, self._max_facts),
                       _id(_attr(eligibility, 'key_revision'), self._limit),
                       _id(_attr(eligibility, 'selection_revision'), self._limit))
                if (_choice_identity(choice, self._limit) != original_choice or now != base
                        or _scope(scope_arg, self._limit) != scope or _ref(ref_arg) != ref):
                    raise RuntimeBindingDenied("Runtime binding source/callback argument changed.")
            except (ExecutionEligibilityContractError, RuntimeBindingContractError):
                raise RuntimeBindingDenied("Runtime binding source/callback argument changed.") from None
        try:
            raw = _call(installed.inventory_operation, verify=guard, scope=scope_arg, capability_ref=ref_arg,
                        policy_id=pid_arg, policy_version=pver_arg)
        except ExecutionEligibilityDenied:
            raise RuntimeBindingDenied("Runtime approval denied or source changed.") from None
        except ExecutionEligibilityUnavailable:
            raise RuntimeBindingUnavailable("Runtime approval backend unavailable.") from None
        approved = _runtime_record(raw, eligibility, self._limit, self._max_modalities)
        if approved.family != 'CHOICE':
            # This application root supports only admitted single-select CHOICE.
            # DIRECT, NUMERIC and other family enablement require own admission.
            raise RuntimeBindingDenied("No approved CHOICE runtime for this admission.")
        if not set(facts.required_modalities).issubset(approved.approved_modalities):
            raise RuntimeBindingDenied("Required modalities are not approved for this runtime.")
        key = (approved.family, approved.runtime_id,
               approved.runtime_version, approved.implementation_ref)
        handler = installed.installed_handlers.get(key)
        if handler is None:
            raise RuntimeBindingDenied("Exact approved runtime is not installed.")
        # Frozen dataclasses are not an in-process security sandbox: a caller
        # holding an internal reference can force mutations via object.__setattr__.
        # Recheck the captured handler immediately before returning the handoff.
        if (type(handler) is not InstalledRuntime
                or handler.handler is not evaluate_single_select_choice
                or (handler.family, handler.runtime_id, handler.runtime_version,
                    handler.implementation_ref) != key):
            raise RuntimeBindingDenied("Installed runtime changed after configuration.")
        guard()
        return BoundEvaluatorRuntime(eligibility, approved, handler)


@dataclass(frozen=True, slots=True, repr=False)
class _HandoffInstallation:
    entry: object
    eligibility: ProductionExecutionEligibilityComposer
    runtime: ProductionEvaluatorRuntimeBinder


class ProductionExecutionHandoff:
    __slots__ = ('_installation', '_entry', '_eligibility', '_runtime')

    """Application seam joining effect admission, execution eligibility and runtime binding. It never invokes an evaluator or scores."""

    def __setattr__(self, name: str, value: object) -> None:
        if name == '_installation':
            try:
                object.__getattribute__(self, '_installation')
            except AttributeError:
                pass  # first installation only
            else:
                raise AttributeError('Installed whole-paper execution configuration is immutable.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == '_installation':
            raise AttributeError('Installed whole-paper execution configuration cannot be deleted.')
        object.__delattr__(self, name)

    @property
    def _configured_entry(self):
        return self._installation.entry

    @property
    def _configured_eligibility(self):
        return self._installation.eligibility

    @property
    def _configured_runtime(self):
        return self._installation.runtime

    def _require_root(self) -> None:
        original = self._installation
        if (getattr(self, '_eligibility', None) is not original.eligibility
                or getattr(self, '_runtime', None) is not original.runtime
                or getattr(self, '_entry', None) is not original.entry):
            raise RuntimeBindingDenied('Execution root execution eligibility authority changed.')
        original.runtime._require_installed_eligibility()
        if original.runtime._configured_eligibility is not original.eligibility:
            raise RuntimeBindingDenied('Execution root execution eligibility authority changed.')

    def __init__(self, *, admission_entry, eligibility, runtime) -> None:
        from grading.integration.grading_orchestration import ProductionGradingEntry
        from grading.integration.execution_eligibility import ProductionExecutionEligibilityComposer
        try:
            if (type(admission_entry) is not ProductionGradingEntry
                    or type(eligibility) is not ProductionExecutionEligibilityComposer
                    or type(runtime) is not ProductionEvaluatorRuntimeBinder):
                raise RuntimeBindingContractError("Exact installed execution composition is required.")
            try:
                runtime._require_installed_eligibility()
            except RuntimeBindingDenied:
                raise RuntimeBindingContractError(
                    "Handoff runtime eligibility authority is corrupted.") from None
            if runtime._configured_eligibility is not eligibility:
                raise RuntimeBindingContractError("Handoff must use the exact installed eligibility authority.")
        except RuntimeBindingContractError as exc:
            raise _strip(exc) from None
        self._installation = _HandoffInstallation(admission_entry, eligibility, runtime)
        self._entry = admission_entry  # checked aliases; never dispatched directly
        self._eligibility = eligibility
        self._runtime = runtime

    def prepare_choice_runtime(self, *, request) -> BoundEvaluatorRuntime:
        # The paper execution integrity callback and subsequent approved eligibility and execution policy callbacks can be re-entrant.
        # Preserve corruption denial precedence on success, denial and outage.
        try:
            installed = self._installation
            self._require_root()
            try:
                admitted = installed.entry.prepare_choice(request=request)
            finally:
                self._require_root()
            try:
                result = installed.runtime.bind_choice(admitted=admitted)
            finally:
                self._require_root()
            return result
        except RuntimeBindingDenied as exc:
            raise _strip(exc) from None
