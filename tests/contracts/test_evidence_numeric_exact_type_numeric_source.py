"""Numeric admission rejects foreign numeric protocols before executing untrusted conversions."""
from dataclasses import replace
import math
import pytest

from grading.contracts.evidence import (
    EvidenceBlock, EvidenceBlockState, EvidenceBlockType,
    EvidenceConfidenceStatus, EvidenceLocation, EvidenceLocationStatus,
)


def _block(*, confidence=0.6):
    return EvidenceBlock(
        block_id='b1', type=EvidenceBlockType.TEXT, content='text', language='en',
        confidence=confidence, confidence_status=EvidenceConfidenceStatus.PRESENT,
        state=EvidenceBlockState.ACTIVE, page=1,
        location=EvidenceLocation(EvidenceLocationStatus.PRESENT, (1, 0.5)),
        reading_order=0, asset_ref=None,
    )


@pytest.mark.parametrize('field', ['bbox', 'confidence'])
@pytest.mark.parametrize('result', [False, True])
def test_no_foreign_class_equality_or_numeric_coercion(field, result):
    effects = []

    class HostileMeta(type):
        def __eq__(cls, other):
            effects.append('class-equality')
            return result

    class Foreign(metaclass=HostileMeta):
        def __float__(self):
            effects.append('numeric-coercion')
            return 0.5

    with pytest.raises(TypeError):
        if field == 'bbox':
            EvidenceLocation(EvidenceLocationStatus.PRESENT, (Foreign(),))
        else:
            replace(_block(), confidence=Foreign())
    assert effects == []


@pytest.mark.parametrize('field', ['bbox', 'confidence'])
@pytest.mark.parametrize('value', [True, False, 0.4, 1, float('inf'), float('nan')])
def test_native_numeric_profile_preserved(field, value):
    operation = (lambda: EvidenceLocation(EvidenceLocationStatus.PRESENT, (value,))) if field == 'bbox' \
        else (lambda: replace(_block(), confidence=value))
    if type(value) is bool:
        with pytest.raises(TypeError):
            operation()
    elif type(value) is float and not math.isfinite(value):
        with pytest.raises(ValueError):
            operation()
    else:
        assert operation()


@pytest.mark.parametrize('field', ['bbox', 'confidence'])
def test_numeric_subclasses_do_not_gain_admission(field):
    class ForeignFloat(float):
        pass
    with pytest.raises(TypeError):
        if field == 'bbox':
            EvidenceLocation(EvidenceLocationStatus.PRESENT, (ForeignFloat(0.5),))
        else:
            replace(_block(), confidence=ForeignFloat(0.5))
