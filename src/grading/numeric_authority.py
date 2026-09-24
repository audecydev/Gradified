from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grading.active_question_authority import ResolvedQuestionAuthority
from grading.contracts.numeric_authority import (
    NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION,
    InvalidNumericAuthorityApprovalError,
    InvalidNumericEvaluationAuthorityError,
    InvalidNumericExpectedBindingError,
    UnsupportedNumericAuthorityProfileError,
    NumericAuthorityApproval,
    NumericBoundAuthorityBinding,
    NumericEvaluationAuthority,
    NumericExpectedBinding,
    NumericNotAuthorizedBinding,
    numeric_authority_fingerprint,
    validate_numeric_authority_approval,
    validate_numeric_expected_binding,
)
from grading.contracts.paper_aggregation import GradingSpecRef, _validate_grading_spec_ref
from grading.rubric.fingerprint import (
    authoring_content_fingerprint,
    compiled_authority_fingerprint,
    finalized_question_fingerprint,
)
from grading.rubric.models import FinalizedQuestionScoringBasis, QuestionRubricAuthoringContent
from grading.contracts.authority import QuestionScoringAuthority


class NumericAuthorityResolutionError(Exception):
    """Base class for expected N1 NUMERIC authority-resolution failures."""


class NumericAuthoritySourceExecutionError(NumericAuthorityResolutionError):
    """Configured trusted source failed while resolving/materializing N1 authority."""


class NumericExpectedBindingError(NumericAuthorityResolutionError):
    """Expected NUMERIC binding is missing or conflicts with ACTIVE context."""


class NumericAuthorityMaterializationError(NumericAuthorityResolutionError):
    """Exact-fingerprint authority materialization has an invalid shape."""


class NumericAuthorityBindingError(NumericAuthorityResolutionError):
    """Materialized authority payload does not match the expected fingerprint."""


class NumericAuthorityApprovalBindingError(NumericAuthorityResolutionError):
    """Required subordinate approval is absent or bound to a different authority."""


class NumericActiveConfigurationBindingError(NumericAuthorityResolutionError):
    """N1 authority does not bind the actual resolved ACTIVE configuration."""


class NumericProjectionScoringMismatchError(NumericAuthorityResolutionError):
    """N1 projections are incompatible with the actual scoring criterion universe."""


class NumericExpectedBindingSource(Protocol):
    def resolve_numeric_binding(
        self,
        *,
        grading_spec_ref: GradingSpecRef,
        question_id: str,
    ) -> NumericExpectedBinding | None:
        ...


class NumericAuthorityMaterialization(Protocol):
    authority: NumericEvaluationAuthority
    approval: NumericAuthorityApproval | None


class NumericAuthoritySource(Protocol):
    def materialize_numeric_authority(
        self,
        *,
        authority_fingerprint: str,
    ) -> NumericAuthorityMaterialization:
        ...


@dataclass(frozen=True, slots=True)
class ResolvedNumericAuthority:
    grading_spec_ref: GradingSpecRef
    question_id: str
    authority_fingerprint: str
    authority: NumericEvaluationAuthority


def _require_resolved_active(value: object) -> ResolvedQuestionAuthority:
    if type(value) is not ResolvedQuestionAuthority:
        raise NumericActiveConfigurationBindingError(
            "active_authority must be an exact ResolvedQuestionAuthority."
        )
    try:
        _validate_grading_spec_ref(
            value.grading_spec_ref,
            field_name="active_authority.grading_spec_ref",
            error_type=NumericActiveConfigurationBindingError,
        )
        if (
            type(value.question_id) is not str
            or not value.question_id
            or value.question_id.strip() != value.question_id
        ):
            raise NumericActiveConfigurationBindingError(
                "active_authority.question_id must be a non-empty exact string without surrounding whitespace."
            )
        if type(value.rubric_content) is not QuestionRubricAuthoringContent:
            raise NumericActiveConfigurationBindingError(
                "active_authority.rubric_content must be exact current rubric authoring content."
            )
        if type(value.scoring_authority) is not QuestionScoringAuthority:
            raise NumericActiveConfigurationBindingError(
                "active_authority.scoring_authority must be an exact QuestionScoringAuthority."
            )
    except NumericActiveConfigurationBindingError:
        raise
    except Exception as exc:
        raise NumericActiveConfigurationBindingError(
            "active_authority contains malformed current configuration state."
        ) from exc
    return value


