"""paper execution correlation issuer-correlation adversarial and positive contract tests."""
from dataclasses import replace
import pytest

from grading.contracts.paper_aggregation import GradingSpecRef
from grading.integration.trusted_preparation import PreparationRequest
from grading.integration.paper_readiness_admission import (
    PaperAdmissionRequest, AdmittedPaperPlan, AdmittedPaperQuestion,
)
from grading.integration.paper_execution_correlation import (
    IssuedPaperExecutionRelation, IssuedQuestionExecutionRelation,
    ProductionPaperExecutionCorrelation, PaperExecutionDenied,
    PaperExecutionContractError, PaperExecutionUnavailable,
)


def fixture():
    spec=GradingSpecRef('SPEC',1)
    req=PaperAdmissionRequest('T','S','RUN','SUB','EXAM','PAPER','SET',spec)
    questions=tuple(AdmittedPaperQuestion(
        PreparationRequest('T','S','RUN','SUB','EXAM',spec,f'Q{i}'),
        'CHOICE','ART','REV',f'SCOPE{i}',f'REGION{i}',f'OCR{i}') for i in (1,2))
    plan=AdmittedPaperPlan(req,'ACTOR','APP','AR','DEC','SR','REV','RR',questions)
    relation=IssuedPaperExecutionRelation(1,req,'ACTOR','SCHOOL','ISSUANCE','PAPER','SET','APP','AR','DEC','SR','REV','RR',
        tuple(IssuedQuestionExecutionRelation(q.request.question_id,q.family,q.source_artifact_ref,
            q.evidence_scope_ref,q.answer_region_ref,q.source_revision,q.provenance_ref,
            f'RUBRIC{i}',f'POLICY{i}') for i,q in enumerate(questions)))
    return plan,relation


class Issuer:
    def __init__(self, relation):
        self.relation=relation
        self.calls=0
        self.action=None
    def correlate_paper_execution(self, *, plan):
        self.calls+=1
        if self.action: self.action(plan)
        return self.relation


def composer(issuer):
    return ProductionPaperExecutionCorrelation(issuer=issuer,max_questions=5,max_identifier_characters=64)


def test_valid_multi_question_correlation_nonbearer():
    plan,rel=fixture(); port=Issuer(rel)
    result=composer(port).preflight(plan=plan)
    assert result.execution_state=='CORRELATED_CHOICE_ONLY'
    assert result.issuer_relation.questions[1].rubric_ref=='RUBRIC1'
    assert result.plan is not plan
    assert port.calls==1


@pytest.mark.parametrize('field,value', [('actor_ref','FOREIGN'),('paper_ref','OTHER'),('set_ref','OTHER'),
    ('approval_revision','OLD'),('selection_revision','OLD'),('source_revision','OLD'),
    ('readiness_revision','OLD'),('selection_decision_ref','OTHER')])
def test_foreign_global_authority_denied(field,value):
    plan,rel=fixture(); port=Issuer(replace(rel,**{field:value}))
    with pytest.raises(PaperExecutionDenied): composer(port).preflight(plan=plan)


@pytest.mark.parametrize('field,value', [('answer_region_ref','OTHER'),('source_artifact_ref','FOREIGN'),
    ('provenance_ref','OTHER'),('source_revision','OLD'),('evidence_scope_ref','OTHER'),
    ('family','DIRECT')])
def test_foreign_question_authority_denied(field,value):
    plan,rel=fixture(); q=replace(rel.questions[0],**{field:value})
    port=Issuer(replace(rel,questions=(q,rel.questions[1])))
    with pytest.raises(PaperExecutionDenied): composer(port).preflight(plan=plan)


def test_duplicate_and_missing_rejected():
    plan,rel=fixture()
    for questions in ((rel.questions[0],),(rel.questions[0],rel.questions[0])):
        with pytest.raises(PaperExecutionDenied):
            composer(Issuer(replace(rel,questions=questions))).preflight(plan=plan)


