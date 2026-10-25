"""Connected Release-1 acceptance of actual original operations and nonpublishing governance.

The source ports below are synthetic qualified *contract* fixtures. These tests
never claim authenticated school issuers, physical provider billing, durable CAS
atomicity, an approved publication policy, or an official student grade.
"""
from dataclasses import replace

import pytest

from grading.integration.governed_operation_consumer import (
    GovernedOperationState, ProductionGovernedOperationConsumer,
)
from grading.integration.paper_lifecycle import PaperLifecycleState
from grading.integration.paper_readiness_admission import (
    PaperAnswerNotReady, PaperAdmissionDenied,
)
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_family_first_scored_cas import connected_regrade
from tests.integration.test_family_retry_accounting import connected_family_retry
from tests.integration.test_governed_operation_consumer import rig
from tests.integration.test_production_paper_operations import _root


@pytest.mark.parametrize('family,physical_count', (
    ('CHOICE', 2), ('DIRECT', 1), ('NUMERIC', 1), ('MIXED', 2),
))
def test_first_original_paper_to_scored_cas_to_governed_readers(family, physical_count):
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig(family=family)
    outcome = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert outcome.operation.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert outcome.operation.execution.cas.state is PaperCASState.COMMITTED
    tx = outcome.operation.execution.cas.transaction
    assert source.keys[0].original_scored_result_ref == tx.result_ref
    assert source.keys[0].source_revision == tx.intent.plan.source_revision
    assert source.keys[0].transaction_ref == tx.request_ref
    assert source.keys[0].transaction_event_ref == tx.event_ref
    assert (physical.claims, store.commits, conditional.contacts) == (physical_count, 1, 1)
    assert all(port.calls == 1 for port in originals + views)
    assert not outcome.authorizes_publication and not outcome.authorizes_retry


@pytest.mark.parametrize('kind', (PaperOperationKind.REGRADE, PaperOperationKind.RETRY))
def test_original_new_run_not_replayed_for_regrade_or_retry(kind):
    if kind is PaperOperationKind.REGRADE:
        lifecycle, plan, physical, _, _, _, store, conditional, predecessor, _ = connected_regrade()
        root, _ = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
        old_ref = predecessor.transaction.result_ref
        original_commits = store.commits
    else:
        retry, plan, physical, _, store, _, _ = connected_family_retry()
        root, _ = _root(retry=retry, plan=plan, kinds=(kind,), qualified=True)
        old_ref = None
        original_commits = store.commits
    template, source, _, _, _, _, _, _, _, _ = rig()
    owner = ProductionGovernedOperationConsumer(operations=root,
        original_source=source, handoff=template._handoff,
        max_identifier_characters=128)
    result = owner.execute_and_assess(request=plan.request, kind=kind)
    assert result.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert result.operation.kind is kind
    assert source.keys[0].kind is kind
    assert source.keys[0].original_scored_result_ref == result.operation.execution.cas.transaction.result_ref
    if old_ref is not None:
        assert source.keys[0].original_scored_result_ref != old_ref
    assert (physical.claims, store.commits) == (1, original_commits + 1)
    assert not result.authorizes_publication and not result.authorizes_retry


@pytest.mark.parametrize('family', ('CHOICE', 'DIRECT', 'NUMERIC', 'MIXED'))
def test_pre_effect_source_not_ready_fails_before_f25_provider_and_cas(family):
    owner, source, _, _, plan, school, physical, provider, store, conditional = rig(family=family)
    first = school.readiness.answers[0]
    school.readiness = replace(school.readiness, answers=(
        replace(first, status='UNKNOWN'), *school.readiness.answers[1:]))
    with pytest.raises(PaperAnswerNotReady):
        owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert (physical.claims, store.commits, conditional.contacts, source.calls) == (0, 0, 0, 0)
    assert provider is None or not provider.requests


