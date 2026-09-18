from __future__ import annotations

from decimal import localcontext

from hypothesis import given, strategies as st

from grading.scoring.arithmetic import exact_sum
from tests._b3_red_support import (
    context_snapshot,
    fraction_from_sd,
    hostile_context,
    load_b3,
    paper_fixture,
    sd,
)


@given(
    values=st.lists(
        st.integers(min_value=-20, max_value=20),
        min_size=1,
        max_size=6,
    )
)
def test_b3_num_01__aggregate_matches_inherited_b1_exact_sum(values) -> None:
    """B3-NUM-01"""
    b3 = load_b3()
    rows = tuple(
        (f"Q{index}", str(value), "-20", "20")
        for index, value in enumerate(values)
    )
    auth, results = paper_fixture(
        b3,
        rows,
        paper_minimum="-120",
        paper_maximum="120",
    )

    paper = b3.aggregate_paper(auth, results)
    expected = exact_sum(tuple(result.final_score for result in results))

    assert paper.final_score == expected


@given(
    coefficients=st.lists(
        st.integers(min_value=-500, max_value=500),
        min_size=1,
        max_size=6,
    )
)
def test_b3_num_02__aggregate_matches_independent_fraction_oracle(coefficients) -> None:
    """B3-NUM-02"""
    b3 = load_b3()
    rows = tuple(
        (f"Q{index}", f"{coefficient}e-2", "-10", "10")
        for index, coefficient in enumerate(coefficients)
    )
    auth, results = paper_fixture(
        b3,
        rows,
        paper_minimum="-60",
        paper_maximum="60",
    )

    paper = b3.aggregate_paper(auth, results)

    expected_fraction = sum(
        (fraction_from_sd(result.final_score) for result in results),
        start=0,
    )
    assert fraction_from_sd(paper.final_score) == expected_fraction


@given(
    values=st.lists(
        st.integers(min_value=-9, max_value=9),
        min_size=1,
        max_size=5,
    )
)
def test_b3_num_09__hostile_decimal_context_does_not_change_result_or_context(
    values,
) -> None:
    """B3-NUM-09"""
    b3 = load_b3()
    rows = tuple(
        (f"Q{index}", str(value), "-10", "10")
        for index, value in enumerate(values)
    )
    auth, results = paper_fixture(
        b3,
        rows,
        paper_minimum="-50",
        paper_maximum="50",
    )
    expected = exact_sum(tuple(result.final_score for result in results))
    hostile = hostile_context()

    with localcontext(hostile) as context:
        before = context_snapshot(context)
        paper = b3.aggregate_paper(auth, results)
        after = context_snapshot(context)

    assert paper.final_score == expected
    assert after == before


@given(
    values=st.lists(
        st.integers(min_value=-20, max_value=20),
        min_size=1,
        max_size=5,
    ),
    data=st.data(),
)
def test_b3_order_01__caller_permutation_is_numerically_invariant(
    values,
    data,
) -> None:
    """B3-ORDER-01"""
    b3 = load_b3()
    rows = tuple(
        (f"Q{index}", str(value), "-20", "20")
        for index, value in enumerate(values)
    )
    auth, results = paper_fixture(
        b3,
        rows,
        paper_minimum="-100",
        paper_maximum="100",
    )
    permutation = data.draw(st.permutations(tuple(range(len(results)))))
    supplied = tuple(results[index] for index in permutation)

    paper = b3.aggregate_paper(auth, supplied)

    assert paper.final_score == exact_sum(tuple(result.final_score for result in results))
    assert tuple(result.question_id for result in paper.question_results) == tuple(
        f"Q{index}" for index in range(len(results))
    )


@given(
    values=st.lists(
        st.integers(min_value=-10, max_value=10),
        min_size=1,
        max_size=5,
    )
)
def test_b3_profile_01__supported_profile_one_is_admitted(values) -> None:
    """B3-PROFILE-01"""
    b3 = load_b3()
    rows = tuple(
        (f"Q{index}", str(value), "-10", "10")
        for index, value in enumerate(values)
    )
    auth, results = paper_fixture(
        b3,
        rows,
        paper_minimum="-50",
        paper_maximum="50",
    )

    paper = b3.aggregate_paper(auth, results)

    assert paper.numeric_profile_version == "1"
    assert all(result.numeric_profile_version == "1" for result in results)


@given(
    spec_version=st.integers(min_value=1, max_value=1000),
    spec_suffix=st.integers(min_value=1, max_value=1000),
)
def test_b3_prov_01__grading_spec_ref_is_preserved_by_value(
    spec_version,
    spec_suffix,
) -> None:
    """B3-PROV-01"""
    b3 = load_b3()
    spec_id = f"GS-{spec_suffix}"
    auth, results = paper_fixture(
        b3,
        (("Q1", "1", "0", "10"),),
        paper_minimum="0",
        paper_maximum="10",
        spec_id=spec_id,
        spec_version=spec_version,
    )

    paper = b3.aggregate_paper(auth, results)

    assert paper.grading_spec_ref == auth.grading_spec_ref
    assert paper.grading_spec_ref.id == spec_id
    assert paper.grading_spec_ref.version == spec_version
