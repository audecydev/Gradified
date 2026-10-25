"""governed scored-paper handoff qualification must be source-recovered for the SAME scored original.

Uses controlled synthetic ports; this cannot authenticate a real source or vendor.
"""
from grading.integration.qualified_governed_operation import (
    OriginalQualifiedGovernedOutcome, ProductionOriginalQualifiedGovernedConsumer,
)
from grading.integration.governed_operation_consumer import (
    GovernedOperationState, ProductionGovernedOperationConsumer,
)
from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_governed_operation_consumer import rig
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_scored_paper_promotion_family_provider_continuity import recorded_handoff


def test_same_original_c5_admits_nonpublishing_direct_first():
    owner, source, original, views, plan, school, physical, provider, store, conditional = rig()
    qualified = ProductionOriginalQualifiedGovernedConsumer(governed=owner)
    outcome = qualified.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert type(outcome) is OriginalQualifiedGovernedOutcome
    assert outcome.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert outcome.original_c5.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims, store.commits, conditional.contacts) == (1, 1, 1)
    assert not outcome.authorizes_retry and not outcome.authorizes_publication


def test_lost_original_c5_history_after_valid_commit_cannot_qualify_handoff():
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    c5 = owner._execute.__self__._promotion
    c5._original.__self__.original = None
    qualified = ProductionOriginalQualifiedGovernedConsumer(governed=owner)
    outcome = qualified.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.governed.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.original_c5.state is PaperHandoffEligibilityState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == (1, 1, 1)
    assert not outcome.authorizes_publication


def test_eligible_c5_for_another_paper_cannot_qualify_direct_original():
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    foreign_c5 = recorded_handoff('MIXED')[0]
    assert foreign_c5.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    root, _ = _root(lifecycle=owner._execute.__self__._lifecycle, plan=plan,
                    kinds=(PaperOperationKind.FIRST,), qualified=True, promotion=foreign_c5)
    governed = ProductionGovernedOperationConsumer(
        operations=root, original_source=source, handoff=owner._handoff,
        max_identifier_characters=128)
    outcome = ProductionOriginalQualifiedGovernedConsumer(governed=governed).execute_and_assess(
        request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.governed.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.original_c5.state is PaperHandoffEligibilityState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == (1, 1, 1)


def test_uncertain_scored_cas_never_reads_c5_or_retries_provider():
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    conditional.lost_ack = True
    c5 = owner._execute.__self__._promotion
    original_reader = c5._original.__self__
    calls = original_reader.calls
    outcome = ProductionOriginalQualifiedGovernedConsumer(governed=owner).execute_and_assess(
        request=plan.request, kind=PaperOperationKind.FIRST)
    assert outcome.state is GovernedOperationState.UNKNOWN
    assert outcome.original_c5 is None
    assert original_reader.calls == calls
    assert (physical.claims, store.commits, conditional.contacts) == (1, 1, 1)


def test_original_c5_comparison_pair_must_be_complete():
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    c5 = owner._execute.__self__._promotion
    import pytest
    with pytest.raises(ValueError):
        c5.assess(expected_commit_ref='COMMIT')
    with pytest.raises(ValueError):
        c5.assess(expected_transaction=object(), expected_commit_ref='COMMIT')
    assert physical.claims == store.commits == 0
