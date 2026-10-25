"""Independent physical attempt claim authority/transport failure regressions; no external trust claims."""
from dataclasses import replace

import pytest

from grading.integration.direct_provider_route import (
    DirectEffectDecision, ProductionDirectProviderRoute,
)
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_direct_provider_route_connected import install
from tests.integration.test_direct_issued_effect_authority import forged
from tests.integration.test_production_paper_operations import _root


def setup_first(*, limit=100000):
    cas, plan, _, physical, _, f25, _, store, _ = connected('DIRECT')
    executor = cas._custody._executor
    route, source, sender, accounting = install(executor, plan, 'FIRST')
    if limit != 100000:
        route = ProductionDirectProviderRoute(
            source=source, sender=sender, accounting=accounting,
            effect_authority=route._authorize.__self__,
            max_identifier_characters=128, max_questions=10,
            max_request_bytes=limit, max_response_bytes=100000, sender_ref='SENDER')
        object.__setattr__(executor, '_direct_route', route)
    lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    root, _ = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,))
    return root, plan, route, source, sender, accounting, physical, store


@pytest.mark.parametrize('bad', [object(), 'NOT AN ATTEMPT'])
def test_invalid_local_input_does_not_poison_uncontacted_provider_event(bad):
    root, plan, route, source, sender, writer, physical, store = setup_first()
    with pytest.raises(Exception):
        route.consume_issued_effect(source.grants[('Q1', 'FIRST')], bad)
    assert route._authorize.__self__.calls == 0
    assert not route._consumed
    out = root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and len(sender.dispatched) == len(writer.events) == 1


def test_malformed_typed_reservation_cannot_poison_uncontacted_provider_event():
    root, plan, route, source, sender, writer, physical, store = setup_first()
    full = route._authorize.__self__.executor._resolve(plan=plan)
    bad = replace(forged(full.scopes[0], 9), request_ref=False)
    with pytest.raises(Exception):
        route.consume_issued_effect(source.grants[('Q1', 'FIRST')], bad)
    assert route._authorize.__self__.calls == 0
    assert not route._consumed
    assert root.execute(request=plan.request, kind=PaperOperationKind.FIRST).execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and len(sender.dispatched) == len(writer.events) == 1


def test_known_canonical_size_violation_stops_before_f25_or_accounting():
    root, plan, route, source, sender, writer, physical, store = setup_first(limit=1)
    result = root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert result.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 0
    assert route._authorize.__self__.calls == 0
    assert not sender.dispatched and not writer.events and store.commits == 0


def test_issued_denied_attempt_must_not_be_reauthorized_after_revocation_changes():
    root, plan, route, source, sender, writer, physical, store = setup_first()
    owner = route._authorize.__self__
    owner.forced = DirectEffectDecision.DENIED
    first = root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert first.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and not sender.dispatched and not writer.events
    original = physical.last_reservation
    owner.forced = None
    with pytest.raises(ValueError):
        route.consume_issued_effect(source.grants[('Q1', 'FIRST')], original)
    assert not sender.dispatched and not writer.events
    assert owner.calls == 1


def test_unissued_claim_does_not_poison_later_genuine_claim():
    root, plan, route, source, sender, writer, physical, store = setup_first()
    full = route._authorize.__self__.executor._resolve(plan=plan)
    with pytest.raises(ValueError):
        route.consume_issued_effect(source.grants[('Q1', 'FIRST')], forged(full.scopes[0], 50))
    assert not route._consumed
    assert root.execute(request=plan.request, kind=PaperOperationKind.FIRST).execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and len(sender.dispatched) == len(writer.events) == 1


def test_untampered_direct_first_control():
    root, plan, route, source, sender, writer, physical, store = setup_first()
    assert root.execute(request=plan.request, kind=PaperOperationKind.FIRST).execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and len(sender.dispatched) == len(writer.events) == 1


def test_regade_request_too_large_does_not_consume_new_f25():
    from tests.integration.test_family_first_scored_cas import connected_regrade
    lifecycle, plan, physical, backend, f25, old, store, conditional, prior, f57 = connected_regrade()
    executor = lifecycle._cas._custody._executor
    route, source, sender, writer = install(executor, plan, 'REGRADE')
    tiny = ProductionDirectProviderRoute(source=source, sender=sender, accounting=writer,
        effect_authority=route._authorize.__self__, max_identifier_characters=128,
        max_questions=10, max_request_bytes=1, max_response_bytes=100000, sender_ref='SENDER')
    object.__setattr__(executor, '_direct_route', tiny)
    root, _ = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.REGRADE,))
    out = root.execute(request=plan.request, kind=PaperOperationKind.REGRADE)
    assert out.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 0 and tiny._authorize.__self__.calls == 0
    assert not sender.dispatched and not writer.events


def test_retry_request_too_large_does_not_consume_new_f25():
    from tests.integration.test_family_retry_accounting import connected_family_retry
    from grading.integration.paper_retry_grading import GradedRetryState
    retry, plan, physical, _, store, _, old = connected_family_retry('DIRECT')
    executor = retry._executor
    route, source, sender, writer = install(executor, plan, 'RETRY')
    tiny = ProductionDirectProviderRoute(source=source, sender=sender, accounting=writer,
        effect_authority=route._authorize.__self__, max_identifier_characters=128,
        max_questions=10, max_request_bytes=1, max_response_bytes=100000, sender_ref='SENDER')
    object.__setattr__(executor, '_direct_route', tiny)
    root, _ = _root(retry=retry, plan=plan, kinds=(PaperOperationKind.RETRY,))
    out = root.execute(request=plan.request, kind=PaperOperationKind.RETRY)
    assert out.execution.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims == 0 and tiny._authorize.__self__.calls == 0
    assert not sender.dispatched and not writer.events
