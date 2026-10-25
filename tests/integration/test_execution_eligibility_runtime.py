"""execution eligibility/evaluator handler binding: controlled test-authority fixtures, NEVER production approvals."""
from dataclasses import replace

import pytest

from grading.active_question_authority import ContextPolicy
from grading.capability_registry import ResolvedEvaluatorCapability
from grading.choice_evaluator import evaluate_single_select_choice
from grading.contracts.choice import (DETERMINISTIC_CHOICE_EVALUATOR_ID,
                                      DETERMINISTIC_CHOICE_EVALUATOR_VERSION)
from grading.contracts.capability import (
    EvaluatorCapabilityRecord, EvaluatorCapabilityRef, EvaluatorCapabilityStatus,
)
from grading.contracts.evaluation import EvaluatorMetadata
from grading.contracts.evaluator_selection import (
    QuestionEvaluationClassification, EvaluatorSelectionPolicyRef,
)
from grading.evaluator_selection import ResolvedQuestionEvaluatorSelection
from grading.integration.choice_authority_admission import AdmittedChoice
from grading.integration.execution_eligibility import (
    AdmittedExecutionEligibility, ApprovedEligibilityPolicy, EligibilityFact,
    EligibilityFactSet, EligibilityRequirement, FactOrigin,
    ProductionExecutionEligibilityComposer, ExecutionEligibilityDenied,
    ExecutionEligibilityUnavailable, ExecutionEligibilityContractError,
)
from grading.integration.evaluator_execution_binding import (
    ApprovedRuntimeRecord, InstalledRuntime, ProductionEvaluatorRuntimeBinder,
    RuntimeBindingContractError, RuntimeBindingDenied, RuntimeBindingUnavailable,
    ProductionExecutionHandoff,
)
from grading.integration.grading_orchestration import ProductionGradingEntry
from tests.integration.test_choice_authority_admission import setup
from tests.integration.test_authorized_preparation import _compose


class FixtureAuthorities:
    def __init__(self, admitted):
        self.admitted = admitted
        self.events = []
        scope = admitted.scope
        ref = EvaluatorCapabilityRef(EvaluatorMetadata(DETERMINISTIC_CHOICE_EVALUATOR_ID, DETERMINISTIC_CHOICE_EVALUATOR_VERSION), 1)
        record = EvaluatorCapabilityRecord(
            schema_version='1', capability_ref=ref,
            status=EvaluatorCapabilityStatus.VALIDATED,
            supported_answer_types=('CHOICE',), supported_languages=('en',),
            supported_modalities=('OCR',), tested_grade_range=None,
            domain_scope=None, verification_mechanisms=(), benchmark_version=None,
            known_failure_modes=(), cost_profile=None, latency_profile=None,
        )
        self.selection = ResolvedQuestionEvaluatorSelection(
            classification=QuestionEvaluationClassification(
                '1', scope.grading_spec_ref, scope.question_id, 'CHOICE', 'en',
            ),
            context_policy=admitted.bound.prepared.question_authority.context_policy,
            policy_ref=EvaluatorSelectionPolicyRef('IF2-POLICY', 1),
            selected_capability_ref=ref,
            resolved_capability=ResolvedEvaluatorCapability(record),
        )
        self.facts = EligibilityFactSet(
            scope, ref, (EligibilityFact('readiness', 'approved', FactOrigin.DIRECT,
                                         'READINESS-AUTHORITY', 'REV-1'),), ('OCR',),
        )
        self.policy = ApprovedEligibilityPolicy(
            scope, ref, 'ELIGIBILITY-POLICY', 1, 'ACADEMIC-APPROVAL',
            (EligibilityRequirement('readiness', 'approved', (FactOrigin.DIRECT,)),),
            ('OCR',),
        )
        self.runtime_record = ApprovedRuntimeRecord(
            scope, ref, 'ELIGIBILITY-POLICY', 1, 'CHOICE', 'choice-native', '1',
            'content-sha256-ref-1', 'RUNTIME-APPROVAL', ('OCR',),
        )
        self.invoke_count = 0

    def resolve_admitted_selection(self, *, scope):
        self.events.append('selection')
        return self.selection

    def resolve_execution_facts(self, *, scope, capability_ref):
        self.events.append('facts')
        return self.facts

    def resolve_approved_eligibility_policy(self, *, scope, capability_ref):
        self.events.append('policy')
        return self.policy

    def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
        self.events.append('runtime')
        return self.runtime_record


def prepared():
    request, prep_ports, _, choice_ports, choice_composer = setup()
    admitted = choice_composer.admit(prepared=choice_ports.prepared)
    return request, prep_ports, choice_composer, admitted


def assemble():
    request, prep_ports, choice_composer, admitted = prepared()
    ports = FixtureAuthorities(admitted)
    eligible_composer = ProductionExecutionEligibilityComposer(
        selection=ports, facts=ports, policy=ports,
        max_identifier_characters=64, max_facts=8,
    )
    installed = InstalledRuntime('CHOICE', 'choice-native', '1',
                                 'content-sha256-ref-1', evaluate_single_select_choice)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=ports, eligibility=eligible_composer, installed=(installed,),
        max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8,
    )
    return request, prep_ports, choice_composer, admitted, ports, eligible_composer, binder


def test_positive_g0_eligibility_runtime_handoff_does_not_invoke_evaluator():
    request, prep_ports, choice_composer, admitted, ports, eligible, binder = assemble()
    result = binder.bind_choice(admitted=admitted)
    assert result.installed.handler is evaluate_single_select_choice
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']
    assert not hasattr(result, 'score')
    assert ports.invoke_count == 0
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choice_composer)
    out = ProductionExecutionHandoff(admission_entry=entry, eligibility=eligible, runtime=binder)
    bound = out.prepare_choice_runtime(request=request)
    assert bound.approved_runtime.approval_ref == 'RUNTIME-APPROVAL'
    assert not hasattr(out, 'execute')


def test_missing_real_approval_port_cannot_be_replaced_with_capability_status():
    _, _, _, admitted, ports, _, _ = assemble()
    class Missing:
        pass
    with pytest.raises(ExecutionEligibilityContractError):
        ProductionExecutionEligibilityComposer(
            selection=ports, facts=ports, policy=Missing(),
            max_identifier_characters=64, max_facts=8,
        )
    assert ports.events == []


