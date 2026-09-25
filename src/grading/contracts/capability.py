from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from grading.contracts.evaluation import EvaluatorMetadata


EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION = "1"
MAX_CAPABILITY_IDENTIFIER_CHARACTERS = 128
MAX_CAPABILITY_TUPLE_ENTRIES = 32
MAX_CAPABILITY_DESCRIPTION_CHARACTERS = 512


class EvaluatorCapabilityContractError(ValueError):
    """Base class for expected IF1 capability-record contract failures."""


class InvalidEvaluatorCapabilityRefError(EvaluatorCapabilityContractError):
    """Raised when an evaluator capability reference is malformed."""


class InvalidEvaluatorCapabilityRecordError(EvaluatorCapabilityContractError):
    """Raised when an evaluator capability record is malformed."""


class UnsupportedEvaluatorCapabilityRecordSchemaError(EvaluatorCapabilityContractError):
    """Raised when a capability record requests an unsupported schema version."""


class EvaluatorCapabilityStatus(str, Enum):
    VALIDATED = "VALIDATED"
    PILOT = "PILOT"
    DISABLED = "DISABLED"


def _required_field(
    value: object,
    field_name: str,
    *,
    owner_name: str,
    error_type: type[EvaluatorCapabilityContractError],
) -> object:
    try:
        return object.__getattribute__(value, field_name)
    except AttributeError as exc:
        raise error_type(f"{owner_name}.{field_name} is missing.") from exc


def _require_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[EvaluatorCapabilityContractError],
) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise error_type(
            f"{field_name} must be a non-empty exact string without surrounding whitespace."
        )
    if len(value) > MAX_CAPABILITY_IDENTIFIER_CHARACTERS:
        raise error_type(
            f"{field_name} exceeds the IF1-v1 {MAX_CAPABILITY_IDENTIFIER_CHARACTERS}-character limit."
        )
    return value


