"""Strict FIRST/REGRADE/RETRY root rejects a changed installed issuer before physical attempt claim."""
import pytest

from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_family_retry_accounting import connected_family_retry


@pytest.mark.parametrize('kind', (PaperOperationKind.FIRST, PaperOperationKind.REGRADE))
def test_strict_operation_refuses_foreign_installed_admission_reader_without_effect(kind):
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle = ProductionPaperLifecycle(
        cas=cas, permission_source=f25.f57_source, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10,
    )
    root, ports = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
    object.__setattr__(root._admission, '_revisions', lambda *, approval, readiness: ports.confirmation)
    with pytest.raises(Exception):
        root.execute(request=plan.request, kind=kind)
    assert ports.events == []
    assert physical.claims == 0 and store.commits == 0
    assert conditional.contacts == 0 and provider.requests == []


def test_strict_retry_refuses_swapped_paper_authority_before_any_original_claim():
    retry, plan, physical, _, store, _, provider = connected_family_retry('DIRECT')
    root, ports = _root(retry=retry, plan=plan, kinds=(PaperOperationKind.RETRY,), qualified=True)
    object.__setattr__(root._admission, '_answers', lambda *, approval: ports.readiness)
    with pytest.raises(Exception):
        root.execute(request=plan.request, kind=PaperOperationKind.RETRY)
    assert ports.events == []
    assert physical.claims == 0 and store.commits == 0 and provider.requests == []
