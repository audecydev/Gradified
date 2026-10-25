from __future__ import annotations

from dataclasses import replace

import pytest

from grading.integration.paper_family_evaluation import (
    DirectQuestionEvaluation, NumericQuestionEvaluation,
    PaperFamilyEvaluationDenied, evaluate_supported_paper_questions,
)
from grading.contracts.scoring_decimal import ScoringDecimal
from tests.integration.test_direct_text_semantic_evaluator_hostile import (
    _resolved_question_authority, _evidence, _context, _evaluator, _Provider,
)
from tests.integration.test_direct_text_semantic_evaluator_regression import _paper_authority
from tests.unit.test_numeric_authority_resolution_regression import (
    _resolved_active, _authority, _BindingSource, _AuthoritySource, _Materialized, _paper,
)
from tests.unit.test_numeric_evidence_admission_regression import _bundle, _block, _question
from grading.contracts.numeric_authority import (
    NumericBoundAuthorityBinding, NumericAuthorityApproval, numeric_authority_fingerprint,
)
from grading.execution import GradingExecutionContext


def _direct():
    authority = _resolved_question_authority()
    evidence = _evidence()
    context = _context(authority=authority, evidence=evidence)
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=authority, provider=provider)
    operation = DirectQuestionEvaluation(authority, evaluator, 'direct-attempt-1')
    return context, evidence, _paper_authority(), operation, provider


def _numeric():
    authority = _resolved_active()
    scoring_authority = _authority(authority)
    fingerprint = numeric_authority_fingerprint(scoring_authority)
    binding = NumericBoundAuthorityBinding(authority.grading_spec_ref, authority.question_id, '1', fingerprint)
    approval = NumericAuthorityApproval('teacher:authorized-numeric', fingerprint)
    evidence = _bundle(_question(_block('5.1')))
    context = GradingExecutionContext('run-numeric', evidence.submission_ref, 'exam-numeric', authority.grading_spec_ref)
    op = NumericQuestionEvaluation(authority, _BindingSource(binding), _AuthoritySource(_Materialized(scoring_authority, approval)))
    return context, evidence, _paper(), op


def test_direct_executes_real_semantic_provider_through_s1_and_frozen_scoring():
    context, evidence, paper, op, provider = _direct()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence, paper_authority=paper, operations=(op,))
    assert len(provider.requests) == 1
    assert result.paper_score.question_results == tuple(x.score for x in result.questions)
    assert len(result.questions) == 1


def test_numeric_executes_n1_n2_n3_n4_through_s1_and_frozen_scoring():
    context, evidence, paper, op = _numeric()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence, paper_authority=paper, operations=(op,))
    assert result.paper_score.final_score == ScoringDecimal.from_raw('5')
    assert result.questions[0].score.final_score == ScoringDecimal.from_raw('5')


def test_bad_inventory_fails_before_direct_provider_call():
    context, evidence, paper, op, provider = _direct()
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence, paper_authority=paper, operations=(op,op))
    assert provider.requests == []


def test_wrong_evidence_provenance_fails_before_provider():
    context, evidence, paper, op, provider = _direct()
    context = replace(context, submission_ref='another-student')
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence, paper_authority=paper, operations=(op,))
    assert provider.requests == []


def test_caller_cannot_supply_fake_judgments_or_choice_family():
    context, evidence, paper, op, provider = _direct()
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence, paper_authority=paper, operations=(object(),))
    assert provider.requests == []


def test_bad_numeric_approval_denies_instead_of_zero_mark():
    context, evidence, paper, op = _numeric()
    from grading.numeric_authority import NumericExpectedBindingError
    # Missing approved numeric binding cannot be converted into NOT_SATISFIED.
    op = NumericQuestionEvaluation(op.authority, _BindingSource(None), op.authority_source)
    with pytest.raises(NumericExpectedBindingError):
        evaluate_supported_paper_questions(context=context, evidence=evidence, paper_authority=paper, operations=(op,))


