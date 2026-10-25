from dataclasses import replace
import pytest
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_authorized_retry_graded_retry_real import graded_rig
from grading.integration.paper_retry_grading import GradedRetryState


def test_first_rechecks_runtime_after_paper_issuer_callback():
    root,plan,issuer,fresh,runtime,store = _setup_two()
    mutation=[]
    def drift(_plan):
        if fresh.calls >= 2 and not mutation:
            runtime['Q2'].runtime_record=replace(runtime['Q2'].runtime_record,
                implementation_ref='REVOKED-IMPLEMENTATION-Q2')
            mutation.append(True)
    issuer.action = drift
    out = root.execute(plan=plan)
    assert mutation
    assert out.state != 'COMPLETE', (out.state,store.claims)


def test_retry_rechecks_runtime_after_paper_issuer_callback_before_CAS():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,issuer,fresh = graded_rig()
    inventory=graded._executor._handoff._installation.runtime._operation
    runtime=inventory.__func__.__closure__[0].cell_contents
    assert 'Q2' in runtime
    changed=[]
    def revoke_inside_paper_read(_plan):
        # Q2 has just been successfully confirmed by current-question authority.
        # The *next installed paper issuer callback* changes the independent
        # approved runtime policy while it returns the unchanged paper relation.
        if fresh.calls >= 2 and not changed:
            runtime['Q2'].runtime_record=replace(runtime['Q2'].runtime_record,
                implementation_ref='REVOKED-RETRY-RUNTIME-Q2')
            changed.append(True)
    issuer.action = revoke_inside_paper_read
    out=graded.execute_and_commit(plan=plan)
    assert changed, 'Reviewer callback was not reached'
    assert store.commits == 0, ('CAS after changed installed runtime policy',store.commits,out.state)
    assert out.state is GradedRetryState.UNKNOWN


def test_baseline_retry_real_positive():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,issuer,fresh = graded_rig()
    out = graded.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.CAS_ACKNOWLEDGED
    assert store.commits==1


def test_first_rejects_runtime_revocation_during_Q2_confirmation():
    root,plan,issuer,fresh,runtime,store=_setup_two()
    def revoke(_paper,question,_scope):
        if question.question_id=='Q2':
            runtime['Q2'].runtime_record=replace(runtime['Q2'].runtime_record,
                implementation_ref='REVOKED-WITHIN-CONFIRM')
    fresh.action=revoke
    out=root.execute(plan=plan)
    assert out.state != 'COMPLETE'
    assert out.result is None and store.claims==1


def test_first_baseline_two_question_positive():
    root,plan,issuer,fresh,runtime,store=_setup_two()
    out=root.execute(plan=plan)
    assert out.state=='COMPLETE' and out.result is not None
    assert store.claims==2


@pytest.mark.parametrize('field,new_value', [
    ('approval_ref', 'REVOKED-APPROVAL-Q2'),
    ('runtime_version', '2'),
    ('implementation_ref', 'REVOKED-IMPLEMENTATION-Q2'),
])
def test_q2_current_question_changes_independent_runtime_before_f25(field, new_value):
    root, plan, issuer, fresh, runtime, store = _setup_two()
    touched=[]
    def change(_paper, question, _scope):
        if question.question_id == 'Q2' and not touched:
            runtime['Q2'].runtime_record = replace(runtime['Q2'].runtime_record,
                                                    **{field: new_value})
            touched.append(True)
    fresh.action=change
    out=root.execute(plan=plan)
    assert touched
    assert store.claims==1
    assert out.result is None and out.state in ('INCOMPLETE', 'DENIED', 'UNAVAILABLE')
    assert len(out.completed)==1 and len(out.observed_reservations)==1


@pytest.mark.parametrize('field,new_value', [
    ('approval_ref', 'REVOKED-RETRY-APPROVAL-Q2'),
    ('runtime_version', '2'),
    ('implementation_ref', 'REVOKED-RETRY-IMPLEMENTATION-Q2'),
])
def test_retry_q2_confirmation_changed_runtime_never_commits(field, new_value):
    graded,plan,physical,auth,academic,atomic,store,unused_f25,issuer,fresh=graded_rig()
    inventory=graded._executor._handoff._installation.runtime._operation
    runtime=inventory.__func__.__closure__[0].cell_contents
    seen=[]
    def change(_paper,question,_scope):
        if question.question_id == 'Q2' and not seen:
            runtime['Q2'].runtime_record=replace(runtime['Q2'].runtime_record,
                                                 **{field:new_value})
            seen.append(True)
    fresh.action=change
    out=graded.execute_and_commit(plan=plan)
    assert seen
    assert physical.claims==2 and atomic.calls==2
    assert store.commits==0 and out.state is GradedRetryState.UNKNOWN
    assert out.physical is not None and len(out.physical.claimed)==2


def test_q2_physical_claim_callback_changes_runtime_withholds_complete():
    ready={};fired=[]
    def drift(request):
        if request.scope.question_id=='Q2':
            runtime=ready['runtime']
            runtime['Q2'].runtime_record=replace(runtime['Q2'].runtime_record,
                    implementation_ref='REVOKED-F25-Q2')
            fired.append(True)
    root,plan,issuer,fresh,runtime,store=_setup_two(on_physical_claim=drift)
    ready['runtime']=runtime
    out=root.execute(plan=plan)
    assert fired and store.claims==2
    assert out.state=='INDETERMINATE' and out.result is None
    assert len(out.observed_reservations)==2
    assert [x.question_id for x in out.completed]==['Q1']
    assert out.failure_kind=='UNKNOWN'


def test_q1_confirm_changes_runtime_before_any_physical_effect():
    root,plan,issuer,fresh,runtime,store=_setup_two()
    seen=[]
    def revoke(_paper,question,_scope):
        if question.question_id=='Q1':
            runtime['Q1'].runtime_record=replace(runtime['Q1'].runtime_record,
                approval_ref='REVOKED-Q1')
            seen.append(True)
    fresh.action=revoke
    out=root.execute(plan=plan)
    assert seen and store.claims==0 and out.result is None
    assert not out.observed_reservations


def test_q1_f25_changes_runtime_preserves_single_physical_claim():
    ready={}; seen=[]
    def drift(request):
        if request.scope.question_id=='Q1':
            runtime=ready['runtime']
            runtime['Q1'].runtime_record=replace(runtime['Q1'].runtime_record,
                implementation_ref='REVOKED-F25-Q1')
            seen.append(True)
    root,plan,issuer,fresh,runtime,store=_setup_two(on_physical_claim=drift)
    ready['runtime']=runtime
    out=root.execute(plan=plan)
    assert seen and store.claims==1
    assert out.result is None and out.state=='INDETERMINATE'
    assert len(out.observed_reservations)==1 and out.failure_kind=='UNKNOWN'