@pytest.mark.parametrize('alter', [
    lambda p: setattr(p, 'policy', replace(p.policy, approval_ref='')),
    lambda p: setattr(p, 'policy', replace(p.policy, scope=replace(p.policy.scope, tenant_ref='OTHER'))),
    lambda p: setattr(p, 'policy', replace(p.policy, policy_version=True)),
    lambda p: setattr(p, 'policy', replace(p.policy, requirements=())),
    lambda p: setattr(p, 'policy', replace(p.policy, requirements=(EligibilityRequirement('other', 'yes', (FactOrigin.DIRECT,)),))),
    lambda p: setattr(p, 'facts', replace(p.facts, facts=())),
    lambda p: setattr(p, 'facts', replace(p.facts, facts=(EligibilityFact('readiness', 'denied', FactOrigin.DIRECT, 'SOURCE', 'REV'),))),
    lambda p: setattr(p, 'facts', replace(p.facts, facts=(EligibilityFact('readiness', 'approved', FactOrigin.DERIVED, 'SOURCE', 'REV'),))),
    lambda p: setattr(p, 'facts', replace(p.facts, required_modalities=('VIDEO',))),
    lambda p: setattr(p, 'selection', replace(p.selection, classification=replace(p.selection.classification, question_id='OTHER'))),
    lambda p: setattr(p, 'selection', replace(p.selection, selected_capability_ref=EvaluatorCapabilityRef(EvaluatorMetadata('FOREIGN', '1'), 1))),
])
def test_source_forgery_or_missing_semantics_fails_closed(alter):
    _, _, _, admitted, ports, eligible, _ = assemble()
    alter(ports)
    with pytest.raises((ExecutionEligibilityDenied, ExecutionEligibilityContractError)):
        eligible.admit_choice(admitted=admitted)
    assert 'runtime' not in ports.events


def test_policy_origin_must_be_explicit_and_matching():
    _, _, _, admitted, ports, eligible, _ = assemble()
    ports.facts = replace(ports.facts, facts=(EligibilityFact('readiness', 'approved', FactOrigin.DERIVED,
                                                             'SOURCE', 'REV', 'DERIVATION-1'),))
    with pytest.raises(ExecutionEligibilityDenied):
        eligible.admit_choice(admitted=admitted)
    ports.policy = replace(ports.policy, requirements=(EligibilityRequirement('readiness', 'approved', (FactOrigin.DERIVED,)),))
    assert eligible.admit_choice(admitted=admitted).facts.facts[0].origin is FactOrigin.DERIVED


def test_source_callback_can_neither_rewrite_original_choice_nor_scope_argument():
    _, _, _, admitted, ports, _, _ = assemble()
    class Mutator(FixtureAuthorities):
        def resolve_admitted_selection(self, *, scope):
            object.__setattr__(scope, 'tenant_ref', 'FORGED')
            return self.selection
    bad = Mutator(admitted)
    composer = ProductionExecutionEligibilityComposer(selection=bad, facts=bad, policy=bad,
                                                     max_identifier_characters=64, max_facts=8)
    with pytest.raises(ExecutionEligibilityDenied):
        composer.admit_choice(admitted=admitted)
    assert bad.events == []


def test_mutation_during_backend_outage_has_denial_precedence_and_no_private_context():
    _, _, _, admitted, ports, _, _ = assemble()
    class Mutator(FixtureAuthorities):
        def resolve_execution_facts(self, *, scope, capability_ref):
            object.__setattr__(scope, 'tenant_ref', 'FORGED')
            raise RuntimeError('PRIVATE-TOKEN')
    bad = Mutator(admitted)
    composer = ProductionExecutionEligibilityComposer(selection=bad, facts=bad, policy=bad,
                                                     max_identifier_characters=64, max_facts=8)
    with pytest.raises(ExecutionEligibilityDenied) as error:
        composer.admit_choice(admitted=admitted)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    assert 'PRIVATE' not in str(error.value)


def test_unchanged_backend_failure_remains_unavailable():
    _, _, _, admitted, ports, _, _ = assemble()
    class Outage(FixtureAuthorities):
        def resolve_execution_facts(self, *, scope, capability_ref):
            raise RuntimeError('PRIVATE-TOKEN')
    bad = Outage(admitted)
    composer = ProductionExecutionEligibilityComposer(selection=bad, facts=bad, policy=bad,
                                                     max_identifier_characters=64, max_facts=8)
    with pytest.raises(ExecutionEligibilityUnavailable) as error:
        composer.admit_choice(admitted=admitted)
    assert error.value.__context__ is None
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('alter', [
    lambda p: setattr(p, 'runtime_record', replace(p.runtime_record, runtime_version='2')),
    lambda p: setattr(p, 'runtime_record', replace(p.runtime_record, family='DIRECT')),
    lambda p: setattr(p, 'runtime_record', replace(p.runtime_record, implementation_ref='OTHER')),
    lambda p: setattr(p, 'runtime_record', replace(p.runtime_record, scope=replace(p.runtime_record.scope, session_ref='OTHER'))),
    lambda p: setattr(p, 'runtime_record', replace(p.runtime_record, eligibility_policy_version=2)),
    lambda p: setattr(p, 'runtime_record', replace(p.runtime_record, approved_modalities=())),
])
def test_unapproved_or_uninstalled_runtime_never_invoked(alter):
    _, _, _, admitted, ports, eligible, binder = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    alter(ports)
    with pytest.raises((RuntimeBindingDenied, RuntimeBindingContractError)):
        binder._bind_eligibility(valid)
    assert ports.events[-1] == 'runtime'
    assert ports.invoke_count == 0


def test_runtime_inventory_callback_cannot_mutate_binding_input_before_denial():
    _, _, _, admitted, ports, eligible, _ = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    class Mutator(FixtureAuthorities):
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            object.__setattr__(scope, 'tenant_ref', 'FORGED')
            raise RuntimeBindingDenied('SECRET-DENIAL')
    bad = Mutator(admitted)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=bad, eligibility=eligible, installed=(InstalledRuntime('CHOICE', 'choice-native', '1',
            'content-sha256-ref-1', evaluate_single_select_choice),),
        max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8)
    with pytest.raises(RuntimeBindingDenied) as error:
        binder._bind_eligibility(valid)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None


def test_constructor_rejects_descriptor_without_getter_execution():
    _, _, _, admitted, ports, eligible, _ = assemble()
    class Hostile:
        @property
        def resolve_approved_runtime(self):
            raise RuntimeError('DESCRIPTOR EXECUTED')
    with pytest.raises(RuntimeBindingContractError) as err:
        ProductionEvaluatorRuntimeBinder(
            inventory=Hostile(), eligibility=eligible, installed=(InstalledRuntime('CHOICE', 'native', '1', 'hash', evaluate_single_select_choice),),
            max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8)
    assert 'DESCRIPTOR' not in str(err.value)


