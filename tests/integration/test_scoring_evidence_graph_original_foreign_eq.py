import pytest
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents
from test_result_constituents_provenance import example

@pytest.mark.parametrize('target', ['bbox','confidence'])
def test_foreign_type_eq_callback_during_original_F53_ingress(target):
    execution,evidence,query,recommender,reader = example(unknown_ocr=True)
    calls=[]
    class HostileMeta(type):
        def __eq__(cls, other):
            calls.append(('class-eq', getattr(other, '__name__', 'other')))
            return False
    class Foreign(metaclass=HostileMeta):
        def __float__(self):
            calls.append(('float', 'ran'))
            return 0.6
    block=evidence.questions[0].blocks[0]
    if target == 'bbox':
        object.__setattr__(block.location, 'bbox', (Foreign(),))
    else:
        object.__setattr__(block, 'confidence', Foreign())
        # confidence-status PRESENT so validator inspects numeric type
        from grading.contracts.evidence import EvidenceConfidenceStatus
        object.__setattr__(block,'confidence_status',EvidenceConfidenceStatus.PRESENT)
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=execution,evidence=evidence,policy_query=query,recommender=recommender)
    assert reader.calls == 0
    assert calls == [], 'foreign class equality ran before candidate-constituent denial: '+repr(calls)

def test_valid_original_control():
    execution,evidence,query,recommender,reader=example(unknown_ocr=True)
    c=compose_nonpublishing_constituents(execution=execution,evidence=evidence,policy_query=query,recommender=recommender)
    assert c.official_result is False and reader.calls == 1
