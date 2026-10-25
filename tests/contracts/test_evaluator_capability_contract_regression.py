from importlib import import_module

from grading.contracts.evaluation import EvaluatorMetadata


def test_if1_red1_existing_evaluator_identity_is_valid_before_missing_capability_contract() -> None:
    metadata = EvaluatorMetadata(
        evaluator_id="gradified-deterministic-numeric",
        version="1",
    )
    assert metadata.evaluator_id == "gradified-deterministic-numeric"
    assert metadata.version == "1"

    capability = import_module("grading.contracts.capability")
    assert capability.EVALUATOR_CAPABILITY_RECORD_SCHEMA_VERSION == "1"
