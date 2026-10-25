"""Outer CHOICE identity checks using actual admitted normalized OCR evidence admission/question evidence binding inputs.

These fixtures are controlled tests, not evidence of production source authority.
"""
from dataclasses import replace
import json

import pytest

from grading.active_question_authority import ContextPolicy, ResolvedQuestionAuthority
from grading.contracts.choice import (
    CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
    CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
    CanonicalChoiceSelection,
    ChoiceCriterionProjection,
    ChoiceEvaluationAuthority,
)
from grading.contracts.paper_aggregation import (
    ExpectedQuestionResult, GradingSpecRef, ResolvedPaperScoringAuthority,
)
from grading.contracts.result import RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.execution import GradingExecutionContext
from grading.integration.evidence_ingress import NormalizedEvidenceAdmissionPolicy
from grading.integration.question_evaluation_preparation import prepare_question_evaluation_inputs
from grading.rubric.fingerprint import compiled_authority_fingerprint
from grading.rubric.lifecycle import (
    activate_version, approve_version, create_initial_version,
    get_active_scoring_authority, validate_version,
)
from tests.support.rubric_authoring import authoring_test_limits, simple_basis, simple_content


def _prepared():
    limits = authoring_test_limits()
    active = activate_version(
        approve_version(
            validate_version(
                create_initial_version(simple_basis(), simple_content()),
                limits=limits,
            ),
            teacher_ref="fixture-teacher",
        ),
        limits=limits,
    )
    scoring = get_active_scoring_authority(active)
    spec = GradingSpecRef(id="SPEC-1", version=1)
    paper = ResolvedPaperScoringAuthority(
        grading_spec_ref=spec,
        expected_questions=(ExpectedQuestionResult(
            question_id="Q1",
            rubric_ref=RubricRef(scoring.rubric.rubric_id, scoring.rubric.version),
            scoring_policy_ref=ScoringPolicyRef(
                scoring.policy.policy_id, scoring.policy.version,
                scoring.policy.scoring_semantics_version,
            ),
        ),),
        minimum_score=ScoringDecimal.from_raw("0"),
        maximum_score=ScoringDecimal.from_raw("5"),
    )
    question = ResolvedQuestionAuthority(
        grading_spec_ref=spec,
        question_id="Q1",
        question_text="Select the option",
        context_policy=ContextPolicy.DIRECT,
        rubric_content=active.content,
        scoring_authority=scoring,
    )
    context = GradingExecutionContext(
        grading_run_id="RUN-1", submission_ref="SUB-1",
        exam_ref="EXAM-1", grading_spec_ref=spec,
    )
    admission = NormalizedEvidenceAdmissionPolicy(
        admission_policy_identity="fixture-admission", max_raw_bytes=10_000,
        max_json_depth=16, max_json_nodes=100, max_json_number_characters=32,
        max_identifier_characters=128, max_metadata_text_characters=512,
        max_block_content_characters=512, max_total_content_characters=1000,
        max_questions=5, max_blocks_per_question=10, max_total_blocks=20,
        max_warnings_per_question=10, max_location_coordinates=8,
    )
    payload = json.dumps({
        "schema_version":"1", "submission_ref":"SUB-1", "ocr_provenance":"fixture-ocr",
        "questions":[{"question_id":"Q1", "answer_scope_ref":"SCOPE-1",
                     "warnings":[], "blocks":[{
                         "block_id":"EVIDENCE-1", "type":"TEXT", "content":"B",
                         "language":"en", "confidence":None,
                         "confidence_status":"UNAVAILABLE", "state":"ACTIVE",
                         "page":1, "location":{"status":"UNAVAILABLE", "bbox":None},
                         "reading_order":1, "asset_ref":None,
                     }]}],
    }).encode()
    return prepare_question_evaluation_inputs(
        raw_payload=payload, admission_policy=admission, context=context,
        paper_authority=paper, question_authority=question,
    )


