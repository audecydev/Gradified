"""academic-bound physical claim original-issuance-bound physical attempt claim: real execution and failure order."""
from dataclasses import replace
import pytest
from grading.integration.attempt_authority import ClaimedAttemptAllocator, AttemptClaim
from grading.integration.academic_claim_binding import (
    AcademicPreclaimState, AcademicClaimPreparation, AcademicallyBoundClaim,
    AcademicClaimBindingRecovery, academic_intent, validate_binding_recovery,
)
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_cas import ProductionWholePaperCAS, PaperCASState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.contracts.job_state import GradingJobState
from tests.integration.test_whole_paper_choice_execution import _setup_two
from tests.integration.test_whole_paper_attempt_custody_original_operation import KnownRequests
from tests.integration.test_whole_paper_cas import Issuer, OriginalSource, Store
from tests.integration.test_attempt_authority import Issuer as F25Issuer


class QualifiedShapeAcademicBackend:
    """Conformance fixture, NOT evidence of a real durable/atomic backend."""
    def __init__(self, physical):
        self.physical = physical
        self.prepares = []
        self.bound_claims = []
        self.recovery_reads = []
        self.claimed = {}
        self.mode = 'GOOD'

    def prepare_original_binding(self, *, intent):
        self.prepares.append(intent)
        if self.mode == 'LOST_PREPARE':
            raise RuntimeError('PRIVATE store may have persisted preclaim')
        if self.mode == 'FOREIGN_PREPARE':
            return AcademicClaimPreparation(replace(intent, question_id='WRONG'),
                'BIND-'+intent.question_id, intent.issued_paper.approval_revision,
                AcademicPreclaimState.PREPARED)
        if self.mode == 'STALE_PREPARE':
            return AcademicClaimPreparation(intent, 'BIND-'+intent.question_id,
                'OLD-APPROVAL', AcademicPreclaimState.PREPARED)
        if self.mode == 'REJECT_PREPARE':
            return AcademicClaimPreparation(intent, 'BIND-'+intent.question_id,
                intent.issued_paper.approval_revision, AcademicPreclaimState.CONFLICT)
        return AcademicClaimPreparation(intent, 'BIND-'+intent.question_id,
            intent.issued_paper.approval_revision, AcademicPreclaimState.PREPARED)

    def claim_bound_fresh(self, *, preparation):
        self.bound_claims.append(preparation)
        claim = self.physical.claim_fresh_attempt(request=preparation.intent.original_request)
        self.claimed[preparation.intent.original_request.request_ref] = claim
        if self.mode == 'FOREIGN_BOUND':
            return AcademicallyBoundClaim(replace(preparation, binding_ref='OTHER'), claim)
        if self.mode == 'LOST_BOUND':
            raise RuntimeError('Claim physically occurred; response lost')
        return AcademicallyBoundClaim(preparation, claim)

    def reconcile_bound_attempt(self, *, request):
        from grading.integration.attempt_authority import AttemptClaimRecoveryFact, AttemptClaimRecoveryDisposition
        stored = self.claimed.get(request.request_ref)
        if stored is None:
            return AttemptClaimRecoveryFact(request, AttemptClaimRecoveryDisposition.NOT_RESERVED, None)
        return AttemptClaimRecoveryFact(request, AttemptClaimRecoveryDisposition.RESERVED, stored.reservation)

    def reconcile_original_binding(self, *, intent):
        self.recovery_reads.append(intent)
        matches = [i for i in self.prepares if i == intent]
        if not matches:
            return AcademicClaimBindingRecovery(intent, AcademicPreclaimState.INDETERMINATE, None)
        return AcademicClaimBindingRecovery(intent, AcademicPreclaimState.PREPARED,
            AcademicClaimPreparation(intent, 'BIND-'+intent.question_id,
                intent.issued_paper.approval_revision, AcademicPreclaimState.PREPARED))


class PerQuestionF25Issuer(F25Issuer):
    def identify_reservation_request(self, *, scope, family, runtime_id, runtime_version,
                                     implementation_ref, eligibility_policy_id,
                                     eligibility_policy_version):
        issued = super().identify_reservation_request(
            scope=scope, family=family, runtime_id=runtime_id,
            runtime_version=runtime_version, implementation_ref=implementation_ref,
            eligibility_policy_id=eligibility_policy_id,
            eligibility_policy_version=eligibility_policy_version)
        return replace(issued, request_ref='REQUEST-'+scope.question_id)


