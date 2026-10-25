"""execution preparation trusted source/selection admission; fixtures are not backend proof."""
from dataclasses import replace

import pytest

from grading.integration.authorized_preparation import ProductionPreparationComposer
from grading.integration.choice_authority_admission import (
    ChoiceAccessGrant, ApprovedChoiceKeyRecord, VerifiedChoiceSelectionRecord,
    ChoiceRevisionConfirmation, ProductionChoiceAdmissionComposer,
    ChoiceAdmissionContractError, ChoiceAdmissionDenied, ChoiceAdmissionUnavailable,
)
from grading.integration.grading_orchestration import ProductionGradingEntry
from tests.integration.test_authorized_preparation import _compose, _inputs
from tests.integration.test_choice_binding import _choice


class ChoicePorts:
    def __init__(self, prepared):
        self.events = []
        self.prepared = prepared
        bound = prepared.prepared.bound
        authority, selection = _choice(bound)
        custody = prepared.custody
        request = prepared.prepared.request
        question = next(q for q in bound.admitted_evidence.evidence.questions if q.question_id == request.question_id)
        from grading.integration.choice_authority_admission import ChoiceAdmissionScope
        scope = ChoiceAdmissionScope(
            custody.actor_ref, custody.tenant_ref, custody.session_ref,
            request.grading_run_id, request.submission_ref, request.exam_ref,
            request.grading_spec_ref, request.question_id, question.answer_scope_ref,
            custody.source_artifact_ref, custody.source_revision,
            custody.admission_policy_identity, custody.policy_revision,
            bound.admitted_evidence.evidence.ocr_provenance,
        )
        self.grant = ChoiceAccessGrant(scope, "KEY-REV-1", "SELECTION-REV-1")
        self.key = ApprovedChoiceKeyRecord(scope, "KEY-REV-1", "APPROVAL-1", authority)
        self.selection = VerifiedChoiceSelectionRecord(scope, "SELECTION-REV-1", "OCR-SELECTION-1", selection)
        self.confirmation = ChoiceRevisionConfirmation(scope, "KEY-REV-1", "SELECTION-REV-1", custody.source_revision)

    def authorize_choice_request(self, *, request):
        self.events.append("preaccess")
        from grading.integration.choice_authority_admission import ChoicePreEvidenceGrant
        custody = self.prepared.custody
        return ChoicePreEvidenceGrant(request, custody.source_artifact_ref,
                                      custody.source_revision, "KEY-REV-1", "SELECTION-REV-1")

    def authorize_choice(self, *, scope):
        self.events.append("access")
        return self.grant

    def resolve_approved_choice_key(self, *, grant):
        self.events.append("key")
        return self.key

    def resolve_verified_choice_selection(self, *, grant):
        self.events.append("selection")
        return self.selection

    def confirm_choice_revisions(self, *, grant):
        self.events.append("confirm")
        return self.confirmation


def setup():
    request, _, pre_ports = _inputs()
    prepared = _compose(pre_ports).prepare(request=request)
    choice_ports = ChoicePorts(prepared)
    composer = ProductionChoiceAdmissionComposer(pre_evidence=choice_ports, access=choice_ports, approved_keys=choice_ports,
        selections=choice_ports, revisions=choice_ports, max_identifier_characters=64, max_choice_options=64, max_choice_criteria=64)
    return request, pre_ports, prepared, choice_ports, composer


def test_complete_pre_to_choice_admission_without_evaluator_execution():
    request, pre_ports, prepared, ports, composer = setup()
    result = composer.admit(prepared=prepared)
    assert result.bound.selection.selected_option_id == "B"
    assert result.scope.source_revision == "SOURCE-REV-1"
    assert ports.events == ["access", "key", "selection", "confirm"]
    assert result.approval_ref == "APPROVAL-1"
    assert not hasattr(result, "is_eligible")
    assert not hasattr(result, "grade")
    entry = ProductionGradingEntry(preparation=_compose(pre_ports), choices=composer)
    result2 = entry.prepare_choice(request=request)
    assert result2.bound.choice_authority.official_option_id == "B"
    assert ports.events[-5:] == ["preaccess", "access", "key", "selection", "confirm"]


def test_admitted_wrong_option_is_not_fraud_or_source_rejection():
    _, _, prepared, ports, composer = setup()
    ports.selection = replace(ports.selection, selection=replace(ports.selection.selection, selected_option_id="A"))
    out = composer.admit(prepared=prepared)
    assert out.bound.selection.selected_option_id == "A"
    assert ports.events == ["access", "key", "selection", "confirm"]


@pytest.mark.parametrize("target, field, value, last_event", [
    ("grant", "scope", "OTHER", "access"),
    ("grant", "key_revision", "KEY-OTHER", "key"),
    ("key", "key_revision", "KEY-OTHER", "key"),
    ("key", "scope", "OTHER", "key"),
    ("selection", "scope", "OTHER", "selection"),
    ("selection", "selection_revision", "OTHER", "selection"),
    ("confirmation", "source_revision", "OTHER", "confirm"),
    ("confirmation", "key_revision", "OTHER", "confirm"),
    ("confirmation", "selection_revision", "OTHER", "confirm"),
    ("confirmation", "scope", "OTHER", "confirm"),
])
def test_revision_and_scope_mismatches_fail_closed(target, field, value, last_event):
    _, _, prepared, ports, composer = setup()
    obj = getattr(ports, target)
    if field == "scope":
        value = replace(obj.scope, tenant_ref=value)
    setattr(ports, target, replace(obj, **{field: value}))
    with pytest.raises(ChoiceAdmissionDenied):
        composer.admit(prepared=prepared)
    assert ports.events[-1] == last_event