def _choice(prepared):
    scoring = prepared.question_authority.scoring_authority
    authority = ChoiceEvaluationAuthority(
        schema_version=CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
        grading_spec_ref=prepared.context.grading_spec_ref,
        question_id="Q1",
        compiled_authority_hash=compiled_authority_fingerprint(scoring),
        option_ids=("A", "B"), official_option_id="B",
        match_projection=tuple(
            ChoiceCriterionProjection(c.criterion_id, "FULL")
            for c in scoring.rubric.criteria
        ),
        mismatch_projection=tuple(
            ChoiceCriterionProjection(c.criterion_id, "NOT_MET")
            for c in scoring.rubric.criteria
        ),
    )
    selection = CanonicalChoiceSelection(
        schema_version=CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
        submission_ref="SUB-1", question_id="Q1", selected_option_id="B",
        evidence_refs=("EVIDENCE-1",),
    )
    return authority, selection


def test_valid_outer_binding_detaches_prepared_and_preserves_choice_values():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    result = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    assert result.prepared is not prepared
    assert result.prepared.context.submission_ref == prepared.context.submission_ref
    assert result.prepared.question_authority.question_id == prepared.question_authority.question_id
    assert result.choice_authority == authority
    assert result.selection == selection
    assert "EVIDENCE-1" not in repr(result)
    assert not hasattr(result, "is_execution_eligible")
    assert not hasattr(result, "authenticated")


@pytest.mark.parametrize("change", (
    "submission", "selection_question", "authority_question", "spec_id", "spec_version", "hash"
))
def test_cross_scope_substitution_fails(change):
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    if change == "submission":
        selection = replace(selection, submission_ref="SUB-OTHER")
    elif change == "selection_question":
        selection = replace(selection, question_id="Q2")
    elif change == "authority_question":
        authority = replace(authority, question_id="Q2")
    elif change == "spec_id":
        authority = replace(authority, grading_spec_ref=GradingSpecRef("OTHER", 1))
    elif change == "spec_version":
        authority = replace(authority, grading_spec_ref=GradingSpecRef("SPEC-1", 2))
    else:
        authority = replace(authority, compiled_authority_hash="0" * 64)
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def test_rejects_untrusted_object_shapes_without_dereferencing_properties():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    class Hostile:
        @property
        def grading_spec_ref(self):
            raise RuntimeError("hostile property executed")
    prepared = _prepared()
    authority, selection = _choice(prepared)
    for kwargs in (
        {"prepared": Hostile(), "choice_authority": authority, "selection": selection},
        {"prepared": prepared, "choice_authority": Hostile(), "selection": selection},
        {"prepared": prepared, "choice_authority": authority, "selection": Hostile()},
    ):
        with pytest.raises(ChoiceInputBindingError):
            bind_choice_evaluation_inputs(**kwargs)


def test_rejects_damaged_exact_contract_fields_with_typed_error():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    object.__delattr__(authority, "grading_spec_ref")
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def test_rejects_damaged_choice_selection_fields_with_typed_error():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    object.__delattr__(selection, "submission_ref")
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def test_does_not_interpret_or_verify_ocr_selected_option_or_evidence():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    # Admission of the canonical selection itself is an upstream responsibility;
    # structural outer binding is not evidence verification or OCR extraction.
    selection = replace(selection, evidence_refs=("NOT_VERIFIED_HERE",))
    result = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    assert result.selection.evidence_refs == ("NOT_VERIFIED_HERE",)


def test_binding_detaches_choice_inputs_from_later_caller_mutation():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    object.__setattr__(authority, "official_option_id", "A")
    object.__setattr__(selection, "selected_option_id", "A")
    assert bound.choice_authority.official_option_id == "B"
    assert bound.selection.selected_option_id == "B"