def test_callback_mutation_rejected():
    plan,rel=fixture(); issuer=Issuer(rel)
    issuer.action=lambda x: object.__setattr__(plan,'selection_revision','MUTATED')
    with pytest.raises(PaperExecutionDenied): composer(issuer).preflight(plan=plan)


def test_callback_mutates_argument_rejected():
    plan,rel=fixture(); issuer=Issuer(rel)
    issuer.action=lambda x: object.__setattr__(x,'source_revision','MUTATED')
    with pytest.raises(PaperExecutionDenied): composer(issuer).preflight(plan=plan)


def test_unavailable_and_foreign_record():
    plan,rel=fixture(); issuer=Issuer(rel)
    issuer.action=lambda x: (_ for _ in ()).throw(RuntimeError('secret'))
    with pytest.raises(PaperExecutionUnavailable,match='unavailable'):
        composer(issuer).preflight(plan=plan)
    issuer.action=None; issuer.relation={'fake':'issuer'}
    with pytest.raises(PaperExecutionContractError): composer(issuer).preflight(plan=plan)


def test_unsupported_family_is_not_executable():
    plan,rel=fixture()
    q=replace(plan.questions[0],family='DIRECT')
    plan=replace(plan,questions=(q,plan.questions[1]))
    issued=replace(rel.questions[0],family='DIRECT')
    rel=replace(rel,questions=(issued,rel.questions[1]))
    result=composer(Issuer(rel)).preflight(plan=plan)
    assert result.execution_state=='UNSUPPORTED_FAMILIES'


def test_invalid_plan_before_issuer_contact():
    plan,rel=fixture(); issuer=Issuer(rel)
    with pytest.raises(PaperExecutionContractError):
        composer(issuer).preflight(plan={'fake':'plan'})
    assert issuer.calls==0

# Independent-review regressions: revalidate paper readiness invariants at the numeric scoring profile boundary,
# since the public dataclass constructor is not evidence of paper readiness provenance.
def test_review_question_revision_must_match_paper_before_issuer_contact():
    plan, relation = fixture()
    q = replace(plan.questions[0], source_revision='STALE')
    rq = replace(relation.questions[0], source_revision='STALE')
    issuer = Issuer(replace(relation, questions=(rq, relation.questions[1])))
    with pytest.raises(PaperExecutionDenied):
        composer(issuer).preflight(plan=replace(plan, questions=(q, plan.questions[1])))
    assert issuer.calls == 0


def test_review_evidence_scopes_must_be_disjoint_before_issuer_contact():
    plan, relation = fixture()
    reused = plan.questions[0].evidence_scope_ref
    q = replace(plan.questions[1], evidence_scope_ref=reused)
    rq = replace(relation.questions[1], evidence_scope_ref=reused)
    issuer = Issuer(replace(relation, questions=(relation.questions[0], rq)))
    with pytest.raises(PaperExecutionDenied):
        composer(issuer).preflight(plan=replace(plan, questions=(plan.questions[0], q)))
    assert issuer.calls == 0


@pytest.mark.parametrize('kind', ['unavailable', 'denied'])
def test_review_private_issuer_exception_not_retained(kind):
    plan, relation = fixture()
    issuer = Issuer(relation)
    def secret(_):
        if kind == 'denied':
            raise PaperExecutionDenied('PRIVATE_DENIAL_DETAIL')
        raise RuntimeError('PRIVATE_CALLBACK_DETAIL')
    issuer.action = secret
    expected = PaperExecutionDenied if kind == 'denied' else PaperExecutionUnavailable
    with pytest.raises(expected) as captured:
        composer(issuer).preflight(plan=plan)
    public = captured.value
    assert public.__cause__ is None
    assert public.__context__ is None
    assert public.__suppress_context__ is True
    assert 'PRIVATE' not in str(public)
    assert issuer.calls == 1


def test_review_malformed_nested_issuer_data_has_no_public_exception_context():
    plan, relation = fixture()
    invalid = replace(relation.questions[0], scoring_policy_ref=object())
    issuer = Issuer(replace(relation, questions=(invalid, relation.questions[1])))
    with pytest.raises(PaperExecutionContractError) as captured:
        composer(issuer).preflight(plan=plan)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert issuer.calls == 1


