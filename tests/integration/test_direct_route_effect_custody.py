"""External hostile verification: current-route reread after last dependency check.
No changes to production source. Execute from repository root with PYTHONPATH=src:.
"""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, connected_regrade, POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_direct_provider_route_connected import install
from tests.integration.test_family_retry_accounting import connected_family_retry

class MutateOnSecondRead(dict):
    def __init__(self, base, target, name):
        super().__init__(base)
        self.target=target
        self.name=name
        self.reads=0
    def __getitem__(self, key):
        self.reads += 1
        if self.reads == 2:
            object.__setattr__(self.target, self.name, object())
        return super().__getitem__(key)

@pytest.mark.parametrize('field', ['_provider','_model_answer_source'])
def test_second_approval_read_mutation_must_not_reach_avoidable_first_f25(field):
    cas, plan, _, physical, _, f25, old, storage, conditional = connected('DIRECT')
    executor=cas._custody._executor
    direct=executor._resolve(plan=plan).operations[0].evaluator
    route, source, sender, writer=install(executor,plan,'FIRST')
    src=MutateOnSecondRead(source.grants, direct, field)
    source.grants=src
    lifecycle=ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert src.reads >= 2, 'did not contact second independent approval read'
    # Stronger pre-effect custody: do not consume claim when callback mutates installed evaluator.
    assert physical.claims == 0, (field,physical.claims,outcome.execution.state)
    assert storage.commits == 0 and sender.dispatched == [] and writer.events == []

@pytest.mark.parametrize('field', ['_provider','_model_answer_source'])
def test_second_approval_read_mutation_must_not_reach_avoidable_regrade_f25(field):
    lifecycle,plan,physical,backend,f25,old,storage,conditional,prior,f57=connected_regrade()
    executor=lifecycle._cas._custody._executor
    direct=executor._resolve(plan=plan).operations[0].evaluator
    route,source,sender,writer=install(executor,plan,'REGRADE')
    src=MutateOnSecondRead(source.grants,direct,field)
    source.grants=src
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.REGRADE,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.REGRADE)
    assert src.reads >= 2
    assert physical.claims == 0, (field,physical.claims,outcome.execution.state)
    assert sender.dispatched == [] and writer.events == []

def test_positive_first_route_requires_two_reads_and_scores():
    cas,plan,_,physical,_,f25,old,storage,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert outcome.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert len(source.calls)>=2 and physical.claims==1
    assert len(sender.dispatched)==len(writer.events)==storage.commits==1

def test_negative_revoked_second_approval_read_denied_without_vendor():
    cas,plan,_,physical,_,f25,old,storage,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    source.revoke_on_read=2
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
        legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert outcome.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==0 and sender.dispatched==[] and writer.events==[] and storage.commits==0

def test_retry_third_approval_read_mutation_must_not_reach_avoidable_f25():
    from tests.integration.test_family_retry_accounting import connected_family_retry
    retry, plan, physical, _, storage, _, old = connected_family_retry('DIRECT')
    executor=retry._executor
    direct=executor._resolve(plan=plan).operations[0].evaluator
    route, source, sender, writer=install(executor,plan,'RETRY')
    class MutateThird(dict):
        reads=0
        def __getitem__(self,key):
            self.reads+=1
            if self.reads==3:
                object.__setattr__(direct,'_model_answer_source',object())
            return super().__getitem__(key)
    src=MutateThird(source.grants);source.grants=src
    root,_=_root(retry=retry,plan=plan,kinds=(PaperOperationKind.RETRY,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.RETRY)
    assert src.reads>=3
    assert physical.claims==0,(src.reads,physical.claims,outcome.execution.state)
    assert sender.dispatched == [] and writer.events == [] and storage.commits==0

def test_positive_retry_original_absence_with_valid_route():
    from tests.integration.test_family_retry_accounting import connected_family_retry
    from grading.integration.paper_retry_grading import GradedRetryState
    retry, plan, physical, _, storage, _, old = connected_family_retry('DIRECT')
    route,source,sender,writer=install(retry._executor,plan,'RETRY')
    root,_=_root(retry=retry,plan=plan,kinds=(PaperOperationKind.RETRY,))
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.RETRY)
    assert outcome.execution.state is GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims==storage.commits==len(sender.dispatched)==len(writer.events)==1


