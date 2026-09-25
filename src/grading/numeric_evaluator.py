from __future__ import annotations

import re

from grading.contracts.numeric_authority import (
    InvalidNumericEvaluationAuthorityError,
    NumericAbsoluteToleranceCondition,
    NumericEvaluationAuthority,
    NumericExactCondition,
    UnsupportedNumericAuthorityProfileError,
    numeric_authority_fingerprint,
)
from grading.contracts.numeric_evaluation import (
    NUMERIC_DETERMINISTIC_EVALUATION_RESULT_SCHEMA_VERSION,
    NumericConditionOutcome,
    NumericEvaluationResult,
)
from grading.contracts.numeric_evidence import (
    AdmittedNumericScalar,
    InvalidAdmittedNumericScalarError,
    validate_admitted_numeric_scalar,
)
from grading.contracts.paper_aggregation import GradingSpecRef, _validate_grading_spec_ref
from grading.numeric_authority import ResolvedNumericAuthority


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NumericDeterministicEvaluationError(Exception):
    """Base class for expected N3 deterministic NUMERIC evaluation failures."""


class NumericEvaluationAuthorityBindingError(NumericDeterministicEvaluationError):
    """Resolved N1 authority is malformed, forged, or internally inconsistent."""


class NumericEvaluationEvidenceBindingError(NumericDeterministicEvaluationError):
    """Admitted N2 evidence is malformed or bound to a different question."""


def _require_identifier(value: object, *, field_name: str, error_type: type[NumericDeterministicEvaluationError]) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise error_type(
            f"{field_name} must be a non-empty exact string without surrounding whitespace."
        )
    return value


def _required_field(
    value: object,
    field_name: str,
    *,
    owner_name: str,
    error_type: type[NumericDeterministicEvaluationError],
) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise error_type(f"{owner_name}.{field_name} is missing.") from exc


def _require_resolved_numeric_authority(value: object) -> ResolvedNumericAuthority:
    if type(value) is not ResolvedNumericAuthority:
        raise NumericEvaluationAuthorityBindingError(
            "resolved_authority must be an exact ResolvedNumericAuthority."
        )

    owner = "ResolvedNumericAuthority"
    spec_ref = _required_field(
        value,
        "grading_spec_ref",
        owner_name=owner,
        error_type=NumericEvaluationAuthorityBindingError,
    )
    question_id = _required_field(
        value,
        "question_id",
        owner_name=owner,
        error_type=NumericEvaluationAuthorityBindingError,
    )
    authority_fingerprint = _required_field(
        value,
        "authority_fingerprint",
        owner_name=owner,
        error_type=NumericEvaluationAuthorityBindingError,
    )
    authority = _required_field(
        value,
        "authority",
        owner_name=owner,
        error_type=NumericEvaluationAuthorityBindingError,
    )

    _validate_grading_spec_ref(
        spec_ref,
        field_name=f"{owner}.grading_spec_ref",
        error_type=NumericEvaluationAuthorityBindingError,
    )
    _require_identifier(
        question_id,
        field_name=f"{owner}.question_id",
        error_type=NumericEvaluationAuthorityBindingError,
    )
    if type(authority_fingerprint) is not str or _SHA256_RE.fullmatch(authority_fingerprint) is None:
        raise NumericEvaluationAuthorityBindingError(
            "ResolvedNumericAuthority.authority_fingerprint must be canonical lowercase SHA-256 hex."
        )
    if type(authority) is not NumericEvaluationAuthority:
        raise NumericEvaluationAuthorityBindingError(
            "ResolvedNumericAuthority.authority must be an exact NumericEvaluationAuthority."
        )

    try:
        actual_fingerprint = numeric_authority_fingerprint(authority)
    except (InvalidNumericEvaluationAuthorityError, UnsupportedNumericAuthorityProfileError) as exc:
        raise NumericEvaluationAuthorityBindingError(
            "Resolved NUMERIC authority current payload is invalid."
        ) from exc

    if actual_fingerprint != authority_fingerprint:
        raise NumericEvaluationAuthorityBindingError(
            "Resolved NUMERIC authority fingerprint does not match its current payload."
        )
    if authority.grading_spec_ref != spec_ref or authority.question_id != question_id:
        raise NumericEvaluationAuthorityBindingError(
            "Resolved NUMERIC authority identity does not match its current authority payload."
        )
    return value