def _resolve_expected_binding(
    *,
    active_authority: ResolvedQuestionAuthority,
    binding_source: NumericExpectedBindingSource,
) -> NumericExpectedBinding:
    try:
        binding = binding_source.resolve_numeric_binding(
            grading_spec_ref=active_authority.grading_spec_ref,
            question_id=active_authority.question_id,
        )
    except Exception as exc:
        raise NumericAuthoritySourceExecutionError(
            "NUMERIC expected-binding source failed during exact configuration resolution."
        ) from exc

    if binding is None:
        raise NumericExpectedBindingError(
            "NUMERIC expected binding is missing; missing is not NOT_AUTHORIZED."
        )
    try:
        validated = validate_numeric_expected_binding(binding)
    except (
        InvalidNumericExpectedBindingError,
        UnsupportedNumericAuthorityProfileError,
    ):
        raise
    except Exception as exc:
        raise InvalidNumericExpectedBindingError(
            "NUMERIC expected binding is malformed."
        ) from exc

    if (
        validated.grading_spec_ref != active_authority.grading_spec_ref
        or validated.question_id != active_authority.question_id
    ):
        raise NumericExpectedBindingError(
            "NUMERIC expected binding does not match the exact ACTIVE spec/question context."
        )
    return validated


def _materialize_exact(
    *,
    authority_source: NumericAuthoritySource,
    authority_fingerprint: str,
) -> tuple[NumericEvaluationAuthority, NumericAuthorityApproval | None]:
    try:
        materialized = authority_source.materialize_numeric_authority(
            authority_fingerprint=authority_fingerprint
        )
    except Exception as exc:
        raise NumericAuthoritySourceExecutionError(
            "NUMERIC authority source failed during exact-fingerprint materialization."
        ) from exc

    try:
        authority = materialized.authority
        approval = materialized.approval
    except AttributeError as exc:
        raise NumericAuthorityMaterializationError(
            "NUMERIC authority source returned an invalid materialization shape."
        ) from exc
    except Exception as exc:
        raise NumericAuthoritySourceExecutionError(
            "NUMERIC authority source failed during materialization access."
        ) from exc

    if type(authority) is not NumericEvaluationAuthority:
        raise NumericAuthorityMaterializationError(
            "materialized authority must be an exact NumericEvaluationAuthority."
        )
    if approval is not None and type(approval) is not NumericAuthorityApproval:
        raise NumericAuthorityMaterializationError(
            "materialized approval must be an exact NumericAuthorityApproval or None."
        )
    return authority, approval


def _cross_check_active_configuration(
    *,
    active: ResolvedQuestionAuthority,
    authority: NumericEvaluationAuthority,
) -> None:
    scoring = active.scoring_authority

    try:
        rubric = scoring.rubric
        active_rubric_id = rubric.rubric_id
        active_rubric_version = rubric.version
        active_question_id = rubric.question_id
        active_max_marks = rubric.max_marks
    except Exception as exc:
        raise NumericActiveConfigurationBindingError(
            "ACTIVE scoring authority is malformed while establishing NUMERIC binding."
        ) from exc

    if (
        authority.grading_spec_ref != active.grading_spec_ref
        or authority.question_id != active.question_id
        or authority.rubric_id != active_rubric_id
        or authority.rubric_version != active_rubric_version
    ):
        raise NumericActiveConfigurationBindingError(
            "NUMERIC authority does not bind the exact ACTIVE spec/question/rubric identity."
        )

    try:
        basis = FinalizedQuestionScoringBasis(
            question_id=active_question_id,
            max_marks=active_max_marks,
        )
        finalized_hash = finalized_question_fingerprint(basis)
        source_hash = authoring_content_fingerprint(active.rubric_content)
        compiled_hash = compiled_authority_fingerprint(scoring)
    except Exception as exc:
        raise NumericActiveConfigurationBindingError(
            "Failed to recompute exact ACTIVE authority identities from current objects."
        ) from exc

    if (
        authority.finalized_question_hash != finalized_hash
        or authority.source_content_hash != source_hash
        or authority.compiled_authority_hash != compiled_hash
    ):
        raise NumericActiveConfigurationBindingError(
            "NUMERIC authority hashes do not match recomputed ACTIVE configuration identities."
        )


