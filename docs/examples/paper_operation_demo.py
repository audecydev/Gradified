"""Reproduce one supported paper operation with the repository's synthetic host ports.

Run from the repository root:
    PYTHONPATH=src:. python docs/examples/paper_operation_demo.py

The test fixture imports are deliberate: they are the in-repository, executable
reference implementations of the many strict host interfaces. They are not
qualified school, provider, or database implementations.
"""
from __future__ import annotations

from grading.integration.paper_lifecycle import PaperLifecycleState, ProductionPaperLifecycle
from grading.integration.production_paper_operations import (
    PaperOperationKind,
    ProductionPaperOperations,
)
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_admitted_paper_family_effect_continuity import installation
from tests.integration.test_direct_provider_route_connected import install
from tests.integration.test_family_first_scored_cas import POLICY, connected
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff


def demo() -> None:
    # A two-question DIRECT + NUMERIC paper. All sources are synthetic test ports;
    # no live provider, real teacher identity, or durable database is contacted.
    cas, plan, _, physical, _, permissions, provider, store, conditional = connected("MIXED")
    ports, admission = installation(plan)
    lifecycle = ProductionPaperLifecycle(
        cas=cas,
        permission_source=permissions.f57_source,
        legal_policy=POLICY,
        max_identifier_characters=128,
        max_questions=10,
    )
    # The DIRECT route requires source-matched model activity / receipt witnesses;
    # the connected test installer provides only synthetic versions.
    install(cas._custody._executor, plan, PaperOperationKind.FIRST.value)
    promotion = recorded_handoff("DIRECT")[0]
    operations = ProductionPaperOperations(
        admission=admission,
        promotion=promotion,
        lifecycle=lifecycle,
        retry=None,
        enabled_kinds=(PaperOperationKind.FIRST,),
        max_identifier_characters=128,
        max_questions=10,
    )
    result = operations.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert result.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert result.execution.cas.state is PaperCASState.COMMITTED
    assert ports.events == ["identity", "selection", "readiness", "revision"]
    score = result.execution.cas.custody.outcome.result.paper_score
    assert score is not None
    expected = (("Q1", "5"), ("Q2", "5"))
    actual = tuple((q.question_id, q.final_score.to_canonical_string()) for q in score.question_results)
    assert actual == expected, actual
    assert score.final_score.to_canonical_string() == "10"
    assert physical.claims == 2 and conditional.contacts == 1 and store.commits == 1
    assert result.authorizes_publication is False and result.authorizes_retry is False

    print("SYNTHETIC PAPER OPERATION PASS")
    print("Operation: FIRST")
    for question_id, marks in actual:
        print(f"{question_id}: {marks}")
    print("Paper candidate total: 10")
    print("Physical attempts: 2; conditional scored commits: 1")
    print("Publication authorized: False")


if __name__ == "__main__":
    demo()
