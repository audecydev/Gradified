"""Regression tests for physical-attempt claim origin and callback exception handling."""

"""Independent original-request runtime cross-binding challenge."""
from dataclasses import replace
from grading.integration.attempt_authority import AttemptClaimRequest
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody, PaperRecoveryState
from tests.integration.test_whole_paper_choice_execution import _setup_two

class IssuedRequestSource:
    def __init__(self):
        self.requests = {}
        self.recovery_reads = []
    def resolve_original_request(self, *, plan, question_id, request_ref):
        if question_id == 'Q1':
            raise RuntimeError('Q1 source temporarily unavailable')
        return self.requests[question_id]

def as_request(reservation):
    return AttemptClaimRequest(reservation.request_ref, reservation.scope, reservation.family,
        reservation.runtime_id, reservation.runtime_version, reservation.implementation_ref,
        reservation.eligibility_policy_id, reservation.eligibility_policy_version,
        reservation.predecessor_result_ref, reservation.regrade_approval_ref)

def test_inconsistent_runtime_original_request_must_block_backend_read():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,request_source=source,
        max_identifier_characters=128,max_questions=10)
    record=svc.execute_and_capture(plan=plan)
    assert record.outcome.state == 'INDETERMINATE'
    assert record.questions[1].request_ref == 'REQUEST-Q2'
    assert record.questions[1].reservation is None
    source.requests['Q2'] = replace(as_request(store.last_reservation), runtime_id='foreign-runtime')
    recovered = svc.reconcile(record=record)
    assert store.reconciliations == 0, f'unverified runtime led to {store.reconciliations} backend recovery reads, state={recovered.questions[1].state}'

def test_unmodified_original_request_does_recover():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,request_source=source,
        max_identifier_characters=128,max_questions=10)
    record=svc.execute_and_capture(plan=plan)
    source.requests['Q2'] = as_request(store.last_reservation)
    recovered = svc.reconcile(record=record)
    assert store.reconciliations == 1
    assert recovered.questions[1].state in (PaperRecoveryState.RESERVED, PaperRecoveryState.UNKNOWN, PaperRecoveryState.CONFLICT)

def test_unverified_runtime_can_be_promoted_to_reserved_from_backend():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,request_source=source,
        max_identifier_characters=128,max_questions=10)
    record=svc.execute_and_capture(plan=plan)
    assert record.questions[1].reservation is None
    fabricated = replace(store.last_reservation, runtime_id='foreign-runtime')
    source.requests['Q2'] = as_request(fabricated)
    store.last_reservation = fabricated
    recovered = svc.reconcile(record=record)
    assert recovered.questions[1].state is not PaperRecoveryState.RESERVED, ('Original actual Q2 runtime differs; cannot positively promote foreign runtime recovery')

import pytest
@pytest.mark.parametrize('field,value', [
    ('runtime_id', 'foreign-runtime'),
    ('runtime_version', 'foreign-version'),
    ('implementation_ref', 'foreign-implementation'),
    ('eligibility_policy_id', 'foreign-policy'),
    ('eligibility_policy_version', 99),
])
def test_original_ambiguous_request_must_not_promote_changed_execution_binding(field,value):
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,request_source=source,
        max_identifier_characters=128,max_questions=10)
    record=svc.execute_and_capture(plan=plan)
    assert record.questions[1].reservation is None
    fabricated = replace(store.last_reservation, **{field:value})
    source.requests['Q2'] = as_request(fabricated)
    store.last_reservation = fabricated
    recovered = svc.reconcile(record=record)
    assert recovered.questions[1].state is not PaperRecoveryState.RESERVED, f'Foreign {field} accepted as physical original claim'

def test_ambiguous_request_does_not_admit_new_regrade_lineage():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,request_source=source,
        max_identifier_characters=128,max_questions=10)
    record=svc.execute_and_capture(plan=plan)
    assert record.questions[1].reservation is None
    fake = replace(store.last_reservation,
                   predecessor_result_ref='FOREIGN-PREDECESSOR',
                   regrade_approval_ref='FOREIGN-APPROVAL')
    source.requests['Q2'] = as_request(fake)
    store.last_reservation = fake
    recovered=svc.reconcile(record=record)
    assert recovered.questions[1].state is not PaperRecoveryState.RESERVED, 'Original first-run attempt misclassified as a regrade recovery'


"""Fresh independently authored C1/C2 callback-exception custody challenges."""
from dataclasses import replace
import pytest
from tests.integration.test_whole_paper_choice_execution import _setup_one
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody, PaperCustodyDenied, PaperRecoveryState, _admit