@pytest.mark.parametrize("target,field,value", [
    ("key", "approval_ref", object()),
    ("key", "key_revision", object()),
    ("selection", "selection_origin_ref", object()),
    ("selection", "selection_revision", object()),
    ("grant", "key_revision", object()),
    ("confirmation", "source_revision", object()),
])
def test_noncanonical_foreign_source_fields_do_not_run_equality(target, field, value):
    _, _, prepared, ports, composer = setup()
    obj = getattr(ports, target)
    setattr(ports, target, replace(obj, **{field: value}))
    with pytest.raises(ChoiceAdmissionContractError):
        composer.admit(prepared=prepared)


def test_foreign_submission_selected_question_or_unsupported_option_rejected():
    for field, value in (("submission_ref", "OTHER"), ("question_id", "OTHER"), ("selected_option_id", "Z")):
        _, _, prepared, ports, composer = setup()
        ports.selection = replace(ports.selection, selection=replace(ports.selection.selection, **{field: value}))
        with pytest.raises(ChoiceAdmissionDenied):
            composer.admit(prepared=prepared)
        assert "confirm" not in ports.events


def test_wrong_scoring_hash_prevents_confirmation():
    _, _, prepared, ports, composer = setup()
    ports.key = replace(ports.key, authority=replace(ports.key.authority, compiled_authority_hash="0"*64))
    with pytest.raises(ChoiceAdmissionDenied):
        composer.admit(prepared=prepared)
    assert ports.events == ["access", "key", "selection"]


def test_foreign_and_cross_question_evidence_never_emits_choice():
    for ref in ("MISSING-EVIDENCE", "FOREIGN-EVIDENCE"):
        _, _, prepared, ports, composer = setup()
        ports.selection = replace(ports.selection, selection=replace(ports.selection.selection, evidence_refs=(ref,)))
        with pytest.raises(ChoiceAdmissionDenied):
            composer.admit(prepared=prepared)
    assert ports.events == ["access", "key", "selection"]


def test_backend_deny_is_not_translated_to_unavailable():
    _, _, prepared, ports, composer = setup()
    def deny(*, scope):
        ports.events.append("access")
        raise ChoiceAdmissionDenied("SECRET-DENIAL")
    ports.authorize_choice = deny
    composer = ProductionChoiceAdmissionComposer(pre_evidence=ports, access=ports, approved_keys=ports,
        selections=ports, revisions=ports, max_identifier_characters=64, max_choice_options=64, max_choice_criteria=64)
    with pytest.raises(ChoiceAdmissionDenied) as err:
        composer.admit(prepared=prepared)
    assert "SECRET" not in str(err.value)
    assert err.value.__context__ is None
    assert ports.events == ["access"]


def test_private_backend_failure_does_not_leak_exception_context():
    _, _, prepared, ports, _ = setup()
    def failure(*, grant):
        ports.events.append("key")
        raise RuntimeError("SECRET-TOKEN")
    ports.resolve_approved_choice_key = failure
    composer = ProductionChoiceAdmissionComposer(pre_evidence=ports, access=ports, approved_keys=ports,
        selections=ports, revisions=ports, max_identifier_characters=64, max_choice_options=64, max_choice_criteria=64)
    with pytest.raises(ChoiceAdmissionUnavailable) as err:
        composer.admit(prepared=prepared)
    assert err.value.__context__ is None
    assert err.value.__cause__ is None
    assert "SECRET" not in str(err.value)
    assert ports.events == ["access", "key"]


def test_descriptor_not_invoked_at_composer_construction():
    class Hostile:
        @property
        def authorize_choice(self):
            raise RuntimeError("DESCRIPTOR-EXECUTED")
    _, _, _, ports, _ = setup()
    with pytest.raises(ChoiceAdmissionContractError):
        ProductionChoiceAdmissionComposer(pre_evidence=ports, access=Hostile(), approved_keys=ports,
            selections=ports, revisions=ports, max_identifier_characters=64, max_choice_options=64, max_choice_criteria=64)


def test_backend_method_reassignment_cannot_replace_captured_callback():
    _, _, prepared, ports, composer = setup()
    def substitute(*, scope):
        raise RuntimeError("SUBSTITUTE EXECUTED")
    ports.authorize_choice = substitute
    assert composer.admit(prepared=prepared).key_revision == "KEY-REV-1"


def test_source_scope_mismatch_fails_before_any_choice_backend_access():
    _, _, prepared, ports, composer = setup()
    object.__setattr__(prepared.custody, "source_artifact_ref", "OTHER")
    with pytest.raises(ChoiceAdmissionDenied):
        composer.admit(prepared=prepared)
    assert ports.events == []


