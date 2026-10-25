from __future__ import annotations

import pytest

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
from grading.numeric_evidence import (
    NumericEvidenceBindingError,
    UnassessableNumericEvidenceError,
    UnsupportedNumericEvidenceError,
    admit_numeric_scalar,
)


def _block(
    content: str,
    *,
    block_id: str = "Q1-B1",
    block_type: EvidenceBlockType = EvidenceBlockType.TEXT,
    state: EvidenceBlockState = EvidenceBlockState.ACTIVE,
    confidence: float | None = 0.2,
    confidence_status: EvidenceConfidenceStatus = EvidenceConfidenceStatus.PRESENT,
) -> EvidenceBlock:
    return EvidenceBlock(
        block_id=block_id,
        type=block_type,
        content=content,
        language="en",
        confidence=confidence,
        confidence_status=confidence_status,
        state=state,
        page=1,
        location=EvidenceLocation(
            status=EvidenceLocationStatus.PRESENT,
            bbox=(0.0, 0.0, 10.0, 10.0),
        ),
        reading_order=1,
        asset_ref=None,
    )


def _question(
    *blocks: EvidenceBlock,
    question_id: str = "Q1",
    answer_scope_ref: str = "scope-Q1",
) -> QuestionEvidence:
    return QuestionEvidence(
        question_id=question_id,
        answer_scope_ref=answer_scope_ref,
        blocks=tuple(blocks),
        warnings=(),
    )


def _bundle(*questions: QuestionEvidence) -> AnswerEvidenceBundle:
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref="submission-1",
        ocr_provenance="ocr-run-1",
        questions=tuple(questions),
    )


@pytest.mark.parametrize(
    ("source", "canonical"),
    [
        ("0", "0"),
        ("-0", "0"),
        ("+0", "0"),
        ("000", "0"),
        ("000.000", "0"),
        ("5", "5"),
        ("+5", "5"),
        ("05", "5"),
        ("5.0", "5"),
        ("005.2500", "5.25"),
        ("+000.500", "0.5"),
        (".5", "0.5"),
        ("-.500", "-0.5"),
        ("-0012.3400", "-12.34"),
    ],
)
def test_admit_numeric_scalar_normalizes_supported_ascii_decimal_syntax(
    source: str,
    canonical: str,
) -> None:
    result = admit_numeric_scalar(evidence=_bundle(_question(_block(source))), question_id="Q1")
    assert result.canonical_value == canonical
    assert result.submission_ref == "submission-1"
    assert result.ocr_provenance == "ocr-run-1"
    assert result.question_id == "Q1"
    assert result.answer_scope_ref == "scope-Q1"
    assert result.evidence_ref == "Q1-B1"


def test_math_block_is_supported_for_scalar_text() -> None:
    result = admit_numeric_scalar(
        evidence=_bundle(_question(_block("3.5", block_type=EvidenceBlockType.MATH))),
        question_id="Q1",
    )
    assert result.canonical_value == "3.5"


@pytest.mark.parametrize(
    "source",
    [
        "",
        " 5",
        "5 ",
        "5.",
        "+",
        "-",
        ".",
        "1e3",
        "1E3",
        "1_000",
        "1,000",
        "1/2",
        "5 m",
        "5m",
        "$5$",
        "NaN",
        "Inf",
        "Infinity",
        "١٢",
        "１２",
        "−5",
    ],
)
def test_unsupported_numeric_syntax_never_becomes_an_admitted_scalar(source: str) -> None:
    with pytest.raises(UnsupportedNumericEvidenceError):
        admit_numeric_scalar(evidence=_bundle(_question(_block(source))), question_id="Q1")


@pytest.mark.parametrize(
    "block_type",
    [
        EvidenceBlockType.TABLE,
        EvidenceBlockType.FIGURE,
        EvidenceBlockType.CODE,
        EvidenceBlockType.OTHER,
    ],
)
def test_unsupported_evidence_block_types_fail_closed(block_type: EvidenceBlockType) -> None:
    with pytest.raises(UnsupportedNumericEvidenceError):
        admit_numeric_scalar(
            evidence=_bundle(_question(_block("5", block_type=block_type))),
            question_id="Q1",
        )


@pytest.mark.parametrize(
    "state",
    [EvidenceBlockState.CROSSED_OUT, EvidenceBlockState.UNCERTAIN],
)
def test_non_active_block_never_becomes_numeric_value(state: EvidenceBlockState) -> None:
    with pytest.raises(UnassessableNumericEvidenceError):
        admit_numeric_scalar(
            evidence=_bundle(_question(_block("5", state=state))),
            question_id="Q1",
        )


def test_missing_block_is_unassessable() -> None:
    with pytest.raises(UnassessableNumericEvidenceError):
        admit_numeric_scalar(evidence=_bundle(_question()), question_id="Q1")


def test_multiple_blocks_are_unsupported_in_profile_v1_without_hidden_selection() -> None:
    with pytest.raises(UnsupportedNumericEvidenceError):
        admit_numeric_scalar(
            evidence=_bundle(
                _question(
                    _block("5", block_id="Q1-B1"),
                    _block("6", block_id="Q1-B2"),
                )
            ),
            question_id="Q1",
        )


def test_duplicate_question_identity_is_rejected_as_ambiguous() -> None:
    with pytest.raises(NumericEvidenceBindingError):
        admit_numeric_scalar(
            evidence=_bundle(
                _question(_block("5", block_id="Q1-B1")),
                _question(_block("6", block_id="Q1-B2")),
            ),
            question_id="Q1",
        )


def test_unknown_question_is_rejected() -> None:
    with pytest.raises(NumericEvidenceBindingError):
        admit_numeric_scalar(evidence=_bundle(_question(_block("5"))), question_id="Q9")


def test_low_or_unavailable_ocr_confidence_is_not_reinterpreted_as_numeric_correctness() -> None:
    low = admit_numeric_scalar(
        evidence=_bundle(_question(_block("5", confidence=0.0))),
        question_id="Q1",
    )
    unknown = admit_numeric_scalar(
        evidence=_bundle(
            _question(
                _block(
                    "5",
                    confidence=None,
                    confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
                )
            )
        ),
        question_id="Q1",
    )
    assert low.canonical_value == "5"
    assert unknown.canonical_value == "5"


def test_warnings_are_not_interpreted_as_hidden_parser_or_academic_policy() -> None:
    question = QuestionEvidence(
        question_id="Q1",
        answer_scope_ref="scope-Q1",
        blocks=(_block("5"),),
        warnings=("OCR_LOW_CONFIDENCE", "anything-opaque"),
    )
    assert admit_numeric_scalar(evidence=_bundle(question), question_id="Q1").canonical_value == "5"


def test_profile_text_limit_accepts_128_and_rejects_129() -> None:
    accepted = "9" * 128
    assert (
        admit_numeric_scalar(evidence=_bundle(_question(_block(accepted))), question_id="Q1").canonical_value
        == accepted
    )
    with pytest.raises(UnsupportedNumericEvidenceError):
        admit_numeric_scalar(
            evidence=_bundle(_question(_block("9" * 129))),
            question_id="Q1",
        )
    with pytest.raises(UnsupportedNumericEvidenceError):
        admit_numeric_scalar(
            evidence=_bundle(_question(_block("0" * 129))),
            question_id="Q1",
        )


def test_question_id_requires_exact_identifier() -> None:
    with pytest.raises(NumericEvidenceBindingError):
        admit_numeric_scalar(evidence=_bundle(_question(_block("5"))), question_id=" Q1")
