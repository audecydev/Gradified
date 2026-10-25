from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

import pytest

from grading.contracts.result import QuestionScoreResult, RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from tests.support.rubric_fixture_builders import (
    assert_invalid_input,
    authority,
    expected_question,
    load_b3,
    paper_fixture,
    policy_ref,
    question_result,
    rubric_ref,
    sd,
    valid_pair,
    weird_b2_provenance,
)


def _forge_exact_question_result(
    base: QuestionScoreResult,
    **overrides,
) -> QuestionScoreResult:
    """Bypass criterion scoring construction to exercise scoring aggregation defensive admission directly."""

    forged = object.__new__(QuestionScoreResult)
    for field in fields(QuestionScoreResult):
        object.__setattr__(
            forged,
            field.name,
            overrides.get(field.name, getattr(base, field.name)),
        )
    return forged


def _forge_exact_ref(ref_type: type, /, **field_values):
    """Forge an exact criterion scoring ref with leaf values its constructor would reject."""

    forged = object.__new__(ref_type)
    for field_name, value in field_values.items():
        object.__setattr__(forged, field_name, value)
    return forged


def test_b3_set_01__submitted_collection_requires_exact_tuple() -> None:
    """B3-SET-01"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(rubric_fixture_builders, (("Q1", "1", "0", "10"),))

    class TupleSubclass(tuple):
        pass

    invalid_collections = (
        list(results),
        {"Q1": results[0]},
        (item for item in results),
        TupleSubclass(results),
    )

    for invalid in invalid_collections:
        with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
            rubric_fixture_builders.aggregate_paper(auth, invalid)


def test_b3_set_02__submitted_items_require_exact_question_result_type() -> None:
    """B3-SET-02"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(rubric_fixture_builders, (("Q1", "1", "0", "10"),))

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (object(),))

    class QuestionScoreResultSubclass(QuestionScoreResult):
        pass

    base = results[0]
    subclass_result = QuestionScoreResultSubclass(
        **{field.name: getattr(base, field.name) for field in fields(QuestionScoreResult)}
    )
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (subclass_result,))


def test_b3_set_03__malformed_submitted_question_id_is_rejected() -> None:
    """B3-SET-03"""
    rubric_fixture_builders = load_b3()
    expected, _ = valid_pair(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    malformed = question_result(
        "",
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (malformed,))

    class StrSubclass(str):
        pass

    exact = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )
    forged = _forge_exact_question_result(exact, question_id=StrSubclass("Q1"))
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (forged,))


def test_b3_set_04__duplicate_submitted_question_ids_are_rejected() -> None:
    """B3-SET-04"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(rubric_fixture_builders, (("Q1", "1", "0", "10"),))

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (results[0], results[0]))


def test_b3_set_05__missing_question_is_rejected_not_zero_filled() -> None:
    """B3-SET-05"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
        paper_maximum="20",
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (results[0],))


def test_b3_set_06__unexpected_question_is_rejected_not_ignored() -> None:
    """B3-SET-06"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(rubric_fixture_builders, (("Q1", "1", "0", "10"),))
    unexpected = question_result("QX", final="2", minimum="0", maximum="10")

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (results[0], unexpected))


def test_b3_set_07__set_mismatch_error_is_deterministic_under_permutation() -> None:
    """B3-SET-07"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
    )
    unexpected = question_result("QX", final="3", minimum="0", maximum="10")

    errors = []
    for supplied in (
        (results[0], unexpected),
        (unexpected, results[0]),
    ):
        with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError) as captured:
            rubric_fixture_builders.aggregate_paper(auth, supplied)
        errors.append(str(captured.value))

    assert errors[0] == errors[1]


