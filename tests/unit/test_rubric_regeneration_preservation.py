"""Real three-way rubric regeneration: preserve edits, never invent approval."""
from dataclasses import replace
import pytest
from grading.rubric.fingerprint import authoring_content_fingerprint
from grading.rubric.regeneration import RegenerationDisposition, propose_regenerated_draft
from grading.rubric.lifecycle import create_initial_version, revise_version, RubricLifecycleState
from grading.rubric.errors import RubricLifecycleError
from tests.support.rubric_authoring import simple_content, simple_basis, criterion, sd


def proposal(base, current, generated, *, expected_hash=None, basis=None):
    return propose_regenerated_draft(baseline_generated=base,
        current_teacher=current, newly_generated=generated,
        finalized_question=basis or simple_basis(),
        expected_current_hash=expected_hash or current.source_content_hash,
        expected_baseline_hash=authoring_content_fingerprint(base))


def test_preserves_teacher_criterion_while_admitting_unrelated_regenerated_criterion():
    base = simple_content()
    original = create_initial_version(simple_basis(), base)
    teacher = revise_version(original, simple_basis(), replace(base,
        criteria=(replace(base.criteria[0], evidence_requirement='Teacher evidence'),base.criteria[1])))
    regenerated = replace(base, criteria=(base.criteria[0], replace(base.criteria[1],
        operational_description='New generated C2')))
    result=proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.DRAFT
    assert result.conflicts == () and result.draft.state is RubricLifecycleState.DRAFT
    assert result.draft.content.criteria[0].evidence_requirement == 'Teacher evidence'
    assert result.draft.content.criteria[1].operational_description == 'New generated C2'
    assert result.draft.version == teacher.version+1
    assert result.draft.approval is None and not result.authorizes_activation and not result.authorizes_grading


def test_concurrent_edits_to_same_criterion_block_without_draft():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(), base),simple_basis(),replace(base,
        criteria=(replace(base.criteria[0], evidence_requirement='Teacher'),base.criteria[1])))
    fresh=replace(base, criteria=(replace(base.criteria[0], operational_description='Generator'),base.criteria[1]))
    result=proposal(base,teacher,fresh)
    assert result.disposition is RegenerationDisposition.CONFLICT
    assert result.draft is None and result.conflicts == ('criterion:C1',)


def test_teacher_added_criterion_is_not_silently_dropped():
    base=simple_content()
    added=criterion('C3',0)
    teacher=revise_version(create_initial_version(simple_basis(), base),simple_basis(),
        replace(base, criteria=(*base.criteria,added)))
    result=proposal(base,teacher,base)
    assert result.disposition is RegenerationDisposition.UNCHANGED
    assert result.draft is None and not result.authorizes_grading
    fresh=replace(base,criteria=(replace(base.criteria[0], operational_description='Regen C1'),base.criteria[1]))
    result=proposal(base,teacher,fresh)
    assert result.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in result.draft.content.criteria) == ('C1','C2','C3')


def test_deleted_teacher_criterion_conflicts_with_generator_modification():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base, criteria=(base.criteria[1],)))
    fresh=replace(base,criteria=(replace(base.criteria[0], operational_description='Regen C1'),base.criteria[1]))
    out=proposal(base,teacher,fresh)
    assert out.disposition is RegenerationDisposition.CONFLICT and out.conflicts == ('criterion:C1',)


def test_generator_deletion_conflicts_with_teacher_modification():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,criteria=(replace(base.criteria[0], evidence_requirement='Teacher'),base.criteria[1])))
    fresh=replace(base,criteria=(base.criteria[1],))
    out=proposal(base,teacher,fresh)
    assert out.disposition is RegenerationDisposition.CONFLICT and out.conflicts == ('criterion:C1',)


def test_policy_concurrent_change_requires_reconfirmation():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,minimum_score=sd(1)))
    out=proposal(base,teacher,replace(base,minimum_score=sd(2)))
    assert out.disposition is RegenerationDisposition.CONFLICT
    assert out.conflicts == ('policy:minimum_score',)


def test_stale_teacher_version_rejected():
    base=simple_content()
    cur=create_initial_version(simple_basis(),base)
    with pytest.raises(RubricLifecycleError):
        proposal(base,cur,replace(base,criteria=(criterion('NEW',1),)),expected_hash='0'*64)


