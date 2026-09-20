from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from grading.contracts.errors import (
    InvalidScoringValueError,
    ScoringNumericEnvelopeError,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.generator import RubricGenerationProposal
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterion,
    AuthoringCriterionCondition,
    AuthoringDeductionRule,
    AuthoringGateRule,
    AuthoringPerformanceLevel,
    AuthoringPositiveCreditDependencyRule,
    RubricCompilationLimits,
)


__all__ = [
    "RubricProviderIngressLimits",
    "RubricProviderProvenance",
    "AdmittedRubricProviderProposal",
    "RubricProviderIngressError",
    "RubricProviderResourceError",
    "RubricProviderMalformedResponseError",
    "RubricProviderSchemaError",
    "parse_rubric_provider_payload",
]

_INGRESS_PROFILE_VERSION = "1"
_SCHEMA_VERSION = "1"


class RubricProviderIngressError(ValueError):
    """Base class for expected provider-ingress rejection."""


class RubricProviderResourceError(RubricProviderIngressError):
    """Provider payload exceeded an explicit ingress/resource policy."""


class RubricProviderMalformedResponseError(RubricProviderIngressError):
    """Provider bytes were not one complete strict UTF-8 JSON document."""


class RubricProviderSchemaError(RubricProviderIngressError):
    """Provider JSON was syntactically valid but violated the closed schema."""


