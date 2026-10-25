"""academic-bound physical claim: engine-owned academic-issuance-bound physical-attempt preclaim contract.

Preparation must durably record the *original* complete academic authority before
any physical attempt claim. The same qualified store must atomically enforce that
binding (or an approved equivalent lease/version predicate) during the claim.
These typed results test that contract; they do not authenticate the backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.integration.attempt_authority import (
    AttemptClaimRequest, AttemptClaim, AttemptClaimRecoveryFact, _request_snapshot,
)
from grading.integration.paper_execution_correlation import (
    IssuedPaperExecutionRelation, _relation,
)
from grading.integration.execution_eligibility import _id
from grading.contracts.paper_aggregation import (
    ResolvedPaperScoringAuthority, ExpectedQuestionResult,
    _validate_resolved_paper_scoring_authority,
)


class AcademicPreclaimState(str, Enum):
    PREPARED = 'PREPARED'
    REJECTED = 'REJECTED'
    CONFLICT = 'CONFLICT'
    INDETERMINATE = 'INDETERMINATE'


@dataclass(frozen=True, slots=True, repr=False)
class AcademicClaimIntent:
    original_request: AttemptClaimRequest
    issued_paper: IssuedPaperExecutionRelation
    question_id: str
    scoring: ResolvedPaperScoringAuthority  # versioned rubric AND policy for whole paper


@dataclass(frozen=True, slots=True, repr=False)
class AcademicClaimPreparation:
    """A backend-asserted durable binding, NOT a transferable permit."""
    intent: AcademicClaimIntent
    binding_ref: str
    approval_revision: str
    state: AcademicPreclaimState


@dataclass(frozen=True, slots=True, repr=False)
class AcademicallyBoundClaim:
    preparation: AcademicClaimPreparation
    claim: AttemptClaim


@dataclass(frozen=True, slots=True, repr=False)
class AcademicClaimBindingRecovery:
    """Read-only backend observation; never grants retry, grade or new physical attempt claim."""
    intent: AcademicClaimIntent
    state: AcademicPreclaimState
    preparation: AcademicClaimPreparation | None


class QualifiedAcademicClaimBindingStore(Protocol):
    """Operations MUST refer to one durable, atomic academic/physical attempt claim authority.

    prepare_original_binding MUST persist original request+full issuance before
    any physical attempt claim. claim_bound_fresh MUST atomically enforce that same binding,
    approved revision and any approved lease condition at physical claim time.
    reconcile_original_binding MUST be read-only under original request identity.
    """
    def prepare_original_binding(self, *, intent: AcademicClaimIntent) -> AcademicClaimPreparation: ...
    def claim_bound_fresh(self, *, preparation: AcademicClaimPreparation) -> AcademicallyBoundClaim: ...
    def reconcile_original_binding(self, *, intent: AcademicClaimIntent) -> AcademicClaimBindingRecovery: ...
    def reconcile_bound_attempt(self, *, request: AttemptClaimRequest) -> AttemptClaimRecoveryFact: ...


def academic_intent(request: AttemptClaimRequest, issued: IssuedPaperExecutionRelation,
                    scoring: ResolvedPaperScoringAuthority,
                    maximum: int, max_questions: int) -> AcademicClaimIntent:
    original = _request_snapshot(request, maximum)
    paper = _relation(issued, max_questions, maximum)
    resolved = _validate_resolved_paper_scoring_authority(scoring)
    if (resolved.grading_spec_ref != paper.request.grading_spec_ref
            or len(resolved.expected_questions) != len(paper.questions)
            or len(resolved.expected_questions) > max_questions):
        raise ValueError('Versioned paper score authority differs from academic issuance.')
    for academic, versioned in zip(paper.questions, resolved.expected_questions, strict=True):
        if (type(versioned) is not ExpectedQuestionResult
                or academic.question_id != versioned.question_id
                or academic.rubric_ref != versioned.rubric_ref.id
                or academic.scoring_policy_ref != versioned.scoring_policy_ref.id
                or versioned.rubric_ref.version <= 0
                or versioned.scoring_policy_ref.version <= 0
                or not versioned.scoring_policy_ref.scoring_semantics_version):
            raise ValueError('Rubric or policy revision does not match approved full paper.')
    scope = original[0]
    req = paper.request
    if (scope.actor_ref != paper.actor_ref
            or (scope.tenant_ref, scope.session_ref, scope.grading_run_id,
                scope.submission_ref, scope.exam_ref, scope.grading_spec_ref) !=
               (req.tenant_ref, req.session_ref, req.grading_run_id,
                req.submission_ref, req.exam_ref, req.grading_spec_ref)
            or scope.source_revision != paper.source_revision):
        raise ValueError('Original grading-attempt request does not belong to this issued academic paper.')
    matching = [q for q in paper.questions if q.question_id == scope.question_id]
    if len(matching) != 1:
        raise ValueError('Original grading-attempt question is not unique in the issued paper.')
    q = matching[0]
    if (q.family != original[2] or q.family not in ('CHOICE', 'DIRECT', 'NUMERIC')
            or (q.source_artifact_ref, q.evidence_scope_ref, q.source_revision,
                q.provenance_ref) != (scope.source_artifact_ref, scope.evidence_scope_ref,
                                      scope.source_revision, scope.ocr_provenance)):
        raise ValueError('Original grading-attempt request and question academic provenance disagree.')
    return AcademicClaimIntent(request, paper, q.question_id, resolved)


def validate_preparation(value: object, intent: AcademicClaimIntent, maximum: int,
                         *, require_prepared: bool = True) -> AcademicClaimPreparation:
    if (type(value) is not AcademicClaimPreparation
            or type(value.intent) is not AcademicClaimIntent
            or value.intent != intent
            or type(value.state) is not AcademicPreclaimState):
        raise ValueError('Foreign or invalid academic grading-attempt preparation.')
    _id(value.binding_ref, maximum)
    _id(value.approval_revision, maximum)
    if value.approval_revision != intent.issued_paper.approval_revision:
        raise ValueError('Durable academic approval revision differs from original issuer.')
    if require_prepared and value.state is not AcademicPreclaimState.PREPARED:
        raise ValueError('Academic claim preparation is not affirmative.')
    return value


def validate_bound_claim(value: object, preparation: AcademicClaimPreparation,
                         maximum: int) -> AttemptClaim:
    if (type(value) is not AcademicallyBoundClaim
            or type(value.claim) is not AttemptClaim
            or type(value.preparation) is not AcademicClaimPreparation
            or value.preparation != preparation
            or _request_snapshot(value.claim.request, maximum) !=
               _request_snapshot(preparation.intent.original_request, maximum)):
        raise ValueError('grading-attempt claim not bound to the exact prepared academic request.')
    return value.claim


def validate_binding_recovery(value: object, intent: AcademicClaimIntent,
                              maximum: int) -> AcademicClaimBindingRecovery:
    if (type(value) is not AcademicClaimBindingRecovery
            or type(value.intent) is not AcademicClaimIntent
            or value.intent != intent
            or type(value.state) is not AcademicPreclaimState):
        raise ValueError('Foreign academic preclaim recovery identity.')
    if value.state is AcademicPreclaimState.PREPARED:
        validate_preparation(value.preparation, intent, maximum)
    elif value.preparation is not None:
        raise ValueError('Negative or unknown binding recovery carried a positive receipt.')
    return value


@dataclass(frozen=True, slots=True, repr=False)
class AcademicQuestionRecovery:
    question_id: str
    state: AcademicPreclaimState
    preparation: AcademicClaimPreparation | None = None

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def authorizes_publication(self) -> bool:
        return False


class ProductionPaperAcademicBindingRecovery:
    """Read-only academic-bound physical claim consumer of actually captured, original preclaim identities.

    No claim, evaluator, audit write or retry. The custody record is a local
    observation, not an authenticated source-of-record grant. Real backend
    authenticity and durable persistence remain adapter qualification gates.
    """
    __slots__ = ('_read', '_maximum', '_questions')

    def __init__(self, *, store: QualifiedAcademicClaimBindingStore,
                 max_identifier_characters: int, max_questions: int):
        from grading.integration.execution_eligibility import _capture
        if (type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 10000):
            raise ValueError('Finite academic recovery bounds are required.')
        object.__setattr__(self, '_read', _capture(
            store, 'reconcile_original_binding', ('intent',)))
        object.__setattr__(self, '_maximum', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)

    def __setattr__(self, name, value):
        raise AttributeError('Installed academic recovery operation is immutable.')

    def reconcile(self, *, custody) -> tuple[AcademicQuestionRecovery, ...]:
        from grading.integration.whole_paper_attempt_custody import _admit
        from grading.integration.attempt_lineage import _snapshot_owned
        # Re-admit complete inter-question identity before ANY external read.
        validated = _admit(custody.plan, custody.outcome, self._questions, self._maximum)
        if validated != custody:
            raise ValueError('Caller record differs from captured paper custody.')
        baseline = _snapshot_owned(custody)
        results = []
        for q in validated.questions:
            if q.claim_conflict:
                results.append(AcademicQuestionRecovery(q.question_id, AcademicPreclaimState.CONFLICT))
                continue
            if q.original_f25_request is None or q.academic_preparation is None:
                results.append(AcademicQuestionRecovery(q.question_id, AcademicPreclaimState.INDETERMINATE))
                continue
            try:
                intent = academic_intent(q.original_f25_request,
                    validated.outcome.issued_paper, q.academic_preparation.intent.scoring,
                    self._maximum, self._questions)
                expected = validate_preparation(q.academic_preparation, intent, self._maximum)
                if _snapshot_owned(custody) != baseline:
                    raise ValueError('Original paper changed before binding recovery.')
            except Exception:
                results.append(AcademicQuestionRecovery(q.question_id, AcademicPreclaimState.CONFLICT))
                continue
            try:
                fact = self._read(intent=intent)
                if _snapshot_owned(custody) != baseline:
                    results.append(AcademicQuestionRecovery(q.question_id, AcademicPreclaimState.CONFLICT))
                    continue
                recovered = validate_binding_recovery(fact, intent, self._maximum)
                if (recovered.state is AcademicPreclaimState.PREPARED
                        and recovered.preparation != expected):
                    results.append(AcademicQuestionRecovery(q.question_id, AcademicPreclaimState.CONFLICT))
                else:
                    results.append(AcademicQuestionRecovery(q.question_id, recovered.state,
                        recovered.preparation))
            except Exception:
                results.append(AcademicQuestionRecovery(q.question_id, AcademicPreclaimState.INDETERMINATE))
        return tuple(results)


def academic_identity_snapshot(intent: AcademicClaimIntent, maximum: int,
                               max_questions: int) -> tuple[object, ...]:
    """Value-based *complete* bounded academic identity across Python copies.

    The generic owned-object snapshot includes allocation IDs and therefore
    cannot compare `_relation()`'s independently reconstructed values. This
    specialized snapshot captures exact physical request, whole issuer relation,
    rubric/policy versions, scoring semantics and original score limits.
    """
    if type(intent) is not AcademicClaimIntent:
        raise ValueError('Original academic binding intent required.')
    checked = academic_intent(intent.original_request, intent.issued_paper,
                              intent.scoring, maximum, max_questions)
    scoring = checked.scoring
    return (_request_snapshot(checked.original_request, maximum),
            checked.issued_paper, checked.question_id,
            scoring.grading_spec_ref,
            tuple((q.question_id, q.rubric_ref.id, q.rubric_ref.version,
                   q.scoring_policy_ref.id, q.scoring_policy_ref.version,
                   q.scoring_policy_ref.scoring_semantics_version)
                  for q in scoring.expected_questions),
            scoring.minimum_score.as_decimal().as_tuple(),
            scoring.maximum_score.as_decimal().as_tuple())
