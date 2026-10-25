"""Fail-closed grading-engine disposition for independently issued review evidence.

This is a recommendation/hold mechanism, not a publication or grading authority.
School identity, approval and durability remain obligations of the installed source.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResultDisposition(str, Enum):
    REVIEW = 'REVIEW'
    UNKNOWN = 'UNKNOWN'
    ACCEPTED_FOR_GOVERNED_HANDOFF = 'ACCEPTED_FOR_GOVERNED_HANDOFF'


@dataclass(frozen=True, slots=True)
class GovernedResultEvidence:
    tenant_ref: str
    grading_run_id: str
    original_scored_result_ref: str
    policy_ref: str
    policy_revision: str
    source_revision: str
    # These are strictly source-attested facts, not confidence probabilities.
    academic_evidence_complete: bool | None
    scoring_record_current: bool | None
    reviewer_decision_current: bool | None
    adverse_flags_cleared: bool | None


@dataclass(frozen=True, slots=True)
class GovernedResultDecision:
    disposition: ResultDisposition
    tenant_ref: str
    grading_run_id: str
    source_revision: str
    original_scored_result_ref: str
    policy_ref: str
    policy_revision: str
    reason_codes: tuple[str, ...]

    @property
    def authorizes_publication(self) -> bool:
        return False

    @property
    def authorizes_retry(self) -> bool:
        return False


class GovernedResultDisposition:
    """A bounded versioned mechanism with no guessed calibration thresholds."""
    __slots__ = ('_limit',)

    def __init__(self, *, max_identifier_characters: int):
        if type(max_identifier_characters) is not int or not 0 < max_identifier_characters <= 4096:
            raise ValueError('Bounded identifier length required.')
        object.__setattr__(self, '_limit', max_identifier_characters)

    def __setattr__(self, name, value):
        raise AttributeError('Disposition installation is immutable.')

    def evaluate(self, *, evidence: GovernedResultEvidence) -> GovernedResultDecision:
        if type(evidence) is not GovernedResultEvidence:
            raise ValueError('Exact governed evidence required.')
        refs = (evidence.tenant_ref, evidence.grading_run_id,
                evidence.original_scored_result_ref, evidence.policy_ref,
                evidence.policy_revision, evidence.source_revision)
        if any(type(x) is not str or not x or x != x.strip() or len(x) > self._limit for x in refs):
            raise ValueError('Complete bounded evidence identity required.')
        facts = (evidence.academic_evidence_complete, evidence.scoring_record_current,
                 evidence.reviewer_decision_current, evidence.adverse_flags_cleared)
        if any(x is not None and type(x) is not bool for x in facts):
            raise ValueError('Only source-attested ternary facts admitted.')
        reasons = tuple(name for name, fact in zip((
            'ACADEMIC_EVIDENCE', 'SCORING_RECORD', 'REVIEWER_DECISION', 'ADVERSE_FLAGS'), facts)
            if fact is not True)
        if any(x is None for x in facts):
            state = ResultDisposition.UNKNOWN
        elif not all(facts):
            state = ResultDisposition.REVIEW
        else:
            state = ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
        return GovernedResultDecision(state, evidence.tenant_ref, evidence.grading_run_id,
                                      evidence.source_revision, evidence.original_scored_result_ref,
                                      evidence.policy_ref, evidence.policy_revision, reasons)
