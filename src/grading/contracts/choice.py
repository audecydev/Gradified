from __future__ import annotations

from dataclasses import dataclass

from grading.contracts.paper_aggregation import GradingSpecRef


CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION = "1"
CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION = "1"

DETERMINISTIC_CHOICE_EVALUATOR_ID = "gradified-deterministic-choice"
DETERMINISTIC_CHOICE_EVALUATOR_VERSION = "1"

CHOICE_MATCH_REASON_CODE = "DETERMINISTIC_CHOICE_MATCH"
CHOICE_MISMATCH_REASON_CODE = "DETERMINISTIC_CHOICE_MISMATCH"

CHOICE_MATCH_RATIONALE = (
    "Canonical selected option matches the authoritative option."
)
CHOICE_MISMATCH_RATIONALE = (
    "Canonical selected option does not match the authoritative option."
)


class ChoiceEvaluationError(ValueError):
    """Base class for expected single-select CHOICE contract failures."""


class InvalidChoiceEvaluationAuthorityError(ChoiceEvaluationError):
    """Raised when local CHOICE evaluation authority is malformed."""


class InvalidCanonicalChoiceSelectionError(ChoiceEvaluationError):
    """Raised when a canonical single-select choice value is malformed."""


class UnsupportedChoiceInputError(ChoiceEvaluationError):
    """Raised when a valid input is outside the admitted CHOICE authority."""


class ChoiceSelectionBindingError(ChoiceEvaluationError):
    """Raised when a selection does not bind to the CHOICE question."""


class ChoiceScoringAuthorityBindingError(ChoiceEvaluationError):
    """Raised when CHOICE authority does not bind to supplied scoring authority."""


class ChoiceProjectionScoringMismatchError(ChoiceEvaluationError):
    """Raised when CHOICE projections are incompatible with scoring authority."""


def _require_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[ChoiceEvaluationError],
) -> str:
    if type(value) is not str:
        raise error_type(f"{field_name} must be an exact string.")
    if not value or value.strip() != value:
        raise error_type(
            f"{field_name} must be non-empty without surrounding whitespace."
        )
    return value


def _require_schema_version(
    value: object,
    *,
    expected: str,
    field_name: str,
    error_type: type[ChoiceEvaluationError],
) -> None:
    if type(value) is not str or value != expected:
        raise error_type(f"{field_name} must equal supported schema version {expected!r}.")


def _require_exact_nonempty_tuple(
    value: object,
    *,
    field_name: str,
    error_type: type[ChoiceEvaluationError],
) -> tuple[object, ...]:
    if type(value) is not tuple or not value:
        raise error_type(f"{field_name} must be a non-empty exact tuple.")
    return value


@dataclass(frozen=True, slots=True)
class ChoiceCriterionProjection:
    criterion_id: str
    selected_level: str

    def __post_init__(self) -> None:
        _require_identifier(
            self.criterion_id,
            field_name="ChoiceCriterionProjection.criterion_id",
            error_type=InvalidChoiceEvaluationAuthorityError,
        )
        _require_identifier(
            self.selected_level,
            field_name="ChoiceCriterionProjection.selected_level",
            error_type=InvalidChoiceEvaluationAuthorityError,
        )


