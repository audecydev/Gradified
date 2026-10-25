"""Conservative teacher-edit preservation for regenerated rubric *drafts*.

This three-way reconciliation is an authoring operation, never an academic
approval. The caller must prove the baseline was the generator output from
which the teacher's current revision descended; local hashes do not prove
that provenance. Ambiguous concurrent changes block a proposed revision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from grading.rubric.errors import RubricLifecycleError, NoMeaningfulRubricChangeError
from grading.rubric.fingerprint import authoring_content_fingerprint
from grading.rubric.lifecycle import RubricAuthoringVersion, revise_version
from grading.rubric.models import (
    AuthoringCriterion, FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
)


class RegenerationDisposition(str, Enum):
    DRAFT = 'DRAFT'
    CONFLICT = 'CONFLICT'
    UNCHANGED = 'UNCHANGED'


@dataclass(frozen=True, slots=True)
class RegenerationProposal:
    disposition: RegenerationDisposition
    draft: RubricAuthoringVersion | None
    conflicts: tuple[str, ...]
    baseline_content_hash: str
    teacher_content_hash: str
    proposed_content_hash: str | None

    @property
    def authorizes_activation(self) -> bool:
        return False

    @property
    def authorizes_grading(self) -> bool:
        return False


def _three_way(base: object, teacher: object, regenerated: object):
    """Preserve edits unless generator independently changes the same item."""
    if teacher == base:
        return regenerated, False
    if regenerated == base or regenerated == teacher:
        return teacher, False
    return None, True


def _criteria_by_id(items: tuple[AuthoringCriterion, ...], field: str):
    if type(items) is not tuple or any(type(c) is not AuthoringCriterion for c in items):
        raise RubricLifecycleError(f'{field} must contain exact criteria.')
    out = {}
    for c in items:
        if type(c.criterion_id) is not str or not c.criterion_id or c.criterion_id.strip() != c.criterion_id:
            raise RubricLifecycleError(f'{field} contains an invalid criterion identity.')
        if c.criterion_id in out:
            raise RubricLifecycleError(f'{field} has duplicate criterion identities.')
        out[c.criterion_id] = c
    return out




def _deletion_overlaps_authored_move(baseline: dict, deleting: dict,
                                     editing: dict) -> bool:
    """Detect a moved baseline criterion deleted by the other contributor.

    A criterion's authored position is relative to other baseline IDs. Check
    inversions *before* deleting IDs are projected away. Insertions alone are
    not baseline reorders. This is linear in the baseline sequence size.
    """
    baseline_positions = {key: i for i, key in enumerate(baseline)}
    deleted = baseline_positions.keys() - deleting.keys()
    if not deleted:
        return False
    edited_baseline = [key for key in editing if key in baseline_positions]
    largest_before = -1
    for key in edited_baseline:
        position = baseline_positions[key]
        if key in deleted and largest_before > position:
            return True
        largest_before = max(largest_before, position)
    smallest_after = len(baseline_positions)
    for key in reversed(edited_baseline):
        position = baseline_positions[key]
        if key in deleted and smallest_after < position:
            return True
        smallest_after = min(smallest_after, position)
    return False


def _reconciled_criterion_order(before: dict, teacher: dict, fresh: dict, reconciled: dict):
    """Three-way merge of the *entire* authored sequence, including additions.

    The common surviving baseline IDs determine whether an existing criterion
    was moved. Newly added IDs belong to an insertion gap bounded by surviving
    baseline IDs. Incompatible reorders, different insertions into the same
    gap, and insertions whose anchor gap was reversed all require review.
    Delete-versus-reorder collisions are checked before discarding deleted IDs;
    delete-versus-value-edit collisions are reconciled by the value merge.
    """
    if (_deletion_overlaps_authored_move(before, teacher, fresh)
            or _deletion_overlaps_authored_move(before, fresh, teacher)):
        return None
    surviving_old = set(before).intersection(reconciled)
    base_order = tuple(key for key in before if key in surviving_old)
    teacher_order = tuple(key for key in teacher if key in surviving_old)
    generator_order = tuple(key for key in fresh if key in surviving_old)
    # Every surviving base criterion must occur in both contributors; otherwise
    # the value-level reconciliation was violated and order is not admissible.
    if set(teacher_order) != surviving_old or set(generator_order) != surviving_old:
        return None
    teacher_moved = teacher_order != base_order
    generator_moved = generator_order != base_order
    if teacher_moved and generator_moved and teacher_order != generator_order:
        return None
    order = teacher_order if teacher_moved else generator_order

    def insertions(branch: dict):
        retained = tuple(key for key in branch if key in reconciled)
        groups = {}
        index = 0
        while index < len(retained):
            if retained[index] in surviving_old:
                index += 1
                continue
            start = index
            while index < len(retained) and retained[index] not in surviving_old:
                index += 1
            left = next((key for key in reversed(retained[:start]) if key in surviving_old), None)
            right = next((key for key in retained[index:] if key in surviving_old), None)
            group = retained[start:index]
            # Only an unchanged adjacent gap can be merged without relocating
            # the contributor's ordering intent (also handles start/end gaps).
            try:
                left_pos = order.index(left) if left is not None else -1
                right_pos = order.index(right) if right is not None else len(order)
            except ValueError:
                return None
            if right_pos != left_pos + 1 or (left, right) in groups:
                return None
            groups[left, right] = group
        return groups

    teacher_groups = insertions(teacher)
    generator_groups = insertions(fresh)
    if teacher_groups is None or generator_groups is None:
        return None
    all_groups = {}
    for gap in set(teacher_groups) | set(generator_groups):
        t = teacher_groups.get(gap, ())
        g = generator_groups.get(gap, ())
        if t and g and t != g:
            return None
        all_groups[gap] = t or g

    merged = []
    for i in range(len(order) + 1):
        left = order[i - 1] if i else None
        right = order[i] if i < len(order) else None
        merged.extend(all_groups.get((left, right), ()))
        if i < len(order):
            merged.append(order[i])
    # An insertion may appear in both contributors; ensure it was not merged
    # twice or positioned under incompatible gap identities.
    if len(merged) != len(reconciled) or set(merged) != set(reconciled):
        return None
    return tuple(merged)


def propose_regenerated_draft(*, baseline_generated: QuestionRubricAuthoringContent,
                               current_teacher: RubricAuthoringVersion,
                               newly_generated: QuestionRubricAuthoringContent,
                               finalized_question: FinalizedQuestionScoringBasis,
                               expected_current_hash: str,
                               expected_baseline_hash: str) -> RegenerationProposal:
    """Return a fresh unapproved draft, or exact conflicts; never auto-merge conflicts.

    Both expected hashes must be obtained from independently managed, qualified
    source records. They provide optimistic continuity, not source authentication
    by themselves. Never treat caller-supplied hashes as a school-issued grant.
    """
    if (type(baseline_generated) is not QuestionRubricAuthoringContent
            or type(current_teacher) is not RubricAuthoringVersion
            or type(newly_generated) is not QuestionRubricAuthoringContent
            or type(finalized_question) is not FinalizedQuestionScoringBasis
            or type(expected_current_hash) is not str
            or type(expected_baseline_hash) is not str
            or current_teacher.source_content_hash != expected_current_hash
            or authoring_content_fingerprint(baseline_generated) != expected_baseline_hash):
        raise RubricLifecycleError('Exact baseline/current/revision binding required.')
    if (current_teacher.finalized_question.question_id != finalized_question.question_id
            or baseline_generated.rubric_id != current_teacher.content.rubric_id
            or newly_generated.rubric_id != current_teacher.content.rubric_id
            or baseline_generated.policy_id != current_teacher.content.policy_id
            or newly_generated.policy_id != current_teacher.content.policy_id):
        raise RubricLifecycleError('Regeneration changes rubric, policy or question identity.')

    before = _criteria_by_id(baseline_generated.criteria, 'baseline')
    teacher = _criteria_by_id(current_teacher.content.criteria, 'teacher')
    fresh = _criteria_by_id(newly_generated.criteria, 'regenerated')
    missing = object()
    reconciled = {}
    conflicts = []
    for key in dict.fromkeys((*before, *teacher, *fresh)):
        candidate, collided = _three_way(before.get(key, missing),
                                         teacher.get(key, missing),
                                         fresh.get(key, missing))
        if collided:
            conflicts.append(f'criterion:{key}')
        elif candidate is not missing:
            reconciled[key] = candidate

    ordering = _reconciled_criterion_order(before, teacher, fresh, reconciled)
    if ordering is None:
        conflicts.append('criteria:order')
        ordering = ()
    replacement = {'criteria': tuple(reconciled[key] for key in ordering)}
    for field in ('minimum_score', 'positive_credit_dependencies', 'gates',
                  'caps', 'deductions', 'rounding'):
        candidate, collided = _three_way(getattr(baseline_generated, field),
                                         getattr(current_teacher.content, field),
                                         getattr(newly_generated, field))
        if collided:
            conflicts.append(f'policy:{field}')
        else:
            replacement[field] = candidate

    baseline_hash = authoring_content_fingerprint(baseline_generated)
    if conflicts:
        return RegenerationProposal(RegenerationDisposition.CONFLICT, None,
                                    tuple(sorted(conflicts)), baseline_hash,
                                    current_teacher.source_content_hash, None)
    from dataclasses import replace
    content = replace(current_teacher.content, **replacement)
    content_hash = authoring_content_fingerprint(content)
    try:
        draft = revise_version(current_teacher, finalized_question, content)
    except NoMeaningfulRubricChangeError:
        return RegenerationProposal(RegenerationDisposition.UNCHANGED, None, (),
                                    baseline_hash, current_teacher.source_content_hash,
                                    content_hash)
    return RegenerationProposal(RegenerationDisposition.DRAFT, draft, (),
                                baseline_hash, current_teacher.source_content_hash,
                                content_hash)
