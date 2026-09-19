from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import importlib
import importlib.util
import inspect

import pytest

from grading.contracts.authority import QuestionScoringAuthority
from grading.contracts.scoring_decimal import ScoringDecimal
from grading.rubric.compiler import CompiledRubricCandidate, compile_rubric_content
from grading.rubric.errors import RubricCompilationError
from grading.rubric.fingerprint import authoring_content_fingerprint
from grading.rubric.models import (
    AuthoringCapRule,
    AuthoringCriterion,
    AuthoringCriterionCondition,
    AuthoringDeductionRule,
    AuthoringGateRule,
    AuthoringPerformanceLevel,
    AuthoringPositiveCreditDependencyRule,
    AuthoringRoundingRule,
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
    RubricCompilationLimits,
)


def sd(value: int | str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def _generator_module():
    if importlib.util.find_spec("grading.rubric.generator") is None:
        pytest.skip("RubricGenerator G1 module is not implemented yet.")
    return importlib.import_module("grading.rubric.generator")


def _require_generator_api(*names: str):
    module = _generator_module()
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail("Missing RubricGenerator G1 required API: " + ", ".join(missing))
    return module


def _limits() -> RubricCompilationLimits:
    return RubricCompilationLimits(
        max_criteria=20,
        max_levels_per_criterion=10,
        max_accepted_equivalents_per_criterion=20,
        max_rules=50,
        max_conditions_per_rule=20,
        max_allowed_level_ids_per_condition=10,
        max_text_characters_per_field=2000,
        max_serialized_authority_bytes=100000,
        max_reconciliation_states=1000,
    )


def _criterion(criterion_id: str, marks: int) -> AuthoringCriterion:
    return AuthoringCriterion(
        criterion_id=criterion_id,
        operational_description=f"Award credit for {criterion_id}.",
        evidence_requirement=f"Evidence demonstrates {criterion_id}.",
        performance_levels=(
            AuthoringPerformanceLevel("FULL", "Fully met.", sd(marks)),
            AuthoringPerformanceLevel("NOT_MET", "Not met.", sd(0)),
        ),
    )


def _source_input(module, *, question_text: str = "Explain why 2 + 3 = 5.", model_answer_text: str = "Two objects plus three objects make five objects."):
    return module.RubricGenerationInput(
        finalized_question=FinalizedQuestionScoringBasis("Q1", sd(5)),
        question_text=question_text,
        model_answer_text=model_answer_text,
        rubric_id="rubric-Q1",
        policy_id="policy-Q1",
        minimum_score=sd(0),
        rounding=None,
    )


def _proposal(module):
    return module.RubricGenerationProposal(
        criteria=(
            _criterion("C1", 2),
            _criterion("C2", 3),
        ),
        positive_credit_dependencies=(),
        gates=(),
        caps=(),
        deductions=(),
    )


def test_generator_module_exists_at_the_architecture_boundary() -> None:
    assert importlib.util.find_spec("grading.rubric.generator") is not None


def test_g1_public_contract_surfaces_exist() -> None:
    module = _generator_module()
    for name in (
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "GeneratedRubricCandidate",
        "generate_rubric_candidate",
    ):
        assert hasattr(module, name), name


def test_generation_input_owns_trusted_source_and_policy_inputs_not_duplicate_question_authority() -> None:
    module = _require_generator_api("RubricGenerationInput")
    names = {field.name for field in fields(module.RubricGenerationInput)}

    assert {
        "finalized_question",
        "question_text",
        "model_answer_text",
        "rubric_id",
        "policy_id",
        "minimum_score",
        "rounding",
    } <= names
    assert "question_id" not in names
    assert "max_marks" not in names
    assert "scoring_semantics_version" not in names
    assert "teacher_approval" not in names
    assert "lifecycle_state" not in names


def test_provider_proposal_cannot_own_trusted_identity_marks_policy_or_approval() -> None:
    module = _require_generator_api("RubricGenerationProposal")
    names = {field.name for field in fields(module.RubricGenerationProposal)}

    assert names == {
        "criteria",
        "positive_credit_dependencies",
        "gates",
        "caps",
        "deductions",
    }
    assert {
        "question_id",
        "max_marks",
        "scoring_semantics_version",
        "rubric_id",
        "policy_id",
        "minimum_score",
        "rounding",
        "version",
        "approval",
        "teacher_ref",
        "state",
        "authority",
    }.isdisjoint(names)


def test_generate_api_requires_explicit_trusted_input_and_candidate_proposal() -> None:
    module = _require_generator_api("generate_rubric_candidate")
    signature = inspect.signature(module.generate_rubric_candidate)
    assert "source" in signature.parameters
    assert "proposal" in signature.parameters
    assert signature.parameters["source"].default is inspect.Parameter.empty
    assert signature.parameters["proposal"].default is inspect.Parameter.empty


def test_generated_candidate_is_not_compiled_approved_active_or_reducer_authority() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "GeneratedRubricCandidate",
        "generate_rubric_candidate",
    )
    candidate = module.generate_rubric_candidate(
        source=_source_input(module),
        proposal=_proposal(module),
    )

    assert type(candidate) is module.GeneratedRubricCandidate
    assert not isinstance(candidate, CompiledRubricCandidate)
    assert not isinstance(candidate, QuestionScoringAuthority)
    candidate_fields = {field.name for field in fields(candidate)}
    assert {"authority", "approval", "teacher_ref", "state"}.isdisjoint(candidate_fields)
    assert not hasattr(candidate, "authority")
    assert not hasattr(candidate, "approval")
    assert not hasattr(candidate, "activate")


