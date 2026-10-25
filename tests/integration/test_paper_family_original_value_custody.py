"""Verify admitted academic evidence and grading source values survive hostile callbacks."""

"""Independent source-external identity custody probes on immutable-wrapper hostile in-process callback model."""
from dataclasses import replace
import pytest
from tests.integration.test_paper_family_evaluation import _mixed
from grading.integration.paper_family_evaluation import (
    NumericQuestionEvaluation, PaperFamilyEvaluationDenied, evaluate_supported_paper_questions,
)
from grading.contracts.scoring_decimal import ScoringDecimal


def _run(mutation):
    context, evidence, paper, operations, provider = _mixed()
    direct, numeric = operations
    originals = (direct.authority.question_text, evidence.questions[0].blocks[0].content, paper.maximum_score)
    class MutatingBinding:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            mutation(context, evidence, paper, direct, numeric)
            return numeric.binding_source.resolve_numeric_binding(
                grading_spec_ref=grading_spec_ref, question_id=question_id)
    new_ops = (direct, NumericQuestionEvaluation(numeric.authority, MutatingBinding(), numeric.authority_source))
    return (context, evidence, paper, originals, provider,
        lambda: evaluate_supported_paper_questions(context=context,evidence=evidence,paper_authority=paper,operations=new_ops))


def test_numeric_callback_cannot_change_admitted_direct_question_text():
    attack = lambda ctx,ev,paper,d,n: object.__setattr__(d.authority,'question_text','How do volcanoes erupt?')
    ctx, ev, paper, originals, provider, run = _run(attack)
    with pytest.raises(PaperFamilyEvaluationDenied):
        run()
    assert provider.requests == [], 'A mutated official question must not reach paid DIRECT provider'


def test_numeric_callback_cannot_replace_admitted_student_evidence():
    attack = lambda ctx,ev,paper,d,n: object.__setattr__(ev.questions[0].blocks[0], 'content','CONTRADICTORY REPLACED STUDENT ANSWER')
    ctx, ev, paper, originals, provider, run = _run(attack)
    with pytest.raises(PaperFamilyEvaluationDenied):
        run()
    assert provider.requests == [], 'A substituted OCR answer must not reach paid DIRECT provider'


def test_numeric_callback_cannot_change_original_paper_scoring_ceiling():
    attack = lambda ctx,ev,paper,d,n: object.__setattr__(paper,'maximum_score',ScoringDecimal.from_raw('20'))
    ctx, ev, paper, originals, provider, run = _run(attack)
    with pytest.raises(PaperFamilyEvaluationDenied):
        run()
    assert provider.requests == [], 'A substituted paper score ceiling must not reach DIRECT provider'


def test_valid_mixed_operation_continues_to_score():
    ctx,ev,paper,originals,provider,run = _run(lambda *args: None)
    result=run()
    assert len(provider.requests) == 1
    assert result.paper_score.final_score == ScoringDecimal.from_raw('10')


def test_valid_direct_operation_continues_to_score():
    from tests.integration.test_paper_family_evaluation import _direct
    ctx,ev,paper,op,provider=_direct()
    result=evaluate_supported_paper_questions(context=ctx,evidence=ev,paper_authority=paper,operations=(op,))
    assert len(provider.requests)==1
    assert len(result.questions)==1


def test_numeric_callback_cannot_replace_installed_direct_semantic_provider():
    from tests.integration.test_direct_text_semantic_evaluator_hostile import _Provider
    replacement_provider = _Provider()
    attack = lambda ctx,ev,paper,d,n: object.__setattr__(d.evaluator,'_provider',replacement_provider)
    ctx,ev,paper,originals,original_provider,run = _run(attack)
    with pytest.raises(PaperFamilyEvaluationDenied):
        run()
    assert replacement_provider.requests == [], 'Unadmitted semantic provider must not receive the student answer'


