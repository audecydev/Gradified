from dataclasses import replace
import pytest
from grading.integration.governed_result_disposition import (
    GovernedResultEvidence, GovernedResultDisposition, ResultDisposition,
)


def sample(**kw):
    return replace(GovernedResultEvidence('school', 'run', 'original', 'approved-policy',
        'revision', 'source', True, True, True, True), **kw)


def test_fully_attested_evidence_can_only_reach_governed_handoff():
    result = GovernedResultDisposition(max_identifier_characters=128).evaluate(evidence=sample())
    assert result.disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
    assert result.reason_codes == ()
    assert not result.authorizes_publication and not result.authorizes_retry


@pytest.mark.parametrize('field', ['academic_evidence_complete','scoring_record_current',
                                     'reviewer_decision_current','adverse_flags_cleared'])
def test_each_adverse_source_fact_forces_review(field):
    result = GovernedResultDisposition(max_identifier_characters=128).evaluate(
        evidence=sample(**{field: False}))
    assert result.disposition is ResultDisposition.REVIEW
    assert result.reason_codes


@pytest.mark.parametrize('field', ['academic_evidence_complete','scoring_record_current',
                                     'reviewer_decision_current','adverse_flags_cleared'])
def test_each_unresolved_source_fact_forces_unknown(field):
    result = GovernedResultDisposition(max_identifier_characters=128).evaluate(
        evidence=sample(**{field: None}))
    assert result.disposition is ResultDisposition.UNKNOWN


def test_unknown_outweighs_adverse_to_preserve_uncertainty():
    result = GovernedResultDisposition(max_identifier_characters=128).evaluate(
        evidence=sample(academic_evidence_complete=False, reviewer_decision_current=None))
    assert result.disposition is ResultDisposition.UNKNOWN


@pytest.mark.parametrize('tampering', [
    {'policy_ref': ''}, {'source_revision': ' x'}, {'original_scored_result_ref': 'x'*129},
    {'reviewer_decision_current': 1}, {'academic_evidence_complete': 'TRUE'},
])
def test_malformed_or_forged_values_never_become_approved(tampering):
    with pytest.raises(ValueError):
        GovernedResultDisposition(max_identifier_characters=128).evaluate(evidence=sample(**tampering))


def test_foreign_object_does_not_trigger_comparison_or_hash():
    class Hostile:
        def __eq__(self, _): raise AssertionError('foreign equality invoked')
        def __hash__(self): raise AssertionError('foreign hash invoked')
    with pytest.raises(ValueError):
        GovernedResultDisposition(max_identifier_characters=128).evaluate(
            evidence=sample(tenant_ref=Hostile()))
