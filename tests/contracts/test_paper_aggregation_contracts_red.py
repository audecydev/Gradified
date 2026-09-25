from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal

import pytest

from grading.contracts.errors import InvalidScoringAuthorityError
from grading.contracts.result import QuestionScoreResult, RubricRef, ScoringPolicyRef
from grading.contracts.scoring_decimal import ScoringDecimal
from tests.support.b3 import (
    authority,
    authority_field_names,
    expected_question,
    load_b3,
    paper_fixture,
    question_result,
    result_field_names,
    sd,
)


def _construct_subclass(base_type: type, name: str) -> type | None:
    """Return a constructible subclass type when Python permits one."""

    try:
        return type(name, (base_type,), {})
    except TypeError:
        return None


def _instantiate_or_none(subclass_type: type | None, /, *args, **kwargs):
    """Create a subclass attack object when Python permits the subclass type.

    A B3 constructor may itself reject the subclass with the authority-domain
    error. In that case, forge only the dataclass field state so the reducer
    boundary is still tested independently of constructor provenance.
    """

    if subclass_type is None:
        return None
    try:
        return subclass_type(*args, **kwargs)
    except TypeError:
        return None
    except InvalidScoringAuthorityError:
        field_defs = fields(subclass_type)
        if len(args) > len(field_defs):
            return None

        field_values = {field.name: value for field, value in zip(field_defs, args)}
        field_values.update(kwargs)
        if any(field.name not in field_values for field in field_defs):
            return None

        forged = object.__new__(subclass_type)
        for field in field_defs:
            object.__setattr__(forged, field.name, field_values[field.name])
        return forged


def _forge_exact(instance_type: type, /, **field_values):
    """Bypass construction to exercise defensive re-admission of exact classes."""

    forged = object.__new__(instance_type)
    for field_name, value in field_values.items():
        object.__setattr__(forged, field_name, value)
    return forged


def test_b3_auth_01__authority_exact_type_is_required() -> None:
    """B3-AUTH-01"""
    b3 = load_b3()
    exact_authority, results = paper_fixture(
        b3,
        (("Q1", "1", "0", "10"),),
        paper_minimum="0",
        paper_maximum="10",
    )

    assert type(exact_authority) is b3.ResolvedPaperScoringAuthority
    assert b3.aggregate_paper(exact_authority, results).final_score == sd("1")

    with pytest.raises(InvalidScoringAuthorityError):
        b3.aggregate_paper(object(), ())

    authority_subclass = _construct_subclass(
        b3.ResolvedPaperScoringAuthority,
        "ResolvedPaperScoringAuthoritySubclass",
    )
    subclass_authority = _instantiate_or_none(
        authority_subclass,
        grading_spec_ref=exact_authority.grading_spec_ref,
        expected_questions=exact_authority.expected_questions,
        minimum_score=exact_authority.minimum_score,
        maximum_score=exact_authority.maximum_score,
    )
    if subclass_authority is not None:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.aggregate_paper(subclass_authority, results)


def test_b3_auth_02__grading_spec_ref_rejects_malformed_id_and_version() -> None:
    """B3-AUTH-02"""
    b3 = load_b3()
    exact_spec = b3.GradingSpecRef(id="GS", version=1)
    expected = expected_question(b3, "Q1")

    assert type(exact_spec) is b3.GradingSpecRef

    class StrSubclass(str):
        pass

    for kwargs in (
        {"id": "", "version": 1},
        {"id": " surrounded ", "version": 1},
        {"id": StrSubclass("GS"), "version": 1},
        {"id": "GS", "version": 0},
        {"id": "GS", "version": True},
    ):
        with pytest.raises(InvalidScoringAuthorityError):
            b3.GradingSpecRef(**kwargs)

    grading_spec_subclass = _construct_subclass(
        b3.GradingSpecRef,
        "GradingSpecRefSubclass",
    )
    smuggled_spec = _instantiate_or_none(
        grading_spec_subclass,
        id="GS",
        version=1,
    )
    if smuggled_spec is not None:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ResolvedPaperScoringAuthority(
                grading_spec_ref=smuggled_spec,
                expected_questions=(expected,),
                minimum_score=sd("0"),
                maximum_score=sd("10"),
            )


