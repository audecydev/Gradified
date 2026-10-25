"""evaluator invocation CHOICE owned invocation; the fixture allocator is NOT an physical attempt claim approval."""
from __future__ import annotations

from dataclasses import replace
from contextlib import contextmanager
import sys

import pytest

from grading.choice_evaluator import evaluate_single_select_choice
from grading.contracts.evaluation import EvaluatedCriterionJudgment
from grading.integration.evaluator_invocation import (
    AttemptReservation, AttemptReservationRejected, AttemptReservationUnavailable,
    InvocationContractError, InvocationDenied, InvocationUnavailable,
    OneQuestionExecutionCandidate, ProductionChoiceEvaluatorInvoker,
)
from grading.integration.grading_orchestration import ProductionGradingEntry
from grading.integration.evaluator_execution_binding import (
    BoundEvaluatorRuntime, ProductionExecutionHandoff,
)
from tests.integration.test_execution_eligibility_runtime import assemble
from tests.integration.test_authorized_preparation import _compose


class FixtureAttempts:
    """Only a controlled structural physical attempt claim source; cannot establish durable uniqueness."""
    def __init__(self):
        self.events = []

    def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                        implementation_ref, eligibility_policy_id,
                        eligibility_policy_version):
        self.events.append((scope, family, runtime_id))
        return AttemptReservation(scope, 'ATTEMPT-1', 'RESERVATION-1', family,
                                  runtime_id, runtime_version, implementation_ref,
                                  eligibility_policy_id, eligibility_policy_version)


def assembled_invoker(attempts=None):
    request, prep_ports, choices, _, ports, eligibility, binder = assemble()
    entry = ProductionGradingEntry(preparation=_compose(prep_ports), choices=choices)
    handoff = ProductionExecutionHandoff(
        admission_entry=entry, eligibility=eligibility, runtime=binder,
    )
    attempts = FixtureAttempts() if attempts is None else attempts
    invoker = ProductionChoiceEvaluatorInvoker(
        handoff=handoff, attempts=attempts, max_identifier_characters=64,
    )
    return invoker, request, ports, attempts


@contextmanager
def _track_frozen_calls():
    """Use a real function-frame entry count, independent of result metadata."""
    counter = [0]
    previous = sys.getprofile()
    def profile(frame, event, arg):
        if event == 'call' and frame.f_code is evaluate_single_select_choice.__code__:
            counter[0] += 1
    try:
        sys.setprofile(profile)
        yield counter
    finally:
        sys.setprofile(previous)


def test_true_frozen_evaluator_runs_once_then_s2a_consumes_emitted_judgments():
    invoker, request, ports, attempts = assembled_invoker()
    with _track_frozen_calls() as calls:
        result = invoker.run_one_question(request=request)
    assert calls == [1]
    assert type(result) is OneQuestionExecutionCandidate
    assert result.reservation.attempt_id == 'ATTEMPT-1'
    assert type(result.emitted_judgments) is tuple
    assert all(type(j) is EvaluatedCriterionJudgment for j in result.emitted_judgments)
    assert len(result.execution.questions) == 1
    assert (result.execution.questions[0].verified.evaluated_judgments
            == result.emitted_judgments)
    assert result.execution.context.grading_run_id == result.reservation.scope.grading_run_id
    assert result.execution.context.submission_ref == result.reservation.scope.submission_ref
    assert result.execution.context.exam_ref == result.reservation.scope.exam_ref
    assert result.execution.context.grading_spec_ref == result.reservation.scope.grading_spec_ref
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']
    assert len(attempts.events) == 1


