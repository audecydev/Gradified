from importlib import import_module
from inspect import signature

import pytest


def test_reduce_question_public_boundary_exists_and_is_narrow() -> None:
    """B2 exposes only authority + semantic judgments as scoring inputs."""

    try:
        reducer_module = import_module("grading.scoring.reducer")
    except ModuleNotFoundError as exc:
        if exc.name == "grading.scoring.reducer":
            pytest.fail(
                "B2 RED-1: grading.scoring.reducer does not exist yet.",
                pytrace=False,
            )
        raise

    reduce_question = getattr(reducer_module, "reduce_question", None)

    assert callable(reduce_question), (
        "B2 RED-1: grading.scoring.reducer must expose callable reduce_question."
    )

    assert tuple(signature(reduce_question).parameters) == (
        "authority",
        "judgments",
    ), (
        "B2 reducer public boundary must accept exactly "
        "(authority, judgments); numerical evaluator totals are not inputs."
    )