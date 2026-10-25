from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import import_module

import pytest

from grading.active_question_authority import (
    ContextPolicy,
    ResolvedQuestionAuthority,
    resolve_active_question_authority,
)
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult,
    GradingSpecRef,
    ResolvedPaperScoringAuthority,
)
from grading.contracts.policy import SCORING_SEMANTICS_V1
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.fingerprint import (
    authoring_content_fingerprint,
    compiled_authority_fingerprint,
    finalized_question_fingerprint,
)
from grading.rubric.lifecycle import (
    RubricAuthoringVersion,
    activate_version,
    approve_version,
    create_initial_version,
    validate_version,
)
from grading.rubric.models import FinalizedQuestionScoringBasis
from tests.support.rubric_authoring import authoring_test_limits, simple_basis, simple_content


def _contract():
    return import_module("grading.contracts.numeric_authority")


def _resolver_module():
    return import_module("grading.numeric_authority")


@dataclass(frozen=True, slots=True)
class _SelectedActiveQuestion:
    grading_spec_ref: GradingSpecRef
    question_id: str
    question_text: str
    context_policy: ContextPolicy
    active_rubric: RubricAuthoringVersion


class _ActiveSource:
    def __init__(self, selected: _SelectedActiveQuestion) -> None:
        self.selected = selected

    def resolve_active_question(self, *, grading_spec_ref: GradingSpecRef, question_id: str):
        return self.selected


class _BindingSource:
    def __init__(self, binding: object) -> None:
        self.binding = binding
        self.calls: list[tuple[GradingSpecRef, str]] = []

    def resolve_numeric_binding(self, *, grading_spec_ref: GradingSpecRef, question_id: str):
        self.calls.append((grading_spec_ref, question_id))
        return self.binding


@dataclass(frozen=True, slots=True)
class _Materialized:
    authority: object
    approval: object


class _AuthoritySource:
    def __init__(self, materialized: object) -> None:
        self.materialized = materialized
        self.calls: list[str] = []

    def materialize_numeric_authority(self, *, authority_fingerprint: str):
        self.calls.append(authority_fingerprint)
        return self.materialized


class _ExplodingBindingSource:
    def resolve_numeric_binding(self, *, grading_spec_ref: GradingSpecRef, question_id: str):
        raise RuntimeError("binding backend exploded")


class _ExplodingAuthoritySource:
    def materialize_numeric_authority(self, *, authority_fingerprint: str):
        raise RuntimeError("authority backend exploded")


def _active_version() -> RubricAuthoringVersion:
    limits = authoring_test_limits()
    draft = create_initial_version(simple_basis(), simple_content())
    validated = validate_version(draft, limits=limits)
    approved = approve_version(validated, teacher_ref="teacher:n1-red")
    return activate_version(approved, limits=limits)


def _paper() -> ResolvedPaperScoringAuthority:
    return ResolvedPaperScoringAuthority(
        grading_spec_ref=GradingSpecRef("SPEC-1", 1),
        expected_questions=(
            ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=RubricRef("R-Q1", 1),
                scoring_policy_ref=ScoringPolicyRef(
                    "P-Q1",
                    1,
                    SCORING_SEMANTICS_V1,
                ),
            ),
        ),
        minimum_score=ScoringDecimal.from_raw("0"),
        maximum_score=ScoringDecimal.from_raw("5"),
    )


def _resolved_active() -> ResolvedQuestionAuthority:
    active = _active_version()
    paper = _paper()
    return resolve_active_question_authority(
        paper_authority=paper,
        question_id="Q1",
        source=_ActiveSource(
            _SelectedActiveQuestion(
                grading_spec_ref=paper.grading_spec_ref,
                question_id="Q1",
                question_text="Return the final scalar result.",
                context_policy=ContextPolicy.DIRECT,
                active_rubric=active,
            )
        ),
    )


def _authority(active: ResolvedQuestionAuthority, **overrides: object):
    c = _contract()
    scoring = active.scoring_authority
    basis = FinalizedQuestionScoringBasis(
        question_id=scoring.rubric.question_id,
        max_marks=scoring.rubric.max_marks,
    )
    values: dict[str, object] = {
        "evaluation_authority_profile_version": c.NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
        "grading_spec_ref": active.grading_spec_ref,
        "question_id": active.question_id,
        "rubric_id": scoring.rubric.rubric_id,
        "rubric_version": scoring.rubric.version,
        "finalized_question_hash": finalized_question_fingerprint(basis),
        "source_content_hash": authoring_content_fingerprint(active.rubric_content),
        "compiled_authority_hash": compiled_authority_fingerprint(scoring),
        "conditions": (c.NumericAbsoluteToleranceCondition("5", "0.2"),),
        "satisfied_projection": (
            c.NumericCriterionProjection("C1", "FULL"),
            c.NumericCriterionProjection("C2", "FULL"),
        ),
        "not_satisfied_projection": (
            c.NumericCriterionProjection("C1", "NOT_MET"),
            c.NumericCriterionProjection("C2", "NOT_MET"),
        ),
    }
    values.update(overrides)
    return c.NumericEvaluationAuthority(**values)


