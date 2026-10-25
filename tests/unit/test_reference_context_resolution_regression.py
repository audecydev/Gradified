from __future__ import annotations

from importlib import import_module

from grading.active_question_authority import ContextPolicy
from grading.contracts.paper_aggregation import GradingSpecRef


def test_ref1_red2_existing_binding_primitives_are_valid_before_missing_resolver() -> None:
    spec_ref = GradingSpecRef(id="SPEC-REF-1", version=1)
    assert spec_ref.id == "SPEC-REF-1"
    assert spec_ref.version == 1
    assert ContextPolicy.DIRECT_PLUS_REFERENCE.value == "DIRECT_PLUS_REFERENCE"

    module = import_module("grading.reference_context")
    assert callable(module.resolve_reference_context)
