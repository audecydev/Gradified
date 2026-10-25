"""Real installed recovered-FIRST and teacher review/authorized result release/student-safe feedback -> conditional effect owner.

All issuers and effect owners in this file are synthetic contract fixtures. They
cannot authenticate a school, authorize a real student, or prove backend CAS.
"""
from dataclasses import replace

import pytest

from grading.integration.official_result_release import (
    ConditionalReleaseIntent, ConditionalReleaseReceipt, ConditionalReleaseReply,
    ProductionGovernedResultRelease, ReleaseOperationIdentity, ReleasePurpose, ReleaseState,
    ReleaseIntentEstablishmentState, ReleaseIntentEstablishmentReply,
)
from grading.integration.recovered_feedback_candidate import ProductionRecoveredFeedbackCandidate
from grading.integration.student_safe_feedback import (
    FeedbackOriginal, ProductionStudentFeedback,
)
from tests.integration.test_recovered_teacher_review_candidate import rig as teacher_rig
from tests.integration.test_recovered_feedback_candidate import (
    Confirmation, Inventory, QuestionSource, SyntheticCurrentBinding,
)


class AtomicReleaseFixture:
    """Simulates a qualified effect owner, not real school/backend compliance."""
    def __init__(self):
        self.calls = []
        self.mode = 'RELEASED'
        self.on_commit = None
        self.intent_ledger = {}  # synthetic transactionally unique write-ahead store
        self.establish_calls = []
        self.custody_mode = 'NORMAL'
        from threading import Lock
        self.intent_lock = Lock()

    def establish_original_intent(self, *, request):
        # This deliberately simulates the contract. Real durable transactions,
        # crash recovery and issuance/authentication require backend conformance.
        self.establish_calls.append(request)
        if self.custody_mode == 'TIMEOUT_BEFORE':
            raise TimeoutError('no authoritative establishment ACK')
        if self.custody_mode == 'MALFORMED':
            return ReleaseIntentEstablishmentReply('ESTABLISHED', request)
        if self.custody_mode == 'FOREIGN':
            return ReleaseIntentEstablishmentReply(ReleaseIntentEstablishmentState.ESTABLISHED,
                replace(request, policy_revision='FOREIGN'))
        with self.intent_lock:
            prior = self.intent_ledger.get(request.release_identity)
            if prior is not None:
                return ReleaseIntentEstablishmentReply(
                    ReleaseIntentEstablishmentState.ALREADY_ESTABLISHED if prior == request
                    else ReleaseIntentEstablishmentState.CONFLICT, prior)
            self.intent_ledger[request.release_identity] = request
        if self.custody_mode == 'TIMEOUT_AFTER':
            raise TimeoutError('durably established then ACK lost')
        if self.custody_mode == 'UNKNOWN_AFTER':
            return ReleaseIntentEstablishmentReply(ReleaseIntentEstablishmentState.UNKNOWN, request)
        return ReleaseIntentEstablishmentReply(ReleaseIntentEstablishmentState.ESTABLISHED, request)

    def commit_if_current(self, *, request):
        self.calls.append(request)
        if self.on_commit is not None:
            self.on_commit(request)
        if self.mode == 'DENIED':
            return ConditionalReleaseReply(request, ReleaseState.DENIED)
        if self.mode == 'UNKNOWN':
            return ConditionalReleaseReply(request, ReleaseState.UNKNOWN)
        if self.mode == 'LOST_ACK':
            raise TimeoutError('after one possible durable write')
        if self.mode == 'FOREIGN_ACK':
            return ConditionalReleaseReply(replace(request, policy_revision='FOREIGN'), ReleaseState.RELEASED)
        if self.mode == 'EMPTY_GENERATION':
            return ConditionalReleaseReply(request, ReleaseState.RELEASED,
                ConditionalReleaseReceipt(request, 'rel-E1','auth-E1','issuer-E1',''))
        if self.mode == 'FOREIGN_RECEIPT_INTENT':
            return ConditionalReleaseReply(request, ReleaseState.RELEASED,
                ConditionalReleaseReceipt(replace(request, decision_ref='FOREIGN'),
                    'rel-E1','auth-E1','issuer-E1','gen-E1'))
        if self.mode == 'INVALID_STATE':
            return ConditionalReleaseReply(request, 'RELEASED')
        if self.mode == 'POSITIVE_RECEIPT_ON_DENIED':
            return ConditionalReleaseReply(request, ReleaseState.DENIED,
                ConditionalReleaseReceipt(request,'rel-E1','auth-E1','issuer-E1','gen-E1'))
        if self.mode == 'POSITIVE_RECEIPT_ON_UNKNOWN':
            return ConditionalReleaseReply(request, ReleaseState.UNKNOWN,
                ConditionalReleaseReceipt(request,'rel-E1','auth-E1','issuer-E1','gen-E1'))
        if self.mode == 'BAD_RECEIPT':
            return ConditionalReleaseReply(request, ReleaseState.RELEASED,
                ConditionalReleaseReceipt(request, '', 'auth', 'issuer', 'generation'))
        return ConditionalReleaseReply(request, ReleaseState.RELEASED,
            ConditionalReleaseReceipt(request, 'rel-E1', 'auth-E1', 'issuer-E1', 'gen-E1'))


