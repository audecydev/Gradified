"""paper readiness paper authority/readiness admission, side-effect ordering and custody."""
from dataclasses import replace

import pytest

from grading.contracts.paper_aggregation import GradingSpecRef
from grading.integration.authorized_preparation import AuthenticatedActor
from grading.integration.paper_readiness_admission import (
    PaperAdmissionRequest, AuthorizedPaperQuestion, ApprovedPaperSelection,
    QuestionAnswerReadiness, PaperReadinessRecord, PaperRevisionConfirmation,
    ProductionPaperAdmissionComposer, PaperAdmissionDenied, PaperAdmissionUnavailable,
    PaperAdmissionContractError, PaperAnswerNotReady,
)


def make_fixture():
    request = PaperAdmissionRequest(
        tenant_ref="TENANT", session_ref="SESSION", grading_run_id="RUN",
        submission_ref="SUBMISSION", exam_ref="EXAM", paper_ref="PAPER",
        set_ref="SET-1", grading_spec_ref=GradingSpecRef("SPEC", 2),
    )
    ports = Ports(request)
    composer = ProductionPaperAdmissionComposer(
        identity=ports, selections=ports, answers=ports, revisions=ports,
        max_identifier_characters=64, max_questions=5,
    )
    return request, ports, composer


class Ports:
    def __init__(self, request):
        self.events = []
        self.actor = AuthenticatedActor("ACTOR", request.tenant_ref, request.session_ref)
        self.approved = ApprovedPaperSelection(
            request=request, actor_ref="ACTOR", approval_ref="SCHOOL-APPROVAL",
            approval_revision="APP-REV-1", selection_decision_ref="SELECTION-DECISION",
            selection_revision="SEL-REV-1", source_revision="SOURCE-REV-1",
            approved_question_ids=("Q1", "Q2", "Q3"),
            required_question_ids=("Q1",),
            selected_questions=(AuthorizedPaperQuestion("Q1", "CHOICE", "ART-1", "SCOPE-1"),
                                AuthorizedPaperQuestion("Q2", "DIRECT", "ART-1", "SCOPE-2")),
        )
        self.readiness = PaperReadinessRecord(
            request=request, approval_ref="SCHOOL-APPROVAL", approval_revision="APP-REV-1",
            selection_revision="SEL-REV-1", source_revision="SOURCE-REV-1",
            readiness_revision="READY-REV-1",
            answers=(
                QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-1", "OCR-1"),
                QuestionAnswerReadiness("Q2", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-2", "REGION-2", "OCR-2"),
            ),
        )
        self.confirm = PaperRevisionConfirmation(
            request=request, approval_ref="SCHOOL-APPROVAL", approval_revision="APP-REV-1",
            selection_revision="SEL-REV-1", source_revision="SOURCE-REV-1",
            readiness_revision="READY-REV-1", state="CURRENT",
        )
        self.approve_action = None
        self.mutate_callback_actor = False
        self.mutate_callback_request = False
        self.mutate_callback_approval = False
        self.mutate_callback_confirmation_readiness = False
        self.readiness_action = None
        self.confirm_action = None

    def current_actor(self):
        self.events.append("identity")
        return self.actor

    def authorize_paper(self, *, actor, request):
        self.events.append("approval")
        if self.mutate_callback_actor:
            object.__setattr__(actor, "actor_ref", "IMPERSONATED")
        if self.mutate_callback_request:
            object.__setattr__(request, "paper_ref", "OTHER-PAPER")
        if self.approve_action:
            self.approve_action()
        return self.approved

    def resolve_paper_readiness(self, *, approval):
        self.events.append("readiness")
        if self.mutate_callback_approval:
            object.__setattr__(approval, "source_revision", "CHANGED")
        if self.readiness_action:
            self.readiness_action()
        return self.readiness

    def confirm_paper_revision(self, *, approval, readiness):
        self.events.append("confirm")
        if self.mutate_callback_confirmation_readiness:
            object.__setattr__(readiness.answers[0], "answer_region_ref", "OTHER")
        if self.confirm_action:
            self.confirm_action()
        return self.confirm


def test_valid_multiquestion_plan_is_detached_nonpublishing_and_never_executes():
    request, ports, composer = make_fixture()
    plan = composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness", "confirm"]
    assert [q.request.question_id for q in plan.questions] == ["Q1", "Q2"]
    assert [q.family for q in plan.questions] == ["CHOICE", "DIRECT"]
    assert plan.request.paper_ref == "PAPER" and plan.request.set_ref == "SET-1"
    assert plan.questions[0].source_revision == "SOURCE-REV-1"
    assert not hasattr(plan, "score") and not hasattr(plan, "publish")
    assert not hasattr(plan, "execution_authorized")
    assert plan.questions is not ports.readiness.answers
    assert plan.questions[0].request.grading_spec_ref is not request.grading_spec_ref
    object.__setattr__(ports.approved, "approval_revision", "CHANGED")
    object.__setattr__(ports.readiness.answers[0], "answer_region_ref", "CHANGED")
    assert plan.approval_revision == "APP-REV-1"
    assert plan.questions[0].answer_region_ref == "REGION-1"


def test_valid_one_question_scope_and_missing_optional_are_not_inferred_as_error():
    request, ports, composer = make_fixture()
    ports.approved = replace(ports.approved, selected_questions=(AuthorizedPaperQuestion("Q1", "CHOICE", "ART-1", "SCOPE-1"),))
    ports.readiness = replace(ports.readiness, answers=ports.readiness.answers[:1])
    plan = composer.admit(request=request)
    assert len(plan.questions) == 1 and plan.questions[0].family == "CHOICE"


@pytest.mark.parametrize("mutation", ["paper_ref", "tenant_ref", "spec_version"])
def test_identity_callback_cannot_mutate_original_request_before_school_lookup(mutation):
    request, ports, _ = make_fixture()
    original_identity = ports.current_actor

    def mutating_identity():
        actor = original_identity()
        if mutation == "spec_version":
            object.__setattr__(request.grading_spec_ref, "version", 99)
        else:
            object.__setattr__(request, mutation, "CHANGED")
        return actor

    ports.current_actor = mutating_identity
    composer = ProductionPaperAdmissionComposer(
        identity=ports, selections=ports, answers=ports, revisions=ports,
        max_identifier_characters=64, max_questions=5,
    )
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity"]  # No school, readiness or revision contact.


def test_normal_identity_callback_still_admits_selected_questions():
    request, ports, composer = make_fixture()
    plan = composer.admit(request=request)
    assert tuple(q.request.question_id for q in plan.questions) == ("Q1", "Q2")
    assert ports.events == ["identity", "approval", "readiness", "confirm"]


@pytest.mark.parametrize("field", ["tenant_ref", "session_ref"])
def test_foreign_authenticated_scope_rejected_before_paper_lookup(field):
    request, ports, composer = make_fixture()
    ports.actor = replace(ports.actor, **{field: "FOREIGN"})
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity"]


@pytest.mark.parametrize("field", [
    "tenant_ref", "session_ref", "grading_run_id", "submission_ref", "exam_ref",
    "paper_ref", "set_ref", "grading_spec_ref",
])
def test_foreign_approved_paper_scope_rejected_before_readiness(field):
    request, ports, composer = make_fixture()
    value = GradingSpecRef("WRONG", 2) if field == "grading_spec_ref" else "WRONG"
    ports.approved = replace(ports.approved, request=replace(request, **{field: value}))
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval"]


@pytest.mark.parametrize("field", ["actor_ref", "approval_ref", "approval_revision", "selection_revision", "source_revision"])
def test_bad_approval_or_readiness_identity_does_not_confirm(field):
    request, ports, composer = make_fixture()
    if field == "actor_ref":
        ports.approved = replace(ports.approved, actor_ref="FOREIGN")
        expected_events = ["identity", "approval"]
    else:
        ports.readiness = replace(ports.readiness, **{field: "FOREIGN"})
        expected_events = ["identity", "approval", "readiness"]
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == expected_events


@pytest.mark.parametrize("change", [
    {"approved_question_ids": ("Q1", "Q1")},
    {"required_question_ids": ("Q1", "Q3")},
    {"selected_questions": (AuthorizedPaperQuestion("Q1", "CHOICE", "ART-1", "SCOPE-1"), AuthorizedPaperQuestion("Q1", "DIRECT", "ART-1", "SCOPE-1"))},
    {"selected_questions": (AuthorizedPaperQuestion("Q1", "CHOICE", "ART-1", "SCOPE-1"), AuthorizedPaperQuestion("OTHER", "NUMERIC", "ART-1", "SCOPE-X"))},
    {"selected_questions": ()},
    {"selection_decision_ref": ""},
    {"approval_revision": " "},
    {"selected_questions": (AuthorizedPaperQuestion("Q1", "UNAPPROVED", "ART-1", "SCOPE-1"),)},
])
def test_invalid_selection_prevents_readiness_lookup(change):
    request, ports, composer = make_fixture()
    ports.approved = replace(ports.approved, **change)
    with pytest.raises((PaperAdmissionDenied, PaperAdmissionContractError)):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval"]


@pytest.mark.parametrize("answers", [
    (),
    (QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-1", "OCR-1"),),
    (QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-1", "OCR-1"),
     QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-2", "REGION-2", "OCR-2")),
    (QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-1", "OCR-1"),
     QuestionAnswerReadiness("Q2", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-2", "OCR-2")),
    (QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-1", "OCR-1"),
     QuestionAnswerReadiness("Q2", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-2", "REGION-1", "OCR-2")),
    (QuestionAnswerReadiness("Q1", "READY", "ART-1", "SOURCE-REV-1", "SCOPE-1", "REGION-1", "OCR-1"),
     QuestionAnswerReadiness("Q2", "READY", "ART-1", "OTHER", "SCOPE-2", "REGION-2", "OCR-2")),
])
def test_bad_answer_mappings_rejected_before_confirmation(answers):
    request, ports, composer = make_fixture()
    ports.readiness = replace(ports.readiness, answers=answers)
    with pytest.raises((PaperAdmissionDenied, PaperAdmissionContractError)):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness"]


@pytest.mark.parametrize("status", ["UNKNOWN", "UNREADABLE", "UNMAPPED", "ABSENT_CONFIRMED"])
def test_nonready_answer_is_not_scored_or_silently_skipped(status):
    request, ports, composer = make_fixture()
    ports.readiness = replace(ports.readiness, answers=(replace(ports.readiness.answers[0], status=status), ports.readiness.answers[1]))
    with pytest.raises(PaperAnswerNotReady) as failure:
        composer.admit(request=request)
    assert failure.value.status == status
    assert ports.events == ["identity", "approval", "readiness"]


@pytest.mark.parametrize("field", ["approval_ref", "approval_revision", "selection_revision", "source_revision", "readiness_revision"])
def test_wrong_confirmation_revision_denied(field):
    request, ports, composer = make_fixture()
    ports.confirm = replace(ports.confirm, **{field: "FOREIGN"})
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events[-1] == "confirm"


@pytest.mark.parametrize("state", ["REVOKED", "STALE"])
def test_revoked_or_stale_authority_denied(state):
    request, ports, composer = make_fixture()
    ports.confirm = replace(ports.confirm, state=state)
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)


def test_mutated_original_request_during_approval_denied():
    request, ports, composer = make_fixture()
    ports.approve_action = lambda: object.__setattr__(request, "paper_ref", "OTHER")
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval"]


def test_mutated_approval_during_readiness_denied():
    request, ports, composer = make_fixture()
    ports.readiness_action = lambda: object.__setattr__(ports.approved, "source_revision", "OTHER")
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness"]


def test_mutated_readiness_during_confirmation_denied():
    request, ports, composer = make_fixture()
    ports.confirm_action = lambda: object.__setattr__(ports.readiness.answers[0], "answer_region_ref", "OTHER")
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events[-1] == "confirm"


def test_backend_exceptions_never_leak_private_reference_or_exception_context():
    request, ports, composer = make_fixture()
    def fail():
        raise RuntimeError("PRIVATE_STUDENT_RECORD")
    ports.approve_action = fail
    with pytest.raises(PaperAdmissionUnavailable) as exc:
        composer.admit(request=request)
    assert "PRIVATE_STUDENT_RECORD" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_forged_nested_request_and_foreign_readiness_type_denied_before_revision_contact():
    request, ports, composer = make_fixture()
    class Foreign:
        def __getattribute__(self, name):
            raise AssertionError("foreign object must never be read")
    ports.readiness = Foreign()
    with pytest.raises(PaperAdmissionContractError):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness"]


def test_resource_configuration_and_oversized_paper_fail_closed():
    request, ports, composer = make_fixture()
    with pytest.raises(PaperAdmissionContractError):
        ProductionPaperAdmissionComposer(identity=ports, selections=ports, answers=ports,
                                         revisions=ports, max_identifier_characters=True, max_questions=5)
    constrained = ProductionPaperAdmissionComposer(identity=ports, selections=ports, answers=ports,
                                                   revisions=ports, max_identifier_characters=64, max_questions=1)
    with pytest.raises(PaperAdmissionContractError):
        constrained.admit(request=request)
    assert ports.events == ["identity", "approval"]


@pytest.mark.parametrize("field", ["source_artifact_ref", "evidence_scope_ref"])
def test_foreign_question_source_scope_rejected_before_revision_contact(field):
    request, ports, composer = make_fixture()
    ports.readiness = replace(ports.readiness, answers=(
        replace(ports.readiness.answers[0], **{field: "FOREIGN"}),
        ports.readiness.answers[1],
    ))
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness"]


def test_approval_cannot_reuse_a_question_evidence_scope():
    request, ports, composer = make_fixture()
    ports.approved = replace(ports.approved, selected_questions=(
        ports.approved.selected_questions[0],
        replace(ports.approved.selected_questions[1], evidence_scope_ref="SCOPE-1"),
    ))
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval"]


@pytest.mark.parametrize("mutation", ["mutate_callback_actor", "mutate_callback_request"])
def test_approval_cannot_mutate_callback_identity_or_scope(mutation):
    request, ports, composer = make_fixture()
    setattr(ports, mutation, True)
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval"]


def test_readiness_cannot_mutate_provided_approval():
    request, ports, composer = make_fixture()
    ports.mutate_callback_approval = True
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness"]


def test_confirmation_cannot_mutate_passed_readiness():
    request, ports, composer = make_fixture()
    ports.mutate_callback_confirmation_readiness = True
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events[-1] == "confirm"


def test_original_actor_changed_during_approval_is_denied():
    request, ports, composer = make_fixture()
    ports.approve_action = lambda: object.__setattr__(ports.actor, "actor_ref", "OTHER")
    with pytest.raises(PaperAdmissionDenied):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval"]


@pytest.mark.parametrize("status", ["UNKNOWN", "UNREADABLE", "UNMAPPED", "ABSENT_CONFIRMED"])
def test_genuinely_unavailable_answer_does_not_need_fabricated_region(status):
    request, ports, composer = make_fixture()
    no_region = replace(ports.readiness.answers[0], status=status,
                        source_artifact_ref=None, evidence_scope_ref=None,
                        answer_region_ref=None, provenance_ref=None)
    ports.readiness = replace(ports.readiness, answers=(no_region, ports.readiness.answers[1]))
    with pytest.raises(PaperAnswerNotReady) as failure:
        composer.admit(request=request)
    assert failure.value.status == status
    assert ports.events == ["identity", "approval", "readiness"]


@pytest.mark.parametrize("field", ["source_artifact_ref", "evidence_scope_ref", "answer_region_ref", "provenance_ref"])
def test_ready_answer_requires_real_reference_not_missing_or_fabricated(field):
    request, ports, composer = make_fixture()
    ports.readiness = replace(ports.readiness, answers=(
        replace(ports.readiness.answers[0], **{field: None}),
        ports.readiness.answers[1],
    ))
    with pytest.raises(PaperAdmissionContractError):
        composer.admit(request=request)
    assert ports.events == ["identity", "approval", "readiness"]