def test_generated_content_uses_trusted_identity_and_policy_values_not_proposal_values() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    source = _source_input(module)
    proposal = _proposal(module)
    candidate = module.generate_rubric_candidate(source=source, proposal=proposal)

    assert candidate.content.rubric_id == source.rubric_id
    assert candidate.content.policy_id == source.policy_id
    assert candidate.content.minimum_score == source.minimum_score
    assert candidate.content.rounding == source.rounding
    assert candidate.content.criteria == proposal.criteria
    assert candidate.content.positive_credit_dependencies == proposal.positive_credit_dependencies
    assert candidate.content.gates == proposal.gates
    assert candidate.content.caps == proposal.caps
    assert candidate.content.deductions == proposal.deductions


def test_generation_preserves_school_question_and_model_answer_exactly_as_bound_source() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    source = _source_input(
        module,
        question_text="  Exact school question text.  ",
        model_answer_text="  Exact school model answer text.  ",
    )
    candidate = module.generate_rubric_candidate(source=source, proposal=_proposal(module))

    assert candidate.source == source
    assert candidate.source.question_text == "  Exact school question text.  "
    assert candidate.source.model_answer_text == "  Exact school model answer text.  "


def test_generated_candidate_can_feed_frozen_compiler_but_is_not_compiled_implicitly() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    candidate = module.generate_rubric_candidate(
        source=_source_input(module),
        proposal=_proposal(module),
    )

    assert type(candidate.content) is QuestionRubricAuthoringContent
    assert candidate.content_fingerprint == authoring_content_fingerprint(candidate.content)
    compiled = compile_rubric_content(
        candidate.content,
        finalized_question=candidate.source.finalized_question,
        version=1,
        limits=_limits(),
    )
    assert type(compiled) is CompiledRubricCandidate
    assert candidate is not compiled


def test_same_exact_source_and_proposal_replay_produces_same_generation_fingerprints() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    source = _source_input(module)
    proposal = _proposal(module)

    first = module.generate_rubric_candidate(source=source, proposal=proposal)
    second = module.generate_rubric_candidate(source=source, proposal=proposal)

    assert first == second
    assert first.source_fingerprint == second.source_fingerprint
    assert first.proposal_fingerprint == second.proposal_fingerprint
    assert first.content_fingerprint == second.content_fingerprint
    assert type(first.generator_profile_version) is str
    assert first.generator_profile_version


