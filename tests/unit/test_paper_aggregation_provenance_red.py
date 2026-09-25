from __future__ import annotations

from contextlib import contextmanager
from importlib import reload
import os
import random
import time

import pytest

from grading.contracts.errors import ScoreOutOfRangeError, ScoringNumericEnvelopeError
from grading.contracts.numeric_profile import MAX_SCORING_CANONICAL_DIGITS
from grading.contracts.result import QuestionScoreResult, RubricRef
import grading.scoring.arithmetic as arithmetic_module
from tests.support.b3 import (
    authority,
    expected_question,
    grading_spec_ref,
    load_b3,
    paper_fixture,
    question_result,
    sd,
    valid_pair,
)


def _constructor_spy(monkeypatch, b3, *, failure: BaseException | None = None):
    counter = {"calls": 0}
    real_constructor = b3.PaperScoreResult

    def _construct(*args, **kwargs):
        counter["calls"] += 1
        if failure is not None:
            raise failure
        return real_constructor(*args, **kwargs)

    # Spy on the constructor binding used by aggregate_paper rather than
    # monkeypatching __new__. Mutating an inherited object.__new__ changes
    # CPython's type-level allocation slot and is not safely reversible by
    # deleting the temporary class attribute.
    monkeypatch.setattr(b3.paper_module, "PaperScoreResult", _construct)
    return counter


@contextmanager
def _paper_module_with_exact_sum_bomb(b3, exception: BaseException):
    original = arithmetic_module.exact_sum

    def _boom(_values):
        raise exception

    arithmetic_module.exact_sum = _boom
    reloaded = reload(b3.paper_module)
    try:
        yield reloaded
    finally:
        arithmetic_module.exact_sum = original
        reload(b3.paper_module)


def test_b3_order_02__caller_permutation_has_same_canonical_result_order() -> None:
    """B3-ORDER-02"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
            ("Q3", "3", "0", "10"),
        ),
        paper_maximum="30",
    )

    forward = b3.aggregate_paper(auth, results)
    reverse = b3.aggregate_paper(auth, tuple(reversed(results)))

    assert forward.final_score == reverse.final_score
    assert forward.question_results == reverse.question_results
    assert tuple(r.question_id for r in reverse.question_results) == ("Q1", "Q2", "Q3")


def test_b3_order_03__authority_order_is_not_lexicographically_sorted() -> None:
    """B3-ORDER-03"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q10", "2", "0", "10"),
            ("Q2", "3", "0", "10"),
        ),
        paper_maximum="30",
    )

    paper = b3.aggregate_paper(auth, (results[2], results[0], results[1]))

    assert tuple(r.question_id for r in paper.question_results) == ("Q1", "Q10", "Q2")


def test_b3_order_04__canonicalization_does_not_rebuild_or_mutate_b2_evidence() -> None:
    """B3-ORDER-04"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )
    snapshots = tuple(
        (
            r.question_id,
            r.rubric_ref,
            r.scoring_policy_ref,
            r.numeric_profile_version,
            r.criterion_effects,
            r.rule_decisions,
            r.stage_effects,
            r.base_subtotal,
            r.score_before_rounding,
            r.final_score,
            r.minimum_score,
            r.maximum_score,
        )
        for r in results
    )

    paper = b3.aggregate_paper(auth, tuple(reversed(results)))

    after = tuple(
        (
            r.question_id,
            r.rubric_ref,
            r.scoring_policy_ref,
            r.numeric_profile_version,
            r.criterion_effects,
            r.rule_decisions,
            r.stage_effects,
            r.base_subtotal,
            r.score_before_rounding,
            r.final_score,
            r.minimum_score,
            r.maximum_score,
        )
        for r in results
    )
    assert after == snapshots
    assert tuple(r.question_id for r in paper.question_results) == ("Q1", "Q2")


def test_b3_order_05__canonical_tuple_reuses_same_in_process_question_result_instances() -> None:
    """B3-ORDER-05"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )

    paper = b3.aggregate_paper(auth, tuple(reversed(results)))

    assert paper.question_results[0] is results[0]
    assert paper.question_results[1] is results[1]