def rig():
    teacher, recovery, original_source, review_source, journal, before, physical, store, conditional = teacher_rig()
    identity = recovery._target.__self__.identity
    question = QuestionSource(FeedbackOriginal(
        identity.tenant_ref, identity.grading_run_id,
        identity.original_scored_result_ref, identity.source_revision, 'Q1'))
    inventory, confirmation = Inventory(), Confirmation()
    formatter = ProductionStudentFeedback(source=confirmation, inventory_source=inventory,
                                          max_identifier_characters=128)
    binding = SyntheticCurrentBinding(recovery._target.__self__, question)
    feedback = ProductionRecoveredFeedbackCandidate(
        recovery=recovery, feedback=formatter, question_source=question,
        current_binding_source=binding)
    backend = AtomicReleaseFixture()
    owner = ProductionGovernedResultRelease(recovery=recovery, teacher_review=teacher,
        feedback_candidate=feedback, effect_owner=backend, intent_custody=backend, max_identifier_characters=128)
    return (owner, backend, recovery, teacher, feedback, original_source, review_source,
            journal, before, physical, store, conditional, question, inventory, confirmation)


def no_new_scoring(r):
    return r[9].claims, r[10].commits, r[11].contacts


@pytest.mark.parametrize('purpose', [ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK])
def test_authorized_synthetic_effect_contacts_once_and_retains_provenance(purpose):
    r=rig(); owner, backend=r[:2]; before=no_new_scoring(r)
    out=owner.transition(purpose=purpose)
    assert out.state is ReleaseState.RELEASED
    assert len(backend.calls) == 1 and backend.calls[0] == out.intent
    assert out.receipt.intent == out.intent
    assert out.original == r[2]._target.__self__.identity
    assert len(out.intent.readiness_views) == 3
    assert out.intent.decision_ref and out.intent.journal_event_ref
    if purpose is ReleasePurpose.STUDENT_FEEDBACK:
        assert out.intent.feedback is not None
        assert out.intent.feedback_binding_revision == 'SYNTHETIC-TEST-ONLY-GENERATION'
    else:
        assert out.intent.feedback is None and out.intent.feedback_binding_revision is None
    assert not out.authorizes_publication and not out.authorizes_retry
    assert no_new_scoring(r) == before


@pytest.mark.parametrize('mode,state', [('DENIED',ReleaseState.DENIED),('UNKNOWN',ReleaseState.UNKNOWN),
    ('LOST_ACK',ReleaseState.UNKNOWN),('FOREIGN_ACK',ReleaseState.UNKNOWN),
    ('BAD_RECEIPT',ReleaseState.UNKNOWN)])
def test_backend_negative_or_uncertain_result_never_retries(mode,state):
    r=rig();owner,backend=r[:2];before=no_new_scoring(r)
    backend.mode=mode
    out=owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert out.state is state and out.receipt is None
    assert out.intent is not None and out.original is not None
    assert len(backend.calls)==1 and no_new_scoring(r)==before