def test_invalid_postconstruction_projection_field_rejected():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    object.__setattr__(authority.match_projection[0], "criterion_id", "")
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def test_postconstruction_forged_nested_spec_rejected_without_dispatch():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    class Hostile:
        @property
        def id(self):
            raise RuntimeError("hostile nested property executed")
    object.__setattr__(authority, "grading_spec_ref", Hostile())
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def test_bound_choice_is_not_permission_to_run_or_evidence_certification():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    # No evaluator invocation, no deterministic scoring verification and no manufactured provenance.
    assert bound.prepared.context.grading_run_id == "RUN-1"
    assert bound.selection.evidence_refs == ("EVIDENCE-1",)
    assert not hasattr(bound, "verified_judgments")
    assert not hasattr(bound, "execution_attempt_id")


def test_tampered_prepared_question_is_revalidated_against_paper_and_evidence():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    # Privileged in-process code can bypass frozen dataclass protections.
    object.__setattr__(prepared.question_authority, "question_id", "Q2")
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared,
            choice_authority=authority,
            selection=selection,
        )


def test_corrupted_prepared_scoring_structure_is_rejected():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    object.__delattr__(prepared.question_authority.scoring_authority, "rubric")
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared,
            choice_authority=authority,
            selection=selection,
        )


def test_binding_preserves_frozen_choice_and_s1_positive_behavior():
    from grading.choice_evaluator import evaluate_single_select_choice
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    from grading.verification.evidence import verify_evaluated_judgments
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    # Controlled test invocation only: production eligibility and actual
    # attempt origin have NOT been established by this outer binding.
    judgments = evaluate_single_select_choice(
        authority=bound.choice_authority, selection=bound.selection,
        scoring_authority=bound.prepared.question_authority.scoring_authority,
    )
    verified = verify_evaluated_judgments(
        evidence=bound.prepared.admitted_evidence.evidence,
        question_id=bound.prepared.question_authority.question_id,
        judgments=judgments,
    )
    assert len(verified.scoring_judgments) == len(
        prepared.question_authority.scoring_authority.rubric.criteria
    )


def test_s1_still_rejects_unproven_choice_evidence_reference():
    from grading.choice_evaluator import evaluate_single_select_choice
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    from grading.verification.evidence import EvidenceVerificationError, verify_evaluated_judgments
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority,
        selection=replace(selection, evidence_refs=("FORGED-BLOCK",)),
    )
    judgments = evaluate_single_select_choice(
        authority=bound.choice_authority, selection=bound.selection,
        scoring_authority=bound.prepared.question_authority.scoring_authority,
    )
    with pytest.raises(EvidenceVerificationError):
        verify_evaluated_judgments(
            evidence=bound.prepared.admitted_evidence.evidence,
            question_id=bound.prepared.question_authority.question_id,
            judgments=judgments,
        )

# Independent hostile-review closure: binding lifetime and damaged nested state.
def test_rejects_malformed_paper_question_collections():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    for corrupted in (None, [], ()):  # originally validated by paper authority constructor
        prepared = _prepared()
        authority, selection = _choice(prepared)
        object.__setattr__(prepared.paper_authority, "expected_questions", corrupted)
        with pytest.raises(ChoiceInputBindingError):
            bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)
    prepared = _prepared()
    authority, selection = _choice(prepared)
    object.__setattr__(prepared.paper_authority, "expected_questions", list(prepared.paper_authority.expected_questions))
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)


def test_prepared_snapshot_survives_caller_root_mutation():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)
    object.__setattr__(prepared.context, "submission_ref", "SUB-CHANGED")
    object.__setattr__(prepared.question_authority, "question_id", "Q-CHANGED")
    object.__setattr__(prepared.paper_authority, "expected_questions", None)
    object.__setattr__(prepared.question_authority.scoring_authority.rubric, "question_id", "Q-CHANGED")
    assert bound.prepared is not prepared
    assert bound.prepared.context.submission_ref == bound.selection.submission_ref == "SUB-1"
    assert bound.prepared.question_authority.question_id == bound.selection.question_id == "Q1"
    assert bound.prepared.paper_authority.expected_questions is not None
    assert bound.prepared.question_authority.scoring_authority.rubric.question_id == "Q1"


