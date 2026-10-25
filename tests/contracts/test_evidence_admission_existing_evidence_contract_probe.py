from __future__ import annotations

import pytest

from grading.contracts.evidence import (
    EvidenceBlock,
    EvidenceBlockState,
    EvidenceBlockType,
    EvidenceConfidenceStatus,
    EvidenceLocation,
    EvidenceLocationStatus,
)


def test_probe_frozen_evidence_contract_cannot_represent_missing_page() -> None:
    """Diagnostic probe: page=None cannot project into frozen EvidenceBlock.

    This intentionally records a current integration-contract tension. It is not a
    request to modify the frozen evidence contract in normalized OCR evidence admission.
    """
    with pytest.raises(TypeError, match="EvidenceBlock.page must be a int"):
        EvidenceBlock(
            block_id="Q1-B1",
            type=EvidenceBlockType.TEXT,
            content="answer",
            language=None,
            confidence=None,
            confidence_status=EvidenceConfidenceStatus.UNAVAILABLE,
            state=EvidenceBlockState.ACTIVE,
            page=None,  # type: ignore[arg-type]
            location=EvidenceLocation(
                status=EvidenceLocationStatus.UNAVAILABLE,
                bbox=None,
            ),
            reading_order=1,
            asset_ref=None,
        )
