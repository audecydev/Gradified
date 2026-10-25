"""Local issuer-to-scored authority remains mandatory even when two sources agree."""
from dataclasses import replace
import pytest
from grading.integration.paper_accounting import PaperAccountingState
from tests.integration.test_original_recovery_complete_paper_gate import _provider_accounting_fixture

@pytest.mark.parametrize('field', ('rubric_ref','scoring_policy_ref'))
def test_two_agreeing_but_academically_inconsistent_sources_do_not_trigger_provider_read(field):
    consumer, intent, _, store = _provider_accounting_fixture()
    academic = replace(intent.issued.questions[0], **{field:'OTHER-AUTHORITY'})
    corrupt = replace(intent,issued=replace(intent.issued,questions=(
        academic,*intent.issued.questions[1:])))
    # Even a fixed-source adapter accidentally returning the same corrupted
    # historical record must NOT override an independent academic invariant.
    consumer._origin.__self__.original=corrupt
    assert consumer.reconcile(intent=corrupt).state is PaperAccountingState.CONFLICT
    assert store.reads==0