def test_mutation_during_key_resolution_cannot_change_pinned_run_identity():
    _, _, prepared, ports, _ = setup()
    def mutate(*, grant):
        ports.events.append("key")
        object.__setattr__(prepared.prepared.bound.context, "grading_run_id", "FORGED-RUN")
        return ports.key
    ports.resolve_approved_choice_key = mutate
    composer = ProductionChoiceAdmissionComposer(pre_evidence=ports, access=ports, approved_keys=ports,
        selections=ports, revisions=ports, max_identifier_characters=64, max_choice_options=64, max_choice_criteria=64)
    with pytest.raises(ChoiceAdmissionDenied):
        composer.admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_mutation_during_key_resolution_cannot_change_pinned_evidence_scope():
    _, _, prepared, ports, _ = setup()
    block = prepared.prepared.bound.admitted_evidence.evidence.questions[0]
    def mutate(*, grant):
        ports.events.append("key")
        object.__setattr__(block, "answer_scope_ref", "OTHER-SCOPE")
        return ports.key
    ports.resolve_approved_choice_key = mutate
    composer = ProductionChoiceAdmissionComposer(pre_evidence=ports, access=ports, approved_keys=ports,
        selections=ports, revisions=ports, max_identifier_characters=64, max_choice_options=64, max_choice_criteria=64)
    with pytest.raises(ChoiceAdmissionDenied):
        composer.admit(prepared=prepared)
    assert ports.events == ["access", "key"]

# Fresh adversarial acceptance for the complete, pre-callback PRE graph and paper execution integrity.

def _fresh_composer(ports, *, max_identifier=64, max_options=64, max_criteria=64):
    return ProductionChoiceAdmissionComposer(
        pre_evidence=ports, access=ports, approved_keys=ports,
        selections=ports, revisions=ports,
        max_identifier_characters=max_identifier,
        max_choice_options=max_options, max_choice_criteria=max_criteria,
    )


def test_g0_choice_deny_precedes_any_preparation_backend_or_evidence_access():
    from grading.integration.choice_authority_admission import ChoiceAdmissionDenied
    request, pre_ports, prepared, ports, _ = setup()
    def deny(*, request):
        ports.events.append("preaccess")
        raise ChoiceAdmissionDenied("PRIVATE_EXTERNAL_DENIAL")
    ports.authorize_choice_request = deny
    pre_ports.events.clear()
    entry = ProductionGradingEntry(preparation=_compose(pre_ports), choices=_fresh_composer(ports))
    with pytest.raises(ChoiceAdmissionDenied):
        entry.prepare_choice(request=request)
    assert pre_ports.events == []
    assert ports.events == ["preaccess"]


def test_g0_wrong_pre_evidence_request_rejects_before_open():
    from grading.integration.choice_authority_admission import ChoicePreEvidenceGrant
    request, pre_ports, prepared, ports, _ = setup()
    def foreign(*, request):
        ports.events.append("preaccess")
        return ChoicePreEvidenceGrant(replace(request, tenant_ref="FOREIGN"),
            prepared.custody.source_artifact_ref, prepared.custody.source_revision,
            "KEY-REV-1", "SELECTION-REV-1")
    ports.authorize_choice_request = foreign
    pre_ports.events.clear()
    with pytest.raises(ChoiceAdmissionDenied):
        ProductionGradingEntry(preparation=_compose(pre_ports), choices=_fresh_composer(ports)).prepare_choice(request=request)
    assert pre_ports.events == []
    assert ports.events == ["preaccess"]


def test_g0_rejects_pre_evidence_revision_disagreement_before_choice_key_resolution():
    from grading.integration.choice_authority_admission import ChoicePreEvidenceGrant
    request, pre_ports, prepared, ports, _ = setup()
    def changed(*, request):
        ports.events.append("preaccess")
        return ChoicePreEvidenceGrant(request, prepared.custody.source_artifact_ref,
            prepared.custody.source_revision, "WRONG-KEY-REV", "SELECTION-REV-1")
    ports.authorize_choice_request = changed
    with pytest.raises(ChoiceAdmissionDenied):
        ProductionGradingEntry(preparation=_compose(pre_ports), choices=_fresh_composer(ports)).prepare_choice(request=request)
    assert ports.events == ["preaccess", "access"]


@pytest.mark.parametrize("field", [
    "actor_ref", "tenant_ref", "session_ref", "source_revision",
    "source_artifact_ref", "admission_policy_identity", "policy_revision",
])
def test_all_pre_custody_mutations_stop_before_subsequent_backend_calls(field):
    _, _, prepared, ports, _ = setup()
    def mutate(*, grant):
        ports.events.append("key")
        object.__setattr__(prepared.custody, field, "FORGED")
        return ports.key
    ports.resolve_approved_choice_key = mutate
    with pytest.raises(ChoiceAdmissionDenied):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key"]