"""DIRECT route custody through real family-operation effects (synthetic ports)."""
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_direct_provider_route_connected import install
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind
from grading.providers.canonical_transport import CanonicalProviderReply
from tests.integration.test_direct_text_semantic_evaluator_regression import _provider_response

class RogueSender:
    def __init__(self): self.dispatched=[]
    def deliver(self, *, dispatch):
        self.dispatched.append(dispatch)
        i=dispatch.identity
        return CanonicalProviderReply(dispatch.dispatch_ref,i.operation_ref,i.event_ref,
          i.logical_evaluation_ref,i.attempt_id,i.request_ref,dispatch.request_sha256,
          i.provider_id,i.model_id,i.configuration_ref,_provider_response())

def setup(poison=False):
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    rogue=RogueSender()
    if poison:
        class PoisonDict(dict):
            def __getitem__(self,key):
                # Happens inside current approval callback; frozen/slot attributes
                # on the route do not guarantee source-independent custody.
                object.__setattr__(route,'_deliver',rogue.deliver)
                return super().__getitem__(key)
        source.grants=PoisonDict(source.grants)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
      legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    return root,plan,physical,store,sender,rogue,writer

def test_hostile_approval_source_must_not_replace_installed_sender_before_f25():
    root,plan,physical,store,legitimate,rogue,writer=setup(poison=True)
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims==0, (out.execution.state,physical.claims,store.commits,len(legitimate.dispatched),len(rogue.dispatched))
    assert len(rogue.dispatched)==0

def test_legitimate_sender_remains_functional():
    root,plan,physical,store,legitimate,rogue,writer=setup(poison=False)
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and store.commits==1
    assert len(legitimate.dispatched)==1 and len(rogue.dispatched)==0

class RogueAccounting:
    def __init__(self):self.events=[]
    def record_outcome(self, *, event):
        from grading.providers.attempt_accounting import ProviderAccountingReceipt
        self.events.append(event)
        return ProviderAccountingReceipt(event.identity.event_ref,event.identity.operation_ref,event.status)

def test_hostile_approval_source_must_not_replace_accounting_writer_before_f25():
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    rogue=RogueAccounting()
    class PoisonDict(dict):
        def __getitem__(self,key):
            object.__setattr__(route,'_write',rogue.record_outcome)
            return super().__getitem__(key)
    source.grants=PoisonDict(source.grants)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
      legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims==0, (out.execution.state,physical.claims,store.commits,len(writer.events),len(rogue.events))
    assert len(rogue.events)==0

def test_official_family_input_source_must_not_replace_entire_route_before_f25():
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    executor=cas._custody._executor
    original_route,original_src,original_sender,original_writer=install(executor,plan,'FIRST')
    replacement_route,replacement_src,replacement_sender,replacement_writer=install(executor,plan,'FIRST')
    object.__setattr__(executor,'_direct_route',original_route)
    original_resolve=executor._resolve
    def swapping_source(*,plan):
        object.__setattr__(executor,'_direct_route',replacement_route)
        return original_resolve(plan=plan)
    object.__setattr__(executor,'_resolve',swapping_source)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
      legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert physical.claims==0, (out.execution.state,physical.claims,store.commits,
           len(original_sender.dispatched),len(replacement_sender.dispatched))
    assert len(replacement_sender.dispatched)==0



def test_current_approval_read_cannot_switch_sender_after_original_f25():
    """A revoked installation after a physical claim cannot redirect vendor bytes."""
    cas, plan, _, physical, _, f25, old, storage, conditional = connected('DIRECT')
    executor = cas._custody._executor
    route, source, sender, writer = install(executor, plan, 'FIRST')
    rogue = RogueSender()

    class LateSwitch(dict):
        reads = 0
        def __getitem__(self, key):
            self.reads += 1
            if self.reads == 4:  # physical attempt claim has been claimed, before vendor delivery.
                object.__setattr__(route, '_deliver', rogue.deliver)
            return super().__getitem__(key)

    source.grants = LateSwitch(source.grants)
    lifecycle = ProductionPaperLifecycle(
        cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10,
    )
    root, _ = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,))
    outcome = root.execute(request=plan.request, kind=PaperOperationKind.FIRST)
    assert len(rogue.dispatched) == 0
    assert storage.commits == 0
    assert outcome.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims <= 1  # No second physical attempt after ambiguous effect.
