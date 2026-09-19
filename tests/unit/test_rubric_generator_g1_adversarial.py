from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import os
from pathlib import Path
import subprocess
import sys

import pytest

import grading.rubric.generator as generator
from grading.contracts.scoring_decimal import ScoringDecimal
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
)


def sd(value: int | str) -> ScoringDecimal:
    return ScoringDecimal.from_raw(str(value))


def _criterion(
    criterion_id: str,
    marks: int,
    *,
    accepted_equivalents: tuple[str, ...] = (),
) -> AuthoringCriterion:
    return AuthoringCriterion(
        criterion_id=criterion_id,
        operational_description=f"  Preserve description for {criterion_id}.  ",
        evidence_requirement=f"  Preserve evidence for {criterion_id}.  ",
        performance_levels=(
            AuthoringPerformanceLevel("FULL", "  Fully met.  ", sd(marks)),
            AuthoringPerformanceLevel("NOT_MET", "  Not met.  ", sd(0)),
        ),
        accepted_equivalents=accepted_equivalents,
    )


def _source(*, minimum_score: int | str = 0) -> generator.RubricGenerationInput:
    return generator.RubricGenerationInput(
        finalized_question=FinalizedQuestionScoringBasis("Q1", sd(5)),
        question_text="  Exact question text.  ",
        model_answer_text="  Exact model answer text.  ",
        rubric_id="rubric-Q1",
        policy_id="policy-Q1",
        minimum_score=sd(minimum_score),
        rounding=AuthoringRoundingRule("ROUND-Q1", sd("0.5"), "ROUND_HALF_UP"),
    )


def _proposal(*, c1_marks: int = 2) -> generator.RubricGenerationProposal:
    condition_c1 = AuthoringCriterionCondition("C1", ("FULL",))
    condition_c2 = AuthoringCriterionCondition("C2", ("NOT_MET",))
    return generator.RubricGenerationProposal(
        criteria=(
            _criterion("C1", c1_marks, accepted_equivalents=("  equivalent A  ",)),
            _criterion("C2", 3, accepted_equivalents=("equivalent B",)),
        ),
        positive_credit_dependencies=(
            AuthoringPositiveCreditDependencyRule(
                "DEP-1",
                "C2",
                (condition_c1,),
            ),
        ),
        gates=(AuthoringGateRule("GATE-1", (condition_c1,), sd(4)),),
        caps=(AuthoringCapRule("CAP-1", (condition_c2,), sd(4)),),
        deductions=(AuthoringDeductionRule("DED-1", (condition_c2,), sd(1)),),
    )


def test_g1_public_surface_is_deliberately_narrow() -> None:
    assert set(generator.__all__) == {
        "RubricGenerationInput",
        "RubricGenerationProposal",
        "GeneratedRubricCandidate",
        "generate_rubric_candidate",
    }


def test_g1_fingerprint_schema_is_locked_to_every_current_material_model_field() -> None:
    assert {field.name for field in fields(generator.RubricGenerationInput)} == {
        "finalized_question",
        "question_text",
        "model_answer_text",
        "rubric_id",
        "policy_id",
        "minimum_score",
        "rounding",
    }
    assert {field.name for field in fields(FinalizedQuestionScoringBasis)} == {
        "question_id",
        "max_marks",
    }
    assert {field.name for field in fields(AuthoringRoundingRule)} == {
        "rule_id",
        "increment",
        "mode",
    }
    assert {field.name for field in fields(generator.RubricGenerationProposal)} == {
        "criteria",
        "positive_credit_dependencies",
        "gates",
        "caps",
        "deductions",
    }
    assert {field.name for field in fields(AuthoringCriterion)} == {
        "criterion_id",
        "operational_description",
        "evidence_requirement",
        "performance_levels",
        "accepted_equivalents",
    }
    assert {field.name for field in fields(AuthoringPerformanceLevel)} == {
        "level_id",
        "operational_description",
        "contribution",
    }
    assert {field.name for field in fields(AuthoringCriterionCondition)} == {
        "criterion_id",
        "allowed_level_ids",
    }
    assert {field.name for field in fields(AuthoringPositiveCreditDependencyRule)} == {
        "rule_id",
        "target_criterion_id",
        "prerequisite_conditions",
    }
    assert {field.name for field in fields(AuthoringGateRule)} == {
        "rule_id",
        "required_conditions",
        "failure_ceiling",
    }
    assert {field.name for field in fields(AuthoringCapRule)} == {
        "rule_id",
        "trigger_conditions",
        "ceiling",
    }
    assert {field.name for field in fields(AuthoringDeductionRule)} == {
        "rule_id",
        "trigger_conditions",
        "amount",
    }


