"""Bind each question execution to the original paper and installed issuer.

A structural correlation is not a credential. Only a qualified installed issuer can
establish the facts, and criterion scoring MUST reauthorize immediately before every attempt.
No PRE/evidence IO, physical attempt reservation, evaluator or scoring contact occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grading.integration.paper_readiness_admission import (
    PaperAdmissionRequest, AdmittedPaperPlan, AdmittedPaperQuestion, PaperAdmissionContractError,
    _request, _id,
)
from grading.integration.trusted_preparation import _request_snapshot


class PaperExecutionDenied(ValueError):
    """Issuer's execution relationship conflicts with admitted paper facts."""


class PaperExecutionUnavailable(Exception):
    """Required issuer relationship cannot be established."""


class PaperExecutionContractError(ValueError):
    """An installed issuer supplied an invalid correlation contract."""


@dataclass(frozen=True, slots=True, repr=False)
class IssuedQuestionExecutionRelation:
    question_id: str
    family: str
    source_artifact_ref: str
    evidence_scope_ref: str
    answer_region_ref: str
    source_revision: str
    provenance_ref: str
    rubric_ref: str
    scoring_policy_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class IssuedPaperExecutionRelation:
    version: int
    request: PaperAdmissionRequest
    actor_ref: str
    issuer_ref: str
    issuance_ref: str
    paper_ref: str
    set_ref: str
    approval_ref: str
    approval_revision: str
    selection_decision_ref: str
    selection_revision: str
    source_revision: str
    readiness_revision: str
    questions: tuple[IssuedQuestionExecutionRelation, ...]


@dataclass(frozen=True, slots=True, repr=False)
class CorrelatedPaperExecution:
    """Detached snapshot, deliberately NOT transferable execution authority."""
    plan: AdmittedPaperPlan
    issuer_relation: IssuedPaperExecutionRelation
    execution_state: str  # CORRELATED_CHOICE_ONLY or CORRELATED_DIRECT_NUMERIC; not effect authorization


class PaperExecutionIssuer(Protocol):
    def correlate_paper_execution(self, *, plan: AdmittedPaperPlan) -> IssuedPaperExecutionRelation: ...


def _attr(value: object, name: str) -> object:
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        raise PaperExecutionContractError('Incomplete installed correlation record.') from None


def _plan(value: object, maximum: int, limit: int) -> AdmittedPaperPlan:
    if type(value) is not AdmittedPaperPlan:
        raise PaperExecutionContractError('An exact admitted paper plan is required.')
    req = _request(_attr(value, 'request'), limit)
    approved_source_revision = _id(_attr(value, 'source_revision'), limit)
    questions = _attr(value, 'questions')
    if type(questions) is not tuple or not questions or len(questions) > maximum:
        raise PaperExecutionContractError('Question inventory is missing or oversized.')
    copy = []
    ids = set()
    regions = set()
    scopes = set()
    for q in questions:
        if type(q) is not AdmittedPaperQuestion:
            raise PaperExecutionContractError('Foreign admitted question record.')
        r = _request_snapshot(_attr(q, 'request'), limit)
        if (r.tenant_ref, r.session_ref, r.grading_run_id, r.submission_ref,
            r.exam_ref, r.grading_spec_ref) != (
                req.tenant_ref, req.session_ref, req.grading_run_id, req.submission_ref,
                req.exam_ref, req.grading_spec_ref):
            raise PaperExecutionDenied('Question scope differs from the paper.')
        if r.question_id in ids:
            raise PaperExecutionDenied('Duplicate question.')
        ids.add(r.question_id)
        fields = [_id(_attr(q, k), limit) for k in ('family', 'source_artifact_ref',
                    'source_revision', 'evidence_scope_ref', 'answer_region_ref', 'provenance_ref')]
        if fields[0] not in ('CHOICE', 'DIRECT', 'NUMERIC'):
            raise PaperExecutionContractError('Unknown paper family.')
        if fields[2] != approved_source_revision:
            raise PaperExecutionDenied('Question source revision differs from approved paper.')
        if fields[3] in scopes:
            raise PaperExecutionDenied('Question evidence scopes overlap.')
        scopes.add(fields[3])
        region = (fields[1], fields[4])
        if region in regions:
            raise PaperExecutionDenied('Duplicate answer region.')
        regions.add(region)
        copy.append(AdmittedPaperQuestion(request=r, family=fields[0], source_artifact_ref=fields[1],
            source_revision=fields[2], evidence_scope_ref=fields[3], answer_region_ref=fields[4],
            provenance_ref=fields[5]))
    return AdmittedPaperPlan(request=req, questions=tuple(copy), **{
        k: _id(_attr(value, k), limit) for k in ('actor_ref', 'approval_ref',
        'approval_revision', 'selection_decision_ref', 'selection_revision',
        'source_revision', 'readiness_revision')})