def test_fingerprint_side_effect_cannot_return_cross_submission_binding():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    old_marks = prepared.question_authority.scoring_authority.rubric.max_marks
    accessed = []
    class HostileMarks:
        def __eq__(self, other):
            return True
        def to_canonical_string(self):
            accessed.append("malformed scorer callback executed")
            object.__setattr__(prepared.context, "submission_ref", "SUB-SWAPPED")
            return old_marks.to_canonical_string()
    object.__setattr__(prepared.question_authority.scoring_authority.rubric, "max_marks", HostileMarks())
    with pytest.raises(ChoiceInputBindingError, match="invalid or inconsistent"):
        bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)
    assert not accessed
    assert prepared.context.submission_ref == "SUB-1"


def test_mutation_of_caller_evidence_does_not_rewrite_bound_evidence():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)
    object.__setattr__(prepared.admitted_evidence.evidence, "submission_ref", "SUB-OTHER")
    assert bound.prepared.admitted_evidence is not prepared.admitted_evidence
    assert bound.prepared.admitted_evidence.evidence.submission_ref == "SUB-1"
    assert bound.prepared.admitted_evidence.evidence.submission_ref == bound.selection.submission_ref


def test_bounded_choice_result_not_directly_constructible():
    from grading.integration.choice_binding import BoundChoiceEvaluationInputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    with pytest.raises(TypeError):
        BoundChoiceEvaluationInputs(prepared=prepared, choice_authority=authority, selection=selection)

@pytest.mark.parametrize("root", ("context", "admitted_evidence", "paper_authority", "question_authority"))
def test_rejects_malicious_prepared_root_without_property_execution(root):
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    class Hostile:
        @property
        def grading_spec_ref(self):
            raise AssertionError("source-controlled property must not run")
        @property
        def expected_questions(self):
            raise AssertionError("source-controlled property must not run")
    object.__setattr__(prepared, root, Hostile())
    with pytest.raises(ChoiceInputBindingError, match="root types"):
        bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)


def test_frozen_choice_and_s1_consume_detached_values_after_input_mutation():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    from grading.choice_evaluator import evaluate_single_select_choice
    from grading.verification.evidence import verify_evaluated_judgments
    prepared = _prepared()
    authority, selection = _choice(prepared)
    bound = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    object.__setattr__(prepared.context, "submission_ref", "OTHER-SUBMISSION")
    object.__setattr__(prepared.question_authority, "question_id", "OTHER-QUESTION")
    judgments = evaluate_single_select_choice(
        authority=bound.choice_authority,
        selection=bound.selection,
        scoring_authority=bound.prepared.question_authority.scoring_authority,
    )
    verified = verify_evaluated_judgments(
        evidence=bound.prepared.admitted_evidence.evidence,
        question_id=bound.prepared.question_authority.question_id,
        judgments=judgments,
    )
    assert verified.scoring_judgments
    assert bound.prepared.context.submission_ref == bound.selection.submission_ref == "SUB-1"


def test_deleted_prepared_field_fails_with_typed_input_error():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    object.__delattr__(prepared.paper_authority, "expected_questions")
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)


def test_nested_compiled_amount_cannot_impersonate_scoring_fingerprint():
    from grading.integration.choice_binding import ChoiceInputBindingError, bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    rubric = prepared.question_authority.scoring_authority.rubric
    level = rubric.criteria[0].performance_levels[0]
    original = level.contribution
    side_effects = []
    class HostileContribution:
        def to_canonical_string(self):
            side_effects.append("not a canonical scoring value")
            return original.to_canonical_string()
    object.__setattr__(level, "contribution", HostileContribution())
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(prepared=prepared, choice_authority=authority, selection=selection)
    assert not side_effects

