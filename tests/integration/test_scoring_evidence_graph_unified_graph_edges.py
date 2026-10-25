"""R9 cross-variant shared-graph admission: boundary and cycle controls."""
import pytest
from grading.integration.result_constituents import (
    CandidateConstituentsDenied,
    _preflight_owned_graph,
    _MAX_CONSTITUENT_DEPTH,
)
from grading.risk import RiskObservationSet


def _nested(depth):
    value = 'leaf'
    for _ in range(depth):
        value = (value,)
    return value


def test_exact_admission_depth_limit_is_accepted():
    _preflight_owned_graph(_nested(_MAX_CONSTITUENT_DEPTH))


def test_one_edge_beyond_depth_limit_is_denied():
    with pytest.raises(CandidateConstituentsDenied, match='structural admission budget'):
        _preflight_owned_graph(_nested(_MAX_CONSTITUENT_DEPTH + 1))


def test_cyclic_allowed_dataclass_graph_rejected_without_copy():
    graph = RiskObservationSet('1', 'run', 'submission', ())
    object.__setattr__(graph, 'observations', (graph,))
    with pytest.raises(CandidateConstituentsDenied, match='Cyclic'):
        _preflight_owned_graph(graph)