@dataclass(frozen=True, slots=True)
class ChoiceEvaluationAuthority:
    schema_version: str
    grading_spec_ref: GradingSpecRef
    question_id: str
    compiled_authority_hash: str
    option_ids: tuple[str, ...]
    official_option_id: str
    match_projection: tuple[ChoiceCriterionProjection, ...]
    mismatch_projection: tuple[ChoiceCriterionProjection, ...]

    def __post_init__(self) -> None:
        _require_schema_version(
            self.schema_version,
            expected=CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
            field_name="ChoiceEvaluationAuthority.schema_version",
            error_type=InvalidChoiceEvaluationAuthorityError,
        )

        if type(self.grading_spec_ref) is not GradingSpecRef:
            raise InvalidChoiceEvaluationAuthorityError(
                "ChoiceEvaluationAuthority.grading_spec_ref must be an exact GradingSpecRef."
            )

        _require_identifier(
            self.question_id,
            field_name="ChoiceEvaluationAuthority.question_id",
            error_type=InvalidChoiceEvaluationAuthorityError,
        )

        authority_hash = self.compiled_authority_hash
        if (
            type(authority_hash) is not str
            or len(authority_hash) != 64
            or any(character not in "0123456789abcdef" for character in authority_hash)
        ):
            raise InvalidChoiceEvaluationAuthorityError(
                "ChoiceEvaluationAuthority.compiled_authority_hash must be "
                "canonical lowercase SHA-256 hex."
            )

        option_ids = _require_exact_nonempty_tuple(
            self.option_ids,
            field_name="ChoiceEvaluationAuthority.option_ids",
            error_type=InvalidChoiceEvaluationAuthorityError,
        )
        validated_option_ids: list[str] = []
        for index, option_id in enumerate(option_ids):
            validated_option_ids.append(
                _require_identifier(
                    option_id,
                    field_name=f"ChoiceEvaluationAuthority.option_ids[{index}]",
                    error_type=InvalidChoiceEvaluationAuthorityError,
                )
            )
        if len(validated_option_ids) != len(set(validated_option_ids)):
            raise InvalidChoiceEvaluationAuthorityError(
                "ChoiceEvaluationAuthority.option_ids must be unique."
            )

        official_option_id = _require_identifier(
            self.official_option_id,
            field_name="ChoiceEvaluationAuthority.official_option_id",
            error_type=InvalidChoiceEvaluationAuthorityError,
        )
        if official_option_id not in validated_option_ids:
            raise InvalidChoiceEvaluationAuthorityError(
                "ChoiceEvaluationAuthority.official_option_id must belong to option_ids."
            )

        match_projection = self._validate_projection_tuple(
            self.match_projection,
            field_name="ChoiceEvaluationAuthority.match_projection",
        )
        mismatch_projection = self._validate_projection_tuple(
            self.mismatch_projection,
            field_name="ChoiceEvaluationAuthority.mismatch_projection",
        )

        match_ids = tuple(item.criterion_id for item in match_projection)
        mismatch_ids = tuple(item.criterion_id for item in mismatch_projection)
        if match_ids != mismatch_ids:
            raise InvalidChoiceEvaluationAuthorityError(
                "CHOICE match/mismatch projections must have identical "
                "criterion-ID sequences."
            )

    @staticmethod
    def _validate_projection_tuple(
        value: object,
        *,
        field_name: str,
    ) -> tuple[ChoiceCriterionProjection, ...]:
        items = _require_exact_nonempty_tuple(
            value,
            field_name=field_name,
            error_type=InvalidChoiceEvaluationAuthorityError,
        )

        criterion_ids: list[str] = []
        for index, item in enumerate(items):
            if type(item) is not ChoiceCriterionProjection:
                raise InvalidChoiceEvaluationAuthorityError(
                    f"{field_name}[{index}] must be an exact ChoiceCriterionProjection."
                )
            criterion_ids.append(item.criterion_id)

        if len(criterion_ids) != len(set(criterion_ids)):
            raise InvalidChoiceEvaluationAuthorityError(
                f"{field_name} contains duplicate criterion_id values."
            )

        return items  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CanonicalChoiceSelection:
    schema_version: str
    submission_ref: str
    question_id: str
    selected_option_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_schema_version(
            self.schema_version,
            expected=CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
            field_name="CanonicalChoiceSelection.schema_version",
            error_type=InvalidCanonicalChoiceSelectionError,
        )

        _require_identifier(
            self.submission_ref,
            field_name="CanonicalChoiceSelection.submission_ref",
            error_type=InvalidCanonicalChoiceSelectionError,
        )
        _require_identifier(
            self.question_id,
            field_name="CanonicalChoiceSelection.question_id",
            error_type=InvalidCanonicalChoiceSelectionError,
        )
        _require_identifier(
            self.selected_option_id,
            field_name="CanonicalChoiceSelection.selected_option_id",
            error_type=InvalidCanonicalChoiceSelectionError,
        )

        evidence_refs = _require_exact_nonempty_tuple(
            self.evidence_refs,
            field_name="CanonicalChoiceSelection.evidence_refs",
            error_type=InvalidCanonicalChoiceSelectionError,
        )
        validated_refs: list[str] = []
        for index, evidence_ref in enumerate(evidence_refs):
            validated_refs.append(
                _require_identifier(
                    evidence_ref,
                    field_name=f"CanonicalChoiceSelection.evidence_refs[{index}]",
                    error_type=InvalidCanonicalChoiceSelectionError,
                )
            )

        if len(validated_refs) != len(set(validated_refs)):
            raise InvalidCanonicalChoiceSelectionError(
                "CanonicalChoiceSelection.evidence_refs must be unique."
            )
