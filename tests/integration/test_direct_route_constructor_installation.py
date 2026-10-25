"""Production constructor installation of the qualified route (not test-time route replacement)."""
from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_direct_provider_route_connected import install


class _OriginalFamilySource:
    def __init__(self, source):
        self._source = source

    def resolve_family_paper_inputs(self, *, plan):
        return self._source(plan=plan)


def test_constructor_installed_route_can_execute_first_through_strict_root():
    cas, plan, _, physical, _, f25, old_provider, storage, _ = connected('DIRECT')
    custody = cas._custody
    previous = custody._executor
    route, source, sender, writer = install(previous, plan, 'FIRST')
    rebuilt = ProductionWholePaperFamilyExecutor(
        correlation=previous._correlation, runtime=previous._binder,
        attempts=previous._attempts,
        inputs=_OriginalFamilySource(previous._resolve),
        max_identifier_characters=previous._max, max_questions=previous._questions,
        direct_route=route,
    )
    # Fixture substitution is at the enclosing custody owner, not route
    # installation. The new executor's route can only come from its constructor.
    object.__setattr__(custody, '_executor', rebuilt)
    lifecycle = ProductionPaperLifecycle(
        cas=cas, permission_source=f25.f57_source, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10,
    )
    root, _ = _root(lifecycle=lifecycle, plan=plan,
                    kinds=(PaperOperationKind.FIRST,))
    out = root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1 and storage.commits == 1
    assert len(sender.dispatched) == len(writer.events) == 1
    assert writer.events[0].identity == sender.dispatched[0].identity
    assert old_provider.requests == []
