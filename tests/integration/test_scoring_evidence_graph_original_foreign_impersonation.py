import pytest
from grading.integration.result_constituents import CandidateConstituentsDenied, compose_nonpublishing_constituents
from test_result_constituents_provenance import example

@pytest.mark.parametrize('target', ['bbox','confidence'])
def test_foreign_class_eq_impersonates_builtin_and_reaches_reader(target):
    execution,evidence,query,recommender,reader = example(unknown_ocr=True)
    calls=[]
    class HostileMeta(type):
        def __eq__(cls, other):
            calls.append('metaclass-equality')
            return True
    class Foreign(metaclass=HostileMeta):
        def __float__(self):
            calls.append('foreign-float-coercion')
            return 0.6
    block=evidence.questions[0].blocks[0]
    if target == 'bbox':
        object.__setattr__(block.location, 'bbox', (Foreign(),))
    else:
        from grading.contracts.evidence import EvidenceConfidenceStatus
        object.__setattr__(block, 'confidence', Foreign())
        object.__setattr__(block, 'confidence_status', EvidenceConfidenceStatus.PRESENT)
    with pytest.raises(CandidateConstituentsDenied):
        compose_nonpublishing_constituents(execution=execution,evidence=evidence,policy_query=query,recommender=recommender)
    assert reader.calls == 0

def test_valid_control():
    execution,evidence,query,recommender,reader=example(unknown_ocr=True)
    c=compose_nonpublishing_constituents(execution=execution,evidence=evidence,policy_query=query,recommender=recommender)
    assert not c.official_result and reader.calls == 1