def test_runtime_cannot_upgrade_fabricated_eligibility_records():
    _, _, _, admitted, ports, eligible, binder = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    forged = replace(valid, facts=replace(valid.facts, facts=(EligibilityFact(
        'readiness', 'denied', FactOrigin.DIRECT, 'SOURCE', 'REV'),)))
    with pytest.raises(ExecutionEligibilityDenied):
        binder._bind_eligibility(forged)
    assert ports.events == ['selection', 'facts', 'policy']


def test_runtime_binding_rejects_changed_original_choice_after_eligibility():
    _, _, _, admitted, ports, eligible, binder = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    object.__setattr__(admitted.scope, 'tenant_ref', 'UNAUTHORIZED')
    with pytest.raises((RuntimeBindingDenied, ExecutionEligibilityDenied)):
        binder._bind_eligibility(valid)
    assert 'runtime' not in ports.events


def test_runtime_binding_rejects_wrong_selected_evaluator_metadata():
    _, _, _, admitted, ports, eligible, binder = assemble()
    ref = EvaluatorCapabilityRef(EvaluatorMetadata('UNAPPROVED-CHOICE-HANDLER', '1'), 1)
    record = replace(ports.selection.resolved_capability.record, capability_ref=ref)
    ports.selection = replace(ports.selection, selected_capability_ref=ref,
                              resolved_capability=ResolvedEvaluatorCapability(record))
    ports.facts = replace(ports.facts, capability_ref=ref)
    ports.policy = replace(ports.policy, capability_ref=ref)
    valid = eligible.admit_choice(admitted=admitted)
    with pytest.raises(RuntimeBindingDenied):
        binder._bind_eligibility(valid)
    assert 'runtime' not in ports.events


def test_wrong_python_handler_is_rejected_even_with_matching_installed_labels():
    _, _, _, admitted, ports, eligible, _ = assemble()
    def fake_choice(*, authority, selection, scoring_authority):
        raise RuntimeError('SHOULD NEVER EXECUTE')
    with pytest.raises(RuntimeBindingContractError):
        ProductionEvaluatorRuntimeBinder(
            inventory=ports, eligibility=eligible, installed=(InstalledRuntime('CHOICE', 'choice-native', '1',
                'content-sha256-ref-1', fake_choice),),
            max_identifier_characters=64, max_modalities=8,
            max_installed_runtimes=8, max_facts=8,
        )


def test_mutated_installed_handler_is_rejected_before_handoff():
    _, _, _, admitted, ports, eligible, binder = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    installed = next(iter(binder._installed.values()))
    def wrong(*, authority, selection, scoring_authority):
        raise RuntimeError('WRONG')
    object.__setattr__(installed, 'handler', wrong)
    with pytest.raises(RuntimeBindingDenied):
        binder._bind_eligibility(valid)



@pytest.mark.parametrize('method', ['resolve_admitted_selection', 'resolve_execution_facts',
                                    'resolve_approved_eligibility_policy'])
def test_backend_method_descriptors_are_not_invoked_during_installation(method):
    _, _, _, admitted, ports, _, _ = assemble()
    class Dynamic:
        @property
        def resolve_admitted_selection(self):
            raise AssertionError('DESCRIPTOR-EXECUTED')
        @property
        def resolve_execution_facts(self):
            raise AssertionError('DESCRIPTOR-EXECUTED')
        @property
        def resolve_approved_eligibility_policy(self):
            raise AssertionError('DESCRIPTOR-EXECUTED')
    bad = Dynamic()
    kwargs = {'selection': ports, 'facts': ports, 'policy': ports}
    kwargs[{'resolve_admitted_selection':'selection',
            'resolve_execution_facts':'facts',
            'resolve_approved_eligibility_policy':'policy'}[method]] = bad
    with pytest.raises(ExecutionEligibilityContractError):
        ProductionExecutionEligibilityComposer(max_identifier_characters=64,
                                               max_facts=8, **kwargs)


def test_backend_method_signature_requires_exact_keyword_arguments():
    _, _, _, admitted, ports, _, _ = assemble()
    class Invalid:
        def resolve_execution_facts(self, scope):
            raise AssertionError('SHOULD NOT RUN')
    with pytest.raises(ExecutionEligibilityContractError):
        ProductionExecutionEligibilityComposer(selection=ports, facts=Invalid(), policy=ports,
                                               max_identifier_characters=64, max_facts=8)


def test_explicit_runtime_inventory_limit_rejects_before_handler_walk():
    _, _, _, admitted, ports, eligible, _ = assemble()
    handle = InstalledRuntime('CHOICE', 'choice-native', '1',
                              'content-sha256-ref-1', evaluate_single_select_choice)
    with pytest.raises(RuntimeBindingContractError):
        ProductionEvaluatorRuntimeBinder(inventory=ports, eligibility=eligible, installed=(handle,handle),
                                        max_identifier_characters=64, max_modalities=8,
                                        max_installed_runtimes=1, max_facts=8)


def test_noncanonical_capability_metadata_rejected_before_user_property_access():
    _, _, _, admitted, ports, eligible, _ = assemble()
    class Hostile:
        @property
        def evaluator_id(self):
            raise AssertionError('HOSTILE-PROPERTY')
    object.__setattr__(ports.selection.selected_capability_ref, 'evaluator_metadata', Hostile())
    with pytest.raises(ExecutionEligibilityContractError):
        eligible.admit_choice(admitted=admitted)


def test_evaluator_status_alone_does_not_authorize_execution():
    _, _, _, admitted, ports, eligible, _ = assemble()
    record = replace(ports.selection.resolved_capability.record,
                     status=EvaluatorCapabilityStatus.VALIDATED)
    ports.selection = replace(ports.selection, resolved_capability=ResolvedEvaluatorCapability(record))
    ports.policy = None
    with pytest.raises(ExecutionEligibilityContractError):
        eligible.admit_choice(admitted=admitted)


def test_forged_eligibility_selection_other_question_rejected_before_backend():
    _, _, _, admitted, ports, eligible, binder = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    other = replace(valid.selection, classification=replace(valid.selection.classification,
                                                             question_id='FOREIGN-QUESTION'))
    forged = replace(valid, selection=other)
    with pytest.raises(RuntimeBindingDenied):
        binder._bind_eligibility(forged)
    assert 'runtime' not in ports.events


def test_policy_callback_mutating_returned_source_object_cannot_rewrite_snapshot():
    _, _, _, admitted, ports, _, _ = assemble()
    class Mutator(FixtureAuthorities):
        def resolve_approved_eligibility_policy(self, *, scope, capability_ref):
            object.__setattr__(self.facts.facts[0], 'value', 'denied')
            return self.policy
    bad = Mutator(admitted)
    composer = ProductionExecutionEligibilityComposer(selection=bad, facts=bad,
               policy=bad, max_identifier_characters=64, max_facts=8)
    result = composer.admit_choice(admitted=admitted)
    assert result.facts.facts[0].value == 'approved'
    assert bad.facts.facts[0].value == 'denied'