@pytest.mark.parametrize("field,new_value", [
    ("grading_run_id", "BAD-RUN"),
    ("submission_ref", "BAD-SUBMISSION"),
    ("exam_ref", "BAD-EXAM"),
    ("question_id", "BAD-QUESTION"),
])
def test_all_original_request_mutations_stop_before_subsequent_backend_calls(field, new_value):
    _, _, prepared, ports, _ = setup()
    def mutate(*, grant):
        ports.events.append("key")
        object.__setattr__(prepared.prepared.request, field, new_value)
        return ports.key
    ports.resolve_approved_choice_key = mutate
    with pytest.raises(ChoiceAdmissionDenied):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_original_grading_spec_version_mutation_is_detected():
    _, _, prepared, ports, _ = setup()
    def mutate(*, grant):
        ports.events.append("key")
        object.__setattr__(prepared.prepared.request.grading_spec_ref, "version", 2)
        return ports.key
    ports.resolve_approved_choice_key = mutate
    with pytest.raises(ChoiceAdmissionDenied):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_pre_graph_full_policy_inflation_fails_before_selection_callback():
    _, _, prepared, ports, _ = setup()
    admitted = prepared.prepared.bound.admitted_evidence
    evidence = admitted.evidence
    policy = admitted.effective_policy_snapshot
    assert policy.max_questions == 5
    original = evidence.questions[0]
    def mutate(*, grant):
        ports.events.append("key")
        extra = tuple(replace(original, question_id=f"Q{i}", answer_scope_ref=f"SCOPE{i}",
                              blocks=(), warnings=()) for i in range(2, 7))
        object.__setattr__(admitted, "effective_policy_snapshot", replace(policy, max_questions=6))
        object.__setattr__(evidence, "questions", (original,) + extra)
        return ports.key
    ports.resolve_approved_choice_key = mutate
    with pytest.raises(ChoiceAdmissionDenied):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_callback_drift_detected_after_final_revision_confirmation():
    _, _, prepared, ports, _ = setup()
    def mutate(*, grant):
        ports.events.append("confirm")
        object.__setattr__(prepared.custody, "source_revision", "REVOKED")
        return ports.confirmation
    ports.confirm_choice_revisions = mutate
    with pytest.raises(ChoiceAdmissionDenied):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key", "selection", "confirm"]


def test_overlong_approved_option_is_rejected_before_binder():
    _, _, prepared, ports, _ = setup()
    object.__setattr__(ports.key.authority, "option_ids", ("A", "B", "C" * 300))
    with pytest.raises(ChoiceAdmissionContractError):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_approved_option_count_and_projection_count_are_bounded():
    for field, oversize in (
        ("option_ids", tuple(f"OPT{i}" for i in range(65))),
        ("match_projection", None),
    ):
        _, _, prepared, ports, _ = setup()
        if field == "match_projection":
            original = ports.key.authority.match_projection[0]
            oversize = (original,) * 65
        object.__setattr__(ports.key.authority, field, oversize)
        with pytest.raises(ChoiceAdmissionContractError):
            _fresh_composer(ports).admit(prepared=prepared)
        assert ports.events == ["access", "key"]


@pytest.mark.parametrize("op,parameter", [
    ("authorize_choice_request", "request"),
    ("authorize_choice", "scope"),
    ("resolve_approved_choice_key", "grant"),
    ("resolve_verified_choice_selection", "grant"),
    ("confirm_choice_revisions", "grant"),
])
def test_incompatible_backend_signatures_rejected_at_configuration(op, parameter):
    _, _, _, ports, _ = setup()
    def wrong(*, unavailable_required):
        raise AssertionError("SHOULD NEVER BE CALLED")
    setattr(ports, op, wrong)
    with pytest.raises(ChoiceAdmissionContractError):
        _fresh_composer(ports)
    assert ports.events == []


def test_forged_function_signature_metadata_is_rejected_at_configuration():
    import inspect
    _, _, _, ports, _ = setup()
    def fake(*, unavailable_required):
        raise AssertionError("SHOULD NEVER BE CALLED")
    fake.__signature__ = inspect.Signature([inspect.Parameter("scope", inspect.Parameter.KEYWORD_ONLY)])
    ports.authorize_choice = fake
    with pytest.raises(ChoiceAdmissionContractError):
        _fresh_composer(ports)
    assert ports.events == []


def test_prepared_foreign_equality_never_executes():
    _, _, prepared, ports, _ = setup()
    events = []
    class Foreign:
        def __eq__(self, other):
            events.append("UNSAFE")
            raise RuntimeError("PRIVATE")
    question = prepared.prepared.bound.admitted_evidence.evidence.questions[0]
    object.__setattr__(question, "question_id", Foreign())
    with pytest.raises(ChoiceAdmissionContractError):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == [] and events == []


def test_constructor_confidentiality_inside_ambient_exception():
    import traceback
    _, _, _, ports, _ = setup()
    try:
        raise ValueError("PRIVATE_SCHOOL_SECRET")
    except ValueError:
        with pytest.raises(ChoiceAdmissionContractError) as caught:
            ProductionChoiceAdmissionComposer(
                pre_evidence=ports, access=ports, approved_keys=ports,
                selections=ports, revisions=ports, max_identifier_characters=0,
                max_choice_options=64, max_choice_criteria=64)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert "PRIVATE_SCHOOL_SECRET" not in ''.join(traceback.format_exception(caught.value))

