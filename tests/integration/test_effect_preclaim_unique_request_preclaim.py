from dataclasses import replace
from grading.integration.paper_lifecycle import PaperLifecycleState
from tests.integration.test_paper_lifecycle_regrade import setup_regrade, RegradeF25Issuer


def test_second_new_question_cannot_reuse_first_original_request_before_f25(monkeypatch):
    original = RegradeF25Issuer.identify_reservation_request
    def dup(self, *, scope, family, runtime_id, runtime_version, implementation_ref, eligibility_policy_id, eligibility_policy_version):
        val = original(self, scope=scope, family=family, runtime_id=runtime_id, runtime_version=runtime_version, implementation_ref=implementation_ref, eligibility_policy_id=eligibility_policy_id, eligibility_policy_version=eligibility_policy_version)
        if val.scope.question_id == 'Q2':
            return replace(val, request_ref='REGR-REQUEST-Q1')
        return val
    monkeypatch.setattr(RegradeF25Issuer, 'identify_reservation_request', dup)
    service, plan, physical, store, issuer, backend, old = setup_regrade(monkeypatch)
    response = service.execute_regrade(plan=plan)
    assert response.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 1, 'A duplicate original attempt request must be rejected before physical contact'
    assert store.commits == 1
    assert not response.authorizes_retry and not response.authorizes_publication