def _require_optional_description(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value or value.strip() != value:
        raise InvalidEvaluatorCapabilityRecordError(
            f"{field_name} must be None or a non-empty exact string without surrounding whitespace."
        )
    if len(value) > MAX_CAPABILITY_DESCRIPTION_CHARACTERS:
        raise InvalidEvaluatorCapabilityRecordError(
            f"{field_name} exceeds the IF1-v1 {MAX_CAPABILITY_DESCRIPTION_CHARACTERS}-character limit."
        )
    return value


def _require_string_tuple(
    value: object,
    *,
    field_name: str,
    max_text_characters: int,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise InvalidEvaluatorCapabilityRecordError(
            f"{field_name} must be an exact tuple."
        )
    if len(value) > MAX_CAPABILITY_TUPLE_ENTRIES:
        raise InvalidEvaluatorCapabilityRecordError(
            f"{field_name} exceeds the IF1-v1 {MAX_CAPABILITY_TUPLE_ENTRIES}-entry limit."
        )

    seen: set[str] = set()
    for index, item in enumerate(value):
        if type(item) is not str or not item or item.strip() != item:
            raise InvalidEvaluatorCapabilityRecordError(
                f"{field_name}[{index}] must be a non-empty exact string without surrounding whitespace."
            )
        if len(item) > max_text_characters:
            raise InvalidEvaluatorCapabilityRecordError(
                f"{field_name}[{index}] exceeds the IF1-v1 {max_text_characters}-character limit."
            )
        if item in seen:
            raise InvalidEvaluatorCapabilityRecordError(
                f"{field_name} must not contain duplicate entries."
            )
        seen.add(item)
    return value


def _validate_evaluator_metadata(
    value: object,
    *,
    field_name: str,
    error_type: type[EvaluatorCapabilityContractError],
) -> EvaluatorMetadata:
    if type(value) is not EvaluatorMetadata:
        raise error_type(f"{field_name} must be an exact EvaluatorMetadata.")

    evaluator_id = _required_field(
        value,
        "evaluator_id",
        owner_name="EvaluatorMetadata",
        error_type=error_type,
    )
    version = _required_field(
        value,
        "version",
        owner_name="EvaluatorMetadata",
        error_type=error_type,
    )
    _require_identifier(
        evaluator_id,
        field_name=f"{field_name}.evaluator_id",
        error_type=error_type,
    )
    _require_identifier(
        version,
        field_name=f"{field_name}.version",
        error_type=error_type,
    )
    return value


@dataclass(frozen=True, slots=True)
class EvaluatorCapabilityRef:
    evaluator_metadata: EvaluatorMetadata
    record_version: int

    def __post_init__(self) -> None:
        validate_evaluator_capability_ref(self)


@dataclass(frozen=True, slots=True)
class EvaluatorCapabilityRecord:
    schema_version: str
    capability_ref: EvaluatorCapabilityRef
    status: EvaluatorCapabilityStatus
    supported_answer_types: tuple[str, ...]
    supported_languages: tuple[str, ...]
    supported_modalities: tuple[str, ...]
    tested_grade_range: str | None
    domain_scope: str | None
    verification_mechanisms: tuple[str, ...]
    benchmark_version: str | None
    known_failure_modes: tuple[str, ...]
    cost_profile: str | None
    latency_profile: str | None

    def __post_init__(self) -> None:
        validate_evaluator_capability_record(self)


def validate_evaluator_capability_ref(value: object) -> EvaluatorCapabilityRef:
    """Validate the complete current state of one exact IF1 capability reference."""

    if type(value) is not EvaluatorCapabilityRef:
        raise InvalidEvaluatorCapabilityRefError(
            "capability_ref must be an exact EvaluatorCapabilityRef."
        )

    evaluator_metadata = _required_field(
        value,
        "evaluator_metadata",
        owner_name="EvaluatorCapabilityRef",
        error_type=InvalidEvaluatorCapabilityRefError,
    )
    record_version = _required_field(
        value,
        "record_version",
        owner_name="EvaluatorCapabilityRef",
        error_type=InvalidEvaluatorCapabilityRefError,
    )

    _validate_evaluator_metadata(
        evaluator_metadata,
        field_name="EvaluatorCapabilityRef.evaluator_metadata",
        error_type=InvalidEvaluatorCapabilityRefError,
    )
    if type(record_version) is not int or record_version <= 0:
        raise InvalidEvaluatorCapabilityRefError(
            "EvaluatorCapabilityRef.record_version must be a positive exact integer."
        )
    return value


def validate_evaluator_capability_record(value: object) -> EvaluatorCapabilityRecord:
    """Validate the complete current state of one exact IF1 capability record."""

    if type(value) is not EvaluatorCapabilityRecord:
        raise InvalidEvaluatorCapabilityRecordError(
            "capability record must be an exact EvaluatorCapabilityRecord."
        )

    schema_version = _required_field(
        value,
        "schema_version",
        owner_name="EvaluatorCapabilityRecord",
        error_type=InvalidEvaluatorCapabilityRecordError,
    )
    if type(schema_version) is not str or schema_version != EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION:
        raise UnsupportedEvaluatorCapabilityRecordSchemaError(
            "EvaluatorCapabilityRecord.schema_version must equal supported IF1 schema version '1'."
        )

    capability_ref = _required_field(
        value,
        "capability_ref",
        owner_name="EvaluatorCapabilityRecord",
        error_type=InvalidEvaluatorCapabilityRecordError,
    )
    try:
        validate_evaluator_capability_ref(capability_ref)
    except InvalidEvaluatorCapabilityRefError as exc:
        raise InvalidEvaluatorCapabilityRecordError(
            "EvaluatorCapabilityRecord.capability_ref is invalid."
        ) from exc

    status = _required_field(
        value,
        "status",
        owner_name="EvaluatorCapabilityRecord",
        error_type=InvalidEvaluatorCapabilityRecordError,
    )
    if type(status) is not EvaluatorCapabilityStatus or not any(
        status is member for member in EvaluatorCapabilityStatus
    ):
        raise InvalidEvaluatorCapabilityRecordError(
            "EvaluatorCapabilityRecord.status must be a canonical EvaluatorCapabilityStatus member."
        )

    _require_string_tuple(
        _required_field(
            value,
            "supported_answer_types",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.supported_answer_types",
        max_text_characters=MAX_CAPABILITY_IDENTIFIER_CHARACTERS,
    )
    _require_string_tuple(
        _required_field(
            value,
            "supported_languages",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.supported_languages",
        max_text_characters=MAX_CAPABILITY_IDENTIFIER_CHARACTERS,
    )
    _require_string_tuple(
        _required_field(
            value,
            "supported_modalities",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.supported_modalities",
        max_text_characters=MAX_CAPABILITY_IDENTIFIER_CHARACTERS,
    )

    _require_optional_description(
        _required_field(
            value,
            "tested_grade_range",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.tested_grade_range",
    )
    _require_optional_description(
        _required_field(
            value,
            "domain_scope",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.domain_scope",
    )

    _require_string_tuple(
        _required_field(
            value,
            "verification_mechanisms",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.verification_mechanisms",
        max_text_characters=MAX_CAPABILITY_IDENTIFIER_CHARACTERS,
    )

    benchmark_version = _required_field(
        value,
        "benchmark_version",
        owner_name="EvaluatorCapabilityRecord",
        error_type=InvalidEvaluatorCapabilityRecordError,
    )
    if benchmark_version is not None:
        _require_identifier(
            benchmark_version,
            field_name="EvaluatorCapabilityRecord.benchmark_version",
            error_type=InvalidEvaluatorCapabilityRecordError,
        )

    _require_string_tuple(
        _required_field(
            value,
            "known_failure_modes",
            owner_name="EvaluatorCapabilityRecord",
            error_type=InvalidEvaluatorCapabilityRecordError,
        ),
        field_name="EvaluatorCapabilityRecord.known_failure_modes",
        max_text_characters=MAX_CAPABILITY_DESCRIPTION_CHARACTERS,
    )

    for field_name in ("cost_profile", "latency_profile"):
        _require_optional_description(
            _required_field(
                value,
                field_name,
                owner_name="EvaluatorCapabilityRecord",
                error_type=InvalidEvaluatorCapabilityRecordError,
            ),
            field_name=f"EvaluatorCapabilityRecord.{field_name}",
        )

    return value