@pytest.mark.parametrize('alter', [
    lambda r: replace(r, attempt_id=''),
    lambda r: replace(r, attempt_id=' A '),
    lambda r: replace(r, attempt_id='X'*65),
    lambda r: replace(r, attempt_id=True),
    lambda r: replace(r, reservation_ref=''),
    lambda r: replace(r, scope=replace(r.scope, tenant_ref='OTHER-TENANT')),
    lambda r: replace(r, scope=replace(r.scope, grading_run_id='OTHER-RUN')),
    lambda r: replace(r, scope=replace(r.scope, question_id='OTHER-QUESTION')),
    lambda r: replace(r, scope=replace(r.scope, submission_ref='OTHER-SUBMISSION')),
    lambda r: replace(r, family='DIRECT'),
    lambda r: replace(r, runtime_id='other-runtime'),
    lambda r: replace(r, runtime_version='unapproved'),
    lambda r: replace(r, implementation_ref='foreign-implementation'),
    lambda r: replace(r, eligibility_policy_id='foreign-policy'),
    lambda r: replace(r, eligibility_policy_version=2),
    lambda r: replace(r, eligibility_policy_version=True),
    lambda r: object(),
])
def test_foreign_or_malformed_f25_return_never_invokes_or_scores(alter):
    class Poison(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            issued = super().reserve_attempt(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version,
                implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version,
            )
            return alter(issued)
    invoker, request, ports, attempts = assembled_invoker(Poison())
    with _track_frozen_calls() as calls:
        with pytest.raises((InvocationDenied, InvocationContractError)):
            invoker.run_one_question(request=request)
    assert calls == [0]
    assert len(attempts.events) == 1
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']


@pytest.mark.parametrize('raised,expected', [
    (AttemptReservationRejected, InvocationDenied),
    (AttemptReservationUnavailable, InvocationUnavailable),
    (RuntimeError, InvocationUnavailable),
])
def test_allocator_denial_outage_or_exception_stops_before_evaluator(raised, expected):
    class Fail(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            self.events.append('allocator')
            raise raised('PRIVATE_INTERNAL_ATTEMPT_SECRET')
    invoker, request, _, attempts = assembled_invoker(Fail())
    with _track_frozen_calls() as calls:
        try:
            raise RuntimeError('PRIVATE_CALLER_EXCEPTION')
        except RuntimeError:
            with pytest.raises(expected) as caught:
                invoker.run_one_question(request=request)
    assert calls == [0]
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert attempts.events == ['allocator']


def test_allocator_mutates_its_scope_argument_and_denies_with_integrity_precedence():
    class Mutation(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            object.__setattr__(scope, 'tenant_ref', 'OTHER-TENANT')
            self.events.append('mutated')
            raise AttemptReservationUnavailable('PRIVATE_BACKEND_FAILURE')
    invoker, request, _, attempts = assembled_invoker(Mutation())
    with _track_frozen_calls() as calls:
        with pytest.raises(InvocationDenied) as caught:
            invoker.run_one_question(request=request)
    assert calls == [0]
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert attempts.events == ['mutated']


def test_allocator_corrupts_root_alias_then_returns_valid_reservation_must_fail():
    class Mutation(FixtureAttempts):
        invoker = None
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            result = super().reserve_attempt(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version, implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version,
            )
            self.invoker._installation.handoff._entry = object()
            return result
    ports = Mutation()
    invoker, request, _, _ = assembled_invoker(ports)
    ports.invoker = invoker
    with _track_frozen_calls() as calls:
        with pytest.raises(InvocationDenied):
            invoker.run_one_question(request=request)
    assert calls == [0]


def test_installation_reassignment_and_deletion_are_rejected():
    invoker, _, _, _ = assembled_invoker()
    original = invoker._installation
    with pytest.raises(AttributeError):
        del invoker._installation
    with pytest.raises(AttributeError):
        invoker._installation = original
    assert invoker._installation is original


def test_constructed_runtime_binding_is_not_an_invocation_credential():
    invoker, request, _, attempts = assembled_invoker()
    with _track_frozen_calls() as calls:
        with pytest.raises((InvocationContractError, InvocationDenied, TypeError, ValueError)):
            invoker.run_one_question(request=BoundEvaluatorRuntime(None, None, None))
    assert calls == [0]
    assert attempts.events == []


def test_wrong_allocator_method_signature_is_rejected_before_call():
    class Bad:
        def reserve_attempt(self, *, scope):
            raise AssertionError('Must not call wrong-signature issuer')
    with pytest.raises(InvocationContractError):
        assembled_invoker(Bad())


def test_invalid_limit_refused_and_no_installed_authority_run():
    invoker, _, _, _ = assembled_invoker()
    with pytest.raises(InvocationContractError):
        ProductionChoiceEvaluatorInvoker(
            handoff=invoker._installation.handoff,
            attempts=FixtureAttempts(), max_identifier_characters=True,
        )


def test_poison_equality_in_reservation_never_executes_before_exact_type_admission():
    class PoisonEquals:
        def __init__(self):
            self.called = False
        def __eq__(self, other):
            self.called = True
            raise RuntimeError('PRIVATE_SIDE_EFFECT')
    poison = PoisonEquals()
    class Poison(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            issued = super().reserve_attempt(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version,
                implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version,
            )
            object.__setattr__(issued, 'runtime_id', poison)
            return issued
    invoker, request, _, _ = assembled_invoker(Poison())
    with pytest.raises(InvocationContractError):
        invoker.run_one_question(request=request)
    assert poison.called is False


def test_allocator_reentrancy_cannot_create_nested_scoring_attempt():
    class Reentrant(FixtureAttempts):
        invoker = None
        request = None
        nested_errors = None
        attempted = False
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            if not self.attempted:
                self.attempted = True
                try:
                    self.invoker.run_one_question(request=self.request)
                except InvocationDenied as exc:
                    self.nested_errors = type(exc)
            return super().reserve_attempt(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version,
                implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version,
            )
    port = Reentrant()
    invoker, request, events, attempts = assembled_invoker(port)
    port.invoker, port.request = invoker, request
    with _track_frozen_calls() as calls:
        invoker.run_one_question(request=request)
    assert calls == [1]
    assert port.nested_errors is InvocationDenied
    assert len(port.events) == 1
    assert events.events == ['selection','facts','policy','runtime']


def test_s2a_uses_exact_tuple_emitted_by_original_frozen_choice_call():
    import grading.execution as execution
    expected = execution.execute_grading_from_evaluations.__code__
    seen = []
    previous = sys.getprofile()
    def inspect_origin(frame, event, arg):
        if event == 'call' and frame.f_code is expected:
            seen.append(frame.f_locals['questions'][0].judgments)
    invoker, request, _, _ = assembled_invoker()
    try:
        sys.setprofile(inspect_origin)
        result = invoker.run_one_question(request=request)
    finally:
        sys.setprofile(previous)
    assert len(seen) == 1
    assert seen[0] is result.emitted_judgments
    assert result.execution.questions[0].verified.evaluated_judgments is seen[0]


@pytest.mark.parametrize('failure', ['evidence', 'scoring'])
def test_s2a_frozen_consumer_domain_failure_is_sanitized_not_a_student_error(monkeypatch, failure):
    import grading.execution as execution
    from grading.verification.evidence import EvidenceVerificationError
    from grading.contracts.errors import ScoringError
    failure_type = EvidenceVerificationError if failure == 'evidence' else ScoringError
    def fail(**kwargs):
        raise failure_type('PRIVATE_SCHOOL_MATERIAL')
    monkeypatch.setattr(execution, 'verify_evaluated_judgments' if failure == 'evidence' else 'reduce_question', fail)
    invoker, request, _, _ = assembled_invoker()
    try:
        raise RuntimeError('PRIVATE_AMBIENT_SCHOOL_SECRET')
    except RuntimeError:
        with pytest.raises(InvocationContractError) as caught:
            invoker.run_one_question(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)


def test_allocator_operation_captured_before_instance_method_replacement():
    port = FixtureAttempts()
    invoker, request, _, _ = assembled_invoker(port)
    foreign = []
    def untrusted(**kwargs):
        foreign.append('foreign F25')
        raise AssertionError('must not consult replacement callback')
    port.reserve_attempt = untrusted
    result = invoker.run_one_question(request=request)
    assert result.reservation.attempt_id == 'ATTEMPT-1'
    assert len(port.events) == 1
    assert foreign == []


def test_dispatch_uses_captured_handler_even_if_module_alias_changes_between_check_and_call():
    import grading.integration.evaluator_invocation as module
    invoker, request, _, _ = assembled_invoker()
    foreign_calls = []
    changed = [False]
    snapshots = [0]
    original_alias = module.evaluate_single_select_choice
    def foreign(**kwargs):
        foreign_calls.append('WRONG-EVALUATOR')
        return original_alias(**kwargs)
    def interleave(frame, event, arg):
        # The third pure snapshot finishes immediately before actual dispatch.
        # Schedule by callback completion, not source-text line numbers.
        if event == 'return' and frame.f_code is module._validated_binding_snapshot.__code__:
            snapshots[0] += 1
            if snapshots[0] == 3 and not changed[0]:
                module.evaluate_single_select_choice = foreign
                changed[0] = True
        return interleave
    previous = sys.gettrace()
    try:
        sys.settrace(interleave)
        with _track_frozen_calls() as calls:
            result = invoker.run_one_question(request=request)
    finally:
        sys.settrace(previous)
        module.evaluate_single_select_choice = original_alias
    assert changed == [True]
    assert foreign_calls == []
    assert calls == [1]
    assert len(result.emitted_judgments) > 0

# Regression group: original installed binder/scoring targets and final public
# confidentiality. These are invariants discovered by independent review.

def test_f25_alias_redirect_cannot_consult_alternative_s2a(monkeypatch):
    import grading.integration.evaluator_invocation as module
    import grading.execution as execution
    actual_code = execution.execute_grading_from_evaluations.__code__
    calls = []
    class Retarget(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            response = super().reserve_attempt(
                scope=scope, family=family, runtime_id=runtime_id,
                runtime_version=runtime_version, implementation_ref=implementation_ref,
                eligibility_policy_id=eligibility_policy_id,
                eligibility_policy_version=eligibility_policy_version)
            monkeypatch.setattr(module, 'execute_grading_from_evaluations',
                                lambda **kw: calls.append('FOREIGN_S2A') or object())
            return response
    invoker, request, _, attempts = assembled_invoker(Retarget())
    count = {'s2a': 0, 'choice': 0}
    old = sys.getprofile()
    def observe(frame, event, arg):
        if event == 'call':
            if frame.f_code is actual_code:
                count['s2a'] += 1
            if frame.f_code is evaluate_single_select_choice.__code__:
                count['choice'] += 1
    try:
        sys.setprofile(observe)
        result = invoker.run_one_question(request=request)
    finally:
        sys.setprofile(old)
    assert count == {'s2a': 1, 'choice': 1}
    assert calls == [] and len(attempts.events) == 1
    assert result.execution.questions[0].verified.evaluated_judgments is result.emitted_judgments


def test_post_install_rebinding_of_choice_input_binder_never_dispatches_foreign(monkeypatch):
    import grading.integration.evaluator_invocation as module
    invoker, request, _, _ = assembled_invoker()
    foreign = []
    monkeypatch.setattr(module, 'bind_choice_evaluation_inputs',
                        lambda **kw: foreign.append('FOREIGN_BINDER') or object())
    with _track_frozen_calls() as count:
        result = invoker.run_one_question(request=request)
    assert foreign == [] and count == [1]
    assert result.execution.questions[0].verified.evaluated_judgments is result.emitted_judgments


@pytest.mark.parametrize('target', ['binder', 's2a'])
def test_alias_rebound_before_installation_is_refused_without_f25_effects(monkeypatch, target):
    import grading.integration.evaluator_invocation as module
    alias = ('bind_choice_evaluation_inputs' if target == 'binder'
             else 'execute_grading_from_evaluations')
    foreign = []
    monkeypatch.setattr(module, alias, lambda **kw: foreign.append(target))
    with pytest.raises(InvocationContractError) as caught:
        assembled_invoker()
    assert foreign == []
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize('alter', ['wrong_type','copied_context','copied_judgments','wrong_question'])
def test_s2a_result_origin_validation_rejects_invalid_return(monkeypatch, alter):
    import grading.execution as execution
    from dataclasses import replace
    real_result_type = execution.GradingExecutionResult
    def substitute(*args, **kw):
        result = real_result_type(*args, **kw)
        if alter == 'wrong_type':
            return object()
        if alter == 'copied_context':
            return replace(result, context=replace(result.context))
        if alter == 'copied_judgments':
            original = result.questions[0]
            copied = tuple([*original.verified.evaluated_judgments])
            assert copied is not original.verified.evaluated_judgments
            return replace(result, questions=(replace(original, verified=replace(
                original.verified, evaluated_judgments=copied)),))
        original = result.questions[0]
        # A foreign question identity in an already-built scored record.
        object.__setattr__(original.verified, 'question_id', 'FOREIGN-QUESTION')
        return result
    invoker, request, _, attempts = assembled_invoker()
    monkeypatch.setattr(execution, 'GradingExecutionResult', substitute)
    with _track_frozen_calls() as count:
        with pytest.raises(InvocationContractError) as caught:
            invoker.run_one_question(request=request)
    assert count == [1] and len(attempts.events) == 1
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_f25_malformed_post_callback_scope_is_integrity_denial_not_contract(monkeypatch):
    class Corrupt(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            object.__setattr__(scope, 'tenant_ref', object())
            self.events.append('mutation')
            raise AttemptReservationUnavailable('PRIVATE_UNAVAILABLE')
    invoker, request, _, port = assembled_invoker(Corrupt())
    with _track_frozen_calls() as calls:
        with pytest.raises(InvocationDenied) as caught:
            invoker.run_one_question(request=request)
    assert calls == [0] and port.events == ['mutation']
    assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_unexpected_error_inside_real_s2a_is_typed_private_and_nonofficial(monkeypatch):
    import grading.execution as execution
    def break_verifier(**kw):
        raise RuntimeError('PRIVATE_S2A_EXCEPTION_DETAILS')
    invoker, request, _, attempts = assembled_invoker()
    monkeypatch.setattr(execution, 'verify_evaluated_judgments', break_verifier)
    with _track_frozen_calls() as calls:
        with pytest.raises(InvocationUnavailable) as caught:
            invoker.run_one_question(request=request)
    assert calls == [1] and len(attempts.events) == 1
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'PRIVATE' not in str(caught.value)


def test_bad_root_public_failure_and_constructor_have_no_private_context():
    from grading.integration.evaluator_execution_binding import RuntimeBindingDenied
    runner, request, _, attempts = assembled_invoker()
    root = runner._installation.handoff
    root._entry = object()
    try:
        raise RuntimeError('PRIVATE_OUTER_CONTEXT')
    except RuntimeError:
        with pytest.raises(InvocationDenied) as failure:
            runner.run_one_question(request=request)
        with pytest.raises(InvocationContractError) as construct:
            ProductionChoiceEvaluatorInvoker(handoff=root, attempts=FixtureAttempts(),
                                            max_identifier_characters=64)
    assert failure.value.__context__ is None and failure.value.__cause__ is None
    assert construct.value.__context__ is None and construct.value.__cause__ is None
    assert attempts.events == []

# Source-review closure: physical attempt claim exception-family semantics and constructor privacy.
# These are ordinary trusted-adapter failure semantics, not issuer authentication.

class _ScopedF25Refusal(AttemptReservationRejected):
    pass


class _ScopedF25Outage(AttemptReservationUnavailable):
    pass


@contextmanager
def _track_choice_and_s2a_calls():
    from grading.execution import execute_grading_from_evaluations
    counts = {'choice': 0, 's2a': 0}
    previous = sys.getprofile()
    def observe(frame, event, arg):
        if event == 'call':
            if frame.f_code is evaluate_single_select_choice.__code__:
                counts['choice'] += 1
            elif frame.f_code is execute_grading_from_evaluations.__code__:
                counts['s2a'] += 1
    try:
        sys.setprofile(observe)
        yield counts
    finally:
        sys.setprofile(previous)


@pytest.mark.parametrize('failure_type,expected_type', [
    (AttemptReservationRejected, InvocationDenied),
    (_ScopedF25Refusal, InvocationDenied),
    (_ScopedF25Outage, InvocationUnavailable),
    (RuntimeError, InvocationUnavailable),
])
def test_f25_exception_family_preserves_refusal_outage_and_no_execution(failure_type, expected_type):
    class Refuse(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            self.events.append('called')
            raise failure_type('PRIVATE_F25_BACKEND')
    invoker, request, ports, attempts = assembled_invoker(Refuse())
    with _track_choice_and_s2a_calls() as count:
        with pytest.raises(expected_type) as got:
            invoker.run_one_question(request=request)
    assert type(got.value) is expected_type
    assert got.value.__cause__ is None and got.value.__context__ is None
    assert 'PRIVATE' not in str(got.value)
    assert count == {'choice': 0, 's2a': 0}
    assert attempts.events == ['called']
    assert ports.events == ['selection', 'facts', 'policy', 'runtime']


@pytest.mark.parametrize('failure_type', [_ScopedF25Refusal, _ScopedF25Outage])
def test_post_f25_scope_corruption_overrides_exception_family(failure_type):
    class Corrupt(FixtureAttempts):
        def reserve_attempt(self, *, scope, family, runtime_id, runtime_version,
                            implementation_ref, eligibility_policy_id,
                            eligibility_policy_version):
            self.events.append('called')
            object.__setattr__(scope, 'tenant_ref', object())
            raise failure_type('PRIVATE_F25_OUTCOME')
    invoker, request, _, attempts = assembled_invoker(Corrupt())
    with _track_choice_and_s2a_calls() as count:
        with pytest.raises(InvocationDenied) as got:
            invoker.run_one_question(request=request)
    assert type(got.value) is InvocationDenied
    assert got.value.__context__ is None and got.value.__cause__ is None
    assert count == {'choice': 0, 's2a': 0}
    assert attempts.events == ['called']


def test_unexpected_constructor_dependency_failure_is_sanitized_at_outer_boundary(monkeypatch):
    import traceback
    import grading.integration.evaluator_invocation as module
    root = assembled_invoker()[0]._installation.handoff
    def break_capture(*args, **kwargs):
        raise RuntimeError('PRIVATE_INSTALLATION_CAPTURE')
    monkeypatch.setattr(module, '_capture', break_capture)
    try:
        raise RuntimeError('PRIVATE_AMBIENT_EXCEPTION')
    except RuntimeError:
        with pytest.raises(InvocationContractError) as got:
            ProductionChoiceEvaluatorInvoker(
                handoff=root, attempts=FixtureAttempts(), max_identifier_characters=64,
            )
    assert type(got.value) is InvocationContractError
    assert got.value.__context__ is None and got.value.__cause__ is None
    assert 'PRIVATE' not in str(got.value)
    assert 'PRIVATE' not in ''.join(traceback.format_exception(got.value))


# Independent result-admission review: exact nested type-before-access custody.
# The attack corrupts an otherwise genuine frozen scoring result after construction;
# it does not grant caller data a way to monkeypatch production Python code.
class _NestedPoisonComparison:
    calls = 0

    def __ne__(self, other):
        type(self).calls += 1
        raise RuntimeError('PRIVATE_NESTED_COMPARISON')


class _NestedForeignQuestion:
    reads = 0

    def __getattribute__(self, name):
        if name == 'verified':
            type(self).reads += 1
            raise RuntimeError('PRIVATE_FOREIGN_VERIFIED_GETTER')
        return object.__getattribute__(self, name)


@pytest.mark.parametrize('attack', [
    'record_object', 'record_foreign_getter', 'verified_object',
    'questions_object', 'verified_question_poison', 'score_question_poison',
    'paper_score_object', 'paper_question_scores_object', 'paper_score_foreign',
    'paper_spec_foreign', 'paper_spec_poison',
])
def test_final_s2a_admission_rejects_malformed_nested_result_before_foreign_access(
        monkeypatch, attack):
    import grading.execution as execution
    import traceback
    original_type = execution.GradingExecutionResult
    _NestedForeignQuestion.reads = 0
    _NestedPoisonComparison.calls = 0

    def constructed_then_corrupted(**kwargs):
        result = original_type(**kwargs)
        record = result.questions[0]
        if attack == 'record_object':
            object.__setattr__(result, 'questions', (object(),))
        elif attack == 'record_foreign_getter':
            object.__setattr__(result, 'questions', (_NestedForeignQuestion(),))
        elif attack == 'verified_object':
            object.__setattr__(record, 'verified', object())
        elif attack == 'questions_object':
            object.__setattr__(result, 'questions', object())
        elif attack == 'verified_question_poison':
            object.__setattr__(record.verified, 'question_id', _NestedPoisonComparison())
        elif attack == 'score_question_poison':
            object.__setattr__(record.score, 'question_id', _NestedPoisonComparison())
        elif attack == 'paper_score_object':
            object.__setattr__(result, 'paper_score', object())
        elif attack == 'paper_question_scores_object':
            object.__setattr__(result.paper_score, 'question_results', object())
        elif attack == 'paper_spec_foreign':
            object.__setattr__(result.paper_score, 'grading_spec_ref', object())
        elif attack == 'paper_spec_poison':
            object.__setattr__(result.paper_score, 'grading_spec_ref', _NestedPoisonComparison())
        else:
            object.__setattr__(result.paper_score, 'question_results', (object(),))
        return result

    monkeypatch.setattr(execution, 'GradingExecutionResult', constructed_then_corrupted)
    invoker, request, _, attempts = assembled_invoker()
    with _track_choice_and_s2a_calls() as calls:
        try:
            raise RuntimeError('PRIVATE_AMBIENT_EXCEPTION')
        except RuntimeError:
            with pytest.raises(InvocationContractError) as caught:
                invoker.run_one_question(request=request)
    assert calls == {'choice': 1, 's2a': 1}
    assert len(attempts.events) == 1  # physical attempt claim may have reserved; no rollback claim.
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in str(caught.value)
    assert 'PRIVATE' not in ''.join(traceback.format_exception(caught.value))
    assert _NestedForeignQuestion.reads == 0
    assert _NestedPoisonComparison.calls == 0


def test_unexpected_installation_capture_never_invokes_f25_choice_or_s2a(monkeypatch):
    import grading.integration.evaluator_invocation as module
    import traceback
    root = assembled_invoker()[0]._installation.handoff
    attempted = FixtureAttempts()

    def fail_capture(*args, **kwargs):
        raise RuntimeError('PRIVATE_INSTALL_FAILURE')

    monkeypatch.setattr(module, '_capture', fail_capture)
    with _track_choice_and_s2a_calls() as calls:
        try:
            raise RuntimeError('PRIVATE_AMBIENT_INSTALL')
        except RuntimeError:
            with pytest.raises(InvocationContractError) as caught:
                ProductionChoiceEvaluatorInvoker(
                    handoff=root, attempts=attempted, max_identifier_characters=64,
                )
    assert attempted.events == []
    assert calls == {'choice': 0, 's2a': 0}
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in ''.join(traceback.format_exception(caught.value))

# Full exposed-output contract regression. All mutations below are performed
# AFTER genuine frozen scoring construction: they challenge evaluator invocation's last admission
# boundary without suggesting that the trusted scorer normally emits corruption.
class _ForeignComparison:
    calls = 0
    def __eq__(self, other):
        type(self).calls += 1
        raise RuntimeError('PRIVATE_FOREIGN_RESULT_COMPARISON')
    def __ne__(self, other):
        return not self.__eq__(other)


class _EqualIdentifierSubclass(str):
    pass


@pytest.mark.parametrize('field', [
    'spec_id_foreign', 'spec_id_subclass', 'spec_version_float',
    'spec_version_bool', 'paper_profile', 'paper_final_score',
    'paper_minimum_score', 'paper_maximum_score',
    'question_profile', 'question_final_score', 'question_minimum_score',
    'question_maximum_score', 'question_base_subtotal',
    'question_pre_rounding', 'rubric_id_subclass', 'rubric_version_bool',
    'policy_id_foreign', 'policy_version_float', 'policy_semantics_subclass',
    'criterion_effects_foreign', 'criterion_effect_amount',
    'criterion_effect_id_subclass', 'stage_effects_foreign',
    'stage_amount', 'stage_source_ids_foreign',
    'scoring_projection_foreign', 'scoring_projection_id_foreign',
])
def test_full_owned_s2a_output_contract_rejects_corruption_before_foreign_operations(
        monkeypatch, field):
    import grading.execution as execution
    import traceback
    original = execution.GradingExecutionResult
    _ForeignComparison.calls = 0

    def corrupt(**kwargs):
        result = original(**kwargs)
        paper = result.paper_score
        score = result.questions[0].score
        spec = paper.grading_spec_ref
        rubric = score.rubric_ref
        policy = score.scoring_policy_ref
        if field == 'spec_id_foreign':
            object.__setattr__(spec, 'id', _ForeignComparison())
        elif field == 'spec_id_subclass':
            object.__setattr__(spec, 'id', _EqualIdentifierSubclass(spec.id))
        elif field == 'spec_version_float':
            object.__setattr__(spec, 'version', float(spec.version))
        elif field == 'spec_version_bool':
            object.__setattr__(spec, 'version', True)
        elif field == 'paper_profile':
            object.__setattr__(paper, 'numeric_profile_version', 'INVALID')
        elif field in ('paper_final_score', 'paper_minimum_score', 'paper_maximum_score'):
            object.__setattr__(paper, field.removeprefix('paper_'), object())
        elif field == 'question_profile':
            object.__setattr__(score, 'numeric_profile_version', 'INVALID')
        elif field in ('question_final_score', 'question_minimum_score',
                       'question_maximum_score', 'question_base_subtotal', 'question_pre_rounding'):
            name = field.removeprefix('question_').replace('pre_rounding', 'score_before_rounding')
            object.__setattr__(score, name, object())
        elif field == 'rubric_id_subclass':
            object.__setattr__(rubric, 'id', _EqualIdentifierSubclass(rubric.id))
        elif field == 'rubric_version_bool':
            object.__setattr__(rubric, 'version', True)
        elif field == 'policy_id_foreign':
            object.__setattr__(policy, 'id', _ForeignComparison())
        elif field == 'policy_version_float':
            object.__setattr__(policy, 'version', float(policy.version))
        elif field == 'policy_semantics_subclass':
            object.__setattr__(policy, 'scoring_semantics_version',
                               _EqualIdentifierSubclass(policy.scoring_semantics_version))
        elif field == 'criterion_effects_foreign':
            object.__setattr__(score, 'criterion_effects', (object(),))
        elif field in ('criterion_effect_amount', 'criterion_effect_id_subclass'):
            ce = score.criterion_effects[0]
            if field == 'criterion_effect_amount':
                object.__setattr__(ce, 'effective_contribution', object())
            else:
                object.__setattr__(ce, 'criterion_id', _EqualIdentifierSubclass(ce.criterion_id))
        elif field == 'stage_effects_foreign':
            object.__setattr__(score, 'stage_effects', (object(),))
        elif field == 'stage_amount':
            object.__setattr__(score.stage_effects[0], 'before', object())
        elif field == 'stage_source_ids_foreign':
            object.__setattr__(score.stage_effects[0], 'source_rule_ids', (_ForeignComparison(),))
        elif field == 'scoring_projection_foreign':
            object.__setattr__(result.questions[0].verified, 'scoring_judgments', (object(),))
        elif field == 'scoring_projection_id_foreign':
            judgment = result.questions[0].verified.scoring_judgments[0]
            object.__setattr__(judgment, 'criterion_id', _ForeignComparison())
        return result

    monkeypatch.setattr(execution, 'GradingExecutionResult', corrupt)
    invoker, request, _, attempts = assembled_invoker()
    with _track_choice_and_s2a_calls() as calls:
        try:
            raise RuntimeError('PRIVATE_AMBIENT_ERROR')
        except RuntimeError:
            with pytest.raises(InvocationContractError) as caught:
                invoker.run_one_question(request=request)
    assert calls == {'choice': 1, 's2a': 1}
    assert len(attempts.events) == 1
    assert _ForeignComparison.calls == 0
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert 'PRIVATE' not in ''.join(traceback.format_exception(caught.value))