def test_original_paper_revoked_before_first_operation_never_grades():
    owner, source, _, _, plan, school, physical, provider, store, conditional = rig()
    school.confirmation = replace(school.confirmation, state='REVOKED')
    with pytest.raises(PaperAdmissionDenied):
        owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert (physical.claims, store.commits, conditional.contacts, source.calls) == (0, 0, 0, 0)
    assert provider is None or not provider.requests


def test_scored_cas_denied_does_not_read_governance_or_issue_success():
    owner, source, originals, views, plan, _, physical, _, store, conditional = rig()
    conditional.revoke_at_commit = True
    outcome = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.state is GovernedOperationState.BLOCKED
    assert (physical.claims, store.commits, conditional.contacts) == (1, 0, 1)
    assert source.calls == 0
    assert all(port.calls == 0 for port in originals + views)


def test_scored_cas_lost_ack_does_not_duplicate_effect_or_claim_governance():
    owner, source, originals, views, plan, _, physical, _, store, conditional = rig()
    conditional.lost_ack = True
    result = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert result.state is GovernedOperationState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == (1, 1, 1)
    assert source.calls == 0
    assert all(port.calls == 0 for port in originals + views)


def test_post_commit_original_read_disappears_without_second_physical_effect():
    owner, source, originals, views, plan, _, physical, _, store, conditional = rig()
    source.explode = True
    result = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert result.state is GovernedOperationState.UNKNOWN
    assert result.operation.execution.cas.state is PaperCASState.COMMITTED
    assert (physical.claims, store.commits, conditional.contacts, source.calls) == (1, 1, 1, 1)
    assert all(port.calls == 0 for port in originals + views)


def test_original_academic_policy_readiness_requires_all_distinct_sources():
    owner, source, original, views, plan, _, physical, _, store, _ = rig()
    original[1].value = None
    outcome = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.handoff is not None
    assert source.calls == 1
    assert all(p.calls == 1 for p in original + views)
    assert (physical.claims, store.commits) == (1, 1)


def test_governed_key_wrong_revision_cannot_reach_original_readers():
    owner, source, originals, views, plan, _, physical, _, store, conditional = rig()
    source.foreign = {'source_revision': 'FORGED-REVISION'}
    outcome = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts, source.calls) == (1, 1, 1, 1)
    assert all(port.calls == 0 for port in originals + views)

@pytest.mark.parametrize('kind', (PaperOperationKind.REGRADE, PaperOperationKind.RETRY))
def test_revoked_school_paper_blocks_new_operation_before_new_claim(kind):
    if kind is PaperOperationKind.REGRADE:
        lifecycle, plan, physical, _, _, _, store, conditional, _, _ = connected_regrade()
        root, school = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
        before = store.commits
        contacted = conditional.contacts
    else:
        retry, plan, physical, _, store, _, _ = connected_family_retry()
        root, school = _root(retry=retry, plan=plan, kinds=(kind,), qualified=True)
        before = store.commits
        contacted = None
    school.confirmation = replace(school.confirmation, state='REVOKED')
    with pytest.raises(PaperAdmissionDenied):
        root.execute(request=plan.request, kind=kind)
    assert physical.claims == 0 and store.commits == before
    if contacted is not None:
        assert conditional.contacts == contacted


@pytest.mark.parametrize('kind', (PaperOperationKind.REGRADE, PaperOperationKind.RETRY))
def test_unready_school_paper_blocks_new_operation_before_new_claim(kind):
    if kind is PaperOperationKind.REGRADE:
        lifecycle, plan, physical, _, _, _, store, _, _, _ = connected_regrade()
        root, school = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
    else:
        retry, plan, physical, _, store, _, _ = connected_family_retry()
        root, school = _root(retry=retry, plan=plan, kinds=(kind,), qualified=True)
    before = store.commits
    school.readiness = replace(school.readiness, answers=(
        replace(school.readiness.answers[0], status='UNMAPPED'),
        *school.readiness.answers[1:]))
    with pytest.raises(PaperAnswerNotReady):
        root.execute(request=plan.request, kind=kind)
    assert physical.claims == 0 and store.commits == before