def test_source_proposal_and_content_fingerprints_have_distinct_domains() -> None:
    source = _source()
    proposal = _proposal()
    base = generator.generate_rubric_candidate(source=source, proposal=proposal)

    changed_text = generator.generate_rubric_candidate(
        source=replace(source, question_text="Different question text."),
        proposal=proposal,
    )
    assert changed_text.source_fingerprint != base.source_fingerprint
    assert changed_text.proposal_fingerprint == base.proposal_fingerprint
    assert changed_text.content_fingerprint == base.content_fingerprint

    changed_policy = generator.generate_rubric_candidate(
        source=replace(source, minimum_score=sd(1)),
        proposal=proposal,
    )
    assert changed_policy.source_fingerprint != base.source_fingerprint
    assert changed_policy.proposal_fingerprint == base.proposal_fingerprint
    assert changed_policy.content_fingerprint != base.content_fingerprint

    changed_proposal = generator.generate_rubric_candidate(
        source=source,
        proposal=_proposal(c1_marks=1),
    )
    assert changed_proposal.source_fingerprint == base.source_fingerprint
    assert changed_proposal.proposal_fingerprint != base.proposal_fingerprint
    assert changed_proposal.content_fingerprint != base.content_fingerprint


def test_direct_candidate_constructor_rejects_cross_bound_provenance_forgery() -> None:
    source = _source()
    proposal = _proposal()
    base = generator.generate_rubric_candidate(source=source, proposal=proposal)

    changed_source = replace(source, minimum_score=sd(1))
    changed_source_candidate = generator.generate_rubric_candidate(
        source=changed_source,
        proposal=proposal,
    )
    with pytest.raises(ValueError, match="content does not match"):
        replace(
            base,
            source=changed_source,
            source_fingerprint=changed_source_candidate.source_fingerprint,
        )

    changed_proposal = _proposal(c1_marks=1)
    changed_proposal_candidate = generator.generate_rubric_candidate(
        source=source,
        proposal=changed_proposal,
    )
    with pytest.raises(ValueError, match="content does not match"):
        replace(
            base,
            proposal=changed_proposal,
            proposal_fingerprint=changed_proposal_candidate.proposal_fingerprint,
        )

    foreign_content = changed_source_candidate.content
    with pytest.raises(ValueError, match="content does not match"):
        replace(
            base,
            content=foreign_content,
            content_fingerprint=authoring_content_fingerprint(foreign_content),
        )

    with pytest.raises(ValueError, match="source_fingerprint"):
        replace(base, source_fingerprint="0" * 64)
    with pytest.raises(ValueError, match="proposal_fingerprint"):
        replace(base, proposal_fingerprint="0" * 64)
    with pytest.raises(ValueError, match="content_fingerprint"):
        replace(base, content_fingerprint="0" * 64)
    with pytest.raises(ValueError, match="generator_profile_version"):
        replace(base, generator_profile_version="2")


def test_generation_object_graph_is_deeply_immutable_under_supported_python_mutation() -> None:
    source = _source()
    proposal = _proposal()
    candidate = generator.generate_rubric_candidate(source=source, proposal=proposal)

    assert type(proposal.criteria) is tuple
    assert type(proposal.criteria[0].performance_levels) is tuple
    assert type(proposal.criteria[0].accepted_equivalents) is tuple
    assert type(proposal.positive_credit_dependencies) is tuple
    assert type(proposal.positive_credit_dependencies[0].prerequisite_conditions) is tuple
    assert type(proposal.positive_credit_dependencies[0].prerequisite_conditions[0].allowed_level_ids) is tuple

    with pytest.raises(FrozenInstanceError):
        source.finalized_question.question_id = "QX"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        source.rounding.mode = "ROUND_DOWN"  # type: ignore[union-attr,misc]
    with pytest.raises(FrozenInstanceError):
        proposal.criteria[0].criterion_id = "CX"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        proposal.criteria[0].performance_levels[0].contribution = sd(99)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        proposal.positive_credit_dependencies[0].prerequisite_conditions[0].criterion_id = "CX"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        proposal.criteria.append(_criterion("C3", 1))  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        proposal.criteria[0].accepted_equivalents.append("evil")  # type: ignore[attr-defined]
    with pytest.raises(FrozenInstanceError):
        candidate.source = source  # type: ignore[misc]


