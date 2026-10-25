"""Connected official paper readiness -> family legal operation transition/physical attempt claim -> deterministic scoring/frozen scoring.

These synthetic installed school ports prove engine-owned contracts and effect
ordering; they do not authenticate a real school, teacher or OCR backend.
"""
from dataclasses import replace
import pytest

from grading.integration.authorized_preparation import AuthenticatedActor
from grading.integration.paper_readiness_admission import (
    ApprovedPaperSelection, AuthorizedPaperQuestion, QuestionAnswerReadiness,
    PaperReadinessRecord, PaperRevisionConfirmation, ProductionPaperAdmissionComposer,
    PaperAnswerNotReady, PaperAdmissionDenied,
)
from tests.integration.test_whole_paper_family_execution import rig


class SchoolPaperPorts:
    def __init__(self, plan):
        self.events = []
        request = plan.request
        self.actor = AuthenticatedActor(plan.actor_ref, request.tenant_ref, request.session_ref)
        self.selection = ApprovedPaperSelection(
            request, plan.actor_ref, plan.approval_ref, plan.approval_revision,
            plan.selection_decision_ref, plan.selection_revision, plan.source_revision,
            tuple(q.request.question_id for q in plan.questions),
            tuple(q.request.question_id for q in plan.questions),
            tuple(AuthorizedPaperQuestion(q.request.question_id, q.family,
                q.source_artifact_ref, q.evidence_scope_ref) for q in plan.questions))
        self.readiness = PaperReadinessRecord(
            request, plan.approval_ref, plan.approval_revision,
            plan.selection_revision, plan.source_revision, plan.readiness_revision,
            tuple(QuestionAnswerReadiness(q.request.question_id, 'READY',
                q.source_artifact_ref, q.source_revision, q.evidence_scope_ref,
                q.answer_region_ref, q.provenance_ref) for q in plan.questions))
        self.confirmation = PaperRevisionConfirmation(
            request, plan.approval_ref, plan.approval_revision,
            plan.selection_revision, plan.source_revision, plan.readiness_revision, 'CURRENT')

    def current_actor(self):
        self.events.append('identity')
        return self.actor

    def authorize_paper(self, *, actor, request):
        self.events.append('selection')
        return self.selection

    def resolve_paper_readiness(self, *, approval):
        self.events.append('readiness')
        return self.readiness

    def confirm_paper_revision(self, *, approval, readiness):
        self.events.append('revision')
        return self.confirmation


def installation(plan):
    ports = SchoolPaperPorts(plan)
    composer = ProductionPaperAdmissionComposer(
        identity=ports, selections=ports, answers=ports, revisions=ports,
        max_identifier_characters=128, max_questions=10)
    return ports, composer


def test_admitted_official_paper_enters_real_family_first_after_all_readiness_checks():
    executor, plan, permission, physical, backend, conditional, provider, _ = rig()
    ports, composer = installation(plan)
    admitted = composer.admit(request=plan.request)
    assert admitted == plan  # preserve the authentic source relation, not just ID shape
    assert ports.events == ['identity', 'selection', 'readiness', 'revision']
    out = executor.execute_first(plan=admitted, permission=permission)
    assert out.state == 'COMPLETE'
    assert physical.claims == 1 and len(provider.requests) == 1
    assert out.result is not None and out.result.paper_score is not None
    assert out.authorizes_publication is False


@pytest.mark.parametrize('status', ('UNKNOWN', 'UNREADABLE', 'UNMAPPED', 'ABSENT_CONFIRMED'))
def test_not_ready_official_answer_cannot_reach_family_physical_effect(status):
    executor, plan, permission, physical, backend, conditional, provider, _ = rig()
    ports, composer = installation(plan)
    ports.readiness = replace(ports.readiness, answers=(
        replace(ports.readiness.answers[0], status=status),))
    with pytest.raises(PaperAnswerNotReady):
        composer.admit(request=plan.request)
    assert ports.events == ['identity', 'selection', 'readiness']
    assert physical.claims == 0 and provider.requests == []


def test_stale_school_source_revision_blocks_before_f57_and_f25():
    executor, plan, permission, physical, backend, conditional, provider, _ = rig()
    ports, composer = installation(plan)
    ports.confirmation = replace(ports.confirmation, source_revision='REPLACED-SCHOOL-SOURCE')
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=plan.request)
    assert physical.claims == 0 and provider.requests == []


def test_changed_approved_rubric_version_after_readiness_cannot_be_scored():
    """governed result checks output is not a silent in-place modification of ACTIVE scoring authority."""
    executor, plan, permission, physical, backend, conditional, provider, source = rig()
    ports, composer = installation(plan)
    admitted = composer.admit(request=plan.request)
    paper = source.inputs.paper_authority
    expected = paper.expected_questions[0]
    replacement = replace(expected, rubric_ref=replace(expected.rubric_ref,
                                                        version=expected.rubric_ref.version + 1))
    source.inputs = replace(source.inputs, paper_authority=replace(
        paper, expected_questions=(replacement,)))
    out = executor.execute_first(plan=admitted, permission=permission)
    assert out.state != 'COMPLETE' and out.result is None
    assert physical.claims == 0 and provider.requests == []