def test_unavailable_inventory_does_not_emit_runtime():
    _, _, _, admitted, ports, eligible, _ = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    class Outage(FixtureAuthorities):
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            raise RuntimeError('PRIVATE-API-CREDENTIAL')
    bad = Outage(admitted)
    binder = ProductionEvaluatorRuntimeBinder(inventory=bad, eligibility=eligible,
         installed=(InstalledRuntime('CHOICE', 'choice-native', '1',
                                    'content-sha256-ref-1', evaluate_single_select_choice),),
         max_identifier_characters=64, max_modalities=8,
         max_installed_runtimes=8, max_facts=8)
    with pytest.raises(RuntimeBindingUnavailable) as err:
        binder._bind_eligibility(valid)
    assert err.value.__context__ is None
    assert err.value.__cause__ is None
    assert 'PRIVATE' not in str(err.value)


def test_callback_original_choice_corruption_precedes_operational_outage():
    _, _, _, admitted, ports, _, _ = assemble()
    class CorruptOriginal(FixtureAuthorities):
        def resolve_admitted_selection(self, *, scope):
            object.__setattr__(self.admitted.scope, 'tenant_ref', 'CORRUPTED')
            raise RuntimeError('PRIVATE-OUTAGE')
    bad = CorruptOriginal(admitted)
    composer = ProductionExecutionEligibilityComposer(
        selection=bad, facts=bad, policy=bad,
        max_identifier_characters=64, max_facts=8)
    with pytest.raises(ExecutionEligibilityDenied) as err:
        composer.admit_choice(admitted=admitted)
    assert err.value.__context__ is None
    assert err.value.__cause__ is None

# Independently reported contract failures: cross-family routing, PRE nested
# foreign equality, evaluator eligibility policy modality custody, and constructible intermediate data.
@pytest.mark.parametrize('field', [
    'grading_run_id', 'submission_ref', 'exam_ref', 'grading_spec_ref',
    'question_id',
])
def test_foreign_nested_pre_fields_cannot_run_comparison_methods(field):
    _, _, _, admitted, ports, eligible, _ = assemble()
    class HostileEquality:
        calls = 0
        def __eq__(self, other):
            type(self).calls += 1
            raise RuntimeError('PRIVATE-EQUALITY-CREDENTIAL')
        def __ne__(self, other):
            type(self).calls += 1
            raise RuntimeError('PRIVATE-EQUALITY-CREDENTIAL')
    original = (admitted.bound.prepared.question_authority if field == 'question_id'
                else admitted.bound.prepared.context)
    object.__setattr__(original, field, HostileEquality())
    with pytest.raises(ExecutionEligibilityContractError) as err:
        eligible.admit_choice(admitted=admitted)
    assert HostileEquality.calls == 0
    assert err.value.__cause__ is None and err.value.__context__ is None
    assert 'PRIVATE' not in str(err.value)
    assert ports.events == []


def test_if2_direct_does_not_enter_choice_fact_or_runtime_admission():
    _, _, _, admitted, ports, eligible, binder = assemble()
    chosen = ports.selection
    record = replace(chosen.resolved_capability.record, supported_answer_types=('DIRECT',))
    ports.selection = replace(chosen,
        classification=replace(chosen.classification, answer_type='DIRECT'),
        resolved_capability=ResolvedEvaluatorCapability(record))
    with pytest.raises(ExecutionEligibilityDenied):
        eligible.admit_choice(admitted=admitted)
    assert ports.events == ['selection']
    ports.events.clear()
    with pytest.raises(ExecutionEligibilityDenied):
        binder.bind_choice(admitted=admitted)
    assert ports.events == ['selection']


def test_runtime_validator_independently_denies_constructed_direct_family():
    _, _, _, admitted, ports, eligible, binder = assemble()
    valid = eligible.admit_choice(admitted=admitted)
    selected = valid.selection
    record = replace(selected.resolved_capability.record, supported_answer_types=('DIRECT',))
    foreign = replace(valid, selection=replace(selected,
        classification=replace(selected.classification, answer_type='DIRECT'),
        resolved_capability=ResolvedEvaluatorCapability(record)))
    ports.events.clear()
    with pytest.raises(RuntimeBindingDenied):
        binder._bind_eligibility(foreign)
    assert ports.events == []


def test_fully_constructed_eligibility_never_crosses_public_runtime_boundary():
    _, _, _, admitted, ports, eligible, binder = assemble()
    fake = AdmittedExecutionEligibility(
        admitted.scope, ports.selection, ports.facts, ports.policy,
        admitted.key_revision, admitted.selection_revision, admitted)
    with pytest.raises(TypeError):
        binder.bind_choice(eligibility=fake)
    assert ports.events == []
    result = binder.bind_choice(admitted=admitted)
    assert result.installed.handler is evaluate_single_select_choice
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']
    assert not hasattr(result, 'execute')


@pytest.mark.parametrize('alter', [
    lambda p: setattr(p, 'facts', replace(p.facts, required_modalities=())),
    lambda p: setattr(p, 'facts', replace(p.facts, required_modalities=('OCR', 'OCR'))),
    lambda p: setattr(p, 'policy', replace(p.policy, required_modalities=())),
    lambda p: setattr(p, 'policy', replace(p.policy, required_modalities=('VIDEO',))),
    lambda p: setattr(p, 'policy', replace(p.policy, required_modalities=('OCR', 'OCR'))),
    lambda p: setattr(p, 'policy', replace(p.policy, required_modalities=('OCR', object()))),
    lambda p: setattr(p, 'policy', replace(p.policy, required_modalities=None)),
])
def test_f17_policy_is_explicit_source_for_required_modalities(alter):
    _, _, _, admitted, ports, eligible, _ = assemble()
    alter(ports)
    with pytest.raises((ExecutionEligibilityDenied, ExecutionEligibilityContractError)):
        eligible.admit_choice(admitted=admitted)
    assert ports.events in (['selection', 'facts'], ['selection', 'facts', 'policy'])
    assert 'runtime' not in ports.events


def test_explicit_empty_modality_policy_is_not_silently_inferred():
    # The evaluator eligibility policy issuer must explicitly approve zero modalities; the engine must
    # neither invent OCR nor infer a required modality from text labels.
    _, _, _, admitted, ports, eligible, binder = assemble()
    ports.facts = replace(ports.facts, required_modalities=())
    ports.policy = replace(ports.policy, required_modalities=())
    result = binder.bind_choice(admitted=admitted)
    assert result.approved_runtime.approval_ref == 'RUNTIME-APPROVAL'
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']