def _mixed():
    from grading.active_question_authority import ContextPolicy, resolve_active_question_authority
    from grading.contracts.paper_aggregation import ExpectedQuestionResult, ResolvedPaperScoringAuthority
    from grading.contracts.result import RubricRef, ScoringPolicyRef
    from grading.contracts.policy import SCORING_SEMANTICS_V1
    from grading.rubric.lifecycle import create_initial_version, validate_version, approve_version, activate_version
    from tests.support.rubric_authoring import simple_basis, simple_content, authoring_test_limits
    from tests.integration.test_direct_text_semantic_evaluator_regression import (
        _SelectedActiveQuestion as _Selected, _ActiveSpecSourceDouble as _Source,
        _active_rubric,
    )
    from tests.unit.test_numeric_authority_resolution_regression import _SelectedActiveQuestion as _NSelected, _ActiveSource as _NSource
    from grading.contracts.evidence import AnswerEvidenceBundle

    base = _paper_authority()
    numeric_expected = ExpectedQuestionResult('Q2', RubricRef('R-Q2', 1),
        ScoringPolicyRef('P-Q2', 1, SCORING_SEMANTICS_V1))
    paper = ResolvedPaperScoringAuthority(base.grading_spec_ref,
        (base.expected_questions[0], numeric_expected),
        ScoringDecimal.from_raw('0'), ScoringDecimal.from_raw('10'))

    direct_active = resolve_active_question_authority(paper_authority=paper, question_id='Q1',
        source=_Source(_Selected(paper.grading_spec_ref, 'Q1', 'Why is the sky blue?',
                                 ContextPolicy.DIRECT, _active_rubric())))
    content = replace(simple_content(), rubric_id='R-Q2', policy_id='P-Q2')
    limits = authoring_test_limits()
    draft = create_initial_version(simple_basis(question_id='Q2'), content)
    active_version = activate_version(approve_version(validate_version(draft, limits=limits),
                                           teacher_ref='teacher:Q2'), limits=limits)
    numeric_active = resolve_active_question_authority(paper_authority=paper, question_id='Q2',
        source=_NSource(_NSelected(paper.grading_spec_ref, 'Q2', 'Return the scalar result.',
                                   ContextPolicy.DIRECT, active_version)))
    numeric_auth = _authority(numeric_active)
    fingerprint = numeric_authority_fingerprint(numeric_auth)
    numeric_binding = NumericBoundAuthorityBinding(numeric_active.grading_spec_ref,
                                                     'Q2', '1', fingerprint)
    numeric_approval = NumericAuthorityApproval('teacher:numeric-Q2', fingerprint)

    direct_evidence = _evidence()
    numeric_block = replace(_block('5.1'), block_id='Q2_B1')
    numeric_evidence = _question(numeric_block, question_id='Q2', answer_scope_ref='scope-Q2')
    evidence = AnswerEvidenceBundle(direct_evidence.schema_version, direct_evidence.submission_ref,
                                    direct_evidence.ocr_provenance,
                                    direct_evidence.questions + (numeric_evidence,))
    context = _context(authority=direct_active, evidence=evidence)
    provider = _Provider()
    evaluator, _, _ = _evaluator(authority=direct_active, provider=provider)
    ops = (DirectQuestionEvaluation(direct_active, evaluator, 'FIRST-Q1'),
           NumericQuestionEvaluation(numeric_active, _BindingSource(numeric_binding),
                                     _AuthoritySource(_Materialized(numeric_auth, numeric_approval))))
    return context, evidence, paper, ops, provider


def test_real_mixed_direct_numeric_two_question_aggregation_without_forged_judgments():
    context, evidence, paper, operations, provider = _mixed()
    result = evaluate_supported_paper_questions(context=context, evidence=evidence,
                                                paper_authority=paper, operations=operations)
    assert tuple(r.score.question_id for r in result.questions) == ('Q1', 'Q2')
    assert result.questions[1].score.final_score == ScoringDecimal.from_raw('5')
    assert result.paper_score.final_score == ScoringDecimal.from_raw('10')
    assert len(provider.requests) == 1


def test_mixed_inventory_cross_question_swap_denied_before_semantic_provider():
    context, evidence, paper, operations, provider = _mixed()
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
                                           paper_authority=paper, operations=tuple(reversed(operations)))
    assert provider.requests == []


