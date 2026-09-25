from __future__ import annotations

import re

from grading.contracts.evidence import (
    AnswerEvidenceBundle,
    EvidenceBlockState,
    EvidenceBlockType,
    QuestionEvidence,
)
from grading.contracts.numeric_evidence import (
    MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS,
    NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
    AdmittedNumericScalar,
)


_ASCII_DECIMAL_INPUT_RE = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$"
)


class NumericEvidenceAdmissionError(ValueError):
    """Base class for expected NUMERIC evidence-admission failures."""


class NumericEvidenceBindingError(NumericEvidenceAdmissionError):
    """Normalized evidence is malformed or ambiguously bound to the question."""


class UnsupportedNumericEvidenceError(NumericEvidenceAdmissionError):
    """Evidence is well-formed but outside NUMERIC evidence profile v1."""


class UnassessableNumericEvidenceError(NumericEvidenceAdmissionError):
    """No active, assessable scalar evidence is available under profile v1."""


def _require_question_id(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise NumericEvidenceBindingError(
            "question_id must be a non-empty exact string without surrounding whitespace."
        )
    return value


def _revalidate_evidence_graph(value: object) -> AnswerEvidenceBundle:
    if type(value) is not AnswerEvidenceBundle:
        raise NumericEvidenceBindingError(
            "evidence must be an exact AnswerEvidenceBundle."
        )
    try:
        # Revalidate from the inside out. Existing construction-time validators
        # assume their nested dataclasses were already valid when constructed;
        # after hostile post-construction mutation that assumption no longer holds.
        # Prove each container/item type before iterating it or invoking a nested
        # validator so forged foreign objects never receive method/attribute dispatch.
        questions = object.__getattribute__(value, "questions")
        if type(questions) is not tuple or any(
            type(question) is not QuestionEvidence for question in questions
        ):
            raise TypeError(
                "AnswerEvidenceBundle.questions must be a tuple of exact QuestionEvidence values."
            )

        for question in questions:
            question.__post_init__()
            for block in question.blocks:
                block.__post_init__()
                block.location.__post_init__()

        # Run the bundle validator only after nested state is known safe to traverse;
        # it additionally enforces top-level identifiers and global block-id uniqueness.
        value.__post_init__()
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise NumericEvidenceBindingError(
            "normalized evidence contains malformed current state."
        ) from exc
    return value


def _canonicalize_ascii_decimal(source: str) -> str:
    if len(source) > MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS:
        raise UnsupportedNumericEvidenceError(
            "numeric evidence exceeds the profile-v1 text limit."
        )
    if _ASCII_DECIMAL_INPUT_RE.fullmatch(source) is None:
        raise UnsupportedNumericEvidenceError(
            "numeric evidence is outside the supported unitless ASCII-decimal syntax."
        )

    negative = source.startswith("-")
    if source[:1] in ("+", "-"):
        body = source[1:]
    else:
        body = source

    if body.startswith("."):
        integer_text = "0"
        fraction_text = body[1:]
    elif "." in body:
        integer_text, fraction_text = body.split(".", 1)
    else:
        integer_text = body
        fraction_text = ""

    canonical_integer = integer_text.lstrip("0") or "0"
    canonical_fraction = fraction_text.rstrip("0")
    is_zero = canonical_integer == "0" and not canonical_fraction

    canonical = canonical_integer
    if canonical_fraction:
        canonical += "." + canonical_fraction
    if negative and not is_zero:
        canonical = "-" + canonical

    if len(canonical) > MAX_NUMERIC_EVIDENCE_TEXT_CHARACTERS:
        raise UnsupportedNumericEvidenceError(
            "canonical numeric evidence exceeds the profile-v1 text limit."
        )
    return canonical


def admit_numeric_scalar(
    *,
    evidence: AnswerEvidenceBundle,
    question_id: str,
) -> AdmittedNumericScalar:
    """Admit one unambiguous unitless scalar from normalized question evidence.

    Profile v1 deliberately requires exactly one evidence block for the target
    question and never chooses a first/latest/best block. Parsing establishes a
    scalar observation only; it does not compare against academic authority,
    choose rubric levels, or calculate marks.
    """

    canonical_question_id = _require_question_id(question_id)
    bundle = _revalidate_evidence_graph(evidence)

    matching_questions = tuple(
        question
        for question in bundle.questions
        if question.question_id == canonical_question_id
    )
    if len(matching_questions) != 1:
        raise NumericEvidenceBindingError(
            "evidence must contain exactly one matching question for NUMERIC admission."
        )

    question = matching_questions[0]
    if not question.blocks:
        raise UnassessableNumericEvidenceError(
            "NUMERIC profile v1 requires one assessable evidence block."
        )
    if len(question.blocks) != 1:
        raise UnsupportedNumericEvidenceError(
            "NUMERIC profile v1 does not select among multiple evidence blocks."
        )

    block = question.blocks[0]
    if block.state is not EvidenceBlockState.ACTIVE:
        raise UnassessableNumericEvidenceError(
            "NUMERIC profile v1 requires an ACTIVE evidence block."
        )
    if block.type not in (EvidenceBlockType.TEXT, EvidenceBlockType.MATH):
        raise UnsupportedNumericEvidenceError(
            "NUMERIC profile v1 supports only TEXT or MATH scalar evidence blocks."
        )

    canonical_value = _canonicalize_ascii_decimal(block.content)
    return AdmittedNumericScalar(
        admission_profile_version=NUMERIC_EVIDENCE_ADMISSION_PROFILE_VERSION,
        submission_ref=bundle.submission_ref,
        ocr_provenance=bundle.ocr_provenance,
        question_id=question.question_id,
        answer_scope_ref=question.answer_scope_ref,
        evidence_ref=block.block_id,
        canonical_value=canonical_value,
    )