def test_b3_id_01__exact_question_rubric_and_policy_identity_is_admitted() -> None:
    """B3-ID-01"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(rubric_fixture_builders, (("Q1", "4", "0", "10"),))
    result = results[0]

    assert type(result) is QuestionScoreResult
    assert type(result.rubric_ref) is RubricRef
    assert type(result.scoring_policy_ref) is ScoringPolicyRef
    assert type(result.final_score) is type(sd("0"))

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("4")


def test_b3_id_02__question_id_mismatch_including_nfc_nfd_is_rejected() -> None:
    """B3-ID-02"""
    rubric_fixture_builders = load_b3()
    nfc = "Q-\u00e9"
    nfd = "Q-e\u0301"
    assert nfc != nfd

    expected, _ = valid_pair(rubric_fixture_builders, nfc)
    result = question_result(
        nfd,
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result,))


def test_b3_id_03__rubric_id_mismatch_is_rejected() -> None:
    """B3-ID-03"""
    rubric_fixture_builders = load_b3()
    expected, valid = valid_pair(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    result = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=RubricRef("other-rubric", expected.rubric_ref.version),
        policy=expected.scoring_policy_ref,
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result,))

    class RubricRefSubclass(RubricRef):
        pass

    smuggled = _forge_exact_question_result(
        valid,
        rubric_ref=RubricRefSubclass(
            expected.rubric_ref.id,
            expected.rubric_ref.version,
        ),
    )
    assert type(smuggled) is QuestionScoreResult
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (smuggled,))


    class StrSubclass(str):
        pass

    for forged_ref in (
        _forge_exact_ref(
            RubricRef,
            id=StrSubclass(expected.rubric_ref.id),
            version=expected.rubric_ref.version,
        ),
        _forge_exact_ref(
            RubricRef,
            id=expected.rubric_ref.id,
            version=True,
        ),
    ):
        # These compare equal by value under Python subclass equality; scoring aggregation must
        # still reject the malformed leaves before identity equality can mask them.
        assert forged_ref == expected.rubric_ref
        forged_result = _forge_exact_question_result(valid, rubric_ref=forged_ref)
        with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
            rubric_fixture_builders.aggregate_paper(auth, (forged_result,))


def test_b3_id_04__rubric_version_mismatch_is_rejected() -> None:
    """B3-ID-04"""
    rubric_fixture_builders = load_b3()
    expected, _ = valid_pair(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    result = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=RubricRef(expected.rubric_ref.id, expected.rubric_ref.version + 1),
        policy=expected.scoring_policy_ref,
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result,))


def test_b3_id_05__policy_id_mismatch_is_rejected() -> None:
    """B3-ID-05"""
    rubric_fixture_builders = load_b3()
    expected, valid = valid_pair(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    result = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=ScoringPolicyRef(
            "other-policy",
            expected.scoring_policy_ref.version,
            expected.scoring_policy_ref.scoring_semantics_version,
        ),
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result,))

    class ScoringPolicyRefSubclass(ScoringPolicyRef):
        pass

    smuggled = _forge_exact_question_result(
        valid,
        scoring_policy_ref=ScoringPolicyRefSubclass(
            expected.scoring_policy_ref.id,
            expected.scoring_policy_ref.version,
            expected.scoring_policy_ref.scoring_semantics_version,
        ),
    )
    assert type(smuggled) is QuestionScoreResult
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (smuggled,))


    class StrSubclass(str):
        pass

    for forged_ref in (
        _forge_exact_ref(
            ScoringPolicyRef,
            id=StrSubclass(expected.scoring_policy_ref.id),
            version=expected.scoring_policy_ref.version,
            scoring_semantics_version=expected.scoring_policy_ref.scoring_semantics_version,
        ),
        _forge_exact_ref(
            ScoringPolicyRef,
            id=expected.scoring_policy_ref.id,
            version=True,
            scoring_semantics_version=expected.scoring_policy_ref.scoring_semantics_version,
        ),
        _forge_exact_ref(
            ScoringPolicyRef,
            id=expected.scoring_policy_ref.id,
            version=expected.scoring_policy_ref.version,
            scoring_semantics_version=StrSubclass(
                expected.scoring_policy_ref.scoring_semantics_version
            ),
        ),
    ):
        assert forged_ref == expected.scoring_policy_ref
        forged_result = _forge_exact_question_result(
            valid,
            scoring_policy_ref=forged_ref,
        )
        with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
            rubric_fixture_builders.aggregate_paper(auth, (forged_result,))


def test_b3_id_06__policy_version_mismatch_is_rejected() -> None:
    """B3-ID-06"""
    rubric_fixture_builders = load_b3()
    expected, _ = valid_pair(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    result = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=ScoringPolicyRef(
            expected.scoring_policy_ref.id,
            expected.scoring_policy_ref.version + 1,
            expected.scoring_policy_ref.scoring_semantics_version,
        ),
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result,))


def test_b3_id_07__policy_semantics_version_mismatch_is_rejected() -> None:
    """B3-ID-07"""
    rubric_fixture_builders = load_b3()
    expected, _ = valid_pair(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    result = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=ScoringPolicyRef(
            expected.scoring_policy_ref.id,
            expected.scoring_policy_ref.version,
            "2",
        ),
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result,))


def test_b3_id_08__same_score_with_stale_identity_is_still_rejected() -> None:
    """B3-ID-08"""
    rubric_fixture_builders = load_b3()
    expected, valid = valid_pair(rubric_fixture_builders, "Q1", final="5")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    stale = question_result(
        "Q1",
        final=valid.final_score,
        minimum=valid.minimum_score,
        maximum=valid.maximum_score,
        rubric=expected.rubric_ref,
        policy=ScoringPolicyRef(
            expected.scoring_policy_ref.id,
            expected.scoring_policy_ref.version + 1,
            expected.scoring_policy_ref.scoring_semantics_version,
        ),
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (stale,))


def test_b3_id_09__caller_order_can_change_without_identity_failure() -> None:
    """B3-ID-09"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (
            ("Q1", "1", "0", "10"),
            ("Q2", "2", "0", "10"),
        ),
        paper_maximum="20",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, tuple(reversed(results)))

    assert tuple(result.question_id for result in paper.question_results) == ("Q1", "Q2")
    assert paper.final_score == sd("3")