def _bound_setup():
    c = _contract()
    active = _resolved_active()
    authority = _authority(active)
    fingerprint = c.numeric_authority_fingerprint(authority)
    binding = c.NumericBoundAuthorityBinding(
        active.grading_spec_ref,
        active.question_id,
        c.NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
        fingerprint,
    )
    approval = c.NumericAuthorityApproval("teacher:n1", fingerprint)
    return active, authority, fingerprint, binding, approval


def test_red1_real_active_authority_is_valid_before_missing_n1_resolver_import() -> None:
    active = _resolved_active()
    assert active.question_id == "Q1"
    assert active.scoring_authority.rubric.rubric_id == "R-Q1"

    n = _resolver_module()
    assert callable(n.resolve_numeric_authority)


def test_bound_resolution_uses_exact_expected_fingerprint_and_returns_verified_projection() -> None:
    c = _contract()
    n = _resolver_module()
    active, authority, fingerprint, binding, approval = _bound_setup()
    binding_source = _BindingSource(binding)
    authority_source = _AuthoritySource(_Materialized(authority, approval))

    resolved = n.resolve_numeric_authority(
        active_authority=active,
        binding_source=binding_source,
        authority_source=authority_source,
    )

    assert binding_source.calls == [(active.grading_spec_ref, active.question_id)]
    assert authority_source.calls == [fingerprint]
    assert type(resolved) is n.ResolvedNumericAuthority
    assert resolved.grading_spec_ref == active.grading_spec_ref
    assert resolved.question_id == active.question_id
    assert resolved.authority_fingerprint == fingerprint
    assert resolved.authority == authority
    assert c.numeric_authority_fingerprint(resolved.authority) == fingerprint


def test_explicit_not_authorized_returns_without_authority_materialization() -> None:
    c = _contract()
    n = _resolver_module()
    active = _resolved_active()
    binding = c.NumericNotAuthorizedBinding(active.grading_spec_ref, active.question_id)
    binding_source = _BindingSource(binding)
    authority_source = _AuthoritySource(object())

    result = n.resolve_numeric_authority(
        active_authority=active,
        binding_source=binding_source,
        authority_source=authority_source,
    )
    assert type(result) is c.NumericNotAuthorizedBinding
    assert result == binding
    assert authority_source.calls == []


def test_missing_binding_is_integrity_failure_not_not_authorized() -> None:
    n = _resolver_module()
    active = _resolved_active()
    with pytest.raises(n.NumericExpectedBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(None),
            authority_source=_AuthoritySource(object()),
        )


def test_binding_source_execution_failure_is_contained_without_becoming_not_authorized() -> None:
    n = _resolver_module()
    with pytest.raises(n.NumericAuthoritySourceExecutionError):
        n.resolve_numeric_authority(
            active_authority=_resolved_active(),
            binding_source=_ExplodingBindingSource(),
            authority_source=_AuthoritySource(object()),
        )


def test_authority_source_execution_failure_is_contained() -> None:
    n = _resolver_module()
    active, _, _, binding, _ = _bound_setup()
    with pytest.raises(n.NumericAuthoritySourceExecutionError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_ExplodingAuthoritySource(),
        )


def test_bound_source_is_queried_by_exact_expected_fingerprint_only() -> None:
    n = _resolver_module()
    active, authority, fingerprint, binding, approval = _bound_setup()
    source = _AuthoritySource(_Materialized(authority, approval))
    n.resolve_numeric_authority(
        active_authority=active,
        binding_source=_BindingSource(binding),
        authority_source=source,
    )
    assert source.calls == [fingerprint]


def test_binding_wrong_spec_or_question_is_rejected_before_materialization() -> None:
    c = _contract()
    n = _resolver_module()
    active, _, fingerprint, _, _ = _bound_setup()
    for binding in (
        c.NumericBoundAuthorityBinding(GradingSpecRef("SPEC-2", 1), "Q1", "1", fingerprint),
        c.NumericBoundAuthorityBinding(active.grading_spec_ref, "Q2", "1", fingerprint),
    ):
        source = _AuthoritySource(object())
        with pytest.raises(n.NumericExpectedBindingError):
            n.resolve_numeric_authority(
                active_authority=active,
                binding_source=_BindingSource(binding),
                authority_source=source,
            )
        assert source.calls == []