def test_missing_g3_teacher_journal_blocks_before_release_contact():
    r=rig();owner,backend,journal=r[0],r[1],r[7];before=no_new_scoring(r)
    from grading.integration.teacher_review_journal import TeacherReviewRecoveryState
    journal.state=TeacherReviewRecoveryState.UNKNOWN
    out=owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert out.state is ReleaseState.UNKNOWN and not backend.calls
    assert no_new_scoring(r)==before


def test_missing_feedback_binding_blocks_feedback_but_official_path_remains_supported():
    r=rig();owner,backend=r[:2];before=no_new_scoring(r)
    owner._feedback._binding.__self__.mode='ABSENT'
    assert owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK).state is ReleaseState.UNKNOWN
    assert backend.calls == []
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.RELEASED
    assert len(backend.calls)==1 and no_new_scoring(r)==before


def test_missing_confirmation_cannot_disclose_unconfirmed_specific_error():
    r=rig(); owner,backend=r[:2];before=no_new_scoring(r)
    r[13].mode='ABSENT'
    out=owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert out.state is ReleaseState.UNKNOWN and not backend.calls
    assert no_new_scoring(r)==before


def test_foreign_recovered_operation_blocks_release_without_effect():
    r=rig();owner,backend,recovery=r[:3];before=no_new_scoring(r)
    pending = recovery._target.__self__
    pending.identity = replace(pending.identity, original_scored_result_ref='FOREIGN')
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert backend.calls == [] and no_new_scoring(r)==before


def test_changed_selected_question_blocks_before_disclosure_effect():
    r=rig();owner,backend=r[:2];before=no_new_scoring(r)
    q=r[12];q.original=replace(q.original, question_id='Q-FOREIGN')
    assert owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK).state is ReleaseState.UNKNOWN
    assert backend.calls == [] and no_new_scoring(r)==before


def test_effect_owner_cannot_turn_mutated_request_into_success():
    r=rig();owner,backend=r[:2];before=no_new_scoring(r)
    def change(req):
        object.__setattr__(req, 'policy_revision', 'TAMPERED')
    backend.on_commit=change
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert len(backend.calls)==1 and no_new_scoring(r)==before


def test_cannot_install_unrelated_g3_recovery():
    r1=rig();r2=rig()
    with pytest.raises(ValueError):
        ProductionGovernedResultRelease(recovery=r1[2], teacher_review=r2[3],
            feedback_candidate=r1[4], effect_owner=r1[1], intent_custody=r1[1], max_identifier_characters=128)


def test_invalid_purpose_refused_without_any_effect():
    r=rig();owner,backend=r[:2]
    with pytest.raises(ValueError):
        owner.transition(purpose='STUDENT_FEEDBACK')
    assert backend.calls==[]


def test_review_required_academic_fact_cannot_contact_conditional_release():
    r=rig();owner,backend=r[:2];before=no_new_scoring(r)
    # Independent original academic reader withdraws its affirmative fact.
    governed = r[2]._handoff._original
    academic = governed._readers[1].__self__
    academic.value = False
    out=owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert out.state is ReleaseState.UNKNOWN and backend.calls == []
    assert no_new_scoring(r)==before


def test_teacher_original_replaced_with_different_committed_original_blocks_effect():
    r=rig();owner,backend=r[:2];before=no_new_scoring(r)
    original_reader=r[5]
    original_reader.value=replace(original_reader.value,
        original_cas=replace(original_reader.value.original_cas,commit_ref='DIFFERENT'))
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert backend.calls == [] and no_new_scoring(r)==before


def test_missing_feedback_module_cannot_issue_feedback_release():
    r=rig();backend=r[1]
    owner=ProductionGovernedResultRelease(recovery=r[2],teacher_review=r[3],
        effect_owner=backend,intent_custody=backend,max_identifier_characters=128)
    assert owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK).state is ReleaseState.UNKNOWN
    assert backend.calls == []
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.RELEASED


def test_release_owner_uncertain_on_reentrant_request_no_duplicate_effect():
    r=rig();owner,backend=r[:2]
    observed=[]
    def call_once(_):
        observed.append(owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT))
    backend.on_commit=call_once
    final=owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert final.state is ReleaseState.RELEASED
    assert observed[0].state is ReleaseState.UNKNOWN
    assert len(backend.calls)==1


