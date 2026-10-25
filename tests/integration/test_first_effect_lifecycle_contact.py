"""Hostile FIRST-operation transition effect-contact tests on unchanged exact 95db... source.

This is a local compositional-model gap, NOT evidence of real provider/database behavior.
"""
from grading.integration.paper_lifecycle import ProductionPaperLifecycle, PaperLifecycleState
from tests.integration.test_joint_first_claim_connected_execution import connected_cas, AtomicConditionalAcademicFixture, ReadOnlyCASPort
from tests.integration.test_paper_lifecycle_pre_effect import POLICY
from tests.integration.test_whole_paper_cas import OriginalSource, Issuer
from grading.integration.whole_paper_cas import ProductionWholePaperCAS



def make_lifecycle():
    cas, plan, physical, store, conditional_first, conditional_cas = connected_cas()
    source = conditional_cas.source
    conditional_first.f57_source = source
    original_source = OriginalSource()
    cas = ProductionWholePaperCAS(
        custody=cas._custody, issuer=Issuer(original_source), original_source=original_source,
        store=ReadOnlyCASPort(store), purpose_scored_store=conditional_cas,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10,
        require_academic_preclaim=True)
    lifecycle = ProductionPaperLifecycle(
        cas=cas, permission_source=source, legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    return lifecycle, plan, physical, store, conditional_first, conditional_cas, source


def test_control_real_first_source_grant_positive():
    svc, plan, physical, store, first, scored, source = make_lifecycle()
    out = svc.execute_first(plan=plan)
    assert out.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert physical.claims == 2 and store.commits == 1
    assert first.claim_contacts == 2 and scored.contacts == 1


def test_f57_revoke_during_first_physical_contact_blocks_first_claim(monkeypatch):
    original = AtomicConditionalAcademicFixture.claim_if_current
    source_ref = {}
    def revoke_first(self, *, request):
        source_ref['source'].mode = 'UNAVAILABLE'  # source revokes before physical effect
        return original(self, request=request)
    monkeypatch.setattr(AtomicConditionalAcademicFixture, 'claim_if_current', revoke_first)
    svc, plan, physical, store, first, scored, source = make_lifecycle()
    source_ref['source'] = source
    out = svc.execute_first(plan=plan)
    assert physical.claims == 0, (
        f'F57 revoked at physical FIRST effect but {physical.claims} real claims occurred; '
        f'CAS commits={store.commits}; operation state={out.state}')


def test_first_conditional_owner_receives_original_source_grant(monkeypatch):
    original = AtomicConditionalAcademicFixture.claim_if_current
    seen = []
    def inspect(self, *, request):
        seen.append(request)
        return original(self, request=request)
    monkeypatch.setattr(AtomicConditionalAcademicFixture, 'claim_if_current', inspect)
    svc, plan, physical, store, first, scored, source = make_lifecycle()
    outcome = svc.execute_first(plan=plan)
    assert outcome.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert seen and all(getattr(record, 'first_permission', None) is not None for record in seen), (
        'A source-issued initial-attempt lifecycle grant must not be supplied to the physical owner')


def test_strict_first_direct_executor_without_f57_denied_before_paper_source_or_f25():
    from tests.integration.test_joint_first_claim_connected_execution import connected_first
    engine, plan, physical, backend, first = connected_first()
    result = engine.execute(plan=plan)
    assert result.state == 'DENIED'
    assert physical.claims == 0 and first.claim_contacts == 0
    assert len(backend.bound_claims) == 0


def test_first_revoked_after_one_physical_claim_never_produces_scored_cas(monkeypatch):
    original = AtomicConditionalAcademicFixture.claim_if_current
    source_ref = {}
    def revoke_after_one(self, *, request):
        reply = original(self, request=request)
        if self.claim_contacts == 1:
            source_ref['source'].mode = 'UNAVAILABLE'
        return reply
    monkeypatch.setattr(AtomicConditionalAcademicFixture, 'claim_if_current', revoke_after_one)
    svc, plan, physical, store, first, scored, source = make_lifecycle()
    source_ref['source'] = source
    out = svc.execute_first(plan=plan)
    assert physical.claims == 1
    assert first.claim_contacts == 2
    assert scored.contacts == 0 and store.commits == 0
    assert out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED


def test_first_permission_mutated_after_physical_contact_is_unknown(monkeypatch):
    original = AtomicConditionalAcademicFixture.claim_if_current
    def mutate_original(self, *, request):
        reply = original(self, request=request)
        object.__setattr__(request.first_permission, 'approval_ref', 'FOREIGN-AFTER-CONTACT')
        return reply
    monkeypatch.setattr(AtomicConditionalAcademicFixture, 'claim_if_current', mutate_original)
    svc, plan, physical, store, first, scored, source = make_lifecycle()
    out = svc.execute_first(plan=plan)
    assert physical.claims == 1  # a physical effect may already exist
    assert first.claim_contacts == 1
    assert scored.contacts == 0 and store.commits == 0
    assert out.state is not PaperLifecycleState.CAS_ACKNOWLEDGED


def test_first_malformed_original_permission_rejected_before_equality():
    from dataclasses import replace
    import pytest
    class Poison:
        def __init__(self): self.calls = 0
        def __eq__(self, other):
            self.calls += 1
            raise RuntimeError('UNTRUSTED_EQ_SIDE_EFFECT')
    svc, plan, physical, store, first, scored, source = make_lifecycle()
    original = source.resolve_paper_execution_permission(plan=plan)
    poison = Poison()
    malformed = replace(original, plan=replace(
        plan, request=replace(plan.request, tenant_ref=poison)))
    with pytest.raises(ValueError):
        svc._cas.execute_and_commit(plan=plan, permission=malformed)
    assert poison.calls == 0
    assert physical.claims == 0 and first.claim_contacts == 0 and scored.contacts == 0
