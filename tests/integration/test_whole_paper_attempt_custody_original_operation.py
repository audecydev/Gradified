"""original-operation custody and recovery: genuine effectful result -> admitted custody -> read-only physical attempt claim recovery."""
from dataclasses import replace

import pytest

from grading.integration.attempt_authority import AttemptClaimRequest, AttemptClaimRecoveryDisposition
from grading.integration.whole_paper_attempt_custody import (
    ProductionPaperAttemptCustody, PaperCustodyDenied, PaperRecoveryState,
)
from tests.integration.test_whole_paper_choice_execution import _setup_one, _setup_two


class KnownRequests:
    """Fixture values are NOT authentic school or backend issuance."""
    def __init__(self):
        self.calls = []
        self.mode = None
    def resolve_original_request(self, *, plan, question_id, request_ref):
        self.calls.append((question_id, request_ref))
        if self.mode == 'missing':
            raise RuntimeError('backend request inaccessible')
        observed = self.requests[question_id]
        if self.mode == 'foreign':
            return replace(observed, request_ref='FOREIGN')
        if self.mode == 'wrong_paper':
            return replace(observed, scope=replace(observed.scope, grading_run_id='OTHER'))
        return observed


def _capture(root, plan, *, source=None):
    lookup = source if source is not None else KnownRequests()
    service = ProductionPaperAttemptCustody(
        executor=root, attempts=root._attempts, request_source=lookup,
        max_identifier_characters=128, max_questions=10)
    return service, lookup


def _request(res):
    return AttemptClaimRequest(res.request_ref, res.scope, res.family,
        res.runtime_id, res.runtime_version, res.implementation_ref,
        res.eligibility_policy_id, res.eligibility_policy_version,
        res.predecessor_result_ref, res.regrade_approval_ref)


def test_live_complete_execution_retains_original_question_and_attempt_custody():
    root, plan, _, _, _, store = _setup_two()
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    assert store.claims == 2
    assert record.outcome.state == 'COMPLETE'
    assert tuple(x.question_id for x in record.questions) == ('Q1', 'Q2')
    assert [x.reservation.attempt_id for x in record.questions] == ['ATT-Q1', 'ATT-Q2']
    assert record.nonpublishing and record.audit_commit_state == 'UNKNOWN'
    assert all(x.s1_verified for x in record.questions)
    assert not source.calls


def test_read_only_positive_recovery_reports_reserved_without_any_new_claim():
    root, plan, _, _, _, store = _setup_one()
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    source.requests = {'Q1': _request(record.questions[0].reservation)}
    before = store.claims
    recovered = service.reconcile(record=record)
    assert store.claims == before and store.reconciliations == 1
    assert recovered.questions[0].state is PaperRecoveryState.RESERVED
    assert recovered.questions[0].reservation == record.questions[0].reservation
    assert recovered.authorizes_retry is False and recovered.audit_commit_state == 'UNKNOWN'


@pytest.mark.parametrize('mode', ('foreign', 'wrong_paper', 'missing'))
def test_foreign_or_missing_original_request_never_starts_a_claim(mode):
    root, plan, _, _, _, store = _setup_one()
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    source.requests = {'Q1': _request(record.questions[0].reservation)}
    source.mode = mode
    before = store.claims
    recovered = service.reconcile(record=record)
    assert store.claims == before and store.reconciliations == 0
    assert recovered.questions[0].state in (PaperRecoveryState.CONFLICT, PaperRecoveryState.UNKNOWN)
    assert not recovered.authorizes_retry


def test_reconcile_before_any_f25_claim_does_not_contact_recovery_backend():
    root, plan, _, fresh, _, store = _setup_one()
    fresh.response = object()
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    assert record.outcome.result is None and store.claims == 0
    recovered = service.reconcile(record=record)
    assert not source.calls and store.reconciliations == 0
    assert recovered.questions[0].state is PaperRecoveryState.NOT_CONTACTED


def test_later_claim_uncertain_preserves_first_issued_attempt_without_grade():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    assert store.claims == 2
    assert record.outcome.state == 'INDETERMINATE' and record.outcome.result is None
    assert record.questions[0].s1_verified and record.questions[0].reservation is not None
    assert record.questions[1].f25_call_started
    assert record.questions[1].reservation is None
    assert record.audit_commit_state == 'UNKNOWN'
    source.mode = 'missing'
    result = service.reconcile(record=record)
    assert result.questions[1].state is PaperRecoveryState.UNKNOWN
    assert result.authorizes_retry is False and store.claims == 2


def test_cannot_supply_raw_prebuilt_outcome_as_lifecycle_grant():
    root, plan, _, _, _, store = _setup_one()
    service, _ = _capture(root, plan)
    assert not hasattr(service, 'record_caller_outcome')
    with pytest.raises(TypeError):
        service.execute_and_capture(plan=plan, outcome=object())
    assert store.claims == 0


