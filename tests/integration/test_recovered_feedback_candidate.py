"""Causal student-safe feedback candidate consumption from an actual scored, recovered FIRST.

The fixture's issuer facts are synthetic, not real backend authentication or a
permission to publish; physical, scored and governed roots execute unchanged.
"""
from dataclasses import replace
import pytest

from grading.integration.recovered_feedback_candidate import (
    FeedbackCandidateState, ProductionRecoveredFeedbackCandidate, CurrentFeedbackBinding,
)
from grading.integration.student_safe_feedback import (
    ProductionStudentFeedback, FeedbackOriginal, IssuedFeedbackInventory,
    IssuedErrorAssessment, ConfirmedErrorEvidence, FeedbackCategory,
)
from tests.integration.test_recovered_original_governance import setup_scored


class QuestionSource:
    def __init__(self, original):
        self.original = original
        self.calls = 0
        self.on_read = None
    def read_feedback_question(self):
        self.calls += 1
        if self.on_read: self.on_read()
        return (self.original, ('C-1',), ('E-1',))


class SyntheticCurrentBinding:
    """Test-only joined source; does NOT establish real issuer or DB atomicity."""
    def __init__(self, pending, question):
        self.pending, self.question = pending, question
        self.calls = 0
        self.mode = 'OK'
    def read_current_feedback_binding(self):
        self.calls += 1
        if self.mode == 'ABSENT':
            raise TimeoutError('unavailable consistency snapshot')
        operation = self.pending.identity
        original, criteria, evidence = self.question.read_feedback_question()
        if self.mode == 'FOREIGN':
            operation = replace(operation, original_scored_result_ref='OTHER')
        if self.mode == 'INVALID_VERSION':
            generation = ''
        else:
            generation = 'SYNTHETIC-TEST-ONLY-GENERATION'
        return CurrentFeedbackBinding(operation, original, criteria, evidence, generation)


class Inventory:
    def __init__(self):
        self.calls = 0
        self.mode = 'OK'
    def read_feedback_inventory(self, *, original):
        self.calls += 1
        if self.mode == 'FOREIGN':
            original = replace(original, original_scored_result_ref='FOREIGN')
        if self.mode == 'ABSENT':
            raise TimeoutError('no original inventory')
        return IssuedFeedbackInventory(original, ('C-1',), ('E-1',))


class Confirmation:
    def __init__(self):
        self.calls = 0
        self.mode = 'OK'
        self.on_read = None
    def read_confirmed_error(self, *, original):
        self.calls += 1
        if self.on_read: self.on_read()
        if self.mode == 'ABSENT': raise TimeoutError('unknown school error')
        if self.mode == 'FOREIGN':
            original = replace(original, tenant_ref='FOREIGN')
        return IssuedErrorAssessment(original, ConfirmedErrorEvidence(
            FeedbackCategory.INCOMPLETE_SOLUTION, 'C-1', 'E-1', 'SCHOOL-CHECK'))


def rig():
    recovery, qualified, source, originals, views, baseline, physical, store, conditional = setup_scored()
    identity = recovery._target.__self__.identity
    original = FeedbackOriginal(identity.tenant_ref, identity.grading_run_id,
        identity.original_scored_result_ref, identity.source_revision, 'Q1')
    question = QuestionSource(original)
    inventory = Inventory()
    confirmed = Confirmation()
    formatter = ProductionStudentFeedback(source=confirmed,
        inventory_source=inventory, max_identifier_characters=128)
    binding = SyntheticCurrentBinding(recovery._target.__self__, question)
    binding.qualified = qualified
    owner = ProductionRecoveredFeedbackCandidate(recovery=recovery,
        feedback=formatter, question_source=question,
        current_binding_source=binding)
    return owner, recovery, source, originals, views, baseline, physical, store, conditional, question, inventory, confirmed