def test_numeric_callback_cannot_replace_installed_model_answer_source():
    from tests.integration.test_direct_text_semantic_evaluator_hostile import _ModelAnswerSource, _answer
    replacement_source = _ModelAnswerSource(_answer())
    attack = lambda ctx,ev,paper,d,n: object.__setattr__(d.evaluator,'_model_answer_source',replacement_source)
    ctx,ev,paper,originals,original_provider,run = _run(attack)
    with pytest.raises(PaperFamilyEvaluationDenied):
        run()
    assert replacement_source.calls == [], 'Unadmitted model answer source must not be invoked'


"""Additional regressions for admitted family source custody.
The regression assertions require the original admitted academic/evidence inputs to stay bound.
"""
import pytest
from grading.integration.paper_family_evaluation import (
    DirectQuestionEvaluation, NumericQuestionEvaluation,
    PaperFamilyEvaluationDenied, evaluate_supported_paper_questions,
)
from tests.integration.test_paper_family_evaluation import _mixed, _direct


def test_positive_mixed_control():
    context, evidence, paper, operations, provider = _mixed()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence,
        paper_authority=paper, operations=operations)
    assert len(result.questions) == 2
    assert len(provider.requests) == 1
    assert result.paper_score is not None


def test_positive_direct_control():
    context, evidence, paper, op, provider = _direct()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence,
        paper_authority=paper, operations=(op,))
    assert len(result.questions) == 1
    assert len(provider.requests) == 1


def test_numeric_resolver_cannot_replace_original_direct_question_text():
    context, evidence, paper, operations, provider = _mixed()
    direct, numeric = operations
    original_text = direct.authority.question_text
    class MutateQuestion:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            object.__setattr__(direct.authority, 'question_text', 'FORGED AFTER ACADEMIC ADMISSION')
            return numeric.binding_source.resolve_numeric_binding(
                grading_spec_ref=grading_spec_ref, question_id=question_id)
    substitute = NumericQuestionEvaluation(numeric.authority, MutateQuestion(), numeric.authority_source)
    # Mutating a previously admitted academic question must never yield a scored result.
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper, operations=(direct, substitute))
    assert original_text != direct.authority.question_text
    assert provider.requests == []


def test_numeric_resolver_cannot_replace_direct_evidence_after_preflight():
    context, evidence, paper, operations, provider = _mixed()
    direct, numeric = operations
    block = evidence.questions[0].blocks[0]
    original_text = block.content
    class MutateEvidence:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            object.__setattr__(block, 'content', 'FORGED ANSWER AFTER EVIDENCE PREFLIGHT')
            return numeric.binding_source.resolve_numeric_binding(
                grading_spec_ref=grading_spec_ref, question_id=question_id)
    substitute = NumericQuestionEvaluation(numeric.authority, MutateEvidence(), numeric.authority_source)
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper, operations=(direct, substitute))
    assert block.content != original_text
    assert provider.requests == []


def test_numeric_resolver_cannot_replace_original_official_question_order():
    context, evidence, paper, operations, provider = _mixed()
    original_order = tuple(x.question_id for x in paper.expected_questions)
    direct, numeric = operations
    class MutatePaper:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            object.__setattr__(paper, 'expected_questions', tuple(reversed(paper.expected_questions)))
            return numeric.binding_source.resolve_numeric_binding(
                grading_spec_ref=grading_spec_ref, question_id=question_id)
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper, operations=(direct, NumericQuestionEvaluation(numeric.authority, MutatePaper(), numeric.authority_source)))
    assert tuple(x.question_id for x in paper.expected_questions) != original_order
    assert provider.requests == []


def test_direct_provider_cannot_replace_admitted_question_after_contact():
    context, evidence, paper, op, _ = _direct()
    from tests.integration.test_paper_family_evaluation import _Provider, _evaluator
    original = op.authority.question_text
    class MutatingProvider(_Provider):
        def evaluate(self, *, request):
            object.__setattr__(op.authority, 'question_text', 'AFTER PHYSICAL PROVIDER CONTACT')
            return super().evaluate(request=request)
    provider = MutatingProvider()
    evaluator, _, _ = _evaluator(authority=op.authority, provider=provider)
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper, operations=(DirectQuestionEvaluation(op.authority, evaluator, op.evaluation_attempt_id),))
    assert original != op.authority.question_text
    assert len(provider.requests) == 1  # effect already happened, cannot be undone