def _require_admitted_scalar(value: object) -> AdmittedNumericScalar:
    try:
        return validate_admitted_numeric_scalar(value)
    except InvalidAdmittedNumericScalarError as exc:
        raise NumericEvaluationEvidenceBindingError(
            "Admitted NUMERIC scalar current state is invalid."
        ) from exc


def _decimal_parts(text: str) -> tuple[int, int]:
    """Convert already-validated canonical finite-decimal text to coefficient/scale."""

    negative = text.startswith("-")
    body = text[1:] if negative else text
    if "." in body:
        integer_text, fractional_text = body.split(".", 1)
    else:
        integer_text, fractional_text = body, ""
    coefficient = int(integer_text + fractional_text)
    if negative:
        coefficient = -coefficient
    return coefficient, len(fractional_text)


def _at_common_scale(
    left: tuple[int, int],
    right: tuple[int, int],
) -> tuple[int, int]:
    left_coefficient, left_scale = left
    right_coefficient, right_scale = right
    target_scale = max(left_scale, right_scale)
    return (
        left_coefficient * (10 ** (target_scale - left_scale)),
        right_coefficient * (10 ** (target_scale - right_scale)),
    )


def _exact_matches(observed: tuple[int, int], expected_text: str) -> bool:
    observed_scaled, expected_scaled = _at_common_scale(observed, _decimal_parts(expected_text))
    return observed_scaled == expected_scaled


def _within_absolute_tolerance(
    observed: tuple[int, int],
    *,
    expected_text: str,
    tolerance_text: str,
) -> bool:
    expected = _decimal_parts(expected_text)
    tolerance = _decimal_parts(tolerance_text)
    target_scale = max(observed[1], expected[1], tolerance[1])

    observed_scaled = observed[0] * (10 ** (target_scale - observed[1]))
    expected_scaled = expected[0] * (10 ** (target_scale - expected[1]))
    tolerance_scaled = tolerance[0] * (10 ** (target_scale - tolerance[1]))
    return abs(observed_scaled - expected_scaled) <= tolerance_scaled


def evaluate_numeric_scalar(
    *,
    resolved_authority: ResolvedNumericAuthority,
    observation: AdmittedNumericScalar,
) -> NumericEvaluationResult:
    """Execute only the approved N1 exact/absolute-tolerance relation over N2 evidence.

    A successful comparison yields SATISFIED or NOT_SATISFIED. Validation,
    binding, or technical failures raise and are never converted into an academic
    NOT_SATISFIED outcome. N3 does not select criterion levels or calculate marks.
    """

    resolved = _require_resolved_numeric_authority(resolved_authority)
    admitted = _require_admitted_scalar(observation)

    if admitted.question_id != resolved.question_id:
        raise NumericEvaluationEvidenceBindingError(
            "Admitted NUMERIC scalar question_id must match resolved NUMERIC authority question_id."
        )

    observed = _decimal_parts(admitted.canonical_value)
    authority = resolved.authority

    satisfied = False
    for condition in authority.conditions:
        if type(condition) is NumericExactCondition:
            matched = _exact_matches(observed, condition.expected_value)
        elif type(condition) is NumericAbsoluteToleranceCondition:
            matched = _within_absolute_tolerance(
                observed,
                expected_text=condition.expected_value,
                tolerance_text=condition.tolerance,
            )
        else:  # current-state authority validation above should make this unreachable
            raise NumericEvaluationAuthorityBindingError(
                "Resolved NUMERIC authority contains an unsupported condition type."
            )
        if matched:
            satisfied = True
            break

    return NumericEvaluationResult(
        schema_version=NUMERIC_DETERMINISTIC_EVALUATION_RESULT_SCHEMA_VERSION,
        grading_spec_ref=resolved.grading_spec_ref,
        authority_fingerprint=resolved.authority_fingerprint,
        question_id=resolved.question_id,
        submission_ref=admitted.submission_ref,
        ocr_provenance=admitted.ocr_provenance,
        answer_scope_ref=admitted.answer_scope_ref,
        evidence_ref=admitted.evidence_ref,
        admission_profile_version=admitted.admission_profile_version,
        outcome=(
            NumericConditionOutcome.SATISFIED
            if satisfied
            else NumericConditionOutcome.NOT_SATISFIED
        ),
    )
