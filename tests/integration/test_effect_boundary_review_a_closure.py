"""Independent A1/A2/A3 regressions at the reusable effect and install owners.

The fixtures simulate conditional durability; they do NOT establish an
institution-issued grant or real backend atomicity.
"""
from dataclasses import replace

import pytest

from grading.integration.joint_effect_authority import (
    ConditionalEffectClaim, GradingEffectKind, JointEffectAdmission,
)
from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from tests.integration.test_joint_effect_time_authority_contract import components
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_production_paper_operations import _root


@pytest.mark.parametrize('missing', ['both', 'original', 'grant'])
def test_retry_cannot_omit_either_original_absence_or_source_grant(components, missing):
    owner, req, _ = components
    # No authority is supplied for an actual retry; any of these partial
    # combinations must be rejected at construction, before owner contact.
    from grading.integration.paper_retry_recovery import (
        OriginalPaperRecovery, OriginalPaperRecoveryState,
    )
    from grading.integration.paper_retry_claim import AuthorizedPaperRetry
    if missing == 'both':
        values = {}
    else:
        values = ({'retry_grant': object()} if missing == 'original' else
                  {'original_retry': OriginalPaperRecovery(OriginalPaperRecoveryState.ABSENCE_REPORTED)})
    with pytest.raises(ValueError, match='RETRY|original|purpose'):
        ConditionalEffectClaim(req.authority, req.preparation,
                            GradingEffectKind.RETRY_F25, **values)
    assert owner.claim_effects == []


@pytest.mark.parametrize('field', [
    'actor_ref', 'approval_ref', 'approval_revision', 'selection_decision_ref',
    'selection_revision', 'source_revision', 'readiness_revision',
])
def test_first_rejects_substituted_selected_paper_header(components, field):
    owner, req, _ = components
    plan = replace(req.first_permission.plan, **{field: 'FOREIGN-OR-STALE'})
    permission = replace(req.first_permission, plan=plan)
    with pytest.raises(ValueError, match='FIRST|paper|permission'):
        ConditionalEffectClaim(req.authority, req.preparation,
            GradingEffectKind.FIRST_F25, first_permission=permission)
    assert owner.claim_effects == []


@pytest.mark.parametrize('field', [
    'family', 'source_artifact_ref', 'evidence_scope_ref', 'answer_region_ref',
    'source_revision', 'provenance_ref',
])
def test_first_rejects_substituted_selected_question(components, field):
    owner, req, _ = components
    plan = req.first_permission.plan
    question = replace(plan.questions[0], **{field: 'FOREIGN-OR-STALE'})
    altered_plan = replace(plan, questions=(question, *plan.questions[1:]))
    permission = replace(req.first_permission, plan=altered_plan)
    with pytest.raises(ValueError, match='FIRST|paper|permission'):
        ConditionalEffectClaim(req.authority, req.preparation,
            GradingEffectKind.FIRST_F25, first_permission=permission)
    assert owner.claim_effects == []


class _HostileHash:
    def __hash__(self):
        raise AssertionError('foreign hash executed')


@pytest.mark.parametrize('hostile', [[], _HostileHash(), 'FIRST', None])
def test_installer_rejects_foreign_kind_before_foreign_hash_or_effect(hostile):
    cas, plan, _, physical, _, f25, provider, store, conditional = connected('DIRECT')
    lifecycle = ProductionPaperLifecycle(
        cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    with pytest.raises(ValueError, match='operation selection'):
        _root(lifecycle=lifecycle, plan=plan,
              kinds=(PaperOperationKind.FIRST, hostile))
    assert physical.claims == 0 and store.commits == 0
    assert not provider.requests


def test_unaltered_first_goes_through_conditional_owner(components):
    owner, request, _ = components
    from grading.integration.joint_effect_authority import EffectDecision
    result = JointEffectAdmission(owner=owner).claim(request=request)
    assert result.state is EffectDecision.COMMITTED
    assert len(owner.claim_effects) == 1


def test_regrade_rejects_substituted_f57_paper_after_real_connected_predecessor(monkeypatch):
    from tests.integration.test_joint_regrade_connected_execution import (
        connected_regrade, ConditionalRegradeFixture,
    )
    seen = []
    original = ConditionalRegradeFixture.claim_if_current

    def observe(self, *, request):
        seen.append(request)
        return original(self, request=request)

    monkeypatch.setattr(ConditionalRegradeFixture, 'claim_if_current', observe)
    service, plan, physical, store, *_ = connected_regrade(monkeypatch)
    assert service.execute_regrade(plan=plan).state.value == 'CAS_ACKNOWLEDGED'
    before_effects = physical.claims
    assert seen
    first = seen[0]
    grant = first.regrade_permission
    q = grant.plan.questions[0]
    bad_plan = replace(grant.plan, questions=(replace(q, provenance_ref='FOREIGN'),
                                              *grant.plan.questions[1:]))
    with pytest.raises(ValueError, match='regrade grant'):
        ConditionalEffectClaim(first.authority, first.preparation,
            GradingEffectKind.REGRADE_F25,
            regrade_permission=replace(grant, plan=bad_plan))
    assert physical.claims == before_effects


def test_retry_requires_positive_whole_original_absence_not_just_two_records(monkeypatch):
    from tests.integration.test_joint_retry_connected_execution import (
        connected_retry, ConditionalRetryFixture,
    )
    from grading.integration.paper_retry_recovery import OriginalPaperRecoveryState
    from grading.integration.whole_paper_attempt_custody import PaperRecoveryState
    seen = []
    original = ConditionalRetryFixture.claim_if_current

    def observe(self, *, request):
        seen.append(request)
        return original(self, request=request)

    monkeypatch.setattr(ConditionalRetryFixture, 'claim_if_current', observe)
    grade, plan, physical, atomic, store, *_ = connected_retry()
    assert grade.execute_and_commit(plan=plan).state.value == 'CAS_ACKNOWLEDGED'
    assert seen and physical.claims == 2 and store.commits == 1
    sample = seen[0]
    absent = sample.original_retry
    assert absent.state is OriginalPaperRecoveryState.ABSENCE_REPORTED
    variants = (
        replace(absent, state=OriginalPaperRecoveryState.UNKNOWN),
        replace(absent, details=replace(absent.details, questions=(
            replace(absent.details.questions[0], state=PaperRecoveryState.UNKNOWN),
            *absent.details.questions[1:]))),
    )
    for fake in variants:
        with pytest.raises(ValueError, match='RETRY'):
            ConditionalEffectClaim(sample.authority, sample.preparation,
                GradingEffectKind.RETRY_F25, original_retry=fake,
                retry_grant=sample.retry_grant)
    q = sample.retry_grant.new_plan.questions[0]
    swapped = replace(sample.retry_grant.new_plan, questions=(
        replace(q, provenance_ref='FOREIGN'),
        *sample.retry_grant.new_plan.questions[1:]))
    with pytest.raises(ValueError, match='RETRY'):
        ConditionalEffectClaim(sample.authority, sample.preparation,
            GradingEffectKind.RETRY_F25, original_retry=absent,
            retry_grant=replace(sample.retry_grant, new_plan=swapped))
    assert physical.claims == 2 and store.commits == 1