def test_not_authorized_binding_still_must_match_exact_active_context() -> None:
    c = _contract()
    n = _resolver_module()
    active = _resolved_active()
    source = _AuthoritySource(object())
    with pytest.raises(n.NumericExpectedBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(
                c.NumericNotAuthorizedBinding(GradingSpecRef("SPEC-2", 1), "Q1")
            ),
            authority_source=source,
        )
    assert source.calls == []


def test_authority_spec_or_question_substitution_is_rejected_against_active_context() -> None:
    c = _contract()
    n = _resolver_module()
    active = _resolved_active()
    for overrides in (
        {"grading_spec_ref": GradingSpecRef("SPEC-2", 1)},
        {"question_id": "Q2"},
    ):
        authority = _authority(active, **overrides)
        fingerprint = c.numeric_authority_fingerprint(authority)
        binding = c.NumericBoundAuthorityBinding(
            active.grading_spec_ref, active.question_id, "1", fingerprint
        )
        approval = c.NumericAuthorityApproval("teacher:n1", fingerprint)
        with pytest.raises(n.NumericActiveConfigurationBindingError):
            n.resolve_numeric_authority(
                active_authority=active,
                binding_source=_BindingSource(binding),
                authority_source=_AuthoritySource(_Materialized(authority, approval)),
            )


