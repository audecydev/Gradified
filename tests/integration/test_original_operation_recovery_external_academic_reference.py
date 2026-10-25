"""Independently authored falsification: provider accounting must not read on an incoherent scoring authority."""
from dataclasses import replace
import pytest
from grading.integration.paper_accounting import PaperAccountingState
from tests.integration.test_original_recovery_complete_paper_gate import _provider_accounting_fixture

@pytest.mark.parametrize('field',('rubric_ref','scoring_policy_ref'))
def test_issuer_academic_question_drift_must_deny_before_provider_read(field):
    consumer, original_intent, _, backend = _provider_accounting_fixture()
    issued_question = original_intent.issued.questions[0]
    mismatched_issuer = replace(original_intent.issued, questions=(
        replace(issued_question, **{field: 'UNAPPROVED-FOREIGN-ACADEMIC-REFERENCE'}),
        *original_intent.issued.questions[1:]))
    altered_intent = replace(original_intent, issued=mismatched_issuer)
    observation = consumer.reconcile(intent=altered_intent)
    assert observation.state is not PaperAccountingState.REPORTED_RECORDED, \
        'Recovery must not report positive provider accounting for contradictory academic scoring.'
    assert backend.reads == 0, 'Reject before provider backend read, not after its side effect.'

@pytest.mark.parametrize('field',('rubric_ref','scoring_policy_ref'))
def test_scored_academic_version_ids_must_not_depart_from_issuer_before_provider_read(field):
    consumer, original_intent, _, backend = _provider_accounting_fixture()
    result_record = original_intent.result.questions[0]
    original_ref = getattr(result_record.score, field)
    altered_score = replace(result_record.score,
        **{field: replace(original_ref, id='UNAPPROVED-SCORED-AUTHORITY')})
    altered_record = replace(result_record, score=altered_score)
    altered_result = replace(original_intent.result,
        questions=(altered_record, *original_intent.result.questions[1:]))
    observation = consumer.reconcile(intent=replace(original_intent, result=altered_result))
    assert observation.state is not PaperAccountingState.REPORTED_RECORDED
    assert backend.reads == 0

def test_valid_provider_accounting_control():
    consumer, original_intent, _, backend = _provider_accounting_fixture()
    observation = consumer.reconcile(intent=original_intent)
    assert observation.state is PaperAccountingState.REPORTED_RECORDED
    assert backend.reads == 1

def test_unapproved_family_drift_is_already_rejected():
    consumer, original_intent, _, backend = _provider_accounting_fixture()
    altered_issuer = replace(original_intent.issued, questions=(
        replace(original_intent.issued.questions[0], family='CHOICE'),
        *original_intent.issued.questions[1:]))
    observation = consumer.reconcile(intent=replace(original_intent,issued=altered_issuer))
    assert observation.state is PaperAccountingState.CONFLICT
    assert backend.reads == 0

@pytest.mark.parametrize('field', ('rubric_ref', 'scoring_policy_ref'))
@pytest.mark.parametrize('location', ('issuer', 'scored'))
def test_actual_choice_c5_blocks_academic_disagreement_before_any_audit_read(field, location):
    from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle
    from tests.integration.test_original_recovery_complete_paper_gate import _gate
    from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
    svc, plan, physical, audit_store, _ = setup_lifecycle()
    true_history = svc.execute_first(plan=plan)
    execution = true_history.cas.custody.outcome
    if location == 'issuer':
        original_issued = execution.issued_paper
        q = original_issued.questions[0]
        modified_issued = replace(original_issued, questions=(
            replace(q, **{field:'FOREIGN-ACADEMIC-ISSUANCE'}),
            *original_issued.questions[1:]))
        modified_execution = replace(execution, issued_paper=modified_issued)
    else:
        orig_result = execution.result
        scored_record = orig_result.questions[0]
        bad_ref = replace(getattr(scored_record.score, field), id='FOREIGN-ACADEMIC-SCORE')
        bad_record = replace(scored_record, score=replace(scored_record.score, **{field:bad_ref}))
        modified_execution = replace(execution, result=replace(orig_result,questions=(
            bad_record, *orig_result.questions[1:])))
    historical = replace(true_history, cas=replace(true_history.cas, custody=replace(
        true_history.cas.custody,outcome=modified_execution)))
    gate, _, _ = _gate(historical, audit_store)
    before = audit_store.reads
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert audit_store.reads == before