# Independent acceptance regressions: callback objects are never the trusted
# request baseline; foreign nested records must never execute properties.
@pytest.mark.parametrize("field", [
    "tenant_ref", "session_ref", "grading_run_id", "submission_ref",
    "exam_ref", "question_id", "grading_spec_ref.id", "grading_spec_ref.version",
])
def test_pre_evidence_callback_cannot_rewrite_its_authorized_request(field):
    import traceback
    from grading.integration.choice_authority_admission import ChoicePreEvidenceGrant
    request, pre_ports, prepared, ports, _ = setup()
    def mutate(*, request):
        ports.events.append("preaccess")
        if "." in field:
            _, nested = field.split(".")
            object.__setattr__(request.grading_spec_ref, nested,
                               2 if nested == "version" else "FOREIGN-SPEC")
        else:
            object.__setattr__(request, field, "FOREIGN")
        return ChoicePreEvidenceGrant(
            request, prepared.custody.source_artifact_ref,
            prepared.custody.source_revision, "KEY-REV-1", "SELECTION-REV-1",
        )
    ports.authorize_choice_request = mutate
    pre_ports.events.clear()
    entry = ProductionGradingEntry(preparation=_compose(pre_ports), choices=_fresh_composer(ports))
    try:
        raise ValueError("PRIVATE_STUDENT_CONTEXT")
    except ValueError:
        with pytest.raises(ChoiceAdmissionDenied) as caught:
            entry.prepare_choice(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_STUDENT_CONTEXT" not in "".join(traceback.format_exception(caught.value))
    assert ports.events == ["preaccess"] and pre_ports.events == []


def test_pre_evidence_callback_cannot_rewrite_original_caller_request():
    from grading.integration.choice_authority_admission import ChoicePreEvidenceGrant
    request, pre_ports, prepared, ports, _ = setup()
    original_run = request.grading_run_id
    def mutate_original(*, request):
        ports.events.append("preaccess")
        object.__setattr__(original, "grading_run_id", "FORGED-RUN")
        return ChoicePreEvidenceGrant(
            request, prepared.custody.source_artifact_ref,
            prepared.custody.source_revision, "KEY-REV-1", "SELECTION-REV-1",
        )
    original = request
    ports.authorize_choice_request = mutate_original
    pre_ports.events.clear()
    with pytest.raises(ChoiceAdmissionDenied):
        ProductionGradingEntry(preparation=_compose(pre_ports), choices=_fresh_composer(ports)).prepare_choice(request=request)
    assert original_run == "RUN-1"
    assert ports.events == ["preaccess"] and pre_ports.events == []


def test_pre_evidence_callback_malformed_mutation_is_denial_not_backend_outage():
    from grading.integration.choice_authority_admission import ChoicePreEvidenceGrant
    request, pre_ports, prepared, ports, _ = setup()
    def malformed(*, request):
        ports.events.append("preaccess")
        object.__setattr__(request, "tenant_ref", object())
        return ChoicePreEvidenceGrant(
            request, prepared.custody.source_artifact_ref,
            prepared.custody.source_revision, "KEY-REV-1", "SELECTION-REV-1",
        )
    ports.authorize_choice_request = malformed
    pre_ports.events.clear()
    with pytest.raises(ChoiceAdmissionDenied):
        ProductionGradingEntry(preparation=_compose(pre_ports), choices=_fresh_composer(ports)).prepare_choice(request=request)
    assert ports.events == ["preaccess"] and pre_ports.events == []


@pytest.mark.parametrize("projection_field", ["match_projection", "mismatch_projection"])
def test_approved_projection_levels_are_bounded_before_selection_callback(projection_field):
    _, _, prepared, ports, composer = setup()
    a = ports.key.authority
    previous = getattr(a, projection_field)
    changed = tuple(replace(item, selected_level="S" * 10000) for item in previous)
    ports.key = replace(ports.key, authority=replace(a, **{projection_field: changed}))
    with pytest.raises(ChoiceAdmissionContractError):
        composer.admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_approved_spec_identifier_is_bounded_before_selection_callback():
    from grading.contracts.paper_aggregation import GradingSpecRef
    _, _, prepared, ports, composer = setup()
    a = ports.key.authority
    changed = replace(a, grading_spec_ref=GradingSpecRef("S" * 10000, a.grading_spec_ref.version))
    ports.key = replace(ports.key, authority=changed)
    with pytest.raises(ChoiceAdmissionContractError):
        composer.admit(prepared=prepared)
    assert ports.events == ["access", "key"]


def test_mutated_prepared_admitted_evidence_cannot_execute_foreign_property():
    import traceback
    _, _, prepared, ports, _ = setup()
    executed = []
    class Foreign:
        @property
        def effective_policy_snapshot(self):
            executed.append("hostile-property")
            raise RuntimeError("PRIVATE_FOREIGN_BACKEND_DIAGNOSTIC")
    def mutate(*, scope):
        ports.events.append("access")
        object.__setattr__(prepared.prepared.bound, "admitted_evidence", Foreign())
        return ports.grant
    ports.authorize_choice = mutate
    try:
        raise ValueError("PRIVATE_AMBIENT_DATA")
    except ValueError:
        with pytest.raises(ChoiceAdmissionDenied) as caught:
            _fresh_composer(ports).admit(prepared=prepared)
    assert executed == [] and ports.events == ["access"]
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))