def test_b3_order_06__authority_order_changes_provenance_not_numeric_weight() -> None:
    """B3-ORDER-06"""
    b3 = load_b3()
    first, result1 = valid_pair(b3, "Q1", final="1")
    second, result2 = valid_pair(b3, "Q2", final="2")
    auth_forward = authority(b3, (first, second), minimum="0", maximum="20")
    auth_reverse = authority(b3, (second, first), minimum="0", maximum="20")
    supplied = (result1, result2)

    forward = b3.aggregate_paper(auth_forward, supplied)
    reverse = b3.aggregate_paper(auth_reverse, supplied)

    assert forward.final_score == reverse.final_score == sd("3")
    assert tuple(r.question_id for r in forward.question_results) == ("Q1", "Q2")
    assert tuple(r.question_id for r in reverse.question_results) == ("Q2", "Q1")


def test_b3_fail_01__invalid_last_expected_question_constructs_no_result(monkeypatch) -> None:
    """B3-FAIL-01"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )
    invalid_last = question_result(
        "Q2",
        final="2",
        minimum="0",
        maximum="10",
        rubric=RubricRef("wrong-rubric", 1),
        policy=results[1].scoring_policy_ref,
    )
    counter = _constructor_spy(monkeypatch, b3)

    with pytest.raises(b3.InvalidPaperAggregationInputError):
        b3.aggregate_paper(auth, (results[0], invalid_last))

    assert counter["calls"] == 0


def test_b3_fail_02__set_mismatch_occurs_before_aggregation_or_result_construction(
    monkeypatch,
) -> None:
    """B3-FAIL-02"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )
    counter = _constructor_spy(monkeypatch, b3)

    class SumReached(RuntimeError):
        pass

    sentinel = SumReached("exact_sum should not be reached")
    with _paper_module_with_exact_sum_bomb(b3, sentinel) as paper_module:
        with pytest.raises(b3.InvalidPaperAggregationInputError):
            paper_module.aggregate_paper(auth, (results[0],))

    assert counter["calls"] == 0


def test_b3_fail_03__identity_mismatch_occurs_before_aggregation_or_result_construction(
    monkeypatch,
) -> None:
    """B3-FAIL-03"""
    b3 = load_b3()
    expected, _ = valid_pair(b3, "Q1")
    auth = authority(b3, (expected,), minimum="0", maximum="10")
    invalid = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=RubricRef("wrong-rubric", 1),
        policy=expected.scoring_policy_ref,
    )
    counter = _constructor_spy(monkeypatch, b3)

    class SumReached(RuntimeError):
        pass

    sentinel = SumReached("exact_sum should not be reached")
    with _paper_module_with_exact_sum_bomb(b3, sentinel) as paper_module:
        with pytest.raises(b3.InvalidPaperAggregationInputError):
            paper_module.aggregate_paper(auth, (invalid,))

    assert counter["calls"] == 0


def test_b3_fail_04__profile_mismatch_constructs_no_result(monkeypatch) -> None:
    """B3-FAIL-04"""
    b3 = load_b3()
    expected, _ = valid_pair(b3, "Q1")
    auth = authority(b3, (expected,), minimum="0", maximum="10")
    invalid = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
        profile="2",
    )
    counter = _constructor_spy(monkeypatch, b3)

    with pytest.raises(b3.InvalidPaperAggregationInputError):
        b3.aggregate_paper(auth, (invalid,))

    assert counter["calls"] == 0