def setup_bound():
    original, plan, _, _, _, physical = _setup_two()
    backend = QualifiedShapeAcademicBackend(physical)
    allocator = ClaimedAttemptAllocator(
        issuer=PerQuestionF25Issuer(), store=physical,
        academic_store=backend, academic_max_questions=10,
        max_identifier_characters=128)
    root = ProductionWholePaperChoiceExecutor(
        contact=original._contact, correlation=original._correlation,
        handoff=original._handoff, attempts=allocator,
        max_identifier_characters=128, max_questions=10)
    return root, plan, physical, backend


def test_complete_paper_has_exact_preclaims_before_each_physical_attempt():
    root, plan, physical, backend = setup_bound()
    outcome = root.execute(plan=plan)
    assert outcome.state == 'COMPLETE', outcome.state
    assert physical.claims == 2
    assert [x.question_id for x in backend.prepares] == ['Q1', 'Q2']
    assert [x.intent.question_id for x in backend.bound_claims] == ['Q1', 'Q2']
    assert all(i.issued_paper == outcome.issued_paper for i in backend.prepares)
    assert all(t.academic_preparation is not None for t in outcome.contact_trace)


def test_c3a_strict_consumer_requires_the_genuine_c3b_preclaim():
    root, plan, physical, backend = setup_bound()
    custody = ProductionPaperAttemptCustody(executor=root, attempts=root._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    source = OriginalSource()
    issuer = Issuer(source)
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    cas = ProductionWholePaperCAS(custody=custody, issuer=issuer, original_source=source,
        store=Store(), legal_policy=policy, max_identifier_characters=128,
        max_questions=10, require_academic_preclaim=True)
    result = cas.execute_and_commit(plan=plan)
    assert result.state is PaperCASState.COMMITTED
    assert result.academic_binding_verified is True
    assert physical.claims == 2


@pytest.mark.parametrize('mode', ('LOST_PREPARE', 'FOREIGN_PREPARE', 'STALE_PREPARE',
                                  'REJECT_PREPARE'))
def test_bad_or_uncertain_preclaim_never_calls_physical_f25(mode):
    root, plan, physical, backend = setup_bound()
    backend.mode = mode
    result = root.execute(plan=plan)
    assert result.result is None and result.state != 'COMPLETE'
    assert physical.claims == 0 and backend.bound_claims == []
    assert result.contact_trace and result.contact_trace[0].request_ref == 'REQUEST-Q1'
    assert not result.contact_trace[0].reservation_validated


@pytest.mark.parametrize('mode', ('FOREIGN_BOUND', 'LOST_BOUND'))
def test_postclaim_contradiction_or_lost_reply_never_scores(mode):
    root, plan, physical, backend = setup_bound()
    backend.mode = mode
    result = root.execute(plan=plan)
    assert result.state == 'INDETERMINATE'
    assert result.result is None and physical.claims == 1
    assert len(backend.bound_claims) == 1
    assert result.contact_trace[0].original_f25_request is not None
    assert result.contact_trace[0].academic_preparation is not None
    assert not result.contact_trace[0].s1_verified


def test_binding_readonly_recovery_never_promotes_to_attempt_or_retry():
    root, plan, physical, backend = setup_bound()
    outcome = root.execute(plan=plan)
    original = outcome.contact_trace[0].academic_preparation.intent
    before = physical.claims
    fact = backend.reconcile_original_binding(intent=original)
    assert validate_binding_recovery(fact, original, 128).state is AcademicPreclaimState.PREPARED
    assert physical.claims == before


def test_unbound_legacy_c3a_does_not_pass_explicit_strict_gate():
    original, plan, _, _, _, physical = _setup_two()
    custody = ProductionPaperAttemptCustody(executor=original, attempts=original._attempts,
        request_source=KnownRequests(), max_identifier_characters=128, max_questions=10)
    source = OriginalSource()
    policy = LegalGradingTransitionPolicy('TEST-F57', 1,
        ((GradingJobState.SCORING, GradingJobState.REVIEW_REQUIRED),))
    with pytest.raises(ValueError, match='Strict paper CAS requires a bound'):
        ProductionWholePaperCAS(custody=custody, issuer=Issuer(source),
            original_source=source, store=Store(), legal_policy=policy,
            max_identifier_characters=128, max_questions=10,
            require_academic_preclaim=True)
    assert physical.claims == 0



def test_versioned_scoring_policy_revision_mismatch_blocks_physical_claim():
    root, plan, physical, backend = setup_bound()
    class WrongVersionStore(QualifiedShapeAcademicBackend):
        def prepare_original_binding(self, *, intent):
            # A source-visible policy version must not silently become another
            # approved rubric/policy identity during the durable preclaim.
            from dataclasses import replace
            wrong = replace(intent.scoring.expected_questions[0],
                scoring_policy_ref=replace(intent.scoring.expected_questions[0].scoring_policy_ref,
                    version=intent.scoring.expected_questions[0].scoring_policy_ref.version+1))
            object.__setattr__(intent.scoring, 'expected_questions',
                (wrong, *intent.scoring.expected_questions[1:]))
            return super().prepare_original_binding(intent=intent)
    bad = WrongVersionStore(physical)
    # Install a separate root; do not mutate an existing production installation.
    new = ClaimedAttemptAllocator(issuer=PerQuestionF25Issuer(), store=physical,
        academic_store=bad, academic_max_questions=10, max_identifier_characters=128)
    service = ProductionWholePaperChoiceExecutor(contact=root._contact,
        correlation=root._correlation, handoff=root._handoff,
        attempts=new, max_identifier_characters=128, max_questions=10)
    result = service.execute(plan=plan)
    assert result.result is None and result.state != 'COMPLETE'
    assert physical.claims == 0 and bad.bound_claims == []


def test_bound_claim_mutates_preparation_before_return_is_uncertain():
    root, plan, physical, backend = setup_bound()
    class MutatingReceiptBackend(QualifiedShapeAcademicBackend):
        def claim_bound_fresh(self, *, preparation):
            result = super().claim_bound_fresh(preparation=preparation)
            object.__setattr__(preparation, 'binding_ref', 'MUTATED-BINDING')
            return result
    bad = MutatingReceiptBackend(physical)
    allocator = ClaimedAttemptAllocator(issuer=PerQuestionF25Issuer(), store=physical,
        academic_store=bad, academic_max_questions=10, max_identifier_characters=128)
    service = ProductionWholePaperChoiceExecutor(contact=root._contact,
        correlation=root._correlation, handoff=root._handoff,
        attempts=allocator, max_identifier_characters=128, max_questions=10)
    result = service.execute(plan=plan)
    assert result.state == 'INDETERMINATE' and result.result is None
    assert physical.claims == 1


def test_bound_mode_uses_bound_store_for_physical_recovery_not_raw_f25_reader():
    root, plan, physical, backend = setup_bound()
    class BoundReadSpy(QualifiedShapeAcademicBackend):
        def __init__(self, physical):
            super().__init__(physical)
            self.bound_reads = 0
        def reconcile_bound_attempt(self, *, request):
            self.bound_reads += 1
            return super().reconcile_bound_attempt(request=request)
    source = BoundReadSpy(physical)
    allocator = ClaimedAttemptAllocator(issuer=PerQuestionF25Issuer(), store=physical,
        academic_store=source, academic_max_questions=10, max_identifier_characters=128)
    service = ProductionWholePaperChoiceExecutor(contact=root._contact,
        correlation=root._correlation, handoff=root._handoff,
        attempts=allocator, max_identifier_characters=128, max_questions=10)
    result = service.execute(plan=plan)
    assert result.state == 'COMPLETE'
    before = physical.claims
    q = result.contact_trace[0]
    r = q.original_f25_request
    recovered = allocator.reconcile_request(scope=r.scope, family=r.family,
        runtime_id=r.runtime_id, runtime_version=r.runtime_version,
        implementation_ref=r.implementation_ref,
        eligibility_policy_id=r.eligibility_policy_id,
        eligibility_policy_version=r.eligibility_policy_version,
        original_request=r)
    assert recovered.request == r and source.bound_reads == 1
    assert physical.claims == before