def test_b3_auth_03__expected_questions_requires_exact_tuple_and_exact_items() -> None:
    """B3-AUTH-03"""
    b3 = load_b3()
    expected = expected_question(b3, "Q1")
    spec = b3.GradingSpecRef(id="GS", version=1)

    assert type(expected) is b3.ExpectedQuestionResult
    exact_authority = b3.ResolvedPaperScoringAuthority(
        grading_spec_ref=spec,
        expected_questions=(expected,),
        minimum_score=sd("0"),
        maximum_score=sd("10"),
    )
    assert type(exact_authority.expected_questions[0]) is b3.ExpectedQuestionResult

    class TupleSubclass(tuple):
        pass

    expected_subclass = _construct_subclass(
        b3.ExpectedQuestionResult,
        "ExpectedQuestionResultSubclass",
    )
    subclass_expected = _instantiate_or_none(
        expected_subclass,
        question_id=expected.question_id,
        rubric_ref=expected.rubric_ref,
        scoring_policy_ref=expected.scoring_policy_ref,
    )

    invalid_questions_cases = [
        [expected],
        TupleSubclass((expected,)),
        (object(),),
    ]
    if subclass_expected is not None:
        invalid_questions_cases.append((subclass_expected,))

    for invalid_questions in invalid_questions_cases:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ResolvedPaperScoringAuthority(
                grading_spec_ref=spec,
                expected_questions=invalid_questions,
                minimum_score=sd("0"),
                maximum_score=sd("10"),
            )


def test_b3_auth_04__empty_resolved_composition_is_rejected() -> None:
    """B3-AUTH-04"""
    b3 = load_b3()

    with pytest.raises(InvalidScoringAuthorityError):
        authority(b3, (), minimum="0", maximum="0")


def test_b3_auth_05__duplicate_expected_question_ids_are_rejected() -> None:
    """B3-AUTH-05"""
    b3 = load_b3()
    first = expected_question(b3, "Q1")
    second = expected_question(b3, "Q1")

    with pytest.raises(InvalidScoringAuthorityError):
        authority(b3, (first, second))


def test_b3_auth_06__malformed_expected_identity_refs_are_rejected() -> None:
    """B3-AUTH-06"""
    b3 = load_b3()
    exact_rubric = RubricRef("rubric", 1)
    exact_policy = ScoringPolicyRef("policy", 1, "1")
    exact_expected = b3.ExpectedQuestionResult(
        question_id="Q1",
        rubric_ref=exact_rubric,
        scoring_policy_ref=exact_policy,
    )

    assert type(exact_expected.rubric_ref) is RubricRef
    assert type(exact_expected.scoring_policy_ref) is ScoringPolicyRef

    class StrSubclass(str):
        pass

    invalid_cases = (
        ("", exact_rubric, exact_policy),
        (" Q1 ", exact_rubric, exact_policy),
        (StrSubclass("Q1"), exact_rubric, exact_policy),
        ("Q1", RubricRef("", 1), exact_policy),
        ("Q1", RubricRef("rubric", 0), exact_policy),
        ("Q1", exact_rubric, ScoringPolicyRef("", 1, "1")),
        ("Q1", exact_rubric, ScoringPolicyRef("policy", 0, "1")),
    )

    for question_id, malformed_rubric, malformed_policy in invalid_cases:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ExpectedQuestionResult(
                question_id=question_id,
                rubric_ref=malformed_rubric,
                scoring_policy_ref=malformed_policy,
            )

    rubric_subclass = _construct_subclass(RubricRef, "RubricRefSubclass")
    smuggled_rubric = _instantiate_or_none(rubric_subclass, "rubric", 1)
    if smuggled_rubric is not None:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=smuggled_rubric,
                scoring_policy_ref=exact_policy,
            )

    policy_subclass = _construct_subclass(
        ScoringPolicyRef,
        "ScoringPolicyRefSubclass",
    )
    smuggled_policy = _instantiate_or_none(
        policy_subclass,
        "policy",
        1,
        "1",
    )
    if smuggled_policy is not None:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=exact_rubric,
                scoring_policy_ref=smuggled_policy,
            )


    # Exact outer B2 ref classes can still be forged with invalid leaf runtime
    # types. These values compare equal in Python (e.g. True == 1), so B3 must
    # structurally re-admit the leaves rather than trusting dataclass equality.
    forged_rubric_id = _forge_exact(
        RubricRef,
        id=StrSubclass("rubric"),
        version=1,
    )
    forged_rubric_version = _forge_exact(
        RubricRef,
        id="rubric",
        version=True,
    )
    forged_policy_id = _forge_exact(
        ScoringPolicyRef,
        id=StrSubclass("policy"),
        version=1,
        scoring_semantics_version="1",
    )
    forged_policy_version = _forge_exact(
        ScoringPolicyRef,
        id="policy",
        version=True,
        scoring_semantics_version="1",
    )
    forged_policy_semantics = _forge_exact(
        ScoringPolicyRef,
        id="policy",
        version=1,
        scoring_semantics_version=StrSubclass("1"),
    )

    for forged_rubric in (forged_rubric_id, forged_rubric_version):
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=forged_rubric,
                scoring_policy_ref=exact_policy,
            )

    for forged_policy in (
        forged_policy_id,
        forged_policy_version,
        forged_policy_semantics,
    ):
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ExpectedQuestionResult(
                question_id="Q1",
                rubric_ref=exact_rubric,
                scoring_policy_ref=forged_policy,
            )