def test_expected_fingerprint_mismatch_rejects_actual_payload_even_with_matching_approval_claim() -> None:
    c = _contract()
    n = _resolver_module()
    active, authority, _, _, _ = _bound_setup()
    wrong = "0" * 64
    binding = c.NumericBoundAuthorityBinding(active.grading_spec_ref, "Q1", "1", wrong)
    approval = c.NumericAuthorityApproval("teacher:n1", wrong)
    with pytest.raises(n.NumericAuthorityBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_missing_or_mismatched_approval_fails_closed() -> None:
    c = _contract()
    n = _resolver_module()
    active, authority, fingerprint, binding, _ = _bound_setup()
    for approval in (None, c.NumericAuthorityApproval("teacher:n1", "0" * 64)):
        with pytest.raises(n.NumericAuthorityApprovalBindingError):
            n.resolve_numeric_authority(
                active_authority=active,
                binding_source=_BindingSource(binding),
                authority_source=_AuthoritySource(_Materialized(authority, approval)),
            )


def test_actual_active_authoring_identity_is_recomputed_and_cross_checked() -> None:
    n = _resolver_module()
    active, _, _, _, _ = _bound_setup()
    for field_name in ("finalized_question_hash", "source_content_hash", "compiled_authority_hash"):
        authority = _authority(active, **{field_name: "0" * 64})
        c = _contract()
        fingerprint = c.numeric_authority_fingerprint(authority)
        binding = c.NumericBoundAuthorityBinding(active.grading_spec_ref, "Q1", "1", fingerprint)
        approval = c.NumericAuthorityApproval("teacher:n1", fingerprint)
        with pytest.raises(n.NumericActiveConfigurationBindingError):
            n.resolve_numeric_authority(
                active_authority=active,
                binding_source=_BindingSource(binding),
                authority_source=_AuthoritySource(_Materialized(authority, approval)),
            )


def test_rubric_id_or_version_substitution_is_rejected_against_actual_active_scoring_authority() -> None:
    n = _resolver_module()
    c = _contract()
    active = _resolved_active()
    for overrides in ({"rubric_id": "R-OTHER"}, {"rubric_version": 2}):
        authority = _authority(active, **overrides)
        fingerprint = c.numeric_authority_fingerprint(authority)
        binding = c.NumericBoundAuthorityBinding(active.grading_spec_ref, "Q1", "1", fingerprint)
        approval = c.NumericAuthorityApproval("teacher:n1", fingerprint)
        with pytest.raises(n.NumericActiveConfigurationBindingError):
            n.resolve_numeric_authority(
                active_authority=active,
                binding_source=_BindingSource(binding),
                authority_source=_AuthoritySource(_Materialized(authority, approval)),
            )


def test_projection_must_match_complete_actual_scoring_criterion_order() -> None:
    n = _resolver_module()
    c = _contract()
    active = _resolved_active()
    authority = _authority(
        active,
        satisfied_projection=(
            c.NumericCriterionProjection("C2", "FULL"),
            c.NumericCriterionProjection("C1", "FULL"),
        ),
        not_satisfied_projection=(
            c.NumericCriterionProjection("C2", "NOT_MET"),
            c.NumericCriterionProjection("C1", "NOT_MET"),
        ),
    )
    fingerprint = c.numeric_authority_fingerprint(authority)
    binding = c.NumericBoundAuthorityBinding(active.grading_spec_ref, "Q1", "1", fingerprint)
    approval = c.NumericAuthorityApproval("teacher:n1", fingerprint)
    with pytest.raises(n.NumericProjectionScoringMismatchError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_projection_level_must_be_admitted_by_exact_actual_scoring_criterion() -> None:
    n = _resolver_module()
    c = _contract()
    active = _resolved_active()
    authority = _authority(
        active,
        satisfied_projection=(
            c.NumericCriterionProjection("C1", "DOES_NOT_EXIST"),
            c.NumericCriterionProjection("C2", "FULL"),
        ),
    )
    fingerprint = c.numeric_authority_fingerprint(authority)
    binding = c.NumericBoundAuthorityBinding(active.grading_spec_ref, "Q1", "1", fingerprint)
    approval = c.NumericAuthorityApproval("teacher:n1", fingerprint)
    with pytest.raises(n.NumericProjectionScoringMismatchError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_resolver_revalidates_forged_authority_after_construction() -> None:
    c = _contract()
    n = _resolver_module()
    active, authority, fingerprint, binding, approval = _bound_setup()
    object.__setattr__(authority, "source_content_hash", "A" * 64)
    with pytest.raises(c.InvalidNumericEvaluationAuthorityError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )



def test_resolver_revalidates_forged_expected_binding_after_construction() -> None:
    c = _contract()
    n = _resolver_module()
    active, _, _, binding, _ = _bound_setup()
    object.__setattr__(binding, "authority_fingerprint", "A" * 64)
    with pytest.raises(c.InvalidNumericExpectedBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(object()),
        )


def test_resolver_revalidates_forged_approval_after_construction() -> None:
    c = _contract()
    n = _resolver_module()
    active, authority, _, binding, approval = _bound_setup()
    object.__setattr__(approval, "numeric_authority_fingerprint", "A" * 64)
    with pytest.raises(c.InvalidNumericAuthorityApprovalError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )

def test_malformed_materialization_fails_domain_safely() -> None:
    n = _resolver_module()
    active, _, _, binding, _ = _bound_setup()
    with pytest.raises(n.NumericAuthorityMaterializationError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(object()),
        )


def test_resolver_requires_exact_resolved_active_authority_type() -> None:
    n = _resolver_module()
    with pytest.raises(n.NumericActiveConfigurationBindingError):
        n.resolve_numeric_authority(
            active_authority=object(),
            binding_source=_BindingSource(object()),
            authority_source=_AuthoritySource(object()),
        )


def test_resolver_revalidates_forged_not_authorized_binding_with_valid_wrong_context() -> None:
    c = _contract()
    n = _resolver_module()
    active = _resolved_active()
    binding = c.NumericNotAuthorizedBinding(active.grading_spec_ref, active.question_id)
    object.__setattr__(binding, "grading_spec_ref", GradingSpecRef("SPEC-OTHER", 1))
    source = _AuthoritySource(object())
    with pytest.raises(n.NumericExpectedBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=source,
        )
    assert source.calls == []


def test_resolver_revalidates_forged_bound_binding_with_valid_wrong_context() -> None:
    c = _contract()
    n = _resolver_module()
    active, _, _, binding, _ = _bound_setup()
    object.__setattr__(binding, "question_id", "Q-OTHER")
    source = _AuthoritySource(object())
    with pytest.raises(n.NumericExpectedBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=source,
        )
    assert source.calls == []


def test_resolver_revalidates_forged_approval_with_well_formed_wrong_fingerprint() -> None:
    c = _contract()
    n = _resolver_module()
    active, authority, _, binding, approval = _bound_setup()
    object.__setattr__(approval, "numeric_authority_fingerprint", "0" * 64)
    with pytest.raises(n.NumericAuthorityApprovalBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )


def test_resolver_preserves_unsupported_profile_failure_for_forged_binding() -> None:
    c = _contract()
    n = _resolver_module()
    active, _, _, binding, _ = _bound_setup()
    object.__setattr__(binding, "evaluation_authority_profile_version", "2")
    with pytest.raises(c.UnsupportedNumericAuthorityProfileError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(object()),
        )


def test_forged_nested_active_scoring_state_fails_with_n1_domain_error() -> None:
    n = _resolver_module()
    active, authority, fingerprint, binding, approval = _bound_setup()
    object.__setattr__(active.scoring_authority, "rubric", object())
    with pytest.raises(n.NumericActiveConfigurationBindingError):
        n.resolve_numeric_authority(
            active_authority=active,
            binding_source=_BindingSource(binding),
            authority_source=_AuthoritySource(_Materialized(authority, approval)),
        )