def test_review_private_constructor_method_getter_exception_not_retained():
    class FailingIssuer:
        @property
        def correlate_paper_execution(self):
            raise RuntimeError('PRIVATE_CONSTRUCTOR_DETAIL')
    with pytest.raises(PaperExecutionContractError) as captured:
        composer(FailingIssuer())
    public = captured.value
    assert public.__cause__ is None
    assert public.__context__ is None
    assert public.__suppress_context__ is True
    assert 'PRIVATE' not in str(public)


def test_review_valid_correlated_paper_remains_only_a_detached_preflight():
    plan, relation = fixture()
    issuer = Issuer(relation)
    preflight = composer(issuer).preflight(plan=plan)
    assert issuer.calls == 1
    assert preflight.execution_state == 'CORRELATED_CHOICE_ONLY'
    assert preflight.plan is not plan
    assert preflight.issuer_relation is not relation
    assert not hasattr(preflight, 'authorize_execution')
    assert not hasattr(preflight, 'attempt_id')


# Installed limits are an authority boundary, not callback-writable options.
@pytest.mark.parametrize('field', ['rubric_ref', 'scoring_policy_ref', 'issuance_ref'])
def test_review_issuer_cannot_relax_identifier_limit_during_contact(field):
    plan, relation = fixture()
    if field == 'issuance_ref':
        relation = replace(relation, issuance_ref='X' * 65)
    else:
        q = replace(relation.questions[0], **{field: 'X' * 65})
        relation = replace(relation, questions=(q, relation.questions[1]))
    issuer = Issuer(relation)
    bound = composer(issuer)
    issuer.action = lambda _: setattr(bound, '_limit', 100)
    with pytest.raises(PaperExecutionContractError) as caught:
        bound.preflight(plan=plan)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert issuer.calls == 1


def test_review_poisoned_limit_denies_subsequent_preflight_before_contact():
    plan, relation = fixture()
    relation = replace(relation, issuance_ref='X' * 65)
    issuer = Issuer(relation)
    bound = composer(issuer)
    issuer.action = lambda _: setattr(bound, '_limit', 100)
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1
    issuer.action = None
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1


def test_review_limit_mutated_before_entry_denies_without_issuer_contact():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    bound._limit = 100
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 0


def test_review_question_maximum_mutated_in_callback_denies():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    issuer.action = lambda _: setattr(bound, '_maximum', 100)
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1
    issuer.action = None
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1


def test_review_oversized_issuer_id_rejected_without_mutation():
    plan, relation = fixture()
    relation = replace(relation, questions=(replace(relation.questions[0], rubric_ref='X' * 65), relation.questions[1]))
    issuer = Issuer(relation)
    with pytest.raises(PaperExecutionContractError):
        composer(issuer).preflight(plan=plan)
    assert issuer.calls == 1


def test_review_normal_issuer_remains_correlatable_with_installed_limits():
    plan, relation = fixture()
    issuer = Issuer(relation)
    admitted = composer(issuer).preflight(plan=plan)
    assert admitted.issuer_relation.issuance_ref == 'ISSUANCE'
    assert admitted.execution_state == 'CORRELATED_CHOICE_ONLY'
    assert issuer.calls == 1

# Independent numeric scoring profile installation-state custody: an immutable tuple in a writable
# attribute is not an immutable installation baseline.
def test_installed_baseline_reassignment_is_denied_before_issuer_contact():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    for original, forged in (('_configured_limits', (5, 100)),
                             ('_configured_limits', (10, 64))):
        with pytest.raises(PaperExecutionContractError):
            setattr(bound, original, forged)
    assert issuer.calls == 0
    assert bound.preflight(plan=plan).issuer_relation.issuance_ref == 'ISSUANCE'
    assert issuer.calls == 1


