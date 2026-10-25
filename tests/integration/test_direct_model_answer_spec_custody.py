"""Verify model-answer source callbacks cannot redirect an already admitted grading specification."""
import pytest
from grading.semantic_evaluator import DirectTextSemanticBindingError
from grading.integration.paper_family_evaluation import (
    DirectQuestionEvaluation, evaluate_supported_paper_questions,
)
from tests.integration.test_paper_family_evaluation import _direct, _mixed
from tests.integration.test_direct_text_semantic_evaluator_hostile import (
    _MaterializedModelAnswer, _Provider, _evaluator, _answer, _ModelAnswerSource,
)


def _exercise(source):
    ctx, evidence, paper, original, _ = _direct()
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=original.authority, source=source, provider=provider)
    operation = DirectQuestionEvaluation(original.authority, evaluator, original.evaluation_attempt_id)
    return ctx, original, provider, lambda: evaluate_supported_paper_questions(
        context=ctx, evidence=evidence, paper_authority=paper, operations=(operation,))


@pytest.mark.parametrize('new_version', [1.0, True])
def test_model_answer_source_cannot_retype_detached_spec_and_still_score(new_version):
    class AlteringSource(_ModelAnswerSource):
        def resolve_model_answer(self, *, grading_spec_ref, question_id):
            object.__setattr__(grading_spec_ref, 'version', new_version)
            return super().resolve_model_answer(grading_spec_ref=grading_spec_ref, question_id=question_id)
    ctx, original, provider, grade = _exercise(AlteringSource(_answer()))
    with pytest.raises((DirectTextSemanticBindingError,)):
        grade()
    assert len(provider.requests) == 0, 'Source changed a detached spec to an invalid version before a paid provider request'
    assert type(ctx.grading_spec_ref.version) is int
    assert type(original.authority.grading_spec_ref.version) is int


def test_model_answer_source_cannot_redirect_detached_academic_spec_and_score():
    class RedirectingSource:
        def resolve_model_answer(self, *, grading_spec_ref, question_id):
            object.__setattr__(grading_spec_ref, 'id', 'FOREIGN-ACADEMIC-SPEC')
            return _MaterializedModelAnswer(grading_spec_ref=grading_spec_ref,
                 question_id=question_id, content='FOREIGN ANSWER FOR DIFFERENT SPEC')
    ctx, original, provider, grade = _exercise(RedirectingSource())
    with pytest.raises((DirectTextSemanticBindingError,)):
        grade()
    assert len(provider.requests) == 0, 'Foreign model-answer basis reached paid provider'
    assert ctx.grading_spec_ref.id != 'FOREIGN-ACADEMIC-SPEC'
    assert original.authority.grading_spec_ref.id != 'FOREIGN-ACADEMIC-SPEC'


def test_valid_direct_control():
    ctx, ev, paper, op, provider = _direct()
    result = evaluate_supported_paper_questions(context=ctx, evidence=ev, paper_authority=paper, operations=(op,))
    assert len(result.questions) == 1
    assert len(provider.requests) == 1


def test_valid_mixed_control():
    ctx, ev, paper, ops, provider = _mixed()
    result = evaluate_supported_paper_questions(context=ctx, evidence=ev, paper_authority=paper, operations=ops)
    assert len(result.questions) == 2
    assert len(provider.requests) == 1
