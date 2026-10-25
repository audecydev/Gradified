"""Verify NUMERIC family execution rejects equivalent-looking but invalid callback types."""
import pytest
from tests.integration.test_paper_family_evaluation import _mixed, _direct
from grading.integration.paper_family_evaluation import (NumericQuestionEvaluation, PaperFamilyEvaluationDenied, evaluate_supported_paper_questions)
from grading.contracts.paper_aggregation import GradingSpecRef


def _with_mutator(mutate):
    context, evidence, paper, operations, provider = _mixed()
    direct, numeric = operations
    class Binding:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            mutate(context, direct)
            return numeric.binding_source.resolve_numeric_binding(grading_spec_ref=grading_spec_ref, question_id=question_id)
    new_operations=(direct,NumericQuestionEvaluation(numeric.authority,Binding(),numeric.authority_source))
    def go():
        return evaluate_supported_paper_questions(context=context,evidence=evidence,paper_authority=paper,operations=new_operations)
    return context,direct,provider,go


def test_float_for_int_grading_spec_version_must_not_pass_original_continuity():
    def mut(ctx,direct):
        original=ctx.grading_spec_ref
        forged=object.__new__(GradingSpecRef)
        object.__setattr__(forged,'id',original.id)
        object.__setattr__(forged,'version',float(original.version))
        object.__setattr__(ctx,'grading_spec_ref',forged)
    ctx, direct, provider,go=_with_mutator(mut)
    with pytest.raises(PaperFamilyEvaluationDenied):
        go()
    assert provider.requests==[]


def test_bool_for_int_grading_spec_version_must_not_pass_original_continuity():
    def mut(ctx,direct):
        original=ctx.grading_spec_ref
        forged=object.__new__(GradingSpecRef)
        object.__setattr__(forged,'id',original.id)
        object.__setattr__(forged,'version',True)
        object.__setattr__(ctx,'grading_spec_ref',forged)
    ctx, direct, provider,go=_with_mutator(mut)
    with pytest.raises(PaperFamilyEvaluationDenied):
        go()
    assert provider.requests==[]


def test_subclass_direct_attempt_id_must_not_pass_original_continuity():
    class ForeignString(str): pass
    def mut(ctx,direct):
        object.__setattr__(direct,'evaluation_attempt_id',ForeignString(direct.evaluation_attempt_id))
    ctx, direct, provider,go=_with_mutator(mut)
    with pytest.raises(PaperFamilyEvaluationDenied):
        go()
    assert provider.requests==[]


def test_legitimate_mixed_positive():
    ctx,direct,prov,go=_with_mutator(lambda *_:None)
    result=go()
    assert len(result.questions)==2 and len(prov.requests)==1


def test_legitimate_direct_positive():
    ctx,ev,paper,op,provider=_direct()
    result=evaluate_supported_paper_questions(context=ctx,evidence=ev,paper_authority=paper,operations=(op,))
    assert len(result.questions)==1 and len(provider.requests)==1
