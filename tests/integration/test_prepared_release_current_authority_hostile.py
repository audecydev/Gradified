"""Independent safety regression: prepared resolution must not bypass current
Gradified teacher review/authorized result release/governed scored-paper handoff preflight. Backend effect-time atomicity remains external.
"""
import pytest

from grading.integration.official_result_release import ReleasePurpose, ReleaseState
from grading.integration.teacher_review_journal import TeacherReviewRecoveryState
from tests.integration.test_prepared_release_resolution import scenario


@pytest.mark.parametrize('purpose', (ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK))
@pytest.mark.parametrize('revocation', ('academic_unavailable', 'teacher_journal_unavailable'))
def test_prepared_release_blocks_when_current_local_original_or_teacher_review_withdrawn(purpose, revocation):
    graph, _, resolver, new_owner, initial, before = scenario(
        purpose=purpose, mode='TIMEOUT_AFTER')
    if revocation == 'academic_unavailable':
        academic = graph[2]._handoff._original._readers[1].__self__
        academic.value = False
    else:
        graph[7].state = TeacherReviewRecoveryState.UNKNOWN
    result = new_owner().resolve_prepared(release=initial.intent.release_identity)
    assert result.state is ReleaseState.UNKNOWN
    assert result.receipt is None
    assert resolver.calls == []
    assert resolver.durable_effects == {}
    assert graph[1].calls == []


@pytest.mark.parametrize('purpose', (ReleasePurpose.OFFICIAL_RESULT, ReleasePurpose.STUDENT_FEEDBACK))
def test_prepared_release_still_allows_current_same_original_and_decision(purpose):
    graph, _, resolver, new_owner, initial, before = scenario(
        purpose=purpose, mode='TIMEOUT_AFTER')
    result = new_owner().resolve_prepared(release=initial.intent.release_identity)
    assert result.state is ReleaseState.RELEASED
    assert len(resolver.calls) == 1
    assert len(resolver.durable_effects) == 1
    assert not graph[1].calls
