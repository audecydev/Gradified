from importlib import import_module
from inspect import signature

import pytest


def test_reduce_question_public_boundary_exists_and_is_narrow() -> None:
    """criterion scoring exposes only authority + semantic judgments as scoring inputs."""

    try:
        reducer_module = import_module("grading.scoring.reducer")
    except ModuleNotFoundError as exc:
        if exc.name == "grading.scoring.reducer":
            pytest.fail(
                "Required grading.scoring.reducer module does not exist.",
                pytrace=False,
            )
        raise

    reduce_question = getattr(reducer_module, "reduce_question", None)

    assert callable(reduce_question), (
        "Required grading.scoring.reducer must expose callable reduce_question."
    )

    assert tuple(signature(reduce_question).parameters) == (
        "authority",
        "judgments",
    ), (
        "The question reducer public boundary must accept exactly "
        "(authority, judgments); numerical evaluator totals are not inputs."
    )