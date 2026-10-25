"""Source-owned regression: physical attempt claim is physical custody, not a lease on issuer revision."""
from dataclasses import replace
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_attempt_authority import AtomicStore


def test_q2_installed_f25_backend_revokes_paper_before_return_and_must_not_score(monkeypatch):
    root,plan,issuer,fresh,runtime,store=_setup_two()
    original=AtomicStore.claim_fresh_attempt
    def revoke_after_claim(self,*,request):
        reported=original(self,request=request)
        if self is store and request.scope.question_id=='Q2':
            issuer.relation=replace(issuer.relation,
                approval_revision='REVOKED_WHILE_Q2_F25_CALLBACK_WAS_RUNNING')
        return reported
    monkeypatch.setattr(AtomicStore,'claim_fresh_attempt',revoke_after_claim)
    outcome=root.execute(plan=plan)
    assert store.claims == 2
    assert outcome.state == 'INDETERMINATE'
    assert outcome.result is None
    assert tuple(c.question_id for c in outcome.completed)==('Q1',)
    assert len(outcome.observed_reservations)==2


def test_unchanged_issuer_two_physical_claims_and_one_frozen_paper_score():
    root,plan,issuer,fresh,runtime,store=_setup_two()
    outcome=root.execute(plan=plan)
    assert outcome.state=='COMPLETE' and outcome.result is not None
    assert store.claims==2 and len(outcome.completed)==2
