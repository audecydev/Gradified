"""result envelope: an honest nonpublishing envelope of *supplied* scoring constituents.

Does not assert that the paper execution integrity evaluator ran, authenticate a school/issuer,
redistribute question-level stage effects to criteria, or publish GradeResult.
Unknown runtime usage/audit information is explicitly UNKNOWN, never zero.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
import math
from copy import deepcopy
from enum import Enum
from decimal import Decimal

from grading.contracts.evidence import (
    AnswerEvidenceBundle, QuestionEvidence, EvidenceBlock, EvidenceLocation,
    EvidenceBlockType, EvidenceBlockState, EvidenceConfidenceStatus,
    EvidenceLocationStatus,
)
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
from grading.contracts.judgment import CriterionJudgment
from grading.verification.evidence import VerifiedCriterionJudgments
from grading.execution import GradingExecutionContext, QuestionExecutionRecord
from grading.contracts.result import (
    CriterionEffect, PaperScoreResult, QuestionScoreResult,
    RubricRef, RuleDecision, ScoreStageEffect, ScoringPolicyRef,
)
from grading.contracts.paper_aggregation import (
    GradingSpecRef, _validate_scoring_decimal_structure, _validate_identifier,
    _validate_grading_spec_ref, _validate_rubric_ref, _validate_scoring_policy_ref,
)
from grading.contracts.numeric_profile import NUMERIC_PROFILE_VERSION
from grading.contracts.result import ScoreStage, RuleType
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import GradingExecutionResult
from grading.numeric_evidence import _revalidate_evidence_graph
from grading.verification.evidence import verify_evaluated_judgments
from grading.scoring.arithmetic import exact_compare, exact_sum, exact_minimum, exact_subtract
from grading.risk import (
    RiskObservation, RiskObservationSet, RiskObservationCode, InvalidRiskObservationInputError,
    extract_risk_observations,
)
from grading.risk_policy import (
    PolicyQuery, ReviewRecommendation, RiskReviewRecommender, RiskPolicyDenied,
    ReviewDisposition, RecommendationReason, PolicyRule, PolicyAuthorityState,
    REVIEW_RECOMMENDATION_SCHEMA_VERSION, _query, _identifier, _revision, _observations,
)


CANDIDATE_CONSTITUENTS_SCHEMA_VERSION = '1'


class CandidateConstituentsDenied(ValueError):
    """Supplied constituent identity, source or risk association is invalid."""


class ConstituentEvidenceState(str, Enum):
    UNKNOWN = 'UNKNOWN'


class CandidateReadiness(str, Enum):
    INCOMPLETE_UNATTESTED_EXECUTION = 'INCOMPLETE_UNATTESTED_EXECUTION'


# Structural budget applies to *untrusted* public second-pass evidence admission constituents before
# Python copying (which can execute user-supplied __deepcopy__ methods).
# It bounds admission work; it is not the source of academic validity.
_MAX_CONSTITUENT_GRAPH_NODES = 200_000
_MAX_CONSTITUENT_COLLECTION_ITEMS = 10_000
_MAX_CONSTITUENT_DEPTH = 64
_MAX_CONSTITUENT_TEXT_CHARS = 1_000_000

# Only exact installed v1 record/enum types may enter the public second-pass evidence admission copy
# boundary. Do NOT inspect foreign class metadata (even through
# type.__getattribute__): hostile metaclass data descriptors can execute.
# Class comparison here must be by identity, never by equality or hashing.
_ADMITTED_CONSTITUENT_TYPES = (
    GradingSpecRef, CriterionEffect, PaperScoreResult, QuestionScoreResult,
    RubricRef, ScoringPolicyRef, ScoreStageEffect, RuleDecision,
    ScoringDecimal, RiskObservation, RiskObservationSet, PolicyQuery,
    PolicyRule, ReviewRecommendation,
    RiskObservationCode, ScoreStage, RuleType, PolicyAuthorityState,
    ReviewDisposition, RecommendationReason,
    # Incoming source types for exact pre-admission traversal. A mutated
    # otherwise-valid record must not reach its validator with a foreign value.
    GradingExecutionResult, GradingExecutionContext, QuestionExecutionRecord,
    AnswerEvidenceBundle, QuestionEvidence, EvidenceBlock, EvidenceLocation,
    EvidenceBlockType, EvidenceBlockState, EvidenceConfidenceStatus,
    EvidenceLocationStatus, EvaluatedCriterionJudgment, EvaluatorMetadata,
    VerifiedCriterionJudgments, CriterionJudgment,
)


def _preflight_owned_graph(value: object) -> None:
    """Admit exact built-in/installed Gradified value types before detaching.

    No arbitrary __deepcopy__, comparison, iterator or user validation methods
    are called on an unadmitted object. Frozen dataclasses do not imply trusted
    inner values, so visit *every* field, including ScoringDecimal internals.

    The iterative post-order walk memoizes each admitted container's maximum
    descendant depth. This checks the longest path through shared DAG nodes
    without either skipping a deeper alias path or repeatedly traversing the
    same subgraph. Cycles are rejected explicitly.
    """
    # Frames are (object, exiting, children). `active` detects cycles, while
    # `heights` memoizes each completed container's maximum edge distance to a
    # leaf. This avoids a visited-set depth bypass for shared subgraphs.
    pending = [(value, False, None)]
    active: set[int] = set()
    heights: dict[int, int] = {}
    count = 0
    while pending:
        item, exiting, children = pending.pop()
        if exiting:
            assert children is not None
            identity = id(item)
            active.remove(identity)
            height = 1 + max((heights.get(id(child), 0) for child in children), default=0)
            if height > _MAX_CONSTITUENT_DEPTH:
                raise CandidateConstituentsDenied('Constituent graph exceeds structural admission budget.')
            heights[identity] = height
            continue

        count += 1
        if count > _MAX_CONSTITUENT_GRAPH_NODES:
            raise CandidateConstituentsDenied('Constituent graph exceeds structural admission budget.')
        kind = type(item)
        # A foreign metaclass may override equality, so `kind in (...)` is
        # itself unsafe before admission; use identity for primitives too.
        if kind is str or kind is int or kind is bool or kind is type(None):
            if kind is str and len(item) > _MAX_CONSTITUENT_TEXT_CHARS:
                raise CandidateConstituentsDenied('Constituent text exceeds structural admission budget.')
            continue
        if kind is float:
            if not math.isfinite(item):
                raise CandidateConstituentsDenied('Invalid constituent number.')
            continue
        if kind is Decimal:
            # Decimal is an exact stdlib immutable value; Profile-v1 numeric
            # validity is subsequently checked by inherited validators.
            continue
        identity = id(item)
        if identity in active:
            raise CandidateConstituentsDenied('Cyclic constituent graph is not admissible.')
        if identity in heights:
            continue
        if kind is tuple:
            if len(item) > _MAX_CONSTITUENT_COLLECTION_ITEMS:
                raise CandidateConstituentsDenied('Constituent tuple exceeds structural admission budget.')
            child_items = item
        else:
            if not any(kind is approved for approved in _ADMITTED_CONSTITUENT_TYPES):
                raise CandidateConstituentsDenied('Foreign constituent object is not admissible.')
            if isinstance(item, Enum):
                # Exact installed Enum class. Do not accept caller-defined subclasses
                # or enum lookalikes with equality/name side effects.
                continue
            if not is_dataclass(kind):
                raise CandidateConstituentsDenied('Unsupported constituent object type.')
            members = fields(kind)
            if len(members) > _MAX_CONSTITUENT_COLLECTION_ITEMS:
                raise CandidateConstituentsDenied('Constituent record exceeds structural admission budget.')
            child_items = tuple(object.__getattribute__(item, member.name) for member in members)
        active.add(identity)
        pending.append((item, True, child_items))
        pending.extend((child, False, None) for child in child_items)


@dataclass(frozen=True, slots=True)
class CandidateResultConstituents:
    schema_version: str
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    grading_spec_id: str
    grading_spec_version: int
    question_scores: tuple[QuestionScoreResult, ...]
    paper_score: PaperScoreResult
    risk_observations: RiskObservationSet
    review_recommendation: ReviewRecommendation
    usage_evidence_state: ConstituentEvidenceState
    audit_evidence_state: ConstituentEvidenceState
    readiness: CandidateReadiness
    official_result: bool

    def __post_init__(self) -> None:
        # Detach caller-owned, mutable-shaped nested records as one graph, so
        # aliases between paper/question views survive the copy without
        # retaining external objects. frozen=True alone is not deep ownership.
        detached_ok = True
        try:
            source = (self.question_scores, self.paper_score,
                      self.risk_observations, self.review_recommendation)
            _preflight_owned_graph(source)
            detached = deepcopy(source)
            for name, value in zip(('question_scores', 'paper_score',
                                    'risk_observations', 'review_recommendation'), detached):
                object.__setattr__(self, name, value)
        except Exception:
            detached_ok = False
        if not detached_ok:
            raise CandidateConstituentsDenied('Cannot own nonofficial constituent graph.')
        # Public construction never leaks a nested source exception or its
        # potentially confidential __context__ to integration consumers.
        invalid = False
        try:
            self._validate_constituents()
        except (CandidateConstituentsDenied, TypeError, ValueError, AttributeError,
                ArithmeticError, OverflowError, RecursionError):
            invalid = True
        if invalid:
            raise CandidateConstituentsDenied('Invalid nonofficial constituent graph.') from None

    def validated_snapshot(self) -> 'CandidateResultConstituents':
        """Return a separately owned and re-admitted snapshot at consumption.

        This structural check grants no execution, issuer, school or publication
        authority. Consumers must not trust an earlier validation after a graph
        has been returned to code able to bypass frozen dataclass protections.
        """
        invalid = False
        try:
            copy = replace(self)
        except Exception:
            invalid = True
        if invalid:
            raise CandidateConstituentsDenied('Cannot consume invalid constituent graph.')
        return copy

    def _validate_constituents(self) -> None:
        if type(self.schema_version) is not str or self.schema_version != CANDIDATE_CONSTITUENTS_SCHEMA_VERSION:
            raise CandidateConstituentsDenied('Unsupported candidate schema.')
        try:
            for name in ('grading_run_id', 'submission_ref', 'exam_ref', 'grading_spec_id'):
                _identifier(getattr(self, name), name)
            _revision(self.grading_spec_version, 'grading_spec_version')
        except RiskPolicyDenied:
            raise CandidateConstituentsDenied('Invalid candidate identity.') from None
        if (type(self.question_scores) is not tuple
                or any(type(q) is not QuestionScoreResult for q in self.question_scores)
                or type(self.paper_score) is not PaperScoreResult):
            raise CandidateConstituentsDenied('Invalid numerical constituent inventory.')
        # Re-admit BOTH public score representations before equality. An exact
        # frozen dataclass can still have been corrupted through a callback.
        _readmit_paper_score(self.paper_score)
        if not self.question_scores:
            raise CandidateConstituentsDenied('Successful paper has no question scores.')
        for score in self.question_scores:
            _readmit_question_score(score)
        if self.question_scores != self.paper_score.question_results:
            raise CandidateConstituentsDenied('Question scores disagree with paper score.')
        paper_spec = self.paper_score.grading_spec_ref
        if (type(paper_spec) is not GradingSpecRef or type(paper_spec.id) is not str
                or type(paper_spec.version) is not int
                or paper_spec.id != self.grading_spec_id
                or paper_spec.version != self.grading_spec_version):
            raise CandidateConstituentsDenied('Paper grading specification disagrees with candidate.')
        if (type(self.risk_observations) is not RiskObservationSet
                or type(self.review_recommendation) is not ReviewRecommendation):
            raise CandidateConstituentsDenied('Invalid recommendation constituents.')
        try:
            risk = _observations(self.risk_observations, 10000)
            review_query = _query(self.review_recommendation.query)
            # The recommendation carries a second copy of the observations.
            # Its tuple and EVERY nested field require independent admission
            # before invoking structural equality with the risk-set snapshot.
            reviewed = RiskObservationSet(
                self.risk_observations.schema_version,
                self.grading_run_id, self.submission_ref,
                self.review_recommendation.observations,
            )
            review_observations = _observations(reviewed, 10000)
        except (RiskPolicyDenied, InvalidRiskObservationInputError):
            raise CandidateConstituentsDenied('Invalid risk/recommendation inputs.') from None
        if (self.risk_observations.grading_run_id != self.grading_run_id
                or self.risk_observations.submission_ref != self.submission_ref
                or review_query.grading_run_id != self.grading_run_id
                or review_query.submission_ref != self.submission_ref
                or review_query.exam_ref != self.exam_ref
                or review_query.grading_spec_id != self.grading_spec_id
                or review_query.grading_spec_version != self.grading_spec_version
                or review_observations != risk):
            raise CandidateConstituentsDenied('Invalid risk/result continuity.')
        score_ids = set()
        scores_by_id = {}
        for score in self.question_scores:
            try:
                question_id = _identifier(score.question_id, 'scored_question_id')
            except RiskPolicyDenied:
                raise CandidateConstituentsDenied('Invalid scored question identity.') from None
            if question_id in score_ids:
                raise CandidateConstituentsDenied('Duplicate scored question identity.')
            score_ids.add(question_id)
            scores_by_id[question_id] = score
        for item in risk:
            if item.question_id not in score_ids:
                raise CandidateConstituentsDenied('Risk observation refers to an unscored question.')
            if (item.code is RiskObservationCode.EVALUATOR_UNCERTAINTY_REPORTED
                    and item.criterion_id not in {effect.criterion_id
                        for effect in scores_by_id[item.question_id].criterion_effects}):
                raise CandidateConstituentsDenied('Risk observation refers to an unscored criterion.')
        _validate_review_metadata(self.review_recommendation, risk)
        if (self.usage_evidence_state is not ConstituentEvidenceState.UNKNOWN
                or self.audit_evidence_state is not ConstituentEvidenceState.UNKNOWN
                or self.readiness is not CandidateReadiness.INCOMPLETE_UNATTESTED_EXECUTION
                or self.official_result is not False):
            raise CandidateConstituentsDenied('This source cannot authorize official or complete results.')



def _readmit_amount(amount: object) -> None:
    # Reuse the inherited Numeric Profile v1 canonical/finite envelope, not
    # a second arithmetic validator. A mutated ScoringDecimal._value is not
    # made safe merely by the outer ScoringDecimal type.
    _validate_scoring_decimal_structure(
        amount, field_name='question score amount', error_type=CandidateConstituentsDenied,
    )


def _canonical_id(value: object, name: str) -> None:
    _validate_identifier(value, field_name=name, error_type=CandidateConstituentsDenied)


def _score_within_bounds(minimum: ScoringDecimal, score: ScoringDecimal,
                         maximum: ScoringDecimal) -> None:
    if (exact_compare(minimum, maximum) > 0
            or exact_compare(score, minimum) < 0
            or exact_compare(score, maximum) > 0):
        raise CandidateConstituentsDenied('Numerical score outside its declared bounds.')


def _readmit_question_score(score: QuestionScoreResult) -> None:
    if type(score) is not QuestionScoreResult:
        raise CandidateConstituentsDenied('Invalid question score type.')
    try:
        replace(score)  # Inherited criterion scoring structural post-init.
        _canonical_id(score.question_id, 'question score question_id')
        if score.numeric_profile_version != NUMERIC_PROFILE_VERSION:
            raise CandidateConstituentsDenied('Unsupported question numeric profile.')
        _validate_rubric_ref(score.rubric_ref, field_name='question score rubric reference',
                             error_type=CandidateConstituentsDenied)
        _validate_scoring_policy_ref(score.scoring_policy_ref, field_name='question score scoring-policy reference',
                                     error_type=CandidateConstituentsDenied,
                                     require_supported_semantics=True)
        for amount in (score.base_subtotal, score.score_before_rounding,
                       score.final_score, score.minimum_score, score.maximum_score):
            _readmit_amount(amount)
        _score_within_bounds(score.minimum_score, score.final_score, score.maximum_score)
        # A successful criterion scoring result originates from a rubric with at least one
        # criterion; an empty collection is not valid merely because zero sums.
        if not score.criterion_effects:
            raise CandidateConstituentsDenied('Successful question has no criterion effects.')
        for effect in score.criterion_effects:
            replace(effect)
            _canonical_id(effect.criterion_id, 'question score criterion_id')
            _canonical_id(effect.selected_level, 'question score selected_level')
            for rule_id in effect.blocking_dependency_rule_ids:
                _canonical_id(rule_id, 'question score dependency rule_id')
            _readmit_amount(effect.base_contribution)
            _readmit_amount(effect.effective_contribution)
        for decision in score.rule_decisions:
            replace(decision)
            _canonical_id(decision.rule_id, 'question score decision rule_id')
            if decision.configured_effect is not None:
                _readmit_amount(decision.configured_effect)
        for effect in score.stage_effects:
            replace(effect)
            for rule_id in effect.source_rule_ids:
                _canonical_id(rule_id, 'question score stage rule_id')
            _readmit_amount(effect.before)
            _readmit_amount(effect.after)
        # Enforce finite output-provenance invariants of the *accepted reducer*.
        # This does not decide whether a configured academic rule should fire;
        # it checks that the reported effects could have come from the recorded
        # decisions. Stage ordering is defined by frozen criterion scoring, not by second-pass evidence admission.
        if tuple(item.stage for item in score.stage_effects) != tuple(ScoreStage):
            raise CandidateConstituentsDenied('Invalid stage inventory.')
        ids = tuple(item.criterion_id for item in score.criterion_effects)
        if len(ids) != len(set(ids)):
            raise CandidateConstituentsDenied('Repeated criterion effect.')
        rule_ids = tuple(item.rule_id for item in score.rule_decisions)
        if (len(rule_ids) != len(set(rule_ids)) or rule_ids != tuple(sorted(rule_ids))):
            raise CandidateConstituentsDenied('Repeated or uncanonical rule decision.')
        for decision in score.rule_decisions:
            if ((decision.rule_type is RuleType.DEPENDENCY and decision.configured_effect is not None)
                    or (decision.rule_type is not RuleType.DEPENDENCY
                        and decision.configured_effect is None)):
                raise CandidateConstituentsDenied('Impossible rule-effect provenance.')
            # The frozen QuestionScoringPolicy enforces configured constraints
            # for every rule, even when the rule did not trigger this time.
            configured = decision.configured_effect
            if decision.rule_type is RuleType.DEDUCTION:
                if exact_compare(configured, ScoringDecimal.from_raw('0')) <= 0:
                    raise CandidateConstituentsDenied('Nonpositive configured deduction.')
            elif decision.rule_type in (RuleType.GATE, RuleType.CAP):
                _score_within_bounds(score.minimum_score, configured, score.maximum_score)
        triggered_dependencies = {decision.rule_id for decision in score.rule_decisions
                                  if decision.rule_type is RuleType.DEPENDENCY and decision.triggered}
        # criterion scoring records each triggered rule on exactly one target criterion,
        # even when the target's selected credit is zero or negative. A
        # one-way subset check incorrectly admitted orphan and multi-target
        # rule provenance without affecting numerical sums.
        blocker_owners = {rule_id: 0 for rule_id in triggered_dependencies}
        for item in score.criterion_effects:
            blockers = item.blocking_dependency_rule_ids
            if (len(blockers) != len(set(blockers)) or blockers != tuple(sorted(blockers))
                    or not set(blockers).issubset(triggered_dependencies)):
                raise CandidateConstituentsDenied('Invalid dependency blocker provenance.')
            # The reducer zeroes a blocked *positive* contribution; it never
            # creates marks by redistributing the blocked contribution.
            zero = ScoringDecimal.from_raw('0')
            effective = (zero if blockers and exact_compare(item.base_contribution, zero) > 0
                         else item.base_contribution)
            if item.effective_contribution != effective:
                raise CandidateConstituentsDenied('Blocked criterion amount is inconsistent.')
            for rule_id in blockers:
                blocker_owners[rule_id] += 1
        if any(owners != 1 for owners in blocker_owners.values()):
            raise CandidateConstituentsDenied('Triggered dependency has no unique criterion target.')
        stage_types = ((ScoreStage.GATES, RuleType.GATE),
                       (ScoreStage.CAPS, RuleType.CAP),
                       (ScoreStage.DEDUCTIONS, RuleType.DEDUCTION))
        for stage, kind in stage_types:
            effect = next(item for item in score.stage_effects if item.stage is stage)
            expected = tuple(sorted(decision.rule_id for decision in score.rule_decisions
                                    if decision.rule_type is kind and decision.triggered))
            if effect.source_rule_ids != expected:
                raise CandidateConstituentsDenied('Stage provenance contradicts rule decisions.')
        for stage in score.stage_effects:
            if (len(stage.source_rule_ids) != len(set(stage.source_rule_ids))
                    or stage.source_rule_ids != tuple(sorted(stage.source_rule_ids))):
                raise CandidateConstituentsDenied('Duplicate or unordered stage source.')
        rounding_stage = score.stage_effects[-1]
        if len(rounding_stage.source_rule_ids) > 1:
            raise CandidateConstituentsDenied('Invalid rounding provenance.')
        if rounding_stage.source_rule_ids:
            if rounding_stage.source_rule_ids[0] in rule_ids:
                raise CandidateConstituentsDenied('Rounding rule duplicates a conditional rule.')
        elif rounding_stage.before != rounding_stage.after:
            # The frozen criterion scoring reducer leaves the number unchanged if no
            # rounding policy was admitted; no new rounding semantics here.
            raise CandidateConstituentsDenied('Unruled rounding changed the score.')
        # Numeric effects must agree with the reported decisions, without
        # re-evaluating any academic condition or the rounding policy.
        for stage, kind in stage_types:
            effect = next(item for item in score.stage_effects if item.stage is stage)
            decisions = tuple(dec for dec in score.rule_decisions
                              if dec.rule_type is kind and dec.triggered)
            if any(dec.configured_effect is None for dec in decisions):
                raise CandidateConstituentsDenied('Missing triggered numerical rule effect.')
            if kind is RuleType.DEDUCTION:
                computed = exact_subtract(effect.before,
                    exact_sum(tuple(dec.configured_effect for dec in decisions))) if decisions else effect.before
            else:
                computed = effect.before
                for decision in decisions:
                    computed = exact_minimum(computed, decision.configured_effect)
            if computed != effect.after:
                raise CandidateConstituentsDenied('Stage amount contradicts reported rules.')
        # Check frozen criterion scoring stage-lineage relationships, not the grading rules.
        # Recomputing which rules *should* trigger would require the original
        # approved rubric/policy and belongs to the accepted scoring kernel.
        stages = score.stage_effects
        if (tuple(item.stage for item in stages) != tuple(ScoreStage)
                or stages[0].before != score.base_subtotal
                or any(left.after != right.before for left, right in zip(stages, stages[1:]))
                or stages[2].after != score.score_before_rounding
                or stages[-1].after != score.final_score
                or exact_sum(tuple(effect.effective_contribution
                                   for effect in score.criterion_effects)) != score.base_subtotal):
            raise CandidateConstituentsDenied('Inconsistent question score stage lineage.')
    except (TypeError, ValueError, AttributeError, ArithmeticError, OverflowError, RecursionError):
        raise CandidateConstituentsDenied('Invalid nested question score.') from None


def _readmit_paper_score(paper: PaperScoreResult) -> None:
    if type(paper) is not PaperScoreResult:
        raise CandidateConstituentsDenied('Invalid paper score type.')
    try:
        replace(paper)  # Inherited scoring aggregation structural post-init.
        _validate_grading_spec_ref(paper.grading_spec_ref, field_name='paper score grading-spec reference',
                                   error_type=CandidateConstituentsDenied)
        for amount in (paper.final_score, paper.minimum_score, paper.maximum_score):
            _readmit_amount(amount)
        if paper.numeric_profile_version != NUMERIC_PROFILE_VERSION:
            raise CandidateConstituentsDenied('Unsupported paper numeric profile.')
        # scoring aggregation only aggregates a resolved, nonempty expected-question set.
        if not paper.question_results:
            raise CandidateConstituentsDenied('Successful paper has no questions.')
        _score_within_bounds(paper.minimum_score, paper.final_score, paper.maximum_score)
        for score in paper.question_results:
            _readmit_question_score(score)
        if exact_sum(tuple(q.final_score for q in paper.question_results)) != paper.final_score:
            raise CandidateConstituentsDenied('Paper score does not equal its question sum.')
    except (TypeError, ValueError, AttributeError, ArithmeticError, OverflowError, RecursionError):
        raise CandidateConstituentsDenied('Invalid nested paper score.') from None


def _validate_review_metadata(review: ReviewRecommendation, risk: tuple) -> None:
    if (review.authority_state is not PolicyAuthorityState.UNVERIFIED_EXTERNAL_AUTHORITY
            or type(review.schema_version) is not str
            or review.schema_version != REVIEW_RECOMMENDATION_SCHEMA_VERSION
            or type(review.disposition) is not ReviewDisposition
            or type(review.reason) is not RecommendationReason):
        raise CandidateConstituentsDenied('Invalid review disposition or schema.')
    refs = (review.policy_ref, review.approval_ref, review.issuer_ref)
    policy_present = review.policy_ref is not None
    try:
        if policy_present:
            for name, item in zip(('policy_ref', 'approval_ref', 'issuer_ref'), refs):
                _identifier(item, name)
            _revision(review.policy_version, 'policy_version')
        elif (review.policy_version is not None or review.approval_ref is not None
                or review.issuer_ref is not None):
            raise CandidateConstituentsDenied('Partial policy provenance is forbidden.')
    except RiskPolicyDenied:
        raise CandidateConstituentsDenied('Invalid policy provenance.') from None
    rules = review.effective_rules
    if type(rules) is not tuple:
        raise CandidateConstituentsDenied('Invalid effective policy snapshot.')
    if policy_present:
        # This is a reproducible local *mapping*, not proof that the issuer
        # was authenticated, approved, or durably current.
        if (len(rules) != len(tuple(RiskObservationCode))
                or any(type(rule) is not PolicyRule
                       or type(rule.observation_code) is not RiskObservationCode
                       for rule in rules)):
            raise CandidateConstituentsDenied('Incomplete effective policy snapshot.')
        if (tuple(rule.observation_code for rule in rules) != tuple(RiskObservationCode)
                or any(type(rule.disposition) is not ReviewDisposition
                       or rule.disposition is ReviewDisposition.DEFERRED for rule in rules)):
            raise CandidateConstituentsDenied('Invalid effective policy mapping.')
    elif rules:
        raise CandidateConstituentsDenied('Unauthored policy snapshot.')
    if review.reason is RecommendationReason.ADMITTED_OBSERVATIONS:
        if (not risk or not policy_present
                or review.disposition not in (ReviewDisposition.HUMAN_REVIEW, ReviewDisposition.SECOND_CHECK)):
            raise CandidateConstituentsDenied('Invalid admitted review recommendation.')
        assignments = dict((rule.observation_code, rule.disposition) for rule in rules)
        if any(assignments[item.code] is not review.disposition for item in risk):
            raise CandidateConstituentsDenied('Recommendation differs from its policy mapping.')
    elif review.reason is RecommendationReason.CONFLICTING_RULES:
        if (not risk or not policy_present or review.disposition is not ReviewDisposition.DEFERRED
                or len({rule.disposition for rule in rules if any(obs.code is rule.observation_code for obs in risk)}) < 2):
            raise CandidateConstituentsDenied('False policy conflict.')
    elif review.reason is RecommendationReason.NO_POSITIVE_ELIGIBILITY:
        if risk or policy_present or review.disposition is not ReviewDisposition.DEFERRED:
            raise CandidateConstituentsDenied('Invalid missing-eligibility outcome.')
    elif review.reason in (RecommendationReason.POLICY_UNAVAILABLE,
                           RecommendationReason.POLICY_REVOKED):
        if not risk or policy_present or review.disposition is not ReviewDisposition.DEFERRED:
            raise CandidateConstituentsDenied('Invalid unavailable-policy outcome.')
    else:
        raise CandidateConstituentsDenied('Unsupported recommendation reason.')


def _detached_signature(value: object) -> object:
    """Exact primitive signature; no equality method on caller-supplied wrappers."""
    kind = type(value)
    if kind is str or kind is int or kind is bool or kind is type(None):
        return (kind, value)
    if type(value) is float and math.isfinite(value):
        return ('float', value.hex())
    if type(value) is ScoringDecimal:
        _readmit_amount(value)
        return ('ScoringDecimal', value.to_canonical_string())
    if type(value) is tuple:
        return tuple(_detached_signature(item) for item in value)
    if isinstance(value, Enum):
        return (type(value), value.name)
    if is_dataclass(value) and type(value).__module__.startswith('grading.'):
        return (type(value), tuple((field.name, _detached_signature(getattr(value, field.name)))
                                               for field in fields(value)))
    raise CandidateConstituentsDenied('Unsupported numerical or provenance constituent.')


def _readmit_execution_and_evidence(execution: GradingExecutionResult,
                                   evidence: AnswerEvidenceBundle) -> None:
    """Re-admit supplied scoring/Evidence facts; does not attest their issuer."""
    # Reject foreign objects on BOTH supplied graphs before any nested
    # constructor/readmission can evaluate user-defined metaclass equality,
    # descriptors, coercions, or copy hooks. Exact-type checks are identity-only.
    _preflight_owned_graph((execution, evidence))
    _revalidate_evidence_graph(evidence)
    replace(execution)
    if execution.context.submission_ref != evidence.submission_ref:
        raise CandidateConstituentsDenied('Execution/evidence submission disagreement.')
    replace(execution.context)
    _validate_grading_spec_ref(execution.context.grading_spec_ref,
                               field_name='execution grading-spec reference',
                               error_type=CandidateConstituentsDenied)
    _readmit_paper_score(execution.paper_score)
    paper_by_id = {item.question_id: item for item in execution.paper_score.question_results}
    if (len(paper_by_id) != len(execution.paper_score.question_results)
            or len(execution.questions) != len(paper_by_id)):
        raise CandidateConstituentsDenied('Execution/question score inventory mismatch.')
    seen = set()
    for record in execution.questions:
        replace(record)
        verified = record.verified
        replace(verified)
        _readmit_question_score(record.score)
        qid = record.score.question_id
        if (qid in seen or qid not in paper_by_id
                or record.score != paper_by_id[qid]
                or verified.submission_ref != evidence.submission_ref
                or verified.question_id != qid):
            raise CandidateConstituentsDenied('Execution/verified/paper question mismatch.')
        seen.add(qid)
        for evaluated in verified.evaluated_judgments:
            replace(evaluated)
            replace(evaluated.evaluator_metadata)
            for evidence_ref in evaluated.evidence_refs:
                _canonical_id(evidence_ref, 'verified judgment evidence_ref')
        for scoring in verified.scoring_judgments:
            replace(scoring)
        # Reuse accepted deterministic scoring to validate actual evidence block ownership, state
        # and projection; typed IDs alone cannot establish verification.
        rebuilt = verify_evaluated_judgments(
            evidence=evidence, question_id=qid,
            judgments=verified.evaluated_judgments,
        )
        if rebuilt != verified:
            raise CandidateConstituentsDenied('Scoring projection disagrees with evidence verification evidence.')
        if (len(record.score.criterion_effects) != len(verified.scoring_judgments)
                or {(item.criterion_id, item.selected_level)
                    for item in record.score.criterion_effects}
                   != {(item.criterion_id, item.selected_level)
                       for item in verified.scoring_judgments}):
            raise CandidateConstituentsDenied('Scored criteria contradict verified judgments.')


def compose_nonpublishing_constituents(
    *,
    execution: GradingExecutionResult,
    evidence: AnswerEvidenceBundle,
    policy_query: PolicyQuery,
    recommender: RiskReviewRecommender,
) -> CandidateResultConstituents:
    """Bind accepted scoring and risk observation data; return incomplete/no publish status.

    scoring accepts supplied judgments; this function does not certify that the
    installed paper execution integrity evaluator actually emitted them. When paper execution integrity becomes available,
    its actual execution receipt must gate any promotion of this envelope.
    """
    invalid = False
    try:
        return _compose_admitted_constituents(
            execution=execution, evidence=evidence,
            policy_query=policy_query, recommender=recommender,
        )
    except (CandidateConstituentsDenied, RiskPolicyDenied,
            InvalidRiskObservationInputError, ValueError, TypeError,
            AttributeError, OverflowError, ArithmeticError, RecursionError):
        invalid = True
    if invalid:
        raise CandidateConstituentsDenied('Cannot admit nonofficial candidate inputs.')


def _compose_admitted_constituents(*, execution: GradingExecutionResult,
                                   evidence: AnswerEvidenceBundle,
                                   policy_query: PolicyQuery,
                                   recommender: RiskReviewRecommender) -> CandidateResultConstituents:
    if type(execution) is not GradingExecutionResult or type(evidence) is not AnswerEvidenceBundle:
        raise CandidateConstituentsDenied('Invalid execution or evidence type.')
    if type(policy_query) is not PolicyQuery or type(recommender) is not RiskReviewRecommender:
        raise CandidateConstituentsDenied('Invalid policy query or recommender type.')
    try:
        admitted_query = _query(policy_query)
        _readmit_execution_and_evidence(execution, evidence)
        prior_execution_signature = _detached_signature(execution)
        prior_evidence_signature = _detached_signature(evidence)
    except (RiskPolicyDenied, CandidateConstituentsDenied, TypeError, ValueError,
            AttributeError, OverflowError, ArithmeticError, RecursionError):
        raise CandidateConstituentsDenied('Cannot admit candidate and policy identities.') from None
    context = execution.context
    spec = context.grading_spec_ref
    paper_spec = execution.paper_score.grading_spec_ref
    if (type(paper_spec) is not GradingSpecRef or type(paper_spec.id) is not str
            or type(paper_spec.version) is not int
            or paper_spec.id != spec.id or paper_spec.version != spec.version):
        raise CandidateConstituentsDenied('Paper scoring specification disagrees with execution.')
    if (admitted_query.grading_run_id != context.grading_run_id
            or admitted_query.submission_ref != context.submission_ref
            or admitted_query.exam_ref != context.exam_ref
            or admitted_query.grading_spec_id != spec.id
            or admitted_query.grading_spec_version != spec.version):
        raise CandidateConstituentsDenied('Policy query does not match supplied execution.')
    try:
        observations = extract_risk_observations(execution=execution, evidence=evidence)
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise CandidateConstituentsDenied('Cannot bind execution to evidence.') from None
    # A candidate need not imply that its grading execution was a physically
    # installed run: this is only a detached, nonofficial constituent envelope.
    try:
        snapshot = deepcopy(execution.paper_score)
        original_scores = snapshot.question_results
    except (TypeError, ValueError, AttributeError, RecursionError):
        raise CandidateConstituentsDenied('Cannot snapshot supplied numerical constituents.') from None
    recommendation = recommender.recommend(query=admitted_query, observations=observations)
    # Policy-reader contact may mutate any supplied nested source. All source
    # validation must be repeated before consuming its returned recommendation.
    _readmit_execution_and_evidence(execution, evidence)
    if (type(recommendation) is not ReviewRecommendation
            or recommendation.query != admitted_query
            or recommendation.observations != observations.observations):
        raise CandidateConstituentsDenied('Review recommendation changed scope.')
    # If a callback mutated the supplied source graph, do not publish any of
    # its potentially inconsistent identities or numerical constituents.
    try:
        after = extract_risk_observations(execution=execution, evidence=evidence)
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise CandidateConstituentsDenied('Execution changed during policy lookup.') from None
    try:
        source_changed = (_detached_signature(execution) != prior_execution_signature
                          or _detached_signature(evidence) != prior_evidence_signature)
    except (TypeError, ValueError, AttributeError, OverflowError,
            ArithmeticError, RecursionError):
        raise CandidateConstituentsDenied('Execution changed during policy lookup.') from None
    if after != observations or source_changed:
        raise CandidateConstituentsDenied('Execution changed during policy lookup.')
    return CandidateResultConstituents(
        schema_version=CANDIDATE_CONSTITUENTS_SCHEMA_VERSION,
        grading_run_id=context.grading_run_id,
        submission_ref=context.submission_ref,
        exam_ref=context.exam_ref,
        grading_spec_id=spec.id,
        grading_spec_version=spec.version,
        question_scores=original_scores,
        paper_score=snapshot,
        risk_observations=observations,
        review_recommendation=recommendation,
        usage_evidence_state=ConstituentEvidenceState.UNKNOWN,
        audit_evidence_state=ConstituentEvidenceState.UNKNOWN,
        readiness=CandidateReadiness.INCOMPLETE_UNATTESTED_EXECUTION,
        official_result=False,
    )