@pytest.mark.parametrize('mode', [
    'EMPTY_GENERATION','FOREIGN_RECEIPT_INTENT','INVALID_STATE',
    'POSITIVE_RECEIPT_ON_DENIED','POSITIVE_RECEIPT_ON_UNKNOWN',
    'FOREIGN_ACK','BAD_RECEIPT'])
def test_malformed_or_conflicting_release_receipts_rejected_from_executed_adapter(mode):
    # Configure the actual installed backend before the contact; a method
    # replaced AFTER _capture is not the method the owner will execute.
    r=rig();owner,backend=r[:2]
    backend.mode = mode
    before = no_new_scoring(r)
    out=owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert out.state is ReleaseState.UNKNOWN and out.receipt is None
    assert out.intent is not None and out.original is not None
    assert len(backend.calls) == 1 and no_new_scoring(r) == before
    backend.mode = 'RELEASED'
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert len(backend.calls) == 1



@pytest.mark.parametrize('mode', ['LOST_ACK', 'UNKNOWN', 'FOREIGN_ACK', 'BAD_RECEIPT', 'DENIED'])
def test_effect_contact_may_not_be_reissued_after_first_contact(mode):
    r = rig()
    owner, backend = r[:2]
    before = no_new_scoring(r)
    backend.mode = mode
    first = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert first.intent is not None and len(backend.calls) == 1
    backend.mode = 'RELEASED'
    second = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert second.state is ReleaseState.UNKNOWN
    assert second.original == first.original and second.intent == first.intent
    assert second.receipt is None and len(backend.calls) == 1
    assert no_new_scoring(r) == before


def test_successful_release_observation_not_reissued_as_second_effect():
    r = rig()
    owner, backend = r[:2]
    first = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert first.state is ReleaseState.RELEASED
    second = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert second.state is ReleaseState.UNKNOWN
    assert second.original == first.original and second.intent == first.intent
    assert len(backend.calls) == 1


def test_distinct_release_purposes_have_independent_once_only_fences():
    r = rig()
    owner, backend = r[:2]
    official = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    feedback = owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert official.state is ReleaseState.RELEASED
    assert feedback.state is ReleaseState.RELEASED
    assert len(backend.calls) == 2
    assert {x.purpose for x in backend.calls} == {
        ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK}
    assert owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK).state is ReleaseState.UNKNOWN
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert len(backend.calls) == 2


def test_pre_effect_source_unavailability_does_not_consume_release_fence():
    r = rig()
    owner, backend, journal = r[0], r[1], r[7]
    from grading.integration.teacher_review_journal import TeacherReviewRecoveryState
    journal.state = TeacherReviewRecoveryState.UNKNOWN
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert backend.calls == []
    journal.state = TeacherReviewRecoveryState.COMMITTED
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.RELEASED
    assert len(backend.calls) == 1


class AuthenticatedSyntheticHistory:
    """Read-only fixture from a simulated effect ledger, NOT real durability."""
    def __init__(self, backend):
        self.backend = backend
        self.requests = []
        self.mode = 'RELEASED'
    def read_release_outcome(self, *, request):
        self.requests.append(request)
        # A prepared-only intent does not establish any released effect.
        # A history adapter must never infer release from write-ahead custody.
        if request not in self.backend.calls:
            return ConditionalReleaseReply(request, ReleaseState.UNKNOWN)
        if self.mode == 'TIMEOUT':
            raise TimeoutError('read-only history temporarily unavailable')
        if self.mode == 'FOREIGN':
            return ConditionalReleaseReply(replace(request, decision_ref='FOREIGN'),
                                           ReleaseState.RELEASED)
        if self.mode == 'UNKNOWN':
            return ConditionalReleaseReply(request, ReleaseState.UNKNOWN)
        if self.mode == 'DENIED':
            return ConditionalReleaseReply(request, ReleaseState.DENIED)
        return ConditionalReleaseReply(request, ReleaseState.RELEASED,
            ConditionalReleaseReceipt(request, 'rel-history', 'auth-history',
                                      'issuer-history', 'gen-history'))


