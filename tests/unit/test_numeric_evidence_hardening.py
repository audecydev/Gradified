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
from grading.numeric_evidence import NumericEvidenceBindingError, admit_numeric_scalar


def _fixture() -> AnswerEvidenceBundle:
    block = EvidenceBlock(
        block_id="Q1-B1",
        type=EvidenceBlockType.TEXT,
        content="5.00",
        language=None,
        confidence=1.0,
        confidence_status=EvidenceConfidenceStatus.PRESENT,
        state=EvidenceBlockState.ACTIVE,
        page=1,
        location=EvidenceLocation(
            status=EvidenceLocationStatus.PRESENT,
            bbox=(0.0, 0.0, 1.0, 1.0),
        ),
        reading_order=1,
        asset_ref=None,
    )
    question = QuestionEvidence(
        question_id="Q1",
        answer_scope_ref="scope-Q1",
        blocks=(block,),
        warnings=(),
    )
    return AnswerEvidenceBundle(
        schema_version="1",
        submission_ref="submission-1",
        ocr_provenance="ocr-run-1",
        questions=(question,),
    )


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("bundle", "submission_ref", " forged"),
        ("bundle", "questions", []),
        ("question", "question_id", " Q1"),
        ("question", "blocks", []),
        ("block", "block_id", ""),
        ("block", "content", 5),
        ("block", "type", "TEXT"),
        ("block", "state", "ACTIVE"),
        ("location", "bbox", (float("nan"),)),
    ],
)
def test_post_construction_forgery_is_revalidated_before_admission(
    target: str,
    field: str,
    value: object,
) -> None:
    evidence = _fixture()
    question = evidence.questions[0]
    block = question.blocks[0]
    location = block.location
    targets = {
        "bundle": evidence,
        "question": question,
        "block": block,
        "location": location,
    }
    object.__setattr__(targets[target], field, value)
    with pytest.raises(NumericEvidenceBindingError):
        admit_numeric_scalar(evidence=evidence, question_id="Q1")


def test_post_construction_duplicate_block_id_forgery_is_rejected() -> None:
    evidence = _fixture()
    original = evidence.questions[0].blocks[0]
    other = EvidenceBlock(
        block_id=original.block_id,
        type=EvidenceBlockType.TEXT,
        content="6",
        language=None,
        confidence=1.0,
        confidence_status=EvidenceConfidenceStatus.PRESENT,
        state=EvidenceBlockState.ACTIVE,
        page=2,
        location=EvidenceLocation(status=EvidenceLocationStatus.PRESENT, bbox=(0.0, 0.0, 1.0, 1.0)),
        reading_order=1,
        asset_ref=None,
    )
    other_question = QuestionEvidence(
        question_id="Q2",
        answer_scope_ref="scope-Q2",
        blocks=(other,),
        warnings=(),
    )
    object.__setattr__(evidence, "questions", (evidence.questions[0], other_question))
    with pytest.raises(NumericEvidenceBindingError):
        admit_numeric_scalar(evidence=evidence, question_id="Q1")


def test_foreign_bundle_type_is_rejected_without_attribute_leakage() -> None:
    with pytest.raises(NumericEvidenceBindingError):
        admit_numeric_scalar(evidence=object(), question_id="Q1")  # type: ignore[arg-type]


class _ExplodingForeignLocation:
    def __post_init__(self) -> None:
        raise AssertionError("foreign nested validator must never execute")


def test_foreign_nested_location_is_type_rejected_before_method_dispatch() -> None:
    evidence = _fixture()
    block = evidence.questions[0].blocks[0]
    object.__setattr__(block, "location", _ExplodingForeignLocation())
    with pytest.raises(NumericEvidenceBindingError) as exc_info:
        admit_numeric_scalar(evidence=evidence, question_id="Q1")
    assert not isinstance(exc_info.value.__cause__, AssertionError)


class _ExplodingForeignBlocksContainer:
    iterated = False

    def __iter__(self):
        type(self).iterated = True
        raise AssertionError("foreign blocks container must never be iterated")


def test_foreign_question_blocks_container_is_type_rejected_before_iteration() -> None:
    evidence = _fixture()
    question = evidence.questions[0]
    foreign = _ExplodingForeignBlocksContainer()
    _ExplodingForeignBlocksContainer.iterated = False
    object.__setattr__(question, "blocks", foreign)

    with pytest.raises(NumericEvidenceBindingError) as exc_info:
        admit_numeric_scalar(evidence=evidence, question_id="Q1")

    assert _ExplodingForeignBlocksContainer.iterated is False
    assert not isinstance(exc_info.value.__cause__, AssertionError)


class _ExplodingForeignBlock:
    accessed = False

    @property
    def block_id(self) -> str:
        type(self).accessed = True
        raise AssertionError("foreign block attributes must never be read")


def test_foreign_block_is_type_rejected_before_attribute_dispatch() -> None:
    evidence = _fixture()
    question = evidence.questions[0]
    _ExplodingForeignBlock.accessed = False
    object.__setattr__(question, "blocks", (_ExplodingForeignBlock(),))

    with pytest.raises(NumericEvidenceBindingError) as exc_info:
        admit_numeric_scalar(evidence=evidence, question_id="Q1")

    assert _ExplodingForeignBlock.accessed is False
    assert not isinstance(exc_info.value.__cause__, AssertionError)
