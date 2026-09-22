from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, fields

import pytest

from grading.contracts.choice import (
    CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
    CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
    CHOICE_MATCH_RATIONALE,
    CHOICE_MATCH_REASON_CODE,
    CHOICE_MISMATCH_RATIONALE,
    CHOICE_MISMATCH_REASON_CODE,
    DETERMINISTIC_CHOICE_EVALUATOR_ID,
    DETERMINISTIC_CHOICE_EVALUATOR_VERSION,
    CanonicalChoiceSelection,
    ChoiceCriterionProjection,
    ChoiceEvaluationAuthority,
    ChoiceEvaluationError,
    ChoiceProjectionScoringMismatchError,
    ChoiceScoringAuthorityBindingError,
    ChoiceSelectionBindingError,
    InvalidCanonicalChoiceSelectionError,
    InvalidChoiceEvaluationAuthorityError,
    UnsupportedChoiceInputError,
)
from grading.contracts.paper_aggregation import GradingSpecRef


class _StringSubclass(str):
    pass


class _TupleSubclass(tuple):
    pass


@dataclass(frozen=True, slots=True)
class _ProjectionSubclass(ChoiceCriterionProjection):
    pass


_VALID_HASH = "a" * 64


def projection(
    criterion_id: object = "C1",
    selected_level: object = "FULL",
) -> ChoiceCriterionProjection:
    return ChoiceCriterionProjection(  # type: ignore[arg-type]
        criterion_id=criterion_id,
        selected_level=selected_level,
    )


def authority(**overrides: object) -> ChoiceEvaluationAuthority:
    values: dict[str, object] = {
        "schema_version": CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION,
        "grading_spec_ref": GradingSpecRef("SPEC-1", 1),
        "question_id": "Q1",
        "compiled_authority_hash": _VALID_HASH,
        "option_ids": ("OPT-A", "OPT-B"),
        "official_option_id": "OPT-B",
        "match_projection": (projection("C1", "FULL"),),
        "mismatch_projection": (projection("C1", "NONE"),),
    }
    values.update(overrides)
    return ChoiceEvaluationAuthority(**values)  # type: ignore[arg-type]


def selection(**overrides: object) -> CanonicalChoiceSelection:
    values: dict[str, object] = {
        "schema_version": CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION,
        "submission_ref": "SUB-1",
        "question_id": "Q1",
        "selected_option_id": "OPT-B",
        "evidence_refs": ("BLOCK-1",),
    }
    values.update(overrides)
    return CanonicalChoiceSelection(**values)  # type: ignore[arg-type]


def test_choice_v1_literal_contract_constants_are_exact() -> None:
    assert CHOICE_EVALUATION_AUTHORITY_SCHEMA_VERSION == "1"
    assert CANONICAL_CHOICE_SELECTION_SCHEMA_VERSION == "1"
    assert DETERMINISTIC_CHOICE_EVALUATOR_ID == "gradified-deterministic-choice"
    assert DETERMINISTIC_CHOICE_EVALUATOR_VERSION == "1"
    assert CHOICE_MATCH_REASON_CODE == "DETERMINISTIC_CHOICE_MATCH"
    assert CHOICE_MISMATCH_REASON_CODE == "DETERMINISTIC_CHOICE_MISMATCH"
    assert CHOICE_MATCH_RATIONALE == (
        "Canonical selected option matches the authoritative option."
    )
    assert CHOICE_MISMATCH_RATIONALE == (
        "Canonical selected option does not match the authoritative option."
    )


def test_choice_error_taxonomy_preserves_distinct_sibling_categories() -> None:
    categories = (
        InvalidChoiceEvaluationAuthorityError,
        InvalidCanonicalChoiceSelectionError,
        UnsupportedChoiceInputError,
        ChoiceSelectionBindingError,
        ChoiceScoringAuthorityBindingError,
        ChoiceProjectionScoringMismatchError,
    )
    assert all(issubclass(category, ChoiceEvaluationError) for category in categories)
    assert len(set(categories)) == len(categories)
    assert not issubclass(
        ChoiceProjectionScoringMismatchError,
        ChoiceScoringAuthorityBindingError,
    )
    assert not issubclass(
        ChoiceScoringAuthorityBindingError,
        ChoiceProjectionScoringMismatchError,
    )


def test_contract_surface_contains_no_score_risk_or_recommendation_state() -> None:
    projection_names = {field.name for field in fields(ChoiceCriterionProjection)}
    authority_names = {field.name for field in fields(ChoiceEvaluationAuthority)}
    selection_names = {field.name for field in fields(CanonicalChoiceSelection)}

    assert projection_names == {"criterion_id", "selected_level"}
    assert authority_names == {
        "schema_version",
        "grading_spec_ref",
        "question_id",
        "compiled_authority_hash",
        "option_ids",
        "official_option_id",
        "match_projection",
        "mismatch_projection",
    }
    assert selection_names == {
        "schema_version",
        "submission_ref",
        "question_id",
        "selected_option_id",
        "evidence_refs",
    }

    forbidden = {
        "score",
        "marks",
        "risk",
        "risk_level",
        "recommendation",
        "review_action",
        "awarded_marks",
    }
    assert not (projection_names | authority_names | selection_names) & forbidden


def test_valid_projection_constructs() -> None:
    item = projection()
    assert item == ChoiceCriterionProjection("C1", "FULL")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("criterion_id", ""),
        ("criterion_id", " C1"),
        ("criterion_id", "C1 "),
        ("criterion_id", 1),
        ("selected_level", ""),
        ("selected_level", " FULL"),
        ("selected_level", "FULL "),
        ("selected_level", 1),
        ("selected_level", _StringSubclass("FULL")),
    ),
)
def test_projection_rejects_malformed_identifiers(
    field_name: str,
    bad_value: object,
) -> None:
    kwargs = {field_name: bad_value}
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        projection(**kwargs)