def test_exact_projection_preserves_full_trusted_policy_and_proposal_without_repair() -> None:
    source = _source()
    proposal = _proposal()
    candidate = generator.generate_rubric_candidate(source=source, proposal=proposal)

    expected = QuestionRubricAuthoringContent(
        rubric_id=source.rubric_id,
        policy_id=source.policy_id,
        minimum_score=source.minimum_score,
        criteria=proposal.criteria,
        positive_credit_dependencies=proposal.positive_credit_dependencies,
        gates=proposal.gates,
        caps=proposal.caps,
        deductions=proposal.deductions,
        rounding=source.rounding,
    )

    assert candidate.content == expected
    assert candidate.content.criteria == proposal.criteria
    assert candidate.content.positive_credit_dependencies == proposal.positive_credit_dependencies
    assert candidate.content.gates == proposal.gates
    assert candidate.content.caps == proposal.caps
    assert candidate.content.deductions == proposal.deductions
    assert candidate.content.rounding == source.rounding
    assert candidate.content.criteria[0].operational_description == "  Preserve description for C1.  "
    assert candidate.content.criteria[0].accepted_equivalents == ("  equivalent A  ",)


def test_public_boundaries_reject_mutable_or_wrong_runtime_shapes() -> None:
    source = _source()
    proposal = _proposal()

    with pytest.raises(ValueError, match="source must be an exact RubricGenerationInput"):
        generator.generate_rubric_candidate(source=object(), proposal=proposal)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="proposal must be an exact RubricGenerationProposal"):
        generator.generate_rubric_candidate(source=source, proposal=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="criteria must be a tuple"):
        generator.RubricGenerationProposal(
            criteria=list(proposal.criteria),  # type: ignore[arg-type]
            positive_credit_dependencies=proposal.positive_credit_dependencies,
            gates=proposal.gates,
            caps=proposal.caps,
            deductions=proposal.deductions,
        )


def test_fingerprints_are_identical_across_fresh_process_hash_seeds_for_full_graph() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    code = r"""
import grading.rubric.generator as g
from grading.contracts.scoring_decimal import ScoringDecimal
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
)

def sd(v):
    return ScoringDecimal.from_raw(str(v))

condition_c1 = AuthoringCriterionCondition("C1", ("FULL",))
condition_c2 = AuthoringCriterionCondition("C2", ("NOT_MET",))
source = g.RubricGenerationInput(
    finalized_question=FinalizedQuestionScoringBasis("Q1", sd(5)),
    question_text="  Exact question text.  ",
    model_answer_text="  Exact model answer text.  ",
    rubric_id="rubric-Q1",
    policy_id="policy-Q1",
    minimum_score=sd(0),
    rounding=AuthoringRoundingRule("ROUND-Q1", sd("0.5"), "ROUND_HALF_UP"),
)
proposal = g.RubricGenerationProposal(
    criteria=(
        AuthoringCriterion(
            "C1",
            "  Preserve description for C1.  ",
            "  Preserve evidence for C1.  ",
            (
                AuthoringPerformanceLevel("FULL", "  Fully met.  ", sd(2)),
                AuthoringPerformanceLevel("NOT_MET", "  Not met.  ", sd(0)),
            ),
            ("  equivalent A  ",),
        ),
        AuthoringCriterion(
            "C2",
            "  Preserve description for C2.  ",
            "  Preserve evidence for C2.  ",
            (
                AuthoringPerformanceLevel("FULL", "  Fully met.  ", sd(3)),
                AuthoringPerformanceLevel("NOT_MET", "  Not met.  ", sd(0)),
            ),
            ("equivalent B",),
        ),
    ),
    positive_credit_dependencies=(
        AuthoringPositiveCreditDependencyRule("DEP-1", "C2", (condition_c1,)),
    ),
    gates=(AuthoringGateRule("GATE-1", (condition_c1,), sd(4)),),
    caps=(AuthoringCapRule("CAP-1", (condition_c2,), sd(4)),),
    deductions=(AuthoringDeductionRule("DED-1", (condition_c2,), sd(1)),),
)
c = g.generate_rubric_candidate(source=source, proposal=proposal)
print(c.source_fingerprint)
print(c.proposal_fingerprint)
print(c.content_fingerprint)
print(c.generator_profile_version)
"""

    outputs: list[str] = []
    for seed in ("1", "777", "123456"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(repo_root / "src"), str(repo_root), env.get("PYTHONPATH", "")) if part
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
        outputs.append(result.stdout)

    assert outputs[0] == outputs[1] == outputs[2]