def history_rig():
    r = rig()
    history = AuthenticatedSyntheticHistory(r[1])
    owner = ProductionGovernedResultRelease(
        recovery=r[2], teacher_review=r[3], feedback_candidate=r[4],
        effect_owner=r[1], intent_custody=r[1], release_history=history,
        max_identifier_characters=128)
    return r, owner, history


def test_lost_ack_can_be_recovered_by_read_only_same_intent_without_resend():
    r, owner, history = history_rig()
    backend = r[1]
    backend.mode = 'LOST_ACK'
    original = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert original.state is ReleaseState.UNKNOWN and original.intent is not None
    restored = owner.reconcile(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert restored.state is ReleaseState.RELEASED
    assert restored.intent == original.intent and restored.original == original.original
    assert restored.receipt is not None and restored.receipt.intent == original.intent
    assert len(history.requests) == 1 and len(backend.calls) == 1
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert len(backend.calls) == 1


@pytest.mark.parametrize('mode', ['TIMEOUT', 'FOREIGN', 'UNKNOWN'])
def test_read_only_history_does_not_promote_uncertain_or_foreign_effect(mode):
    r, owner, history = history_rig()
    r[1].mode = 'LOST_ACK'
    original = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    history.mode = mode
    restored = owner.reconcile(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert restored.state is ReleaseState.UNKNOWN and restored.intent == original.intent
    assert len(history.requests) == 1 and len(r[1].calls) == 1


def test_history_never_queries_for_original_that_has_not_contacted_effect_owner():
    r, owner, history = history_rig()
    assert owner.reconcile(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert history.requests == [] and r[1].calls == []
    from grading.integration.teacher_review_journal import TeacherReviewRecoveryState
    r[7].state = TeacherReviewRecoveryState.UNKNOWN
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert owner.reconcile(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert history.requests == [] and r[1].calls == []


def test_two_purpose_history_is_read_only_and_exact_purpose_bound():
    r, owner, history = history_rig()
    r[1].mode = 'LOST_ACK'
    official = owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    feedback = owner.transition(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert official.state is feedback.state is ReleaseState.UNKNOWN
    assert official.intent.purpose is ReleasePurpose.OFFICIAL_RESULT
    assert feedback.intent.purpose is ReleasePurpose.STUDENT_FEEDBACK
    a = owner.reconcile(purpose=ReleasePurpose.OFFICIAL_RESULT)
    b = owner.reconcile(purpose=ReleasePurpose.STUDENT_FEEDBACK)
    assert a.state is b.state is ReleaseState.RELEASED
    assert len(r[1].calls) == 2 and len(history.requests) == 2
    assert a.intent.purpose is ReleasePurpose.OFFICIAL_RESULT
    assert b.intent.purpose is ReleasePurpose.STUDENT_FEEDBACK


class DurableSyntheticOriginalSelection:
    """Read-only test fixture sharing a simulated append-only release journal."""
    def __init__(self, backend):
        self.backend = backend
        self.requests = []
        self.mode = 'NORMAL'
    def read_fixed_intent(self, *, release):
        self.requests.append(release)
        if self.mode == 'TIMEOUT':
            raise TimeoutError('synthetic ledger down')
        sent = self.backend.intent_ledger.get(release)
        if sent is None:
            return None
        if self.mode == 'FOREIGN':
            return replace(sent, operation=replace(sent.operation,
                original_scored_result_ref='FOREIGN'))
        if self.mode == 'WRONG_PURPOSE':
            return replace(sent, purpose=ReleasePurpose.STUDENT_FEEDBACK)
        return sent


def original_source_rig():
    r=rig()
    source=DurableSyntheticOriginalSelection(r[1])
    history=AuthenticatedSyntheticHistory(r[1])
    def make_owner():
        return ProductionGovernedResultRelease(
            recovery=r[2], teacher_review=r[3], feedback_candidate=r[4],
            effect_owner=r[1], intent_custody=r[1], release_history=history,
            original_intent_source=source, max_identifier_characters=128)
    return r,source,history,make_owner


@pytest.mark.parametrize('mode', ['LOST_ACK', 'RELEASED', 'DENIED'])
def test_separate_owner_cannot_recontact_previously_persisted_release(mode):
    r,source,history,make_owner=original_source_rig()
    first_owner=make_owner()
    r[1].mode=mode
    prior=first_owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert len(r[1].calls)==1 and prior.intent is not None
    second_owner=make_owner()  # simulates a separate worker with no local fence
    r[1].mode='RELEASED'
    second=second_owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert second.state is ReleaseState.UNKNOWN and second.receipt is None
    assert second.intent == prior.intent and len(r[1].calls)==1
    assert source.requests and source.requests[-1]==prior.intent.release_identity


def test_new_owner_read_only_reconciles_lost_ack_from_independent_original_ledger():
    r,source,history,make_owner=original_source_rig()
    r[1].mode='LOST_ACK'
    old=make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    assert old.state is ReleaseState.UNKNOWN and old.intent is not None
    restarted=make_owner()
    key=ReleaseOperationIdentity(old.original,ReleasePurpose.OFFICIAL_RESULT)
    assert key==old.intent.release_identity
    before=no_new_scoring(r)
    recovered=restarted.reconcile_original(release=key)
    assert recovered.state is ReleaseState.RELEASED
    assert recovered.original==old.original and recovered.intent==old.intent
    assert recovered.receipt.intent==old.intent
    assert len(r[1].calls)==1 and no_new_scoring(r)==before
    assert len(history.requests)==1 and len(source.requests)==2


@pytest.mark.parametrize('mode', ['TIMEOUT','FOREIGN','WRONG_PURPOSE'])
def test_restarted_reconciliation_rejects_missing_or_foreign_original_intent(mode):
    r,source,history,make_owner=original_source_rig()
    old=make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    source.mode=mode
    restored=make_owner().reconcile_original(release=old.intent.release_identity)
    assert restored.state is ReleaseState.UNKNOWN and restored.receipt is None
    assert len(r[1].calls)==1 and len(history.requests)==0


@pytest.mark.parametrize('mode', ['TIMEOUT','FOREIGN','UNKNOWN','DENIED'])
def test_restarted_reconciliation_keeps_history_truth_without_writer(mode):
    r,source,history,make_owner=original_source_rig()
    old=make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    history.mode=mode
    restarted=make_owner()
    observed=restarted.reconcile_original(release=old.intent.release_identity)
    expected=ReleaseState.DENIED if mode=='DENIED' else ReleaseState.UNKNOWN
    assert observed.state is expected and observed.receipt is None
    assert len(history.requests)==1 and len(r[1].calls)==1


def test_cold_original_lookup_without_stored_attempt_never_infers_noncommit():
    r,source,history,make_owner=original_source_rig()
    owner=make_owner()
    key=ReleaseOperationIdentity(r[2]._target.__self__.identity,
                                 ReleasePurpose.OFFICIAL_RESULT)
    assert owner.reconcile_original(release=key).state is ReleaseState.UNKNOWN
    assert history.requests==[] and r[1].calls==[]


def test_source_unavailable_before_first_contact_does_not_make_a_release_effect():
    r,source,history,make_owner=original_source_rig()
    owner=make_owner()
    source.mode='TIMEOUT'
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.UNKNOWN
    assert r[1].calls==[]
    source.mode='NORMAL'
    assert owner.transition(purpose=ReleasePurpose.OFFICIAL_RESULT).state is ReleaseState.RELEASED
    assert len(r[1].calls)==1


def test_restarted_reconcile_cannot_accept_invalid_key_or_cross_purpose_history():
    r,source,history,make_owner=original_source_rig()
    old=make_owner().transition(purpose=ReleasePurpose.OFFICIAL_RESULT)
    owner=make_owner()
    with pytest.raises(ValueError):
        owner.reconcile_original(release='UNTRUSTED')
    wrong=ReleaseOperationIdentity(old.original,ReleasePurpose.STUDENT_FEEDBACK)
    assert owner.reconcile_original(release=wrong).state is ReleaseState.UNKNOWN
    assert history.requests==[] and len(r[1].calls)==1