def test_issuer_cannot_poison_baseline_and_live_limit_across_calls():
    plan, relation = fixture()
    issuer = Issuer(replace(relation, issuance_ref='X' * 65))
    bound = composer(issuer)
    def poison(_):
        bound._limit = 100
        bound._configured_limits = (5, 100)
    issuer.action = poison
    with pytest.raises(PaperExecutionContractError) as caught:
        bound.preflight(plan=plan)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert issuer.calls == 1
    issuer.action = None
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1  # poisoned live field denies before second contact


def test_installed_maximum_baseline_must_not_be_replaced():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    with pytest.raises(PaperExecutionContractError):
        bound._configured_limits = (10, 64)
    bound._maximum = 10
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 0


def test_issuer_method_cannot_redirect_later_authority_contact():
    plan, relation = fixture()
    issuer, foreign = Issuer(relation), Issuer(relation)
    bound = composer(issuer)
    issuer.action = lambda _: setattr(bound, '_method', foreign.correlate_paper_execution)
    with pytest.raises(PaperExecutionContractError) as caught:
        bound.preflight(plan=plan)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert issuer.calls == 1 and foreign.calls == 0
    issuer.action = None
    assert bound.preflight(plan=plan).issuer_relation.issuance_ref == 'ISSUANCE'
    assert issuer.calls == 2 and foreign.calls == 0


@pytest.mark.parametrize('field', ['_method', '_configured_limits', '_maximum', '_limit'])
def test_installed_fields_cannot_be_deleted_and_reinstalled(field):
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    with pytest.raises(PaperExecutionContractError):
        delattr(bound, field)
    assert issuer.calls == 0
    assert bound.preflight(plan=plan).execution_state == 'CORRELATED_CHOICE_ONLY'
    assert issuer.calls == 1


def test_callback_attempt_to_delete_issuer_binding_is_private_context_free():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    issuer.action = lambda _: delattr(bound, '_method')
    with pytest.raises(PaperExecutionContractError) as caught:
        bound.preflight(plan=plan)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert issuer.calls == 1


def test_local_installation_baseline_still_rejects_oversized_issuer_reference():
    plan, relation = fixture()
    issuer = Issuer(replace(relation, issuance_ref='Y' * 65))
    bound = composer(issuer)
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1


# Review G0B1-06: ordinary __class__ assignment can switch to a compatible
# subclass that shadows installation-owned descriptors or setter enforcement.
class _ReviewReplacementClass(ProductionPaperExecutionCorrelation):
    __slots__ = ()

    def __setattr__(self, name, value):
        return object.__setattr__(self, name, value)


class _ReviewLimitShadow(ProductionPaperExecutionCorrelation):
    __slots__ = ()

    @property
    def _configured_limits(self):
        return (5, 100)

    @property
    def _limit(self):
        return 100


class _ReviewIssuerShadow(ProductionPaperExecutionCorrelation):
    __slots__ = ()

    @property
    def _method(self):
        raise AssertionError('Foreign issuer shadow must never run')


@pytest.mark.parametrize('replacement', [_ReviewReplacementClass, _ReviewLimitShadow,
                                         _ReviewIssuerShadow, ProductionPaperExecutionCorrelation])
def test_review_instance_class_replacement_denied_before_contact(replacement):
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    with pytest.raises(PaperExecutionContractError) as caught:
        bound.__class__ = replacement
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert type(bound) is ProductionPaperExecutionCorrelation
    assert issuer.calls == 0
    assert bound.preflight(plan=plan).execution_state == 'CORRELATED_CHOICE_ONLY'
    assert issuer.calls == 1


def test_review_oversize_reference_denied_after_attempted_class_swap():
    plan, relation = fixture()
    issuer = Issuer(replace(relation, issuance_ref='X' * 65))
    bound = composer(issuer)
    with pytest.raises(PaperExecutionContractError):
        bound.__class__ = _ReviewLimitShadow
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert type(bound) is ProductionPaperExecutionCorrelation
    assert bound._configured_limits == (5, 64)
    assert issuer.calls == 1