def test_approved_authority_near_identifier_limit_and_wrong_option_remain_valid():
    _, _, prepared, ports, _ = setup()
    a = ports.key.authority
    projections = {}
    for field in ("match_projection", "mismatch_projection"):
        projections[field] = tuple(replace(item, selected_level="L" * 64)
                                   for item in getattr(a, field))
    # This is structurally valid admission; no invented rubric-level meaning.
    ports.key = replace(ports.key, authority=replace(a, **projections))
    ports.selection = replace(ports.selection, selection=replace(
        ports.selection.selection, selected_option_id="A"))
    result = _fresh_composer(ports).admit(prepared=prepared)
    assert result.bound.selection.selected_option_id == "A"
    assert ports.events == ["access", "key", "selection", "confirm"]


def test_foreign_official_grading_spec_is_rejected_without_descriptor_access():
    _, _, prepared, ports, composer = setup()
    seen = []
    class ForeignSpec:
        @property
        def id(self):
            seen.append("unsound-access")
            raise RuntimeError("PRIVATE_GRADING_SPEC")
    a = replace(ports.key.authority)
    object.__setattr__(a, "grading_spec_ref", ForeignSpec())
    ports.key = replace(ports.key, authority=a)
    with pytest.raises(ChoiceAdmissionContractError):
        composer.admit(prepared=prepared)
    assert seen == [] and ports.events == ["access", "key"]


@pytest.mark.parametrize("version", [0, -1, True, "2"])
def test_malformed_official_grading_spec_version_stops_before_selection(version):
    _, _, prepared, ports, composer = setup()
    spec = replace(ports.key.authority.grading_spec_ref)
    object.__setattr__(spec, "version", version)
    authority = replace(ports.key.authority)
    object.__setattr__(authority, "grading_spec_ref", spec)
    ports.key = replace(ports.key, authority=authority)
    with pytest.raises(ChoiceAdmissionContractError):
        composer.admit(prepared=prepared)
    assert ports.events == ["access", "key"]


@pytest.mark.parametrize("damage", [
    "delete_policy", "delete_evidence", "delete_bound", "delete_policy_number",
])
def test_callback_removed_previously_validated_fields_are_denied(damage):
    """Contract errors before admission differ from source drift after an authority callback."""
    import traceback
    _, _, prepared, ports, _ = setup()

    def altered(*, scope):
        ports.events.append("access")
        source = prepared.prepared
        admitted = source.bound.admitted_evidence
        if damage == "delete_policy":
            object.__delattr__(admitted, "effective_policy_snapshot")
        elif damage == "delete_evidence":
            object.__delattr__(admitted, "evidence")
        elif damage == "delete_bound":
            object.__delattr__(source, "bound")
        else:
            object.__delattr__(admitted.effective_policy_snapshot, "max_questions")
        return ports.grant

    ports.authorize_choice = altered
    try:
        raise ValueError("PRIVATE_ORIGINAL_STUDENT_ANSWER")
    except ValueError:
        with pytest.raises(ChoiceAdmissionDenied) as caught:
            _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access"]
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_ORIGINAL_STUDENT_ANSWER" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("phase, expected", [
    ("access", ["access"]),
    ("key", ["access", "key"]),
    ("selection", ["access", "key", "selection"]),
    ("confirm", ["access", "key", "selection", "confirm"]),
])
def test_removed_prepared_graph_after_each_authority_phase_is_denied(phase, expected):
    _, _, prepared, ports, _ = setup()
    operation, result_name = {
        "access": ("authorize_choice", "grant"),
        "key": ("resolve_approved_choice_key", "key"),
        "selection": ("resolve_verified_choice_selection", "selection"),
        "confirm": ("confirm_choice_revisions", "confirmation"),
    }[phase]

    def altered(**kwargs):
        ports.events.append(phase)
        object.__delattr__(prepared.prepared, "bound")
        return getattr(ports, result_name)

    setattr(ports, operation, altered)
    with pytest.raises(ChoiceAdmissionDenied) as caught:
        _fresh_composer(ports).admit(prepared=prepared)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert ports.events == expected


@pytest.mark.parametrize("invalid", ["preparation", "choices"])
def test_g0_invalid_composer_error_hides_ambient_confidential_context(invalid):
    import traceback
    _, pre_ports, _, ports, composer = setup()
    configured = {"preparation": _compose(pre_ports), "choices": composer}
    configured[invalid] = None
    try:
        raise ValueError("PRIVATE_G0_STUDENT_ANSWER")
    except ValueError:
        with pytest.raises(TypeError) as caught:
            ProductionGradingEntry(**configured)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_G0_STUDENT_ANSWER" not in "".join(traceback.format_exception(caught.value))


def test_missing_initial_prepared_graph_field_is_contract_error_before_callbacks():
    _, _, prepared, ports, composer = setup()
    object.__delattr__(prepared.prepared, "bound")
    with pytest.raises(ChoiceAdmissionContractError):
        composer.admit(prepared=prepared)
    assert ports.events == []


def test_g0_success_control_remains_admission_only():
    request, pre_ports, _, ports, composer = setup()
    entry = ProductionGradingEntry(preparation=_compose(pre_ports), choices=composer)
    output = entry.prepare_choice(request=request)
    assert output.scope.grading_run_id == request.grading_run_id
    assert ports.events == ["preaccess", "access", "key", "selection", "confirm"]
    assert not hasattr(output, "grade") and not hasattr(output, "is_eligible")


