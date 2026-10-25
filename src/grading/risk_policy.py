"""Review routing: bounded recommendations, never grading/publication authority.

A policy lookup is an *installed read-only port*. Issuer identity here is
continuity evidence, not authentication. The integration authority must prove
that its installed policy reader is authentic and scoped to the school/tenant.
The presently frozen risk observations are insufficient for AUTO_CANDIDATE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from grading.risk import (
    RISK_OBSERVATION_SCHEMA_VERSION,
    RiskObservation,
    RiskObservationCode,
    RiskObservationSet,
)


REVIEW_RECOMMENDATION_SCHEMA_VERSION = '1'
REVIEW_POLICY_SCHEMA_VERSION = '1'


class RiskPolicyDenied(ValueError):
    """Invalid input shape or impossible policy installation."""


class PolicyFactStatus(str, Enum):
    CURRENT = 'CURRENT'
    REVOKED = 'REVOKED'
    UNKNOWN = 'UNKNOWN'


class PolicyAuthorityState(str, Enum):
    UNVERIFIED_EXTERNAL_AUTHORITY = 'UNVERIFIED_EXTERNAL_AUTHORITY'


class ReviewDisposition(str, Enum):
    DEFERRED = 'DEFERRED'
    HUMAN_REVIEW = 'HUMAN_REVIEW'
    SECOND_CHECK = 'SECOND_CHECK'


class RecommendationReason(str, Enum):
    NO_POSITIVE_ELIGIBILITY = 'NO_POSITIVE_ELIGIBILITY'
    POLICY_UNAVAILABLE = 'POLICY_UNAVAILABLE'
    POLICY_REVOKED = 'POLICY_REVOKED'
    CONFLICTING_RULES = 'CONFLICTING_RULES'
    ADMITTED_OBSERVATIONS = 'ADMITTED_OBSERVATIONS'


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > 256:
        raise RiskPolicyDenied(f'Invalid {name}.')
    return value


def _revision(value: object, name: str) -> int:
    if type(value) is not int or not 1 <= value <= 2**31 - 1:
        raise RiskPolicyDenied(f'Invalid {name}.')
    return value


@dataclass(frozen=True, slots=True)
class PolicyQuery:
    tenant_ref: str
    school_ref: str
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    grading_spec_id: str
    grading_spec_version: int
    observation_schema_version: str


@dataclass(frozen=True, slots=True)
class PolicyRule:
    observation_code: RiskObservationCode
    disposition: ReviewDisposition


@dataclass(frozen=True, slots=True)
class PolicyFact:
    """Issuer-reported *read* result, not a self-authenticating approval."""
    query: PolicyQuery
    issuer_ref: str
    status: PolicyFactStatus
    policy_ref: str | None
    policy_version: int | None
    approval_ref: str | None
    rules: tuple[PolicyRule, ...]
    schema_version: str


@dataclass(frozen=True, slots=True)
class ReviewRecommendation:
    schema_version: str
    query: PolicyQuery
    observations: tuple[RiskObservation, ...]
    disposition: ReviewDisposition
    reason: RecommendationReason
    policy_ref: str | None
    policy_version: int | None
    approval_ref: str | None
    issuer_ref: str | None
    # Exact canonical rule mapping actually evaluated; structural evidence only.
    effective_rules: tuple[PolicyRule, ...] = ()
    authority_state: PolicyAuthorityState = PolicyAuthorityState.UNVERIFIED_EXTERNAL_AUTHORITY


class PolicyReader(Protocol):
    def read_current(self, *, query: PolicyQuery) -> PolicyFact: ...


def _query(value: object) -> PolicyQuery:
    if type(value) is not PolicyQuery:
        raise RiskPolicyDenied('Invalid policy query type.')
    names = ('tenant_ref', 'school_ref', 'grading_run_id', 'submission_ref',
             'exam_ref', 'grading_spec_id')
    strings = tuple(_identifier(getattr(value, name), name) for name in names)
    version = _revision(value.grading_spec_version, 'grading_spec_version')
    if type(value.observation_schema_version) is not str or value.observation_schema_version != RISK_OBSERVATION_SCHEMA_VERSION:
        raise RiskPolicyDenied('Unsupported risk-observation schema.')
    return PolicyQuery(*strings, version, RISK_OBSERVATION_SCHEMA_VERSION)


def _observations(value: object, max_observations: int) -> tuple[RiskObservation, ...]:
    if type(value) is not RiskObservationSet:
        raise RiskPolicyDenied('Invalid observation-set type.')
    if type(value.schema_version) is not str or value.schema_version != RISK_OBSERVATION_SCHEMA_VERSION:
        raise RiskPolicyDenied('Unsupported observation-set schema.')
    _identifier(value.grading_run_id, 'grading_run_id')
    _identifier(value.submission_ref, 'submission_ref')
    if type(value.observations) is not tuple or len(value.observations) > max_observations:
        raise RiskPolicyDenied('Invalid observation inventory.')
    snapshot = []
    seen = set()
    for obs in value.observations:
        if type(obs) is not RiskObservation or type(obs.code) is not RiskObservationCode:
            raise RiskPolicyDenied('Invalid observation type.')
        question_id = _identifier(obs.question_id, 'question_id')
        evidence_id = None if obs.evidence_block_id is None else _identifier(obs.evidence_block_id, 'evidence_block_id')
        criterion_id = None if obs.criterion_id is None else _identifier(obs.criterion_id, 'criterion_id')
        if obs.code is RiskObservationCode.OCR_CONFIDENCE_UNKNOWN:
            if evidence_id is None or criterion_id is not None:
                raise RiskPolicyDenied('Malformed OCR risk observation.')
        elif obs.code is RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED:
            if criterion_id is None or evidence_id is not None:
                raise RiskPolicyDenied('Malformed evaluator risk observation.')
        else:
            raise RiskPolicyDenied('Unsupported observation.')
        item = RiskObservation(obs.code, question_id, evidence_id, criterion_id)
        fingerprint = (item.code, item.question_id, item.evidence_block_id, item.criterion_id)
        if fingerprint in seen:
            raise RiskPolicyDenied('Duplicate risk observation.')
        seen.add(fingerprint)
        snapshot.append(item)
    return tuple(snapshot)


def _fact(value: object, *, query: PolicyQuery, issuer: str) -> tuple[PolicyFactStatus, str | None, int | None, str | None, dict[RiskObservationCode, ReviewDisposition]]:
    if type(value) is not PolicyFact or type(value.status) is not PolicyFactStatus:
        raise RiskPolicyDenied('Invalid policy fact.')
    if type(value.schema_version) is not str or value.schema_version != REVIEW_POLICY_SCHEMA_VERSION:
        raise RiskPolicyDenied('Unsupported policy fact schema.')
    actual_query = _query(value.query)
    if actual_query != query or type(value.issuer_ref) is not str or value.issuer_ref != issuer:
        raise RiskPolicyDenied('Foreign policy fact.')
    if type(value.rules) is not tuple:
        raise RiskPolicyDenied('Invalid policy rules.')
    if value.status is not PolicyFactStatus.CURRENT:
        if any(field is not None for field in (value.policy_ref, value.policy_version, value.approval_ref)) or value.rules:
            raise RiskPolicyDenied('Unapproved noncurrent policy payload.')
        return value.status, None, None, None, {}
    ref = _identifier(value.policy_ref, 'policy_ref')
    version = _revision(value.policy_version, 'policy_version')
    approval = _identifier(value.approval_ref, 'approval_ref')
    rules = {}
    for rule in value.rules:
        if type(rule) is not PolicyRule or type(rule.observation_code) is not RiskObservationCode:
            raise RiskPolicyDenied('Invalid policy rule.')
        if type(rule.disposition) is not ReviewDisposition or rule.disposition is ReviewDisposition.DEFERRED:
            raise RiskPolicyDenied('Policy rule cannot authorize this disposition.')
        if rule.observation_code in rules:
            raise RiskPolicyDenied('Duplicate policy rule.')
        rules[rule.observation_code] = rule.disposition
    if set(rules) != set(RiskObservationCode):
        raise RiskPolicyDenied('Policy must cover every admitted observation code.')
    return value.status, ref, version, approval, rules


class RiskReviewRecommender:
    """Pure recommendation after one installed read. Never AUTO/official/publication."""

    __slots__ = ('_read', '_issuer', '_max_observations')

    def __init__(self, *, reader: PolicyReader, issuer_ref: str, max_observations: int) -> None:
        issuer = _identifier(issuer_ref, 'issuer_ref')
        if type(max_observations) is not int or not 1 <= max_observations <= 10000:
            raise RiskPolicyDenied('Invalid maximum observation count.')
        operation = getattr(reader, 'read_current', None)
        if not callable(operation):
            raise RiskPolicyDenied('Installed policy reader is not callable.')
        object.__setattr__(self, '_read', operation)
        object.__setattr__(self, '_issuer', issuer)
        object.__setattr__(self, '_max_observations', max_observations)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self.__slots__ and hasattr(self, name):
            raise AttributeError('Installed policy reader is immutable.')
        object.__setattr__(self, name, value)

    def recommend(self, *, query: PolicyQuery, observations: RiskObservationSet) -> ReviewRecommendation:
        original_query = _query(query)
        original_obs = _observations(observations, self._max_observations)
        if (original_query.grading_run_id != observations.grading_run_id
                or original_query.submission_ref != observations.submission_ref):
            raise RiskPolicyDenied('Risk observation identity disagrees with policy scope.')

        def result(disposition: ReviewDisposition, reason: RecommendationReason,
                   ref: str | None = None, version: int | None = None,
                   approval: str | None = None,
                   effective_rules: tuple[PolicyRule, ...] = ()) -> ReviewRecommendation:
            return ReviewRecommendation(REVIEW_RECOMMENDATION_SCHEMA_VERSION,
                                        original_query, original_obs, disposition,
                                        reason, ref, version, approval,
                                        self._issuer if ref is not None else None, effective_rules)

        # risk observation covers only two negative signals: no observations is NOT proof
        # of complete examination/readiness, and may NEVER admit auto-accept.
        if not original_obs:
            return result(ReviewDisposition.DEFERRED, RecommendationReason.NO_POSITIVE_ELIGIBILITY)
        try:
            read_query = _query(original_query)
            claimed = self._read(query=read_query)
            # Read-only callbacks may mutate input/output. Preserve the original
            # request and do not consume policy if callback corrupted its input.
            if _query(read_query) != original_query:
                raise RiskPolicyDenied('Policy query changed during lookup.')
            status, ref, version, approval, rules = _fact(claimed, query=original_query, issuer=self._issuer)
        except Exception:
            # No exception text, callback context or invented approved policy.
            return result(ReviewDisposition.DEFERRED, RecommendationReason.POLICY_UNAVAILABLE)
        if status is PolicyFactStatus.REVOKED:
            return result(ReviewDisposition.DEFERRED, RecommendationReason.POLICY_REVOKED)
        if status is PolicyFactStatus.UNKNOWN:
            return result(ReviewDisposition.DEFERRED, RecommendationReason.POLICY_UNAVAILABLE)
        # Freeze a complete, canonical local rule snapshot in the recommendation;
        # external policy approval and revision immutability still require a conforming reader.
        effective_rules = tuple(PolicyRule(code, rules[code]) for code in RiskObservationCode)
        decisions = {rules[obs.code] for obs in original_obs}
        if len(decisions) != 1:
            return result(ReviewDisposition.DEFERRED, RecommendationReason.CONFLICTING_RULES,
                          ref, version, approval, effective_rules)
        return result(next(iter(decisions)), RecommendationReason.ADMITTED_OBSERVATIONS,
                      ref, version, approval, effective_rules)
