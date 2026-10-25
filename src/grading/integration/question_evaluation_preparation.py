from __future__ import annotations

from grading.active_question_authority import (
    ResolvedQuestionAuthority as _ResolvedQuestionAuthority,
)
from grading.contracts.paper_aggregation import (
    ResolvedPaperScoringAuthority as _ResolvedPaperScoringAuthority,
)
from grading.execution import GradingExecutionContext as _GradingExecutionContext
from grading.integration import evaluation_binding as _evaluation_binding
from grading.integration import evidence_ingress as _evidence_ingress


__all__ = ("prepare_question_evaluation_inputs",)


def prepare_question_evaluation_inputs(
    *,
    raw_payload: bytes,
    admission_policy: _evidence_ingress.NormalizedEvidenceAdmissionPolicy,
    context: _GradingExecutionContext,
    paper_authority: _ResolvedPaperScoringAuthority,
    question_authority: _ResolvedQuestionAuthority,
    source_artifact_ref: str | None = None,
) -> _evaluation_binding.BoundQuestionEvaluationInputs:
    """Admit one normalized-evidence wire payload, then bind one question.

    This composition boundary adds no policy of its own. normalized OCR evidence admission owns normalized-wire
    admission and question evidence binding owns the four-root question binding. Their results and
    failures are preserved without translation or reconstruction.
    """

    admitted_evidence = _evidence_ingress.parse_normalized_evidence_payload(
        raw_payload=raw_payload,
        policy=admission_policy,
        source_artifact_ref=source_artifact_ref,
    )
    return _evaluation_binding.bind_question_evaluation_inputs(
        context=context,
        admitted_evidence=admitted_evidence,
        paper_authority=paper_authority,
        question_authority=question_authority,
    )