# The outer handoff is a *detached and revalidated* domain graph. These cases
# compare against actual frozen constructors, not its previous validation code.
@pytest.mark.parametrize(('path', 'replacement'), (
    ('run', ''),
    ('exam', ''),
    ('wire_schema', 'FORGED'),
    ('digest', 'NOT_A_SHA256'),
    ('policy_name', ''),
    ('policy_questions', 0),
    ('evidence_questions', 'list'),
    ('question_blocks', 'list'),
    ('block_content', 42),
    ('block_type', 'TEXT'),
    ('block_state', 'ACTIVE'),
    ('evidence_schema', 'FORGED'),
    ('source_ref', ''),
    ('oversize_content', 'B' * 513),
))
def test_mutated_prepared_graph_rejected_at_binding(path, replacement):
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    prepared = _prepared()
    authority, selection = _choice(prepared)
    admitted = prepared.admitted_evidence
    block = admitted.evidence.questions[0].blocks[0]
    changes = {
        'run': (prepared.context, 'grading_run_id', replacement),
        'exam': (prepared.context, 'exam_ref', replacement),
        'wire_schema': (admitted, 'wire_schema_version', replacement),
        'digest': (admitted, 'raw_payload_sha256', replacement),
        'policy_name': (admitted, 'admission_policy_identity', replacement),
        'policy_questions': (admitted.effective_policy_snapshot, 'max_questions', replacement),
        'evidence_questions': (admitted.evidence, 'questions', list(admitted.evidence.questions)),
        'question_blocks': (admitted.evidence.questions[0], 'blocks', list(admitted.evidence.questions[0].blocks)),
        'block_content': (block, 'content', replacement),
        'block_type': (block, 'type', replacement),
        'block_state': (block, 'state', replacement),
        'evidence_schema': (admitted.evidence, 'schema_version', replacement),
        'source_ref': (admitted, 'source_artifact_ref', replacement),
        'oversize_content': (block, 'content', replacement),
    }
    obj, field, value = changes[path]
    object.__setattr__(obj, field, value)
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def _prepared_with_gate():
    from grading.contracts.authority import QuestionScoringAuthority
    from grading.contracts.policy import CriterionCondition, GateRule
    prepared = _prepared()
    original = prepared.question_authority.scoring_authority
    condition = CriterionCondition('C1', ('FULL',))
    rule = GateRule('GATE-1', (condition,), ScoringDecimal.from_raw('0'))
    policy = replace(original.policy, gates=(rule,))
    object.__setattr__(
        prepared.question_authority, 'scoring_authority',
        QuestionScoringAuthority(rubric=original.rubric, policy=policy),
    )
    authority, selection = _choice(prepared)
    return prepared, authority, selection, condition


@pytest.mark.parametrize('corruption', ('custom_container', 'list', 'dependency_list', 'rounding_mode', 'rubric_level_list'))
def test_postconstruction_scoring_shape_corruption_rejected_before_fingerprint(corruption):
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    from grading.contracts.policy import RoundingRule, RoundingMode
    from grading.contracts.authority import QuestionScoringAuthority
    from grading.contracts.policy import PositiveCreditDependencyRule, CriterionCondition
    prepared, authority, selection, condition = _prepared_with_gate()
    scoring = prepared.question_authority.scoring_authority
    if corruption == 'custom_container':
        class MisleadingAllowedLevels:
            def __iter__(self): return iter(('FULL',))
            def __contains__(self, value): return False
        object.__setattr__(condition, 'allowed_level_ids', MisleadingAllowedLevels())
    elif corruption == 'list':
        object.__setattr__(condition, 'allowed_level_ids', ['FULL'])
    elif corruption == 'dependency_list':
        object.__setattr__(scoring.policy, 'positive_credit_dependencies', [])
    elif corruption == 'rounding_mode':
        rule = RoundingRule('ROUND-1', ScoringDecimal.from_raw('1'), RoundingMode.HALF_UP)
        scoring = QuestionScoringAuthority(scoring.rubric, replace(scoring.policy, rounding=rule))
        object.__setattr__(prepared.question_authority, 'scoring_authority', scoring)
        object.__setattr__(rule, 'mode', 'HALF_UP')
    elif corruption == 'rubric_level_list':
        criterion = scoring.rubric.criteria[0]
        object.__setattr__(criterion, 'performance_levels', list(criterion.performance_levels))
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )


