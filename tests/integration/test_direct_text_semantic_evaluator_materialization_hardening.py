from __future__ import annotations

import pytest

from grading import semantic_evaluator as se
from tests.integration.test_direct_text_semantic_evaluator_hostile import (
    _Provider,
    _context,
    _evaluator,
    _evidence,
    _resolved_question_authority,
)


class _ExplodingMaterializedAnswer:
    def __init__(self, authority) -> None:
        self.grading_spec_ref = authority.grading_spec_ref
        self.question_id = authority.question_id

    @property
    def content(self) -> str:
        raise RuntimeError("materialized-content-access-failed")


class _ExplodingMaterializedSource:
    def __init__(self, authority) -> None:
        self._answer = _ExplodingMaterializedAnswer(authority)

    def resolve_model_answer(self, *, grading_spec_ref, question_id):
        return self._answer


def test_model_answer_materialized_property_failure_is_normalized_and_chained() -> None:
    authority = _resolved_question_authority()
    source = _ExplodingMaterializedSource(authority)
    provider = _Provider()
    evaluator, _, _ = _evaluator(
        authority=authority,
        source=source,  # type: ignore[arg-type]
        provider=provider,
    )

    with pytest.raises(se.DirectTextSemanticModelAnswerSourceExecutionError) as excinfo:
        evaluator.evaluate(
            authority=authority,
            evidence=_evidence(),
            execution_context=_context(authority=authority),
            evaluation_attempt_id="ATTEMPT-MATERIALIZATION-BOUNDARY",
        )

    assert type(excinfo.value.__cause__) is RuntimeError
    assert str(excinfo.value.__cause__) == "materialized-content-access-failed"
    assert provider.requests == []
