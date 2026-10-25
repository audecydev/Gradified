"""Adversarial regressions for DIRECT provider source mutation during controlled execution."""
import pytest
from tests.integration.test_family_first_scored_cas import connected,POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_direct_provider_route_connected import install
from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from grading.integration.production_paper_operations import PaperOperationKind


def test_route_source_can_change_direct_evaluator_installation_before_f25_without_detection():
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    executor=cas._custody._executor
    real=executor._resolve(plan=plan).operations[0].evaluator
    original_provider=real._provider
    route,source,sender,writer=install(executor,plan,'FIRST')
    class PoisonDict(dict):
        def __getitem__(self,k):
            object.__setattr__(real,'_provider',object())
            return super().__getitem__(k)
    source.grants=PoisonDict(source.grants)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    # Production admission must not perform any physical attempt claim after its
    # separately installed route reader mutates a previously resolved evaluator.
    assert physical.claims==0, f'mutated evaluator reached first F25 claim; status={out.execution.state} F25={physical.claims}'


def test_authorized_direct_first_still_proceeds_with_original_installation():
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims==1 and len(sender.dispatched)==1 and store.commits==1

@pytest.mark.parametrize('field', ['_model_answer_source', '_provider'])
def test_route_source_mutation_of_resolved_direct_dependencies_must_block_before_f25(field):
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    executor=cas._custody._executor
    real=executor._resolve(plan=plan).operations[0].evaluator
    route,source,sender,writer=install(executor,plan,'FIRST')
    class MutatingApprovalStore(dict):
        def __getitem__(self,k):
            object.__setattr__(real,field,object())
            return super().__getitem__(k)
    source.grants=MutatingApprovalStore(source.grants)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims == 0, (field, out.execution.state, physical.claims)


def test_retry_source_mutation_of_resolved_model_answer_must_block_before_first_f25():
    from tests.integration.test_family_retry_accounting import connected_family_retry
    from tests.integration.test_production_paper_operations import _root
    retry,plan,physical,_,store,_,old=connected_family_retry('DIRECT')
    executor=retry._executor
    real=executor._resolve(plan=plan).operations[0].evaluator
    route,source,sender,writer=install(executor,plan,'RETRY')
    class PoisonDict(dict):
        def __getitem__(self,k):
            object.__setattr__(real,'_model_answer_source',object())
            return super().__getitem__(k)
    source.grants=PoisonDict(source.grants)
    root,_=_root(retry=retry,plan=plan,kinds=(PaperOperationKind.RETRY,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.RETRY)
    assert physical.claims==0, (out.execution.state,physical.claims)

def test_regrade_route_source_mutation_of_evaluator_installation_must_block_before_f25():
    from tests.integration.test_family_first_scored_cas import connected_regrade
    lifecycle,plan,physical,backend,f25,old,storage,conditional,prior,f57=connected_regrade()
    executor=lifecycle._cas._custody._executor
    real=executor._resolve(plan=plan).operations[0].evaluator
    route,source,sender,writer=install(executor,plan,'REGRADE')
    class PoisonDict(dict):
        def __getitem__(self,k):
            object.__setattr__(real,'_model_answer_source',object())
            return super().__getitem__(k)
    source.grants=PoisonDict(source.grants)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.REGRADE,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.REGRADE)
    assert physical.claims==0, (out.execution.state,physical.claims)