def test_runtime_inventory_cannot_override_approved_modalities():
    _, _, _, admitted, ports, eligible, binder = assemble()
    ports.runtime_record = replace(ports.runtime_record, approved_modalities=())
    with pytest.raises(RuntimeBindingDenied):
        binder.bind_choice(admitted=admitted)
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']


def test_handoff_must_use_same_eligibility_composer_as_runtime_binder():
    request, prep_ports, choice_composer, admitted, ports, eligible, binder = assemble()
    different = ProductionExecutionEligibilityComposer(
        selection=ports, facts=ports, policy=ports,
        max_identifier_characters=64, max_facts=8)
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choice_composer)
    with pytest.raises(RuntimeBindingContractError):
        ProductionExecutionHandoff(admission_entry=entry, eligibility=different, runtime=binder)
    assert ports.events == []


def test_execution_handoff_mismatched_eligibility_root_strips_private_ambient_context():
    _, preparation_ports, choice_composer, admitted, authorities, eligible, binder = assemble()
    from grading.integration.grading_orchestration import ProductionGradingEntry
    from tests.integration.test_authorized_preparation import _compose
    foreign_eligibility = ProductionExecutionEligibilityComposer(
        selection=authorities, facts=authorities, policy=authorities,
        max_identifier_characters=64, max_facts=8,
    )
    entry = ProductionGradingEntry(
        preparation=_compose(preparation_ports), choices=choice_composer,
    )
    try:
        raise ValueError('PRIVATE_STUDENT_CONTENT_CANARY')
    except ValueError:
        with pytest.raises(RuntimeBindingContractError) as caught:
            ProductionExecutionHandoff(
                admission_entry=entry, eligibility=foreign_eligibility, runtime=binder,
            )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert 'PRIVATE_STUDENT_CONTENT_CANARY' not in str(caught.value)
    assert authorities.events == []


def test_execution_handoff_matching_eligibility_root_remains_nonexecuting():
    _, preparation_ports, choice_composer, admitted, authorities, eligible, binder = assemble()
    from grading.integration.grading_orchestration import ProductionGradingEntry
    from tests.integration.test_authorized_preparation import _compose
    entry = ProductionGradingEntry(
        preparation=_compose(preparation_ports), choices=choice_composer,
    )
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=eligible, runtime=binder,
    )
    assert type(handoff) is ProductionExecutionHandoff
    assert authorities.events == []

# Post-install execution eligibility root continuity — authority must not be switched between
# configuration and use, or in any of the enrolled backend callbacks.
def _alternative_eligibility(admitted):
    from dataclasses import replace
    alternative = FixtureAuthorities(admitted)
    alternative.facts = replace(alternative.facts, facts=(EligibilityFact(
        'readiness', 'denied', FactOrigin.DIRECT, 'FOREIGN-ISSUER', 'FOREIGN-REV'),))
    alternative.policy = replace(alternative.policy, requirements=(EligibilityRequirement(
        'readiness', 'denied', (FactOrigin.DIRECT,)),))
    composer = ProductionExecutionEligibilityComposer(
        selection=alternative, facts=alternative, policy=alternative,
        max_identifier_characters=64, max_facts=8,
    )
    return alternative, composer


def test_substituted_b54_root_denied_before_g0_preparation_or_f17_access():
    request, prep_ports, choice, admitted, _, installed, binder = assemble()
    alternative, substitute = _alternative_eligibility(admitted)
    handoff = ProductionExecutionHandoff(
        admission_entry=ProductionGradingEntry(preparation=_compose(prep_ports), choices=choice),
        eligibility=installed, runtime=binder,
    )
    baseline_events = tuple(prep_ports.events)
    binder._eligibility = substitute
    try:
        raise ValueError('PRIVATE_STUDENT_EVIDENCE')
    except ValueError:
        with pytest.raises(RuntimeBindingDenied) as caught:
            handoff.prepare_choice_runtime(request=request)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert tuple(prep_ports.events) == baseline_events  # protected evidence not opened
    assert alternative.events == []


def test_public_binder_rejects_substituted_b54_without_alternative_policy_lookup():
    _, _, _, admitted, original, _, binder = assemble()
    alternative, substitute = _alternative_eligibility(admitted)
    binder._eligibility = substitute
    with pytest.raises(RuntimeBindingDenied):
        binder.bind_choice(admitted=admitted)
    assert original.events == []  # reject before any evaluator eligibility policy access
    assert alternative.events == []


@pytest.mark.parametrize('callback_failure', [False, True])
def test_b54_callback_root_change_denied_even_if_it_raises(callback_failure):
    _, _, _, admitted, _, _, _ = assemble()
    alternative, substitute = _alternative_eligibility(admitted)

    class RootSwappingSelection(FixtureAuthorities):
        binder = None
        def resolve_admitted_selection(self, *, scope):
            self.events.append('selection')
            self.binder._eligibility = substitute
            if callback_failure:
                raise RuntimeError('PRIVATE_F17_SECRET')
            return self.selection

    port = RootSwappingSelection(admitted)
    installed = ProductionExecutionEligibilityComposer(
        selection=port, facts=port, policy=port,
        max_identifier_characters=64, max_facts=8,
    )
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=port, eligibility=installed,
        installed=(InstalledRuntime('CHOICE','choice-native','1',
            'content-sha256-ref-1',evaluate_single_select_choice),),
        max_identifier_characters=64, max_modalities=8,
        max_installed_runtimes=8, max_facts=8,
    )
    port.binder = binder
    with pytest.raises(RuntimeBindingDenied) as caught:
        binder.bind_choice(admitted=admitted)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value)
    # execution eligibility completes its own already-started authority sequence, but no
    # substituted evaluator eligibility policy issuer and no evaluator invocation callback may be used.
    assert port.events in (['selection'], ['selection', 'facts', 'policy'])
    assert alternative.events == []


@pytest.mark.parametrize('callback_failure', [None, 'error', 'denied'])
def test_runtime_inventory_root_change_denied_before_result_or_outage(callback_failure):
    _, _, _, admitted, _, installed, _ = assemble()
    alternative, substitute = _alternative_eligibility(admitted)

    class RootSwappingInventory(FixtureAuthorities):
        binder = None
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            self.events.append('runtime')
            self.binder._eligibility = substitute
            if callback_failure == 'error':
                raise RuntimeError('PRIVATE_F59_SECRET')
            if callback_failure == 'denied':
                raise RuntimeBindingDenied('PRIVATE_F59_DENIAL')
            return self.runtime_record

    port = RootSwappingInventory(admitted)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=port, eligibility=installed,
        installed=(InstalledRuntime('CHOICE','choice-native','1',
            'content-sha256-ref-1',evaluate_single_select_choice),),
        max_identifier_characters=64, max_modalities=8,
        max_installed_runtimes=8, max_facts=8,
    )
    port.binder = binder
    with pytest.raises(RuntimeBindingDenied) as caught:
        binder.bind_choice(admitted=admitted)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert alternative.events == []
    assert 'runtime' in port.events