def test_identity_substitution_rejected():
    base=simple_content()
    cur=create_initial_version(simple_basis(),base)
    with pytest.raises(RubricLifecycleError):
        proposal(base,cur,replace(base,rubric_id='FOREIGN'))
    with pytest.raises(RubricLifecycleError):
        proposal(base,cur,base,basis=simple_basis(question_id='FOREIGN'))


def test_duplicate_criterion_id_rejected_even_with_same_values():
    base=simple_content()
    cur=create_initial_version(simple_basis(),base)
    with pytest.raises(RubricLifecycleError):
        proposal(base,cur,replace(base,criteria=(base.criteria[0],base.criteria[0])))


def test_unchanged_regeneration_does_not_generate_fake_version():
    base=simple_content()
    cur=create_initial_version(simple_basis(),base)
    out=proposal(base,cur,base)
    assert out.disposition is RegenerationDisposition.UNCHANGED and out.draft is None


def test_source_max_marks_change_requires_new_unapproved_version():
    base=simple_content()
    cur=create_initial_version(simple_basis(),base)
    out=proposal(base,cur,base,basis=simple_basis(max_marks=6))
    assert out.disposition is RegenerationDisposition.DRAFT
    assert out.draft.state is RubricLifecycleState.DRAFT and out.draft.approval is None
    assert out.draft.finalized_question.max_marks == sd(6)


def test_stale_generator_baseline_hash_blocks_before_merge():
    base=simple_content()
    current=create_initial_version(simple_basis(), base)
    with pytest.raises(RubricLifecycleError):
        propose_regenerated_draft(baseline_generated=base, current_teacher=current,
            newly_generated=base, finalized_question=simple_basis(),
            expected_current_hash=current.source_content_hash,
            expected_baseline_hash='0'*64)


def test_teacher_only_criterion_reorder_is_preserved_without_fake_draft():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,criteria=tuple(reversed(base.criteria))))
    out=proposal(base,teacher,base)
    assert out.disposition is RegenerationDisposition.UNCHANGED
    assert out.draft is None


def test_teacher_reorder_survives_unrelated_generated_text_change():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,criteria=tuple(reversed(base.criteria))))
    new=replace(base,criteria=(replace(base.criteria[0], evidence_requirement='New generated C1'),base.criteria[1]))
    out=proposal(base,teacher,new)
    assert out.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in out.draft.content.criteria)==('C2','C1')
    assert out.draft.content.criteria[1].evidence_requirement=='New generated C1'


def test_generator_only_reorder_remains_valid_when_teacher_did_not_reorder():
    base=simple_content()
    teacher=create_initial_version(simple_basis(),base)
    new=replace(base,criteria=tuple(reversed(base.criteria)))
    out=proposal(base,teacher,new)
    assert out.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in out.draft.content.criteria)==('C2','C1')


def test_incompatible_concurrent_teacher_and_generator_reorder_is_conflict():
    base=simple_content()
    base=replace(base,criteria=(*base.criteria,criterion('C3',0)))
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,criteria=(base.criteria[2],base.criteria[0],base.criteria[1])))
    new=replace(base,criteria=(base.criteria[1],base.criteria[0],base.criteria[2]))
    out=proposal(base,teacher,new)
    assert out.disposition is RegenerationDisposition.CONFLICT
    assert out.conflicts == ('criteria:order',)
    assert out.draft is None


def test_teacher_front_insertion_is_preserved_when_generator_unchanged():
    base = simple_content()
    teacher_content = replace(base, criteria=(criterion('C3', 0), *base.criteria))
    teacher = revise_version(create_initial_version(simple_basis(), base),
                             simple_basis(), teacher_content)
    out = proposal(base, teacher, base)
    assert out.disposition is RegenerationDisposition.UNCHANGED
    assert out.draft is None


def test_teacher_middle_insertion_survives_unrelated_generator_change():
    base = simple_content()
    teacher_content = replace(base, criteria=(base.criteria[0], criterion('C3', 0),
                                               base.criteria[1]))
    teacher = revise_version(create_initial_version(simple_basis(), base),
                             simple_basis(), teacher_content)
    generated = replace(base, criteria=(replace(base.criteria[0],
        evidence_requirement='Generated change'), base.criteria[1]))
    out = proposal(base, teacher, generated)
    assert out.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in out.draft.content.criteria) == ('C1', 'C3', 'C2')
    assert out.draft.content.criteria[0].evidence_requirement == 'Generated change'


