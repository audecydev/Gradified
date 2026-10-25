"""paper readiness/rubric generation/teacher review/result governance: installed paper authority and answer-readiness admission.

The configured application root must supply authenticated identity, actual school
paper approval, source/answer readiness and revision confirmation. This module
checks finite correlations; matching records/IDs do NOT authenticate a source.
No evaluator, provider, scoring, publication, or evidence IO occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from weakref import WeakKeyDictionary, ref

from grading.contracts.paper_aggregation import GradingSpecRef
from grading.integration.authorized_preparation import (
    AuthenticatedActor, IdentityAuthority, _validated_port_method,
)
from grading.integration.trusted_preparation import PreparationRequest


class PaperAdmissionDenied(ValueError):
    """Authoritative scopes, selections, or revisions do not correspond."""


class PaperAdmissionUnavailable(Exception):
    """An installed authority could not supply a required fact."""


class PaperAdmissionContractError(ValueError):
    """An installed authority or caller supplied structurally invalid facts."""


class PaperAnswerNotReady(Exception):
    """Selected answers are not all proved READY. Never infer a student mark."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__("Selected answer readiness is not established.")


@dataclass(frozen=True, slots=True, repr=False)
class PaperAdmissionRequest:
    tenant_ref: str
    session_ref: str
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    paper_ref: str
    set_ref: str
    grading_spec_ref: GradingSpecRef


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedPaperQuestion:
    question_id: str
    family: str  # Family is a declared paper fact, not approved execution.
    source_artifact_ref: str  # Installed source authority pins the allowed source.
    evidence_scope_ref: str  # Installed authority pins the permitted question scope.


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedPaperSelection:
    request: PaperAdmissionRequest
    actor_ref: str
    approval_ref: str
    approval_revision: str
    selection_decision_ref: str
    selection_revision: str
    source_revision: str
    approved_question_ids: tuple[str, ...]
    required_question_ids: tuple[str, ...]
    selected_questions: tuple[AuthorizedPaperQuestion, ...]


@dataclass(frozen=True, slots=True, repr=False)
class QuestionAnswerReadiness:
    question_id: str
    status: str  # READY, UNKNOWN, UNREADABLE, UNMAPPED, ABSENT_CONFIRMED
    source_artifact_ref: str | None
    source_revision: str
    evidence_scope_ref: str | None
    answer_region_ref: str | None
    provenance_ref: str | None


@dataclass(frozen=True, slots=True, repr=False)
class PaperReadinessRecord:
    request: PaperAdmissionRequest
    approval_ref: str
    approval_revision: str
    selection_revision: str
    source_revision: str
    readiness_revision: str
    answers: tuple[QuestionAnswerReadiness, ...]


@dataclass(frozen=True, slots=True, repr=False)
class PaperRevisionConfirmation:
    request: PaperAdmissionRequest
    approval_ref: str
    approval_revision: str
    selection_revision: str
    source_revision: str
    readiness_revision: str
    state: str  # CURRENT only


@dataclass(frozen=True, slots=True, repr=False)
class AdmittedPaperQuestion:
    request: PreparationRequest
    family: str
    source_artifact_ref: str
    source_revision: str
    evidence_scope_ref: str
    answer_region_ref: str
    provenance_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class AdmittedPaperPlan:
    """Detached, nonpublishing paper plan. Not a credential to invoke grading."""
    request: PaperAdmissionRequest
    actor_ref: str
    approval_ref: str
    approval_revision: str
    selection_decision_ref: str
    selection_revision: str
    source_revision: str
    readiness_revision: str
    questions: tuple[AdmittedPaperQuestion, ...]


class PaperSelectionAuthority(Protocol):
    def authorize_paper(self, *, actor: AuthenticatedActor,
                        request: PaperAdmissionRequest) -> ApprovedPaperSelection: ...


class PaperAnswerAuthority(Protocol):
    def resolve_paper_readiness(self, *, approval: ApprovedPaperSelection) -> PaperReadinessRecord: ...


class PaperRevisionAuthority(Protocol):
    def confirm_paper_revision(self, *, approval: ApprovedPaperSelection,
                               readiness: PaperReadinessRecord) -> PaperRevisionConfirmation: ...


_STATUSES = frozenset(("READY", "UNKNOWN", "UNREADABLE", "UNMAPPED", "ABSENT_CONFIRMED"))
_FAMILIES = frozenset(("CHOICE", "DIRECT", "NUMERIC"))