# Callback outcome precedence: once a source was validated, its corruption is
# an integrity denial even when the same callback returns bad data or fails.
# These tests cover all four authority phases and the pre-evidence operation.
@pytest.mark.parametrize("operation,event,response", [
    ("authorize_choice", "access", "grant"),
    ("resolve_approved_choice_key", "key", "key"),
    ("resolve_verified_choice_selection", "selection", "selection"),
    ("confirm_choice_revisions", "confirm", "confirmation"),
])
@pytest.mark.parametrize("field", ["id", "version"])
def test_shared_spec_corruption_takes_precedence_over_response_validation(operation, event, response, field):
    import traceback
    _, _, prepared, ports, _ = setup()

    def corrupt(**kwargs):
        ports.events.append(event)
        object.__delattr__(prepared.prepared.request.grading_spec_ref, field)
        return getattr(ports, response)  # This record shares the damaged spec.

    setattr(ports, operation, corrupt)
    try:
        raise ValueError("PRIVATE_CALLBACK_AMBIENT_DATA")
    except ValueError:
        with pytest.raises(ChoiceAdmissionDenied) as caught:
            _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == ["access", "key", "selection", "confirm"][:(
        ["access", "key", "selection", "confirm"].index(event) + 1
    )]
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_CALLBACK_AMBIENT_DATA" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("operation,event", [
    ("authorize_choice", "access"),
    ("resolve_approved_choice_key", "key"),
    ("resolve_verified_choice_selection", "selection"),
    ("confirm_choice_revisions", "confirm"),
])
@pytest.mark.parametrize("outcome", ["bad_reply", "backend_failure", "explicit_denial"])
def test_callback_corruption_takes_precedence_over_all_outcomes(operation, event, outcome):
    _, _, prepared, ports, _ = setup()

    def corrupt(**kwargs):
        ports.events.append(event)
        object.__delattr__(prepared.prepared, "bound")
        if outcome == "backend_failure":
            raise RuntimeError("PRIVATE_BACKEND_EXCEPTION")
        if outcome == "explicit_denial":
            raise ChoiceAdmissionDenied("PRIVATE_BACKEND_DENIAL")
        return object()

    setattr(ports, operation, corrupt)
    with pytest.raises(ChoiceAdmissionDenied) as caught:
        _fresh_composer(ports).admit(prepared=prepared)
    assert str(caught.value) == "CHOICE source changed during admission."
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert ports.events == ["access", "key", "selection", "confirm"][:(
        ["access", "key", "selection", "confirm"].index(event) + 1
    )]


@pytest.mark.parametrize("operation,event,original_outcome,expected", [
    ("authorize_choice", "access", "backend_failure", ChoiceAdmissionUnavailable),
    ("resolve_approved_choice_key", "key", "backend_failure", ChoiceAdmissionUnavailable),
    ("resolve_verified_choice_selection", "selection", "backend_failure", ChoiceAdmissionUnavailable),
    ("confirm_choice_revisions", "confirm", "backend_failure", ChoiceAdmissionUnavailable),
    ("authorize_choice", "access", "explicit_denial", ChoiceAdmissionDenied),
    ("resolve_approved_choice_key", "key", "explicit_denial", ChoiceAdmissionDenied),
    ("resolve_verified_choice_selection", "selection", "explicit_denial", ChoiceAdmissionDenied),
    ("confirm_choice_revisions", "confirm", "explicit_denial", ChoiceAdmissionDenied),
    ("authorize_choice", "access", "bad_reply", ChoiceAdmissionContractError),
    ("resolve_approved_choice_key", "key", "bad_reply", ChoiceAdmissionContractError),
    ("resolve_verified_choice_selection", "selection", "bad_reply", ChoiceAdmissionContractError),
    ("confirm_choice_revisions", "confirm", "bad_reply", ChoiceAdmissionContractError),
])
def test_unchanged_source_preserves_distinct_callback_failure_taxonomy(operation, event, original_outcome, expected):
    _, _, prepared, ports, _ = setup()

    def unchanged(**kwargs):
        ports.events.append(event)
        if original_outcome == "backend_failure":
            raise RuntimeError("PRIVATE_BACKEND_EXCEPTION")
        if original_outcome == "explicit_denial":
            raise ChoiceAdmissionDenied("PRIVATE_BACKEND_DENIAL")
        return object()

    setattr(ports, operation, unchanged)
    with pytest.raises(expected) as caught:
        _fresh_composer(ports).admit(prepared=prepared)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert ports.events == ["access", "key", "selection", "confirm"][:(
        ["access", "key", "selection", "confirm"].index(event) + 1
    )]


@pytest.mark.parametrize("damage", ["callback_copy", "original_request"])
@pytest.mark.parametrize("outcome", ["backend_failure", "explicit_denial", "bad_reply"])
def test_pre_evidence_corruption_takes_precedence_without_pre_io(damage, outcome):
    request, pre_ports, _, ports, _ = setup()

    def corrupt(*, request: object):
        ports.events.append("preaccess")
        target = request if damage == "callback_copy" else original
        object.__delattr__(target, "question_id")
        if outcome == "backend_failure":
            raise RuntimeError("PRIVATE_PRE_EVIDENCE_ERROR")
        if outcome == "explicit_denial":
            raise ChoiceAdmissionDenied("PRIVATE_PRE_EVIDENCE_DENIAL")
        return object()

    original = request
    ports.authorize_choice_request = corrupt
    pre_ports.events.clear()
    with pytest.raises(ChoiceAdmissionDenied) as caught:
        ProductionGradingEntry(
            preparation=_compose(pre_ports), choices=_fresh_composer(ports),
        ).prepare_choice(request=request)
    assert str(caught.value) == "Pre-evidence CHOICE request changed."
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert ports.events == ["preaccess"] and pre_ports.events == []


