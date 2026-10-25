from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class EvidenceBlockType(str, Enum):
    TEXT = "TEXT"
    MATH = "MATH"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    CODE = "CODE"
    OTHER = "OTHER"


class EvidenceConfidenceStatus(str, Enum):
    PRESENT = "PRESENT"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceBlockState(str, Enum):
    ACTIVE = "ACTIVE"
    CROSSED_OUT = "CROSSED_OUT"
    UNCERTAIN = "UNCERTAIN"


class EvidenceLocationStatus(str, Enum):
    PRESENT = "PRESENT"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


def _require_exact_type(value: object, expected_type: type, field_name: str) -> None:
    if type(value) is not expected_type:
        raise TypeError(f"{field_name} must be a {expected_type.__name__}.")


def _require_identifier(value: object, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string.")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be non-empty without surrounding whitespace."
        )


def _require_optional_string(value: object, field_name: str) -> None:
    if value is not None and type(value) is not str:
        raise TypeError(f"{field_name} must be a string or None.")


def _require_tuple_of(values: object, item_type: type, field_name: str) -> None:
    if type(values) is not tuple:
        raise TypeError(f"{field_name} must be a tuple.")
    if any(type(value) is not item_type for value in values):
        raise TypeError(f"{field_name} contains an invalid item.")


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    status: EvidenceLocationStatus
    bbox: tuple[float, ...] | None

    def __post_init__(self) -> None:
        _require_exact_type(
            self.status,
            EvidenceLocationStatus,
            "EvidenceLocation.status",
        )
        if self.bbox is not None:
            if type(self.bbox) is not tuple:
                raise TypeError("EvidenceLocation.bbox must be a tuple or None.")
            if any(
                not (type(value) is int or type(value) is float)
                for value in self.bbox
            ):
                raise TypeError(
                    "EvidenceLocation.bbox must contain only numeric coordinates."
                )
            if any(not math.isfinite(float(value)) for value in self.bbox):
                raise ValueError("EvidenceLocation.bbox must contain only finite coordinates.")


@dataclass(frozen=True, slots=True)
class EvidenceBlock:
    block_id: str
    type: EvidenceBlockType
    content: str
    language: str | None
    confidence: int | float | None
    confidence_status: EvidenceConfidenceStatus
    state: EvidenceBlockState
    page: int
    location: EvidenceLocation
    reading_order: int
    asset_ref: str | None

    def __post_init__(self) -> None:
        _require_identifier(self.block_id, "EvidenceBlock.block_id")
        _require_exact_type(self.type, EvidenceBlockType, "EvidenceBlock.type")
        _require_exact_type(self.content, str, "EvidenceBlock.content")
        _require_optional_string(self.language, "EvidenceBlock.language")
        _require_exact_type(
            self.confidence_status,
            EvidenceConfidenceStatus,
            "EvidenceBlock.confidence_status",
        )
        _require_exact_type(self.state, EvidenceBlockState, "EvidenceBlock.state")
        _require_exact_type(self.page, int, "EvidenceBlock.page")
        _require_exact_type(self.location, EvidenceLocation, "EvidenceBlock.location")
        _require_exact_type(self.reading_order, int, "EvidenceBlock.reading_order")
        _require_optional_string(self.asset_ref, "EvidenceBlock.asset_ref")

        if self.confidence_status is EvidenceConfidenceStatus.UNAVAILABLE:
            if self.confidence is not None:
                raise ValueError(
                    "EvidenceBlock.confidence must be None when confidence_status is UNAVAILABLE."
                )
        else:
            if not (type(self.confidence) is int or type(self.confidence) is float):
                raise TypeError(
                    "EvidenceBlock.confidence must be numeric when confidence_status is PRESENT."
                )
            if not math.isfinite(float(self.confidence)):
                raise ValueError("EvidenceBlock.confidence must be finite.")


@dataclass(frozen=True, slots=True)
class QuestionEvidence:
    question_id: str
    answer_scope_ref: str
    blocks: tuple[EvidenceBlock, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.question_id, "QuestionEvidence.question_id")
        _require_identifier(self.answer_scope_ref, "QuestionEvidence.answer_scope_ref")
        _require_tuple_of(self.blocks, EvidenceBlock, "QuestionEvidence.blocks")
        _require_tuple_of(self.warnings, str, "QuestionEvidence.warnings")


@dataclass(frozen=True, slots=True)
class AnswerEvidenceBundle:
    schema_version: str
    submission_ref: str
    ocr_provenance: str
    questions: tuple[QuestionEvidence, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.schema_version, "AnswerEvidenceBundle.schema_version")
        _require_identifier(self.submission_ref, "AnswerEvidenceBundle.submission_ref")
        _require_identifier(self.ocr_provenance, "AnswerEvidenceBundle.ocr_provenance")
        _require_tuple_of(self.questions, QuestionEvidence, "AnswerEvidenceBundle.questions")

        seen_block_ids: set[str] = set()
        for question in self.questions:
            for block in question.blocks:
                if block.block_id in seen_block_ids:
                    raise ValueError(
                        f"Duplicate evidence block_id within submission: {block.block_id!r}."
                    )
                seen_block_ids.add(block.block_id)