def test_review_callback_class_swap_denied_without_poisoning_next_call():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    issuer.action = lambda _: setattr(bound, '__class__', _ReviewReplacementClass)
    with pytest.raises(PaperExecutionContractError) as caught:
        bound.preflight(plan=plan)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert issuer.calls == 1
    assert type(bound) is ProductionPaperExecutionCorrelation
    assert bound._configured_limits == (5, 64)
    assert bound._limit == 64
    issuer.action = None
    assert bound.preflight(plan=plan).execution_state == 'CORRELATED_CHOICE_ONLY'
    assert issuer.calls == 2


def test_review_class_swap_cannot_redirect_issuer_between_calls():
    plan, relation = fixture()
    original, foreign = Issuer(relation), Issuer(relation)
    bound = composer(original)
    def tamper(_):
        bound.__class__ = _ReviewReplacementClass
        bound._method = foreign.correlate_paper_execution
    original.action = tamper
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert original.calls == 1 and foreign.calls == 0
    original.action = None
    assert bound.preflight(plan=plan).execution_state == 'CORRELATED_CHOICE_ONLY'
    assert original.calls == 2 and foreign.calls == 0
    assert type(bound) is ProductionPaperExecutionCorrelation


def test_review_subclass_descriptor_shadow_is_not_installed():
    plan, relation = fixture()
    original = Issuer(relation)
    bound = composer(original)
    for replacement in (_ReviewLimitShadow, _ReviewIssuerShadow):
        with pytest.raises(PaperExecutionContractError):
            setattr(bound, '__class__', replacement)
    assert bound._configured_limits == (5, 64)
    assert bound.preflight(plan=plan).issuer_relation.issuer_ref == 'SCHOOL'
    assert original.calls == 1

# Fresh independent numeric scoring profile source review — foreign equality must never certify
# mutable live installation settings as unchanged, before or after contact.
class _LiveLimitAlwaysEqual:
    def __init__(self): self.comparisons = 0
    def __eq__(self, _other):
        self.comparisons += 1
        return True

class _LiveLimitExplosiveEqual:
    def __init__(self): self.comparisons = 0
    def __eq__(self, _other):
        self.comparisons += 1
        raise RuntimeError('PRIVATE_EQ_SIDE_EFFECT')

@pytest.mark.parametrize('field', ['_maximum', '_limit'])
def test_fresh_foreign_equality_pre_contact_denied_without_executing_eq(field):
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    poison = _LiveLimitAlwaysEqual()
    setattr(bound, field, poison)
    with pytest.raises(PaperExecutionContractError) as captured:
        bound.preflight(plan=plan)
    assert captured.value.__cause__ is None and captured.value.__context__ is None
    assert issuer.calls == 0
    assert poison.comparisons == 0

@pytest.mark.parametrize('field', ['_maximum', '_limit'])
def test_fresh_foreign_equality_during_contact_denied_and_future_poisoned(field):
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    poison = _LiveLimitAlwaysEqual()
    issuer.action = lambda _: setattr(bound, field, poison)
    with pytest.raises(PaperExecutionContractError) as captured:
        bound.preflight(plan=plan)
    assert captured.value.__cause__ is None and captured.value.__context__ is None
    assert issuer.calls == 1 and poison.comparisons == 0
    issuer.action = None
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 1 and poison.comparisons == 0

@pytest.mark.parametrize('field,value', [('_maximum', 5.0), ('_limit', 64.0), ('_maximum', True)])
def test_fresh_non_exact_live_limit_type_is_not_integrity_evidence(field, value):
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    setattr(bound, field, value)
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 0

def test_fresh_explosive_equality_never_runs():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    poison = _LiveLimitExplosiveEqual()
    bound._limit = poison
    with pytest.raises(PaperExecutionContractError):
        bound.preflight(plan=plan)
    assert issuer.calls == 0 and poison.comparisons == 0

def test_fresh_valid_limit_control_keeps_issuer_binding():
    plan, relation = fixture()
    issuer = Issuer(relation)
    bound = composer(issuer)
    assert bound.preflight(plan=plan).issuer_relation.issuer_ref == 'SCHOOL'
    assert issuer.calls == 1
