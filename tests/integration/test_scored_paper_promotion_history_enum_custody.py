"""Independent R3 governed scored-paper handoff falsification: exact enum state vs string impostors."""
from dataclasses import replace
import pytest

from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from grading.integration.paper_lifecycle import PaperLifecycleState
from tests.integration.test_original_recovery_complete_paper_gate import _gate
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle
from tests.integration.test_paper_lifecycle_regrade import setup_regrade


def issued_history(kind, monkeypatch):
    if kind == 'FIRST':
        svc, plan, physical, store, _ = setup_lifecycle()
        prior = None
        observation = svc.execute_first(plan=plan)
    else:
        svc, plan, physical, store, _, _, prior = setup_regrade(monkeypatch)
        observation = svc.execute_regrade(plan=plan)
    assert observation.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    return observation, physical, store, prior


@pytest.mark.parametrize('kind', ['FIRST', 'REGRADE'])
@pytest.mark.parametrize('mutation', ['false_binding_str', 'unknown_label_str'])
def test_malformed_string_lifecycle_must_not_promote_or_read(kind, mutation, monkeypatch):
    original, physical, store, prior = issued_history(kind, monkeypatch)
    if mutation == 'false_binding_str':
        hostile = replace(original, state='CAS_ACKNOWLEDGED',
                          cas=replace(original.cas, academic_binding_verified=False))
    else:
        hostile = replace(original, state='UNKNOWN')
    gate, _, _ = _gate(hostile, store, prior=prior)
    prior_effects = (physical.claims, store.commits, store.reads)
    assessment = gate.assess()
    assert assessment.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, (
        'Malformed nonenum C4 lifecycle observation falsely promoted')
    assert store.reads == prior_effects[2], 'CAS audit was read before rejecting malformed lifecycle state'
    assert (physical.claims, store.commits) == prior_effects[:2]


@pytest.mark.parametrize('kind', ['FIRST', 'REGRADE'])
def test_legitimate_original_enum_still_promotes(kind, monkeypatch):
    original, physical, store, prior = issued_history(kind, monkeypatch)
    gate, _, _ = _gate(original, store, prior=prior)
    assert gate.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF


@pytest.mark.parametrize('kind', ['FIRST', 'REGRADE'])
@pytest.mark.parametrize('mutation', ['false_binding_enum', 'unknown_enum_committed'])
def test_correctly_typed_inconsistent_state_is_rejected(kind, mutation, monkeypatch):
    original, physical, store, prior = issued_history(kind, monkeypatch)
    if mutation == 'false_binding_enum':
        hostile = replace(original, cas=replace(original.cas, academic_binding_verified=False))
    else:
        hostile = replace(original, state=PaperLifecycleState.UNKNOWN)
    gate, _, _ = _gate(hostile, store, prior=prior)
    pre = store.reads
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == pre


@pytest.mark.parametrize('kind', ['FIRST', 'REGRADE'])
@pytest.mark.parametrize('raw_kind', ['FIRST', 'REGRADE'])
def test_string_kind_never_authorizes_handoff_or_backend_read(kind, raw_kind, monkeypatch):
    original, physical, store, prior = issued_history(kind, monkeypatch)
    gate, _, _ = _gate(replace(original, kind=raw_kind), store, prior=prior)
    before = (store.reads, store.commits, physical.claims)
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (store.reads, store.commits, physical.claims) == before


@pytest.mark.parametrize('kind', ['FIRST', 'REGRADE'])
def test_string_permission_kind_cannot_promote(kind, monkeypatch):
    original, physical, store, prior = issued_history(kind, monkeypatch)
    corrupted = replace(original, permission=replace(original.permission, kind=kind))
    gate, _, _ = _gate(corrupted, store, prior=prior)
    before = store.reads
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == before


def test_string_graded_retry_state_cannot_promote_or_read():
    from tests.integration.test_scored_paper_retry_handoff import make
    gate, fixed, history, store, _, _ = make()
    fixed.original = replace(history, state='CAS_ACKNOWLEDGED')
    before = store.reads
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads == before
