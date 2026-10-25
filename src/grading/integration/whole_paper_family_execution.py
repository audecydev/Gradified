"""Installed DIRECT/NUMERIC physical grading for source-approved FIRST/REGRADE.

This owner consumes current school-issued paper identity, installed evaluator eligibility policy/evaluator admission/evaluator selection
runtime authority and a real, conditional original physical attempt for each selected
question. It invokes the existing family evaluation/deterministic scoring/frozen scorer exactly
once. Its output is *not* a scored-CAS custody record or a publication permit.

The qualified sources and the joint effect owner must be installed by the
trusted integration root. Protocol conformance is not backend authentication,
atomicity, or proof of school authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from grading.active_question_authority import ContextPolicy
from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.integration.evidence_ingress import AdmittedNormalizedEvidence
from grading.integration.evaluation_binding import bind_question_evaluation_inputs
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.numeric_evaluation import (
    DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION,
)
from grading.contracts.paper_aggregation import ResolvedPaperScoringAuthority, _validate_resolved_paper_scoring_authority
from grading.execution import GradingExecutionContext, GradingExecutionResult
from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.execution_eligibility import _capture, _scope, _id
from grading.integration.direct_provider_route import (
    capture_direct_route_installation, require_direct_route_installation,
)
from grading.integration.evaluator_execution_binding import ProductionEvaluatorRuntimeBinder
from grading.integration.attempt_authority import (
    ClaimedAttemptAllocator, DefinitiveAttemptClaimRefusal, AttemptClaimRequest,
)
from grading.integration.evaluator_invocation import (
    AttemptReservation, _reservation_copy,
)
from grading.integration.paper_execution_correlation import (
    ProductionPaperExecutionCorrelation, IssuedPaperExecutionRelation,
    _plan, _relation,
)
from grading.integration.paper_readiness_admission import AdmittedPaperPlan
from grading.integration.paper_lifecycle import PaperLifecyclePermission, PaperLifecycleKind
from grading.integration.paper_family_evaluation import (
    DirectQuestionEvaluation, NumericQuestionEvaluation,
    _admitted_values, _detached_admitted, _selected_evidence_values,
    evaluate_supported_paper_questions,
)
from grading.integration.whole_paper_choice_execution import (
    AttemptContactTrace, _enter_effectful, _leave_effectful,
)
from grading.numeric_authority import resolve_numeric_authority, ResolvedNumericAuthority
from grading.numeric_evidence import admit_numeric_scalar


class FamilyPhysicalDenied(ValueError):
    """Source, runtime, family, or official paper cannot be admitted."""


@dataclass(frozen=True, slots=True, repr=False)
class FamilyPaperInputs:
    """Source-returned inputs; not caller permission or an attempt credential."""
    context: GradingExecutionContext
    evidence: AdmittedNormalizedEvidence
    paper_authority: ResolvedPaperScoringAuthority
    operations: tuple[DirectQuestionEvaluation | NumericQuestionEvaluation, ...]
    scopes: tuple[ChoiceAdmissionScope, ...]


class QualifiedFamilyPaperInputsSource(Protocol):
    """Authorized materialization of the exact current paper/evidence/runtimes.

    The backend must authorize this read to an already-issued plan. The engine
    independently cross-checks each selected question and re-reads on contact.
    """
    def resolve_family_paper_inputs(self, *, plan: AdmittedPaperPlan) -> FamilyPaperInputs: ...


@dataclass(frozen=True, slots=True, repr=False)
class CapturedFamilyAttempt:
    question_id: str
    family: str
    reservation: AttemptReservation
    judgments: tuple[EvaluatedCriterionJudgment, ...]


@dataclass(frozen=True, slots=True, repr=False)
class FamilyPaperExecutionOutcome:
    state: str
    completed: tuple[CapturedFamilyAttempt, ...]
    result: GradingExecutionResult | None
    failed_question_id: str | None
    contact_trace: tuple[AttemptContactTrace, ...]
    observed_reservations: tuple[AttemptReservation, ...]
    issued_paper: IssuedPaperExecutionRelation | None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class ProductionWholePaperFamilyExecutor:
    """Effectful FIRST/REGRADE family paper root; no caller-supplied runtime grants.

    Claims all current, independently approved selected question identities
    before evaluation. A failed claim/provider/score never yields a partial
    authoritative score. Every contacted request is retained as observation
    for read-only original-key reconciliation by a later custody owner.
    """
    __slots__ = ('_correlation', '_binder', '_attempts', '_resolve', '_max', '_questions', '_direct_route')

    def __init__(self, *, correlation: ProductionPaperExecutionCorrelation,
                 runtime: ProductionEvaluatorRuntimeBinder,
                 attempts: ClaimedAttemptAllocator,
                 inputs: QualifiedFamilyPaperInputsSource,
                 max_identifier_characters: int, max_questions: int,
                 direct_route=None) -> None:
        if (type(correlation) is not ProductionPaperExecutionCorrelation
                or type(runtime) is not ProductionEvaluatorRuntimeBinder
                or type(attempts) is not ClaimedAttemptAllocator
                or type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 1000
                or attempts.academic_binding_enabled is not True
                or attempts._joint_effect is None):
            raise ValueError('Exact qualified joint family execution installation is required.')
        from grading.integration.direct_provider_route import ProductionDirectProviderRoute
        if direct_route is not None and type(direct_route) is not ProductionDirectProviderRoute:
            raise ValueError('Foreign DIRECT route owner.')
        # Captured, exact-signature operation; no dynamic caller-selected source.
        operation = _capture(inputs, 'resolve_family_paper_inputs', ('plan',))
        runtime._require_installed_eligibility()
        object.__setattr__(self, '_correlation', correlation)
        object.__setattr__(self, '_binder', runtime)
        object.__setattr__(self, '_attempts', attempts)
        object.__setattr__(self, '_resolve', operation)
        object.__setattr__(self, '_max', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        object.__setattr__(self, '_direct_route', direct_route)

    def __setattr__(self, name, value):
        raise AttributeError('Installed family effect owner cannot be changed.')

    def __delattr__(self, name):
        raise AttributeError('Installed family effect owner cannot be changed.')

    def _current(self, plan, original, issued):
        """Full cheap preflight, without physical claims or provider invocation."""
        self._binder._require_installed_eligibility()
        before = self._correlation.preflight(plan=plan)
        if (before.execution_state != 'CORRELATED_DIRECT_NUMERIC'
                or _relation(before.issuer_relation, self._questions, self._max) != issued
                or _plan(plan, self._questions, self._max) != original):
            raise FamilyPhysicalDenied('Selected paper or current issuer changed.')
        raw = self._resolve(plan=_plan(original, self._questions, self._max))
        if type(raw) is not FamilyPaperInputs:
            raise FamilyPhysicalDenied('Installed source returned foreign family paper.')
        if (type(raw.context) is not GradingExecutionContext
                or type(raw.evidence) is not AdmittedNormalizedEvidence
                or type(raw.paper_authority) is not ResolvedPaperScoringAuthority
                or type(raw.operations) is not tuple
                or type(raw.scopes) is not tuple
                or len(raw.operations) != len(original.questions)
                or len(raw.scopes) != len(original.questions)):
            raise FamilyPhysicalDenied('Incomplete full-paper family source.')
        # Admit the complete original typed graph before *any* cross-record
        # equality; even frozen domain containers can contain a foreign value
        # installed with object.__setattr__. Never invoke its __eq__.
        _admitted_values((raw.context, raw.evidence.evidence, raw.paper_authority))
        authority = _validate_resolved_paper_scoring_authority(raw.paper_authority)
        evidence = raw.evidence.evidence
        if type(raw.evidence.raw_payload_sha256) is not str or len(raw.evidence.raw_payload_sha256) != 64:
            raise FamilyPhysicalDenied('Missing normalized evidence admission evidence origin.')
        if (authority.grading_spec_ref != issued.request.grading_spec_ref
                or tuple(v.question_id for v in authority.expected_questions)
                   != tuple(q.question_id for q in issued.questions)
                or raw.context.grading_run_id != original.request.grading_run_id
                or raw.context.submission_ref != original.request.submission_ref
                or raw.context.exam_ref != original.request.exam_ref
                or raw.context.grading_spec_ref != original.request.grading_spec_ref
                or evidence.submission_ref != original.request.submission_ref):
            raise FamilyPhysicalDenied('Full-paper scoring/context/evidence differs from issuance.')
        from grading.integration.academic_claim_binding import academic_intent
        from grading.contracts.paper_aggregation import ExpectedQuestionResult
        for q, expected in zip(issued.questions, authority.expected_questions, strict=True):
            if (type(expected) is not ExpectedQuestionResult or expected.question_id != q.question_id
                    or expected.rubric_ref.id != q.rubric_ref
                    or expected.scoring_policy_ref.id != q.scoring_policy_ref):
                raise FamilyPhysicalDenied('Versioned score inventory is not original issuance.')
        ids = {q.question_id for q in issued.questions}
        _selected_evidence_values(evidence, ids)
        # Reject hostile nested data *before* duplicate checks, comparison or
        # any callback-driven copy of authoritative academic/evidence content.
        _admitted_values((raw.context, evidence, raw.paper_authority))
        for q, operation, scope, planned, expected in zip(issued.questions, raw.operations,
                                                raw.scopes, original.questions, authority.expected_questions, strict=True):
            if type(operation) not in (DirectQuestionEvaluation, NumericQuestionEvaluation):
                raise FamilyPhysicalDenied('Unsupported/foreign family evaluator.')
            _admitted_values(operation.authority)
            if (type(scope) is not ChoiceAdmissionScope
                    or _scope(scope, self._max) != scope
                    or (type(operation) is DirectQuestionEvaluation) != (q.family == 'DIRECT')
                    or operation.authority.question_id != q.question_id
                    or operation.authority.grading_spec_ref != authority.grading_spec_ref
                    or scope.question_id != q.question_id
                    or scope.source_artifact_ref != q.source_artifact_ref
                    or scope.evidence_scope_ref != q.evidence_scope_ref
                    or scope.source_revision != q.source_revision
                    or scope.ocr_provenance != q.provenance_ref
                    or scope.actor_ref != original.actor_ref
                    or (scope.tenant_ref, scope.session_ref, scope.grading_run_id,
                        scope.submission_ref, scope.exam_ref, scope.grading_spec_ref) !=
                       (original.request.tenant_ref, original.request.session_ref,
                        original.request.grading_run_id, original.request.submission_ref,
                        original.request.exam_ref, original.request.grading_spec_ref)):
                raise FamilyPhysicalDenied('Family runtime/evidence scope differs from official paper.')
            # Actual question evidence binding four-root binding and complete scoring version check
            # precede ANY avoidable physical attempt claim contact.
            bind_question_evaluation_inputs(
                context=raw.context, admitted_evidence=raw.evidence,
                paper_authority=authority, question_authority=operation.authority)
            scoring = operation.authority.scoring_authority
            if (RubricRef(scoring.rubric.rubric_id, scoring.rubric.version) != expected.rubric_ref
                    or ScoringPolicyRef(scoring.policy.policy_id, scoring.policy.version,
                                        scoring.policy.scoring_semantics_version) != expected.scoring_policy_ref):
                raise FamilyPhysicalDenied('Scoring authority differs from original paper.')
            # Preclaim the deterministic parts for *every* selected question.
            if type(operation) is DirectQuestionEvaluation:
                if (type(operation.evaluator) is not __import__(
                        'grading.semantic_evaluator', fromlist=['DirectTextSemanticEvaluator']).DirectTextSemanticEvaluator
                        or operation.authority.context_policy is not ContextPolicy.DIRECT):
                    raise FamilyPhysicalDenied('DIRECT evaluator is unqualified.')
                operation.evaluator.preflight_local(
                    authority=operation.authority, evidence=evidence,
                    execution_context=raw.context,
                    evaluation_attempt_id=operation.evaluation_attempt_id)
            else:
                if operation.authority.context_policy is not ContextPolicy.DIRECT:
                    raise FamilyPhysicalDenied('NUMERIC context policy is unsupported.')
                checked = resolve_numeric_authority(
                    active_authority=operation.authority,
                    binding_source=operation.binding_source,
                    authority_source=operation.authority_source)
                if type(checked) is not ResolvedNumericAuthority:
                    raise FamilyPhysicalDenied('NUMERIC grading authority is not approved.')
                admit_numeric_scalar(evidence=evidence, question_id=q.question_id)
        # Snapshot only immutable, already admitted values. Source-owned
        # evaluators/callbacks remain installed operations, not copyable facts.
        academic = _detached_admitted((raw.context, evidence, raw.paper_authority))
        detached_ops = tuple(
            DirectQuestionEvaluation(_detached_admitted(op.authority), op.evaluator,
                                     op.evaluation_attempt_id) if type(op) is DirectQuestionEvaluation
            else NumericQuestionEvaluation(_detached_admitted(op.authority),
                                           op.binding_source, op.authority_source)
            for op in raw.operations)
        # Keep the genuine normalized OCR evidence admission admission root, while detaching its evidence before
        # evaluator/provider callbacks to prevent source mutation/restore.
        return FamilyPaperInputs(academic[0], raw.evidence, academic[2], detached_ops,
                                 tuple(_scope(s, self._max) for s in raw.scopes))

    def execute_first(self, *, plan: AdmittedPaperPlan,
                      permission: PaperLifecyclePermission) -> FamilyPaperExecutionOutcome:
        return self._execute(plan=plan, permission=permission, kind=PaperLifecycleKind.FIRST)

    def execute_regrade(self, *, plan: AdmittedPaperPlan,
                        permission: PaperLifecyclePermission) -> FamilyPaperExecutionOutcome:
        """The owning paper lifecycle/CAS lifecycle must already hold the exact regrade lease.

        Regrade predecessor and original historical requests are verified by paper lifecycle
        before this method; the allocator rechecks their issued identities at
        every actual physical attempt request. Direct callers cannot create that lease.
        """
        return self._execute(plan=plan, permission=permission, kind=PaperLifecycleKind.REGRADE)

    def _execute(self, *, plan: AdmittedPaperPlan,
                 permission: PaperLifecyclePermission,
                 kind: PaperLifecycleKind) -> FamilyPaperExecutionOutcome:
        lease = _enter_effectful(self)
        traces = []
        reservations = []
        current_qid = None
        issued = None
        possible_effect = False
        purpose_token = None
        try:
            try:
                # Capture the entire effect owner BEFORE issuer, academic,
                # runtime, and route source callbacks can replace its sender.
                route = self._direct_route
                original_route_installation = capture_direct_route_installation(route)

                def unchanged_route():
                    require_direct_route_installation(self._direct_route,
                                                      original_route_installation)
                    return True

                original = _plan(plan, self._questions, self._max)
                if (type(permission) is not PaperLifecyclePermission or permission.kind is not kind):
                    raise FamilyPhysicalDenied('Wrong original lifecycle authorization operation.')
                if kind is PaperLifecycleKind.FIRST:
                    if permission.predecessor is not None or permission.predecessor_custody is not None:
                        raise FamilyPhysicalDenied('FIRST cannot reuse a predecessor.')
                elif (kind is not PaperLifecycleKind.REGRADE
                        or self._attempts._regrade_permission() is not permission
                        or permission.predecessor is None
                        or permission.predecessor_custody is None):
                    raise FamilyPhysicalDenied('Original source-issued REGRADE lease and predecessor required.')
                _plan(permission.plan, self._questions, self._max)
                if permission.plan != original:
                    raise FamilyPhysicalDenied('FIRST lifecycle authorization paper differs from current paper.')
                issued = _relation(self._correlation.preflight(plan=plan).issuer_relation,
                                   self._questions, self._max)
                full = self._current(plan, original, issued)
                original_values = _admitted_values((full.context, full.evidence.evidence, full.paper_authority,
                    tuple(op.authority for op in full.operations), full.scopes))
                # In-process physical attempt callbacks may mutate a frozen evaluator with
                # object.__setattr__. Preserve its *original installed deps*,
                # not just the identity of its outer evaluator object.
                direct_installations = tuple(
                    (op.evaluator._provider, op.evaluator._model_answer_source,
                     _admitted_values(op.evaluator._limits),
                     _admitted_values(op.evaluator._evaluator_metadata))
                    if type(op) is DirectQuestionEvaluation else None
                    for op in full.operations)
                unchanged_route()
                route_grants = tuple(
                    route.preflight(plan=original,question_id=q.question_id,
                        purpose=kind.value,evaluator=op.evaluator)
                    if route is not None and type(op) is DirectQuestionEvaluation else None
                    for q,op in zip(issued.questions,full.operations,strict=True))

                def unchanged_direct_installations():
                    return all(
                        installed is None or (
                            type(op) is DirectQuestionEvaluation
                            and op.evaluator._provider is installed[0]
                            and op.evaluator._model_answer_source is installed[1]
                            and _admitted_values(op.evaluator._limits) == installed[2]
                            and _admitted_values(op.evaluator._evaluator_metadata) == installed[3])
                        for op, installed in zip(full.operations, direct_installations, strict=True))
                # Qualify the exact academic/model-answer request for the entire
                # admitted paper before any avoidable physical attempt claim. This
                # never calls the provider. Preserve its immutable request for
                # the eventual attempt-bound sender after physical attempt claim.
                from grading.providers.semantic_replay import (
                    direct_text_semantic_request_fingerprint, _direct_text_semantic_request_bytes,
                )
                prepared_requests = tuple(
                    op.evaluator.prepare_request(
                        authority=op.authority, evidence=full.evidence.evidence,
                        execution_context=full.context,
                        evaluation_attempt_id=op.evaluation_attempt_id)
                    if route is not None and type(op) is DirectQuestionEvaluation else None
                    for op in full.operations)
                if any(prepared is not None and (
                    prepared.question_id != grant.question_id or
                    direct_text_semantic_request_fingerprint(prepared) != grant.request_sha256 or
                    len(_direct_text_semantic_request_bytes(prepared)) > route._max_request)
                    for prepared, grant in zip(prepared_requests, route_grants, strict=True)):
                    raise FamilyPhysicalDenied('Approved DIRECT request differs before grading-attempt.')
                # Approval readers are external callbacks: they may change the
                # already-resolved installation. Deny before beginning legal operation transition/physical attempt claim
                # rather than comparing a poisoned post-callback baseline.
                if not unchanged_direct_installations() or not unchanged_route():
                    raise FamilyPhysicalDenied('DIRECT route source changed installed effect owner.')
                # Every execution is tied to installed effect-time purpose
                # guard, not to an arbitrary admission/result object.
                if kind is PaperLifecycleKind.FIRST:
                    purpose_token = self._attempts.begin_authorized_first(
                        plan=original, permission=permission)
                bound = []
                runtime_bindings = []
                for question, op, scope in zip(issued.questions, full.operations, full.scopes, strict=True):
                    current_qid = question.question_id
                    fresh = self._current(plan, original, issued)
                    if (_admitted_values((fresh.context, fresh.evidence.evidence, fresh.paper_authority,
                            tuple(x.authority for x in fresh.operations), fresh.scopes)) != original_values
                            or tuple(type(x) for x in fresh.operations) != tuple(type(x) for x in full.operations)
                            or any((type(a) is DirectQuestionEvaluation and a.evaluator is not b.evaluator)
                                   or (type(a) is NumericQuestionEvaluation and (
                                      a.binding_source is not b.binding_source or
                                      a.authority_source is not b.authority_source))
                                   for a, b in zip(fresh.operations, full.operations, strict=True))):
                        raise FamilyPhysicalDenied('Family source or evaluator changed before grading-attempt.')
                    if not unchanged_direct_installations() or not unchanged_route():
                        raise FamilyPhysicalDenied('Installed DIRECT dependencies changed before grading-attempt.')
                    runtime = self._binder.bind_family(
                        scope=scope, family=question.family,
                        context_policy=op.authority.context_policy)
                    approval = runtime.approved_runtime
                    selected_metadata = runtime.eligibility.selection.selected_capability_ref.evaluator_metadata
                    if (question.family == 'DIRECT' and
                            _admitted_values(op.evaluator._evaluator_metadata)
                              != _admitted_values(selected_metadata)):
                        raise FamilyPhysicalDenied('Installed DIRECT executable identity does not match evaluator selection.')
                    if (question.family == 'NUMERIC' and
                            (selected_metadata.evaluator_id, selected_metadata.version) !=
                            (DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION)):
                        raise FamilyPhysicalDenied('NUMERIC selected evaluator is not the frozen N1–N4 implementation.')
                    # Runtime approval callback may have changed the official
                    # issuer or the selected entire paper. Recheck after it.
                    again = self._correlation.preflight(plan=plan)
                    if (_relation(again.issuer_relation, self._questions, self._max) != issued
                            or again.execution_state != 'CORRELATED_DIRECT_NUMERIC'
                            or _plan(plan, self._questions, self._max) != original):
                        raise FamilyPhysicalDenied('Family issuance changed after runtime binding.')
                    if route is not None and type(op) is DirectQuestionEvaluation:
                        route.require_current(route_grants[len(bound)],original,op.evaluator)
                    # require_current itself reads an external approval source.
                    if not unchanged_direct_installations() or not unchanged_route():
                        raise FamilyPhysicalDenied('DIRECT installation changed on current route read.')
                    token = self._attempts.begin_operation()
                    reservation = None
                    original_request: AttemptClaimRequest | None = None
                    academic_preparation = None
                    stable = None
                    validated = False
                    try:
                        # begin_operation may also execute installed backend code.
                        # No physical attempt claim has begun at this point; denial is still safe.
                        if not unchanged_direct_installations() or not unchanged_route():
                            raise FamilyPhysicalDenied('DIRECT installation changed before physical claim.')
                        try:
                            possible_effect = True
                            reservation = self._attempts.reserve_academically_bound_attempt(
                                scope=_scope(scope, self._max), family=question.family,
                                runtime_id=approval.runtime_id,
                                runtime_version=approval.runtime_version,
                                implementation_ref=approval.implementation_ref,
                                eligibility_policy_id=runtime.eligibility.policy.policy_id,
                                eligibility_policy_version=runtime.eligibility.policy.policy_version,
                                academic_paper=issued, academic_scoring=full.paper_authority,
                                approved_runtime=approval)
                            if type(reservation) is not AttemptReservation:
                                raise FamilyPhysicalDenied('grading-attempt returned no exact reservation.')
                            reservations.append(reservation)
                            stable = reservation.request_ref
                            expected = AttemptReservation(scope, '', '', question.family,
                                approval.runtime_id, approval.runtime_version,
                                approval.implementation_ref, runtime.eligibility.policy.policy_id,
                                runtime.eligibility.policy.policy_version)
                            _reservation_copy(reservation, expected=expected, maximum=self._max)
                            validated = True
                            if (type(stable) is not str or not stable
                                    or any(x.request_ref == stable or x.attempt_id == reservation.attempt_id
                                        or x.reservation_ref == reservation.reservation_ref for x in reservations[:-1])):
                                raise FamilyPhysicalDenied('grading-attempt reused or omitted a physical attempt identity.')
                        finally:
                            try:
                                original_request = self._attempts.observed_original_request()
                            except Exception:
                                pass
                            try:
                                academic_preparation = self._attempts.observed_academic_preparation()
                            except Exception:
                                pass
                            if stable is None and original_request is not None:
                                stable = original_request.request_ref
                            traces.append(AttemptContactTrace(question.question_id, stable, True,
                                type(reservation) is AttemptReservation,
                                validated,
                                False, False, False, original_request,
                                academic_preparation, approval))
                        # Fresh issuer/runtime approval must still agree after
                        # the physical callback. No second claim on mismatch.
                        after = self._correlation.preflight(plan=plan)
                        if (_relation(after.issuer_relation, self._questions, self._max) != issued
                                or after.execution_state != 'CORRELATED_DIRECT_NUMERIC'
                                or _plan(plan, self._questions, self._max) != original):
                            raise FamilyPhysicalDenied('Issuer changed during grading-attempt claim.')
                        after_runtime = self._binder.bind_family(
                            scope=scope, family=question.family,
                            context_policy=op.authority.context_policy)
                        if (_admitted_values(after_runtime.approved_runtime) != _admitted_values(approval)
                                or _admitted_values(after_runtime.eligibility) != _admitted_values(runtime.eligibility)):
                            raise FamilyPhysicalDenied('Runtime authorization changed during grading-attempt contact.')
                        bound.append(reservation)
                        runtime_bindings.append(runtime)
                        possible_effect = False
                    finally:
                        self._attempts.finish_operation(token=token)
                # Final whole-paper source and each installed runtime must still
                # agree before the first provider/score contact. This cannot
                # roll back physical attempt claim; such drift preserves the original claim as
                # indeterminate without manufacturing a score.
                final = self._current(plan, original, issued)
                if (_admitted_values((final.context, final.evidence.evidence,
                        final.paper_authority, tuple(op.authority for op in final.operations),
                        final.scopes)) != original_values):
                    raise FamilyPhysicalDenied('Final academic/evidence sources changed after grading-attempt.')
                for question, op, scope, baseline in zip(issued.questions, full.operations,
                        full.scopes, runtime_bindings, strict=True):
                    fresh_runtime = self._binder.bind_family(scope=scope, family=question.family,
                        context_policy=op.authority.context_policy)
                    if (_admitted_values(fresh_runtime.approved_runtime) !=
                            _admitted_values(baseline.approved_runtime)
                            or _admitted_values(fresh_runtime.eligibility) !=
                            _admitted_values(baseline.eligibility)):
                        raise FamilyPhysicalDenied('Runtime changed before real grading.')
                if not unchanged_direct_installations() or not unchanged_route():
                    raise FamilyPhysicalDenied('Installed DIRECT dependencies changed after grading-attempt.')
                # Only the physical original attempt ids can be sent to DIRECT;
                # N1–N4 has no separate caller-assigned attempt as numerical authority.
                graded_ops = tuple(
                    replace(op, evaluation_attempt_id=reservation.attempt_id,
                        evaluator=route.bind_attempt(approved=route_grants[i],
                            plan=original,evaluator=op.evaluator,reservation=reservation,
                            prepared_request=prepared_requests[i])
                        if route is not None else op.evaluator)
                    if type(op) is DirectQuestionEvaluation else op
                    for i,(op, reservation) in enumerate(zip(full.operations, bound, strict=True)))
                # bind_attempt performs a fresh untrusted issuer read after physical attempt claim.
                # No scored result may use a replaced model-answer or provider.
                if not unchanged_direct_installations() or not unchanged_route():
                    raise FamilyPhysicalDenied('DIRECT evaluator changed during attempt binding.')
                graded = evaluate_supported_paper_questions(
                    context=full.context, evidence=_detached_admitted(full.evidence.evidence),
                    paper_authority=full.paper_authority, operations=graded_ops)
                if (type(graded) is not GradingExecutionResult
                        or len(graded.questions) != len(bound)):
                    raise FamilyPhysicalDenied('Real family scoring result is incomplete.')
                completed = tuple(CapturedFamilyAttempt(
                    question.question_id, question.family, reservation,
                    scored.verified.evaluated_judgments)
                    for question, reservation, scored in zip(
                        issued.questions, bound, graded.questions, strict=True))
                for index, capture in enumerate(completed):
                    if (capture.question_id != graded.questions[index].score.question_id
                            or any(type(j) is not EvaluatedCriterionJudgment for j in capture.judgments)):
                        raise FamilyPhysicalDenied('Scored judgments do not belong to physical original attempts.')
                if not unchanged_direct_installations() or not unchanged_route():
                    raise FamilyPhysicalDenied('DIRECT evaluator changed during academic evaluation.')
                traces = [replace(trace, evaluator_invoked=True, judgments_emitted=True,
                                  s1_verified=True) for trace in traces]
                return FamilyPaperExecutionOutcome('COMPLETE', completed, graded, None,
                                                    tuple(traces), tuple(reservations), issued)
            except Exception:
                # A response after a durable claim might be lost. Even cleanly
                # returned physical attempt claim permits are consumption events if evaluation fails.
                state = ('INDETERMINATE' if possible_effect or reservations else 'DENIED')
                return FamilyPaperExecutionOutcome(state, (), None, current_qid,
                                                    tuple(traces), tuple(reservations), issued)
        finally:
            if purpose_token is not None:
                self._attempts.finish_authorized_first(token=purpose_token)
            _leave_effectful(lease)
