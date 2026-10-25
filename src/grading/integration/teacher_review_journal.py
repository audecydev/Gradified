"""teacher review: fixed-original, append-only teacher review/override *decision* custody.

An admitted teacher override is a recorded school decision, NEVER a rewriting
of frozen criterion scoring/deterministic scoring marks, a rerun grant, a rubric edit, or publication authority.
The installed original reader, teacher issuer and journal owner must authenticate
and compare the ORIGINAL CAS + current approval within the real append transaction.
A Python acknowledgement cannot prove the backend did so.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.scoring.arithmetic import exact_compare
from grading.integration.execution_eligibility import _id, _capture
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy, _snapshot_owned
from grading.integration.whole_paper_cas import (
    PaperCASReceipt, _validate_transaction, _receipt,
)
from grading.integration.result_constituents import _readmit_question_score, _readmit_paper_score


class TeacherReviewAction(str, Enum):
    ACCEPT_ORIGINAL = 'ACCEPT_ORIGINAL'
    OVERRIDE_MARK = 'OVERRIDE_MARK'


class TeacherReviewState(str, Enum):
    BLOCKED = 'BLOCKED'
    COMMITTED = 'COMMITTED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class OriginalTeacherReviewCase:
    """Fixed original scored-CAS receipt, NOT a selectable bearer grant."""
    original_cas: PaperCASReceipt
    question_id: str


@dataclass(frozen=True, slots=True, repr=False)
class SchoolTeacherReviewDecision:
    """Source-issued teacher decision; issuer authentication remains external."""
    decision_ref: str
    teacher_ref: str
    tenant_ref: str
    grading_run_id: str
    submission_ref: str
    question_id: str
    original_result_ref: str
    original_commit_ref: str
    original_rubric_ref: str
    original_rubric_version: int
    approval_ref: str
    approval_version: int
    action: TeacherReviewAction
    proposed_mark: ScoringDecimal | None = None
    reason_ref: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class ConditionalTeacherReviewAppend:
    original: OriginalTeacherReviewCase
    decision: SchoolTeacherReviewDecision


@dataclass(frozen=True, slots=True, repr=False)
class TeacherReviewAppendReceipt:
    decision_ref: str
    original_result_ref: str
    original_commit_ref: str
    journal_event_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class TeacherReviewAppendReply:
    state: TeacherReviewState
    receipt: TeacherReviewAppendReceipt | None = None


@dataclass(frozen=True, slots=True, repr=False)
class TeacherReviewObservation:
    state: TeacherReviewState
    decision_ref: str | None = None
    journal_event_ref: str | None = None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def changes_official_grade(self) -> bool:
        return False


class QualifiedOriginalReviewSource(Protocol):
    def resolve_original_teacher_review_case(self) -> OriginalTeacherReviewCase: ...


class QualifiedTeacherDecisionSource(Protocol):
    def resolve_current_teacher_review_decision(self) -> SchoolTeacherReviewDecision: ...


class QualifiedConditionalReviewJournal(Protocol):
    def append_teacher_review_if_current(
        self, *, request: ConditionalTeacherReviewAppend,
    ) -> TeacherReviewAppendReply: ...


def _admit(case: object, decision: object, policy: LegalGradingTransitionPolicy, limit: int):
    if (type(case) is not OriginalTeacherReviewCase
            or type(case.original_cas) is not PaperCASReceipt
            or type(decision) is not SchoolTeacherReviewDecision
            or type(decision.action) is not TeacherReviewAction):
        raise ValueError('Exact original scored-CAS and teacher decision required.')
    original = case.original_cas
    transaction = original.transaction
    _validate_transaction(transaction, transaction.intent, policy, limit)
    _receipt(original, transaction, limit)
    qid = _id(case.question_id, limit)
    issued_plan = transaction.intent.plan
    scored = transaction.intent.result
    if (type(scored.questions) is not tuple
            or type(scored.paper_score.question_results) is not tuple):
        raise ValueError('Original scored paper is incomplete.')
    _readmit_paper_score(scored.paper_score)
    if (scored.paper_score.grading_spec_ref != issued_plan.request.grading_spec_ref
            or tuple(q.question_id for q in scored.paper_score.question_results) !=
               tuple(q.request.question_id for q in issued_plan.questions)):
        raise ValueError('Scored question inventory differs from original paper.')
    rows = tuple(q for q in scored.paper_score.question_results if q.question_id == qid)
    issued = tuple(q for q in transaction.intent.issued.questions if q.question_id == qid)
    if (len(rows) != 1 or len(issued) != 1
            or sum(q.request.question_id == qid for q in issued_plan.questions) != 1):
        raise ValueError('Review question is outside the original scored paper.')
    score = rows[0]
    _readmit_question_score(score)
    if (score.rubric_ref.id != issued[0].rubric_ref
            or score.scoring_policy_ref.id != issued[0].scoring_policy_ref):
        raise ValueError('Original review rubric/scoring identity is not issued paper identity.')
    if (type(transaction.intent.result.context.grading_run_id) is not str
            or scored.context.grading_run_id != issued_plan.request.grading_run_id
            or scored.context.submission_ref != issued_plan.request.submission_ref):
        raise ValueError('Original scored execution disagrees with paper identity.')
    fields = ('decision_ref', 'teacher_ref', 'tenant_ref', 'grading_run_id',
              'submission_ref', 'question_id', 'original_result_ref',
              'original_commit_ref', 'original_rubric_ref', 'approval_ref')
    for field in fields:
        _id(getattr(decision, field), limit)
    if (type(decision.original_rubric_version) is not int
            or decision.original_rubric_version <= 0
            or type(decision.approval_version) is not int
            or decision.approval_version <= 0
            or (decision.tenant_ref, decision.grading_run_id,
                decision.submission_ref, decision.question_id,
                decision.original_result_ref, decision.original_commit_ref,
                decision.original_rubric_ref, decision.original_rubric_version) !=
               (issued_plan.request.tenant_ref, issued_plan.request.grading_run_id,
                issued_plan.request.submission_ref, qid, transaction.result_ref,
                original.commit_ref, score.rubric_ref.id, score.rubric_ref.version)):
        raise ValueError('Review decision does not bind this original paper/question/rubric.')
    if decision.reason_ref is not None:
        _id(decision.reason_ref, limit)
    if decision.action is TeacherReviewAction.ACCEPT_ORIGINAL:
        if decision.proposed_mark is not None:
            raise ValueError('Acceptance cannot overwrite a mark.')
    else:
        if type(decision.proposed_mark) is not ScoringDecimal:
            raise ValueError('Teacher override requires an exact mark.')
        mark = ScoringDecimal(decision.proposed_mark.as_decimal())
        if (exact_compare(mark, score.minimum_score) < 0
                or exact_compare(mark, score.maximum_score) > 0):
            raise ValueError('Teacher override lies outside the approved question bounds.')
    return ConditionalTeacherReviewAppend(case, decision)


def _snapshot_original_review_case(case: object, policy: LegalGradingTransitionPolicy,
                                   limit: int) -> tuple[object, ...]:
    """Readmit the fixed original before a separately installed teacher callback.

    This in-process continuity snapshot does not authenticate its upstream
    source or substitute for the journal's atomic original/approval comparison.
    """
    if type(case) is not OriginalTeacherReviewCase or type(case.original_cas) is not PaperCASReceipt:
        raise ValueError('Exact original scored-CAS review case required.')
    original = case.original_cas
    tx = original.transaction
    _validate_transaction(tx, tx.intent, policy, limit)
    _receipt(original, tx, limit)
    qid = _id(case.question_id, limit)
    if (sum(q.request.question_id == qid for q in tx.intent.plan.questions) != 1
            or sum(q.question_id == qid for q in tx.intent.issued.questions) != 1
            or sum(q.question_id == qid for q in tx.intent.result.paper_score.question_results) != 1):
        raise ValueError('Review question is outside the original scored paper.')
    return _snapshot_owned(case)


class ProductionTeacherReviewJournal:
    """One guarded teacher decision -> qualified conditional journal operation.

    No synthetic actor, rubric, override value, journal or publication decision.
    The qualified journal MUST compare current original CAS and approved teacher
    authorization atomically with append and make decision_ref idempotent.
    """
    __slots__ = ('_original', '_teacher', '_append', '_policy', '_limit', '_gate', '_consumed')

    def __init__(self, *, original_source: QualifiedOriginalReviewSource,
                 teacher_source: QualifiedTeacherDecisionSource,
                 journal: QualifiedConditionalReviewJournal,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int):
        if (type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096):
            raise ValueError('Exact lifecycle authorization original and bounded review installation required.')
        _id(legal_policy.policy_id, max_identifier_characters)
        object.__setattr__(self, '_original', _capture(original_source,
            'resolve_original_teacher_review_case', ()))
        object.__setattr__(self, '_teacher', _capture(teacher_source,
            'resolve_current_teacher_review_decision', ()))
        object.__setattr__(self, '_append', _capture(journal,
            'append_teacher_review_if_current', ('request',)))
        object.__setattr__(self, '_policy', legal_policy)
        object.__setattr__(self, '_limit', max_identifier_characters)
        object.__setattr__(self, '_gate', Lock())
        object.__setattr__(self, '_consumed', False)

    def __setattr__(self, key, value):
        raise AttributeError('Teacher review installation cannot be replaced.')

    def record(self) -> TeacherReviewObservation:
        if not self._gate.acquire(blocking=False):
            return TeacherReviewObservation(TeacherReviewState.UNKNOWN)
        try:
            if self._consumed:
                return TeacherReviewObservation(TeacherReviewState.UNKNOWN)
            # Per-installed-original one-shot custody. A lost append ack may
            # have committed; repeated contact requires backend original-key
            # recovery and a freshly authorized operation, never this instance.
            object.__setattr__(self, '_consumed', True)
            try:
                original = self._original()  # fixed original, no caller selector
                original_before_teacher = _snapshot_original_review_case(
                    original, self._policy, self._limit)
                teacher = self._teacher()    # separately qualified source
                if _snapshot_owned(original) != original_before_teacher:
                    raise ValueError('Original review selection changed during teacher resolution.')
                request = _admit(original, teacher, self._policy, self._limit)
                if _snapshot_owned(original) != original_before_teacher:
                    raise ValueError('Original review selection changed before journal contact.')
                baseline = _snapshot_owned(request)
            except Exception:
                return TeacherReviewObservation(TeacherReviewState.BLOCKED)
            try:
                reply = self._append(request=request)
                if (_snapshot_owned(request) != baseline
                        or type(reply) is not TeacherReviewAppendReply
                        or type(reply.state) is not TeacherReviewState):
                    return TeacherReviewObservation(TeacherReviewState.UNKNOWN)
                if reply.state is TeacherReviewState.COMMITTED:
                    receipt = reply.receipt
                    if (type(receipt) is not TeacherReviewAppendReceipt
                            or any(type(getattr(receipt, name)) is not str for name in (
                                'decision_ref','original_result_ref',
                                'original_commit_ref','journal_event_ref'))
                            or receipt.decision_ref != teacher.decision_ref
                            or receipt.original_result_ref != original.original_cas.transaction.result_ref
                            or receipt.original_commit_ref != original.original_cas.commit_ref):
                        return TeacherReviewObservation(TeacherReviewState.UNKNOWN)
                    _id(receipt.journal_event_ref, self._limit)
                    return TeacherReviewObservation(TeacherReviewState.COMMITTED,
                        teacher.decision_ref, receipt.journal_event_ref)
                if reply.receipt is not None:
                    return TeacherReviewObservation(TeacherReviewState.UNKNOWN)
                return TeacherReviewObservation(reply.state)
            except Exception:
                # A contacted journal can commit before an exception/lost ack.
                return TeacherReviewObservation(TeacherReviewState.UNKNOWN)
        finally:
            self._gate.release()


class TeacherReviewRecoveryState(str, Enum):
    """Read-only historical status; ABSENCE_REPORTED never permits reappend."""
    COMMITTED = 'COMMITTED'
    ABSENCE_REPORTED = 'ABSENCE_REPORTED'
    CONFLICT = 'CONFLICT'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True, repr=False)
class TeacherReviewJournalRecovery:
    """Qualified backend read of the fixed historical decision/original pair.

    The journal must resolve its ORIGINAL durable key (including decision_ref,
    original result/commit and tenant scope), not a caller-selected replacement.
    The request echo is a consistency assertion, not a bearer credential.
    """
    state: TeacherReviewRecoveryState
    request: ConditionalTeacherReviewAppend
    receipt: TeacherReviewAppendReceipt | None = None


@dataclass(frozen=True, slots=True, repr=False)
class TeacherReviewRecoveryObservation:
    state: TeacherReviewRecoveryState
    decision_ref: str | None = None
    journal_event_ref: str | None = None

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False

    @property
    def authorizes_reappend(self) -> bool:
        return False

    @property
    def changes_official_grade(self) -> bool:
        return False


class QualifiedOriginalTeacherDecisionSource(Protocol):
    """Resolve the original issued decision, NOT the latest/current approval."""
    def resolve_original_teacher_review_decision(self) -> SchoolTeacherReviewDecision: ...


class QualifiedTeacherReviewJournalReader(Protocol):
    """Read only. Exactly the same original-key scope as conditional append."""
    def reconcile_teacher_review(self, *, request: ConditionalTeacherReviewAppend,
                                 ) -> TeacherReviewJournalRecovery: ...


class ProductionTeacherReviewRecovery:
    """Recover one fixed review decision without creating any review effect.

    The application root installs *independently qualified* fixed-original CAS,
    historical decision and journal reader owners. A caller never supplies a
    decision_ref, arbitrary original or recovered receipt to choose the lookup.
    This reads the historical decision even if CURRENT approval was revoked.
    A Python read reply alone does not prove durability or issuer authenticity.
    """
    __slots__ = ('_original', '_decision', '_read', '_policy', '_limit', '_gate')

    def __init__(self, *, original_source: QualifiedOriginalReviewSource,
                 original_decision_source: QualifiedOriginalTeacherDecisionSource,
                 journal_reader: QualifiedTeacherReviewJournalReader,
                 legal_policy: LegalGradingTransitionPolicy,
                 max_identifier_characters: int):
        if (type(legal_policy) is not LegalGradingTransitionPolicy
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096):
            raise ValueError('Exact bounded original teacher review recovery required.')
        _id(legal_policy.policy_id, max_identifier_characters)
        object.__setattr__(self, '_original', _capture(original_source,
            'resolve_original_teacher_review_case', ()))
        object.__setattr__(self, '_decision', _capture(original_decision_source,
            'resolve_original_teacher_review_decision', ()))
        object.__setattr__(self, '_read', _capture(journal_reader,
            'reconcile_teacher_review', ('request',)))
        object.__setattr__(self, '_policy', legal_policy)
        object.__setattr__(self, '_limit', max_identifier_characters)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, key, value):
        raise AttributeError('Original teacher review recovery installation cannot be replaced.')

    def reconcile(self, *, expected_original=None) -> TeacherReviewRecoveryObservation:
        """Read fixed historical journal, optionally compare a recovered scored original.

        ``expected_original`` is a consistency target, not a selector or bearer
        authorization. The installed reader must still recover its own original.
        Legacy selector-free reconcile() retains its existing behavior.
        """
        if expected_original is not None:
            from grading.integration.governed_operation_consumer import ScoredOperationIdentity
            if type(expected_original) is not ScoredOperationIdentity:
                raise ValueError('Exact scored-original comparison target required.')
        if not self._gate.acquire(blocking=False):
            return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
        try:
            try:
                original = self._original()
                original_before = _snapshot_owned(original)
                decision = self._decision()
                if _snapshot_owned(original) != original_before:
                    return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
                request = _admit(original, decision, self._policy, self._limit)
                if expected_original is not None:
                    # No caller-selected journal lookup: match the original fixed
                    # scored-CAS identity *before* contacting the journal reader.
                    tx = original.original_cas.transaction
                    plan = tx.intent.plan
                    expected_values = (
                        expected_original.tenant_ref, expected_original.grading_run_id,
                        expected_original.original_scored_result_ref,
                        expected_original.source_revision, expected_original.transaction_ref,
                        expected_original.transaction_event_ref, expected_original.commit_ref)
                    actual_values = (
                        plan.request.tenant_ref, plan.request.grading_run_id,
                        tx.result_ref, plan.source_revision, tx.request_ref,
                        tx.event_ref, original.original_cas.commit_ref)
                    # The historical teacher review legal policy and original journal
                    # determine allowed purposes, not an invented local list.
                    if actual_values != expected_values:
                        return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
                original_snapshot = _snapshot_owned(request)
            except Exception:
                # A fixed historical source that cannot be read or admitted
                # is not evidence of durable absence.
                return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
            try:
                fact = self._read(request=request)
                if (_snapshot_owned(request) != original_snapshot
                        or type(fact) is not TeacherReviewJournalRecovery
                        or type(fact.state) is not TeacherReviewRecoveryState
                        or type(fact.request) is not ConditionalTeacherReviewAppend
                        or _snapshot_owned(fact.request) != original_snapshot):
                    return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
                if fact.state is TeacherReviewRecoveryState.COMMITTED:
                    receipt = fact.receipt
                    if (type(receipt) is not TeacherReviewAppendReceipt
                            or type(receipt.decision_ref) is not str
                            or type(receipt.original_result_ref) is not str
                            or type(receipt.original_commit_ref) is not str
                            or type(receipt.journal_event_ref) is not str
                            or receipt.decision_ref != decision.decision_ref
                            or receipt.original_result_ref != original.original_cas.transaction.result_ref
                            or receipt.original_commit_ref != original.original_cas.commit_ref):
                        return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
                    _id(receipt.journal_event_ref, self._limit)
                    if _snapshot_owned(request) != original_snapshot:
                        return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
                    return TeacherReviewRecoveryObservation(
                        TeacherReviewRecoveryState.COMMITTED, decision.decision_ref,
                        receipt.journal_event_ref)
                if fact.receipt is not None:
                    return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
                return TeacherReviewRecoveryObservation(fact.state)
            except Exception:
                return TeacherReviewRecoveryObservation(TeacherReviewRecoveryState.UNKNOWN)
        finally:
            self._gate.release()
