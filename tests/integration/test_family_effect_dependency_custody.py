"""Verify provider callbacks cannot mutate already admitted DIRECT family dependencies."""
from tests.integration.test_whole_paper_family_execution import rig
from tests.integration.test_direct_text_semantic_evaluator_hostile import _Provider


def test_f25_callback_cannot_swap_installed_direct_provider_before_scoring():
    executor, plan, permission, physical, backend, conditional, provider, source = rig()
    evaluator = source.inputs.operations[0].evaluator
    replacement = _Provider()
    authentic_claim = backend.claim_bound_fresh
    changes = []

    def claim_and_swap(*, preparation):
        result = authentic_claim(preparation=preparation)
        object.__setattr__(evaluator, '_provider', replacement)
        changes.append(True)
        return result

    backend.claim_bound_fresh = claim_and_swap
    out = executor.execute_first(plan=plan, permission=permission)
    assert changes, 'attack must reach real effect callback'
    assert not replacement.requests, 'unadmitted replacement DIRECT provider must not receive grading data'
    assert out.state != 'COMPLETE', 'source must not silently complete scoring after executor dependency changed'


def test_f25_callback_cannot_swap_installed_model_answer_source_before_scoring():
    executor, plan, permission, physical, backend, conditional, provider, source = rig()
    evaluator = source.inputs.operations[0].evaluator
    original = evaluator._model_answer_source
    replacement = type(original)(original.answer)
    authentic_claim = backend.claim_bound_fresh
    changes = []

    def claim_and_swap(*, preparation):
        result = authentic_claim(preparation=preparation)
        object.__setattr__(evaluator, '_model_answer_source', replacement)
        changes.append(True)
        return result

    backend.claim_bound_fresh = claim_and_swap
    out = executor.execute_first(plan=plan, permission=permission)
    assert changes
    assert not replacement.calls, 'unadmitted model answer source must not be used'
    assert out.state != 'COMPLETE'


def test_control_unmodified_provider_and_model_answer_source_complete():
    executor, plan, permission, physical, backend, conditional, provider, source = rig()
    original = source.inputs.operations[0].evaluator._model_answer_source
    out = executor.execute_first(plan=plan, permission=permission)
    assert out.state == 'COMPLETE'
    assert len(provider.requests) == 1
    assert len(original.calls) == 1
    assert physical.claims == 1


def test_family_first_scored_cas_must_not_commit_using_swapped_provider():
    from tests.integration.test_family_first_scored_cas import connected
    from grading.integration.whole_paper_cas import PaperCASState
    service, plan, permission, physical, backend, f25, provider, store, conditional = connected('DIRECT')
    executor = service._custody._executor
    evaluator = executor._resolve(plan=plan).operations[0].evaluator
    replacement = _Provider()
    old = backend.claim_bound_fresh
    touched = []

    def claim_and_swap(*, preparation):
        result = old(preparation=preparation)
        object.__setattr__(evaluator, '_provider', replacement)
        touched.append(True)
        return result

    backend.claim_bound_fresh = claim_and_swap
    out = service.execute_and_commit(plan=plan, permission=permission)
    assert touched, 'attack callback must actually run'
    assert not replacement.requests, 'foreign installed provider must not be contacted'
    assert store.commits == 0 and out.state is not PaperCASState.COMMITTED

"""Regression of first foreign comparison before source admission."""
from dataclasses import replace
from tests.integration.test_whole_paper_family_execution import rig

class HostileEq:
    calls = 0
    def __eq__(self, other):
        type(self).calls += 1
        raise RuntimeError('foreign callback executed before structural admission')
    def __ne__(self, other):
        type(self).calls += 1
        raise RuntimeError('foreign callback executed before structural admission')

def test_control_admitted_first_real_f25_scoring():
    ex,plan,permission,physical,backend,conditional,provider,_=rig()
    out=ex.execute_first(plan=plan,permission=permission)
    assert out.state=='COMPLETE' and out.result is not None and physical.claims==1
    assert len(provider.requests)==1

def test_hostile_context_precomparison_must_not_execute_unadmitted_equality():
    ex,plan,permission,physical,backend,conditional,provider,source=rig()
    poisoned = replace(source.inputs.context)
    object.__setattr__(poisoned, "grading_run_id", HostileEq())
    source.inputs=replace(source.inputs,context=poisoned)
    HostileEq.calls=0
    out=ex.execute_first(plan=plan,permission=permission)
    assert out.result is None and physical.claims==0 and len(provider.requests)==0
    assert HostileEq.calls == 0, 'foreign comparison must never execute before exact-type admission'
