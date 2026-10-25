"""Official paper admission pins its installed authorities across all admissions.

A source callback may not turn a revoked or not-READY school record into a
positive plan by replacing the authority used later in the same or next call.
The test ports are synthetic; real school-issuer authenticity is a separate gate.
"""
from dataclasses import replace

import pytest

from grading.integration.paper_readiness_admission import (
    PaperAdmissionUnavailable, PaperAdmissionDenied, PaperAnswerNotReady,
)
from tests.integration.test_paper_readiness_admission import make_fixture


def test_approval_callback_cannot_replace_revision_source_before_first_plan():
    request, ports, owner = make_fixture()
    original = ports.confirm
    ports.confirm = replace(ports.confirm, state='REVOKED')
    def substitute():
        object.__setattr__(owner, '_revisions', lambda *, approval, readiness: original)
    ports.approve_action = substitute
    with pytest.raises((PaperAdmissionUnavailable, PaperAdmissionDenied)):
        owner.admit(request=request)
    ports.approve_action = None
    with pytest.raises((PaperAdmissionUnavailable, PaperAdmissionDenied)):
        owner.admit(request=request)


def test_approval_callback_cannot_replace_not_ready_source_on_later_calls():
    request, ports, owner = make_fixture()
    ready = ports.readiness
    ports.readiness = replace(ports.readiness, answers=(
        replace(ports.readiness.answers[0], status='UNKNOWN'),
        ports.readiness.answers[1],
    ))
    def substitute():
        object.__setattr__(owner, '_answers', lambda *, approval: ready)
    ports.approve_action = substitute
    with pytest.raises((PaperAdmissionUnavailable, PaperAdmissionDenied)):
        owner.admit(request=request)
    ports.approve_action = None
    with pytest.raises((PaperAdmissionUnavailable, PaperAdmissionDenied)):
        owner.admit(request=request)


def test_identity_callback_cannot_replace_foreign_selection_source():
    request, ports, owner = make_fixture()
    original_approval = ports.approved
    ports.approved = replace(ports.approved, request=replace(request, tenant_ref='OTHER'))
    original_identity = ports.current_actor
    def substitute_selection():
        object.__setattr__(owner, '_selection', lambda *, actor, request: original_approval)
        return original_identity()
    object.__setattr__(owner, '_identity', substitute_selection)
    with pytest.raises((PaperAdmissionUnavailable, PaperAdmissionDenied)):
        owner.admit(request=request)


def test_legitimate_multiple_admissions_still_use_same_school_sources():
    request, ports, owner = make_fixture()
    first = owner.admit(request=request)
    second = owner.admit(request=request)
    assert first == second
    assert ports.events == ['identity','approval','readiness','confirm'] * 2


def test_deleted_revision_installation_remains_typed_unavailable():
    request, ports, owner = make_fixture()
    def remove_reader():
        object.__delattr__(owner, '_revisions')
    ports.approve_action = remove_reader
    with pytest.raises(PaperAdmissionUnavailable):
        owner.admit(request=request)
    assert ports.events == ['identity', 'approval']


def test_deleted_installation_snapshot_remains_typed_unavailable():
    request, ports, owner = make_fixture()
    def remove_snapshot():
        object.__delattr__(owner, '_installed')
    ports.approve_action = remove_snapshot
    with pytest.raises(PaperAdmissionUnavailable):
        owner.admit(request=request)
    assert ports.events == ['identity', 'approval']


# Independent cross-operation installation-custody regressions.
def _forge_matching_baseline(owner, attr, replacement):
    fields = ('_identity', '_selection', '_answers', '_revisions', '_limit', '_max_questions')
    object.__setattr__(owner, attr, replacement)
    object.__setattr__(owner, '_installed', tuple(object.__getattribute__(owner, f) for f in fields))


def test_readiness_callback_cannot_replace_revision_authority_and_its_baseline():
    req, ports, owner = make_fixture()
    permitted_before_revoke = ports.confirm
    def revoke_then_replace():
        ports.confirm = replace(ports.confirm, state='REVOKED')
        _forge_matching_baseline(owner, '_revisions', lambda *, approval, readiness: permitted_before_revoke)
    ports.readiness_action = revoke_then_replace
    with pytest.raises((PaperAdmissionDenied, PaperAdmissionUnavailable)):
        owner.admit(request=req)
    # Reject the rebaselining immediately after the readiness callback.
    # No later revision source should be called after installation drift.
    assert ports.events.count('confirm') == 0
    ports.readiness_action = None
    # New request must not treat the rebaselined counterfeit source as authoritative.
    with pytest.raises((PaperAdmissionDenied, PaperAdmissionUnavailable)):
        owner.admit(request=req)


def test_first_callback_cannot_replace_unready_answers_and_original_baseline():
    req, ports, owner = make_fixture()
    ready = ports.readiness
    def replace_answer_reader():
        ports.readiness = replace(ports.readiness, answers=(replace(ports.readiness.answers[0],status='UNKNOWN'), ports.readiness.answers[1]))
        _forge_matching_baseline(owner, '_answers', lambda *, approval: ready)
    ports.approve_action = replace_answer_reader
    with pytest.raises((PaperAdmissionDenied, PaperAdmissionUnavailable, PaperAnswerNotReady)):
        owner.admit(request=req)
    ports.approve_action = None
    with pytest.raises((PaperAdmissionDenied, PaperAdmissionUnavailable, PaperAnswerNotReady)):
        owner.admit(request=req)


def test_legitimate_current_admission_control():
    req, ports, owner = make_fixture()
    plan=owner.admit(request=req)
    assert [x.request.question_id for x in plan.questions] == ['Q1','Q2']
    assert ports.events == ['identity','approval','readiness','confirm']


def test_normal_revoke_is_denied_control():
    req, ports, owner = make_fixture()
    ports.confirm=replace(ports.confirm,state='REVOKED')
    with pytest.raises(PaperAdmissionDenied):
        owner.admit(request=req)


def test_strict_root_never_commits_after_callback_rebaselines_revoked_school_source():
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from grading.integration.production_paper_operations import PaperOperationKind
    from tests.integration.test_family_first_scored_cas import connected, POLICY
    from tests.integration.test_production_paper_operations import _root
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root, ports = _root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,),qualified=True)
    initial_confirmation=ports.confirmation
    owner=root._admission
    class PoisonOnSelection(list):
        fired=False
        def append(self, item):
            super().append(item)
            if item=='selection' and not self.fired:
                self.fired=True
                ports.confirmation=replace(ports.confirmation,state='REVOKED')
                _forge_matching_baseline(owner,'_revisions',
                    lambda *, approval, readiness: initial_confirmation)
    ports.events=PoisonOnSelection()
    with pytest.raises((PaperAdmissionDenied,PaperAdmissionUnavailable)):
        root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims == 0 and store.commits == 0
    # Original installed school revision is still revoked on the next request.
    with pytest.raises((PaperAdmissionDenied,PaperAdmissionUnavailable)):
        root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims == 0 and store.commits == 0


def test_resource_limit_type_cannot_be_rebased_to_boolean():
    request, ports, owner = make_fixture()
    def substitute():
        object.__setattr__(owner, '_limit', True)
    ports.approve_action = substitute
    with pytest.raises(PaperAdmissionUnavailable):
        owner.admit(request=request)


def test_one_time_installation_registry_does_not_keep_cyclic_owner_alive():
    import gc
    import weakref
    def create():
        request, ports, owner = make_fixture()
        ports.approve_action = lambda: owner  # cycle through original installed port
        return weakref.ref(owner)
    original_owner = create()
    gc.collect()
    assert original_owner() is None