def test_b3_fail_05__question_self_range_failure_constructs_no_result(monkeypatch) -> None:
    """B3-FAIL-05"""
    b3 = load_b3()
    expected, _ = valid_pair(b3, "Q1")
    auth = authority(b3, (expected,), minimum="-100", maximum="100")
    invalid = question_result(
        "Q1",
        final="11",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )
    counter = _constructor_spy(monkeypatch, b3)

    with pytest.raises(b3.InvalidPaperAggregationInputError):
        b3.aggregate_paper(auth, (invalid,))

    assert counter["calls"] == 0


def test_b3_fail_06__numeric_envelope_failure_constructs_no_result(monkeypatch) -> None:
    """B3-FAIL-06"""
    b3 = load_b3()
    huge_text = "9" * MAX_SCORING_CANONICAL_DIGITS
    huge = sd(huge_text)
    tiny = sd("1e-4095")
    first, _ = valid_pair(b3, "Q1", final=huge, maximum=huge)
    second, _ = valid_pair(b3, "Q2", final=tiny, maximum=tiny)
    results = (
        question_result(
            "Q1",
            final=huge,
            minimum="0",
            maximum=huge,
            rubric=first.rubric_ref,
            policy=first.scoring_policy_ref,
        ),
        question_result(
            "Q2",
            final=tiny,
            minimum="0",
            maximum=tiny,
            rubric=second.rubric_ref,
            policy=second.scoring_policy_ref,
        ),
    )
    auth = authority(b3, (first, second), minimum="0", maximum=huge)
    counter = _constructor_spy(monkeypatch, b3)

    with pytest.raises(ScoringNumericEnvelopeError):
        b3.aggregate_paper(auth, results)

    assert counter["calls"] == 0


def test_b3_fail_07__paper_range_failure_after_sum_constructs_no_result(monkeypatch) -> None:
    """B3-FAIL-07"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (("Q1", "11", "0", "20"),),
        paper_minimum="0",
        paper_maximum="10",
    )
    counter = _constructor_spy(monkeypatch, b3)

    with pytest.raises(ScoreOutOfRangeError):
        b3.aggregate_paper(auth, results)

    assert counter["calls"] == 0


def test_b3_fail_08__unexpected_exact_primitive_exception_propagates_unchanged() -> None:
    """B3-FAIL-08"""
    b3 = load_b3()
    auth, results = paper_fixture(b3, (("Q1", "1", "0", "10"),))

    class ExactPrimitiveBoom(RuntimeError):
        pass

    sentinel = ExactPrimitiveBoom("sentinel")
    with _paper_module_with_exact_sum_bomb(b3, sentinel) as paper_module:
        with pytest.raises(ExactPrimitiveBoom) as captured:
            paper_module.aggregate_paper(auth, results)

    assert captured.value is sentinel


def test_b3_fail_09__multi_fault_precedence_is_stable_under_caller_permutation() -> None:
    """B3-FAIL-09"""
    b3 = load_b3()
    first, _ = valid_pair(b3, "Q1")
    second, _ = valid_pair(b3, "Q2")
    auth = authority(b3, (first, second), minimum="0", maximum="20")
    wrong_identity_and_profile = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=RubricRef("wrong-rubric", 1),
        policy=first.scoring_policy_ref,
        profile="2",
    )
    unexpected = question_result("QX", final="1", minimum="0", maximum="10", profile="2")

    messages = []
    for supplied in (
        (wrong_identity_and_profile, unexpected),
        (unexpected, wrong_identity_and_profile),
    ):
        with pytest.raises(b3.InvalidPaperAggregationInputError) as captured:
            b3.aggregate_paper(auth, supplied)
        messages.append(str(captured.value))

    assert messages[0] == messages[1]


def test_b3_fail_10__successful_aggregation_constructs_exactly_one_result(monkeypatch) -> None:
    """B3-FAIL-10"""
    b3 = load_b3()
    auth, results = paper_fixture(b3, (("Q1", "1", "0", "10"),))
    counter = _constructor_spy(monkeypatch, b3)

    paper = b3.aggregate_paper(auth, results)

    assert paper.final_score == sd("1")
    assert counter["calls"] == 1


def test_b3_fail_11__constructor_failure_propagates_without_fallback(monkeypatch) -> None:
    """B3-FAIL-11"""
    b3 = load_b3()
    auth, results = paper_fixture(b3, (("Q1", "1", "0", "10"),))

    class ConstructorBoom(RuntimeError):
        pass

    sentinel = ConstructorBoom("constructor sentinel")
    counter = _constructor_spy(monkeypatch, b3, failure=sentinel)

    with pytest.raises(ConstructorBoom) as captured:
        b3.aggregate_paper(auth, results)

    assert captured.value is sentinel
    assert counter["calls"] == 1


def test_b3_pure_04__external_mutable_container_cannot_alias_paper_result() -> None:
    """B3-PURE-04"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )
    external = list(results)

    paper = b3.aggregate_paper(auth, tuple(external))
    external.reverse()
    external.clear()

    assert tuple(r.question_id for r in paper.question_results) == ("Q1", "Q2")
    assert paper.final_score == sd("3")