def test_unchanged_installed_b54_root_preserves_valid_nonexecuting_handoff():
    request, prep_ports, choice, admitted, port, installed, binder = assemble()
    handoff = ProductionExecutionHandoff(
        admission_entry=ProductionGradingEntry(preparation=_compose(prep_ports), choices=choice),
        eligibility=installed, runtime=binder,
    )
    output = handoff.prepare_choice_runtime(request=request)
    assert output.installed.handler is evaluate_single_select_choice
    assert port.events == ['selection', 'facts', 'policy', 'runtime']
    assert not hasattr(output, 'score') and not hasattr(output, 'execute')


def test_internal_structural_validator_cannot_consult_f59_after_root_substitution():
    _, _, _, admitted, port, installed, binder = assemble()
    eligible = installed.admit_choice(admitted=admitted)
    original_events = tuple(port.events)
    _, substitute = _alternative_eligibility(admitted)
    binder._eligibility = substitute
    with pytest.raises(RuntimeBindingDenied):
        binder._bind_eligibility(eligible)
    assert tuple(port.events) == original_events


def test_g0_pre_access_check_rejects_corruption_of_installed_root_reference():
    request, prep_ports, choice, admitted, port, installed, binder = assemble()
    handoff = ProductionExecutionHandoff(
        admission_entry=ProductionGradingEntry(preparation=_compose(prep_ports), choices=choice),
        eligibility=installed, runtime=binder,
    )
    initial = tuple(prep_ports.events)
    _, substitute = _alternative_eligibility(admitted)
    binder._installed_eligibility = substitute
    with pytest.raises(RuntimeBindingDenied):
        handoff.prepare_choice_runtime(request=request)
    assert tuple(prep_ports.events) == initial
    assert port.events == []


# Permanent regressions from the independent 2026-10-11 root-custody review.
@pytest.mark.parametrize('callback_fails', [False, True])
def test_selection_callback_cannot_rewire_installed_f17_operation(callback_fails):
    _, _, _, admitted, _, _, _ = assemble()
    foreign = FixtureAuthorities(admitted)
    foreign.policy = replace(foreign.policy, approval_ref='FOREIGN_F17_APPROVAL')
    foreign_composer = ProductionExecutionEligibilityComposer(
        selection=foreign, facts=foreign, policy=foreign,
        max_identifier_characters=64, max_facts=8,
    )

    class Redirecting(FixtureAuthorities):
        composer = None
        def resolve_admitted_selection(self, *, scope):
            self.events.append('selection')
            self.composer._operations = (
                self.composer._operations[0],
                self.composer._operations[1],
                foreign_composer._operations[2],
            )
            if callback_fails:
                raise RuntimeError('PRIVATE_F17_CALLBACK_SECRET')
            return self.selection

    original = Redirecting(admitted)
    composer = ProductionExecutionEligibilityComposer(
        selection=original, facts=original, policy=original,
        max_identifier_characters=64, max_facts=8,
    )
    original.composer = composer
    with pytest.raises(ExecutionEligibilityDenied):
        composer.admit_choice(admitted=admitted)
    assert foreign.events == []


def test_two_reference_root_swap_cannot_retarget_public_binder():
    _, _, _, admitted, _, _, binder = assemble()
    foreign, substitute = _alternative_eligibility(admitted)
    binder._eligibility = substitute
    binder._installed_eligibility = substitute
    with pytest.raises(RuntimeBindingDenied):
        binder.bind_choice(admitted=admitted)
    assert foreign.events == []


def test_g0_callback_changed_handoff_root_denied_before_runtime(monkeypatch):
    request, preparation_ports, choices, admitted, ports, installed, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(preparation_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=installed, runtime=binder,
    )
    _, alternative = _alternative_eligibility(admitted)

    def simulate_g0_callback_which_changes_root(self, *, request):
        handoff._eligibility = alternative
        return admitted

    # Scope-limited monkeypatch: validates the public paper execution integrity->P-B composition seam,
    # not the independently accepted paper execution integrity algorithm.
    monkeypatch.setattr(ProductionGradingEntry, 'prepare_choice',
                        simulate_g0_callback_which_changes_root)
    with pytest.raises(RuntimeBindingDenied):
        handoff.prepare_choice_runtime(request=request)
    assert ports.events == []


def test_mutated_key_revision_cannot_execute_foreign_equality():
    _, _, _, admitted, _, composer, binder = assemble()
    eligible = composer.admit_choice(admitted=admitted)

    class PoisonEquality:
        called = False
        def __eq__(self, other):
            self.called = True
            raise RuntimeError('PRIVATE_CREDENTIALS_IN_COMPARISON')

    poison = PoisonEquality()
    object.__setattr__(eligible, 'key_revision', poison)
    with pytest.raises(ExecutionEligibilityContractError):
        binder._bind_eligibility(eligible)
    assert poison.called is False


# Independently reproduced evaluator invocation double-root alias replacement.
def test_f59_cannot_repoint_both_installed_root_references_and_return_handoff():
    _, _, _, admitted = prepared()

    class SwitchingRuntimeInventory(FixtureAuthorities):
        binder = None
        replacement = None

        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            self.events.append('runtime')
            self.binder._eligibility = self.replacement
            self.binder._installed_eligibility = self.replacement
            return self.runtime_record

    source = SwitchingRuntimeInventory(admitted)
    original = ProductionExecutionEligibilityComposer(
        selection=source, facts=source, policy=source,
        max_identifier_characters=64, max_facts=8,
    )
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=source, eligibility=original,
        installed=(InstalledRuntime(
            'CHOICE', 'choice-native', '1', 'content-sha256-ref-1',
            evaluate_single_select_choice,
        ),),
        max_identifier_characters=64, max_modalities=8,
        max_installed_runtimes=8, max_facts=8,
    )
    foreign_source, replacement = _alternative_eligibility(admitted)
    source.binder = binder
    source.replacement = replacement

    with pytest.raises(RuntimeBindingDenied):
        binder.bind_choice(admitted=admitted)

    assert foreign_source.events == []