def _field(obj: object, name: str) -> object:
    try:
        return object.__getattribute__(obj, name)
    except AttributeError:
        raise PaperAdmissionContractError("An authority record is incomplete.") from None


def _id(value: object, limit: int) -> str:
    if type(value) is not str or not value or len(value) > limit or value.strip() != value:
        raise PaperAdmissionContractError("An authority identifier is malformed.")
    return value


def _optional_id(value: object, limit: int) -> str | None:
    return None if value is None else _id(value, limit)


def _spec(value: object, limit: int) -> GradingSpecRef:
    if type(value) is not GradingSpecRef:
        raise PaperAdmissionContractError("The grading spec reference has an invalid type.")
    version = _field(value, "version")
    if type(version) is not int or version <= 0:
        raise PaperAdmissionContractError("The grading spec revision is invalid.")
    return GradingSpecRef(id=_id(_field(value, "id"), limit), version=version)


def _request(value: object, limit: int) -> PaperAdmissionRequest:
    if type(value) is not PaperAdmissionRequest:
        raise PaperAdmissionContractError("A paper request has an invalid type.")
    return PaperAdmissionRequest(
        grading_spec_ref=_spec(_field(value, "grading_spec_ref"), limit),
        **{key: _id(_field(value, key), limit) for key in (
            "tenant_ref", "session_ref", "grading_run_id", "submission_ref",
            "exam_ref", "paper_ref", "set_ref",
        )},
    )


def _actor(value: object, limit: int) -> AuthenticatedActor:
    if type(value) is not AuthenticatedActor:
        raise PaperAdmissionContractError("Installed identity authority returned an invalid actor.")
    return AuthenticatedActor(*(_id(_field(value, key), limit) for key in (
        "actor_ref", "tenant_ref", "session_ref",
    )))


def _ids(value: object, limit: int, max_questions: int, allow_empty: bool) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) > max_questions or (not allow_empty and not value):
        raise PaperAdmissionContractError("Approved paper question inventory is invalid.")
    result = tuple(_id(x, limit) for x in value)
    if len(set(result)) != len(result):
        raise PaperAdmissionContractError("Approved paper contains duplicate questions.")
    return result


def _approval(value: object, limit: int, max_questions: int) -> ApprovedPaperSelection:
    if type(value) is not ApprovedPaperSelection:
        raise PaperAdmissionContractError("Installed paper authority returned an invalid selection.")
    approved = _ids(_field(value, "approved_question_ids"), limit, max_questions, False)
    required = _ids(_field(value, "required_question_ids"), limit, max_questions, True)
    source = _field(value, "selected_questions")
    if type(source) is not tuple or not source or len(source) > max_questions:
        raise PaperAdmissionContractError("The selected question inventory is invalid.")
    selected = []
    for entry in source:
        if type(entry) is not AuthorizedPaperQuestion:
            raise PaperAdmissionContractError("An approved question is malformed.")
        family = _id(_field(entry, "family"), limit)
        if family not in _FAMILIES:
            raise PaperAdmissionContractError("The declared question family is unsupported by this admission contract.")
        selected.append(AuthorizedPaperQuestion(
            question_id=_id(_field(entry, "question_id"), limit), family=family,
            source_artifact_ref=_id(_field(entry, "source_artifact_ref"), limit),
            evidence_scope_ref=_id(_field(entry, "evidence_scope_ref"), limit),
        ))
    selected_ids = tuple(item.question_id for item in selected)
    if len(set(item.evidence_scope_ref for item in selected)) != len(selected):
        raise PaperAdmissionDenied("Approved question evidence scopes overlap.")
    if (len(set(selected_ids)) != len(selected_ids)
            or not set(selected_ids).issubset(approved)
            or not set(required).issubset(selected_ids)
            or not set(required).issubset(approved)):
        raise PaperAdmissionDenied("The paper selection is not approved or complete.")
    return ApprovedPaperSelection(
        request=_request(_field(value, "request"), limit),
        actor_ref=_id(_field(value, "actor_ref"), limit),
        approval_ref=_id(_field(value, "approval_ref"), limit),
        approval_revision=_id(_field(value, "approval_revision"), limit),
        selection_decision_ref=_id(_field(value, "selection_decision_ref"), limit),
        selection_revision=_id(_field(value, "selection_revision"), limit),
        source_revision=_id(_field(value, "source_revision"), limit),
        approved_question_ids=approved, required_question_ids=required,
        selected_questions=tuple(selected),
    )