def test_candidate_content_graph_is_deeply_immutable() -> None:
    candidate = generator.generate_rubric_candidate(
        source=_source(),
        proposal=_proposal(),
    )
    content = candidate.content

    assert type(content.criteria) is tuple
    assert type(content.criteria[0].performance_levels) is tuple
    assert type(content.criteria[0].accepted_equivalents) is tuple
    assert type(content.positive_credit_dependencies) is tuple
    assert type(content.positive_credit_dependencies[0].prerequisite_conditions) is tuple
    assert type(content.positive_credit_dependencies[0].prerequisite_conditions[0].allowed_level_ids) is tuple
    assert type(content.gates) is tuple
    assert type(content.caps) is tuple
    assert type(content.deductions) is tuple

    with pytest.raises(FrozenInstanceError):
        content.rubric_id = "evil"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.criteria[0].criterion_id = "evil"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.criteria[0].performance_levels[0].contribution = sd(99)  # type: ignore[misc]
    with pytest.raises(AttributeError):
        content.criteria[0].accepted_equivalents.append("evil")  # type: ignore[attr-defined]
    with pytest.raises(FrozenInstanceError):
        content.positive_credit_dependencies[0].target_criterion_id = "evil"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.positive_credit_dependencies[0].prerequisite_conditions[0].criterion_id = "evil"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.gates[0].failure_ceiling = sd(99)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.caps[0].ceiling = sd(99)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        content.deductions[0].amount = sd(99)  # type: ignore[misc]
    assert content.rounding is not None
    with pytest.raises(FrozenInstanceError):
        content.rounding.mode = "ROUND_DOWN"  # type: ignore[misc]


def test_generation_reuses_only_immutable_inputs_and_does_not_rewrite_them() -> None:
    source = _source()
    proposal = _proposal()
    source_before = repr(source)
    proposal_before = repr(proposal)

    candidate = generator.generate_rubric_candidate(source=source, proposal=proposal)

    # Identity reuse is safe here because every reused object is frozen and every
    # nested collection is an exact tuple. Requiring defensive copies would add
    # allocation without improving this boundary's mutation safety.
    assert candidate.source is source
    assert candidate.proposal is proposal
    assert candidate.content.criteria is proposal.criteria
    assert candidate.content.positive_credit_dependencies is proposal.positive_credit_dependencies
    assert candidate.content.gates is proposal.gates
    assert candidate.content.caps is proposal.caps
    assert candidate.content.deductions is proposal.deductions
    assert candidate.content.rounding is source.rounding
    assert repr(source) == source_before
    assert repr(proposal) == proposal_before

def test_source_fingerprint_covers_every_current_nested_rounding_field() -> None:
    proposal = _proposal()
    source = _source()
    base = generator.generate_rubric_candidate(source=source, proposal=proposal)
    assert source.rounding is not None

    variants = (
        replace(source, rounding=replace(source.rounding, rule_id="ROUND-Q1-v2")),
        replace(source, rounding=replace(source.rounding, increment=sd("0.25"))),
        replace(source, rounding=replace(source.rounding, mode="ROUND_DOWN")),
    )
    for variant in variants:
        candidate = generator.generate_rubric_candidate(source=variant, proposal=proposal)
        assert candidate.source_fingerprint != base.source_fingerprint
        assert candidate.proposal_fingerprint == base.proposal_fingerprint
        assert candidate.content_fingerprint != base.content_fingerprint