@pytest.mark.parametrize('callback_fails', [False, True])
def test_g0_root_change_always_denied_even_when_callback_raises(monkeypatch, callback_fails):
    request, preparation_ports, choices, admitted, ports, installed, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(preparation_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=installed, runtime=binder)
    _, alternative = _alternative_eligibility(admitted)
    def mutated_prepare(self, *, request):
        handoff._eligibility = alternative
        if callback_fails:
            raise RuntimeError('PRIVATE_G0_CALLBACK_SECRET')
        return admitted
    monkeypatch.setattr(ProductionGradingEntry, 'prepare_choice', mutated_prepare)
    with pytest.raises(RuntimeBindingDenied) as caught:
        handoff.prepare_choice_runtime(request=request)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert 'PRIVATE_' not in str(caught.value)
    assert ports.events == []


@pytest.mark.parametrize('failure', ['denied', 'outage'])
def test_f59_double_root_swap_has_denial_precedence_over_failure(failure):
    _, _, _, admitted = prepared()
    class MutatingInventory(FixtureAuthorities):
        binder = None
        replacement = None
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            self.events.append('runtime')
            self.binder._eligibility = self.replacement
            self.binder._installed_eligibility = self.replacement
            if failure == 'denied':
                raise ExecutionEligibilityDenied('PRIVATE_DENIED')
            raise RuntimeError('PRIVATE_OUTAGE')
    source = MutatingInventory(admitted)
    composer = ProductionExecutionEligibilityComposer(
        selection=source, facts=source, policy=source,
        max_identifier_characters=64, max_facts=8)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=source, eligibility=composer,
        installed=(InstalledRuntime('CHOICE', 'choice-native', '1',
                'content-sha256-ref-1', evaluate_single_select_choice),),
        max_identifier_characters=64, max_modalities=8,
        max_installed_runtimes=8, max_facts=8)
    foreign, replacement = _alternative_eligibility(admitted)
    source.binder, source.replacement = binder, replacement
    with pytest.raises(RuntimeBindingDenied) as caught:
        binder.bind_choice(admitted=admitted)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert foreign.events == []


def test_installed_configuration_anchors_are_not_normally_reassignable():
    _, _, _, admitted, ports, composer, binder = assemble()
    with pytest.raises(AttributeError):
        composer._pinned_operations = ()
    with pytest.raises(AttributeError):
        binder._configured_eligibility = object()
    with pytest.raises(AttributeError):
        binder._operation = lambda: None
    with pytest.raises(TypeError):
        binder._installed[('CHOICE','native','9','forged')] = None
    assert binder.bind_choice(admitted=admitted).approved_runtime.approval_ref == 'RUNTIME-APPROVAL'


@pytest.mark.parametrize('failure', ['return', 'denied', 'outage'])
def test_f59_cannot_modify_installed_f17_operations_after_valid_b54(failure):
    _, _, _, admitted = prepared()
    class MutatingOps(FixtureAuthorities):
        composer = None
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            self.events.append('runtime')
            a,b,c = self.composer._operations
            self.composer._operations = (a,b,lambda *,scope,capability_ref: self.policy)
            if failure == 'denied':
                raise ExecutionEligibilityDenied('PRIVATE_DENIAL')
            if failure == 'outage':
                raise RuntimeError('PRIVATE_OUTAGE')
            return self.runtime_record
    port = MutatingOps(admitted)
    composer = ProductionExecutionEligibilityComposer(
        selection=port, facts=port, policy=port,
        max_identifier_characters=64, max_facts=8)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=port, eligibility=composer,
        installed=(InstalledRuntime('CHOICE', 'choice-native', '1',
                'content-sha256-ref-1', evaluate_single_select_choice),),
        max_identifier_characters=64, max_modalities=8,
        max_installed_runtimes=8, max_facts=8)
    port.composer = composer
    with pytest.raises(RuntimeBindingDenied) as caught:
        binder.bind_choice(admitted=admitted)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)


def test_g0_constructor_rejects_corrupted_binder_root_without_ambient_leak():
    _, prep_ports, choices, admitted, ports, composer, binder = assemble()
    _, replacement = _alternative_eligibility(admitted)
    binder._eligibility = replacement
    binder._installed_eligibility = replacement
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    try:
        raise ValueError('PRIVATE_CORRUPTED_ROOT_AMBIENT_SECRET')
    except ValueError:
        with pytest.raises(RuntimeBindingContractError) as caught:
            ProductionExecutionHandoff(admission_entry=entry, eligibility=composer, runtime=binder)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert ports.events == []

# Installation-custody regression: the selected dispatch target, not a pair of
# independently mutable aliases, determines which source can be consulted.
@pytest.mark.parametrize('field', [
    '_pinned_operations', '_limit', '_maximum', '_installation',
])
def test_b54_installation_cannot_be_deleted_or_rebound(field):
    _, _, _, admitted, ports, composer, _ = assemble()
    original = getattr(composer, field)
    with pytest.raises(AttributeError):
        delattr(composer, field)
    with pytest.raises(AttributeError):
        setattr(composer, field, object())
    assert getattr(composer, field) is original
    assert composer.admit_choice(admitted=admitted).policy.approval_ref == 'ACADEMIC-APPROVAL'
    assert ports.events == ['selection', 'facts', 'policy']


@pytest.mark.parametrize('field', [
    '_configured_eligibility', '_operation', '_installed', '_limit',
    '_max_modalities', '_max_facts', '_installation',
])
def test_b55_installation_cannot_be_deleted_or_rebound(field):
    _, _, _, admitted, ports, _, binder = assemble()
    original = getattr(binder, field)
    with pytest.raises(AttributeError):
        delattr(binder, field)
    with pytest.raises(AttributeError):
        setattr(binder, field, object())
    assert getattr(binder, field) is original
    assert binder.bind_choice(admitted=admitted).approved_runtime.approval_ref == 'RUNTIME-APPROVAL'
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']


@pytest.mark.parametrize('field', [
    '_configured_entry', '_configured_eligibility', '_configured_runtime', '_installation',
])
def test_g0_installation_cannot_be_deleted_or_rebound(field):
    request, prep_ports, choices, admitted, ports, composer, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=composer, runtime=binder,
    )
    original = getattr(handoff, field)
    with pytest.raises(AttributeError):
        delattr(handoff, field)
    with pytest.raises(AttributeError):
        setattr(handoff, field, object())
    assert getattr(handoff, field) is original
    assert handoff.prepare_choice_runtime(request=request).installed.handler is evaluate_single_select_choice


def test_b54_selection_callback_attempted_anchor_deletion_does_not_use_foreign_f17():
    _, _, _, admitted = prepared()
    foreign = FixtureAuthorities(admitted)
    class Redirecting(FixtureAuthorities):
        composer = None
        def resolve_admitted_selection(self, *, scope):
            self.events.append('selection')
            del self.composer._pinned_operations
            return self.selection
    original = Redirecting(admitted)
    composer = ProductionExecutionEligibilityComposer(
        selection=original, facts=original, policy=original,
        max_identifier_characters=64, max_facts=8,
    )
    original.composer = composer
    with pytest.raises(ExecutionEligibilityUnavailable) as caught:
        composer.admit_choice(admitted=admitted)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert original.events == ['selection'] and foreign.events == []


