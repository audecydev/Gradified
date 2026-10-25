"""Actual installed strict application entry, not bare legacy-only paper lifecycle execution.

The governed scored-paper handoff fixture here supplies a contract-valid installed *reader*. Its source is
independent; these tests establish NO positive production governed scored-paper handoff origin proof.
"""
from dataclasses import replace
import pytest

from grading.integration.production_paper_operations import (
    ProductionPaperOperations, PaperOperationKind,
    PRODUCTION_PAPER_OPERATION_SCHEMA_VERSION,
)
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.paper_readiness_admission import PaperAnswerNotReady
from grading.integration.whole_paper_cas import ProductionWholePaperCAS, PaperCASState
from grading.integration.paper_retry_grading import GradedRetryState
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_family_retry_accounting import connected_family_retry
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff
from tests.integration.test_admitted_paper_family_effect_continuity import installation
from tests.integration.test_authorized_retry_graded_retry_real import graded_rig


def _promotion_fixture():
    return recorded_handoff('DIRECT')[0]


def _root(*, lifecycle=None, retry=None, plan, kinds, promotion=None, qualified=False):
    ports, readiness = installation(plan)
    executor=(lifecycle or retry)._cas._custody._executor
    if qualified and any(q.family=='DIRECT' for q in plan.questions):
        from tests.integration.test_direct_provider_route_connected import install
        install(executor, plan, kinds[0].value)
    result = ProductionPaperOperations(
        admission=readiness, promotion=promotion or _promotion_fixture(),
        lifecycle=lifecycle, retry=retry, enabled_kinds=kinds,
        max_identifier_characters=128, max_questions=10)
    return result, ports


@pytest.mark.parametrize('family,physical_count', [
    ('DIRECT', 1), ('NUMERIC', 1), ('MIXED', 2),
])
def test_strict_root_official_ready_original_first_executes_real_f25_and_cas(family, physical_count):
    cas, plan, _, physical, _, f25, provider, store, conditional = connected(family)
    lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    root, ports = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,), qualified=True)
    result = root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert PRODUCTION_PAPER_OPERATION_SCHEMA_VERSION == '1'
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert result.execution.cas.state is PaperCASState.COMMITTED
    assert (physical.claims, conditional.contacts, store.commits) == (physical_count, 1, 1)
    assert ports.events == ['identity', 'selection', 'readiness', 'revision']
    assert result.authorizes_publication is False and result.authorizes_retry is False


def test_strict_root_rechecks_official_answer_readiness_before_f57_f25_or_provider():
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    root, ports = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,))
    ports.readiness = replace(ports.readiness, answers=(
        replace(ports.readiness.answers[0], status='UNMAPPED'),))
    with pytest.raises(PaperAnswerNotReady):
        root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert (physical.claims, conditional.contacts, store.commits) == (0, 0, 0)
    assert not provider.requests


def test_root_refuses_inactive_operation_without_official_or_physical_contact():
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    root, ports = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,))
    with pytest.raises(ValueError):
        root.execute(request=plan.request, kind=PaperOperationKind.RETRY)
    assert not ports.events and not physical.claims and not store.commits


def test_strict_root_family_retry_requires_original_absence_and_real_c4e():
    retry,plan,physical,_,store,_,provider=connected_family_retry('DIRECT')
    root,ports = _root(retry=retry, plan=plan, kinds=(PaperOperationKind.RETRY,), qualified=True)
    result=root.execute(request=plan.request, kind=PaperOperationKind.RETRY)
    assert result.execution.state is GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and store.commits == 1
    assert ports.events == ['identity', 'selection', 'readiness', 'revision']
    assert not result.authorizes_retry and not result.authorizes_publication


def test_legacy_only_choice_c4_positive_cannot_be_installed_as_production():
    legacy,plan,*_=graded_rig()
    assert legacy._cas._purpose_commit is None
    with pytest.raises(ValueError, match='strict|purpose'):
        _root(retry=legacy, plan=plan, kinds=(PaperOperationKind.RETRY,))


def test_root_rejects_mixed_conditional_and_legacy_cas_installations():
    cas,plan,_,physical,_,f25,provider,store,conditional=connected('DIRECT')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    original=cas._purpose_commit
    object.__setattr__(cas, '_purpose_commit', None)
    try:
        with pytest.raises(ValueError,match='strict|purpose'):
            _root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    finally:
        object.__setattr__(cas, '_purpose_commit', original)
    assert not physical.claims and not store.commits


def test_root_blocks_direct_without_measured_provider_source_before_effect():
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root, ports = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,), qualified=True)
    physical_inventory=root._promotion._physical_accounting
    before=physical_inventory._measurements
    object.__setattr__(physical_inventory,'_measurements', None)
    try:
        with pytest.raises(ValueError,match='physical usage evidence'):
            root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    finally:
        object.__setattr__(physical_inventory,'_measurements',before)
    assert physical.claims==0 and conditional.contacts==0 and store.commits==0
    assert provider.requests==[]


def test_root_does_not_elevate_unrelated_c5_origins_into_paper_result():
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_ = _root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,), qualified=True)
    assert not hasattr(root, 'assess_original_handoff')
    actual=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert actual.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert not actual.authorizes_publication
    assert physical.claims==1 and store.commits==1


def test_strict_root_source_admits_real_regade_predecessor_before_claim():
    from tests.integration.test_family_first_scored_cas import connected_regrade
    lifecycle,plan,physical,backend,f25,provider,storage,conditional,old, f57 = connected_regrade()
    root,ports = _root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.REGRADE,), qualified=True)
    out = root.execute(request=plan.request,kind=PaperOperationKind.REGRADE)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert out.execution.cas.state is PaperCASState.COMMITTED
    assert storage.commits == 2 and physical.claims==1
    assert out.execution.cas.transaction.result_ref != old.transaction.result_ref
    assert ports.events == ['identity','selection','readiness','revision']
