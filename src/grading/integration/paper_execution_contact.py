"""Check current paper authority before contacting an installed CHOICE evaluator.

This is a NO-EFFECT admission stage, not an evaluator permit.  Its successor must
perform physical attempt reservation and invocation in the same guarded execution lifecycle;
returning a detached record from here cannot authorize a later contact.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import local
from typing import Protocol

from grading.integration.paper_execution_correlation import (
    CorrelatedPaperExecution, IssuedPaperExecutionRelation, IssuedQuestionExecutionRelation,
    PaperExecutionDenied, PaperExecutionUnavailable, PaperExecutionContractError,
    ProductionPaperExecutionCorrelation, _plan, _relation,
)
from grading.integration.paper_readiness_admission import AdmittedPaperPlan, PaperAdmissionRequest
from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.evaluator_execution_binding import (
    ProductionExecutionHandoff, ProductionEvaluatorRuntimeBinder,
)
from grading.integration.execution_eligibility import ProductionExecutionEligibilityComposer
from grading.integration.grading_orchestration import ProductionGradingEntry
from grading.integration.authorized_preparation import ProductionPreparationComposer
from grading.integration.choice_authority_admission import ProductionChoiceAdmissionComposer
from grading.integration.evaluator_invocation import _validated_binding_snapshot
from grading.choice_evaluator import evaluate_single_select_choice
from grading.integration.execution_eligibility import _id, _scope
from grading.integration.trusted_preparation import PreparationRequest


# The operation is synchronous. Context().run can change ContextVar state on
# the SAME thread without unwinding the active issuer callback. Therefore
# track active roots in a closure-private per-thread scope, not in the
# callback-reachable installation or in a context-local authorization token.
# This is preflight reentrancy protection, NOT physical attempt claim durable attempt uniqueness.
def _make_thread_preflight_guard():
    state = local()

    def enter(root: object) -> tuple[int, object]:
        # Synchronous guard only; the true effect/attempt guard belongs to physical attempt claim.
        active = getattr(state, 'active_leases', None)
        if active is None:
            active = {}
            state.active_leases = active
        root_id = id(root)
        if root_id in active:
            raise PaperContactDenied('Nested paper contact is forbidden.')
        token = object()
        active[root_id] = token
        return root_id, token

    def leave(lease: tuple[int, object]) -> None:
        # A callback cannot supply an arbitrary former active-root set to
        # clear another invocation's guard. Cleanup requires the held token.
        if type(lease) is not tuple or len(lease) != 2:
            raise PaperContactDenied('Invalid paper contact guard lease.')
        root_id, token = lease
        active = getattr(state, 'active_leases', None)
        if (type(root_id) is not int or active is None
                or active.get(root_id) is not token):
            raise PaperContactDenied('Paper contact guard lease mismatch.')
        del active[root_id]

    return enter, leave


_enter_thread_preflight, _leave_thread_preflight = _make_thread_preflight_guard()


class PaperContactDenied(ValueError):
    """Official question identity or current permission was denied."""


class PaperContactUnavailable(Exception):
    """A required current authority/installed runtime could not be established."""


class PaperContactContractError(ValueError):
    """An installed authority returned malformed or noncanonical facts."""


@dataclass(frozen=True, slots=True, repr=False)
class CurrentQuestionContactFact:
    """Evidence from the installed issuer, not an executable bearer credential."""
    version: int
    request: PaperAdmissionRequest
    actor_ref: str
    paper_issuance_ref: str
    question: IssuedQuestionExecutionRelation
    scope: ChoiceAdmissionScope
    approval_ref: str
    approval_revision: str
    selection_decision_ref: str
    selection_revision: str
    source_revision: str
    readiness_revision: str
    confirmation_ref: str
    state: str  # CURRENT_AUTHORIZED only; semantics supplied by qualified installed issuer


@dataclass(frozen=True, slots=True, repr=False)
class NonExecutingQuestionContact:
    """Detached diagnostic fact, explicitly not permission to reserve or invoke."""
    paper_issuance_ref: str
    question_id: str
    confirmation_ref: str
    runtime_id: str
    runtime_version: str
    implementation_ref: str
    state: str  # PREFLIGHT_ONLY, never EXECUTION_AUTHORIZED
    current_question: IssuedQuestionExecutionRelation  # detached full academic relationship, NOT a bearer
    current_paper: IssuedPaperExecutionRelation  # entire revalidated issuance; NOT an execution grant


class CurrentQuestionContactIssuer(Protocol):
    def confirm_current_question_contact(
        self, *, correlation: CorrelatedPaperExecution,
        question: IssuedQuestionExecutionRelation,
        scope: ChoiceAdmissionScope,
    ) -> CurrentQuestionContactFact: ...


@dataclass(frozen=True, slots=True, repr=False)
class _Installation:
    correlation: ProductionPaperExecutionCorrelation
    handoff: ProductionExecutionHandoff
    operation: object
    max_questions: int
    identifier_limit: int
    installed_entry: ProductionGradingEntry
    installed_runtime: ProductionEvaluatorRuntimeBinder
    installed_eligibility: ProductionExecutionEligibilityComposer
    installed_preparation: ProductionPreparationComposer
    installed_choices: ProductionChoiceAdmissionComposer
    installed_preparation_operations: object
    installed_choice_operations: object
    installed_preparation_targets: tuple[tuple[str, object], ...]
    installed_choice_targets: tuple[tuple[str, object], ...]
    installed_preparation_limit: int
    installed_choice_limits: tuple[int, int, int]


def _clean_exception(exc: Exception) -> Exception:
    exc.__cause__ = None
    exc.__context__ = None
    exc.__suppress_context__ = True
    return exc


def _fact(value: object, limit: int) -> CurrentQuestionContactFact:
    if type(value) is not CurrentQuestionContactFact:
        raise PaperContactContractError('Installed current-question record has invalid type.')
    try:
        get = lambda name: object.__getattribute__(value, name)
        version = get('version')
        if type(version) is not int or version != 1:
            raise ValueError('unsupported contract version')
        question = _relation_question(get('question'), limit)
        request = _plan_request(get('request'), limit)
        scope = _scope(get('scope'), limit)
        fields = {name: _id(get(name), limit) for name in (
            'actor_ref', 'paper_issuance_ref', 'approval_ref', 'approval_revision',
            'selection_decision_ref', 'selection_revision', 'source_revision',
            'readiness_revision', 'confirmation_ref', 'state')}
        return CurrentQuestionContactFact(1, request, fields['actor_ref'],
            fields['paper_issuance_ref'], question, scope, fields['approval_ref'],
            fields['approval_revision'], fields['selection_decision_ref'],
            fields['selection_revision'], fields['source_revision'],
            fields['readiness_revision'], fields['confirmation_ref'], fields['state'])
    except Exception:
        raise PaperContactContractError('Installed current-question record is malformed.') from None


def _plan_request(value: object, limit: int) -> PaperAdmissionRequest:
    from grading.integration.paper_readiness_admission import _request
    return _request(value, limit)


def _relation_question(value: object, limit: int) -> IssuedQuestionExecutionRelation:
    if type(value) is not IssuedQuestionExecutionRelation:
        raise PaperContactContractError('Current-question relation is foreign.')
    try:
        return IssuedQuestionExecutionRelation(*(_id(object.__getattribute__(value, key), limit)
            for key in ('question_id', 'family', 'source_artifact_ref', 'evidence_scope_ref',
                'answer_region_ref', 'source_revision', 'provenance_ref', 'rubric_ref',
                'scoring_policy_ref')))
    except Exception:
        raise PaperContactContractError('Current-question relation is malformed.') from None


def _question_scope_matches(scope: ChoiceAdmissionScope, question: IssuedQuestionExecutionRelation,
                            plan: AdmittedPaperPlan) -> bool:
    req = plan.request
    return (scope.actor_ref == plan.actor_ref
            and scope.tenant_ref == req.tenant_ref
            and scope.session_ref == req.session_ref
            and scope.grading_run_id == req.grading_run_id
            and scope.submission_ref == req.submission_ref
            and scope.exam_ref == req.exam_ref
            and scope.grading_spec_ref == req.grading_spec_ref
            and scope.question_id == question.question_id
            and scope.source_artifact_ref == question.source_artifact_ref
            and scope.evidence_scope_ref == question.evidence_scope_ref
            and scope.source_revision == question.source_revision
            and scope.ocr_provenance == question.provenance_ref)


class ProductionPaperQuestionContact:
    """Owned numeric evaluation + installed PRE/approved eligibility and execution policy + current issuer: ZERO physical attempt claim/evaluator effects.

    The final criterion scoring executor MUST recheck these facts in the same operation as physical attempt claim
    and evaluator contact.  This class must never expose a reusable grant.
    """
    __slots__ = ('_installation',)

    def __setattr__(self, name: str, value: object) -> None:
        if name == '__class__':
            raise PaperContactContractError('Installed root class cannot be replaced.')
        if name == '_installation':
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass
            else:
                raise PaperContactContractError('Installed root cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        raise PaperContactContractError('Installed root cannot be deleted.')

    def __init__(self, *, correlation: ProductionPaperExecutionCorrelation,
                 handoff: ProductionExecutionHandoff,
                 issuer: CurrentQuestionContactIssuer,
                 max_questions: int, max_identifier_characters: int) -> None:
        try:
            try:
                if (type(correlation) is not ProductionPaperExecutionCorrelation
                    or type(handoff) is not ProductionExecutionHandoff
                    or type(max_questions) is not int or not 0 < max_questions <= 1000
                    or type(max_identifier_characters) is not int
                    or not 0 < max_identifier_characters <= 4096):
                    raise PaperContactContractError('Installed contact composition is invalid.')
                installed = object.__getattribute__(handoff, '_installation')
                entry = object.__getattribute__(installed, 'entry')
                if (type(entry) is not ProductionGradingEntry
                    or type(object.__getattribute__(installed, 'runtime'))
                        is not ProductionEvaluatorRuntimeBinder
                    or type(object.__getattribute__(installed, 'eligibility'))
                        is not ProductionExecutionEligibilityComposer):
                    raise PaperContactContractError('Installed execution source is invalid.')
                preparation = object.__getattribute__(entry, '_preparation')
                choices = object.__getattribute__(entry, '_choices')
                if (type(preparation) is not ProductionPreparationComposer
                    or type(choices) is not ProductionChoiceAdmissionComposer
                    or any(name in object.__getattribute__(obj, '__dict__')
                        for obj, names in ((entry, ('prepare_choice',)),
                            (preparation, ('prepare',)),
                            (choices, ('preauthorize', 'admit')))
                        for name in names)):
                    raise PaperContactContractError('Installed admission source is invalid.')
                # Capture the actual PRE/CHOICE authority targets, not only
                # the composer objects and their dispatch method names.
                prep_ops = object.__getattribute__(preparation, '_operations')
                choice_ops = object.__getattribute__(choices, '_operations')
                prep_names = ('current_actor', 'authorize_preparation',
                    'resolve_approved_policy', 'resolve_revisioned_preparation',
                    'open_authorized_evidence')
                choice_names = ('authorize_choice_request', 'authorize_choice',
                    'resolve_approved_choice_key',
                    'resolve_verified_choice_selection', 'confirm_choice_revisions')
                if (type(prep_ops) is not dict or type(choice_ops) is not dict
                    or any(type(key) is not str for key in prep_ops)
                    or any(type(key) is not str for key in choice_ops)
                    or set(prep_ops) != set(prep_names)
                    or set(choice_ops) != set(choice_names)):
                    raise PaperContactContractError('Installed authority target inventory changed.')
                prep_targets = tuple((name, prep_ops[name]) for name in prep_names)
                choice_targets = tuple((name, choice_ops[name]) for name in choice_names)
                handoff._require_root()
                method = object.__getattribute__(issuer, 'confirm_current_question_contact')
                if not callable(method):
                    raise PaperContactContractError('Current contact issuer is not callable.')
                self._installation = _Installation(correlation, handoff, method,
                    max_questions, max_identifier_characters, entry,
                    object.__getattribute__(installed, 'runtime'),
                    object.__getattribute__(installed, 'eligibility'),
                    preparation, choices, prep_ops, choice_ops,
                    prep_targets, choice_targets,
                    object.__getattribute__(preparation, '_maximum'),
                    tuple(object.__getattribute__(choices, attr) for attr in
                        ('_limit', '_max_options', '_max_criteria')))
            except Exception:
                raise PaperContactContractError('Installed contact composition is invalid.') from None
        except PaperContactContractError as exc:
            raise _clean_exception(exc)

    def preflight_choice(self, *, plan: AdmittedPaperPlan,
                         question_id: str) -> NonExecutingQuestionContact:
        try:
            return self._preflight_choice(plan=plan, question_id=question_id)
        except (PaperContactDenied, PaperContactUnavailable, PaperContactContractError) as exc:
            raise _clean_exception(exc) from None
        except Exception:
            raise _clean_exception(PaperContactUnavailable(
                'Execution contact preflight is unavailable.')) from None

    @staticmethod
    def _require_installed_handoff(config: _Installation) -> None:
        # An installed handoff is not trusted merely because its current
        # methods return plausibly shaped data. Python permits ordinary
        # __class__ replacement with layout-compatible subclasses.
        if type(config.handoff) is not ProductionExecutionHandoff:
            raise PaperContactDenied('Installed execution handoff class changed.')
        # Verify the actual dispatch graph, not just the outer handoff.  An
        # unchanged handoff can otherwise return cached preparation, CHOICE, or evaluator-invocation records
        # from replaced nested delegates or instance-shadowed methods.
        installed = object.__getattribute__(config.handoff, '_installation')
        entry = object.__getattribute__(installed, 'entry')
        runtime = object.__getattribute__(installed, 'runtime')
        eligibility = object.__getattribute__(installed, 'eligibility')
        if (type(entry) is not ProductionGradingEntry
            or entry is not config.installed_entry
            or type(runtime) is not ProductionEvaluatorRuntimeBinder
            or runtime is not config.installed_runtime
            or type(eligibility) is not ProductionExecutionEligibilityComposer
            or eligibility is not config.installed_eligibility):
            raise PaperContactDenied('Installed execution source changed.')
        preparation = object.__getattribute__(entry, '_preparation')
        choices = object.__getattribute__(entry, '_choices')
        if (preparation is not config.installed_preparation
            or choices is not config.installed_choices
            or type(preparation) is not ProductionPreparationComposer
            or type(choices) is not ProductionChoiceAdmissionComposer):
            raise PaperContactDenied('Installed PRE/CHOICE delegates changed.')
        # Verify original PRE/CHOICE authority function identity. Replacing an
        # operation in either mutable dictionary bypasses an unchanged wrapper
        # class/method and may replay prior valid-looking issuer facts.
        prep_ops = object.__getattribute__(preparation, '_operations')
        choice_ops = object.__getattribute__(choices, '_operations')
        for current, installed, targets in (
            (prep_ops, config.installed_preparation_operations,
                config.installed_preparation_targets),
            (choice_ops, config.installed_choice_operations,
                config.installed_choice_targets)):
            if (type(current) is not dict or current is not installed
                    or len(current) != len(targets)
                    or any(type(key) is not str for key in current)):
                raise PaperContactDenied('Installed PRE/CHOICE authority targets changed.')
            if any(current.get(name) is not target for name, target in targets):
                raise PaperContactDenied('Installed PRE/CHOICE authority targets changed.')
        # The PRE/CHOICE resource ceilings govern downstream admission.
        # An unchanged composer class is not proof that its installed ceilings
        # have remained intact across an issuer callback.
        prep_limit = object.__getattribute__(preparation, '_maximum')
        choice_limits = tuple(object.__getattribute__(choices, attr) for attr in
            ('_limit', '_max_options', '_max_criteria'))
        if (type(prep_limit) is not int or prep_limit != config.installed_preparation_limit
                or any(type(value) is not int for value in choice_limits)
                or choice_limits != config.installed_choice_limits):
            raise PaperContactDenied('Installed PRE/CHOICE resource limits changed.')
        # These three objects intentionally support __dict__; their dispatch
        # methods must not be replaced by per-instance attributes.  The
        # remaining installed runtime components have exact-class checks.
        if any(name in object.__getattribute__(obj, '__dict__')
               for obj, names in ((entry, ('prepare_choice',)),
                                  (preparation, ('prepare',)),
                                  (choices, ('preauthorize', 'admit')))
               for name in names):
            raise PaperContactDenied('Installed admission method changed.')

    def _preflight_choice(self, *, plan: AdmittedPaperPlan,
                          question_id: str) -> NonExecutingQuestionContact:
        config = object.__getattribute__(self, '_installation')
        guard_lease = _enter_thread_preflight(self)
        try:
            self._require_installed_handoff(config)
            limit, maximum = config.identifier_limit, config.max_questions
            requested_id = _id(question_id, limit)
            original = _plan(plan, maximum, limit)
            # Caller-selected question must belong to the original selected set
            # before contacting even the first installed authority.
            if requested_id not in {q.request.question_id for q in original.questions}:
                raise PaperContactDenied('Question is not selected for the admitted paper.')
            try:
                correlation = config.correlation.preflight(plan=plan)
            finally:
                self._require_installed_handoff(config)
            if (_plan(plan, maximum, limit) != original
                    or _plan(correlation.plan, maximum, limit) != original):
                raise PaperContactDenied('Paper changed during correlation.')
            issued = _relation(correlation.issuer_relation, maximum, limit)
            if len(issued.questions) != len(original.questions):
                raise PaperContactDenied('Current paper inventory is incomplete.')
            matches = [q for q in issued.questions if q.question_id == requested_id]
            if len(matches) != 1:
                raise PaperContactDenied('Question is not selected exactly once.')
            question = matches[0]
            if question.family != 'CHOICE' or correlation.execution_state != 'CORRELATED_CHOICE_ONLY':
                raise PaperContactDenied('Question family is not qualified for CHOICE execution.')
            chosen = next(q for q in original.questions if q.request.question_id == requested_id)
            self._require_installed_handoff(config)
            config.handoff._require_root()
            try:
                bound = config.handoff.prepare_choice_runtime(request=chosen.request)
            finally:
                self._require_installed_handoff(config)
            config.handoff._require_root()
            original_binding = _validated_binding_snapshot(bound, handoff=config.handoff, maximum=limit)
            scope = original_binding[0]
            if original_binding[8].handler is not evaluate_single_select_choice:
                raise PaperContactDenied('Installed runtime is not the frozen CHOICE handler.')
            if not _question_scope_matches(scope, question, original):
                raise PaperContactDenied('Installed CHOICE scope does not belong to official paper question.')
            if (_plan(plan, maximum, limit) != original
                    or _plan(correlation.plan, maximum, limit) != original
                    or _relation(correlation.issuer_relation, maximum, limit) != issued
                    or _scope(scope, limit) != original_binding[0]):
                raise PaperContactDenied('Paper or scope changed during runtime preparation.')
            # Explicitly carry the answer-region not present in ChoiceAdmissionScope;
            # the installed issuer must attest the relation, not infer it from IDs.
            self._require_installed_handoff(config)
            try:
                try:
                    fact_raw = config.operation(correlation=correlation,
                        question=question, scope=scope)
                except PaperContactDenied:
                    raise PaperContactDenied('Current school issuer denied this question.') from None
                except Exception:
                    raise PaperContactUnavailable('Current school issuer unavailable.') from None
            finally:
                self._require_installed_handoff(config)
            fact = _fact(fact_raw, limit)
            config.handoff._require_root()
            if (_scope(scope, limit) != original_binding[0]
                or _validated_binding_snapshot(bound, handoff=config.handoff, maximum=limit)
                    != original_binding
                or _plan(plan, maximum, limit) != original
                or _plan(correlation.plan, maximum, limit) != original
                or _relation(correlation.issuer_relation, maximum, limit) != issued):
                raise PaperContactDenied('Source or runtime changed during current-question confirmation.')
            if (fact.state != 'CURRENT_AUTHORIZED' or fact.request != original.request
                    or fact.actor_ref != original.actor_ref
                    or fact.paper_issuance_ref != issued.issuance_ref
                    or fact.question != question or fact.scope != scope
                    or fact.approval_ref != original.approval_ref
                    or fact.approval_revision != original.approval_revision
                    or fact.selection_decision_ref != original.selection_decision_ref
                    or fact.selection_revision != original.selection_revision
                    or fact.source_revision != original.source_revision
                    or fact.readiness_revision != original.readiness_revision):
                raise PaperContactDenied('Current-question approval does not bind approved paper.')
            runtime = original_binding[8]
            return NonExecutingQuestionContact(issued.issuance_ref, requested_id,
                fact.confirmation_ref, runtime.runtime_id, runtime.runtime_version,
                runtime.implementation_ref, 'PREFLIGHT_ONLY', question, issued)
        except (PaperContactDenied, PaperContactUnavailable):
            raise
        except (PaperExecutionDenied,):
            raise PaperContactDenied('Official paper correlation was denied.') from None
        except (PaperExecutionUnavailable,):
            raise PaperContactUnavailable('Official paper correlation is unavailable.') from None
        except (PaperExecutionContractError, PaperContactContractError):
            raise PaperContactContractError('Official contact facts are malformed.') from None
        except (ValueError, TypeError, AttributeError):
            raise PaperContactContractError('Official contact input is malformed.') from None
        finally:
            _leave_thread_preflight(guard_lease)