def test_b3_pure_05__environment_time_and_random_state_do_not_change_score(
    monkeypatch,
) -> None:
    """B3-PURE-05"""
    b3 = load_b3()
    auth, results = paper_fixture(b3, (("Q1", "3", "0", "10"),))

    monkeypatch.setenv("GRADIFIED_B3_RED_SENTINEL", "A")
    monkeypatch.setattr(time, "time", lambda: 111.0)
    monkeypatch.setattr(random, "random", lambda: 0.1)
    first = b3.aggregate_paper(auth, results)

    monkeypatch.setenv("GRADIFIED_B3_RED_SENTINEL", "B")
    monkeypatch.setattr(time, "time", lambda: 999999.0)
    monkeypatch.setattr(random, "random", lambda: 0.9)
    second = b3.aggregate_paper(auth, results)

    assert first.final_score == second.final_score == sd("3")
    assert first.question_results == second.question_results


def test_b3_pure_06__authority_origin_is_not_authenticated_by_b3() -> None:
    """B3-PURE-06"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (("Q1", "2", "0", "10"),),
        spec_id="NO-DATABASE-RECORD-IS-REQUIRED",
    )

    paper = b3.aggregate_paper(auth, results)

    assert paper.final_score == sd("2")


def test_b3_prov_02__paper_result_reports_numeric_profile_v1() -> None:
    """B3-PROV-02"""
    b3 = load_b3()
    auth, results = paper_fixture(b3, (("Q1", "1", "0", "10"),))

    paper = b3.aggregate_paper(auth, results)

    assert paper.numeric_profile_version == "1"


def test_b3_prov_03__paper_result_question_provenance_uses_authority_order() -> None:
    """B3-PROV-03"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )

    paper = b3.aggregate_paper(auth, tuple(reversed(results)))

    assert tuple(r.question_id for r in paper.question_results) == ("Q1", "Q2")


def test_b3_prov_04__paper_result_preserves_admitted_authority_bounds() -> None:
    """B3-PROV-04"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (("Q1", "1", "-5", "10"),),
        paper_minimum="-7",
        paper_maximum="13",
    )

    paper = b3.aggregate_paper(auth, results)

    assert paper.minimum_score == auth.minimum_score == sd("-7")
    assert paper.maximum_score == auth.maximum_score == sd("13")


def test_b3_prov_06__unrelated_grading_spec_ref_cannot_replace_authority_ref() -> None:
    """B3-PROV-06"""
    b3 = load_b3()
    auth, results = paper_fixture(
        b3,
        (("Q1", "1", "0", "10"),),
        spec_id="GS-A",
        spec_version=3,
    )
    unrelated = grading_spec_ref(b3, spec_id="GS-B", version=1)

    paper = b3.aggregate_paper(auth, results)

    assert paper.grading_spec_ref == auth.grading_spec_ref
    assert paper.grading_spec_ref != unrelated
