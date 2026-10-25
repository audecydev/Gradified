"""Family issuance facts are not executable physical attempt claim authorization."""
from dataclasses import replace
import pytest
from tests.integration.test_paper_execution_correlation import fixture, Issuer, composer
from grading.integration.paper_execution_correlation import PaperExecutionDenied

@pytest.mark.parametrize('families', [('DIRECT','DIRECT'), ('NUMERIC','NUMERIC'), ('DIRECT','NUMERIC'), ('NUMERIC','DIRECT')])
def test_issuer_correlates_exact_supported_nonchoice_paper(families):
    plan, rel = fixture()
    plan = replace(plan, questions=tuple(replace(q,family=f) for q,f in zip(plan.questions,families)))
    rel = replace(rel, questions=tuple(replace(q,family=f) for q,f in zip(rel.questions,families)))
    result = composer(Issuer(rel)).preflight(plan=plan)
    assert result.execution_state == 'CORRELATED_DIRECT_NUMERIC'
    assert tuple(q.family for q in result.issuer_relation.questions) == families

@pytest.mark.parametrize('families', [('CHOICE','DIRECT'),('NUMERIC','CHOICE')])
def test_mixed_choice_and_family_is_not_newly_authorized(families):
    plan, rel = fixture()
    plan = replace(plan, questions=tuple(replace(q,family=f) for q,f in zip(plan.questions,families)))
    rel = replace(rel, questions=tuple(replace(q,family=f) for q,f in zip(rel.questions,families)))
    assert composer(Issuer(rel)).preflight(plan=plan).execution_state == 'UNSUPPORTED_FAMILIES'

def test_issuer_family_substitution_denied():
    plan, rel = fixture()
    plan = replace(plan, questions=(replace(plan.questions[0],family='NUMERIC'),plan.questions[1]))
    with pytest.raises(PaperExecutionDenied):
        composer(Issuer(rel)).preflight(plan=plan)

@pytest.mark.parametrize('family', ['DIRECT','NUMERIC'])
def test_academic_f25_binds_exact_original_supported_family(family):
    from tests.integration.test_academic_effect_preclaim import setup_bound
    from grading.integration.academic_claim_binding import academic_intent
    root, plan, physical, backend = setup_bound()
    result = root.execute(plan=plan)
    assert result.state == 'COMPLETE'
    original = result.contact_trace[0].academic_preparation.intent
    request = replace(original.original_request, family=family)
    relation = replace(original.issued_paper, questions=(replace(original.issued_paper.questions[0],family=family),*original.issued_paper.questions[1:]))
    intent = academic_intent(request, relation, original.scoring, 128, 10)
    assert intent.question_id == original.question_id
    assert intent.original_request.family == family
    assert intent.issued_paper.questions[0].family == family
    with pytest.raises(ValueError):
        academic_intent(replace(request, family='CHOICE'),relation,original.scoring,128,10)
