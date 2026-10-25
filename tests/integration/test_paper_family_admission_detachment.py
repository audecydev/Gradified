"""Verify admitted paper-family evidence is detached from mutable external sources."""
import pytest

from grading.integration.paper_family_evaluation import (
    DirectQuestionEvaluation, PaperFamilyEvaluationDenied, evaluate_supported_paper_questions,
)
from tests.integration.test_paper_family_evaluation import _direct, _mixed
from tests.integration.test_direct_text_semantic_evaluator_hostile import (
    _Provider, _ModelAnswerSource, _answer, _evaluator,
)


class ForeignEquality:
    def __init__(self):
        self.calls = 0

    def __eq__(self, other):
        self.calls += 1
        raise RuntimeError('FOREIGN COMPARISON EXECUTED')


@pytest.mark.parametrize('field', ['expected_question', 'evidence_submission', 'context_spec'])
def test_malformed_nested_field_refused_before_foreign_equality(field):
    context, evidence, paper, op, provider = _direct()
    poison = ForeignEquality()
    if field == 'expected_question':
        object.__setattr__(paper.expected_questions[0], 'question_id', poison)
    elif field == 'evidence_submission':
        object.__setattr__(evidence, 'submission_ref', poison)
    else:
        object.__setattr__(context, 'grading_spec_ref', poison)

    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
                                           paper_authority=paper, operations=(op,))
    assert poison.calls == 0
    assert provider.requests == []


def test_callback_transient_question_substitution_cannot_produce_positive_score():
    context, evidence, paper, op, _ = _direct()
    authority = op.authority
    original = authority.question_text

    class SwappingSource(_ModelAnswerSource):
        def resolve_model_answer(self, **kwargs):
            object.__setattr__(authority, 'question_text', 'UNAUTHORIZED QUESTION SUBSTITUTION')
            return super().resolve_model_answer(**kwargs)

    class RestoringProvider(_Provider):
        def evaluate(self, *, request):
            object.__setattr__(authority, 'question_text', original)
            return super().evaluate(request=request)

    provider = RestoringProvider()
    source = SwappingSource(_answer(authority=authority))
    evaluator, _, _ = _evaluator(authority=authority, source=source, provider=provider)
    modified_op = DirectQuestionEvaluation(authority, evaluator, op.evaluation_attempt_id)
    try:
        evaluate_supported_paper_questions(context=context, evidence=evidence,
                                           paper_authority=paper, operations=(modified_op,))
    except PaperFamilyEvaluationDenied:
        pass
    else:
        assert provider.requests and all(r.question_text == original for r in provider.requests), (
            'Positive grading permitted provider contact with an unadmitted question'
        )
    assert authority.question_text == original


def test_valid_direct_control():
    context, evidence, paper, op, provider = _direct()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence,
                                                paper_authority=paper, operations=(op,))
    assert result.paper_score is not None and len(provider.requests) == 1


def test_valid_mixed_control():
    context, evidence, paper, ops, provider = _mixed()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence,
                                                paper_authority=paper, operations=ops)
    assert len(result.questions) == 2 and len(provider.requests) == 1