def test_b3_auth_07__unsupported_expected_scoring_semantics_is_rejected() -> None:
    """B3-AUTH-07"""
    b3 = load_b3()

    with pytest.raises(InvalidScoringAuthorityError):
        b3.ExpectedQuestionResult(
            question_id="Q1",
            rubric_ref=RubricRef("rubric", 1),
            scoring_policy_ref=ScoringPolicyRef("policy", 1, "2"),
        )


def test_b3_auth_08__paper_bounds_require_exact_scoring_decimal() -> None:
    """B3-AUTH-08"""
    b3 = load_b3()
    expected = (expected_question(b3, "Q1"),)
    spec = b3.GradingSpecRef(id="GS", version=1)
    exact_minimum = sd("0")
    exact_maximum = sd("10")

    exact_authority = b3.ResolvedPaperScoringAuthority(
        grading_spec_ref=spec,
        expected_questions=expected,
        minimum_score=exact_minimum,
        maximum_score=exact_maximum,
    )
    assert type(exact_authority.minimum_score) is ScoringDecimal
    assert type(exact_authority.maximum_score) is ScoringDecimal

    with pytest.raises(InvalidScoringAuthorityError):
        b3.ResolvedPaperScoringAuthority(
            grading_spec_ref=spec,
            expected_questions=expected,
            minimum_score=0,
            maximum_score=exact_maximum,
        )

    scoring_decimal_subclass = _construct_subclass(
        ScoringDecimal,
        "ScoringDecimalSubclass",
    )
    smuggled_minimum = _instantiate_or_none(
        scoring_decimal_subclass,
        exact_minimum.as_decimal(),
    )
    smuggled_maximum = _instantiate_or_none(
        scoring_decimal_subclass,
        exact_maximum.as_decimal(),
    )
    if smuggled_minimum is not None:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ResolvedPaperScoringAuthority(
                grading_spec_ref=spec,
                expected_questions=expected,
                minimum_score=smuggled_minimum,
                maximum_score=exact_maximum,
            )
    if smuggled_maximum is not None:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.ResolvedPaperScoringAuthority(
                grading_spec_ref=spec,
                expected_questions=expected,
                minimum_score=exact_minimum,
                maximum_score=smuggled_maximum,
            )


def test_b3_auth_09__paper_minimum_cannot_exceed_maximum() -> None:
    """B3-AUTH-09"""
    b3 = load_b3()

    with pytest.raises(InvalidScoringAuthorityError):
        authority(
            b3,
            (expected_question(b3, "Q1"),),
            minimum="11",
            maximum="10",
        )


def test_b3_auth_10__authority_has_no_numeric_profile_selector() -> None:
    """B3-AUTH-10"""
    b3 = load_b3()
    names = authority_field_names(b3.ResolvedPaperScoringAuthority)

    assert names == (
        "grading_spec_ref",
        "expected_questions",
        "minimum_score",
        "maximum_score",
    )
    assert "numeric_profile_version" not in names


