from __future__ import annotations

from importlib import import_module

from grading.contracts.numeric_evaluation import NumericConditionOutcome
from grading.numeric_authority import resolve_numeric_authority
from grading.numeric_evaluator import evaluate_numeric_scalar
from grading.numeric_evidence import admit_numeric_scalar
from tests.unit.test_numeric_authority_resolution_regression import (
    _AuthoritySource,
    _BindingSource,
    _Materialized,
    _bound_setup,
)
from tests.unit.test_numeric_evidence_admission_regression import _block, _bundle, _question


def test_red1_existing_n1_n2_n3_path_is_valid_before_missing_n4_import() -> None:
    active, authority, _, binding, approval = _bound_setup()
    evidence = _bundle(_question(_block("5.1")))
    resolved = resolve_numeric_authority(
        active_authority=active,
        binding_source=_BindingSource(binding),
        authority_source=_AuthoritySource(_Materialized(authority, approval)),
    )
    observation = admit_numeric_scalar(evidence=evidence, question_id=active.question_id)
    result = evaluate_numeric_scalar(resolved_authority=resolved, observation=observation)  # type: ignore[arg-type]
    assert result.outcome is NumericConditionOutcome.SATISFIED

    n4 = import_module("grading.numeric_judgments")
    assert callable(n4.evaluate_numeric_question_to_judgments)
