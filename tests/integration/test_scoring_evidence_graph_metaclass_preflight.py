"""Foreign metaclass attribute hooks must not run during second-pass evidence admission preflight."""
from dataclasses import replace
import pytest
from grading.integration.result_constituents import CandidateConstituentsDenied
from test_scoring_evidence_graph_detached_custody import candidate


def test_foreign_metaclass_metadata_hook_not_executed_before_denial():
    original, _, _ = candidate()
    callbacks = []
    class ForeignMeta(type):
        def __getattribute__(cls, name):
            if name in ('__module__', '__name__'):
                callbacks.append('metadata-executed')
            return type.__getattribute__(cls, name)
    class Foreign(metaclass=ForeignMeta):
        def __deepcopy__(self, memo):
            callbacks.append('copy-executed')
            raise RuntimeError('PRIVATE_EXTERNAL_CONTENT')
    with pytest.raises(CandidateConstituentsDenied) as denial:
        replace(original, paper_score=Foreign())
    assert callbacks == []
    assert denial.value.__context__ is None and denial.value.__cause__ is None