def test_b3_auth_11__authority_has_no_guessed_workflow_identity_fields() -> None:
    """B3-AUTH-11"""
    b3 = load_b3()
    names = set(authority_field_names(b3.ResolvedPaperScoringAuthority))

    assert names.isdisjoint(
        {
            "paper_id",
            "paper_ref",
            "submission_ref",
            "student_id",
            "student_ref",
            "exam_ref",
            "tenant_id",
            "tenant_ref",
            "grading_run_id",
        }
    )


def test_b3_auth_12__structurally_valid_unauthenticated_authority_is_admitted() -> None:
    """B3-AUTH-12"""
    b3 = load_b3()

    # B3 authenticates neither construction provenance nor persistence origin.
    # A completely valid exact-type authority graph must therefore be admitted
    # even when every B3-owned node was created by bypassing its constructor.
    rubric_q1 = _forge_exact(RubricRef, id="rubric-Q1", version=1)
    policy_q1 = _forge_exact(
        ScoringPolicyRef,
        id="policy-Q1",
        version=1,
        scoring_semantics_version="1",
    )
    rubric_q2 = _forge_exact(RubricRef, id="rubric-Q2", version=1)
    policy_q2 = _forge_exact(
        ScoringPolicyRef,
        id="policy-Q2",
        version=1,
        scoring_semantics_version="1",
    )

    forged_spec = _forge_exact(
        b3.GradingSpecRef,
        id="STRUCTURALLY-VALID-NOT-AUTHENTICATED",
        version=7,
    )
    forged_q1 = _forge_exact(
        b3.ExpectedQuestionResult,
        question_id="Q1",
        rubric_ref=rubric_q1,
        scoring_policy_ref=policy_q1,
    )
    forged_q2 = _forge_exact(
        b3.ExpectedQuestionResult,
        question_id="Q2",
        rubric_ref=rubric_q2,
        scoring_policy_ref=policy_q2,
    )
    forged_authority = _forge_exact(
        b3.ResolvedPaperScoringAuthority,
        grading_spec_ref=forged_spec,
        # Deliberately Q2,Q1 to prove defensive re-admission preserves the
        # authority's provenance order rather than reconstructing/sorting it.
        expected_questions=(forged_q2, forged_q1),
        minimum_score=_forge_exact(ScoringDecimal, _value=Decimal("0")),
        maximum_score=_forge_exact(ScoringDecimal, _value=Decimal("2E+1")),
    )
    result_q1 = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=rubric_q1,
        policy=policy_q1,
    )
    result_q2 = question_result(
        "Q2",
        final="2",
        minimum="0",
        maximum="10",
        rubric=rubric_q2,
        policy=policy_q2,
    )

    paper = b3.aggregate_paper(forged_authority, (result_q1, result_q2))

    assert paper.final_score == sd("3")
    assert paper.grading_spec_ref == forged_spec
    assert tuple(result.question_id for result in paper.question_results) == (
        "Q2",
        "Q1",
    )