def test_b3_profile_02__one_unsupported_result_profile_is_rejected() -> None:
    """B3-PROFILE-02"""
    rubric_fixture_builders = load_b3()
    expected1, result1 = valid_pair(rubric_fixture_builders, "Q1", profile="1")
    expected2, valid_result2 = valid_pair(rubric_fixture_builders, "Q2", profile="1")
    result2 = question_result(
        "Q2",
        final="2",
        minimum="0",
        maximum="10",
        rubric=expected2.rubric_ref,
        policy=expected2.scoring_policy_ref,
        profile="2",
    )
    auth = authority(rubric_fixture_builders, (expected1, expected2), minimum="0", maximum="20")

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (result1, result2))

    class StrSubclass(str):
        pass

    forged_supported_value_wrong_type = _forge_exact_question_result(
        result1,
        numeric_profile_version=StrSubclass("1"),
    )
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        # Keep every other result valid so the exact-string-type violation is
        # the only rejection reason. This isolates the M52 mutation.
        rubric_fixture_builders.aggregate_paper(auth, (forged_supported_value_wrong_type, valid_result2))


def test_b3_profile_03__all_unsupported_result_profiles_are_rejected() -> None:
    """B3-PROFILE-03"""
    rubric_fixture_builders = load_b3()
    expected1, _ = valid_pair(rubric_fixture_builders, "Q1")
    expected2, _ = valid_pair(rubric_fixture_builders, "Q2")
    results = (
        question_result(
            "Q1",
            final="1",
            minimum="0",
            maximum="10",
            rubric=expected1.rubric_ref,
            policy=expected1.scoring_policy_ref,
            profile="2",
        ),
        question_result(
            "Q2",
            final="2",
            minimum="0",
            maximum="10",
            rubric=expected2.rubric_ref,
            policy=expected2.scoring_policy_ref,
            profile="2",
        ),
    )
    auth = authority(rubric_fixture_builders, (expected1, expected2), minimum="0", maximum="20")

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, results)


def test_b3_profile_04__identity_precedes_profile_validation(monkeypatch) -> None:
    """B3-PROFILE-04"""
    rubric_fixture_builders = load_b3()
    expected, _ = valid_pair(rubric_fixture_builders, "Q1")
    mismatched = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=RubricRef("wrong-rubric", 1),
        policy=expected.scoring_policy_ref,
        profile="2",
    )
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")

    original_descriptor = QuestionScoreResult.numeric_profile_version

    class ProfileAccessed(RuntimeError):
        pass

    def _profile_accessed(_self):
        raise ProfileAccessed("profile was accessed before identity rejection")

    monkeypatch.setattr(
        QuestionScoreResult,
        "numeric_profile_version",
        property(_profile_accessed),
    )
    try:
        with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
            rubric_fixture_builders.aggregate_paper(auth, (mismatched,))
    finally:
        monkeypatch.setattr(
            QuestionScoreResult,
            "numeric_profile_version",
            original_descriptor,
        )


def test_b3_profile_05__paper_authority_cannot_select_numeric_profile() -> None:
    """B3-PROFILE-05"""
    rubric_fixture_builders = load_b3()
    expected = (expected_question(rubric_fixture_builders, "Q1"),)

    with pytest.raises(TypeError):
        rubric_fixture_builders.ResolvedPaperScoringAuthority(
            grading_spec_ref=rubric_fixture_builders.GradingSpecRef(id="GS", version=1),
            expected_questions=expected,
            minimum_score=sd("0"),
            maximum_score=sd("10"),
            numeric_profile_version="2",
        )


