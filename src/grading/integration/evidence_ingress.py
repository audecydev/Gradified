from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
from typing import Any

from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlock,
    EvidenceBlockState,
    EvidenceBlockType,
    EvidenceConfidenceStatus,
    EvidenceLocation,
    EvidenceLocationStatus,
    QuestionEvidence,
)


__all__ = [
    "NormalizedEvidenceAdmissionPolicy",
    "AdmittedNormalizedEvidence",
    "NormalizedEvidenceIngressError",
    "NormalizedEvidenceResourceError",
    "NormalizedEvidenceMalformedPayloadError",
    "NormalizedEvidenceSchemaError",
    "NormalizedEvidenceUnsupportedSchemaVersionError",
    "InvalidNormalizedEvidenceAdmissionPolicyError",
    "NormalizedEvidenceProvenanceError",
    "parse_normalized_evidence_payload",
]

_SCHEMA_VERSION = "1"


class NormalizedEvidenceIngressError(ValueError):
    """Base class for expected normalized OCR evidence admission normalized-evidence admission rejection."""


class NormalizedEvidenceResourceError(NormalizedEvidenceIngressError):
    """Input exceeded an explicitly supplied admission-resource policy."""


class NormalizedEvidenceMalformedPayloadError(NormalizedEvidenceIngressError):
    """Raw bytes were not one complete strict UTF-8 JSON document."""


class NormalizedEvidenceSchemaError(NormalizedEvidenceIngressError):
    """Syntactically valid JSON violated Normalized Evidence Wire v1."""


class NormalizedEvidenceUnsupportedSchemaVersionError(NormalizedEvidenceSchemaError):
    """The normalized-evidence wire schema version is not supported."""


class InvalidNormalizedEvidenceAdmissionPolicyError(ValueError):
    """Trusted composition supplied an invalid normalized OCR evidence admission admission policy."""


class NormalizedEvidenceProvenanceError(NormalizedEvidenceIngressError):
    """Separately supplied admission provenance metadata is invalid."""