def _relation(value: object, maximum: int, limit: int) -> IssuedPaperExecutionRelation:
    if type(value) is not IssuedPaperExecutionRelation:
        raise PaperExecutionContractError('Issuer supplied a foreign record.')
    version = _attr(value, 'version')
    if type(version) is not int or version != 1:
        raise PaperExecutionContractError('Unsupported issuer contract version.')
    questions = _attr(value, 'questions')
    if type(questions) is not tuple or not questions or len(questions) > maximum:
        raise PaperExecutionContractError('Invalid issuer question inventory.')
    copied = []
    ids = set()
    for q in questions:
        if type(q) is not IssuedQuestionExecutionRelation:
            raise PaperExecutionContractError('Foreign issuer question.')
        values = {k: _id(_attr(q, k), limit) for k in (
            'question_id','family','source_artifact_ref','evidence_scope_ref',
            'answer_region_ref','source_revision','provenance_ref','rubric_ref','scoring_policy_ref')}
        if values['question_id'] in ids:
            raise PaperExecutionDenied('Issuer repeats a question.')
        ids.add(values['question_id'])
        copied.append(IssuedQuestionExecutionRelation(**values))
    return IssuedPaperExecutionRelation(version=1, request=_request(_attr(value, "request"), limit),
        questions=tuple(copied), **{
        k: _id(_attr(value, k), limit) for k in ('actor_ref','issuer_ref', 'issuance_ref','paper_ref','set_ref',
        'approval_ref','approval_revision','selection_decision_ref','selection_revision',
        'source_revision','readiness_revision')})


