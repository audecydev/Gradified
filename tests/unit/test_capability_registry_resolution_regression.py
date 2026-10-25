from importlib import import_module

from grading.contracts.evaluation import EvaluatorMetadata


def test_if1_red2_exact_evaluator_identity_is_valid_before_missing_registry_resolution() -> None:
    metadata = EvaluatorMetadata(
        evaluator_id="gradified-deterministic-choice",
        version="1",
    )
    assert metadata.evaluator_id == "gradified-deterministic-choice"
    assert metadata.version == "1"

    registry = import_module("grading.capability_registry")
    assert callable(registry.resolve_evaluator_capability)