def test_b3_auth_13__authority_failure_precedes_malformed_result_collection() -> None:
    """B3-AUTH-13"""
    b3 = load_b3()

    class StrSubclass(str):
        pass

    class TupleSubclass(tuple):
        pass

    exact_spec = _forge_exact(b3.GradingSpecRef, id="GS", version=1)
    exact_rubric = RubricRef("rubric-Q1", 1)
    exact_policy = ScoringPolicyRef("policy-Q1", 1, "1")
    exact_expected = _forge_exact(
        b3.ExpectedQuestionResult,
        question_id="Q1",
        rubric_ref=exact_rubric,
        scoring_policy_ref=exact_policy,
    )

    def forge_authority(**overrides):
        values = {
            "grading_spec_ref": exact_spec,
            "expected_questions": (exact_expected,),
            "minimum_score": sd("0"),
            "maximum_score": sd("10"),
        }
        values.update(overrides)
        return _forge_exact(b3.ResolvedPaperScoringAuthority, **values)

    def forge_expected(**overrides):
        values = {
            "question_id": "Q1",
            "rubric_ref": exact_rubric,
            "scoring_policy_ref": exact_policy,
        }
        values.update(overrides)
        return _forge_exact(b3.ExpectedQuestionResult, **values)

    malformed_authorities = [
        # Every public authority node is re-admitted at the reducer boundary;
        # no constructor history is trusted.
        forge_authority(grading_spec_ref=object()),
        # expected_questions must be an exact, non-empty tuple of unique exact
        # ExpectedQuestionResult objects.
        forge_authority(expected_questions=[exact_expected]),
        forge_authority(expected_questions=TupleSubclass((exact_expected,))),
        forge_authority(expected_questions=()),
        forge_authority(expected_questions=(object(),)),
        forge_authority(expected_questions=(exact_expected, exact_expected)),
        # Expected-question identity leaves are re-admitted even if the exact
        # ExpectedQuestionResult itself was forged around constructor checks.
        forge_authority(
            expected_questions=(forge_expected(question_id=StrSubclass("Q1")),)
        ),
        forge_authority(expected_questions=(forge_expected(question_id=""),)),
        forge_authority(expected_questions=(forge_expected(question_id=" Q1 "),)),
        forge_authority(expected_questions=(forge_expected(rubric_ref=object()),)),
        forge_authority(
            expected_questions=(forge_expected(scoring_policy_ref=object()),)
        ),
        # Paper bounds must be exact ScoringDecimal values and their relation is
        # part of authority admission, not deferred to result processing.
        forge_authority(minimum_score=0),
        forge_authority(maximum_score=10),
        forge_authority(minimum_score=sd("11"), maximum_score=sd("10")),
    ]

    grading_spec_subclass = _construct_subclass(
        b3.GradingSpecRef,
        "ForgedGraphGradingSpecRefSubclass",
    )
    subclass_spec = _instantiate_or_none(
        grading_spec_subclass,
        id="GS",
        version=1,
    )
    if subclass_spec is not None:
        malformed_authorities.append(forge_authority(grading_spec_ref=subclass_spec))

    expected_subclass = _construct_subclass(
        b3.ExpectedQuestionResult,
        "ForgedGraphExpectedQuestionResultSubclass",
    )
    subclass_expected = _instantiate_or_none(
        expected_subclass,
        question_id="Q1",
        rubric_ref=exact_rubric,
        scoring_policy_ref=exact_policy,
    )
    if subclass_expected is not None:
        malformed_authorities.append(
            forge_authority(expected_questions=(subclass_expected,))
        )

    rubric_subclass = _construct_subclass(RubricRef, "ForgedGraphRubricRefSubclass")
    subclass_rubric = _instantiate_or_none(rubric_subclass, "rubric-Q1", 1)
    if subclass_rubric is not None:
        malformed_authorities.append(
            forge_authority(
                expected_questions=(forge_expected(rubric_ref=subclass_rubric),)
            )
        )

    policy_subclass = _construct_subclass(
        ScoringPolicyRef,
        "ForgedGraphScoringPolicyRefSubclass",
    )
    subclass_policy = _instantiate_or_none(
        policy_subclass,
        "policy-Q1",
        1,
        "1",
    )
    if subclass_policy is not None:
        malformed_authorities.append(
            forge_authority(
                expected_questions=(
                    forge_expected(scoring_policy_ref=subclass_policy),
                )
            )
        )

    scoring_decimal_subclass = _construct_subclass(
        ScoringDecimal,
        "ForgedGraphScoringDecimalSubclass",
    )
    subclass_minimum = _instantiate_or_none(
        scoring_decimal_subclass,
        sd("0").as_decimal(),
    )
    subclass_maximum = _instantiate_or_none(
        scoring_decimal_subclass,
        sd("10").as_decimal(),
    )
    if subclass_minimum is not None:
        malformed_authorities.append(forge_authority(minimum_score=subclass_minimum))
    if subclass_maximum is not None:
        malformed_authorities.append(forge_authority(maximum_score=subclass_maximum))

    # Exact outer GradingSpecRef objects can still hide invalid leaves that are
    # equality-compatible with valid values. Re-admission must validate leaves.
    for forged_spec in (
        _forge_exact(b3.GradingSpecRef, id=StrSubclass("GS"), version=1),
        _forge_exact(b3.GradingSpecRef, id="", version=1),
        _forge_exact(b3.GradingSpecRef, id=" GS ", version=1),
        _forge_exact(b3.GradingSpecRef, id="GS", version=True),
        _forge_exact(b3.GradingSpecRef, id="GS", version=0),
    ):
        malformed_authorities.append(forge_authority(grading_spec_ref=forged_spec))

    # Same attack against exact nested B2 identity references.
    for forged_rubric in (
        _forge_exact(RubricRef, id=StrSubclass("rubric-Q1"), version=1),
        _forge_exact(RubricRef, id="", version=1),
        _forge_exact(RubricRef, id=" rubric-Q1 ", version=1),
        _forge_exact(RubricRef, id="rubric-Q1", version=True),
        _forge_exact(RubricRef, id="rubric-Q1", version=0),
    ):
        malformed_authorities.append(
            forge_authority(
                expected_questions=(forge_expected(rubric_ref=forged_rubric),)
            )
        )

    for forged_policy in (
        _forge_exact(
            ScoringPolicyRef,
            id=StrSubclass("policy-Q1"),
            version=1,
            scoring_semantics_version="1",
        ),
        _forge_exact(
            ScoringPolicyRef,
            id="",
            version=1,
            scoring_semantics_version="1",
        ),
        _forge_exact(
            ScoringPolicyRef,
            id=" policy-Q1 ",
            version=1,
            scoring_semantics_version="1",
        ),
        _forge_exact(
            ScoringPolicyRef,
            id="policy-Q1",
            version=True,
            scoring_semantics_version="1",
        ),
        _forge_exact(
            ScoringPolicyRef,
            id="policy-Q1",
            version=0,
            scoring_semantics_version="1",
        ),
        _forge_exact(
            ScoringPolicyRef,
            id="policy-Q1",
            version=1,
            scoring_semantics_version=StrSubclass("1"),
        ),
        _forge_exact(
            ScoringPolicyRef,
            id="policy-Q1",
            version=1,
            scoring_semantics_version="2",
        ),
    ):
        malformed_authorities.append(
            forge_authority(
                expected_questions=(
                    forge_expected(scoring_policy_ref=forged_policy),
                )
            )
        )

    # Defensive admission must reject structurally invalid exact ScoringDecimal
    # instances as malformed authority, not allow a technical Decimal exception
    # to escape later during range comparison.
    malformed_authorities.extend(
        (
            forge_authority(
                minimum_score=_forge_exact(ScoringDecimal, _value=Decimal("NaN"))
            ),
            # Finite but noncanonical Numeric Profile v1 representation.
            # This isolates canonical-form re-admission from the finite guard.
            forge_authority(
                maximum_score=_forge_exact(ScoringDecimal, _value=Decimal("10.0"))
            ),
        )
    )

    # Exact outer authority with one required slot absent: this must translate
    # the known malformed structure to InvalidScoringAuthorityError rather than
    # leak a native AttributeError.
    missing_spec_authority = object.__new__(b3.ResolvedPaperScoringAuthority)
    object.__setattr__(missing_spec_authority, "expected_questions", (exact_expected,))
    object.__setattr__(missing_spec_authority, "minimum_score", sd("0"))
    object.__setattr__(missing_spec_authority, "maximum_score", sd("10"))
    malformed_authorities.append(missing_spec_authority)

    # First isolate the two survivor-remediation authority defects with an
    # otherwise fully valid submitted result so no secondary invalidity can mask
    # the reason for rejection.
    valid_result = question_result(
        "Q1",
        final="1",
        minimum="0",
        maximum="10",
        rubric=exact_rubric,
        policy=exact_policy,
    )
    isolated_survivor_authorities = (
        forge_authority(
            maximum_score=_forge_exact(ScoringDecimal, _value=Decimal("10.0"))
        ),
        missing_spec_authority,
    )
    for forged_authority in isolated_survivor_authorities:
        with pytest.raises(InvalidScoringAuthorityError):
            b3.aggregate_paper(forged_authority, (valid_result,))

    # Result input is deliberately malformed as well. Every malformed authority
    # above must win the frozen authority-first precedence rule.
    for forged_authority in malformed_authorities:
        assert type(forged_authority) is b3.ResolvedPaperScoringAuthority
        with pytest.raises(InvalidScoringAuthorityError):
            b3.aggregate_paper(forged_authority, {"Q1": object()})


