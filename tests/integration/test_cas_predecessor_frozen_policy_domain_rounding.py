"""Regression tests for historical scoring provenance, policy domain, rounding, and durable recovery."""
from dataclasses import replace

import pytest

from grading.contracts.result import RuleDecision, RuleType
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.integration.whole_paper_cas import PaperCASState
from tests.integration.test_paper_cas_predecessor_contract_independent import scenario


def dec(raw: str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(raw)


@pytest.mark.parametrize(
    ('rule_type', 'configured_effect'),
    (
        (RuleType.DEDUCTION, '0'),
        (RuleType.DEDUCTION, '-1'),
        (RuleType.GATE, '-1'),
        (RuleType.GATE, '6'),
        (RuleType.CAP, '-1'),
        (RuleType.CAP, '6'),
    ),
)
def test_invalid_historical_rule_value_blocks_before_original_reads(
    rule_type: RuleType, configured_effect: str,
) -> None:
    _, predecessor, recover, outcome, backend, source = scenario()
    result = predecessor.intent.result
    record = result.questions[0]
    forged_decision = RuleDecision(
        rule_id='UNISSUABLE-RULE',
        rule_type=rule_type,
        triggered=False,
        configured_effect=dec(configured_effect),
    )
    forged_record = replace(
        record, score=replace(record.score, rule_decisions=(forged_decision,)),
    )
    records = (forged_record, *result.questions[1:])
    forged_paper = replace(
        result.paper_score,
        question_results=tuple(q.score for q in records),
    )
    prior = replace(
        predecessor,
        intent=replace(
            predecessor.intent,
            result=replace(result, questions=records, paper_score=forged_paper),
        ),
    )
    reads_before = backend.reads
    actual = recover.reconcile(outcome=outcome, disjoint_from=prior)
    assert actual is PaperCASState.BLOCKED, (rule_type, configured_effect, actual)
    assert source.calls == 0
    assert backend.reads == reads_before


def test_zero_rounding_cannot_create_a_nonzero_scored_result() -> None:
    _, predecessor, recover, outcome, backend, source = scenario()
    result = predecessor.intent.result
    record = result.questions[0]
    score = record.score
    stages = list(score.stage_effects)
    stages[2] = replace(
        stages[2], after=dec('0'), source_rule_ids=('DEDUCTION-5',),
    )
    stages[3] = replace(
        stages[3], before=dec('0'), after=dec('1'),
        source_rule_ids=('ROUND-ANY',),
    )
    forged_score = replace(
        score,
        rule_decisions=(RuleDecision('DEDUCTION-5', RuleType.DEDUCTION, True, dec('5')),),
        stage_effects=tuple(stages),
        score_before_rounding=dec('0'),
        final_score=dec('1'),
    )
    records = (replace(record, score=forged_score), *result.questions[1:])
    forged_paper = replace(
        result.paper_score,
        question_results=tuple(q.score for q in records),
        final_score=dec('6'),
    )
    prior = replace(
        predecessor,
        intent=replace(
            predecessor.intent,
            result=replace(result, questions=records, paper_score=forged_paper),
        ),
    )
    reads_before = backend.reads
    actual = recover.reconcile(outcome=outcome, disjoint_from=prior)
    assert actual is PaperCASState.BLOCKED, actual
    assert source.calls == 0
    assert backend.reads == reads_before


def test_genuine_disjoint_scored_predecessor_still_recovers() -> None:
    _, predecessor, recover, outcome, backend, source = scenario()
    reads_before = backend.reads
    assert (recover.reconcile(outcome=outcome, disjoint_from=predecessor)
            is PaperCASState.COMMITTED)
    assert source.calls == 1
    assert backend.reads == reads_before + 1


@pytest.mark.parametrize(
    ('before', 'after', 'deduction'),
    (('1', '5', '4'), ('5', '1', None), ('1.5', '1', '3.5')),
)
def test_rounding_cannot_invent_impossible_magnitude(
    before: str, after: str, deduction: str | None,
) -> None:
    # No positive-increment nearest rounding (HALF_UP or HALF_EVEN) can
    # output five times the input or one fifth of a nonzero input.
    _, predecessor, recover, outcome, backend, source = scenario()
    result = predecessor.intent.result
    record = result.questions[0]
    score = record.score
    stages = list(score.stage_effects)
    decisions = ()
    deduction_ids = ()
    if deduction is not None:
        decisions = (RuleDecision('DED-4', RuleType.DEDUCTION, True, dec(deduction)),)
        deduction_ids = ('DED-4',)
    stages[2] = replace(stages[2], after=dec(before), source_rule_ids=deduction_ids)
    stages[3] = replace(
        stages[3], before=dec(before), after=dec(after),
        source_rule_ids=('ROUND-ANY',),
    )
    forged_score = replace(
        score, rule_decisions=decisions, stage_effects=tuple(stages),
        score_before_rounding=dec(before), final_score=dec(after),
    )
    records = (replace(record, score=forged_score), *result.questions[1:])
    forged_paper = replace(
        result.paper_score,
        question_results=tuple(q.score for q in records),
        final_score=dec(str(int(after) + 5)),
    )
    prior = replace(
        predecessor,
        intent=replace(
            predecessor.intent,
            result=replace(result, questions=records, paper_score=forged_paper),
        ),
    )
    reads_before = backend.reads
    actual = recover.reconcile(outcome=outcome, disjoint_from=prior)
    assert actual is PaperCASState.BLOCKED, (before, after, actual)
    assert source.calls == 0
    assert backend.reads == reads_before