def _require_positive_exact_int(value: object, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive exact int.")


def _require_exact_nonempty_str(value: object, field_name: str) -> None:
    if type(value) is not str or value == "":
        raise ValueError(f"{field_name} must be a non-empty exact str.")


@dataclass(frozen=True, slots=True)
class RubricProviderIngressLimits:
    max_raw_bytes: int
    max_json_depth: int
    max_json_nodes: int
    max_provenance_text_characters: int
    compilation_limits: RubricCompilationLimits

    def __post_init__(self) -> None:
        _require_positive_exact_int(self.max_raw_bytes, "max_raw_bytes")
        _require_positive_exact_int(self.max_json_depth, "max_json_depth")
        _require_positive_exact_int(self.max_json_nodes, "max_json_nodes")
        _require_positive_exact_int(
            self.max_provenance_text_characters,
            "max_provenance_text_characters",
        )
        if type(self.compilation_limits) is not RubricCompilationLimits:
            raise TypeError("compilation_limits must be an exact RubricCompilationLimits.")


@dataclass(frozen=True, slots=True)
class RubricProviderProvenance:
    provider_id: str
    model_id: str

    def __post_init__(self) -> None:
        _require_exact_nonempty_str(self.provider_id, "provider_id")
        _require_exact_nonempty_str(self.model_id, "model_id")


@dataclass(frozen=True, slots=True, init=False)
class AdmittedRubricProviderProposal:
    proposal: RubricGenerationProposal
    provenance: RubricProviderProvenance
    raw_payload_sha256: str
    schema_version: str
    ingress_profile_version: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "AdmittedRubricProviderProposal instances are created only by "
            "parse_rubric_provider_payload()."
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("AdmittedRubricProviderProposal cannot be subclassed.")

    def __post_init__(self) -> None:
        if type(self.proposal) is not RubricGenerationProposal:
            raise TypeError("proposal must be an exact RubricGenerationProposal.")
        if type(self.provenance) is not RubricProviderProvenance:
            raise TypeError("provenance must be an exact RubricProviderProvenance.")
        if type(self.raw_payload_sha256) is not str:
            raise TypeError("raw_payload_sha256 must be an exact str.")
        if (
            len(self.raw_payload_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.raw_payload_sha256)
        ):
            raise ValueError("raw_payload_sha256 must be lowercase SHA-256 hex.")
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("Unsupported schema_version.")
        if self.ingress_profile_version != _INGRESS_PROFILE_VERSION:
            raise ValueError("Unsupported ingress_profile_version.")


class _PreflightMalformed(Exception):
    pass


class _PreflightResource(Exception):
    pass


class _JsonResourceScanner:
    """Validate strict JSON shape while bounding depth/nodes before object creation."""

    __slots__ = ("text", "length", "index", "max_depth", "max_nodes", "nodes")

    def __init__(self, text: str, *, max_depth: int, max_nodes: int) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.nodes = 0

    def scan(self) -> None:
        self._skip_ws()
        if self.index >= self.length:
            raise _PreflightMalformed("Empty JSON payload.")
        try:
            self._value(1)
        except RecursionError as exc:
            raise _PreflightResource("JSON nesting exhausted parser recursion.") from exc
        self._skip_ws()
        if self.index != self.length:
            raise _PreflightMalformed("Trailing data after JSON document.")

    def _node(self, depth: int) -> None:
        if depth > self.max_depth:
            raise _PreflightResource("JSON depth exceeds ingress limit.")
        self.nodes += 1
        if self.nodes > self.max_nodes:
            raise _PreflightResource("JSON node count exceeds ingress limit.")

    def _skip_ws(self) -> None:
        text = self.text
        length = self.length
        index = self.index
        while index < length and text[index] in " \t\r\n":
            index += 1
        self.index = index

    def _value(self, depth: int) -> None:
        self._node(depth)
        if self.index >= self.length:
            raise _PreflightMalformed("Expected JSON value.")
        ch = self.text[self.index]
        if ch == "{":
            self._object(depth)
            return
        if ch == "[":
            self._array(depth)
            return
        if ch == '"':
            self._string()
            return
        if ch == "-" or ("0" <= ch <= "9"):
            self._number()
            return
        if self.text.startswith("true", self.index):
            self.index += 4
            return
        if self.text.startswith("false", self.index):
            self.index += 5
            return
        if self.text.startswith("null", self.index):
            self.index += 4
            return
        raise _PreflightMalformed("Invalid JSON value token.")

    def _object(self, depth: int) -> None:
        self.index += 1
        self._skip_ws()
        if self.index < self.length and self.text[self.index] == "}":
            self.index += 1
            return
        while True:
            if self.index >= self.length or self.text[self.index] != '"':
                raise _PreflightMalformed("JSON object key must be a string.")
            self._string()
            self._skip_ws()
            if self.index >= self.length or self.text[self.index] != ":":
                raise _PreflightMalformed("Expected ':' after JSON object key.")
            self.index += 1
            self._skip_ws()
            self._value(depth + 1)
            self._skip_ws()
            if self.index >= self.length:
                raise _PreflightMalformed("Unterminated JSON object.")
            ch = self.text[self.index]
            if ch == "}":
                self.index += 1
                return
            if ch != ",":
                raise _PreflightMalformed("Expected ',' or '}' in JSON object.")
            self.index += 1
            self._skip_ws()

    def _array(self, depth: int) -> None:
        self.index += 1
        self._skip_ws()
        if self.index < self.length and self.text[self.index] == "]":
            self.index += 1
            return
        while True:
            self._value(depth + 1)
            self._skip_ws()
            if self.index >= self.length:
                raise _PreflightMalformed("Unterminated JSON array.")
            ch = self.text[self.index]
            if ch == "]":
                self.index += 1
                return
            if ch != ",":
                raise _PreflightMalformed("Expected ',' or ']' in JSON array.")
            self.index += 1
            self._skip_ws()

    def _string(self) -> None:
        self.index += 1
        text = self.text
        length = self.length
        while self.index < length:
            ch = text[self.index]
            if ch == '"':
                self.index += 1
                return
            if ord(ch) < 0x20:
                raise _PreflightMalformed("Unescaped control character in JSON string.")
            if ch == "\\":
                self.index += 1
                if self.index >= length:
                    raise _PreflightMalformed("Unterminated JSON escape.")
                escape = text[self.index]
                if escape == "u":
                    if self.index + 4 >= length:
                        raise _PreflightMalformed("Incomplete JSON unicode escape.")
                    digits = text[self.index + 1 : self.index + 5]
                    if len(digits) != 4 or any(
                        character not in "0123456789abcdefABCDEF" for character in digits
                    ):
                        raise _PreflightMalformed("Invalid JSON unicode escape.")
                    self.index += 5
                    continue
                if escape not in '"\\/bfnrt':
                    raise _PreflightMalformed("Invalid JSON escape.")
            self.index += 1
        raise _PreflightMalformed("Unterminated JSON string.")

    def _number(self) -> None:
        text = self.text
        length = self.length
        index = self.index
        if text[index] == "-":
            index += 1
            if index >= length:
                raise _PreflightMalformed("Invalid JSON number.")
        if text[index] == "0":
            index += 1
            if index < length and "0" <= text[index] <= "9":
                raise _PreflightMalformed("Leading zero in JSON number.")
        elif "1" <= text[index] <= "9":
            index += 1
            while index < length and "0" <= text[index] <= "9":
                index += 1
        else:
            raise _PreflightMalformed("Invalid JSON number.")
        if index < length and text[index] == ".":
            index += 1
            start = index
            while index < length and "0" <= text[index] <= "9":
                index += 1
            if index == start:
                raise _PreflightMalformed("Invalid JSON fraction.")
        if index < length and text[index] in "eE":
            index += 1
            if index < length and text[index] in "+-":
                index += 1
            start = index
            while index < length and "0" <= text[index] <= "9":
                index += 1
            if index == start:
                raise _PreflightMalformed("Invalid JSON exponent.")
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
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _NonStandardConstantError(value)


def _decode_json(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_int=_JsonNumber,
            parse_float=_JsonNumber,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError as exc:
        raise RubricProviderSchemaError("Duplicate JSON object key.") from exc
    except _NonStandardConstantError as exc:
        raise RubricProviderMalformedResponseError(
            "Provider response contains a non-standard JSON constant."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RubricProviderMalformedResponseError(
            "Provider response is not one valid JSON document."
        ) from exc


def _require_object(value: object, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RubricProviderSchemaError(f"{path} must be a JSON object.")
    return value


def _require_array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise RubricProviderSchemaError(f"{path} must be a JSON array.")
    return value


def _require_string(value: object, path: str) -> str:
    if type(value) is not str:
        raise RubricProviderSchemaError(f"{path} must be a JSON string.")
    return value


def _require_number(value: object, path: str) -> _JsonNumber:
    if type(value) is not _JsonNumber:
        raise RubricProviderSchemaError(f"{path} must be a JSON number.")
    return value


def _require_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        raise RubricProviderSchemaError(f"{path} has missing or unknown fields.")


def _check_text(value: str, *, path: str, limit: int) -> None:
    if len(value) > limit:
        raise RubricProviderResourceError(f"{path} exceeds the text-field limit.")


def _validate_condition(
    value: object,
    *,
    path: str,
    limits: RubricCompilationLimits,
) -> None:
    obj = _require_object(value, path)
    _require_keys(obj, {"criterion_id", "allowed_level_ids"}, path)
    criterion_id = _require_string(obj["criterion_id"], f"{path}.criterion_id")
    _check_text(
        criterion_id,
        path=f"{path}.criterion_id",
        limit=limits.max_text_characters_per_field,
    )
    allowed = _require_array(obj["allowed_level_ids"], f"{path}.allowed_level_ids")
    if len(allowed) > limits.max_allowed_level_ids_per_condition:
        raise RubricProviderResourceError(
            f"{path}.allowed_level_ids exceeds the allowed-level cardinality limit."
        )
    for index, level_id in enumerate(allowed):
        text = _require_string(level_id, f"{path}.allowed_level_ids[{index}]")
        _check_text(
            text,
            path=f"{path}.allowed_level_ids[{index}]",
            limit=limits.max_text_characters_per_field,
        )


def _validate_criterion(
    value: object,
    *,
    path: str,
    limits: RubricCompilationLimits,
) -> None:
    obj = _require_object(value, path)
    _require_keys(
        obj,
        {
            "criterion_id",
            "operational_description",
            "evidence_requirement",
            "performance_levels",
            "accepted_equivalents",
        },
        path,
    )
    for field_name in (
        "criterion_id",
        "operational_description",
        "evidence_requirement",
    ):
        text = _require_string(obj[field_name], f"{path}.{field_name}")
        _check_text(
            text,
            path=f"{path}.{field_name}",
            limit=limits.max_text_characters_per_field,
        )

    levels = _require_array(obj["performance_levels"], f"{path}.performance_levels")
    if len(levels) > limits.max_levels_per_criterion:
        raise RubricProviderResourceError(
            f"{path}.performance_levels exceeds the performance-level limit."
        )
    for level_index, level_value in enumerate(levels):
        level_path = f"{path}.performance_levels[{level_index}]"
        level = _require_object(level_value, level_path)
        _require_keys(
            level,
            {"level_id", "operational_description", "contribution"},
            level_path,
        )
        for field_name in ("level_id", "operational_description"):
            text = _require_string(level[field_name], f"{level_path}.{field_name}")
            _check_text(
                text,
                path=f"{level_path}.{field_name}",
                limit=limits.max_text_characters_per_field,
            )
        _require_number(level["contribution"], f"{level_path}.contribution")

    equivalents = _require_array(
        obj["accepted_equivalents"],
        f"{path}.accepted_equivalents",
    )
    if len(equivalents) > limits.max_accepted_equivalents_per_criterion:
        raise RubricProviderResourceError(
            f"{path}.accepted_equivalents exceeds the accepted-equivalent limit."
        )
    for equivalent_index, equivalent in enumerate(equivalents):
        text = _require_string(
            equivalent,
            f"{path}.accepted_equivalents[{equivalent_index}]",
        )
        _check_text(
            text,
            path=f"{path}.accepted_equivalents[{equivalent_index}]",
            limit=limits.max_text_characters_per_field,
        )


def _validate_rule_text(value: dict[str, Any], field_name: str, path: str, limit: int) -> None:
    text = _require_string(value[field_name], f"{path}.{field_name}")
    _check_text(text, path=f"{path}.{field_name}", limit=limit)


def _validate_conditions(
    value: object,
    *,
    path: str,
    limits: RubricCompilationLimits,
) -> None:
    conditions = _require_array(value, path)
    if len(conditions) > limits.max_conditions_per_rule:
        raise RubricProviderResourceError(f"{path} exceeds the condition-count limit.")
    for index, condition in enumerate(conditions):
        _validate_condition(condition, path=f"{path}[{index}]", limits=limits)


def _validate_document(document: object, limits: RubricCompilationLimits) -> dict[str, Any]:
    root = _require_object(document, "root")
    _require_keys(
        root,
        {
            "schema_version",
            "criteria",
            "positive_credit_dependencies",
            "gates",
            "caps",
            "deductions",
        },
        "root",
    )
    schema_version = _require_string(root["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise RubricProviderSchemaError("Unsupported rubric provider schema_version.")

    criteria = _require_array(root["criteria"], "criteria")
    dependencies = _require_array(
        root["positive_credit_dependencies"],
        "positive_credit_dependencies",
    )
    gates = _require_array(root["gates"], "gates")
    caps = _require_array(root["caps"], "caps")
    deductions = _require_array(root["deductions"], "deductions")

    if len(criteria) > limits.max_criteria:
        raise RubricProviderResourceError("criteria exceeds the criterion-count limit.")
    if sum(len(group) for group in (dependencies, gates, caps, deductions)) > limits.max_rules:
        raise RubricProviderResourceError("scoring rules exceed the total rule-count limit.")

    for index, criterion in enumerate(criteria):
        _validate_criterion(criterion, path=f"criteria[{index}]", limits=limits)

    state_count = 1 if criteria else 0
    for criterion in criteria:
        levels = criterion["performance_levels"]
        if len(levels) == 0:
            state_count = 0
            break
        if state_count > limits.max_reconciliation_states // len(levels):
            raise RubricProviderResourceError(
                "criterion performance-level state space exceeds the reconciliation limit."
            )
        state_count *= len(levels)

    for index, value in enumerate(dependencies):
        path = f"positive_credit_dependencies[{index}]"
        obj = _require_object(value, path)
        _require_keys(
            obj,
            {"rule_id", "target_criterion_id", "prerequisite_conditions"},
            path,
        )
        _validate_rule_text(obj, "rule_id", path, limits.max_text_characters_per_field)
        _validate_rule_text(
            obj,
            "target_criterion_id",
            path,
            limits.max_text_characters_per_field,
        )
        _validate_conditions(
            obj["prerequisite_conditions"],
            path=f"{path}.prerequisite_conditions",
            limits=limits,
        )

    rule_specs = (
        ("gates", gates, "required_conditions", "failure_ceiling"),
        ("caps", caps, "trigger_conditions", "ceiling"),
        ("deductions", deductions, "trigger_conditions", "amount"),
    )
    for group_name, group, conditions_name, numeric_name in rule_specs:
        for index, value in enumerate(group):
            path = f"{group_name}[{index}]"
            obj = _require_object(value, path)
            _require_keys(obj, {"rule_id", conditions_name, numeric_name}, path)
            _validate_rule_text(obj, "rule_id", path, limits.max_text_characters_per_field)
            _validate_conditions(
                obj[conditions_name],
                path=f"{path}.{conditions_name}",
                limits=limits,
            )
            _require_number(obj[numeric_name], f"{path}.{numeric_name}")

    return root


def _scoring_decimal(number: _JsonNumber, path: str) -> ScoringDecimal:
    try:
        return ScoringDecimal.from_raw(number.raw)
    except ScoringNumericEnvelopeError as exc:
        raise RubricProviderResourceError(
            f"{path} exceeds Numeric Profile v1 representation limits."
        ) from exc
    except InvalidScoringValueError as exc:
        raise RubricProviderSchemaError(f"{path} is not an admitted scoring value.") from exc


def _build_condition(value: dict[str, Any]) -> AuthoringCriterionCondition:
    return AuthoringCriterionCondition(
        criterion_id=value["criterion_id"],
        allowed_level_ids=tuple(value["allowed_level_ids"]),
    )


def _build_criterion(value: dict[str, Any], index: int) -> AuthoringCriterion:
    return AuthoringCriterion(
        criterion_id=value["criterion_id"],
        operational_description=value["operational_description"],
        evidence_requirement=value["evidence_requirement"],
        performance_levels=tuple(
            AuthoringPerformanceLevel(
                level_id=level["level_id"],
                operational_description=level["operational_description"],
                contribution=_scoring_decimal(
                    level["contribution"],
                    f"criteria[{index}].performance_levels[{level_index}].contribution",
                ),
            )
            for level_index, level in enumerate(value["performance_levels"])
        ),
        accepted_equivalents=tuple(value["accepted_equivalents"]),
    )


def _build_proposal(document: dict[str, Any]) -> RubricGenerationProposal:
    return RubricGenerationProposal(
        criteria=tuple(
            _build_criterion(criterion, index)
            for index, criterion in enumerate(document["criteria"])
        ),
        positive_credit_dependencies=tuple(
            AuthoringPositiveCreditDependencyRule(
                rule_id=rule["rule_id"],
                target_criterion_id=rule["target_criterion_id"],
                prerequisite_conditions=tuple(
                    _build_condition(condition)
                    for condition in rule["prerequisite_conditions"]
                ),
            )
            for rule in document["positive_credit_dependencies"]
        ),
        gates=tuple(
            AuthoringGateRule(
                rule_id=rule["rule_id"],
                required_conditions=tuple(
                    _build_condition(condition) for condition in rule["required_conditions"]
                ),
                failure_ceiling=_scoring_decimal(
                    rule["failure_ceiling"],
                    f"gates[{index}].failure_ceiling",
                ),
            )
            for index, rule in enumerate(document["gates"])
        ),
        caps=tuple(
            AuthoringCapRule(
                rule_id=rule["rule_id"],
                trigger_conditions=tuple(
                    _build_condition(condition) for condition in rule["trigger_conditions"]
                ),
                ceiling=_scoring_decimal(rule["ceiling"], f"caps[{index}].ceiling"),
            )
            for index, rule in enumerate(document["caps"])
        ),
        deductions=tuple(
            AuthoringDeductionRule(
                rule_id=rule["rule_id"],
                trigger_conditions=tuple(
                    _build_condition(condition) for condition in rule["trigger_conditions"]
                ),
                amount=_scoring_decimal(rule["amount"], f"deductions[{index}].amount"),
            )
            for index, rule in enumerate(document["deductions"])
        ),
    )


def parse_rubric_provider_payload(
    *,
    raw_payload: bytes,
    limits: RubricProviderIngressLimits,
    provenance: RubricProviderProvenance,
) -> AdmittedRubricProviderProposal:
    """Admit one exact provider-produced rubric JSON document as an untrusted proposal.

    This boundary performs no generation-source composition, compilation, approval,
    activation, or reducer-authority construction.
    """

    if type(raw_payload) is not bytes:
        raise TypeError("raw_payload must be exact bytes.")
    if type(limits) is not RubricProviderIngressLimits:
        raise TypeError("limits must be an exact RubricProviderIngressLimits.")
    if type(provenance) is not RubricProviderProvenance:
        raise TypeError("provenance must be an exact RubricProviderProvenance.")

    if len(raw_payload) > limits.max_raw_bytes:
        raise RubricProviderResourceError("Provider response exceeds max_raw_bytes.")
    if (
        len(provenance.provider_id) > limits.max_provenance_text_characters
        or len(provenance.model_id) > limits.max_provenance_text_characters
    ):
        raise RubricProviderResourceError(
            "Provider provenance exceeds max_provenance_text_characters."
        )

    try:
        text = raw_payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RubricProviderMalformedResponseError(
            "Provider response is not valid UTF-8."
        ) from exc

    scanner = _JsonResourceScanner(
        text,
        max_depth=limits.max_json_depth,
        max_nodes=limits.max_json_nodes,
    )
    try:
        scanner.scan()
    except _PreflightResource as exc:
        raise RubricProviderResourceError(str(exc)) from exc
    except _PreflightMalformed as exc:
        raise RubricProviderMalformedResponseError(str(exc)) from exc

    document = _decode_json(text)
    admitted_document = _validate_document(document, limits.compilation_limits)
    proposal = _build_proposal(admitted_document)

    admitted = object.__new__(AdmittedRubricProviderProposal)
    object.__setattr__(admitted, "proposal", proposal)
    object.__setattr__(admitted, "provenance", provenance)
    object.__setattr__(
        admitted,
        "raw_payload_sha256",
        hashlib.sha256(raw_payload).hexdigest(),
    )
    object.__setattr__(admitted, "schema_version", _SCHEMA_VERSION)
    object.__setattr__(admitted, "ingress_profile_version", _INGRESS_PROFILE_VERSION)
    admitted.__post_init__()
    return admitted