def test_record_is_bound_to_exact_installation_and_original_paper():
    root, plan, _, _, _, store = _setup_one()
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    foreign = replace(record, plan=replace(record.plan,
        request=replace(record.plan.request, grading_run_id='OTHER')))
    with pytest.raises(PaperCustodyDenied):
        service.reconcile(record=foreign)
    assert store.reconciliations == 0


def test_not_reserved_never_authorizes_retry_even_if_backend_says_absent():
    root, plan, _, _, _, store = _setup_one()
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    source.requests = {'Q1': _request(record.questions[0].reservation)}
    store.claimed.clear()
    recovered = service.reconcile(record=record)
    assert recovered.questions[0].state is PaperRecoveryState.CONFLICT
    assert recovered.authorizes_retry is False


def test_no_provider_usage_fabricated_for_native_choice():
    root, plan, _, _, _, _ = _setup_one()
    service, _ = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    assert not hasattr(record, 'provider_cost')
    assert not hasattr(record, 'provider_receipt')


def test_duplicate_second_physical_claim_is_preserved_as_conflict_not_reused():
    root, plan, _, _, _, store = _setup_two()
    store.duplicate_attempt_id = True
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    assert record.outcome.state == 'INDETERMINATE' and record.outcome.result is None
    assert record.questions[0].reservation is not None
    assert record.questions[1].claim_conflict
    recovered = service.reconcile(record=record)
    assert recovered.questions[1].state is PaperRecoveryState.CONFLICT
    assert store.claims == 2 and store.reconciliations == 0


def test_observed_unknown_request_collision_is_not_promoted_to_success():
    root, plan, _, _, _, store = _setup_two()
    service, _ = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    traces = record.outcome.contact_trace
    duplicate = replace(traces[1], request_ref=traces[0].request_ref)
    forged_outcome = replace(record.outcome, contact_trace=(traces[0], duplicate))
    with pytest.raises(PaperCustodyDenied):
        # Any conflicting fabricated output must be rejected as non-authoritative.
        from grading.integration.whole_paper_attempt_custody import _admit
        _admit(record.plan, forged_outcome, 10, 128)


def test_source_mutating_original_paper_is_denied_before_recovery():
    root, plan, _, _, _, store = _setup_one()
    class MutatingSource(KnownRequests):
        def resolve_original_request(self, *, plan, question_id, request_ref):
            object.__setattr__(plan, 'source_revision', 'INVALID-MUTATION')
            return self.requests[question_id]
    source = MutatingSource()
    service, _ = _capture(root, plan, source=source)
    record = service.execute_and_capture(plan=plan)
    source.requests = {'Q1': _request(record.questions[0].reservation)}
    with pytest.raises(PaperCustodyDenied):
        service.reconcile(record=record)
    assert store.reconciliations == 0


def test_two_question_read_only_reconciliation_consumes_both_original_requests():
    root, plan, _, _, _, store = _setup_two()
    class KeyedRecovery(KnownRequests):
        def resolve_original_request(self, *, plan, question_id, request_ref):
            # This test store holds just its last reservation. Make the
            # permitted read-only fixture return the matching retained one.
            store.last_reservation = self.reservations[question_id]
            return super().resolve_original_request(
                plan=plan, question_id=question_id, request_ref=request_ref)
    source = KeyedRecovery()
    service, _ = _capture(root, plan, source=source)
    record = service.execute_and_capture(plan=plan)
    source.requests = {q.question_id: _request(q.reservation) for q in record.questions}
    source.reservations = {q.question_id: q.reservation for q in record.questions}
    recovery = service.reconcile(record=record)
    assert tuple(q.state for q in recovery.questions) == (PaperRecoveryState.RESERVED,) * 2
    assert store.claims == 2 and store.reconciliations == 2
    assert recovery.audit_commit_state == 'UNKNOWN' and not recovery.authorizes_retry


def test_reentrant_duplicate_unresolved_request_is_explicit_conflict():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    service, source = _capture(root, plan)
    record = service.execute_and_capture(plan=plan)
    traces = record.outcome.contact_trace
    assert len(traces) == 2
    duplicate = replace(traces[1], request_ref=traces[0].request_ref)
    outcome = replace(record.outcome, contact_trace=(traces[0], duplicate))
    from grading.integration.whole_paper_attempt_custody import _admit
    altered = _admit(record.plan, outcome, 10, 128)
    assert altered.questions[1].claim_conflict
    result = service.reconcile(record=altered)
    assert result.questions[1].state is PaperRecoveryState.CONFLICT
    assert store.reconciliations == 0