def _readiness(value: object, limit: int, max_questions: int) -> PaperReadinessRecord:
    if type(value) is not PaperReadinessRecord:
        raise PaperAdmissionContractError("Installed readiness authority returned an invalid record.")
    entries = _field(value, "answers")
    if type(entries) is not tuple or not entries or len(entries) > max_questions:
        raise PaperAdmissionContractError("The answer inventory is invalid.")
    answer_copies = []
    for entry in entries:
        if type(entry) is not QuestionAnswerReadiness:
            raise PaperAdmissionContractError("A question answer mapping is invalid.")
        status = _field(entry, "status")
        if type(status) is not str or status not in _STATUSES:
            raise PaperAdmissionContractError("An answer readiness status is invalid.")
        answer_copies.append(QuestionAnswerReadiness(
            question_id=_id(_field(entry, "question_id"), limit), status=status,
            source_revision=_id(_field(entry, "source_revision"), limit),
            **{key: _optional_id(_field(entry, key), limit) for key in (
                "source_artifact_ref", "evidence_scope_ref", "answer_region_ref", "provenance_ref",
            )},
        ))
    return PaperReadinessRecord(
        request=_request(_field(value, "request"), limit),
        **{key: _id(_field(value, key), limit) for key in (
            "approval_ref", "approval_revision", "selection_revision",
            "source_revision", "readiness_revision",
        )}, answers=tuple(answer_copies),
    )


def _confirmation(value: object, limit: int) -> PaperRevisionConfirmation:
    if type(value) is not PaperRevisionConfirmation:
        raise PaperAdmissionContractError("Paper revision confirmation has an invalid type.")
    state = _field(value, "state")
    if type(state) is not str or state not in ("CURRENT", "REVOKED", "STALE"):
        raise PaperAdmissionContractError("Paper revision state is invalid.")
    return PaperRevisionConfirmation(
        request=_request(_field(value, "request"), limit), state=state,
        **{key: _id(_field(value, key), limit) for key in (
            "approval_ref", "approval_revision", "selection_revision",
            "source_revision", "readiness_revision",
        )},
    )


def _invoke(callback: object, *, may_deny: bool = False, **kwargs: object) -> object:
    failure = False
    denied = False
    result = None
    try:
        result = callback(**kwargs)
    except PaperAdmissionDenied:
        denied = may_deny
        failure = not denied
    except Exception:
        failure = True
    if denied:
        raise PaperAdmissionDenied("Installed authority denied this paper request.") from None
    if failure:
        raise PaperAdmissionUnavailable("Required paper authority is unavailable.") from None
    return result


def _installation_custody():
    # Installation lineage must not be reset by changing fields on its owner.
    # Weak callable references avoid retaining adapters (which may refer back
    # to the owner) beyond the lifetime of the owner itself.
    originals = WeakKeyDictionary()

    def pin(owner: object, installed: tuple) -> None:
        if owner in originals:
            raise PaperAdmissionContractError('Paper installation is already pinned.')
        originals[owner] = (tuple(ref(method) for method in installed[:4]), installed[4:])

    def matches(owner: object, installed: tuple) -> bool:
        recorded = originals.get(owner)
        return (recorded is not None
                and all(original() is installed[index]
                        for index, original in enumerate(recorded[0]))
                and recorded[1] == installed[4:])

    return pin, matches


_pin_installation, _same_installation = _installation_custody()