def test_nested_deepcopy_hook_is_not_executed_by_prepared_snapshot():
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    prepared, authority, selection, condition = _prepared_with_gate()
    called = []
    class ForeignContainer:
        def __deepcopy__(self, memo):
            called.append('executed')
            raise RuntimeError('unsafe arbitrary copying')
    object.__setattr__(condition, 'allowed_level_ids', ForeignContainer())
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )
    assert called == []


def test_valid_gate_scoring_after_detached_choice_binding():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    from grading.choice_evaluator import evaluate_single_select_choice
    from grading.verification.evidence import verify_evaluated_judgments
    from grading.scoring.reducer import reduce_question
    prepared, authority, selection, condition = _prepared_with_gate()
    bound = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    object.__setattr__(condition, 'allowed_level_ids', ['NOT_MET'])
    evaluated = evaluate_single_select_choice(
        authority=bound.choice_authority, selection=bound.selection,
        scoring_authority=bound.prepared.question_authority.scoring_authority,
    )
    verified = verify_evaluated_judgments(
        evidence=bound.prepared.admitted_evidence.evidence,
        question_id=bound.prepared.question_authority.question_id, judgments=evaluated,
    )
    score = reduce_question(
        bound.prepared.question_authority.scoring_authority,
        verified.scoring_judgments,
    )
    assert str(score.final_score) == '5'


def test_expected_rejection_diagnostics_hide_student_evidence_from_chain():
    import traceback
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    p = _prepared()
    authority, selection = _choice(p)
    original = p.admitted_evidence.evidence.questions[0]
    block = original.blocks[0]
    canary = "PRIVATE_STUDENT_CONTENT_8741"
    object.__setattr__(block, "block_id", canary)
    object.__setattr__(block, "content", canary)
    object.__setattr__(original, "blocks", (block, replace(block)))
    with pytest.raises(ChoiceInputBindingError) as captured:
        bind_choice_evaluation_inputs(prepared=p, choice_authority=authority, selection=selection)
    error = captured.value
    assert error.__cause__ is None and error.__context__ is None
    assert not getattr(error, "__notes__", None)
    assert canary not in "".join(traceback.format_exception(error))
    assert canary not in repr(error.args)


@pytest.mark.parametrize("surface", ("authority", "selection", "scoring", "prepared"))
def test_expected_rejections_across_all_binding_surfaces_have_no_private_causes(surface):
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    p = _prepared()
    authority, selection = _choice(p)
    if surface == "authority":
        object.__delattr__(authority, "grading_spec_ref")
    elif surface == "selection":
        object.__delattr__(selection, "submission_ref")
    elif surface == "scoring":
        object.__setattr__(p.question_authority.scoring_authority.rubric, "criteria", [])
    else:
        object.__delattr__(p.paper_authority, "expected_questions")
    with pytest.raises(ChoiceInputBindingError) as captured:
        bind_choice_evaluation_inputs(prepared=p, choice_authority=authority, selection=selection)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert not getattr(captured.value, "__notes__", None)


