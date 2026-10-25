"""Verify shared numeric-source subgraphs cannot bypass maximum admission depth."""
import pytest

from grading.integration.result_constituents import (
    CandidateConstituentsDenied,
    _preflight_owned_graph,
)


def _wrap(value, count):
    for _ in range(count):
        value = (value,)
    return value


def test_shared_subgraph_revisited_when_reached_by_deeper_path():
    # A 10-edge shared branch is admitted when shallow. The same object is
    # also reachable through a 60-edge branch. With the root edge, the latter
    # path exceeds the configured depth of 64. Arrange tuple order so LIFO
    # traversal processes the shallow branch first, reproducing the bypass.
    shared = _wrap(('leaf',), 10)
    deep = _wrap(shared, 60)
    graph = (deep, shared)

    with pytest.raises(CandidateConstituentsDenied, match='structural admission budget'):
        _preflight_owned_graph(graph)


def test_shared_subgraph_within_depth_budget_remains_admissible():
    shared = _wrap(('leaf',), 10)
    deep = _wrap(shared, 20)
    _preflight_owned_graph((deep, shared))
