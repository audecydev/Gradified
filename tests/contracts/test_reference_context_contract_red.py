from __future__ import annotations

from importlib import import_module

from grading.active_question_authority import ContextPolicy


def test_ref1_red1_existing_context_policy_is_valid_before_missing_reference_contract() -> None:
    assert ContextPolicy.HYBRID_RETRIEVAL.value == "HYBRID_RETRIEVAL"
    assert ContextPolicy.REFERENCE_ONLY.value == "REFERENCE_ONLY"

    contract = import_module("grading.contracts.reference_context")
    assert contract.REFERENCE_CONTEXT_SCHEMA_VERSION == "1"
