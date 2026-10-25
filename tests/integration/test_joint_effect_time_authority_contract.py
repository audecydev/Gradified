"""source integrity checks/physical attempt claim/CAS effect-owner seam: conditional effects, not sequential preflights.

The in-memory owner below is a protocol conformance fixture, not an authentic
external school authorization or proof of distributed durability.
"""
from dataclasses import replace
from threading import Lock
import pytest

from grading.integration.academic_claim_binding import AcademicallyBoundClaim
from grading.integration.joint_effect_authority import (
    JointAuthoritySnapshot, ConditionalEffectClaim, ConditionalScoredCAS,
    ConditionalEffectClaimResponse, ConditionalCASResponse, GradingEffectKind,
    EffectDecision, JointEffectAdmission,
)
from tests.integration.test_academic_effect_preclaim import setup_bound


class ConditionalFixtureOwner:
    """Models one atomic compare-and-effect, deliberately NOT a real backend."""
    def __init__(self, q1_claim, academic_revision, runtime_revision):
        self.lock = Lock()
        self.q1_claim = q1_claim
        self.academic_revision = academic_revision
        self.runtime_revision = runtime_revision
        self.claim_effects = []
        self.cas_effects = []
        self.after_effect_exception = False
        self.malformed_receipt = False

    def change_academic(self):
        with self.lock:
            self.academic_revision = 'REV-REVOKED'

    def change_runtime(self):
        with self.lock:
            self.runtime_revision = 'RUNTIME-REVOKED'

    def current(self, authority):
        return (self.academic_revision == authority.academic.issued_paper.approval_revision
                and self.runtime_revision == authority.runtime.approval_ref)

    def claim_if_current(self, *, request):
        with self.lock:
            if not self.current(request.authority):
                return ConditionalEffectClaimResponse(request, EffectDecision.REJECTED)
            self.claim_effects.append(request)
            if self.after_effect_exception:
                raise RuntimeError('lost response after durable claim')
            bound = AcademicallyBoundClaim(request.preparation, self.q1_claim)
            if self.malformed_receipt:
                bound = replace(bound, preparation=replace(request.preparation, binding_ref='FOREIGN'))
            return ConditionalEffectClaimResponse(request, EffectDecision.COMMITTED, bound)

    def commit_if_current(self, *, request):
        with self.lock:
            if not self.current(request.authority):
                return ConditionalCASResponse(request, EffectDecision.REJECTED)
            self.cas_effects.append(request)
            if self.after_effect_exception:
                raise RuntimeError('lost response after durable CAS')
            receipt = request.original_transaction_ref if not self.malformed_receipt else 'FOREIGN'
            return ConditionalCASResponse(request, EffectDecision.COMMITTED, receipt)


@pytest.fixture
def components():
    # Establish genuine CHOICE scoring and physical attempt records from the
    # actual project implementation; only the conditional backend is a fixture.
    root, plan, physical, backend = setup_bound()
    verified = root._correlation.preflight(plan=plan)
    _, snap, _ = root._prepared(plan.questions[0].request, plan, verified.issuer_relation.questions[0])
    approved_runtime = snap[7]
    scored = root.execute(plan=plan)
    assert scored.state == 'COMPLETE' and physical.claims == 2
    prep = scored.contact_trace[0].academic_preparation
    actual_claim = backend.claimed[prep.intent.original_request.request_ref]
    authority = JointAuthoritySnapshot(prep.intent, approved_runtime, 128, 10)
    from tests.integration.test_paper_lifecycle_pre_effect import Permissions
    first_permission = Permissions().resolve_paper_execution_permission(plan=plan)
    request = ConditionalEffectClaim(authority, prep, GradingEffectKind.FIRST_F25,
                                  first_permission=first_permission)
    cas_request = ConditionalScoredCAS(authority, 'ORIGINAL-CAS-Q1', 'GENERATION-1', 'SCORE-Q1')
    owner = ConditionalFixtureOwner(actual_claim, prep.approval_revision,
                                    approved_runtime.approval_ref)
    return owner, request, cas_request


