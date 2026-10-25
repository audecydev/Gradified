"""Verify predecessor admission occurs before effectful backend reads in regrade lifecycles."""
from dataclasses import replace
import pytest
from grading.contracts.job_state import GradingJobState
from grading.integration.paper_lifecycle import PaperLifecycleState
from tests.integration.test_paper_lifecycle_regrade import setup_regrade

MUTATIONS = [
    {'f57_policy_id': 'FOREIGN-F57-POLICY'},
    {'f57_policy_version': 999},
    {'source_state': GradingJobState.COMPLETED},
    {'target_state': GradingJobState.COMPLETED},
]

@pytest.mark.parametrize('method', ('admit_regrade', 'execute_regrade'))
@pytest.mark.parametrize('change', MUTATIONS)
def test_unqualified_predecessor_never_becomes_backend_read_target(monkeypatch, method, change):
    service, plan, physical, store, issuer, academic, original = setup_regrade(monkeypatch)
    # The qualified permission port returns an ordinary *data* value with a
    # substituted predecessor field. No Python state introspection is used.
    service._authorize.__self__.prior = replace(original.transaction, **change)
    reads_before, claims_before, commits_before = store.reads, physical.claims, store.commits
    actual = getattr(service, method)(plan=plan)
    assert store.reads == reads_before, (
        'backend read occurred before predecessor structural admission',
        method, change, store.reads - reads_before, actual.state)
    assert physical.claims == claims_before
    assert store.commits == commits_before
    assert actual.state is PaperLifecycleState.PRE_EFFECT_BLOCKED

@pytest.mark.parametrize('method', ('admit_regrade', 'execute_regrade'))
def test_genuine_predecessor_remains_readable(monkeypatch, method):
    service, plan, physical, store, issuer, academic, original = setup_regrade(monkeypatch)
    reads_before = store.reads
    actual = getattr(service, method)(plan=plan)
    assert store.reads == reads_before + 1
    if method == 'admit_regrade':
        assert actual.state is PaperLifecycleState.REGRADE_LINEAGE_VERIFIED
        assert physical.claims == 0
    else:
        assert actual.state is PaperLifecycleState.CAS_ACKNOWLEDGED
        assert physical.claims == 2