def test_positive_original_bound_nonpublishing_student_safe_category():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    result = owner.assess()
    assert result.state is FeedbackCandidateState.CANDIDATE
    assert result.feedback.category is FeedbackCategory.INCOMPLETE_SOLUTION
    assert result.feedback.message == 'The admitted evidence confirms an incomplete solution.'
    assert result.feedback.original == question.original
    assert result.operation == recovery._target.__self__.identity
    assert result.binding_revision == 'SYNTHETIC-TEST-ONLY-GENERATION'
    assert (question.calls, inventory.calls, confirmed.calls) == (3, 1, 1)
    assert (physical.claims, store.commits, conditional.contacts) == before
    assert not result.authorizes_publication and not result.authorizes_student_visibility
    assert not result.authorizes_retry and not result.feedback.authorizes_publication


@pytest.mark.parametrize('change', ('tenant_ref', 'grading_run_id',
    'original_scored_result_ref', 'source_revision'))
def test_foreign_original_is_rejected_before_feedback_sources(change):
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    question.original = replace(question.original, **{change: 'FOREIGN'})
    assert owner.assess().state is FeedbackCandidateState.UNKNOWN
    assert inventory.calls == confirmed.calls == 0
    assert (physical.claims, store.commits, conditional.contacts) == before


@pytest.mark.parametrize('mode', ('ABSENT', 'FOREIGN'))
def test_unavailable_or_foreign_academic_inventory_never_classifies(mode):
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    inventory.mode = mode
    result = owner.assess()
    assert result.state is FeedbackCandidateState.CANDIDATE
    assert result.feedback.category is FeedbackCategory.UNKNOWN
    assert confirmed.calls == (0 if mode == 'FOREIGN' else 0)
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_wrong_academic_classifier_issuer_cannot_emit_specific_category():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    confirmed.mode = 'FOREIGN'
    result = owner.assess()
    assert result.state is FeedbackCandidateState.CANDIDATE
    assert result.feedback.category is FeedbackCategory.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_pending_recovery_target_changes_during_feedback_refuses_candidate():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    pending = recovery._target.__self__
    saved = pending.identity
    confirmed.on_read = lambda: setattr(pending, 'identity', replace(saved,
        original_scored_result_ref='REPLACED'))
    blocked = owner.assess()
    assert blocked.state is FeedbackCandidateState.UNKNOWN
    assert blocked.operation is None and blocked.binding_revision is None
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_lost_c5_original_or_adverse_review_never_reads_student_feedback():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    originals[1].value = False
    assert owner.assess().state is FeedbackCandidateState.UNKNOWN
    assert inventory.calls == confirmed.calls == question.calls == 0
    qualified = recovery._c5
    qualified._original.__self__.original = None
    assert owner.assess().state is FeedbackCandidateState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_installation_does_not_accept_feedback_without_independent_inventory():
    recovery, qualified, source, originals, views, before, physical, store, conditional = setup_scored()
    from grading.integration.student_safe_feedback import ProductionStudentFeedback
    with pytest.raises(ValueError):
        ProductionRecoveredFeedbackCandidate(recovery=recovery,
            feedback=ProductionStudentFeedback(source=Confirmation(),
                max_identifier_characters=128),question_source=QuestionSource(FeedbackOriginal(
                    'T','R','S','V','Q')))


def test_academically_issued_foreign_question_cannot_use_same_result_id():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    question.original = replace(question.original, question_id='NOT-IN-SCORED-PAPER')
    result = owner.assess()
    assert result.state is FeedbackCandidateState.UNKNOWN
    assert inventory.calls == confirmed.calls == 0
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_question_selector_drift_during_academic_source_does_not_return_candidate():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    saved = question.original
    confirmed.on_read = lambda: setattr(question, 'original', replace(saved,question_id='Q2'))
    assert owner.assess().state is FeedbackCandidateState.UNKNOWN
    assert question.calls == 2
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_missing_shared_consistency_source_cannot_emit_positive_candidate():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    legacy = ProductionRecoveredFeedbackCandidate(recovery=recovery,
        feedback=owner._feedback, question_source=question)
    assert legacy.assess().state is FeedbackCandidateState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


