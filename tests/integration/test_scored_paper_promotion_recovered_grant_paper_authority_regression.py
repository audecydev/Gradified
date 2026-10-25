"""Verify recovered grants remain bound to original paper academic authority."""
from dataclasses import replace
import pytest
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.contracts.paper_aggregation import GradingSpecRef
from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from tests.integration.test_scored_paper_retry_handoff import make

@pytest.mark.parametrize('tamper', ['changed_max', 'changed_min', 'foreign_spec', 'foreign_spec_version'])
def test_recovered_grant_scoring_must_match_original_preclaim_and_cas_before_read(tamper):
    c5, source, outcome, cas_store, f25, ordinary_f25 = make()
    scoring=outcome.authorization.scoring
    if tamper == 'changed_max':
        scoring=replace(scoring,maximum_score=ScoringDecimal.from_raw('11'))
    elif tamper == 'changed_min':
        scoring=replace(scoring,minimum_score=ScoringDecimal.from_raw('-1'))
    elif tamper == 'foreign_spec':
        scoring=replace(scoring,grading_spec_ref=GradingSpecRef('FOREIGN-GRADING-SPEC',1))
    else:
        scoring=replace(scoring,grading_spec_ref=GradingSpecRef('SPEC-1',3))
    source.original=replace(outcome,authorization=replace(outcome.authorization,scoring=scoring))
    before=cas_store.reads
    actual=c5.assess().state
    assert actual is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, f'{tamper} wrongly eligible'
    assert cas_store.reads == before, f'{tamper} contacted CAS before full original custody check'
    assert (f25.claims,ordinary_f25.claims,cas_store.commits)==(2,0,1)

def test_original_unchanged_retry_handoff_positive_control():
    c5,source,outcome,cas_store,f25,ordinary_f25=make()
    before=cas_store.reads
    assert c5.assess().state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (cas_store.reads-before,f25.claims,ordinary_f25.claims,cas_store.commits)==(1,2,0,1)
