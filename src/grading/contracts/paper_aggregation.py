from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TypeVar

from grading.contracts.errors import (
    InvalidScoringAuthorityError,
    InvalidScoringValueError,
    ScoringNumericEnvelopeError,
    UnsupportedScoringSemanticsError,
)
from grading.contracts.policy import SCORING_SEMANTICS_V1
from grading.contracts.scoring_decimal import ScoringDecimal


_ErrorT = TypeVar("_ErrorT", bound=Exception)


def _raise(error_type: type[_ErrorT], message: str, cause: BaseException | None = None) -> None:
    if cause is None:
        raise error_type(message)
    raise error_type(message) from cause


def _required_field(
    value: object,
    field_name: str,
    *,
    error_type: type[_ErrorT],
    owner_name: str,
) -> object:
    """Read one required slotted field without trusting construction history."""

    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        _raise(
            error_type,
            f"{owner_name}.{field_name} is missing.",
            exc,
        )


def _validate_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
) -> str:
    """Require an exact, non-empty identifier without normalizing it."""

    if type(value) is not str or not value or value.strip() != value:
        _raise(
            error_type,
            f"{field_name} must be a non-empty exact string without surrounding whitespace.",
        )
    return value


def _validate_positive_version(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
) -> int:
    if type(value) is not int or value <= 0:
        _raise(error_type, f"{field_name} must be a positive exact integer.")
    return value


def _validate_scoring_decimal_structure(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
) -> ScoringDecimal:
    """Re-admit a possibly forged exact ScoringDecimal through the B1 boundary."""

    if type(value) is not ScoringDecimal:
        _raise(error_type, f"{field_name} must be an exact ScoringDecimal.")

    try:
        raw = object.__getattribute__(value, "_value")
    except AttributeError as exc:
        _raise(error_type, f"{field_name} is missing its Decimal representation.", exc)

    if type(raw) is not Decimal:
        _raise(error_type, f"{field_name} contains an invalid Decimal representation.")

    if not raw.is_finite():
        _raise(error_type, f"{field_name} must be finite.")

    try:
        reconstructed = ScoringDecimal(raw)
    except (InvalidScoringValueError, ScoringNumericEnvelopeError) as exc:
        _raise(error_type, f"{field_name} violates Numeric Profile v1.", exc)

    reconstructed_raw = object.__getattribute__(reconstructed, "_value")
    if reconstructed_raw.as_tuple() != raw.as_tuple():
        _raise(error_type, f"{field_name} is not in canonical Numeric Profile v1 form.")

    return value


def _validate_grading_spec_ref(
    value: object,
    *,
    field_name: str = "grading_spec_ref",
    error_type: type[_ErrorT] = InvalidScoringAuthorityError,
) -> GradingSpecRef:
    if type(value) is not GradingSpecRef:
        _raise(error_type, f"{field_name} must be an exact GradingSpecRef.")

    identifier = _required_field(
        value,
        "id",
        error_type=error_type,
        owner_name=field_name,
    )
    version = _required_field(
        value,
        "version",
        error_type=error_type,
        owner_name=field_name,
    )
    _validate_identifier(identifier, field_name=f"{field_name}.id", error_type=error_type)
    _validate_positive_version(
        version,
        field_name=f"{field_name}.version",
        error_type=error_type,
    )
    return value


def _validate_rubric_ref(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
) -> RubricRef:
    if type(value) is not RubricRef:
        _raise(error_type, f"{field_name} must be an exact RubricRef.")

    identifier = _required_field(
        value,
        "id",
        error_type=error_type,
        owner_name=field_name,
    )
    version = _required_field(
        value,
        "version",
        error_type=error_type,
        owner_name=field_name,
    )
    _validate_identifier(identifier, field_name=f"{field_name}.id", error_type=error_type)
    _validate_positive_version(
        version,
        field_name=f"{field_name}.version",
        error_type=error_type,
    )
    return value


def _validate_scoring_policy_ref(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
    require_supported_semantics: bool,
) -> ScoringPolicyRef:
    if type(value) is not ScoringPolicyRef:
        _raise(error_type, f"{field_name} must be an exact ScoringPolicyRef.")

    identifier = _required_field(
        value,
        "id",
        error_type=error_type,
        owner_name=field_name,
    )
    version = _required_field(
        value,
        "version",
        error_type=error_type,
        owner_name=field_name,
    )
    semantics = _required_field(
        value,
        "scoring_semantics_version",
        error_type=error_type,
        owner_name=field_name,
    )

    _validate_identifier(identifier, field_name=f"{field_name}.id", error_type=error_type)
    _validate_positive_version(
        version,
        field_name=f"{field_name}.version",
        error_type=error_type,
    )
    _validate_identifier(
        semantics,
        field_name=f"{field_name}.scoring_semantics_version",
        error_type=error_type,
    )

    if require_supported_semantics and semantics != SCORING_SEMANTICS_V1:
        if issubclass(error_type, InvalidScoringAuthorityError):
            raise UnsupportedScoringSemanticsError(
                f"{field_name} requests unsupported scoring semantics {semantics!r}."
            )
        _raise(
            error_type,
            f"{field_name} requests unsupported scoring semantics {semantics!r}.",
        )

    return value