@pytest.mark.parametrize("outcome,expected", [
    ("backend_failure", ChoiceAdmissionUnavailable),
    ("explicit_denial", ChoiceAdmissionDenied),
    ("bad_reply", ChoiceAdmissionContractError),
])
def test_pre_evidence_unchanged_failure_taxonomy(outcome, expected):
    request, pre_ports, _, ports, _ = setup()

    def clean(*, request):
        ports.events.append("preaccess")
        if outcome == "backend_failure":
            raise RuntimeError("PRIVATE_BACKEND_FAILURE")
        if outcome == "explicit_denial":
            raise ChoiceAdmissionDenied("PRIVATE_BACKEND_DENIAL")
        return object()

    ports.authorize_choice_request = clean
    pre_ports.events.clear()
    with pytest.raises(expected) as caught:
        ProductionGradingEntry(
            preparation=_compose(pre_ports), choices=_fresh_composer(ports),
        ).prepare_choice(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert ports.events == ["preaccess"] and pre_ports.events == []

# Callback argument custody: the root's validated PRE graph and the detached
# object supplied to each installed authority port are separate integrity checks.
_POST_PRE_ARGUMENT_PHASES = (
    ("authorize_choice", "grant", ("access",)),
    ("resolve_approved_choice_key", "key", ("access", "key")),
    ("resolve_verified_choice_selection", "selection", ("access", "key", "selection")),
    ("confirm_choice_revisions", "confirmation", ("access", "key", "selection", "confirm")),
)


@pytest.mark.parametrize("operation, reply_name, expected_events", _POST_PRE_ARGUMENT_PHASES)
@pytest.mark.parametrize("outcome", ("valid", "unavailable", "denied", "malformed"))
def test_detached_authority_argument_mutation_is_denied_before_reply_or_error(
        operation, reply_name, expected_events, outcome):
    import traceback
    _, _, prepared, ports, _ = setup()

    def change_callback_argument(**kwargs):
        actual_scope = (kwargs["scope"] if operation == "authorize_choice"
                        else kwargs["grant"].scope)
        object.__setattr__(actual_scope, "tenant_ref", "CROSSED-TENANT")
        ports.events.append(expected_events[-1])
        if outcome == "unavailable":
            raise RuntimeError("PRIVATE_BACKEND_FAILURE")
        if outcome == "denied":
            raise ChoiceAdmissionDenied("PRIVATE_BACKEND_DENIAL")
        if outcome == "malformed":
            return object()
        return getattr(ports, reply_name)

    setattr(ports, operation, change_callback_argument)
    try:
        raise RuntimeError("PRIVATE_AMBIENT_CONTEXT")
    except RuntimeError:
        with pytest.raises(ChoiceAdmissionDenied) as caught:
            _fresh_composer(ports).admit(prepared=prepared)
    assert str(caught.value) == "CHOICE callback argument changed during admission."
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "PRIVATE_" not in "".join(traceback.format_exception(caught.value))
    assert ports.events == list(expected_events)


@pytest.mark.parametrize("operation, reply_name, expected_events", _POST_PRE_ARGUMENT_PHASES)
def test_original_source_mutation_takes_precedence_over_detached_callback_argument(
        operation, reply_name, expected_events):
    _, _, prepared, ports, _ = setup()

    def change_both(**kwargs):
        actual_scope = (kwargs["scope"] if operation == "authorize_choice"
                        else kwargs["grant"].scope)
        object.__setattr__(actual_scope, "tenant_ref", "CROSSED-TENANT")
        object.__setattr__(prepared.custody, "tenant_ref", "CROSSED-TENANT")
        ports.events.append(expected_events[-1])
        return getattr(ports, reply_name)

    setattr(ports, operation, change_both)
    with pytest.raises(ChoiceAdmissionDenied, match="Authorized PRE source and CHOICE scope do not agree"):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == list(expected_events)


@pytest.mark.parametrize("operation, reply_name, expected_events", _POST_PRE_ARGUMENT_PHASES)
def test_detached_grant_revision_corruption_is_denied(operation, reply_name, expected_events):
    _, _, prepared, ports, _ = setup()

    def change_revision(**kwargs):
        target = kwargs["scope"] if operation == "authorize_choice" else kwargs["grant"]
        object.__setattr__(target, "actor_ref" if operation == "authorize_choice"
                           else "key_revision", "FORGED-IDENTITY")
        ports.events.append(expected_events[-1])
        return getattr(ports, reply_name)

    setattr(ports, operation, change_revision)
    with pytest.raises(ChoiceAdmissionDenied, match="CHOICE callback argument changed"):
        _fresh_composer(ports).admit(prepared=prepared)
    assert ports.events == list(expected_events)
