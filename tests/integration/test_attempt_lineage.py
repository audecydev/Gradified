"""attempt provenance installed trusted-ledger/legal operation transition/audit structural integration tests.

All fixtures are non-authoritative. No durable uniqueness or audit transaction
is established by these unit/integration tests.
"""
from dataclasses import replace
import pytest

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import (
    AttemptDisposition, TrustedAttemptObservation, GradingTransitionApproval, LegalGradingTransitionPolicy,
    AttemptAuditEvent, AuditCommitReceipt, AuditedOneQuestionCandidate,
    AttemptLineageDenied, AttemptLineageUnavailable, AttemptLineageContractError,
    ProductionChoiceAttemptLifecycle,
)
from grading.integration.evaluator_invocation import (
    AttemptReservationRejected, InvocationDenied, InvocationUnavailable,
)
from tests.integration.test_evaluator_invocation import (
    assembled_invoker, FixtureAttempts, _track_choice_and_s2a_calls,
)


class FixtureLedger:
    def __init__(self):
        self.calls = []
        self.disposition = AttemptDisposition.NEW
        self.replacement = None
        self.failure = None
    def classify_owned_result(self, *, reservation, candidate):
        self.calls.append(reservation)
        if self.failure is not None: raise self.failure
        record = TrustedAttemptObservation(reservation, self.disposition,
                                           GradingJobState.SCORING,
                                           'LEDGER-R1', 'EVENT-R1', 'RESULT-R1')
        return self.replacement(record) if self.replacement is not None else record


class FixtureTransitions:
    def __init__(self):
        self.calls = []
        self.replacement = None
        self.failure = None
    def authorize_result_transition(self, *, observation, candidate):
        self.calls.append((observation, candidate))
        if self.failure is not None: raise self.failure
        record = GradingTransitionApproval(candidate.reservation.scope,
                                       candidate.reservation.attempt_id,
                                       observation.current_state,
                                       GradingJobState.RISK_EVALUATION,
                                       'TEST-F57-POLICY', 1, 'TEST-APPROVAL',
                                       observation.ledger_revision)
        return self.replacement(record) if self.replacement is not None else record


class FixtureAudit:
    def __init__(self):
        self.events = []
        self.replacement = None
        self.failure = None
    def commit_event(self, *, event, candidate):
        self.events.append(event)
        if self.failure is not None: raise self.failure
        record = AuditCommitReceipt(event.event_ref, event.ledger_revision,
                                    event.attempt_id, event.result_ref, 'TEST-TX-1',
                                    event.target_state, event.approval_ref,
                                    event.request_ref,
                                    event.predecessor_result_ref,event.regrade_approval_ref)
        return self.replacement(record) if self.replacement is not None else record


def fixture_policy():
    # This is NOT a signed legal transition approval for production use.
    return LegalGradingTransitionPolicy('TEST-F57-POLICY', 1, (
        (GradingJobState.SCORING, GradingJobState.RISK_EVALUATION),
    ))


def build(*, attempts=None):
    invoker, request, ports, attempt_port = assembled_invoker(attempts)
    ledger, f57, audit = FixtureLedger(), FixtureTransitions(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
    )
    return owner, request, ledger, f57, audit, attempt_port


def test_actual_g0_f25_choice_s2a_lineage_f57_audit_one_owned_call():
    owner, request, ledger, f57, audit, attempts = build()
    with _track_choice_and_s2a_calls() as calls:
        result = owner.run_choice(request=request)
    assert type(result) is AuditedOneQuestionCandidate
    assert calls == {'choice': 1, 's2a': 1}
    assert len(attempts.events) == len(ledger.calls) == len(f57.calls) == len(audit.events) == 1
    assert audit.events[0].event_kind == 'ATTEMPT_RESULT_CANDIDATE'
    assert audit.events[0].attempt_id == result.execution.reservation.attempt_id
    assert result.audit_receipt.event_ref == audit.events[0].event_ref
    assert result.audit_receipt.result_ref == audit.events[0].result_ref
    assert result.execution.emitted_judgments is result.execution.execution.questions[0].verified.evaluated_judgments