def test_valid_choice_authority_constructs() -> None:
    item = authority()
    assert item.question_id == "Q1"
    assert item.option_ids == ("OPT-A", "OPT-B")


@pytest.mark.parametrize("bad_version", ("", "2", 1, None))
def test_authority_rejects_unsupported_schema_version(bad_version: object) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(schema_version=bad_version)


@pytest.mark.parametrize(
    "bad_spec",
    (
        None,
        ("SPEC-1", 1),
        "SPEC-1:1",
    ),
)
def test_authority_requires_exact_grading_spec_ref(bad_spec: object) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(grading_spec_ref=bad_spec)


@pytest.mark.parametrize("bad_question", ("", " Q1", "Q1 ", 1, None, _StringSubclass("Q1")))
def test_authority_rejects_malformed_question_id(bad_question: object) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(question_id=bad_question)


@pytest.mark.parametrize(
    "bad_hash",
    (
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        1,
        None,
    ),
)
def test_authority_requires_canonical_lowercase_sha256(bad_hash: object) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(compiled_authority_hash=bad_hash)


@pytest.mark.parametrize(
    "bad_options",
    (
        (),
        ["OPT-A", "OPT-B"],
        ("OPT-A", "OPT-A"),
        ("", "OPT-B"),
        (" OPT-A", "OPT-B"),
        ("OPT-A ", "OPT-B"),
        (1, "OPT-B"),
        (_StringSubclass("OPT-A"), "OPT-B"),
        _TupleSubclass(("OPT-A", "OPT-B")),
    ),
)
def test_authority_rejects_malformed_option_universe(bad_options: object) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(option_ids=bad_options)


@pytest.mark.parametrize("bad_official", ("", "MISSING", " OPT-B", "OPT-B ", 1, None, _StringSubclass("OPT-B")))
def test_authority_requires_official_option_in_universe(bad_official: object) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(official_option_id=bad_official)


@pytest.mark.parametrize(
    ("field_name", "bad_projection"),
    (
        ("match_projection", ()),
        ("mismatch_projection", ()),
        ("match_projection", [ChoiceCriterionProjection("C1", "FULL")]),
        ("mismatch_projection", [ChoiceCriterionProjection("C1", "NONE")]),
        (
            "match_projection",
            (
                ChoiceCriterionProjection("C1", "FULL"),
                ChoiceCriterionProjection("C1", "NONE"),
            ),
        ),
        (
            "mismatch_projection",
            (
                ChoiceCriterionProjection("C1", "FULL"),
                ChoiceCriterionProjection("C1", "NONE"),
            ),
        ),
        ("match_projection", (object(),)),
        ("mismatch_projection", (object(),)),
        ("match_projection", (_ProjectionSubclass("C1", "FULL"),)),
        ("mismatch_projection", _TupleSubclass((ChoiceCriterionProjection("C1", "NONE"),))),
    ),
)
def test_authority_rejects_malformed_projection_collections(
    field_name: str,
    bad_projection: object,
) -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(**{field_name: bad_projection})


def test_authority_requires_match_and_mismatch_criterion_sequences_to_agree() -> None:
    with pytest.raises(InvalidChoiceEvaluationAuthorityError):
        authority(
            match_projection=(
                ChoiceCriterionProjection("C1", "FULL"),
                ChoiceCriterionProjection("C2", "FULL"),
            ),
            mismatch_projection=(
                ChoiceCriterionProjection("C2", "NONE"),
                ChoiceCriterionProjection("C1", "NONE"),
            ),
        )


def test_valid_canonical_selection_constructs() -> None:
    item = selection()
    assert item.selected_option_id == "OPT-B"
    assert item.evidence_refs == ("BLOCK-1",)


@pytest.mark.parametrize("bad_version", ("", "2", 1, None))
def test_selection_rejects_unsupported_schema_version(bad_version: object) -> None:
    with pytest.raises(InvalidCanonicalChoiceSelectionError):
        selection(schema_version=bad_version)


@pytest.mark.parametrize("field_name", ("submission_ref", "question_id", "selected_option_id"))
@pytest.mark.parametrize("bad_value", ("", " BAD", "BAD ", 1, None, _StringSubclass("BAD")))
def test_selection_rejects_malformed_scalar_identifiers(
    field_name: str,
    bad_value: object,
) -> None:
    with pytest.raises(InvalidCanonicalChoiceSelectionError):
        selection(**{field_name: bad_value})


@pytest.mark.parametrize(
    "bad_refs",
    (
        (),
        ["BLOCK-1"],
        ("BLOCK-1", "BLOCK-1"),
        ("",),
        (" BLOCK-1",),
        ("BLOCK-1 ",),
        (1,),
        (_StringSubclass("BLOCK-1"),),
        _TupleSubclass(("BLOCK-1",)),
    ),
)
def test_selection_rejects_malformed_evidence_refs(bad_refs: object) -> None:
    with pytest.raises(InvalidCanonicalChoiceSelectionError):
        selection(evidence_refs=bad_refs)


def test_choice_contract_graph_is_recursively_immutable() -> None:
    item = authority()
    selected = selection()

    with pytest.raises(FrozenInstanceError):
        item.question_id = "Q2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        item.match_projection[0].selected_level = "NONE"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        item.grading_spec_ref.version = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        selected.selected_option_id = "OPT-A"  # type: ignore[misc]

    assert type(item.option_ids) is tuple
    assert type(item.match_projection) is tuple
    assert type(item.mismatch_projection) is tuple
    assert type(selected.evidence_refs) is tuple