@pytest.mark.parametrize('mode', ('ABSENT', 'FOREIGN', 'INVALID_VERSION'))
def test_inconsistent_or_missing_authoritative_joint_snapshot_blocks_candidate(mode):
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    owner._binding.__self__.mode = mode
    assert owner.assess().state is FeedbackCandidateState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_last_recovery_callback_mutates_question_after_its_last_local_read():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    pending = recovery._target.__self__
    # The fourth pending-target read occurs during last recovery, after the
    # second direct question read. The joined source must detect the drift.
    previous = recovery._target
    class LateMutation:
        def __init__(self, pending, question):
            self.pending, self.question = pending, question
            self.calls = 0
        def read_fixed_recovery_target(self):
            self.calls += 1
            if self.calls == 4:
                self.question.original = replace(self.question.original, question_id='Q2')
            return self.pending.identity
    from grading.integration.recovered_original_governance import ProductionRecoveredOriginalGovernance
    moved = LateMutation(pending, question)
    alternate_recovery = ProductionRecoveredOriginalGovernance(
        qualified=owner._binding.__self__.qualified, target_source=moved)
    binding = SyntheticCurrentBinding(pending, question)
    candidate = ProductionRecoveredFeedbackCandidate(recovery=alternate_recovery,
        feedback=owner._feedback, question_source=question,
        current_binding_source=binding)
    assert candidate.assess().state is FeedbackCandidateState.UNKNOWN
    assert moved.calls == 4 and binding.calls == 1
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_late_recovery_mutates_criterion_evidence_before_final_joint_read():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    pending = recovery._target.__self__
    class ChangingQuestion(QuestionSource):
        def __init__(self, original):
            super().__init__(original)
            self.criteria = ('C-1',)
            self.evidence = ('E-1',)
        def read_feedback_question(self):
            self.calls += 1
            return self.original, self.criteria, self.evidence
    changing = ChangingQuestion(question.original)
    class LatePending:
        def __init__(self): self.calls = 0
        def read_fixed_recovery_target(self):
            self.calls += 1
            if self.calls == 4:
                changing.criteria = ('C-OTHER',)
                changing.evidence = ('E-OTHER',)
            return pending.identity
    from grading.integration.recovered_original_governance import ProductionRecoveredOriginalGovernance
    late = LatePending()
    alternate_recovery = ProductionRecoveredOriginalGovernance(
        qualified=owner._binding.__self__.qualified, target_source=late)
    binding = SyntheticCurrentBinding(pending, changing)
    candidate = ProductionRecoveredFeedbackCandidate(recovery=alternate_recovery,
        feedback=owner._feedback, question_source=changing,
        current_binding_source=binding)
    assert candidate.assess().state is FeedbackCandidateState.UNKNOWN
    assert late.calls == 4 and binding.calls == 1
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_last_question_reader_changes_pending_original_before_final_joint_read():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    pending = recovery._target.__self__
    saved = pending.identity
    question.on_read = lambda: setattr(pending, 'identity', replace(saved,
        original_scored_result_ref='OTHER')) if question.calls == 2 else None
    assert owner.assess().state is FeedbackCandidateState.UNKNOWN
    assert (physical.claims, store.commits, conditional.contacts) == before


def test_feedback_handoff_preserves_distinct_atomic_generations_without_granting_release():
    owner, recovery, source, originals, views, before, physical, store, conditional, question, inventory, confirmed = rig()
    old = owner._binding.__self__

    class RevisionedBinding(SyntheticCurrentBinding):
        def __init__(self, pending, question):
            super().__init__(pending, question)
            self.revision = 'SYNTHETIC-TEST-ONLY-GENERATION-1'
        def read_current_feedback_binding(self):
            return replace(super().read_current_feedback_binding(),
                           snapshot_revision=self.revision)

    binding = RevisionedBinding(old.pending, question)
    connected = ProductionRecoveredFeedbackCandidate(
        recovery=recovery, feedback=owner._feedback, question_source=question,
        current_binding_source=binding)
    first = connected.assess()
    binding.revision = 'SYNTHETIC-TEST-ONLY-GENERATION-2'
    second = connected.assess()
    assert first.state is second.state is FeedbackCandidateState.CANDIDATE
    assert first.feedback == second.feedback
    assert first.operation == second.operation == recovery._target.__self__.identity
    assert first.binding_revision == 'SYNTHETIC-TEST-ONLY-GENERATION-1'
    assert second.binding_revision == 'SYNTHETIC-TEST-ONLY-GENERATION-2'
    assert not first.authorizes_publication and not second.authorizes_student_visibility
    assert (physical.claims, store.commits, conditional.contacts) == before