def test_b3_qres_01__equal_minimum_final_and_maximum_is_admitted() -> None:
    """B3-QRES-01"""
    rubric_fixture_builders = load_b3()
    auth, results = paper_fixture(
        rubric_fixture_builders,
        (("Q1", "3", "3", "3"),),
        paper_minimum="3",
        paper_maximum="3",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, results)

    assert paper.final_score == sd("3")


def test_b3_qres_02__question_minimum_greater_than_maximum_is_rejected() -> None:
    """B3-QRES-02"""
    rubric_fixture_builders = load_b3()
    expected = expected_question(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="-100", maximum="100")
    invalid = question_result(
        "Q1",
        final="0",
        minimum="5",
        maximum="4",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (invalid,))


def test_b3_qres_03__question_final_below_own_minimum_is_rejected() -> None:
    """B3-QRES-03"""
    rubric_fixture_builders = load_b3()
    expected = expected_question(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="-100", maximum="100")
    invalid = question_result(
        "Q1",
        final="2",
        minimum="3",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (invalid,))


def test_b3_qres_04__question_final_above_own_maximum_is_rejected() -> None:
    """B3-QRES-04"""
    rubric_fixture_builders = load_b3()
    expected = expected_question(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="-100", maximum="100")
    invalid = question_result(
        "Q1",
        final="11",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
    )

    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (invalid,))


def test_b3_qres_05__b3_does_not_replay_nonconsumed_b2_provenance() -> None:
    """B3-QRES-05"""
    rubric_fixture_builders = load_b3()
    expected = expected_question(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    effects, decisions, stages = weird_b2_provenance()
    result = question_result(
        "Q1",
        final="4",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
        criterion_effects=effects,
        rule_decisions=decisions,
        stage_effects=stages,
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, (result,))

    assert paper.final_score == sd("4")


def test_b3_qres_06__consumed_field_check_is_not_a_second_b2_proof() -> None:
    """B3-QRES-06"""
    rubric_fixture_builders = load_b3()
    expected = expected_question(rubric_fixture_builders, "Q1")
    auth = authority(rubric_fixture_builders, (expected,), minimum="0", maximum="10")
    result = question_result(
        "Q1",
        final="4",
        minimum="0",
        maximum="10",
        rubric=expected.rubric_ref,
        policy=expected.scoring_policy_ref,
        base_subtotal="999",
        score_before_rounding="-999",
    )

    paper = rubric_fixture_builders.aggregate_paper(auth, (result,))
    assert paper.final_score == sd("4")

    try:
        class ScoringDecimalSubclass(ScoringDecimal):
            pass
    except TypeError:
        ScoringDecimalSubclass = None

    if ScoringDecimalSubclass is not None:
        for field_name in ("minimum_score", "final_score", "maximum_score"):
            original = getattr(result, field_name)
            try:
                smuggled = ScoringDecimalSubclass(original.as_decimal())
            except TypeError:
                continue
            forged = _forge_exact_question_result(result, **{field_name: smuggled})
            assert type(forged) is QuestionScoreResult
            with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
                rubric_fixture_builders.aggregate_paper(auth, (forged,))

    # A required consumed field can be missing on a constructor-bypassed exact
    # result. scoring aggregation must translate that known malformed structure to its input-domain
    # error rather than leak AttributeError.
    missing_final = object.__new__(QuestionScoreResult)
    for field in fields(QuestionScoreResult):
        if field.name != "final_score":
            object.__setattr__(missing_final, field.name, getattr(result, field.name))
    assert type(missing_final) is QuestionScoreResult
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (missing_final,))

    # Exact ScoringDecimal with a finite but noncanonical internal Decimal must be
    # rejected on the consumed-result side as well. Every other field stays valid.
    noncanonical_final = object.__new__(ScoringDecimal)
    object.__setattr__(noncanonical_final, "_value", Decimal("4.0"))
    forged_noncanonical = _forge_exact_question_result(
        result,
        final_score=noncanonical_final,
    )
    with pytest.raises(rubric_fixture_builders.InvalidPaperAggregationInputError):
        rubric_fixture_builders.aggregate_paper(auth, (forged_noncanonical,))
