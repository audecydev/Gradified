from __future__ import annotations

import pytest

from grading.contracts.errors import ScoreOutOfRangeError, ScoringNumericEnvelopeError
from grading.contracts.numeric_profile import MAX_SCORING_CANONICAL_DIGITS
from tests.support.rubric_fixture_builders import (
    authority,
    expected_question,
    load_b3,
    paper_fixture,
    question_result,
    sd,
    valid_pair,
)


def test_b3_num_03__negative_question_contribution_is_preserved() -> None:
    """B3-NUM-03"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (("Q1", "-2", "-5", "10"),),
        paper_minimum="-5",
        paper_maximum="10",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("-2")


def test_b3_num_04__aggregate_exactly_at_paper_minimum_is_accepted() -> None:
    """B3-NUM-04"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "-2", "-5", "10"),
            ("Q2", "1", "-5", "10"),
        ),
        paper_minimum="-1",
        paper_maximum="20",
    )

    assert rubric_fixture_builders.aggregate_paper(auth, results).final_score == sd("-1")


def test_b3_num_05__aggregate_exactly_at_paper_maximum_is_accepted() -> None:
    """B3-NUM-05"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "8", "0", "10"),
            ("Q2", "12", "0", "12"),
        ),
        paper_minimum="0",
        paper_maximum="20",
    )

    assert rubric_fixture_builders.aggregate_paper(auth, results).final_score == sd("20")


def test_b3_num_06__aggregate_below_paper_minimum_is_range_failure() -> None:
    """B3-NUM-06"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (("Q1", "-2", "-5", "10"),),
        paper_minimum="-1",
        paper_maximum="10",
    )

    with pytest.raises(ScoreOutOfRangeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_num_07__aggregate_above_paper_maximum_is_range_failure() -> None:
    """B3-NUM-07"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (("Q1", "11", "0", "20"),),
        paper_minimum="0",
        paper_maximum="10",
    )

    with pytest.raises(ScoreOutOfRangeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_num_08__exact_sum_numeric_envelope_failure_propagates() -> None:
    """B3-NUM-08"""
    rubric_fixture_builders = load_b3()
    huge = sd("9" * MAX_SCORING_CANONICAL_DIGITS)
    tiny = sd("1e-4095")

    expected1, _ = valid_pair(
        rubric_fixture_builders,
        "Q1",
        final=huge,
        minimum="0",
        maximum=huge,
    )
    expected2, _ = valid_pair(
        rubric_fixture_builders,
        "Q2",
        final=tiny,
        minimum="0",
        maximum=tiny,
    )
    results = (
        question_result(
            "Q1",
            final=huge,
            minimum="0",
            maximum=huge,
            rubric=expected1.rubric_ref,
            policy=expected1.scoring_policy_ref,
        ),
        question_result(
            "Q2",
            final=tiny,
            minimum="0",
            maximum=tiny,
            rubric=expected2.rubric_ref,
            policy=expected2.scoring_policy_ref,
        ),
    )
    auth = authority(
        rubric_fixture_builders,
        (expected1, expected2),
        minimum="0",
        maximum=huge,
    )

    with pytest.raises(ScoringNumericEnvelopeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_num_10__paper_total_has_no_second_rounding_stage() -> None:
    """B3-NUM-10"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "0.333", "0", "1"),
            ("Q2", "0.333", "0", "1"),
        ),
        paper_minimum="0",
        paper_maximum="2",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("0.666")


def test_b3_num_11__negative_paper_total_can_succeed_inside_authority_range() -> None:
    """B3-NUM-11"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "-3", "-5", "10"),
            ("Q2", "1", "-5", "10"),
        ),
        paper_minimum="-10",
        paper_maximum="20",
    )

    assert rubric_fixture_builders.aggregate_paper(auth, results).final_score == sd("-2")


def test_b3_num_12__out_of_range_total_is_not_clamped() -> None:
    """B3-NUM-12"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (("Q1", "12", "0", "20"),),
        paper_minimum="0",
        paper_maximum="10",
    )

    with pytest.raises(ScoreOutOfRangeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_bound_01__paper_max_and_question_max_sum_can_coincide() -> None:
    """B3-BOUND-01"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "9", "0", "10"),
            ("Q2", "9", "0", "10"),
        ),
        paper_minimum="0",
        paper_maximum="20",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("18")
    assert paper.maximum_score == sd("20")


def test_b3_bound_02__paper_max_is_not_replaced_by_question_max_sum() -> None:
    """B3-BOUND-02"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "9", "0", "10"),
            ("Q2", "9", "0", "10"),
        ),
        paper_minimum="0",
        paper_maximum="17",
    )

    with pytest.raises(ScoreOutOfRangeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_bound_03__paper_max_need_not_equal_question_max_sum() -> None:
    """B3-BOUND-03"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "8", "0", "9"),
            ("Q2", "8", "0", "8"),
        ),
        paper_minimum="0",
        paper_maximum="20",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("16")
    assert paper.maximum_score == sd("20")
    assert results[0].maximum_score == sd("9")
    assert results[1].maximum_score == sd("8")


def test_b3_bound_04__paper_minimum_is_independent_of_question_minimum_sum() -> None:
    """B3-BOUND-04"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "-2", "-10", "10"),
            ("Q2", "-2", "-10", "10"),
        ),
        paper_minimum="-5",
        paper_maximum="20",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("-4")
    assert paper.minimum_score == sd("-5")


def test_b3_bound_05__deriving_paper_max_from_result_maxima_is_killed() -> None:
    """B3-BOUND-05"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "9", "0", "10"),
            ("Q2", "9", "0", "10"),
        ),
        paper_minimum="0",
        paper_maximum="17",
    )

    with pytest.raises(ScoreOutOfRangeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_bound_06__deriving_paper_min_from_result_minima_is_killed() -> None:
    """B3-BOUND-06"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "-2", "-5", "10"),
            ("Q2", "-2", "-5", "10"),
        ),
        paper_minimum="-3",
        paper_maximum="20",
    )

    with pytest.raises(ScoreOutOfRangeError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_bound_07__b3_success_does_not_reconcile_global_configuration() -> None:
    """B3-BOUND-07"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "8", "0", "9"),
            ("Q2", "8", "0", "8"),
        ),
        paper_minimum="0",
        paper_maximum="50",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("16")
    assert paper.maximum_score == sd("50")