@dataclass(frozen=True, slots=True)
class GradingSpecRef:
    """Immutable scoring-specification reference preserved as B3 provenance."""

    id: str
    version: int

    def __post_init__(self) -> None:
        _validate_grading_spec_ref(self)


# Late import is deliberate: GradingSpecRef must exist before result imports it
# back for PaperScoreResult runtime annotation resolution.
from grading.contracts.result import RubricRef, ScoringPolicyRef


@dataclass(frozen=True, slots=True)
class ExpectedQuestionResult:
    """One exact question-result identity required by the resolved paper authority."""

    question_id: str
    rubric_ref: RubricRef
    scoring_policy_ref: ScoringPolicyRef

    def __post_init__(self) -> None:
        _validate_expected_question_result(self)


def _validate_expected_question_result(
    value: object,
    *,
    field_name: str = "expected_question",
    error_type: type[_ErrorT] = InvalidScoringAuthorityError,
) -> ExpectedQuestionResult:
    if type(value) is not ExpectedQuestionResult:
        _raise(error_type, f"{field_name} must be an exact ExpectedQuestionResult.")

    question_id = _required_field(
        value,
        "question_id",
        error_type=error_type,
        owner_name=field_name,
    )
    rubric_ref = _required_field(
        value,
        "rubric_ref",
        error_type=error_type,
        owner_name=field_name,
    )
    policy_ref = _required_field(
        value,
        "scoring_policy_ref",
        error_type=error_type,
        owner_name=field_name,
    )

    _validate_identifier(
        question_id,
        field_name=f"{field_name}.question_id",
        error_type=error_type,
    )
    _validate_rubric_ref(
        rubric_ref,
        field_name=f"{field_name}.rubric_ref",
        error_type=error_type,
    )
    _validate_scoring_policy_ref(
        policy_ref,
        field_name=f"{field_name}.scoring_policy_ref",
        error_type=error_type,
        require_supported_semantics=True,
    )
    return value


@dataclass(frozen=True, slots=True)
class ResolvedPaperScoringAuthority:
    """Structurally validated resolved paper composition consumed by B3."""

    grading_spec_ref: GradingSpecRef
    expected_questions: tuple[ExpectedQuestionResult, ...]
    minimum_score: ScoringDecimal
    maximum_score: ScoringDecimal

    def __post_init__(self) -> None:
        _validate_resolved_paper_scoring_authority(self)


def _validate_resolved_paper_scoring_authority(
    value: object,
) -> ResolvedPaperScoringAuthority:
    """Defensively validate the complete authority graph without trusting provenance."""

    if type(value) is not ResolvedPaperScoringAuthority:
        raise InvalidScoringAuthorityError(
            "authority must be an exact ResolvedPaperScoringAuthority."
        )

    grading_spec_ref = _required_field(
        value,
        "grading_spec_ref",
        error_type=InvalidScoringAuthorityError,
        owner_name="authority",
    )
    expected_questions = _required_field(
        value,
        "expected_questions",
        error_type=InvalidScoringAuthorityError,
        owner_name="authority",
    )
    minimum_score = _required_field(
        value,
        "minimum_score",
        error_type=InvalidScoringAuthorityError,
        owner_name="authority",
    )
    maximum_score = _required_field(
        value,
        "maximum_score",
        error_type=InvalidScoringAuthorityError,
        owner_name="authority",
    )

    _validate_grading_spec_ref(
        grading_spec_ref,
        field_name="authority.grading_spec_ref",
        error_type=InvalidScoringAuthorityError,
    )

    if type(expected_questions) is not tuple or not expected_questions:
        raise InvalidScoringAuthorityError(
            "authority.expected_questions must be a non-empty exact tuple."
        )

    question_ids: list[str] = []
    for index, expected in enumerate(expected_questions):
        validated = _validate_expected_question_result(
            expected,
            field_name=f"authority.expected_questions[{index}]",
            error_type=InvalidScoringAuthorityError,
        )
        question_id = _required_field(
            validated,
            "question_id",
            error_type=InvalidScoringAuthorityError,
            owner_name=f"authority.expected_questions[{index}]",
        )
        question_ids.append(question_id)

    if len(question_ids) != len(set(question_ids)):
        raise InvalidScoringAuthorityError(
            "authority.expected_questions contains duplicate question IDs."
        )

    validated_minimum = _validate_scoring_decimal_structure(
        minimum_score,
        field_name="authority.minimum_score",
        error_type=InvalidScoringAuthorityError,
    )
    validated_maximum = _validate_scoring_decimal_structure(
        maximum_score,
        field_name="authority.maximum_score",
        error_type=InvalidScoringAuthorityError,
    )

    if validated_minimum.as_decimal() > validated_maximum.as_decimal():
        raise InvalidScoringAuthorityError(
            "authority.minimum_score cannot exceed authority.maximum_score."
        )

    return value
