"""Family execution eligibility/evaluator handler binding real installed-selection controls, no physical attempt claim."""
from dataclasses import replace
import pytest

from grading.active_question_authority import ContextPolicy
from grading.contracts.evaluation import EvaluatorMetadata
from grading.contracts.capability import EvaluatorCapabilityRef
from grading.contracts.numeric_evaluation import (
    DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION,
)
from grading.integration.paper_family_evaluation import evaluate_supported_paper_questions
from grading.integration.execution_eligibility import ExecutionEligibilityDenied
from grading.integration.evaluator_execution_binding import (
    InstalledRuntime, ProductionEvaluatorRuntimeBinder, RuntimeBindingDenied,
    RuntimeBindingContractError,
)
from tests.integration.test_execution_eligibility_runtime import assemble


def family_fixture(family):
    _, _, _, admitted, ports, eligibility, _ = assemble()
    if family == 'NUMERIC':
        metadata = EvaluatorMetadata(DETERMINISTIC_NUMERIC_EVALUATOR_ID, DETERMINISTIC_NUMERIC_EVALUATOR_VERSION)
    else:
        metadata = EvaluatorMetadata('approved-direct-provider', '1')
    ref = EvaluatorCapabilityRef(metadata, 1)
    record = replace(ports.selection.resolved_capability.record,
                     capability_ref=ref, supported_answer_types=(family,))
    ports.selection = replace(ports.selection,
        classification=replace(ports.selection.classification, answer_type=family),
        selected_capability_ref=ref,
        resolved_capability=replace(ports.selection.resolved_capability, record=record))
    ports.facts = replace(ports.facts, capability_ref=ref)
    ports.policy = replace(ports.policy, capability_ref=ref)
    ports.runtime_record = replace(ports.runtime_record, capability_ref=ref,
        family=family, runtime_id='approved-'+family,
        implementation_ref='sha256-approved-'+family)
    installed = InstalledRuntime(family, 'approved-'+family, '1',
                                 'sha256-approved-'+family, evaluate_supported_paper_questions)
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=ports, eligibility=eligibility, installed=(installed,),
        max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8)
    return admitted.scope, ports, eligibility, binder


@pytest.mark.parametrize('family', ('DIRECT', 'NUMERIC'))
def test_installed_family_selector_facts_policy_runtime_true_positive_without_execution(family):
    scope, ports, _, binder = family_fixture(family)
    bound = binder.bind_family(scope=scope, family=family, context_policy=ContextPolicy.DIRECT)
    assert bound.approved_runtime.family == family
    assert bound.installed.handler is evaluate_supported_paper_questions
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']
    assert not hasattr(bound, 'score')


@pytest.mark.parametrize('family', ('DIRECT', 'NUMERIC'))
def test_wrong_family_cannot_reach_runtime_approval(family):
    scope, ports, _, binder = family_fixture(family)
    wrong = 'NUMERIC' if family == 'DIRECT' else 'DIRECT'
    with pytest.raises(ExecutionEligibilityDenied):
        binder.bind_family(scope=scope, family=wrong, context_policy=ContextPolicy.DIRECT)
    assert 'runtime' not in ports.events


def test_original_scope_mutated_by_callback_blocks_before_next_authority_contact():
    scope, ports, eligibility, _ = family_fixture('DIRECT')
    class Mutator:
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            object.__setattr__(scope, 'tenant_ref', 'FOREIGN')
            return ports.runtime_record
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=Mutator(), eligibility=eligibility,
        installed=(InstalledRuntime('DIRECT', 'approved-DIRECT', '1',
                    'sha256-approved-DIRECT', evaluate_supported_paper_questions),),
        max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8)
    with pytest.raises(ExecutionEligibilityDenied):
        binder.bind_family(scope=scope, family='DIRECT', context_policy=ContextPolicy.DIRECT)


def test_uninstalled_family_is_denied_instead_of_auto_enabled():
    scope, ports, eligibility, _ = family_fixture('NUMERIC')
    from grading.choice_evaluator import evaluate_single_select_choice
    binder = ProductionEvaluatorRuntimeBinder(
        inventory=ports, eligibility=eligibility,
        installed=(InstalledRuntime('CHOICE', 'choice-only', '1', 'other', evaluate_single_select_choice),),
        max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8)
    with pytest.raises(RuntimeBindingDenied):
        binder.bind_family(scope=scope, family='NUMERIC', context_policy=ContextPolicy.DIRECT)


def test_runtime_cannot_be_approvable_with_arbitrary_handler():
    _, ports, eligibility, _ = family_fixture('DIRECT')
    with pytest.raises(RuntimeBindingContractError):
        ProductionEvaluatorRuntimeBinder(
            inventory=ports, eligibility=eligibility,
            installed=(InstalledRuntime('DIRECT', 'approved-DIRECT', '1',
                        'sha256-approved-DIRECT', lambda **kwargs: None),),
            max_identifier_characters=64, max_modalities=8, max_installed_runtimes=8, max_facts=8)