@pytest.mark.parametrize("corruption", (
    "questions", "blocks", "warnings", "aggregate_blocks", "block_content", "aggregate_content", "bbox", "policy", "foreign_blocks",
))
def test_admitted_evidence_limits_checked_before_domain_reconstruction(corruption, monkeypatch):
    from grading.contracts import evidence as evidence_contracts
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    p = _prepared()
    authority, selection = _choice(p)
    admitted = p.admitted_evidence
    question = admitted.evidence.questions[0]
    block = question.blocks[0]
    if corruption == "questions":
        object.__setattr__(admitted.evidence, "questions", (question,) * 4000)
    elif corruption == "blocks":
        object.__setattr__(question, "blocks", (block,) * 4000)
    elif corruption == "warnings":
        object.__setattr__(question, "warnings", ("warn",) * 4000)
    elif corruption == "aggregate_blocks":
        object.__setattr__(admitted.effective_policy_snapshot, "max_total_blocks", 1)
        object.__setattr__(question, "blocks", (block, replace(block, block_id="OTHER")))
    elif corruption == "block_content":
        object.__setattr__(block, "content", "x" * 600)
    elif corruption == "aggregate_content":
        object.__setattr__(question, "blocks", tuple(
            replace(block, block_id=f"EVIDENCE-{index + 2}", content="x" * 400)
            for index in range(3)
        ))
    elif corruption == "bbox":
        object.__setattr__(block.location, "bbox", (0,) * 4000)
    elif corruption == "policy":
        object.__setattr__(admitted.effective_policy_snapshot, "max_questions", 0)
    else:
        class Foreign:
            def __len__(self):
                raise AssertionError("foreign len callback ran")
            def __iter__(self):
                raise AssertionError("foreign iter callback ran")
        object.__setattr__(question, "blocks", Foreign())

    reconstructed = []
    old_question = evidence_contracts.QuestionEvidence.__post_init__
    old_block = evidence_contracts.EvidenceBlock.__post_init__
    def track_question(self):
        reconstructed.append("question")
        return old_question(self)
    def track_block(self):
        reconstructed.append("block")
        return old_block(self)
    monkeypatch.setattr(evidence_contracts.QuestionEvidence, "__post_init__", track_question)
    monkeypatch.setattr(evidence_contracts.EvidenceBlock, "__post_init__", track_block)
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(prepared=p, choice_authority=authority, selection=selection)
    assert not reconstructed, "Reconstruction began before normalized-wire limit/shape rejection"


def test_near_admitted_evidence_resource_limit_still_accepts_valid_choice():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    p = _prepared()
    authority, selection = _choice(p)
    policy = p.admitted_evidence.effective_policy_snapshot
    object.__setattr__(p.admitted_evidence, "effective_policy_snapshot", replace(
        policy,
        max_questions=1, max_blocks_per_question=1, max_total_blocks=1,
        max_total_content_characters=1, max_block_content_characters=1,
        max_warnings_per_question=1, max_location_coordinates=1,
    ))
    bound = bind_choice_evaluation_inputs(prepared=p, choice_authority=authority, selection=selection)
    assert bound.selection.selected_option_id == "B"
    assert bound.prepared.admitted_evidence.evidence.questions[0].blocks[0].content == "B"


def test_unexpected_programming_failure_is_not_disguised_as_invalid_input(monkeypatch):
    import grading.integration.choice_binding as binding
    p = _prepared()
    authority, selection = _choice(p)
    fault = RuntimeError("unexpected trusted implementation failure")
    def fail(_):
        raise fault
    monkeypatch.setattr(binding, "compiled_authority_fingerprint", fail)
    with pytest.raises(RuntimeError) as caught:
        binding.bind_choice_evaluation_inputs(
            prepared=p, choice_authority=authority, selection=selection,
        )
    assert caught.value is fault


