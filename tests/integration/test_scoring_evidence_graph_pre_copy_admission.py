"""Direct public constructor denial precedes hostile user copy callbacks."""
from dataclasses import replace
import pytest
from grading.integration.result_constituents import CandidateConstituentsDenied
from test_scoring_evidence_graph_detached_custody import candidate


def test_foreign_outer_record_copy_hook_not_invoked():
    c, _, _ = candidate()
    touched = []
    class Foreign:
        def __deepcopy__(self, memo):
            touched.append('side effect')
            raise RuntimeError('PRIVATE_CODE')
    with pytest.raises(CandidateConstituentsDenied) as ex:
        replace(c, paper_score=Foreign())
    assert touched == []
    assert ex.value.__cause__ is None and ex.value.__context__ is None


def test_nested_copy_hook_not_invoked_or_mutate_original():
    c, ex, _ = candidate()
    touched = []
    class Foreign:
        def __deepcopy__(self, memo):
            touched.append('mutated original')
            object.__setattr__(ex.paper_score, 'final_score', 'PRIVATE_SENTINEL')
            raise RuntimeError('PRIVATE_CODE')
    object.__setattr__(c.paper_score.question_results[0].criterion_effects[0],
                       'blocking_dependency_rule_ids', (Foreign(),))
    with pytest.raises(CandidateConstituentsDenied) as err:
        replace(c)
    assert touched == []
    assert ex.paper_score.final_score != 'PRIVATE_SENTINEL'
    assert err.value.__cause__ is None and err.value.__context__ is None


def test_excessive_graph_refused_without_copy():
    c, _, _ = candidate()
    too_large = tuple('X' for _ in range(10_001))
    with pytest.raises(CandidateConstituentsDenied):
        replace(c, question_scores=too_large)
    deep = 'X'
    for _ in range(72):
        deep = (deep,)
    from grading.integration.result_constituents import _preflight_owned_graph
    with pytest.raises(CandidateConstituentsDenied):
        _preflight_owned_graph(deep)


def test_detaches_admitted_source_without_privilege_escalation():
    c, _, _ = candidate()
    copy = replace(c)
    assert copy.paper_score is not c.paper_score
    assert copy.review_recommendation is not c.review_recommendation
    assert copy.validated_snapshot().official_result is False