def test_b55_binder_alias_deletion_is_sanitized_and_prevents_f17_access():
    _, _, _, admitted, ports, composer, binder = assemble()
    del binder._installed_eligibility  # non-authoritative diagnostic alias
    try:
        raise RuntimeError('PRIVATE_AMBIENT_ROOT_SECRET')
    except RuntimeError:
        with pytest.raises(RuntimeBindingDenied) as caught:
            binder.bind_choice(admitted=admitted)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert ports.events == []


def test_b54_operation_alias_deletion_is_sanitized_before_any_backend_access():
    _, _, _, admitted, ports, composer, binder = assemble()
    del composer._operations
    try:
        raise RuntimeError('PRIVATE_AMBIENT_OPERATION_SECRET')
    except RuntimeError:
        with pytest.raises(ExecutionEligibilityDenied) as caught:
            composer.admit_choice(admitted=admitted)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert ports.events == []


def test_g0_entry_alias_deletion_denied_before_protected_preparation():
    request, prep_ports, choices, admitted, ports, composer, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=composer, runtime=binder,
    )
    del handoff._entry
    try:
        raise RuntimeError('PRIVATE_AMBIENT_G0_SECRET')
    except RuntimeError:
        with pytest.raises(RuntimeBindingDenied) as caught:
            handoff.prepare_choice_runtime(request=request)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert ports.events == []


def test_b55_check_to_dispatch_interleaving_never_consults_replacement_issuer():
    """Deterministic scheduling at the source invocation point, without sleeps."""
    import sys
    import inspect
    import grading.integration.evaluator_execution_binding as module
    _, _, _, admitted, ports, composer, binder = assemble()
    foreign, replacement = _alternative_eligibility(admitted)
    source, first = inspect.getsourcelines(module.ProductionEvaluatorRuntimeBinder.bind_choice)
    target = next(first + i for i, text in enumerate(source)
                  if 'eligibility =' in text and '.admit_choice(' in text)
    changed = False
    def interleave(frame, event, arg):
        nonlocal changed
        if (event == 'line' and frame.f_code.co_name == 'bind_choice'
                and frame.f_code.co_filename == module.__file__
                and frame.f_lineno == target and not changed):
            binder._installed_eligibility = replacement
            changed = True
        return interleave
    prior = sys.gettrace()
    try:
        sys.settrace(interleave)
        with pytest.raises(RuntimeBindingDenied):
            binder.bind_choice(admitted=admitted)
    finally:
        sys.settrace(prior)
    assert changed
    assert foreign.events == []
    assert ports.events == ['selection', 'facts', 'policy']


def test_b54_policy_dispatch_interleaving_never_consults_foreign_f17():
    """An alias changed at dispatch time cannot decide which evaluator eligibility policy policy executes."""
    import sys
    import inspect
    import grading.integration.execution_eligibility as module
    _, _, _, admitted, ports, composer, binder = assemble()
    foreign = FixtureAuthorities(admitted)
    src, first = inspect.getsourcelines(module.ProductionExecutionEligibilityComposer._admit_choice)
    target = next(first + i for i, line in enumerate(src)
                  if 'returned_policy = _call(' in line)
    changed = False
    def interleave(frame, event, arg):
        nonlocal changed
        if (event == 'line' and frame.f_code.co_name == '_admit_choice'
                and frame.f_code.co_filename == module.__file__
                and frame.f_lineno == target and not changed):
            a, b, _ = composer._operations
            composer._operations = (a, b, foreign.resolve_approved_eligibility_policy)
            changed = True
        return interleave
    previous = sys.gettrace()
    try:
        sys.settrace(interleave)
        with pytest.raises(ExecutionEligibilityDenied):
            composer.admit_choice(admitted=admitted)
    finally:
        sys.settrace(previous)
    assert changed and foreign.events == []
    assert ports.events == ['selection', 'facts', 'policy']


def test_g0_dispatch_interleaving_invokes_original_preparation_only(monkeypatch):
    """Root alias drift cannot redirect which prepared-evidence entry is called."""
    import sys
    import inspect
    import grading.integration.evaluator_execution_binding as module
    request, prep_ports, choices, admitted, ports, composer, binder = assemble()
    entry_a = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    entry_b = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry_a, eligibility=composer, runtime=binder,
    )
    calls = []
    old_prepare = ProductionGradingEntry.prepare_choice
    def record_entry(self, *, request):
        calls.append(self)
        return old_prepare(self, request=request)
    monkeypatch.setattr(ProductionGradingEntry, 'prepare_choice', record_entry)
    src, first = inspect.getsourcelines(module.ProductionExecutionHandoff.prepare_choice_runtime)
    target = next(first + i for i, line in enumerate(src)
                  if 'admitted =' in line and '.prepare_choice(' in line)
    changed = False
    def interleave(frame, event, arg):
        nonlocal changed
        if (event == 'line' and frame.f_code.co_name == 'prepare_choice_runtime'
                and frame.f_code.co_filename == module.__file__
                and frame.f_lineno == target and not changed):
            handoff._entry = entry_b
            changed = True
        return interleave
    previous = sys.gettrace()
    try:
        sys.settrace(interleave)
        with pytest.raises(RuntimeBindingDenied):
            handoff.prepare_choice_runtime(request=request)
    finally:
        sys.settrace(previous)
    assert changed and calls == [entry_a]
    assert ports.events == []


@pytest.mark.parametrize('owner', ['composer', 'binder', 'handoff'])
def test_installed_owner_and_installation_record_have_no_writable_instance_dict(owner):
    from dataclasses import FrozenInstanceError
    request, prep_ports, choices, admitted, ports, composer, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    handoff = ProductionExecutionHandoff(admission_entry=entry, eligibility=composer, runtime=binder)
    subject = {'composer': composer, 'binder': binder, 'handoff': handoff}[owner]
    assert not hasattr(subject, '__dict__')
    with pytest.raises(AttributeError):
        subject.__dict__ = {'_installation': object()}
    frozen = subject._installation
    field = {'composer': 'operations', 'binder': 'eligibility', 'handoff': 'entry'}[owner]
    existing = getattr(frozen, field)
    with pytest.raises((AttributeError, FrozenInstanceError)):
        setattr(frozen, field, object())
    with pytest.raises((AttributeError, FrozenInstanceError)):
        delattr(frozen, field)
    assert getattr(frozen, field) is existing
    assert subject._installation is frozen