@pytest.mark.parametrize("surface", ("submission", "choice_authority", "prepared_evidence"))
def test_ambient_expected_error_never_exposes_caller_exception(surface):
    """Use the frozen question evidence binding ambient-context privacy rule, not just clean calls."""
    import traceback
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    prepared = _prepared()
    authority, selection = _choice(prepared)
    if surface == "submission":
        selection = replace(selection, submission_ref="OTHER-SUBMISSION")
    elif surface == "choice_authority":
        authority = replace(authority, compiled_authority_hash="0" * 64)
    else:
        question = prepared.admitted_evidence.evidence.questions[0]
        block = question.blocks[0]
        object.__setattr__(question, "blocks", (block, replace(block)))
    private = "PRIVATE_STUDENT_ANSWER_4928"
    with pytest.raises(ChoiceInputBindingError) as captured:
        try:
            raise ValueError(private)
        except ValueError:
            bind_choice_evaluation_inputs(
                prepared=prepared, choice_authority=authority, selection=selection,
            )
    error = captured.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert not error.__notes__ if hasattr(error, "__notes__") else True
    assert private not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("field", (
    "submission_ref", "ocr_provenance", "source_artifact_ref",
    "question_id", "answer_scope_ref", "block_id", "language", "asset_ref",
))
def test_all_admitted_text_limits_checked_before_child_construction(field, monkeypatch):
    """Existing normalized OCR evidence admission limits must be checked before any nested record rebuild."""
    from grading.contracts import evidence as evidence_contracts
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    prepared = _prepared()
    authority, selection = _choice(prepared)
    admitted = prepared.admitted_evidence
    evidence = admitted.evidence
    question = evidence.questions[0]
    block = question.blocks[0]
    policy = admitted.effective_policy_snapshot
    if field in ("submission_ref", "ocr_provenance"):
        target = evidence
    elif field == "source_artifact_ref":
        target = admitted
    elif field in ("question_id", "answer_scope_ref"):
        target = question
    else:
        target = block
    limit = (
        policy.max_metadata_text_characters
        if field in ("language", "asset_ref")
        else policy.max_identifier_characters
    )
    object.__setattr__(target, field, "X" * (limit + 1))

    calls = []
    for cls in (
        evidence_contracts.EvidenceBlock,
        evidence_contracts.QuestionEvidence,
        evidence_contracts.AnswerEvidenceBundle,
    ):
        original = cls.__post_init__
        def instrument(self, original=original, cls=cls):
            calls.append(cls.__name__)
            return original(self)
        monkeypatch.setattr(cls, "__post_init__", instrument)
    with pytest.raises(ChoiceInputBindingError):
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )
    assert not calls, "Evidence child constructors ran before admitted text limit rejection"


def test_oversized_duplicate_identifier_never_reaches_bundle_constructor(monkeypatch):
    from grading.contracts import evidence as evidence_contracts
    from grading.integration.choice_binding import (
        ChoiceInputBindingError, bind_choice_evaluation_inputs,
    )
    prepared = _prepared()
    authority, selection = _choice(prepared)
    question = prepared.admitted_evidence.evidence.questions[0]
    block = question.blocks[0]
    huge_id = "PRIVATE_" + "X" * 1_000_000
    object.__setattr__(block, "block_id", huge_id)
    object.__setattr__(question, "blocks", (block, block))
    called = []
    original = evidence_contracts.AnswerEvidenceBundle.__post_init__
    def track(self):
        called.append(True)
        return original(self)
    monkeypatch.setattr(evidence_contracts.AnswerEvidenceBundle, "__post_init__", track)
    with pytest.raises(ChoiceInputBindingError) as captured:
        bind_choice_evaluation_inputs(
            prepared=prepared, choice_authority=authority, selection=selection,
        )
    assert not called
    assert huge_id not in str(captured.value)


def test_preflight_accepts_exact_identifier_and_metadata_lengths():
    from grading.integration.choice_binding import bind_choice_evaluation_inputs
    prepared = _prepared()
    authority, selection = _choice(prepared)
    admitted = prepared.admitted_evidence
    policy = admitted.effective_policy_snapshot
    question = admitted.evidence.questions[0]
    block = question.blocks[0]
    exact_id = "I" * policy.max_identifier_characters
    exact_metadata = "L" * policy.max_metadata_text_characters
    object.__setattr__(block, "block_id", exact_id)
    object.__setattr__(block, "language", exact_metadata)
    # Update the selection to reference the revalidated evidence block.
    selection = replace(selection, evidence_refs=(exact_id,))
    result = bind_choice_evaluation_inputs(
        prepared=prepared, choice_authority=authority, selection=selection,
    )
    assert result.prepared.admitted_evidence.evidence.questions[0].blocks[0].block_id == exact_id
    assert result.prepared.admitted_evidence.evidence.questions[0].blocks[0].language == exact_metadata