def test_valid_exact_effect_owner_conditional_claim_and_cas(components):
    owner, request, cas = components
    gate = JointEffectAdmission(owner=owner)
    first = gate.claim(request=request)
    assert first.state is EffectDecision.COMMITTED
    assert first.bound_claim.claim.request is request.authority.academic.original_request
    second = gate.commit(request=cas)
    assert second.state is EffectDecision.COMMITTED
    assert second.committed_transaction_ref == cas.original_transaction_ref
    assert len(owner.claim_effects) == len(owner.cas_effects) == 1


@pytest.mark.parametrize('revocation', ['academic', 'runtime'])
def test_revocation_at_effect_blocks_first_physical_claim(components, revocation):
    owner, request, _ = components
    getattr(owner, f'change_{revocation}')()
    result = JointEffectAdmission(owner=owner).claim(request=request)
    assert result.state is EffectDecision.REJECTED
    assert result.bound_claim is None and owner.claim_effects == []


@pytest.mark.parametrize('revocation', ['academic', 'runtime'])
def test_revocation_at_scored_cas_blocks_commit(components, revocation):
    owner, _, cas = components
    getattr(owner, f'change_{revocation}')()
    result = JointEffectAdmission(owner=owner).commit(request=cas)
    assert result.state is EffectDecision.REJECTED
    assert result.committed_transaction_ref is None and owner.cas_effects == []


@pytest.mark.parametrize('effect', ['claim', 'commit'])
def test_lost_response_preserves_possible_effect_without_retry(components, effect):
    owner, request, cas = components
    owner.after_effect_exception = True
    result = getattr(JointEffectAdmission(owner=owner), effect)(
        request=request if effect == 'claim' else cas)
    assert result.state is EffectDecision.UNKNOWN
    assert len(owner.claim_effects if effect == 'claim' else owner.cas_effects) == 1
    assert result.bound_claim is None if effect == 'claim' else result.committed_transaction_ref is None


@pytest.mark.parametrize('effect', ['claim', 'commit'])
def test_foreign_positive_receipt_is_not_promoted(components, effect):
    owner, request, cas = components
    owner.malformed_receipt = True
    result = getattr(JointEffectAdmission(owner=owner), effect)(
        request=request if effect == 'claim' else cas)
    assert result.state is EffectDecision.UNKNOWN
    assert len(owner.claim_effects if effect == 'claim' else owner.cas_effects) == 1


def test_foreign_runtime_approval_ref_or_f25_request_rejected_before_effect(components):
    owner, request, _ = components
    with pytest.raises(ValueError):
        JointAuthoritySnapshot(request.authority.academic,
            replace(request.authority.runtime, runtime_version='OTHER'), 128, 10)
    with pytest.raises(ValueError):
        ConditionalEffectClaim(request.authority,
            replace(request.preparation, binding_ref='UNRELATED'), GradingEffectKind.SCORED_CAS)
    assert not owner.claim_effects


def test_missing_effect_owner_is_not_assumed_safe():
    with pytest.raises(ValueError):
        JointEffectAdmission(owner=object())


def test_mutated_authority_during_effect_is_unknown_even_with_positive_receipt(components):
    owner, request, _ = components
    class MutatingOwner(ConditionalFixtureOwner):
        def claim_if_current(self, *, request):
            reply = super().claim_if_current(request=request)
            object.__setattr__(request.authority.runtime, 'approval_ref', 'RUNTIME-REPLACED')
            return reply
    adversarial = MutatingOwner(owner.q1_claim, owner.academic_revision,
                                owner.runtime_revision)
    result = JointEffectAdmission(owner=adversarial).claim(request=request)
    assert result.state is EffectDecision.UNKNOWN
    assert result.bound_claim is None and len(adversarial.claim_effects) == 1