def test_proposal_fingerprint_covers_every_current_nested_authoring_field() -> None:
    source = _source()
    base_proposal = _proposal()
    base = generator.generate_rubric_candidate(source=source, proposal=base_proposal)

    c1, c2 = base_proposal.criteria
    full, not_met = c1.performance_levels
    dependency = base_proposal.positive_credit_dependencies[0]
    dep_condition = dependency.prerequisite_conditions[0]
    gate = base_proposal.gates[0]
    gate_condition = gate.required_conditions[0]
    cap = base_proposal.caps[0]
    cap_condition = cap.trigger_conditions[0]
    deduction = base_proposal.deductions[0]
    deduction_condition = deduction.trigger_conditions[0]

    variants = (
        replace(base_proposal, criteria=(replace(c1, criterion_id="C1-v2"), c2)),
        replace(base_proposal, criteria=(replace(c1, operational_description="Changed description"), c2)),
        replace(base_proposal, criteria=(replace(c1, evidence_requirement="Changed evidence"), c2)),
        replace(base_proposal, criteria=(replace(c1, performance_levels=(replace(full, level_id="FULL-v2"), not_met)), c2)),
        replace(base_proposal, criteria=(replace(c1, performance_levels=(replace(full, operational_description="Changed level"), not_met)), c2)),
        replace(base_proposal, criteria=(replace(c1, performance_levels=(replace(full, contribution=sd(1)), not_met)), c2)),
        replace(base_proposal, criteria=(replace(c1, accepted_equivalents=("changed equivalent",)), c2)),
        replace(base_proposal, positive_credit_dependencies=(replace(dependency, rule_id="DEP-2"),)),
        replace(base_proposal, positive_credit_dependencies=(replace(dependency, target_criterion_id="C1"),)),
        replace(base_proposal, positive_credit_dependencies=(replace(dependency, prerequisite_conditions=(replace(dep_condition, criterion_id="C2"),)),)),
        replace(base_proposal, positive_credit_dependencies=(replace(dependency, prerequisite_conditions=(replace(dep_condition, allowed_level_ids=("NOT_MET",)),)),)),
        replace(base_proposal, gates=(replace(gate, rule_id="GATE-2"),)),
        replace(base_proposal, gates=(replace(gate, required_conditions=(replace(gate_condition, criterion_id="C2"),)),)),
        replace(base_proposal, gates=(replace(gate, required_conditions=(replace(gate_condition, allowed_level_ids=("NOT_MET",)),)),)),
        replace(base_proposal, gates=(replace(gate, failure_ceiling=sd(3)),)),
        replace(base_proposal, caps=(replace(cap, rule_id="CAP-2"),)),
        replace(base_proposal, caps=(replace(cap, trigger_conditions=(replace(cap_condition, criterion_id="C1"),)),)),
        replace(base_proposal, caps=(replace(cap, trigger_conditions=(replace(cap_condition, allowed_level_ids=("FULL",)),)),)),
        replace(base_proposal, caps=(replace(cap, ceiling=sd(3)),)),
        replace(base_proposal, deductions=(replace(deduction, rule_id="DED-2"),)),
        replace(base_proposal, deductions=(replace(deduction, trigger_conditions=(replace(deduction_condition, criterion_id="C1"),)),)),
        replace(base_proposal, deductions=(replace(deduction, trigger_conditions=(replace(deduction_condition, allowed_level_ids=("FULL",)),)),)),
        replace(base_proposal, deductions=(replace(deduction, amount=sd(2)),)),
    )

    assert len(variants) == 23
    seen: set[str] = set()
    for variant in variants:
        candidate = generator.generate_rubric_candidate(source=source, proposal=variant)
        assert candidate.source_fingerprint == base.source_fingerprint
        assert candidate.proposal_fingerprint != base.proposal_fingerprint
        assert candidate.content_fingerprint != base.content_fingerprint
        seen.add(candidate.proposal_fingerprint)

    assert len(seen) == len(variants)