def test_b3_pure_01__authority_is_frozen_and_slotted() -> None:
    """B3-PURE-01"""
    b3 = load_b3()
    auth, _ = paper_fixture(b3, (("Q1", "1", "0", "10"),))

    assert not hasattr(auth, "__dict__")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        auth.maximum_score = sd("999")


def test_b3_pure_02__paper_result_is_frozen_slotted_and_closed_typed() -> None:
    """B3-PURE-02"""
    b3 = load_b3()
    auth, results = paper_fixture(b3, (("Q1", "1", "0", "10"),))
    paper = b3.aggregate_paper(auth, results)

    assert type(paper) is b3.PaperScoreResult
    assert not hasattr(paper, "__dict__")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        paper.final_score = sd("999")

    class StrSubclass(str):
        pass

    invalid_constructor_variants = [
        {
            "numeric_profile_version": StrSubclass("1"),
        },
        {
            # Supported-profile value is mandatory even when the exact runtime
            # type itself is otherwise valid. This isolates M47.
            "numeric_profile_version": "2",
        },
    ]

    grading_spec_subclass = _construct_subclass(
        b3.GradingSpecRef,
        "PaperResultGradingSpecRefSubclass",
    )
    smuggled_spec = _instantiate_or_none(
        grading_spec_subclass,
        id="GS",
        version=1,
    )
    if smuggled_spec is not None:
        invalid_constructor_variants.append({"grading_spec_ref": smuggled_spec})

    question_result_subclass = _construct_subclass(
        QuestionScoreResult,
        "PaperResultQuestionScoreResultSubclass",
    )
    subclass_result = _instantiate_or_none(
        question_result_subclass,
        **{field.name: getattr(results[0], field.name) for field in fields(QuestionScoreResult)},
    )
    if subclass_result is not None:
        invalid_constructor_variants.append({"question_results": (subclass_result,)})

    scoring_decimal_subclass = _construct_subclass(
        ScoringDecimal,
        "PaperResultScoringDecimalSubclass",
    )
    for field_name, raw_value in (
        ("final_score", "1"),
        ("minimum_score", "0"),
        ("maximum_score", "10"),
    ):
        smuggled_decimal = _instantiate_or_none(
            scoring_decimal_subclass,
            sd(raw_value).as_decimal(),
        )
        if smuggled_decimal is not None:
            invalid_constructor_variants.append({field_name: smuggled_decimal})

    base_kwargs = {
        "grading_spec_ref": auth.grading_spec_ref,
        "numeric_profile_version": "1",
        "question_results": results,
        "final_score": sd("1"),
        "minimum_score": sd("0"),
        "maximum_score": sd("10"),
    }
    for overrides in invalid_constructor_variants:
        with pytest.raises(TypeError):
            b3.PaperScoreResult(**(base_kwargs | overrides))