def test_source_fingerprint_is_sensitive_to_every_material_trusted_input() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    proposal = _proposal(module)
    source = _source_input(module)
    base = module.generate_rubric_candidate(source=source, proposal=proposal)

    variants = (
        replace(
            source,
            finalized_question=FinalizedQuestionScoringBasis("Q2", sd(5)),
        ),
        replace(
            source,
            finalized_question=FinalizedQuestionScoringBasis("Q1", sd(6)),
        ),
        replace(source, question_text="A changed school question."),
        replace(source, model_answer_text="A changed school model answer."),
        replace(source, rubric_id="rubric-Q1-v2"),
        replace(source, policy_id="policy-Q1-v2"),
        replace(source, minimum_score=sd(1)),
        replace(
            source,
            rounding=AuthoringRoundingRule(
                "ROUND-Q1",
                sd("0.5"),
                "ROUND_HALF_UP",
            ),
        ),
    )

    variant_fingerprints = {
        module.generate_rubric_candidate(source=variant, proposal=proposal).source_fingerprint
        for variant in variants
    }
    assert base.source_fingerprint not in variant_fingerprints
    assert len(variant_fingerprints) == len(variants)


def test_proposal_and_content_fingerprints_are_sensitive_to_every_candidate_dimension() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    source = _source_input(module)
    base_proposal = _proposal(module)
    base = module.generate_rubric_candidate(source=source, proposal=base_proposal)
    condition = AuthoringCriterionCondition("C1", ("FULL",))

    variants = (
        replace(
            base_proposal,
            criteria=(
                _criterion("C1", 1),
                _criterion("C2", 4),
            ),
        ),
        replace(
            base_proposal,
            positive_credit_dependencies=(
                AuthoringPositiveCreditDependencyRule("DEP-1", "C2", (condition,)),
            ),
        ),
        replace(
            base_proposal,
            gates=(AuthoringGateRule("GATE-1", (condition,), sd(4)),),
        ),
        replace(
            base_proposal,
            caps=(AuthoringCapRule("CAP-1", (condition,), sd(4)),),
        ),
        replace(
            base_proposal,
            deductions=(AuthoringDeductionRule("DED-1", (condition,), sd(1)),),
        ),
    )

    generated = tuple(
        module.generate_rubric_candidate(source=source, proposal=variant)
        for variant in variants
    )
    proposal_fingerprints = {candidate.proposal_fingerprint for candidate in generated}
    content_fingerprints = {candidate.content_fingerprint for candidate in generated}

    assert base.proposal_fingerprint not in proposal_fingerprints
    assert base.content_fingerprint not in content_fingerprints
    assert len(proposal_fingerprints) == len(variants)
    assert len(content_fingerprints) == len(variants)


def test_generation_contract_objects_are_immutable_after_provenance_binding() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "GeneratedRubricCandidate",
        "generate_rubric_candidate",
    )
    source = _source_input(module)
    proposal = _proposal(module)
    candidate = module.generate_rubric_candidate(source=source, proposal=proposal)

    with pytest.raises(FrozenInstanceError):
        source.rubric_id = "mutated-rubric"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        proposal.criteria = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        candidate.content = candidate.content  # type: ignore[misc]


def test_generator_preserves_invalid_proposal_and_frozen_compiler_rejects_it() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    source = _source_input(module)
    invalid_proposal = replace(
        _proposal(module),
        criteria=(
            _criterion("C1", 3),
            _criterion("C2", 3),
        ),
    )

    candidate = module.generate_rubric_candidate(
        source=source,
        proposal=invalid_proposal,
    )

    assert candidate.content.criteria == invalid_proposal.criteria
    with pytest.raises(RubricCompilationError):
        compile_rubric_content(
            candidate.content,
            finalized_question=source.finalized_question,
            version=1,
            limits=_limits(),
        )


def test_g1_generation_does_not_require_reference_context() -> None:
    module = _require_generator_api(
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "generate_rubric_candidate",
    )
    source = _source_input(module)
    candidate = module.generate_rubric_candidate(source=source, proposal=_proposal(module))
    assert candidate.content.criteria