def test_mixed_numeric_evidence_missing_denied_before_semantic_provider():
    context, evidence, paper, operations, provider = _mixed()
    evidence = replace(evidence, questions=evidence.questions[:1])
    with pytest.raises(PaperFamilyEvaluationDenied):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
                                           paper_authority=paper, operations=operations)
    assert provider.requests == []


def test_mixed_numeric_source_denial_prevents_avoidable_direct_provider_contact():
    from grading.numeric_authority import NumericExpectedBindingError
    context, evidence, paper, operations, provider = _mixed()
    invalid = NumericQuestionEvaluation(operations[1].authority, _BindingSource(None),
                                        operations[1].authority_source)
    with pytest.raises(NumericExpectedBindingError):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
                                           paper_authority=paper,
                                           operations=(operations[0], invalid))
    assert provider.requests == []


def test_all_direct_local_evidence_is_preflighted_before_any_provider():
    from grading.contracts.evidence import EvidenceBlockState
    from grading.semantic_evaluator import DirectTextSemanticUnsupportedInputError
    context, evidence, paper, operations, first_provider = _mixed()
    evaluator, _, _ = _evaluator(authority=operations[1].authority)
    second = DirectQuestionEvaluation(operations[1].authority, evaluator, 'FIRST-Q2')
    question = evidence.questions[1]
    bad = replace(question, blocks=tuple(replace(b, state=EvidenceBlockState.UNCERTAIN) for b in question.blocks))
    with pytest.raises(DirectTextSemanticUnsupportedInputError):
        evaluate_supported_paper_questions(context=context,
            evidence=replace(evidence, questions=(evidence.questions[0], bad)),
            paper_authority=paper, operations=(operations[0], second))
    assert first_provider.requests == []


def test_numeric_callback_cannot_change_original_direct_attempt():
    context, evidence, paper, operations, provider = _mixed()
    direct, numeric = operations

    class MutatingBinding:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            object.__setattr__(direct, 'evaluation_attempt_id', 'SUBSTITUTED')
            return numeric.binding_source.resolve_numeric_binding(
                grading_spec_ref=grading_spec_ref, question_id=question_id)

    with pytest.raises(PaperFamilyEvaluationDenied, match='Original DIRECT attempt'):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper,
            operations=(direct, NumericQuestionEvaluation(numeric.authority, MutatingBinding(), numeric.authority_source)))
    assert provider.requests == []


def test_numeric_callback_cannot_change_original_exam_context():
    context, evidence, paper, operations, provider = _mixed()
    direct, numeric = operations

    class MutatingBinding:
        def resolve_numeric_binding(self, *, grading_spec_ref, question_id):
            object.__setattr__(context, 'exam_ref', 'OTHER-EXAM')
            return numeric.binding_source.resolve_numeric_binding(
                grading_spec_ref=grading_spec_ref, question_id=question_id)

    with pytest.raises(PaperFamilyEvaluationDenied, match='Original grading execution context'):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper,
            operations=(direct, NumericQuestionEvaluation(numeric.authority, MutatingBinding(), numeric.authority_source)))
    assert provider.requests == []


def test_provider_callback_context_mutation_blocks_score_after_contact():
    context, evidence, paper, op, _ = _direct()

    class MutatingProvider(_Provider):
        def evaluate(self, *, request):
            object.__setattr__(context, 'exam_ref', 'OTHER-EXAM')
            return super().evaluate(request=request)

    provider = MutatingProvider()
    evaluator, _, _ = _evaluator(authority=op.authority, provider=provider)
    with pytest.raises(PaperFamilyEvaluationDenied, match='Original grading execution context'):
        evaluate_supported_paper_questions(context=context, evidence=evidence,
            paper_authority=paper,
            operations=(DirectQuestionEvaluation(op.authority, evaluator, op.evaluation_attempt_id),))
    # This attack occurs inside the provider call: contact is already made.
    # The engine can refuse its result, but cannot undo that physical contact.
    assert len(provider.requests) == 1