def test_generator_front_insertion_is_preserved_when_teacher_unchanged():
    base = simple_content()
    out = proposal(base, create_initial_version(simple_basis(), base),
                   replace(base, criteria=(criterion('C3', 0), *base.criteria)))
    assert out.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in out.draft.content.criteria) == ('C3', 'C1', 'C2')


def test_concurrent_different_insertions_into_same_gap_conflict():
    base = simple_content()
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(criterion('C3', 0), *base.criteria)))
    generated = replace(base, criteria=(criterion('C4', 0), *base.criteria))
    out = proposal(base, teacher, generated)
    assert out.disposition is RegenerationDisposition.CONFLICT
    assert out.conflicts == ('criteria:order',) and out.draft is None


def test_independent_insertions_in_different_gaps_preserve_both_positions():
    base = simple_content()
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(criterion('C3', 0), *base.criteria)))
    generated = replace(base, criteria=(*base.criteria, criterion('C4', 0)))
    out = proposal(base, teacher, generated)
    assert out.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in out.draft.content.criteria) == ('C3', 'C1', 'C2', 'C4')


def test_generator_deletion_conflicts_with_teacher_move_of_deleted_criterion():
    base = simple_content()
    base = replace(base, criteria=(*base.criteria, criterion('C3', 0)))
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(base.criteria[1], base.criteria[0], base.criteria[2])))
    regenerated = replace(base, criteria=(base.criteria[0], base.criteria[2]))
    result = proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.CONFLICT
    assert result.conflicts == ('criteria:order',) and result.draft is None


def test_teacher_deletion_conflicts_with_generator_move_of_deleted_criterion():
    base = simple_content()
    base = replace(base, criteria=(*base.criteria, criterion('C3', 0)))
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(base.criteria[0], base.criteria[2])))
    regenerated = replace(base, criteria=(base.criteria[1], base.criteria[0], base.criteria[2]))
    result = proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.CONFLICT
    assert result.conflicts == ('criteria:order',) and result.draft is None


def test_delete_unaffected_criterion_and_reorder_survivors_remains_valid():
    base = simple_content()
    base = replace(base, criteria=(*base.criteria, criterion('C3', 0), criterion('C4', 0)))
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(base.criteria[1], base.criteria[0], base.criteria[2], base.criteria[3])))
    regenerated = replace(base, criteria=base.criteria[:3])
    result = proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in result.draft.content.criteria) == ('C2','C1','C3')


def test_delete_unaffected_criterion_with_teacher_insertion_preserves_position():
    base = simple_content()
    base = replace(base, criteria=(*base.criteria, criterion('C3', 0)))
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(base.criteria[0], criterion('NEW', 0), base.criteria[1], base.criteria[2])))
    regenerated = replace(base, criteria=base.criteria[:2])
    result = proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in result.draft.content.criteria) == ('C1','NEW','C2')


def test_reorder_relative_to_deleted_anchor_is_conflict_even_with_insertions():
    base = simple_content()
    base = replace(base, criteria=(*base.criteria, criterion('C3', 0)))
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=(base.criteria[1], criterion('NEW', 0), base.criteria[0], base.criteria[2])))
    regenerated = replace(base, criteria=(base.criteria[0], base.criteria[2]))
    result = proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.CONFLICT
    assert result.conflicts == ('criteria:order',) and result.draft is None


def test_generator_can_reorder_survivors_when_teacher_deletes_unmoved_anchor():
    base = simple_content()
    base = replace(base, criteria=(*base.criteria, criterion('C3', 0), criterion('C4', 0)))
    teacher = revise_version(create_initial_version(simple_basis(), base),
        simple_basis(), replace(base, criteria=base.criteria[:3]))
    regenerated = replace(base, criteria=(base.criteria[1], base.criteria[0], base.criteria[2], base.criteria[3]))
    result = proposal(base, teacher, regenerated)
    assert result.disposition is RegenerationDisposition.DRAFT
    assert tuple(c.criterion_id for c in result.draft.content.criteria) == ('C2','C1','C3')
