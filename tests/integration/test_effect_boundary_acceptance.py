"""Cross-purpose installed-root authority/effect test, not backend certification.

This campaign exercises installed original FIRST/REGRADE/RETRY owners with
synthetic source/effect adapters; counters concern actual invoked test ports.
The real adapter must still authenticate the source and enforce atomic
currentness/physical idempotency. No policy facts are manufactured here.
"""
from dataclasses import replace

import pytest

from grading.integration.paper_lifecycle import PaperLifecycleState, ProductionPaperLifecycle
from grading.integration.paper_readiness_admission import PaperAdmissionDenied, PaperAnswerNotReady
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_family_first_scored_cas import connected, connected_regrade, POLICY
from tests.integration.test_family_retry_accounting import connected_family_retry
from tests.integration.test_production_paper_operations import _root


def installed(kind, family='DIRECT'):
    """Actual strict production root and actual original-effect owners."""
    if kind is PaperOperationKind.FIRST:
        cas, plan, _, physical, _, f25, provider, store, conditional = connected(family)
        lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
            legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
        root, school = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
        return root, school, plan, physical, store, conditional, 0, provider
    if kind is PaperOperationKind.REGRADE:
        lifecycle, plan, physical, _, _, provider, store, conditional, old, _ = connected_regrade(family)
        root, school = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
        assert store.commits == 1 and old.transaction.result_ref != ''
        return root, school, plan, physical, store, conditional, 1, provider
    retry, plan, physical, _, store, _, provider = connected_family_retry(family)
    root, school = _root(retry=retry, plan=plan, kinds=(kind,), qualified=True)
    return root, school, plan, physical, store, retry._cas._purpose_commit.__self__, 0, provider


PURPOSES = (PaperOperationKind.FIRST, PaperOperationKind.REGRADE, PaperOperationKind.RETRY)


@pytest.mark.parametrize('kind', PURPOSES)
@pytest.mark.parametrize('invalid', ('REVOKED', 'SOURCE-DRIFT', 'EVIDENCE-SCOPE-DRIFT', 'UNREADY'))
def test_changed_official_source_blocks_new_effect_before_f25(kind, invalid):
    root, school, plan, physical, store, conditional, before, provider = installed(kind)
    if invalid == 'REVOKED':
        school.confirmation = replace(school.confirmation, state='REVOKED')
    elif invalid == 'SOURCE-DRIFT':
        school.confirmation = replace(school.confirmation, source_revision='SUPERSEDED')
    elif invalid == 'EVIDENCE-SCOPE-DRIFT':
        answers = school.readiness.answers
        school.readiness = replace(school.readiness, answers=(
            replace(answers[0], evidence_scope_ref='FOREIGN-SCOPE'), *answers[1:]))
        # The school selection pins this scope independently of readiness.
    else:
        answers = school.readiness.answers
        school.readiness = replace(school.readiness, answers=(
            replace(answers[0], status='UNKNOWN'), *answers[1:]))
    with pytest.raises((PaperAdmissionDenied, PaperAnswerNotReady)):
        root.execute(request=plan.request, kind=kind)
    assert physical.claims == 0
    assert store.commits == before
    expected = ['identity', 'selection', 'readiness', 'revision']
    if invalid in ('UNREADY', 'EVIDENCE-SCOPE-DRIFT'):
        expected = expected[:-1]
    assert school.events == expected


@pytest.mark.parametrize('kind', PURPOSES)
@pytest.mark.parametrize('family', ('DIRECT', 'NUMERIC', 'MIXED'))
def test_real_installed_purposes_preserve_successful_original_identity(kind, family):
    root, school, plan, physical, store, conditional, before, provider = installed(kind, family)
    result = root.execute(request=plan.request, kind=kind)
    assert result.kind is kind
    assert result.execution.cas.state is PaperCASState.COMMITTED
    tx = result.execution.cas.transaction
    assert tx.intent.plan.request == plan.request
    assert tx.intent.plan.source_revision == plan.source_revision
    assert tx.result_ref and tx.request_ref and tx.event_ref
    assert physical.claims == len(plan.questions)
    assert store.commits == before + 1
    assert not result.authorizes_publication and not result.authorizes_retry
    assert school.events == ['identity', 'selection', 'readiness', 'revision']


@pytest.mark.parametrize('kind', PURPOSES)
def test_conditional_scored_cas_revocation_after_f25_never_commits(kind):
    root, school, plan, physical, store, conditional, before, provider = installed(kind)
    if kind is PaperOperationKind.RETRY:
        conditional.revoke = True
    else:
        conditional.revoke_at_commit = True
    out = root.execute(request=plan.request, kind=kind)
    assert out.execution.cas.state is not PaperCASState.COMMITTED
    assert physical.claims == 1  # the first effect may already have happened
    assert store.commits == before
    assert not out.authorizes_publication and not out.authorizes_retry


@pytest.mark.parametrize('kind', PURPOSES)
def test_lost_scored_cas_ack_keeps_original_unknown_not_success(kind):
    root, school, plan, physical, store, conditional, before, provider = installed(kind)
    conditional.lost_ack = True
    out = root.execute(request=plan.request, kind=kind)
    assert out.execution.cas.state is PaperCASState.UNKNOWN
    assert physical.claims == 1 and store.commits == before + 1
    assert not out.authorizes_publication and not out.authorizes_retry

@pytest.mark.parametrize('kind', PURPOSES)
def test_mixed_paper_revocation_after_first_claim_never_commits_second_claim(kind):
    root, school, plan, physical, store, conditional, before, provider = installed(kind, 'MIXED')
    if kind is PaperOperationKind.RETRY:
        root._retry._claims._joint_effect._claim.__self__.revoke_after_first = True
    else:
        root._cas._custody._executor._attempts._joint_effect._claim.__self__.revoke_after_first = True
    result = root.execute(request=plan.request, kind=kind)
    assert result.execution.state.name != 'CAS_ACKNOWLEDGED'
    assert physical.claims == 1  # one irreversible original, not rolled back
    assert store.commits == before
    assert not result.authorizes_publication and not result.authorizes_retry


@pytest.mark.parametrize('kind', PURPOSES)
def test_pre_f25_revoked_direct_route_prevents_physical_and_vendor(kind):
    root, school, plan, physical, store, conditional, before, provider = installed(kind, 'DIRECT')
    route = root._cas._custody._executor._direct_route
    route._read.__self__.revoked = True
    result = root.execute(request=plan.request, kind=kind)
    assert result.execution.state.name != 'CAS_ACKNOWLEDGED'
    assert physical.claims == 0
    assert store.commits == before
    assert not result.authorizes_publication and not result.authorizes_retry


@pytest.mark.parametrize('kind', PURPOSES)
def test_valid_direct_route_records_one_vendor_dispatch_with_attempt_custody(kind):
    root, school, plan, physical, store, conditional, before, provider = installed(kind)
    route = root._cas._custody._executor._direct_route
    sender = route._deliver.__self__
    accounting = route._write.__self__
    result = root.execute(request=plan.request, kind=kind)
    assert result.execution.cas.state is PaperCASState.COMMITTED
    assert physical.claims == 1 and store.commits == before + 1
    assert len(sender.dispatched) == len(accounting.events) == 1
    dispatch = sender.dispatched[0]
    assert dispatch.identity.request_ref
    assert dispatch.identity.attempt_id
    assert accounting.events[0].identity == dispatch.identity
    assert not result.authorizes_publication