def _require_positive_exact_int(value: object, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise InvalidNormalizedEvidenceAdmissionPolicyError(
            f"{field_name} must be a positive exact int."
        )


def _has_surrounding_whitespace(value: str) -> bool:
    return value != "" and (value[0].isspace() or value[-1].isspace())


def _require_identifier_text(value: object, field_name: str, *, error_type: type[Exception]) -> str:
    if type(value) is not str:
        raise error_type(f"{field_name} must be an exact string.")
    if value == "" or _has_surrounding_whitespace(value):
        raise error_type(
            f"{field_name} must be non-empty without surrounding whitespace."
        )
    return value


@dataclass(frozen=True, slots=True)
class NormalizedEvidenceAdmissionPolicy:
    admission_policy_identity: str
    max_raw_bytes: int
    max_json_depth: int
    max_json_nodes: int
    max_json_number_characters: int
    max_identifier_characters: int
    max_metadata_text_characters: int
    max_block_content_characters: int
    max_total_content_characters: int
    max_questions: int
    max_blocks_per_question: int
    max_total_blocks: int
    max_warnings_per_question: int
    max_location_coordinates: int

    def __post_init__(self) -> None:
        _validate_policy_values(self)


_POLICY_NUMERIC_FIELDS = tuple(
    field.name
    for field in fields(NormalizedEvidenceAdmissionPolicy)
    if field.name != "admission_policy_identity"
)


def _validate_policy_values(policy: NormalizedEvidenceAdmissionPolicy) -> None:
    for field_name in _POLICY_NUMERIC_FIELDS:
        _require_positive_exact_int(getattr(policy, field_name), field_name)
    identity = _require_identifier_text(
        policy.admission_policy_identity,
        "admission_policy_identity",
        error_type=InvalidNormalizedEvidenceAdmissionPolicyError,
    )
    if len(identity) > policy.max_identifier_characters:
        raise InvalidNormalizedEvidenceAdmissionPolicyError(
            "admission_policy_identity exceeds max_identifier_characters."
        )


def _validated_policy_snapshot(policy: object) -> NormalizedEvidenceAdmissionPolicy:
    if type(policy) is not NormalizedEvidenceAdmissionPolicy:
        raise TypeError("policy must be an exact NormalizedEvidenceAdmissionPolicy.")
    _validate_policy_values(policy)
    return NormalizedEvidenceAdmissionPolicy(
        **{field.name: getattr(policy, field.name) for field in fields(type(policy))}
    )


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AdmittedNormalizedEvidence:
    evidence: AnswerEvidenceBundle
    raw_payload_sha256: str
    wire_schema_version: str
    admission_policy_identity: str
    effective_policy_snapshot: NormalizedEvidenceAdmissionPolicy
    source_artifact_ref: str | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "AdmittedNormalizedEvidence instances are created only by "
            "parse_normalized_evidence_payload()."
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("AdmittedNormalizedEvidence cannot be subclassed.")

    def __repr__(self) -> str:
        return (
            "AdmittedNormalizedEvidence("
            f"wire_schema_version={self.wire_schema_version!r}, "
            f"admission_policy_identity={self.admission_policy_identity!r}, "
            f"raw_payload_sha256={self.raw_payload_sha256!r})"
        )

    def __post_init__(self) -> None:
        if type(self.evidence) is not AnswerEvidenceBundle:
            raise TypeError("evidence must be an exact AnswerEvidenceBundle.")
        if type(self.raw_payload_sha256) is not str:
            raise TypeError("raw_payload_sha256 must be an exact string.")
        if (
            len(self.raw_payload_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.raw_payload_sha256)
        ):
            raise ValueError("raw_payload_sha256 must be lowercase SHA-256 hex.")
        if self.wire_schema_version != _SCHEMA_VERSION:
            raise ValueError("Unsupported wire_schema_version.")
        if type(self.effective_policy_snapshot) is not NormalizedEvidenceAdmissionPolicy:
            raise TypeError(
                "effective_policy_snapshot must be an exact "
                "NormalizedEvidenceAdmissionPolicy."
            )
        _validate_policy_values(self.effective_policy_snapshot)
        if self.admission_policy_identity != self.effective_policy_snapshot.admission_policy_identity:
            raise ValueError(
                "admission_policy_identity must match effective_policy_snapshot."
            )
        if self.source_artifact_ref is not None and type(self.source_artifact_ref) is not str:
            raise TypeError("source_artifact_ref must be an exact string or None.")


class _PreflightMalformed(Exception):
    pass


class _PreflightResource(Exception):
    pass


@dataclass(slots=True)
class _ContainerState:
    kind: str
    state: str


class _StrictJsonPreflightScanner:
    """Iteratively validate JSON syntax and bound work before object materialization."""

    __slots__ = (
        "text",
        "length",
        "index",
        "max_depth",
        "max_nodes",
        "max_number_characters",
        "nodes",
        "stack",
        "root_started",
        "root_complete",
    )

    def __init__(
        self,
        text: str,
        *,
        max_depth: int,
        max_nodes: int,
        max_number_characters: int,
    ) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.max_number_characters = max_number_characters
        self.nodes = 0
        self.stack: list[_ContainerState] = []
        self.root_started = False
        self.root_complete = False

    def scan(self) -> None:
        while True:
            self._skip_ws()
            if self.root_complete:
                if self.index != self.length:
                    raise _PreflightMalformed("Trailing data after JSON document.")
                return

            if not self.root_started:
                if self.index >= self.length:
                    raise _PreflightMalformed("Empty JSON payload.")
                self.root_started = True
                if not self._parse_value(depth=1):
                    self.root_complete = True
                continue

            if not self.stack:
                # A root container can only leave the stack by completing.
                self.root_complete = True
                continue

            context = self.stack[-1]
            if context.kind == "object":
                self._step_object(context)
            else:
                self._step_array(context)

    def _skip_ws(self) -> None:
        text = self.text
        index = self.index
        while index < self.length and text[index] in " \t\r\n":
            index += 1
        self.index = index

    def _node(self, depth: int) -> None:
        if depth > self.max_depth:
            raise _PreflightResource("JSON depth exceeds admission policy.")
        self.nodes += 1
        if self.nodes > self.max_nodes:
            raise _PreflightResource("JSON node count exceeds admission policy.")

    def _parse_value(self, *, depth: int) -> bool:
        self._node(depth)
        if self.index >= self.length:
            raise _PreflightMalformed("Expected JSON value.")

        ch = self.text[self.index]
        if ch == "{":
            self.index += 1
            self.stack.append(_ContainerState("object", "key_or_end"))
            return True
        if ch == "[":
            self.index += 1
            self.stack.append(_ContainerState("array", "value_or_end"))
            return True
        if ch == '"':
            self._scan_string()
            return False
        if ch == "-" or ("0" <= ch <= "9"):
            self._scan_number()
            return False
        if self.text.startswith("true", self.index):
            self.index += 4
            return False
        if self.text.startswith("false", self.index):
            self.index += 5
            return False
        if self.text.startswith("null", self.index):
            self.index += 4
            return False
        raise _PreflightMalformed("Invalid JSON value token.")

    def _step_object(self, context: _ContainerState) -> None:
        state = context.state
        if state == "key_or_end":
            if self._consume_if("}"):
                self._finish_container()
                return
            self._require_key(context)
            return
        if state == "key":
            self._require_key(context)
            return
        if state == "colon":
            if not self._consume_if(":"):
                raise _PreflightMalformed("Expected ':' after JSON object key.")
            context.state = "value"
            return
        if state == "value":
            context.state = "comma_or_end"
            self._parse_value(depth=len(self.stack) + 1)
            return
        if state == "comma_or_end":
            if self._consume_if("}"):
                self._finish_container()
                return
            if not self._consume_if(","):
                raise _PreflightMalformed("Expected ',' or '}' in JSON object.")
            context.state = "key"
            return
        raise RuntimeError("Invalid JSON object scanner state.")

    def _require_key(self, context: _ContainerState) -> None:
        if self.index >= self.length or self.text[self.index] != '"':
            raise _PreflightMalformed("JSON object key must be a string.")
        self._scan_string()
        context.state = "colon"

    def _step_array(self, context: _ContainerState) -> None:
        state = context.state
        if state == "value_or_end":
            if self._consume_if("]"):
                self._finish_container()
                return
            context.state = "comma_or_end"
            self._parse_value(depth=len(self.stack) + 1)
            return
        if state == "value":
            context.state = "comma_or_end"
            self._parse_value(depth=len(self.stack) + 1)
            return
        if state == "comma_or_end":
            if self._consume_if("]"):
                self._finish_container()
                return
            if not self._consume_if(","):
                raise _PreflightMalformed("Expected ',' or ']' in JSON array.")
            context.state = "value"
            return
        raise RuntimeError("Invalid JSON array scanner state.")

    def _finish_container(self) -> None:
        self.stack.pop()
        if not self.stack:
            self.root_complete = True

    def _consume_if(self, character: str) -> bool:
        if self.index < self.length and self.text[self.index] == character:
            self.index += 1
            return True
        return False

    def _scan_string(self) -> None:
        # Opening quote.
        self.index += 1
        text = self.text
        while self.index < self.length:
            ch = text[self.index]
            if ch == '"':
                self.index += 1
                return
            if ord(ch) < 0x20:
                raise _PreflightMalformed("Unescaped control character in JSON string.")
            if ch != "\\":
                # Strict UTF-8 decoding prevents raw surrogate code points.
                if 0xD800 <= ord(ch) <= 0xDFFF:
                    raise _PreflightMalformed("Unpaired Unicode surrogate in JSON string.")
                self.index += 1
                continue

            self.index += 1
            if self.index >= self.length:
                raise _PreflightMalformed("Unterminated JSON escape.")
            escape = text[self.index]
            if escape in '"\\/bfnrt':
                self.index += 1
                continue
            if escape != "u":
                raise _PreflightMalformed("Invalid JSON escape.")

            code_unit = self._scan_unicode_escape_code_unit()
            if 0xD800 <= code_unit <= 0xDBFF:
                # JSON surrogate pairs must be adjacent escaped code units.
                if (
                    self.index + 1 >= self.length
                    or text[self.index] != "\\"
                    or text[self.index + 1] != "u"
                ):
                    raise _PreflightMalformed("Unpaired Unicode surrogate in JSON string.")
                self.index += 1  # consume backslash; helper expects index at 'u'
                low = self._scan_unicode_escape_code_unit()
                if not 0xDC00 <= low <= 0xDFFF:
                    raise _PreflightMalformed("Invalid Unicode surrogate pair in JSON string.")
            elif 0xDC00 <= code_unit <= 0xDFFF:
                raise _PreflightMalformed("Unpaired Unicode surrogate in JSON string.")

        raise _PreflightMalformed("Unterminated JSON string.")

    def _scan_unicode_escape_code_unit(self) -> int:
        # self.index points at 'u'.
        if self.index + 4 >= self.length:
            raise _PreflightMalformed("Incomplete JSON unicode escape.")
        digits = self.text[self.index + 1 : self.index + 5]
        if len(digits) != 4 or any(ch not in "0123456789abcdefABCDEF" for ch in digits):
            raise _PreflightMalformed("Invalid JSON unicode escape.")
        self.index += 5
        return int(digits, 16)

    def _scan_number(self) -> None:
        start = self.index
        text = self.text
        index = self.index

        if text[index] == "-":
            index += 1
            if index >= self.length:
                raise _PreflightMalformed("Invalid JSON number.")

        if text[index] == "0":
            index += 1
            if index < self.length and "0" <= text[index] <= "9":
                raise _PreflightMalformed("Leading zero in JSON number.")
        elif "1" <= text[index] <= "9":
            index += 1
            while index < self.length and "0" <= text[index] <= "9":
                index += 1
        else:
            raise _PreflightMalformed("Invalid JSON number.")

        if index < self.length and text[index] == ".":
            index += 1
            fraction_start = index
            while index < self.length and "0" <= text[index] <= "9":
                index += 1
            if index == fraction_start:
                raise _PreflightMalformed("Invalid JSON fraction.")

        if index < self.length and text[index] in "eE":
            index += 1
            if index < self.length and text[index] in "+-":
                index += 1
            exponent_start = index
            while index < self.length and "0" <= text[index] <= "9":
                index += 1
            if index == exponent_start:
                raise _PreflightMalformed("Invalid JSON exponent.")

        if index - start > self.max_number_characters:
            raise _PreflightResource("JSON number token exceeds admission policy.")
        self.index = index


@dataclass(frozen=True, slots=True)
class _JsonNumber:
    raw: str


class _DuplicateKeyError(Exception):
    pass


class _NonStandardConstantError(Exception):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _NonStandardConstantError


def _decode_json(text: str) -> Any:
    failure: str | None = None
    document: Any = None
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_int=_JsonNumber,
            parse_float=_JsonNumber,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError:
        failure = "duplicate"
    except _NonStandardConstantError:
        failure = "constant"
    except RecursionError:
        failure = "recursion"
    except json.JSONDecodeError:
        # JSONDecodeError retains the complete decoded document.  Translate only
        # after leaving the except block so it cannot become exception context.
        failure = "malformed"

    if failure == "duplicate":
        raise NormalizedEvidenceSchemaError("Duplicate JSON object key.")
    if failure == "constant":
        raise NormalizedEvidenceMalformedPayloadError(
            "Payload contains a non-standard JSON numeric constant."
        )
    if failure == "recursion":
        raise NormalizedEvidenceResourceError(
            "JSON nesting exceeded runtime materialization safety."
        )
    if failure == "malformed":
        raise NormalizedEvidenceMalformedPayloadError(
            "Payload is not one valid JSON document."
        )
    return document


def _require_object(value: object, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise NormalizedEvidenceSchemaError(f"{path} must be a JSON object.")
    return value


def _require_array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise NormalizedEvidenceSchemaError(f"{path} must be a JSON array.")
    return value


def _require_string(value: object, path: str) -> str:
    if type(value) is not str:
        raise NormalizedEvidenceSchemaError(f"{path} must be a JSON string.")
    return value


def _require_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise NormalizedEvidenceSchemaError(f"{path} has missing or unknown fields.")


def _require_identifier(
    value: object,
    *,
    path: str,
    policy: NormalizedEvidenceAdmissionPolicy,
) -> str:
    text = _require_string(value, path)
    if len(text) > policy.max_identifier_characters:
        raise NormalizedEvidenceResourceError(f"{path} exceeds max_identifier_characters.")
    if text == "" or _has_surrounding_whitespace(text):
        raise NormalizedEvidenceSchemaError(
            f"{path} must be non-empty without surrounding whitespace."
        )
    return text


def _require_metadata_text(
    value: object,
    *,
    path: str,
    policy: NormalizedEvidenceAdmissionPolicy,
    allow_null: bool,
    allow_empty: bool,
) -> str | None:
    if value is None:
        if allow_null:
            return None
        raise NormalizedEvidenceSchemaError(f"{path} cannot be null.")
    text = _require_string(value, path)
    if not allow_empty and text == "":
        raise NormalizedEvidenceSchemaError(f"{path} cannot be empty.")
    if len(text) > policy.max_metadata_text_characters:
        raise NormalizedEvidenceResourceError(
            f"{path} exceeds max_metadata_text_characters."
        )
    return text


def _json_number_is_integer(number: _JsonNumber) -> bool:
    return "." not in number.raw and "e" not in number.raw and "E" not in number.raw


def _exact_int_from_json_number(value: object, path: str) -> int:
    if type(value) is not _JsonNumber or not _json_number_is_integer(value):
        raise NormalizedEvidenceSchemaError(f"{path} must be an exact JSON integer token.")
    raw = value.raw
    negative = raw.startswith("-")
    digits = raw[1:] if negative else raw
    # Chunked conversion avoids Python's decimal-string conversion digit ceiling while
    # preserving the exact integer authorized by the caller-supplied lexical bound.
    result = 0
    for start in range(0, len(digits), 9):
        chunk = digits[start : start + 9]
        result = result * (10 ** len(chunk)) + int(chunk)
    return -result if negative else result


def _finite_number_from_json(value: object, path: str) -> int | float:
    if type(value) is not _JsonNumber:
        raise NormalizedEvidenceSchemaError(f"{path} must be a JSON number.")
    if _json_number_is_integer(value):
        number: int | float = _exact_int_from_json_number(value, path)
    else:
        try:
            number = float(value.raw)
        except (ValueError, OverflowError):
            raise NormalizedEvidenceSchemaError(f"{path} must be a finite JSON number.") from None
        if not math.isfinite(number):
            raise NormalizedEvidenceSchemaError(f"{path} must be a finite JSON number.")
    return number


def _ensure_domain_finite(value: int | float, path: str) -> None:
    # Frozen EvidenceBlock/EvidenceLocation convert numeric values to float to check
    # finiteness. Translate values they cannot represent into a wire-schema failure
    # instead of leaking OverflowError from domain construction.
    try:
        finite = math.isfinite(float(value))
    except OverflowError:
        finite = False
    if not finite:
        raise NormalizedEvidenceSchemaError(f"{path} must be representable as a finite number.")


def _enum_value(enum_type: type, value: object, path: str):
    text = _require_string(value, path)
    for member in enum_type:
        if member.value == text:
            return member
    raise NormalizedEvidenceSchemaError(f"{path} has an unsupported enum value.")


def _validate_location(
    value: object,
    *,
    path: str,
    policy: NormalizedEvidenceAdmissionPolicy,
) -> EvidenceLocation:
    obj = _require_object(value, path)
    _require_keys(obj, {"status", "bbox"}, path)
    status = _enum_value(EvidenceLocationStatus, obj["status"], f"{path}.status")
    bbox_value = obj["bbox"]
    bbox: tuple[int | float, ...] | None
    if bbox_value is None:
        bbox = None
    else:
        items = _require_array(bbox_value, f"{path}.bbox")
        if len(items) > policy.max_location_coordinates:
            raise NormalizedEvidenceResourceError(
                f"{path}.bbox exceeds max_location_coordinates."
            )
        numbers: list[int | float] = []
        for index, item in enumerate(items):
            number = _finite_number_from_json(item, f"{path}.bbox[{index}]")
            _ensure_domain_finite(number, f"{path}.bbox[{index}]")
            numbers.append(number)
        bbox = tuple(numbers)
    return EvidenceLocation(status=status, bbox=bbox)


def _validate_block(
    value: object,
    *,
    path: str,
    policy: NormalizedEvidenceAdmissionPolicy,
) -> EvidenceBlock:
    obj = _require_object(value, path)
    _require_keys(
        obj,
        {
            "block_id",
            "type",
            "content",
            "language",
            "confidence",
            "confidence_status",
            "state",
            "page",
            "location",
            "reading_order",
            "asset_ref",
        },
        path,
    )

    block_id = _require_identifier(obj["block_id"], path=f"{path}.block_id", policy=policy)
    block_type = _enum_value(EvidenceBlockType, obj["type"], f"{path}.type")
    content = _require_string(obj["content"], f"{path}.content")
    if len(content) > policy.max_block_content_characters:
        raise NormalizedEvidenceResourceError(
            f"{path}.content exceeds max_block_content_characters."
        )
    language = _require_metadata_text(
        obj["language"],
        path=f"{path}.language",
        policy=policy,
        allow_null=True,
        allow_empty=False,
    )
    confidence_status = _enum_value(
        EvidenceConfidenceStatus,
        obj["confidence_status"],
        f"{path}.confidence_status",
    )
    if confidence_status is EvidenceConfidenceStatus.UNAVAILABLE:
        if obj["confidence"] is not None:
            raise NormalizedEvidenceSchemaError(
                f"{path}.confidence must be null when confidence_status is UNAVAILABLE."
            )
        confidence: int | float | None = None
    else:
        confidence = _finite_number_from_json(obj["confidence"], f"{path}.confidence")
        _ensure_domain_finite(confidence, f"{path}.confidence")

    state = _enum_value(EvidenceBlockState, obj["state"], f"{path}.state")
    page = _exact_int_from_json_number(obj["page"], f"{path}.page")
    location = _validate_location(obj["location"], path=f"{path}.location", policy=policy)
    reading_order = _exact_int_from_json_number(
        obj["reading_order"], f"{path}.reading_order"
    )
    asset_ref = _require_metadata_text(
        obj["asset_ref"],
        path=f"{path}.asset_ref",
        policy=policy,
        allow_null=True,
        allow_empty=False,
    )

    return EvidenceBlock(
        block_id=block_id,
        type=block_type,
        content=content,
        language=language,
        confidence=confidence,
        confidence_status=confidence_status,
        state=state,
        page=page,
        location=location,
        reading_order=reading_order,
        asset_ref=asset_ref,
    )


def _validate_document(
    document: object,
    policy: NormalizedEvidenceAdmissionPolicy,
) -> AnswerEvidenceBundle:
    root = _require_object(document, "root")
    _require_keys(root, {"schema_version", "submission_ref", "ocr_provenance", "questions"}, "root")

    schema_version = _require_string(root["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise NormalizedEvidenceUnsupportedSchemaVersionError(
            "Unsupported normalized evidence schema_version."
        )

    submission_ref = _require_identifier(
        root["submission_ref"], path="submission_ref", policy=policy
    )
    ocr_provenance = _require_identifier(
        root["ocr_provenance"], path="ocr_provenance", policy=policy
    )
    questions_value = _require_array(root["questions"], "questions")
    if len(questions_value) > policy.max_questions:
        raise NormalizedEvidenceResourceError("questions exceeds max_questions.")

    seen_question_ids: set[str] = set()
    seen_block_ids: set[str] = set()
    questions: list[QuestionEvidence] = []
    total_blocks = 0
    total_content_characters = 0

    for q_index, question_value in enumerate(questions_value):
        path = f"questions[{q_index}]"
        question = _require_object(question_value, path)
        _require_keys(question, {"question_id", "answer_scope_ref", "blocks", "warnings"}, path)
        question_id = _require_identifier(
            question["question_id"], path=f"{path}.question_id", policy=policy
        )
        if question_id in seen_question_ids:
            raise NormalizedEvidenceSchemaError("Duplicate question_id within normalized evidence.")
        seen_question_ids.add(question_id)
        answer_scope_ref = _require_identifier(
            question["answer_scope_ref"], path=f"{path}.answer_scope_ref", policy=policy
        )

        blocks_value = _require_array(question["blocks"], f"{path}.blocks")
        if len(blocks_value) > policy.max_blocks_per_question:
            raise NormalizedEvidenceResourceError(
                f"{path}.blocks exceeds max_blocks_per_question."
            )
        total_blocks += len(blocks_value)
        if total_blocks > policy.max_total_blocks:
            raise NormalizedEvidenceResourceError("blocks exceeds max_total_blocks.")

        blocks: list[EvidenceBlock] = []
        for b_index, block_value in enumerate(blocks_value):
            block = _validate_block(
                block_value,
                path=f"{path}.blocks[{b_index}]",
                policy=policy,
            )
            if block.block_id in seen_block_ids:
                raise NormalizedEvidenceSchemaError(
                    "Duplicate block_id within normalized evidence."
                )
            seen_block_ids.add(block.block_id)
            total_content_characters += len(block.content)
            if total_content_characters > policy.max_total_content_characters:
                raise NormalizedEvidenceResourceError(
                    "block content exceeds max_total_content_characters."
                )
            blocks.append(block)

        warnings_value = _require_array(question["warnings"], f"{path}.warnings")
        if len(warnings_value) > policy.max_warnings_per_question:
            raise NormalizedEvidenceResourceError(
                f"{path}.warnings exceeds max_warnings_per_question."
            )
        warnings: list[str] = []
        for w_index, warning_value in enumerate(warnings_value):
            warning = _require_metadata_text(
                warning_value,
                path=f"{path}.warnings[{w_index}]",
                policy=policy,
                allow_null=False,
                allow_empty=False,
            )
            assert warning is not None
            warnings.append(warning)

        questions.append(
            QuestionEvidence(
                question_id=question_id,
                answer_scope_ref=answer_scope_ref,
                blocks=tuple(blocks),
                warnings=tuple(warnings),
            )
        )

    return AnswerEvidenceBundle(
        schema_version=schema_version,
        submission_ref=submission_ref,
        ocr_provenance=ocr_provenance,
        questions=tuple(questions),
    )


def _validate_source_artifact_ref(
    source_artifact_ref: object,
    policy: NormalizedEvidenceAdmissionPolicy,
) -> str | None:
    if source_artifact_ref is None:
        return None
    if type(source_artifact_ref) is not str:
        raise NormalizedEvidenceProvenanceError(
            "source_artifact_ref must be an exact string."
        )
    if len(source_artifact_ref) > policy.max_identifier_characters:
        raise NormalizedEvidenceResourceError(
            "source_artifact_ref exceeds max_identifier_characters."
        )
    if source_artifact_ref == "" or _has_surrounding_whitespace(source_artifact_ref):
        raise NormalizedEvidenceProvenanceError(
            "source_artifact_ref must be non-empty without surrounding whitespace."
        )
    return source_artifact_ref


def parse_normalized_evidence_payload(
    *,
    raw_payload: bytes,
    policy: NormalizedEvidenceAdmissionPolicy,
    source_artifact_ref: str | None = None,
) -> AdmittedNormalizedEvidence:
    """Structurally admit one exact Normalized Evidence Wire v1 payload.

    This normalized OCR evidence admission boundary does not authenticate the caller, establish tenant or OCR
    completeness, select an evaluator, bind a grading run, or create grading
    authority.  The policy and optional source artifact reference are supplied
    separately by surrounding composition and cannot be selected by wire data.
    """

    if type(raw_payload) is not bytes:
        raise TypeError("raw_payload must be exact bytes.")

    snapshot = _validated_policy_snapshot(policy)
    artifact_ref = _validate_source_artifact_ref(source_artifact_ref, snapshot)

    if len(raw_payload) > snapshot.max_raw_bytes:
        raise NormalizedEvidenceResourceError("Payload exceeds max_raw_bytes.")

    raw_payload_sha256 = hashlib.sha256(raw_payload).hexdigest()

    text: str | None = None
    try:
        text = raw_payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        # UnicodeDecodeError retains the original bytes.  Raise only after the
        # handler exits so rejected student content is not exception context.
        pass
    if text is None:
        raise NormalizedEvidenceMalformedPayloadError("Payload is not valid UTF-8.")

    scanner = _StrictJsonPreflightScanner(
        text,
        max_depth=snapshot.max_json_depth,
        max_nodes=snapshot.max_json_nodes,
        max_number_characters=snapshot.max_json_number_characters,
    )
    preflight_failure: tuple[str, str] | None = None
    try:
        scanner.scan()
    except _PreflightResource as exc:
        # _PreflightResource traceback frames retain the scanner, which retains
        # the complete decoded payload.  Translate only after leaving the
        # except block so the public error has no payload-bearing context.
        preflight_failure = ("resource", str(exc))
    except _PreflightMalformed as exc:
        # Same privacy rule for malformed-input failures.
        preflight_failure = ("malformed", str(exc))

    if preflight_failure is not None:
        failure_kind, failure_message = preflight_failure
        if failure_kind == "resource":
            raise NormalizedEvidenceResourceError(failure_message)
        raise NormalizedEvidenceMalformedPayloadError(failure_message)

    document = _decode_json(text)
    evidence = _validate_document(document, snapshot)

    admitted = object.__new__(AdmittedNormalizedEvidence)
    object.__setattr__(admitted, "evidence", evidence)
    object.__setattr__(admitted, "raw_payload_sha256", raw_payload_sha256)
    object.__setattr__(admitted, "wire_schema_version", _SCHEMA_VERSION)
    object.__setattr__(admitted, "admission_policy_identity", snapshot.admission_policy_identity)
    object.__setattr__(admitted, "effective_policy_snapshot", snapshot)
    object.__setattr__(admitted, "source_artifact_ref", artifact_ref)
    admitted.__post_init__()
    return admitted
