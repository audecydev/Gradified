"""Verify original academic authority across first and regrade whole-paper promotions."""
from dataclasses import replace
import pytest
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.scored_paper_promotion import PaperHandoffEligibilityState
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle
from tests.integration.test_paper_lifecycle_regrade import setup_regrade
from tests.integration.test_original_recovery_complete_paper_gate import _gate


def original_history(kind, monkeypatch):
    if kind == 'first':
        svc, plan, physical, store, _ = setup_lifecycle()
        history = svc.execute_first(plan=plan)
        predecessor = None
    else:
        svc, plan, physical, store, _, _, predecessor = setup_regrade(monkeypatch)
        history = svc.execute_regrade(plan=plan)
    return history, store, physical, predecessor


def corrupt_original_preparation(history, question, field, raw):
    """Synchronized recovered original academic-preparation evidence; leave score/CAS authentic."""
    custody = history.cas.custody
    traces = list(custody.outcome.contact_trace)
    questions = list(custody.questions)
    original_preparation = questions[question].academic_preparation
    new_scoring = replace(original_preparation.intent.scoring,
                          **{field: ScoringDecimal.from_raw(raw)})
    altered = replace(original_preparation, intent=replace(
        original_preparation.intent, scoring=new_scoring))
    questions[question] = replace(questions[question], academic_preparation=altered)
    traces[question] = replace(traces[question], academic_preparation=altered)
    contradictory = replace(custody, questions=tuple(questions),
        outcome=replace(custody.outcome, contact_trace=tuple(traces)))
    return replace(history, cas=replace(history.cas, custody=contradictory))


@pytest.mark.parametrize('kind', ['first', 'regrade'])
@pytest.mark.parametrize('question,field,raw', [
    (0, 'maximum_score', '11'),
    (1, 'minimum_score', '-1'),
    (0, 'minimum_score', '-1'),
    (1, 'maximum_score', '11'),
])
def test_recovered_first_and_regrade_preparation_must_match_scored_paper_before_cas(
        kind, question, field, raw, monkeypatch):
    history, store, physical, predecessor = original_history(kind, monkeypatch)
    altered = corrupt_original_preparation(history, question, field, raw)
    gate, source, fixed = _gate(altered, store, prior=predecessor)
    before = (physical.claims, store.commits, store.reads)
    result = gate.assess()
    assert result.state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF, (
        f'{kind} accepted mismatched {field} in Q{question + 1} original preclaim')
    assert store.reads == before[2], 'CAS read preceded full-paper historical validation'
    assert (physical.claims, store.commits) == before[:2]


@pytest.mark.parametrize('kind', ['first', 'regrade'])
def test_unchanged_first_and_regrade_score_authority_handoff_positive(kind, monkeypatch):
    history, store, physical, predecessor = original_history(kind, monkeypatch)
    gate, _, _ = _gate(history, store, prior=predecessor)
    before = (physical.claims, store.commits)
    result = gate.assess()
    assert result.state is PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert not result.authorizes_publication and not result.authorizes_retry
    assert (physical.claims, store.commits) == before

@pytest.mark.parametrize('kind', ['first','regrade'])
def test_lost_cas_ack_does_not_overrule_contradictory_original_preparation(kind, monkeypatch):
    from grading.integration.paper_lifecycle import PaperLifecycleState
    from grading.integration.whole_paper_cas import PaperCASState, ProductionPaperCASDurableRecovery
    from grading.integration.scored_paper_promotion import ProductionPaperPromotion
    from grading.integration.paper_accounting import ProductionPaperAccounting
    from tests.integration.test_original_recovery_complete_paper_gate import FixedLifecycleOriginal, FixedPaperOriginal
    from tests.integration.test_paper_lifecycle_pre_effect import POLICY
    history, store, physical, predecessor = original_history(kind, monkeypatch)
    original_tx=history.cas.transaction
    corrupted=corrupt_original_preparation(history, 0, 'maximum_score','11')
    lost=replace(corrupted,state=PaperLifecycleState.UNKNOWN,cas=replace(corrupted.cas,
        state=PaperCASState.UNKNOWN, transaction=None,receipt=None,
        academic_binding_verified=False))
    durable=ProductionPaperCASDurableRecovery(original_source=FixedPaperOriginal(original_tx),
        store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    prev=None
    if predecessor is not None:
        prev=ProductionPaperCASDurableRecovery(
            original_source=FixedPaperOriginal(predecessor.transaction),
            store=store,legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    gate=ProductionPaperPromotion(original_source=FixedLifecycleOriginal(lost),
        audit_recovery=durable,predecessor_audit_recovery=prev,
        accounting=ProductionPaperAccounting(operations=(),max_identifier_characters=128),
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    before=(store.reads,store.commits,physical.claims)
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert store.reads==before[0], 'Historical grading-authority contradiction reached CAS on lost reply'
    assert (store.commits,physical.claims)==before[1:]

@pytest.mark.parametrize('kind', ['first', 'regrade'])
@pytest.mark.parametrize('question', [0, 1])
def test_preclaim_scoring_policy_version_for_another_question_cannot_be_substituted(
        kind, question, monkeypatch):
    """A matching current-question rubric alone never validates the whole paper."""
    history, store, physical, predecessor = original_history(kind, monkeypatch)
    custody = history.cas.custody
    original = custody.questions[question].academic_preparation
    scoring = original.intent.scoring
    other_index = 1 - question
    other = scoring.expected_questions[other_index]
    changed_other = replace(other, scoring_policy_ref=replace(
        other.scoring_policy_ref, version=other.scoring_policy_ref.version + 1))
    expected = list(scoring.expected_questions)
    expected[other_index] = changed_other
    modified = replace(original, intent=replace(original.intent,
        scoring=replace(scoring, expected_questions=tuple(expected))))
    questions = list(custody.questions)
    questions[question] = replace(questions[question], academic_preparation=modified)
    traces = list(custody.outcome.contact_trace)
    traces[question] = replace(traces[question], academic_preparation=modified)
    altered_custody = replace(custody, questions=tuple(questions),
        outcome=replace(custody.outcome, contact_trace=tuple(traces)))
    altered = replace(history, cas=replace(history.cas, custody=altered_custody))
    gate, _, _ = _gate(altered, store, prior=predecessor)
    before = (physical.claims, store.commits, store.reads)
    assert gate.assess().state is not PaperHandoffEligibilityState.ELIGIBLE_FOR_GOVERNED_HANDOFF
    assert (physical.claims, store.commits, store.reads) == before
