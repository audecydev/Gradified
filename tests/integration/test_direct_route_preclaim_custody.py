"""Verify DIRECT provider installation custody across original-attempt claims and callbacks."""
from dataclasses import replace
import pytest
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_direct_provider_route_connected import install


def setup(mutate):
    cas,plan,_,physical,_,f25,old,storage,conditional=connected('DIRECT')
    executor=cas._custody._executor
    direct=executor._resolve(plan=plan).operations[0].evaluator
    route,source,sender,writer=install(executor,plan,'FIRST')
    installed=direct._model_answer_source
    fresh=type(installed)(installed.answer)
    class LaterApprovalRead(dict):
        reads=0
        def __getitem__(self,key):
            self.reads += 1
            if mutate and self.reads == 4:
                object.__setattr__(direct,'_model_answer_source',fresh)
            return super().__getitem__(key)
    src=LaterApprovalRead(source.grants)
    source.grants=src
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
            legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    return root,plan,physical,storage,source,sender,writer,direct,installed,fresh,src


def test_valid_original_installation_scored_positive():
    root,plan,physical,store,source,sender,writer,direct,installed,fresh,src=setup(False)
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert outcome.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims==1 and store.commits==1 and len(sender.dispatched)==1
    assert direct._model_answer_source is installed


def test_post_f25_source_swap_must_not_commit_original_score():
    root,plan,physical,store,source,sender,writer,direct,installed,fresh,src=setup(True)
    outcome=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert src.reads>=4
    assert direct._model_answer_source is fresh
    assert physical.claims==1
    # It is unsafe to score from a replaced post-claim academic source even
    # if it deliberately returns identical content. Correct response is UNKNOWN.
    assert store.commits==0, (str(outcome.execution.state),store.commits,len(sender.dispatched),len(writer.events))
    assert outcome.execution.state is not PaperLifecycleState.CAS_ACKNOWLEDGED


from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from grading.integration.production_paper_operations import PaperOperationKind
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_direct_provider_route_connected import install


def test_known_wrong_canonical_digest_must_be_refused_before_avoidable_f25():
    cas,plan,_,physical,_,f25,old,store,conditional=connected('DIRECT')
    route,source,sender,writer=install(cas._custody._executor,plan,'FIRST')
    original=source.grants[('Q1','FIRST')]
    source.grants[('Q1','FIRST')]=replace(original,request_sha256='0'*64)
    lifecycle=ProductionPaperLifecycle(cas=cas,permission_source=f25.f57_source,
       legal_policy=POLICY,max_identifier_characters=128,max_questions=10)
    root,_=_root(lifecycle=lifecycle,plan=plan,kinds=(PaperOperationKind.FIRST,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert len(sender.dispatched)==len(writer.events)==store.commits==0
    assert physical.claims==0, ('Avoidable attempt reservation on provably inconsistent approved digest',physical.claims,out.execution.state)


def test_direct_model_answer_is_materialized_only_before_f25():
    # The installed academic reader is not a post-claim provider dependency:
    # a source which refuses to read after physical attempt claim still permits valid grading.
    from grading.integration.paper_lifecycle import PaperLifecycleState
    cas, plan, _, physical, _, f25, old, store, conditional = connected('DIRECT')
    executor = cas._custody._executor
    route, source, sender, writer = install(executor, plan, 'FIRST')
    evaluator = executor._resolve(plan=plan).operations[0].evaluator
    installed = evaluator._model_answer_source
    class BeforeClaimOnly:
        calls = 0
        def resolve_model_answer(self, *, grading_spec_ref, question_id):
            self.calls += 1
            if physical.claims:
                raise AssertionError('Original academic model-answer reader invoked after grading-attempt')
            return installed.resolve_model_answer(grading_spec_ref=grading_spec_ref,
                                                   question_id=question_id)
    source_reader = BeforeClaimOnly()
    object.__setattr__(evaluator, '_model_answer_source', source_reader)
    lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    root,_ = _root(lifecycle=lifecycle, plan=plan, kinds=(PaperOperationKind.FIRST,))
    out = root.execute(request=plan.request,kind=PaperOperationKind.FIRST)
    assert out.execution.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert source_reader.calls == 1
    assert physical.claims == store.commits == len(sender.dispatched) == 1


def test_retry_wrong_digest_never_consumes_f25():
    from tests.integration.test_family_retry_accounting import connected_family_retry
    from grading.integration.paper_retry_grading import GradedRetryState
    retry,plan,physical,_,store,_,old=connected_family_retry('DIRECT')
    route,source,sender,writer=install(retry._executor,plan,'RETRY')
    source.grants[('Q1','RETRY')]=replace(
        source.grants[('Q1','RETRY')], request_sha256='0'*64)
    root,_ = _root(retry=retry,plan=plan,kinds=(PaperOperationKind.RETRY,))
    out=root.execute(request=plan.request,kind=PaperOperationKind.RETRY)
    assert out.execution.state is not GradedRetryState.CAS_ACKNOWLEDGED
    assert physical.claims == 0 and len(sender.dispatched) == 0
    assert len(writer.events) == 0
