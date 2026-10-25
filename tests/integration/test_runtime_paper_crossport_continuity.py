"""Verify runtime and paper issuer callbacks remain independent under mutation.

In-memory callback tests do not establish distributed revocation timing."""
from dataclasses import replace
import pytest
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_authorized_retry_graded_retry_real import graded_rig
from grading.integration.paper_retry_grading import GradedRetryState


def _hook_runtime_port(port, callback):
    original=type(port)
    class ObservableRuntime(original):
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            result=super().resolve_approved_runtime(scope=scope, capability_ref=capability_ref,
                  policy_id=policy_id,policy_version=policy_version)
            callback(scope)
            return result
    port.__class__=ObservableRuntime


def _first_at_stage(stage):
    root,plan,issuer,fresh,runtime,store=_setup_two()
    events=[]
    def change_issuer(scope):
        if scope.question_id!='Q2' or fresh.calls<2 or events:
            return
        if (stage=='pre_f25' and store.claims==1) or (stage=='post_f25' and store.claims==2):
            issuer.relation=replace(issuer.relation,approval_revision='CHANGED-BY-INSTALLED-RUNTIME')
            events.append((stage,issuer.calls,store.claims))
    _hook_runtime_port(runtime['Q2'],change_issuer)
    out=root.execute(plan=plan)
    return out,store,events,issuer,fresh


@pytest.mark.parametrize('stage',['pre_f25','post_f25'])
def test_first_runtime_callback_changes_independent_paper_issuer(stage):
    out,store,events,issuer,fresh=_first_at_stage(stage)
    assert events, 'Injected real installed runtime callback was not reached'
    if stage=='pre_f25':
        assert store.claims==1, ('Q2 attempt reservation should be blocked by a changed issuer',store.claims,events,out.state)
    else:
        assert store.claims==2, ('Q2 physical attempt was already reserved',store.claims,events,out.state)
    assert out.result is None and out.state!='COMPLETE', (stage,out.state,events)


def test_control_unmodified_first():
    root,plan,issuer,fresh,runtime,store=_setup_two()
    out=root.execute(plan=plan)
    assert out.state=='COMPLETE' and store.claims==2


def test_retry_runtime_callback_changes_independent_paper_issuer():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,issuer,fresh=graded_rig()
    inventory=graded._executor._handoff._installation.runtime._operation
    runtime=inventory.__func__.__closure__[0].cell_contents
    events=[]
    def change_issuer(scope):
        if scope.question_id=='Q2' and fresh.calls>=2 and not events:
            issuer.relation=replace(issuer.relation,approval_revision='CHANGED-RETRY-PAPER')
            events.append((issuer.calls,fresh.calls,physical.claims))
    _hook_runtime_port(runtime['Q2'],change_issuer)
    out=graded.execute_and_commit(plan=plan)
    assert events, 'Retry runtime port not reached'
    assert store.commits==0, ('scored CAS under changed issuer',out.state,events)
    assert out.state is GradedRetryState.UNKNOWN


def test_control_unmodified_retry():
    graded,plan,physical,auth,academic,atomic,store,unused_f25,issuer,fresh=graded_rig()
    out=graded.execute_and_commit(plan=plan)
    assert out.state is GradedRetryState.CAS_ACKNOWLEDGED and store.commits==1
