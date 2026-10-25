"""Trusted-root CHOICE key and canonical-selection admission before execution.

Backend ports establish authority. Matching Python records are not proof of their
origin, and a successful admission is neither eligibility nor permission to grade.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import inspect
from types import FunctionType
from typing import Callable, Protocol

from grading.contracts.choice import (
    CanonicalChoiceSelection, ChoiceCriterionProjection, ChoiceEvaluationAuthority,
    InvalidCanonicalChoiceSelectionError, InvalidChoiceEvaluationAuthorityError,
)
from grading.contracts.evidence import EvidenceBlockState
from grading.contracts.errors import ScoringError
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.integration.authorized_preparation import (
    AuthorizedPreparedQuestion, PreparationCustody,
)
from grading.integration.choice_binding import (
    BoundChoiceEvaluationInputs, ChoiceInputBindingError, _snapshot_prepared,
    bind_choice_evaluation_inputs,
)
from grading.integration.evaluation_binding import BoundQuestionEvaluationInputs
from grading.integration.evidence_ingress import (
    AdmittedNormalizedEvidence, NormalizedEvidenceAdmissionPolicy,
)
from grading.integration.trusted_preparation import (
    PreparedWithSourceCustody, PreparationRequest,
    PreparationSourceContractError, _request_snapshot,
)


class ChoiceAdmissionDenied(ValueError):
    """Choice source access or a required source-identity relationship was denied."""


class ChoiceAdmissionUnavailable(Exception):
    """Installed backend choice authority could not deliver a required fact."""


class ChoiceAdmissionContractError(ValueError):
    """A configured choice authority supplied an invalid structural record."""


def _id(value: object, limit: int) -> str:
    if type(value) is not str or not value or len(value) > limit or value.strip() != value:
        raise ChoiceAdmissionContractError("Choice authority identifier is malformed.")
    return value


def _field(value: object, name: str) -> object:
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        raise ChoiceAdmissionContractError("Choice authority record is incomplete.") from None


@dataclass(frozen=True, slots=True, repr=False)
class ChoiceAdmissionScope:
    actor_ref: str
    tenant_ref: str
    session_ref: str
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    grading_spec_ref: GradingSpecRef
    question_id: str
    evidence_scope_ref: str
    source_artifact_ref: str
    source_revision: str
    admission_policy_identity: str
    policy_revision: str
    ocr_provenance: str


@dataclass(frozen=True, slots=True, repr=False)
class ChoicePreEvidenceGrant:
    """Pre-read backend approval for the requested source and CHOICE revisions.

    Not an execution credential; full evidence-scope admission still follows PRE.
    """
    request: PreparationRequest
    source_artifact_ref: str
    source_revision: str
    key_revision: str
    selection_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class ChoiceAccessGrant:
    """Backend-issued source authorization; NOT a bearer authorization token."""
    scope: ChoiceAdmissionScope
    key_revision: str
    selection_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedChoiceKeyRecord:
    """Returned only by the installed official key/approval authority."""
    scope: ChoiceAdmissionScope
    key_revision: str
    approval_ref: str
    authority: ChoiceEvaluationAuthority


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedChoiceSelectionRecord:
    """Returned only by the installed OCR/selection-origin authority."""
    scope: ChoiceAdmissionScope
    selection_revision: str
    selection_origin_ref: str
    selection: CanonicalChoiceSelection


@dataclass(frozen=True, slots=True, repr=False)
class ChoiceRevisionConfirmation:
    """Post-read backend revision check, not an in-process transaction proof."""
    scope: ChoiceAdmissionScope
    key_revision: str
    selection_revision: str
    source_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class AdmittedChoice:
    """Detached CHOICE structural input plus scope references; never eligibility."""
    bound: BoundChoiceEvaluationInputs
    scope: ChoiceAdmissionScope
    key_revision: str
    selection_revision: str
    approval_ref: str
    selection_origin_ref: str


class ChoicePreEvidenceAuthority(Protocol):
    def authorize_choice_request(self, *, request: PreparationRequest) -> ChoicePreEvidenceGrant: ...


class ChoiceAccessAuthority(Protocol):
    def authorize_choice(self, *, scope: ChoiceAdmissionScope) -> ChoiceAccessGrant: ...


class OfficialChoiceKeyAuthority(Protocol):
    def resolve_approved_choice_key(self, *, grant: ChoiceAccessGrant) -> ApprovedChoiceKeyRecord: ...


class CanonicalSelectionAuthority(Protocol):
    def resolve_verified_choice_selection(self, *, grant: ChoiceAccessGrant) -> VerifiedChoiceSelectionRecord: ...


class ChoiceRevisionAuthority(Protocol):
    def confirm_choice_revisions(self, *, grant: ChoiceAccessGrant) -> ChoiceRevisionConfirmation: ...


def _scope_copy(value: object, limit: int) -> ChoiceAdmissionScope:
    if type(value) is not ChoiceAdmissionScope:
        raise ChoiceAdmissionContractError("Choice scope has invalid type.")
    spec = _field(value, "grading_spec_ref")
    if type(spec) is not GradingSpecRef:
        raise ChoiceAdmissionContractError("Choice grading-spec reference has invalid type.")
    version = _field(spec, "version")
    if type(version) is not int or version <= 0:
        raise ChoiceAdmissionContractError("Choice grading-spec version is invalid.")
    return ChoiceAdmissionScope(
        grading_spec_ref=GradingSpecRef(_id(_field(spec, "id"), limit), version),
        **{name: _id(_field(value, name), limit) for name in (
            "actor_ref", "tenant_ref", "session_ref", "grading_run_id",
            "submission_ref", "exam_ref", "question_id", "evidence_scope_ref",
            "source_artifact_ref", "source_revision", "admission_policy_identity",
            "policy_revision", "ocr_provenance",
        )},
    )


def _request_copy(value: object, limit: int) -> PreparationRequest:
    try:
        return _request_snapshot(value, limit)
    except PreparationSourceContractError:
        raise ChoiceAdmissionContractError("CHOICE request is malformed.") from None


def _pre_grant_copy(value: object, limit: int) -> ChoicePreEvidenceGrant:
    if type(value) is not ChoicePreEvidenceGrant:
        raise ChoiceAdmissionContractError("CHOICE pre-evidence authority returned an invalid grant.")
    return ChoicePreEvidenceGrant(
        request=_request_copy(_field(value, "request"), limit),
        source_artifact_ref=_id(_field(value, "source_artifact_ref"), limit),
        source_revision=_id(_field(value, "source_revision"), limit),
        key_revision=_id(_field(value, "key_revision"), limit),
        selection_revision=_id(_field(value, "selection_revision"), limit),
    )


def _grant_copy(value: object, limit: int) -> ChoiceAccessGrant:
    if type(value) is not ChoiceAccessGrant:
        raise ChoiceAdmissionContractError("Choice grant has invalid type.")
    return ChoiceAccessGrant(
        _scope_copy(_field(value, "scope"), limit),
        _id(_field(value, "key_revision"), limit),
        _id(_field(value, "selection_revision"), limit),
    )


def _key_copy(value: object, limit: int, max_options: int, max_criteria: int) -> ApprovedChoiceKeyRecord:
    if type(value) is not ApprovedChoiceKeyRecord:
        raise ChoiceAdmissionContractError("Approved choice key record has invalid type.")
    authority = _field(value, "authority")
    if type(authority) is not ChoiceEvaluationAuthority:
        raise ChoiceAdmissionContractError("Approved choice key authority has invalid type.")
    # Check finite option inventory before the accepted snapshot helper walks it.
    options = _field(authority, "option_ids")
    if type(options) is not tuple or not 1 <= len(options) <= max_options:
        raise ChoiceAdmissionContractError("Approved CHOICE options exceed configured limits.")
    for option in options:
        _id(option, limit)
    spec = _field(authority, "grading_spec_ref")
    if type(spec) is not GradingSpecRef:
        raise ChoiceAdmissionContractError("Approved CHOICE grading spec is malformed.")
    _id(_field(spec, "id"), limit)
    version = _field(spec, "version")
    if type(version) is not int or version <= 0:
        raise ChoiceAdmissionContractError("Approved CHOICE grading spec is malformed.")
    _id(_field(authority, "official_option_id"), limit)
    _id(_field(authority, "question_id"), limit)
    for field_name in ("match_projection", "mismatch_projection"):
        projection = _field(authority, field_name)
        if type(projection) is not tuple or not 1 <= len(projection) <= max_criteria:
            raise ChoiceAdmissionContractError("Approved CHOICE projection exceeds configured limits.")
        for item in projection:
            if type(item) is not ChoiceCriterionProjection:
                raise ChoiceAdmissionContractError("Approved CHOICE projection is malformed.")
            _id(_field(item, "criterion_id"), limit)
            _id(_field(item, "selected_level"), limit)
    try:
        # No arbitrary deepcopy or caller-provided constructor is invoked.
        from grading.integration.choice_binding import _snapshot_authority
        detached = _snapshot_authority(authority)
    except (ChoiceInputBindingError, InvalidChoiceEvaluationAuthorityError, ScoringError):
        raise ChoiceAdmissionContractError("Approved choice key authority is malformed.") from None
    return ApprovedChoiceKeyRecord(
        _scope_copy(_field(value, "scope"), limit),
        _id(_field(value, "key_revision"), limit),
        _id(_field(value, "approval_ref"), limit), detached,
    )


def _selection_copy(value: object, limit: int, max_refs: int) -> VerifiedChoiceSelectionRecord:
    if type(value) is not VerifiedChoiceSelectionRecord:
        raise ChoiceAdmissionContractError("Verified choice selection record has invalid type.")
    selection = _field(value, "selection")
    if type(selection) is not CanonicalChoiceSelection:
        raise ChoiceAdmissionContractError("Verified choice selection has invalid type.")
    references = _field(selection, "evidence_refs")
    if type(references) is not tuple or len(references) > max_refs:
        raise ChoiceAdmissionContractError("CHOICE evidence references exceed admitted limits.")
    for reference in references:
        _id(reference, limit)
    _id(_field(selection, "selected_option_id"), limit)
    _id(_field(selection, "submission_ref"), limit)
    _id(_field(selection, "question_id"), limit)
    try:
        from grading.integration.choice_binding import _snapshot_selection
        detached = _snapshot_selection(selection)
    except (ChoiceInputBindingError, InvalidCanonicalChoiceSelectionError):
        raise ChoiceAdmissionContractError("Verified choice selection is malformed.") from None
    return VerifiedChoiceSelectionRecord(
        _scope_copy(_field(value, "scope"), limit),
        _id(_field(value, "selection_revision"), limit),
        _id(_field(value, "selection_origin_ref"), limit), detached,
    )


def _confirmation_copy(value: object, limit: int) -> ChoiceRevisionConfirmation:
    if type(value) is not ChoiceRevisionConfirmation:
        raise ChoiceAdmissionContractError("Choice revision confirmation has invalid type.")
    return ChoiceRevisionConfirmation(
        _scope_copy(_field(value, "scope"), limit),
        _id(_field(value, "key_revision"), limit),
        _id(_field(value, "selection_revision"), limit),
        _id(_field(value, "source_revision"), limit),
    )


def _capture(port: object, name: str) -> Callable:
    """Capture and check the plain Python backend operation before any invocation."""
    try:
        declared = inspect.getattr_static(port, name)
        class_declared = inspect.getattr_static(type(port), name, None)
    except (AttributeError, TypeError):
        raise ChoiceAdmissionContractError("Required CHOICE backend port is missing.") from None
    if type(declared) is not FunctionType:
        raise ChoiceAdmissionContractError("Required CHOICE backend port must be a plain method.")
    if "__signature__" in declared.__dict__ or "__wrapped__" in declared.__dict__:
        raise ChoiceAdmissionContractError("CHOICE backend port signature metadata is unsupported.")
    # Do not evaluate user descriptors or use a potentially forged __signature__.
    is_class_method = declared is class_declared
    required_argument = "request" if name == "authorize_choice_request" else (
        "scope" if name == "authorize_choice" else "grant"
    )
    try:
        sig = inspect.signature(declared, follow_wrapped=False)
        args = ((object(),) if is_class_method else ())
        sig.bind(*args, **{required_argument: object()})
    except (TypeError, ValueError):
        raise ChoiceAdmissionContractError("CHOICE backend method has an invalid signature.") from None
    return declared.__get__(port, type(port)) if is_class_method else declared


def _call(callback: Callable, *, operation: str, **kwargs: object) -> object:
    denied = False
    failed = False
    output = None
    try:
        output = callback(**kwargs)
    except ChoiceAdmissionDenied:
        denied = True
    except Exception:
        failed = True
    if denied:
        raise ChoiceAdmissionDenied("Choice source access was denied.") from None
    if failed:
        raise ChoiceAdmissionUnavailable("Choice authority backend is unavailable.") from None
    return output



def _call_then_verify_source(
    callback: Callable, *, operation: str, verify_source: Callable[[], None],
    **kwargs: object,
) -> object:
    """Prioritize corruption of an already-admitted source over callback outcomes.

    A callback can mutate caller-owned records before returning *or* raising.
    Check those records before interpreting either the returned authority record
    or an operational failure. With an unchanged source, keep _call's existing
    explicit-denial/unavailable classification.
    """
    try:
        returned = _call(callback, operation=operation, **kwargs)
    except (ChoiceAdmissionDenied, ChoiceAdmissionUnavailable):
        verify_source()
        raise
    verify_source()
    return returned

def _custody_copy(value: object, limit: int) -> PreparationCustody:
    if type(value) is not PreparationCustody:
        raise ChoiceAdmissionContractError("Authorized PRE custody is malformed.")
    return PreparationCustody(**{
        field.name: _id(_field(value, field.name), limit)
        for field in fields(PreparationCustody)
    })


def _scope_from_prepared(value: object, limit: int) -> tuple[
    ChoiceAdmissionScope, BoundQuestionEvaluationInputs, PreparationRequest, PreparationCustody,
]:
    """Detach and validate the *entire* PRE graph before foreign CHOICE callbacks.

    Frozen Python records may be forcibly mutated. The accepted CHOICE snapshot
    rebuilds all question evidence binding roots through owning constructors, with normalized OCR evidence admission collection limits
    preflighted before it iterates records or compares their identifiers.
    """
    if type(value) is not AuthorizedPreparedQuestion:
        raise ChoiceAdmissionContractError("Exact authorized prepared input is required.")
    source = _field(value, "prepared")
    if type(source) is not PreparedWithSourceCustody:
        raise ChoiceAdmissionContractError("Authorized PRE source is malformed.")
    request = _request_copy(_field(source, "request"), limit)
    custody = _custody_copy(_field(value, "custody"), limit)
    original_bound = _field(source, "bound")
    if type(original_bound) is not BoundQuestionEvaluationInputs:
        raise ChoiceAdmissionContractError("Authorized PRE bound input is malformed.")
    try:
        bound = _snapshot_prepared(original_bound)
    except ChoiceInputBindingError:
        raise ChoiceAdmissionContractError("Authorized PRE question graph is malformed.") from None
    context = bound.context
    question = bound.question_authority
    admitted = bound.admitted_evidence
    evidence = admitted.evidence
    matches = tuple(q for q in evidence.questions if q.question_id == request.question_id)
    if len(matches) != 1:
        raise ChoiceAdmissionDenied("Choice evidence scope is missing or ambiguous.")
    scope = ChoiceAdmissionScope(
        actor_ref=custody.actor_ref,
        tenant_ref=custody.tenant_ref,
        session_ref=custody.session_ref,
        grading_run_id=request.grading_run_id,
        submission_ref=request.submission_ref,
        exam_ref=request.exam_ref,
        grading_spec_ref=request.grading_spec_ref,
        question_id=request.question_id,
        evidence_scope_ref=_id(matches[0].answer_scope_ref, limit),
        source_artifact_ref=custody.source_artifact_ref,
        source_revision=custody.source_revision,
        admission_policy_identity=custody.admission_policy_identity,
        policy_revision=custody.policy_revision,
        ocr_provenance=_id(evidence.ocr_provenance, limit),
    )
    scope = _scope_copy(scope, limit)
    if (
        scope.tenant_ref != request.tenant_ref
        or scope.session_ref != request.session_ref
        or scope.grading_run_id != context.grading_run_id
        or scope.submission_ref != context.submission_ref
        or scope.submission_ref != evidence.submission_ref
        or scope.exam_ref != context.exam_ref
        or scope.question_id != question.question_id
        or scope.grading_spec_ref != context.grading_spec_ref
        or scope.grading_spec_ref != question.grading_spec_ref
        or scope.source_artifact_ref != admitted.source_artifact_ref
        or scope.admission_policy_identity != admitted.effective_policy_snapshot.admission_policy_identity
    ):
        raise ChoiceAdmissionDenied("Authorized PRE source and CHOICE scope do not agree.")
    return scope, bound, request, custody


def _pinned_roots(bound: BoundQuestionEvaluationInputs) -> tuple[object, ...]:
    return (bound.context, bound.admitted_evidence.evidence,
            bound.admitted_evidence.wire_schema_version,
            bound.admitted_evidence.raw_payload_sha256,
            bound.admitted_evidence.admission_policy_identity,
            bound.admitted_evidence.effective_policy_snapshot,
            bound.admitted_evidence.source_artifact_ref,
            bound.paper_authority, bound.question_authority)


def _verify_original_unchanged(
    original: AuthorizedPreparedQuestion, scope: ChoiceAdmissionScope,
    request: PreparationRequest, custody: PreparationCustody,
    pinned: BoundQuestionEvaluationInputs, limit: int,
) -> None:
    """Reject callback-time changes before allowing the next backend operation."""
    # Reject policy inflation *before* trusting its altered resource ceilings.
    # Checking exact primitive fields prevents invoking foreign comparison methods.
    source = _field(original, "prepared")
    if type(source) is not PreparedWithSourceCustody:
        raise ChoiceAdmissionDenied("CHOICE source changed during admission.")
    current_bound_ref = _field(source, "bound")
    if type(current_bound_ref) is not BoundQuestionEvaluationInputs:
        raise ChoiceAdmissionDenied("CHOICE source changed during admission.")
    admitted_ref = _field(current_bound_ref, "admitted_evidence")
    if type(admitted_ref) is not AdmittedNormalizedEvidence:
        raise ChoiceAdmissionDenied("CHOICE source changed during admission.")
    policy_ref = _field(admitted_ref, "effective_policy_snapshot")
    approved = pinned.admitted_evidence.effective_policy_snapshot
    if type(policy_ref) is not NormalizedEvidenceAdmissionPolicy:
        raise ChoiceAdmissionDenied("CHOICE admission policy changed during admission.")
    for field in fields(NormalizedEvidenceAdmissionPolicy):
        current = _field(policy_ref, field.name)
        expected = getattr(approved, field.name)
        if type(current) is not type(expected) or current != expected:
            raise ChoiceAdmissionDenied("CHOICE admission policy changed during admission.")
    evidence_ref = _field(admitted_ref, "evidence")
    from grading.contracts.evidence import AnswerEvidenceBundle
    if type(evidence_ref) is not AnswerEvidenceBundle:
        raise ChoiceAdmissionDenied("CHOICE evidence changed during admission.")
    questions = _field(evidence_ref, "questions")
    if type(questions) is not tuple or len(questions) > approved.max_questions:
        raise ChoiceAdmissionDenied("CHOICE evidence exceeds original admitted limits.")
    try:
        current_scope, current_bound, current_request, current_custody = _scope_from_prepared(original, limit)
    except ChoiceAdmissionContractError:
        raise ChoiceAdmissionDenied("CHOICE source changed during admission.") from None
    if (current_scope != scope or current_request != request
            or current_custody != custody or _pinned_roots(current_bound) != _pinned_roots(pinned)):
        raise ChoiceAdmissionDenied("CHOICE source changed during admission.")


def _verify_selected_evidence(bound: BoundChoiceEvaluationInputs) -> None:
    """Bind cited IDs to this question; deterministic scoring still owns judgment verification."""
    question_id = bound.selection.question_id
    owners = {}
    for question in bound.prepared.admitted_evidence.evidence.questions:
        for block in question.blocks:
            if block.block_id in owners:
                raise ChoiceAdmissionDenied("Choice evidence block ownership is ambiguous.")
            owners[block.block_id] = (question.question_id, block.state)
    for reference in bound.selection.evidence_refs:
        owner = owners.get(reference)
        if owner is None or owner[0] != question_id or owner[1] is EvidenceBlockState.CROSSED_OUT:
            raise ChoiceAdmissionDenied("Canonical CHOICE selection lacks admitted supporting evidence.")




class ProductionChoiceAdmissionComposer:
    """Only the trusted root installs grant, approved-key, selection, and revision ports."""

    def __init__(self, *, pre_evidence: ChoicePreEvidenceAuthority,
                 access: ChoiceAccessAuthority, approved_keys: OfficialChoiceKeyAuthority,
                 selections: CanonicalSelectionAuthority, revisions: ChoiceRevisionAuthority,
                 max_identifier_characters: int, max_choice_options: int,
                 max_choice_criteria: int) -> None:
        try:
            if (type(max_identifier_characters) is not int or max_identifier_characters <= 0
                    or type(max_choice_options) is not int or max_choice_options <= 0
                    or type(max_choice_criteria) is not int or max_choice_criteria <= 0):
                raise ChoiceAdmissionContractError("Trusted CHOICE resource ceilings are required.")
            operations = {
                name: _capture(port, name) for port, name in (
                    (pre_evidence, "authorize_choice_request"),
                    (access, "authorize_choice"),
                    (approved_keys, "resolve_approved_choice_key"),
                    (selections, "resolve_verified_choice_selection"),
                    (revisions, "confirm_choice_revisions"),
                )
            }
        except ChoiceAdmissionContractError as caught:
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None
        self._limit = max_identifier_characters
        self._max_options = max_choice_options
        self._max_criteria = max_choice_criteria
        self._operations = operations

    def preauthorize(self, *, request: PreparationRequest) -> ChoicePreEvidenceGrant:
        """Backend checks independently knowable key/source access *before* PRE IO.

        The resulting metadata is checked against PRE and the full CHOICE grant.
        It is not a bearer credential and cannot replace full CHOICE admission.
        """
        try:
            # Never expose the comparison baseline to an installed backend port.
            pinned_request = _request_copy(request, self._limit)
            callback_request = _request_copy(pinned_request, self._limit)
            def check_request_drift() -> None:
                try:
                    # The callback receives a separate copy, not the pinned baseline.
                    # Check both it and the original even if the callback raises.
                    if (_request_copy(callback_request, self._limit) != pinned_request
                            or _request_copy(request, self._limit) != pinned_request):
                        raise ChoiceAdmissionDenied("Pre-evidence CHOICE request changed.")
                except ChoiceAdmissionContractError:
                    raise ChoiceAdmissionDenied("Pre-evidence CHOICE request changed.") from None

            returned = _call_then_verify_source(
                self._operations["authorize_choice_request"],
                operation="authorize_choice_request", verify_source=check_request_drift,
                request=callback_request,
            )
            grant = _pre_grant_copy(returned, self._limit)
            if grant.request != pinned_request:
                raise ChoiceAdmissionDenied("Pre-evidence CHOICE authorization scope differs.")
            return ChoicePreEvidenceGrant(
                request=pinned_request, source_artifact_ref=grant.source_artifact_ref,
                source_revision=grant.source_revision, key_revision=grant.key_revision,
                selection_revision=grant.selection_revision,
            )
        except (ChoiceAdmissionDenied, ChoiceAdmissionUnavailable, ChoiceAdmissionContractError) as caught:
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None

    def admit(self, *, prepared: AuthorizedPreparedQuestion,
              pre_evidence_grant: ChoicePreEvidenceGrant | None = None) -> AdmittedChoice:
        try:
            return self._admit_impl(prepared=prepared, pre_evidence_grant=pre_evidence_grant)
        except (
            ChoiceAdmissionDenied, ChoiceAdmissionUnavailable,
            ChoiceAdmissionContractError, ChoiceInputBindingError,
        ) as caught:
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None

    def _admit_impl(self, *, prepared: AuthorizedPreparedQuestion,
                    pre_evidence_grant: ChoicePreEvidenceGrant | None) -> AdmittedChoice:
        limit = self._limit
        scope, bound, request, custody = _scope_from_prepared(prepared, limit)
        pre = None
        if pre_evidence_grant is not None:
            pre = _pre_grant_copy(pre_evidence_grant, limit)
            if (pre.request != request or pre.source_artifact_ref != scope.source_artifact_ref
                    or pre.source_revision != scope.source_revision):
                raise ChoiceAdmissionDenied("Pre-evidence CHOICE grant disagrees with authorized PRE.")
        def check_drift() -> None:
            try:
                _verify_original_unchanged(prepared, scope, request, custody, bound, limit)
            except ChoiceAdmissionContractError:
                # Once validated, a callback's structural corruption is a denial,
                # not an initially malformed caller/configuration record.
                raise ChoiceAdmissionDenied("CHOICE source changed during admission.") from None
        def verify_callback_scope(actual: ChoiceAdmissionScope) -> None:
            # Original PRE corruption must take priority over callback-input drift.
            check_drift()
            try:
                if _scope_copy(actual, limit) != scope:
                    raise ChoiceAdmissionDenied("CHOICE callback argument changed during admission.")
            except ChoiceAdmissionContractError:
                raise ChoiceAdmissionDenied("CHOICE callback argument changed during admission.") from None

        callback_scope = _scope_copy(scope, limit)
        grant_reply = _call_then_verify_source(
            self._operations["authorize_choice"], operation="authorize_choice",
            verify_source=lambda: verify_callback_scope(callback_scope), scope=callback_scope,
        )
        grant = _grant_copy(grant_reply, limit)
        if grant.scope != scope or (pre is not None and (
            grant.key_revision != pre.key_revision
            or grant.selection_revision != pre.selection_revision
        )):
            raise ChoiceAdmissionDenied("CHOICE source access grant does not match PRE scope.")
        def verify_callback_grant(actual: ChoiceAccessGrant) -> None:
            check_drift()
            try:
                if _grant_copy(actual, limit) != grant:
                    raise ChoiceAdmissionDenied("CHOICE callback argument changed during admission.")
            except ChoiceAdmissionContractError:
                raise ChoiceAdmissionDenied("CHOICE callback argument changed during admission.") from None

        callback_key_grant = _grant_copy(grant, limit)
        key_reply = _call_then_verify_source(
            self._operations["resolve_approved_choice_key"],
            operation="resolve_approved_choice_key",
            verify_source=lambda: verify_callback_grant(callback_key_grant),
            grant=callback_key_grant,
        )
        key = _key_copy(key_reply, limit, self._max_options, self._max_criteria)
        if key.scope != scope or key.key_revision != grant.key_revision:
            raise ChoiceAdmissionDenied("Official CHOICE key does not match authorized revision.")
        callback_selection_grant = _grant_copy(grant, limit)
        selection_reply = _call_then_verify_source(
            self._operations["resolve_verified_choice_selection"],
            operation="resolve_verified_choice_selection",
            verify_source=lambda: verify_callback_grant(callback_selection_grant),
            grant=callback_selection_grant,
        )
        selection = _selection_copy(
            selection_reply, limit,
            bound.admitted_evidence.effective_policy_snapshot.max_total_blocks,
        )
        if selection.scope != scope or selection.selection_revision != grant.selection_revision:
            raise ChoiceAdmissionDenied("CHOICE selection does not match authorized origin revision.")
        if selection.selection.selected_option_id not in key.authority.option_ids:
            raise ChoiceAdmissionDenied("Canonical CHOICE selection is outside approved option universe.")
        try:
            choice = bind_choice_evaluation_inputs(
                prepared=bound, choice_authority=key.authority, selection=selection.selection,
            )
        except ChoiceInputBindingError:
            raise ChoiceAdmissionDenied("Approved CHOICE values do not bind to prepared question.") from None
        _verify_selected_evidence(choice)
        callback_confirmation_grant = _grant_copy(grant, limit)
        confirmation_reply = _call_then_verify_source(
            self._operations["confirm_choice_revisions"],
            operation="confirm_choice_revisions",
            verify_source=lambda: verify_callback_grant(callback_confirmation_grant),
            grant=callback_confirmation_grant,
        )
        check = _confirmation_copy(confirmation_reply, limit)
        if (check.scope != scope or check.key_revision != grant.key_revision
                or check.selection_revision != grant.selection_revision
                or check.source_revision != scope.source_revision):
            raise ChoiceAdmissionDenied("CHOICE source revision changed during admission.")
        return AdmittedChoice(
            bound=choice, scope=scope, key_revision=grant.key_revision,
            selection_revision=grant.selection_revision,
            approval_ref=key.approval_ref,
            selection_origin_ref=selection.selection_origin_ref,
        )