class ProductionPaperExecutionCorrelation:
    """Consumes only an installed issuer; the caller cannot submit its own relation."""
    # Protect installation-owned bindings against ordinary callback reassignment.
    # Python in-process objects are not a sandbox for malicious executable code.
    __slots__ = ('_method', '_maximum', '_limit', '_configured_limits')

    def __setattr__(self, name: str, value: object) -> None:
        # Do not allow a compatible subclass to replace the attribute guards or
        # shadow the installed issuer/limit descriptors via an ordinary write.
        if name == '__class__':
            raise PaperExecutionContractError('Installed correlation class cannot be replaced.')
        if name in ('_method', '_configured_limits'):
            try:
                object.__getattribute__(self, name)
            except AttributeError:
                pass  # First assignment during installation only.
            else:
                raise PaperExecutionContractError('Installed correlation binding cannot be replaced.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        # Prevent deleting and subsequently reinstalling an installed binding.
        if name in ('_method', '_configured_limits', '_maximum', '_limit'):
            raise PaperExecutionContractError('Installed correlation configuration cannot be deleted.')
        object.__delattr__(self, name)

    def __init__(self, *, issuer: PaperExecutionIssuer, max_questions: int,
                 max_identifier_characters: int) -> None:
        try:
            self._install(issuer=issuer, max_questions=max_questions,
                          max_identifier_characters=max_identifier_characters)
        except PaperExecutionContractError as error:
            # `from None` suppresses display, NOT access to `__context__`.
            error.__cause__ = None
            error.__context__ = None
            error.__suppress_context__ = True
            raise error from None

    def _install(self, *, issuer: PaperExecutionIssuer, max_questions: int,
                 max_identifier_characters: int) -> None:
        if (type(max_questions) is not int or not 0 < max_questions <= 1000 or
            type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 4096):
            raise PaperExecutionContractError('Finite resource limits are required.')
        try:
            method = object.__getattribute__(issuer, 'correlate_paper_execution')
        except (AttributeError, Exception):
            raise PaperExecutionContractError('No installed correlation issuer.') from None
        if not callable(method):
            raise PaperExecutionContractError('Correlation issuer is not callable.')
        self._method = method
        self._maximum = max_questions
        self._limit = max_identifier_characters
        # Installation-time limits are the resource-authority baseline. An issuer
        # callback must not relax admission for this or a later preflight.
        self._configured_limits = (max_questions, max_identifier_characters)

    def preflight(self, *, plan: AdmittedPaperPlan) -> CorrelatedPaperExecution:
        try:
            return self._preflight(plan=plan)
        except (PaperExecutionDenied, PaperExecutionUnavailable, PaperExecutionContractError) as error:
            error.__cause__ = None
            error.__context__ = None
            error.__suppress_context__ = True
            raise error from None

    def _preflight(self, *, plan: AdmittedPaperPlan) -> CorrelatedPaperExecution:
        try:
            maximum, limit = self._configured_limits
            if (type(self._maximum) is not int or type(self._limit) is not int
                    or (self._maximum, self._limit) != (maximum, limit)):
                raise PaperExecutionContractError('Installed correlation resource limits have changed.')
            original = _plan(plan, maximum, limit)
            argument = _plan(original, maximum, limit)
            try:
                raw = self._method(plan=argument)
            except PaperExecutionDenied:
                raise PaperExecutionDenied('Installed issuer refused execution correlation.') from None
            except PaperExecutionContractError:
                raise PaperExecutionContractError('Installed issuer violated its correlation contract.') from None
            except Exception:
                raise PaperExecutionUnavailable('Installed execution issuer is unavailable.') from None
            # Use the installation-time bounds for every validation after contact.
            # Also reject configuration drift so subsequent calls fail closed.
            if (type(self._maximum) is not int or type(self._limit) is not int
                    or (self._maximum, self._limit) != (maximum, limit)):
                raise PaperExecutionContractError('Correlation resource limits changed during issuer contact.')
            # Never contact another authority after a callback mutates an earlier input.
            if (_plan(plan, maximum, limit) != original or
                _plan(argument, maximum, limit) != original):
                raise PaperExecutionDenied('Paper facts changed during issuer contact.')
            issued = _relation(raw, maximum, limit)
            if (issued.request != original.request or
                issued.actor_ref != original.actor_ref or
                issued.paper_ref != original.request.paper_ref or
                issued.set_ref != original.request.set_ref or
                issued.approval_ref != original.approval_ref or
                issued.approval_revision != original.approval_revision or
                issued.selection_decision_ref != original.selection_decision_ref or
                issued.selection_revision != original.selection_revision or
                issued.source_revision != original.source_revision or
                issued.readiness_revision != original.readiness_revision):
                raise PaperExecutionDenied('Issuer returned a foreign paper/revision.')
            if len(issued.questions) != len(original.questions):
                raise PaperExecutionDenied('Incomplete paper execution inventory.')
            by_id = {q.request.question_id: q for q in original.questions}
            for q in issued.questions:
                match = by_id.get(q.question_id)
                if match is None or any(getattr(q, name) != getattr(match, name) for name in (
                    'family','source_artifact_ref','evidence_scope_ref','answer_region_ref',
                    'source_revision','provenance_ref')):
                    raise PaperExecutionDenied('Issuer relationship mismatches admitted answer.')
            return CorrelatedPaperExecution(plan=original, issuer_relation=issued,
                execution_state=('CORRELATED_CHOICE_ONLY' if all(q.family == 'CHOICE'
                                 for q in original.questions) else
                                 'CORRELATED_DIRECT_NUMERIC' if all(q.family in ('DIRECT', 'NUMERIC')
                                 for q in original.questions) else 'UNSUPPORTED_FAMILIES'))
        except (PaperAdmissionContractError, ValueError, TypeError) as error:
            if type(error) in (PaperExecutionDenied, PaperExecutionContractError):
                raise
            raise PaperExecutionContractError('Correlation input is malformed.') from None
