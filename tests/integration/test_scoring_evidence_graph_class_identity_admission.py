"""Verify foreign metaclass callbacks are rejected during evidence admission.

These tests enforce precise class-admission rules, not a general Python sandbox."""
from dataclasses import replace

import pytest

from grading.integration.result_constituents import (
    CandidateConstituentsDenied, CandidateResultConstituents,
    _preflight_owned_graph,
)
from test_result_constituents_provenance import example


def _good_candidate():
    execution, evidence, query, recommender, _ = example(unknown_ocr=True)
    from grading.integration.result_constituents import compose_nonpublishing_constituents
    return compose_nonpublishing_constituents(
        execution=execution, evidence=evidence, policy_query=query,
        recommender=recommender,
    )


@pytest.mark.parametrize('field', ('__module__', '__name__'))
def test_metaclass_data_descriptors_do_not_run_during_public_denial(field):
    original = _good_candidate()
    calls = []

    class HostileDescriptor:
        def __get__(self, instance, owner):
            calls.append('descriptor-called')
            raise RuntimeError('PRIVATE_EXTERNAL_IDENTIFIER')

    # Define the descriptor in the metaclass namespace at creation; assignment
    # to `type.__name__` after creation is intentionally type-restricted.
    HostileMeta = type('HostileMeta', (type,), {field: HostileDescriptor()})

    class Foreign(metaclass=HostileMeta):
        def __deepcopy__(self, memo):
            calls.append('copied')
            raise RuntimeError('PRIVATE_COPY_IDENTIFIER')

    with pytest.raises(CandidateConstituentsDenied) as denied:
        replace(original, question_scores=(Foreign(),))
    assert calls == []
    assert denied.value.__context__ is None
    assert denied.value.__cause__ is None
    assert 'PRIVATE_' not in str(denied.value)


def test_foreign_metaclass_equality_not_evaluated_even_for_primitive_branch():
    original = _good_candidate()
    calls = []

    class HostileMeta(type):
        def __eq__(cls, other):
            calls.append('equal-class')
            return False

    class Foreign(metaclass=HostileMeta):
        pass

    with pytest.raises(CandidateConstituentsDenied):
        replace(original, question_scores=(Foreign(),))
    assert calls == []


def test_foreign_metadata_names_cannot_impersonate_approved_record():
    original = _good_candidate()
    calls = []

    class HostileMeta(type):
        def __getattribute__(cls, field):
            if field in ('__module__', '__name__', '__dataclass_fields__'):
                calls.append(field)
            return super().__getattribute__(field)

    class Foreign(metaclass=HostileMeta):
        __module__ = 'grading.contracts.result'
        __name__ = 'QuestionScoreResult'

    with pytest.raises(CandidateConstituentsDenied):
        replace(original, question_scores=(Foreign(),))
    assert calls == []


def test_foreign_nested_class_denied_before_copy_and_without_mutating_source():
    original = _good_candidate()
    calls = []

    class HostileMeta(type):
        @property
        def __name__(cls):
            calls.append('metadata')
            return 'CriterionEffect'

    class Foreign(metaclass=HostileMeta):
        def __deepcopy__(self, memo):
            calls.append('copied')
            raise RuntimeError('private')

    object.__setattr__(original.paper_score.question_results[0].criterion_effects[0],
                       'blocking_dependency_rule_ids', (Foreign(),))
    with pytest.raises(CandidateConstituentsDenied):
        original.validated_snapshot()
    assert calls == []


def test_legitimate_graph_detaches_and_retains_nonofficial_state():
    original = _good_candidate()
    snapshot = original.validated_snapshot()
    assert type(snapshot) is CandidateResultConstituents
    assert snapshot is not original
    assert snapshot.paper_score is not original.paper_score
    assert snapshot.paper_score == original.paper_score
    assert snapshot.official_result is False


def test_original_reviewer_metaclass_descriptor_reproductions_pass():
    # Simple positive case for the exact foreign-type boundary, without
    # relying on a particular test-module namespace.
    original = _good_candidate()
    callbacks = []

    class Meta(type):
        @property
        def __module__(cls):
            callbacks.append('module')
            return 'grading.contracts.result'

    class Foreign(metaclass=Meta):
        pass

    with pytest.raises(CandidateConstituentsDenied):
        replace(original, paper_score=Foreign())
    assert not callbacks


def test_direct_preflight_rejects_foreign_class_without_metadata_reads():
    callbacks = []

    class Meta(type):
        @property
        def __module__(cls):
            callbacks.append('module')
            return 'grading.fake'

    class Foreign(metaclass=Meta):
        pass

    with pytest.raises(CandidateConstituentsDenied):
        _preflight_owned_graph((Foreign(),))
    assert not callbacks