def _cross_check_projections(
    *,
    active: ResolvedQuestionAuthority,
    authority: NumericEvaluationAuthority,
) -> None:
    try:
        scoring_criteria = active.scoring_authority.rubric.criteria
        expected_ids = tuple(criterion.criterion_id for criterion in scoring_criteria)
        satisfied_ids = tuple(item.criterion_id for item in authority.satisfied_projection)
        not_satisfied_ids = tuple(item.criterion_id for item in authority.not_satisfied_projection)
    except Exception as exc:
        raise NumericProjectionScoringMismatchError(
            "Unable to establish the current scoring criterion universe for NUMERIC projections."
        ) from exc
    if satisfied_ids != expected_ids or not_satisfied_ids != expected_ids:
        raise NumericProjectionScoringMismatchError(
            "NUMERIC projections must match the complete scoring-rubric criterion order."
        )

    try:
        for criterion, satisfied, not_satisfied in zip(
            scoring_criteria,
            authority.satisfied_projection,
            authority.not_satisfied_projection,
            strict=True,
        ):
            level_ids = criterion.level_ids()
            if satisfied.selected_level not in level_ids or not_satisfied.selected_level not in level_ids:
                raise NumericProjectionScoringMismatchError(
                    f"NUMERIC projection selects a level not admitted by criterion {criterion.criterion_id!r}."
                )
    except NumericProjectionScoringMismatchError:
        raise
    except Exception as exc:
        raise NumericProjectionScoringMismatchError(
            "Unable to validate NUMERIC projection levels against current scoring authority."
        ) from exc


def resolve_numeric_authority(
    *,
    active_authority: ResolvedQuestionAuthority,
    binding_source: NumericExpectedBindingSource,
    authority_source: NumericAuthoritySource,
) -> NumericNotAuthorizedBinding | ResolvedNumericAuthority:
    """Resolve one exact approved NUMERIC-v1 authority without grading evidence."""

    active = _require_resolved_active(active_authority)
    binding = _resolve_expected_binding(
        active_authority=active,
        binding_source=binding_source,
    )

    if type(binding) is NumericNotAuthorizedBinding:
        return binding

    if type(binding) is not NumericBoundAuthorityBinding:
        raise NumericExpectedBindingError("Unsupported NUMERIC expected-binding state.")
    if binding.evaluation_authority_profile_version != NUMERIC_EVALUATION_AUTHORITY_PROFILE_VERSION:
        # Normally caught by local binding validation; retained as explicit defense in depth.
        raise NumericExpectedBindingError("NUMERIC expected binding requests an unsupported profile.")

    authority, approval = _materialize_exact(
        authority_source=authority_source,
        authority_fingerprint=binding.authority_fingerprint,
    )

    # Approval shape/binding is cheap to reject before canonicalizing the bounded
    # authority payload. Approval still authenticates nothing by itself.
    if approval is None:
        raise NumericAuthorityApprovalBindingError(
            "Bound NUMERIC authority is missing required subordinate approval evidence."
        )
    validate_numeric_authority_approval(approval)
    if approval.numeric_authority_fingerprint != binding.authority_fingerprint:
        raise NumericAuthorityApprovalBindingError(
            "Subordinate NUMERIC approval does not bind the exact expected authority fingerprint."
        )

    # Revalidation occurs inside fingerprinting; construction history is not trusted.
    actual_fingerprint = numeric_authority_fingerprint(authority)
    if actual_fingerprint != binding.authority_fingerprint:
        raise NumericAuthorityBindingError(
            "Materialized NUMERIC authority fingerprint does not match the immutable expected binding."
        )

    _cross_check_active_configuration(active=active, authority=authority)
    _cross_check_projections(active=active, authority=authority)

    return ResolvedNumericAuthority(
        grading_spec_ref=active.grading_spec_ref,
        question_id=active.question_id,
        authority_fingerprint=actual_fingerprint,
        authority=authority,
    )