@pytest.mark.parametrize('disposition,expected', [
    (AttemptDisposition.REPLAY_IDENTICAL, AttemptLineageDenied),
    (AttemptDisposition.CONFLICTING_DUPLICATE, AttemptLineageDenied),
    (AttemptDisposition.STALE_OR_LATE, AttemptLineageDenied),
    (AttemptDisposition.FOREIGN, AttemptLineageDenied),
    (AttemptDisposition.INDETERMINATE, AttemptLineageUnavailable),
])
def test_nonfresh_ledger_prevents_f57_and_audit(disposition,expected):
    owner, request, ledger, f57, audit, _ = build()
    ledger.disposition = disposition
    with pytest.raises(expected):owner.run_choice(request=request)
    assert len(ledger.calls)==1 and not f57.calls and not audit.events


@pytest.mark.parametrize('mutation', [
    lambda r: replace(r, reservation=replace(r.reservation, attempt_id='FOREIGN')),
    lambda r: replace(r, reservation=replace(r.reservation, reservation_ref='FOREIGN')),
    lambda r: replace(r, reservation=replace(r.reservation, runtime_id='FOREIGN')),
    lambda r: replace(r, reservation=replace(r.reservation, scope=replace(r.reservation.scope,tenant_ref='FOREIGN'))),
    lambda r: replace(r, disposition='NEW'),
    lambda r: replace(r, current_state='SCORING'),
    lambda r: replace(r, event_ref=True),
    lambda r: replace(r, result_ref=''),
])
def test_foreign_or_malformed_ledger_claim_cannot_authorize_audit(mutation):
    owner, request, ledger, f57, audit, _ = build()
    ledger.replacement=mutation
    with pytest.raises((AttemptLineageDenied,AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert not f57.calls and not audit.events


@pytest.mark.parametrize('mutation', [
    lambda r: replace(r,scope=replace(r.scope,tenant_ref='FOREIGN')),
    lambda r: replace(r,attempt_id='FOREIGN'),
    lambda r: replace(r,source_state=GradingJobState.COMPLETED),
    lambda r: replace(r,target_state='COMPLETED'),
    lambda r: replace(r,policy_version=True),
    lambda r: replace(r,policy_id='DIFFERENT-F57-POLICY'),
    lambda r: replace(r,policy_version=2),
    lambda r: replace(r,target_state=GradingJobState.COMPLETED),
    lambda r: replace(r,approval_ref=''),
])
def test_foreign_or_malformed_f57_approval_cannot_authorize_audit(mutation):
    owner,request,ledger,f57,audit,_=build()
    f57.replacement=mutation
    with pytest.raises((AttemptLineageDenied,AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert len(f57.calls)==1 and not audit.events


@pytest.mark.parametrize('mutation', [
    lambda r: replace(r,event_ref='FOREIGN'),
    lambda r: replace(r,ledger_revision='FOREIGN'),
    lambda r: replace(r,attempt_id='FOREIGN'),
    lambda r: replace(r,target_state=GradingJobState.COMPLETED),
    lambda r: replace(r,transaction_ref=''),
    lambda r: replace(r,result_ref='FOREIGN'),
    lambda r: object(),
])
def test_bad_audit_receipt_cannot_claim_success(mutation):
    owner,request,ledger,f57,audit,_=build()
    audit.replacement=mutation
    with pytest.raises(AttemptLineageContractError):
        owner.run_choice(request=request)
    assert len(audit.events)==1


@pytest.mark.parametrize('stage', ['ledger','f57','audit'])
def test_unavailable_external_callback_never_claims_committed_success(stage):
    owner,request,ledger,f57,audit,_=build()
    {'ledger':ledger,'f57':f57,'audit':audit}[stage].failure=RuntimeError('PRIVATE_AUDIT_BACKEND_SECRET')
    with pytest.raises(AttemptLineageUnavailable) as err:
        owner.run_choice(request=request)
    assert err.value.__context__ is None and err.value.__cause__ is None
    assert 'PRIVATE' not in str(err.value)
    assert len(audit.events)==(1 if stage=='audit' else 0)


def test_explicit_f25_refusal_preserves_denial_not_uncertain_and_never_audits():
    class Refusing(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            self.events.append('refused')
            raise AttemptReservationRejected('PRIVATE_EXPLICIT_DENIAL')
    owner,request,ledger,f57,audit,attempts=build(attempts=Refusing())
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageDenied):owner.run_choice(request=request)
    assert calls=={'choice':0,'s2a':0}
    assert len(attempts.events)==1 and not ledger.calls and not f57.calls and not audit.events


def test_lifecycle_rejects_caller_constructed_candidate_path():
    owner,request,ledger,f57,audit,_=build()
    assert not hasattr(owner,'commit_candidate')
    with pytest.raises(TypeError):
        owner.run_choice(request=request, candidate=object())
    assert not ledger.calls and not f57.calls and not audit.events


def test_translated_invocation_denial_never_retains_private_ambient_error():
    class Refusing(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            raise AttemptReservationRejected('PRIVATE_ORIGINAL_F25_DENIAL')
    owner, request, ledger, f57, audit, _ = build(attempts=Refusing())
    try:
        raise RuntimeError('PRIVATE_CALLER_EXCEPTION')
    except RuntimeError:
        with pytest.raises(AttemptLineageDenied) as caught:
            owner.run_choice(request=request)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    import traceback
    assert 'PRIVATE' not in ''.join(traceback.format_exception(caught.value))
    assert not ledger.calls and not f57.calls and not audit.events


def test_ledger_candidate_mutation_denied_before_f57_and_audit():
    class MutatingLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            observation = super().classify_owned_result(
                reservation=reservation, candidate=candidate)
            object.__setattr__(candidate.reservation, 'attempt_id', 'FOREIGN')
            return observation
    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = MutatingLedger(), FixtureTransitions(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    with pytest.raises(AttemptLineageDenied): owner.run_choice(request=request)
    assert len(ledger.calls)==1 and not f57.calls and not audit.events


def test_ledger_mutation_plus_outage_integrity_denial_precedes_unavailability():
    class MutatingFailingLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            object.__setattr__(candidate.reservation, 'attempt_id', 'FOREIGN')
            raise RuntimeError('PRIVATE_BACKEND_FAILURE')
    invoker, request, _, _ = assembled_invoker()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=MutatingFailingLedger(),
        transitions=FixtureTransitions(), audit=FixtureAudit(),
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    with pytest.raises(AttemptLineageDenied) as caught:
        owner.run_choice(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_audit_event_scope_corruption_cannot_return_success():
    class CorruptAudit(FixtureAudit):
        def commit_event(self, *, event, candidate):
            receipt = super().commit_event(event=event, candidate=candidate)
            object.__setattr__(event, 'scope', replace(event.scope, tenant_ref='FOREIGN'))
            return receipt
    invoker, request, _, _ = assembled_invoker()
    audit = CorruptAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=FixtureLedger(),
        transitions=FixtureTransitions(), audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    with pytest.raises(AttemptLineageDenied):owner.run_choice(request=request)
    assert len(audit.events)==1  # possible external audit effect, no success


def test_missing_or_malformed_installed_f57_policy_fails_before_execution():
    invoker,_,_,_=assembled_invoker()
    variants=(None, LegalGradingTransitionPolicy('TEST-F57-POLICY',True,()),
              LegalGradingTransitionPolicy('TEST-F57-POLICY',1,((GradingJobState.COMPLETED,GradingJobState.GRADING),)),
              LegalGradingTransitionPolicy('TEST-F57-POLICY',1,((GradingJobState.SCORING,'COMPLETED'),)))
    for variant in variants:
        with pytest.raises(AttemptLineageContractError):
            ProductionChoiceAttemptLifecycle(
                invoker=invoker,ledger=FixtureLedger(),transitions=FixtureTransitions(),
                audit=FixtureAudit(),approved_f57_policy=variant,
                max_identifier_characters=64)


# Permanent independent attempt provenance lifecycle/callback custody falsification regressions.
def _owner_with(ledger=None, f57=None, audit=None):
    invoker, request, _, attempt_port = assembled_invoker()
    ledger = ledger if ledger is not None else FixtureLedger()
    f57 = f57 if f57 is not None else FixtureTransitions()
    audit = audit if audit is not None else FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    return owner, request, ledger, f57, audit, attempt_port


def test_ledger_cannot_corrupt_completed_score_and_still_return_audited_success():
    class AlteringLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            obs = super().classify_owned_result(reservation=reservation, candidate=candidate)
            # Exact dataclass type and object identity preserved, contents corrupted.
            result = candidate.execution.questions[0].score
            object.__setattr__(result, 'final_score', 'UNTRUSTED_REPLACEMENT')
            return obs
    owner, request, ledger, f57, audit, attempts = _owner_with(ledger=AlteringLedger())
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
            owner.run_choice(request=request)
    assert calls == {'choice': 1, 's2a': 1}
    assert not f57.calls and not audit.events, 'No lifecycle transition or audit on corrupted execution'


def test_f57_cannot_mutate_ledger_result_reference_and_still_return_audited_success():
    class AlteringF57(FixtureTransitions):
        def authorize_result_transition(self, *, observation, candidate):
            record = super().authorize_result_transition(observation=observation, candidate=candidate)
            object.__setattr__(observation, 'result_ref', 'REPLACED-RESULT-REF')
            return record
    owner, request, ledger, f57, audit, attempts = _owner_with(f57=AlteringF57())
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert not audit.events, 'No audit commit after ledger result_ref corruption'


def test_audit_cannot_corrupt_f57_approval_and_return_claimed_success():
    class RecordingF57(FixtureTransitions):
        last_approval = None
        def authorize_result_transition(self, *, observation, candidate):
            self.last_approval = super().authorize_result_transition(observation=observation, candidate=candidate)
            return self.last_approval
    f57 = RecordingF57()
    class AlteringAudit(FixtureAudit):
        def commit_event(self, *, event, candidate):
            receipt = super().commit_event(event=event, candidate=candidate)
            object.__setattr__(f57.last_approval, 'target_state', 'UNTRUSTED_TERMINAL_STATE')
            return receipt
    owner, request, ledger, f57, audit, attempts = _owner_with(f57=f57, audit=AlteringAudit())
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    # commit might already have happened: no false successful return is allowed
    assert len(audit.events) == 1


def test_same_lifecycle_cannot_reenter_during_ledger_and_duplicate_physical_execution():
    class ReenteringLedger(FixtureLedger):
        depth = 0
        owner = None
        request = None
        def classify_owned_result(self, *, reservation, candidate):
            self.depth += 1
            try:
                if self.depth == 1:
                    self.owner.run_choice(request=self.request)
                return super().classify_owned_result(reservation=reservation, candidate=candidate)
            finally:
                self.depth -= 1
    ledger = ReenteringLedger()
    owner, request, ledger, f57, audit, attempts = _owner_with(ledger=ledger)
    ledger.owner = owner
    ledger.request = request
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageDenied):
            owner.run_choice(request=request)
    assert calls == {'choice':1,'s2a':1}, 'Nested call must not invoke CHOICE or the scoring execution boundary'
    assert len(attempts.events) == 1, 'Only one attempt reservation is allowed'


def test_fixture_positive_control():
    owner, request, ledger, f57, audit, attempts = build()
    result = owner.run_choice(request=request)
    assert type(result) is AuditedOneQuestionCandidate
    assert result.observation.result_ref == result.audit_receipt.result_ref
    assert result.approval.target_state is result.audit_receipt.target_state


def test_f57_cannot_change_observation_disposition_to_replay_and_still_audit():
    from grading.integration.attempt_lineage import AttemptDisposition
    class ReplayingF57(FixtureTransitions):
        def authorize_result_transition(self, *, observation, candidate):
            approval = super().authorize_result_transition(observation=observation,candidate=candidate)
            object.__setattr__(observation, 'disposition', AttemptDisposition.REPLAY_IDENTICAL)
            return approval
    owner, request, ledger, f57, audit, attempts = _owner_with(f57=ReplayingF57())
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert len(audit.events) == 0


def test_audit_cannot_change_approval_policy_identifier_and_still_succeed():
    class RecordingF57(FixtureTransitions):
        last_approval = None
        def authorize_result_transition(self, *, observation, candidate):
            self.last_approval = super().authorize_result_transition(observation=observation,candidate=candidate)
            return self.last_approval
    f57 = RecordingF57()
    class MalformingAudit(FixtureAudit):
        def commit_event(self, *, event, candidate):
            receipt = super().commit_event(event=event, candidate=candidate)
            object.__setattr__(f57.last_approval, 'policy_id', 'FOREIGN-UNAPPROVED-F57')
            return receipt
    owner, request, ledger, f57, audit, attempts = _owner_with(f57=f57, audit=MalformingAudit())
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert len(audit.events) == 1  # an external effect might have happened; no success


def test_audit_event_corruption_plus_backend_exception_cannot_be_reported_as_simple_unavailability():
    class CorruptThenRaiseAudit(FixtureAudit):
        def commit_event(self, *, event, candidate):
            self.events.append(event)
            object.__setattr__(event, 'result_ref', 'FOREIGN-RESULT')
            raise RuntimeError('PRIVATE_BACKEND_EXC')
    owner, request, ledger, f57, audit, attempts = _owner_with(audit=CorruptThenRaiseAudit())
    with pytest.raises(AttemptLineageDenied):
        owner.run_choice(request=request)
    assert len(audit.events) == 1  # effect may already have occurred


def test_f57_candidate_corruption_plus_backend_exception_prioritizes_corruption():
    class CorruptThenRaiseF57(FixtureTransitions):
        def authorize_result_transition(self, *, observation, candidate):
            self.calls.append((observation,candidate))
            object.__setattr__(candidate.execution.questions[0].score, 'final_score','FOREIGN')
            raise RuntimeError('PRIVATE_BACKEND_EXC')
    owner, request, ledger, f57, audit, attempts = _owner_with(f57=CorruptThenRaiseF57())
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert len(f57.calls) == 1 and not audit.events


# Additional independent exceptional-path and duplicate-call regressions.
def test_f57_callback_cannot_turn_new_ledger_observation_into_replay_before_audit():
    class RewritingF57(FixtureTransitions):
        def authorize_result_transition(self, *, observation, candidate):
            object.__setattr__(observation, 'disposition', AttemptDisposition.REPLAY_IDENTICAL)
            object.__setattr__(observation, 'result_ref', 'FOREIGN-RESULT')
            return super().authorize_result_transition(observation=observation, candidate=candidate)

    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = FixtureLedger(), RewritingF57(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
    )
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert len(ledger.calls) == len(f57.calls) == 1
    assert audit.events == []  # corrupted ledger authority must not reach commit


def test_ledger_callback_cannot_change_scored_result_after_b56_ownership_check():
    class MutatingLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            observation = super().classify_owned_result(reservation=reservation, candidate=candidate)
            score = candidate.execution.questions[0].score
            object.__setattr__(score, 'numeric_profile_version', 'FOREIGN-PROFILE')
            return observation

    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = MutatingLedger(), FixtureTransitions(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
    )
    with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)):
        owner.run_choice(request=request)
    assert len(ledger.calls) == 1
    assert f57.calls == [] and audit.events == []


def test_f57_exception_after_observation_mutation_cannot_be_plain_outage():
    class MutatingFailingF57(FixtureTransitions):
        def authorize_result_transition(self, *, observation, candidate):
            object.__setattr__(observation, 'disposition', AttemptDisposition.CONFLICTING_DUPLICATE)
            raise RuntimeError('PRIVATE_F57_EXCEPTION')

    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = FixtureLedger(), MutatingFailingF57(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
    )
    try:
        raise RuntimeError('PRIVATE_AMBIENT')
    except RuntimeError:
        with pytest.raises((AttemptLineageDenied, AttemptLineageContractError)) as caught:
            owner.run_choice(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert audit.events == []


def test_ledger_reentry_same_owner_must_not_execute_nested_choice_before_lineage_decision():
    class ReenteringLedger(FixtureLedger):
        def __init__(self):
            super().__init__()
            self.owner = None
            self.reentered = False
            self.nested_outcome = None
        def classify_owned_result(self, *, reservation, candidate):
            if not self.reentered:
                self.reentered = True
                try:
                    self.owner.run_choice(request=request)
                except (AttemptLineageDenied, AttemptLineageContractError, AttemptLineageUnavailable) as e:
                    self.nested_outcome = e
            return super().classify_owned_result(reservation=reservation, candidate=candidate)

    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = ReenteringLedger(), FixtureTransitions(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64,
    )
    ledger.owner = owner
    with _track_choice_and_s2a_calls() as calls:
        owner.run_choice(request=request)
    assert ledger.nested_outcome is not None
    assert calls == {'choice': 1, 's2a': 1}
    assert len(audit.events) == 1


def test_nested_reentry_denial_sanitizes_private_ambient_context():
    class ReenteringLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            try:
                raise RuntimeError('PRIVATE_NESTED_CALLBACK_CONTEXT')
            except RuntimeError:
                with pytest.raises(AttemptLineageDenied) as caught:
                    self.owner.run_choice(request=self.request)
            assert caught.value.__cause__ is None and caught.value.__context__ is None
            return super().classify_owned_result(reservation=reservation, candidate=candidate)

    owner, request, ledger, f57, audit, attempts = build()
    replacement = ReenteringLedger()
    invoker, request, _, attempts = assembled_invoker()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=replacement, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    replacement.owner = owner
    replacement.request = request
    with _track_choice_and_s2a_calls() as calls:
        owner.run_choice(request=request)
    assert calls == {'choice': 1, 's2a': 1}
    assert len(attempts.events) == len(audit.events) == 1


def test_callback_cannot_substitute_another_canonical_numeric_score():
    from grading.contracts.scoring_decimal import ScoringDecimal
    class ReplacingLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            observation = super().classify_owned_result(reservation=reservation, candidate=candidate)
            score = candidate.execution.questions[0].score
            original = score.final_score.as_decimal()
            substitute = ScoringDecimal.from_raw(0 if original != 0 else 1)
            object.__setattr__(score, 'final_score', substitute)
            return observation

    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = ReplacingLedger(), FixtureTransitions(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    with pytest.raises(AttemptLineageDenied):
        owner.run_choice(request=request)
    assert len(ledger.calls) == 1 and not f57.calls and not audit.events


def test_callback_cannot_mutate_admitted_execution_context():
    class ReplacingLedger(FixtureLedger):
        def classify_owned_result(self, *, reservation, candidate):
            observation = super().classify_owned_result(reservation=reservation, candidate=candidate)
            context = candidate.execution.context
            object.__setattr__(context, 'grading_run_id', 'FOREIGN-GRADING-RUN')
            return observation

    invoker, request, _, _ = assembled_invoker()
    ledger, f57, audit = ReplacingLedger(), FixtureTransitions(), FixtureAudit()
    owner = ProductionChoiceAttemptLifecycle(
        invoker=invoker, ledger=ledger, transitions=f57, audit=audit,
        approved_f57_policy=fixture_policy(), max_identifier_characters=64)
    with pytest.raises(AttemptLineageDenied):
        owner.run_choice(request=request)
    assert len(ledger.calls) == 1 and not f57.calls and not audit.events


# R3 independent actual-repository operation lifetime regression.
from tests.integration.test_attempt_history import Writer
"""Independent full-composition active-correlation hostile regression."""
"""Proposed Gradified full-repository hostile regression for R3.

Requires the accepted P-B checkout plus the exact R3 15 additions.
This file is syntax-checked only in the independent review environment:
the inherited parent repository was not available to execute it here.
"""
import pytest

from grading.integration.attempt_authority import assemble_controlled_choice_root
from grading.integration.attempt_history import AttemptEventAcknowledgment, AttemptStage
from grading.integration.attempt_lineage import AttemptLineageUnavailable
from grading.integration.evaluator_invocation import AttemptReservationRejected
from tests.integration.test_evaluator_invocation import assembled_invoker, _track_choice_and_s2a_calls


class CorrelationResetDuringHistory(Writer):
    def __init__(self, reset: bool):
        super().__init__()
        self.reset = reset
        self.claim_adapter = None

    def append_attempt_event(self, *, event):
        self.events.append(event)
        if self.reset and event.stage is AttemptStage.EVALUATION:
            # Public operation-lifetime API invoked by an installed writer.
            # Must not erase a live attempt's authoritative correlation.
            try:
                self.claim_adapter.begin_operation()
            except AttemptReservationRejected:
                pass
        return AttemptEventAcknowledgment(event.event_ref, event.request_ref, 'BACKEND-RECEIPT')


@pytest.mark.parametrize('reset', [False, True])
def test_history_callback_cannot_silence_failure_history_after_F25(reset):
    from tests.integration.test_attempt_authority import Issuer, AtomicStore
    from tests.integration.test_attempt_history import EventIssuer, Writer
    from tests.integration.test_attempt_transaction import Store
    from tests.integration.test_attempt_lineage import FixtureLedger, FixtureTransitions, fixture_policy
    normal, request, _, _ = assembled_invoker()
    writer = CorrelationResetDuringHistory(reset)
    f57 = FixtureTransitions()
    f57.failure = RuntimeError('PRIVATE_F57_FAILURE_AFTER_F25')
    store = AtomicStore()
    transaction = Store()
    owned = assemble_controlled_choice_root(
        handoff=normal._installation.handoff,
        request_issuer=Issuer(),
        f25_store=store,
        ledger=FixtureLedger(),
        transitions=f57,
        transaction_store=transaction,
        approved_f57_policy=fixture_policy(),
        max_identifier_characters=64,
        history_issuer=EventIssuer(),
        history_writer=writer,
    )
    writer.claim_adapter = owned._claim
    with _track_choice_and_s2a_calls() as calls:
        with pytest.raises(AttemptLineageUnavailable) as failure:
            owned.run_choice(request=request)
    assert failure.value.__cause__ is None and failure.value.__context__ is None
    assert calls == {'choice':1, 's2a':1}
    assert store.claims == 1
    assert not transaction.effects
    # physical attempt claim, scoring and legal operation transition were really contacted. Thus the owned request has
    # an established exact request_ref; its FAILURE event must not disappear.
    stages = [e.stage for e in writer.events]
    assert AttemptStage.PRE in stages
    assert AttemptStage.ATTEMPT in stages
    assert AttemptStage.EVALUATION in stages
    assert AttemptStage.VERIFY in stages
    assert AttemptStage.FAILURE in stages
    assert writer.events[-1].request_ref == writer.events[0].request_ref
    assert writer.events[-1].attempt_id == 'BACKEND-ATT-1'