def service_for(source):
    root, plan, *_ = _setup_one()
    svc = ProductionPaperAttemptCustody(executor=root,attempts=root._attempts,
          request_source=source,max_identifier_characters=128,max_questions=10)
    return svc, svc.execute_and_capture(plan=plan)


@pytest.mark.parametrize('mode', ['explicit_cause','implicit_context','private_message'])
def test_request_source_denial_is_not_returned_as_public_denial(mode):
    class BadSource:
        def resolve_original_request(self, *, plan, question_id, request_ref):
            if mode == 'explicit_cause':
                raise PaperCustodyDenied('ISSUER_PRIVATE') from RuntimeError('ISSUER_SECRET')
            if mode == 'implicit_context':
                try:
                    raise RuntimeError('ISSUER_SECRET')
                except RuntimeError:
                    raise PaperCustodyDenied('Callback denied') from None
            raise PaperCustodyDenied('ISSUER_PRIVATE')
    svc,record=service_for(BadSource())
    # An exception from the installed external source is not a original-attempt custody-originated
    # integrity denial. The contract treats an unavailable callback as UNKNOWN.
    recovered=svc.reconcile(record=record)
    assert recovered.questions[0].state is PaperRecoveryState.UNKNOWN
    assert not recovered.authorizes_retry


def test_other_source_exception_is_unknown_control():
    class MissingSource:
        def resolve_original_request(self, *, plan, question_id, request_ref):
            raise RuntimeError('ISSUER_SECRET')
    svc,record=service_for(MissingSource())
    result=svc.reconcile(record=record)
    assert result.questions[0].state is PaperRecoveryState.UNKNOWN
    assert not result.authorizes_retry


def test_own_admission_error_has_no_exception_context_control():
    root,plan,*_= _setup_one()
    with pytest.raises(PaperCustodyDenied) as info:
        _admit(plan, object(), 10, 128)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_callback_mutation_plus_denial_still_fails_closed():
    class MutatingSource:
        def resolve_original_request(self, *, plan, question_id, request_ref):
            object.__setattr__(plan, 'source_revision', 'MUTATED-REVISION')
            raise PaperCustodyDenied('CALLBACK-PRIVATE-DENIAL')
    svc,record=service_for(MutatingSource())
    with pytest.raises(PaperCustodyDenied) as exc:
        svc.reconcile(record=record)
    assert str(exc.value) != 'CALLBACK-PRIVATE-DENIAL'
    assert exc.value.__cause__ is None and exc.value.__context__ is None




def test_ambiguous_claim_retains_actual_original_binding_before_recovery():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=source, max_identifier_characters=128, max_questions=10)
    record = svc.execute_and_capture(plan=plan)
    original = record.questions[1].original_f25_request
    assert original is not None
    assert original.request_ref == 'REQUEST-Q2'
    assert original.runtime_id == store.last_reservation.runtime_id
    assert original.eligibility_policy_version == store.last_reservation.eligibility_policy_version
    assert record.questions[1].reservation is None
    source.requests['Q2'] = as_request(store.last_reservation)
    recovered = svc.reconcile(record=record)
    assert recovered.questions[1].state is PaperRecoveryState.RESERVED
    assert store.reconciliations == 1 and store.claims == 2
    assert not recovered.authorizes_retry


def test_missing_original_observation_keeps_ambiguous_recovery_unknown_without_read():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=source, max_identifier_characters=128, max_questions=10)
    record = svc.execute_and_capture(plan=plan)
    source.requests['Q2'] = as_request(store.last_reservation)
    from grading.integration.whole_paper_attempt_custody import _admit
    traces = tuple(replace(t, original_f25_request=None) if t.question_id == 'Q2'
                   else t for t in record.outcome.contact_trace)
    outcome = replace(record.outcome, contact_trace=traces)
    missing = _admit(record.plan, outcome, 10, 128)
    recovered = svc.reconcile(record=missing)
    assert recovered.questions[1].state is PaperRecoveryState.UNKNOWN
    assert store.reconciliations == 0
    assert not recovered.authorizes_retry


def test_original_observation_cannot_be_overwritten_by_later_request_source():
    root, plan, _, _, _, store = _setup_two()
    store.timeout_second = True
    source = IssuedRequestSource()
    svc = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=source, max_identifier_characters=128, max_questions=10)
    record = svc.execute_and_capture(plan=plan)
    snapshot = record.questions[1].original_f25_request
    source.requests['Q2'] = replace(snapshot, runtime_id='foreign-runtime')
    recovered = svc.reconcile(record=record)
    assert recovered.questions[1].state is PaperRecoveryState.CONFLICT
    assert store.reconciliations == 0
    assert record.questions[1].original_f25_request == snapshot