class ProductionPaperAdmissionComposer:
    """Paper-only admission. Caller must later recheck actual PRE/attempt authority.

    The application's installed adapters must genuinely authenticate the actor,
    validate the school-approved selection, and confirm source/revision currency.
    A Python-matching approval record is not evidence of an external signature.
    """

    __slots__ = ('_identity', '_selection', '_answers', '_revisions',
                 '_limit', '_max_questions', '_installed', '__weakref__')

    def __init__(self, *, identity: IdentityAuthority,
                 selections: PaperSelectionAuthority, answers: PaperAnswerAuthority,
                 revisions: PaperRevisionAuthority, max_identifier_characters: int,
                 max_questions: int) -> None:
        try:
            if (type(max_identifier_characters) is not int or max_identifier_characters <= 0
                    or type(max_questions) is not int or max_questions <= 0):
                raise PaperAdmissionContractError("Trusted paper admission resource limits are required.")
            identity_op = _validated_port_method(identity, "current_actor")
            selection_op = _validated_port_method(selections, "authorize_paper")
            answers_op = _validated_port_method(answers, "resolve_paper_readiness")
            revision_op = _validated_port_method(revisions, "confirm_paper_revision")
        except Exception:
            raise PaperAdmissionContractError("Required installed paper authorities are invalid.") from None
        installed = (identity_op, selection_op, answers_op, revision_op,
                     max_identifier_characters, max_questions)
        for name, value in zip(('_identity', '_selection', '_answers', '_revisions',
                                '_limit', '_max_questions'), installed):
            object.__setattr__(self, name, value)
        object.__setattr__(self, '_installed', installed)
        _pin_installation(self, installed)

    def __setattr__(self, name, value):
        raise AttributeError('Paper-admission source installation is immutable.')

    def __delattr__(self, name):
        raise AttributeError('Paper-admission source installation is immutable.')

    def _operations(self):
        # Recheck the one-time installation lineage across paper operations.
        # No callback can reset it through fields on this owner. These local
        # checks are defense in depth, not an in-process Python sandbox.
        try:
            installed = object.__getattribute__(self, '_installed')
            if (type(installed) is not tuple or len(installed) != 6
                    or any(object.__getattribute__(self, name) is not installed[i]
                           for i, name in enumerate(('_identity', '_selection', '_answers', '_revisions')))
                    or type(object.__getattribute__(self, '_limit')) is not int
                    or type(object.__getattribute__(self, '_max_questions')) is not int
                    or object.__getattribute__(self, '_limit') != installed[4]
                    or object.__getattribute__(self, '_max_questions') != installed[5]
                    or not _same_installation(self, installed)):
                raise PaperAdmissionUnavailable('Installed paper authorities changed.')
        except AttributeError:
            # A nonconforming callback may remove a slot through reflection.
            # Admission must fail with its documented unavailable condition,
            # never escape as a host-unclassified AttributeError.
            raise PaperAdmissionUnavailable('Installed paper authorities changed.') from None
        return installed[:4]

    def admit(self, *, request: PaperAdmissionRequest) -> AdmittedPaperPlan:
        try:
            return self._admit(request)
        except (PaperAdmissionDenied, PaperAdmissionUnavailable,
                PaperAdmissionContractError, PaperAnswerNotReady) as caught:
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None

    def _admit(self, original_request: object) -> AdmittedPaperPlan:
        # The entire paper is admitted before the next whole-paper checkpoint can act.
        methods = self._operations()
        limit, maximum = self._limit, self._max_questions
        request = _request(original_request, limit)
        original_actor = _invoke(methods[0])
        self._operations()
        actor = _actor(original_actor, limit)
        if (actor.tenant_ref != request.tenant_ref or actor.session_ref != request.session_ref):
            raise PaperAdmissionDenied("The authenticated actor does not own this paper scope.")
        # Identity callbacks may mutate caller-owned request records. Reject drift
        # before contacting school selection, not merely before readiness.
        if _request(original_request, limit) != request:
            raise PaperAdmissionDenied("Original paper request changed during identity admission.")
        actor_argument = _actor(actor, limit)
        request_argument = _request(request, limit)
        original_approval = _invoke(
            methods[1], may_deny=True, actor=actor_argument, request=request_argument,
        )
        self._operations()
        approved = _approval(original_approval, limit, maximum)
        if approved.request != request or approved.actor_ref != actor.actor_ref:
            raise PaperAdmissionDenied("School paper approval does not match authenticated scope.")
        if (_request(original_request, limit) != request
                or _request(request_argument, limit) != request
                or _actor(original_actor, limit) != actor
                or _actor(actor_argument, limit) != actor):
            raise PaperAdmissionDenied("Original identity or paper request changed during approval.")

        approval_argument = _approval(approved, limit, maximum)
        original_readiness = _invoke(methods[2], approval=approval_argument)
        self._operations()
        readiness = _readiness(original_readiness, limit, maximum)
        if (_request(original_request, limit) != request
                or _actor(original_actor, limit) != actor
                or _approval(approval_argument, limit, maximum) != approved
                or _approval(original_approval, limit, maximum) != approved):
            raise PaperAdmissionDenied("Paper approval or original request changed during readiness.")
        if (readiness.request != request or readiness.approval_ref != approved.approval_ref
                or readiness.approval_revision != approved.approval_revision
                or readiness.selection_revision != approved.selection_revision
                or readiness.source_revision != approved.source_revision):
            raise PaperAdmissionDenied("Paper readiness does not match its approval.")
        selected = tuple(x.question_id for x in approved.selected_questions)
        approved_by_question = {x.question_id: x for x in approved.selected_questions}
        answers = readiness.answers
        if len(answers) != len(selected) or set(x.question_id for x in answers) != set(selected):
            raise PaperAdmissionDenied("Every selected question must have one exact answer mapping.")
        if len(set(x.question_id for x in answers)) != len(answers):
            raise PaperAdmissionDenied("Answer mapping contains duplicate question identities.")
        for answer in answers:
            if answer.source_revision != approved.source_revision:
                raise PaperAdmissionDenied("Answer evidence has a foreign source revision.")
            if answer.status != "READY":
                raise PaperAnswerNotReady(answer.status)
            if any(value is None for value in (answer.source_artifact_ref,
                    answer.evidence_scope_ref, answer.answer_region_ref, answer.provenance_ref)):
                raise PaperAdmissionContractError("A READY answer lacks evidence provenance.")
            authorized = approved_by_question[answer.question_id]
            if (answer.source_artifact_ref != authorized.source_artifact_ref
                    or answer.evidence_scope_ref != authorized.evidence_scope_ref):
                raise PaperAdmissionDenied("Answer evidence is outside its approved question scope.")
        if (len(set(x.evidence_scope_ref for x in answers)) != len(answers)
                or len(set((x.source_artifact_ref, x.answer_region_ref) for x in answers)) != len(answers)):
            raise PaperAdmissionDenied("Answer mapping duplicates evidence regions or identities.")

        confirmation_approval_argument = _approval(approved, limit, maximum)
        confirmation_readiness_argument = _readiness(readiness, limit, maximum)
        original_confirmation = _invoke(
            methods[3], approval=confirmation_approval_argument,
            readiness=confirmation_readiness_argument,
        )
        self._operations()
        confirmation = _confirmation(original_confirmation, limit)
        if (_request(original_request, limit) != request
                or _actor(original_actor, limit) != actor
                or _approval(original_approval, limit, maximum) != approved
                or _approval(confirmation_approval_argument, limit, maximum) != approved
                or _readiness(confirmation_readiness_argument, limit, maximum) != readiness
                or _readiness(original_readiness, limit, maximum) != readiness):
            raise PaperAdmissionDenied("The paper authority source changed during confirmation.")
        if (confirmation.request != request or confirmation.state != "CURRENT"
                or any(getattr(confirmation, field) != getattr(readiness, field) for field in (
                    "approval_ref", "approval_revision", "selection_revision",
                    "source_revision", "readiness_revision",
                ))):
            raise PaperAdmissionDenied("The paper source was revoked, stale, or changed.")

        by_question = {answer.question_id: answer for answer in answers}
        questions = tuple(AdmittedPaperQuestion(
            request=PreparationRequest(
                tenant_ref=request.tenant_ref, session_ref=request.session_ref,
                grading_run_id=request.grading_run_id, submission_ref=request.submission_ref,
                exam_ref=request.exam_ref, grading_spec_ref=_spec(request.grading_spec_ref, limit),
                question_id=selection.question_id,
            ),
            family=selection.family, source_artifact_ref=by_question[selection.question_id].source_artifact_ref,
            source_revision=by_question[selection.question_id].source_revision,
            evidence_scope_ref=by_question[selection.question_id].evidence_scope_ref,
            answer_region_ref=by_question[selection.question_id].answer_region_ref,
            provenance_ref=by_question[selection.question_id].provenance_ref,
        ) for selection in approved.selected_questions)
        self._operations()
        return AdmittedPaperPlan(
            request=_request(request, limit), actor_ref=actor.actor_ref,
            approval_ref=approved.approval_ref, approval_revision=approved.approval_revision,
            selection_decision_ref=approved.selection_decision_ref,
            selection_revision=approved.selection_revision,
            source_revision=approved.source_revision,
            readiness_revision=readiness.readiness_revision, questions=questions,
        )