def test_b3_pure_03__nested_collection_boundaries_are_exact_tuples() -> None:
    """B3-PURE-03"""
    b3 = load_b3()
    expected = expected_question(b3, "Q1")
    spec = b3.GradingSpecRef(id="GS", version=1)

    with pytest.raises(InvalidScoringAuthorityError):
        b3.ResolvedPaperScoringAuthority(
            grading_spec_ref=spec,
            expected_questions=[expected],
            minimum_score=sd("0"),
            maximum_score=sd("10"),
        )

    result = question_result("Q1")

    class TupleSubclass(tuple):
        pass

    for invalid_results in (
        [result],
        TupleSubclass((result,)),
    ):
        with pytest.raises(TypeError):
            b3.PaperScoreResult(
                grading_spec_ref=spec,
                numeric_profile_version="1",
                question_results=invalid_results,
                final_score=sd("1"),
                minimum_score=sd("0"),
                maximum_score=sd("10"),
            )


def test_b3_prov_05__paper_result_does_not_invent_school_paper_identity() -> None:
    """B3-PROV-05"""
    b3 = load_b3()

    assert result_field_names(b3.PaperScoreResult) == (
        "grading_spec_ref",
        "numeric_profile_version",
        "question_results",
        "final_score",
        "minimum_score",
        "maximum_score",
    )
