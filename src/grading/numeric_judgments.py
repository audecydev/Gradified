from __future__ import annotations

from grading.active_question_authority import ResolvedQuestionAuthority
from grading.contracts.evaluation import EvaluatedCriterionJudgment, EvaluatorMetadata
from grading.contracts.evidence import AnswerEvidenceBundle
from grading.contracts.numeric_authority import NumericNotAuthorizedBinding
from grading.contracts.numeric_evaluation import (
    DETERMINISTIC_NUMERIC_EVALUATOR_ID,
    DETERMINISTIC_NUMERIC_EVALUATOR_VERSION,
    NumericConditionOutcome,
    validate_numeric_evaluation_result,
)
from grading.numeric_authority import (
    NumericAuthoritySource,
    NumericExpectedBindingSource,
    ResolvedNumericAuthority,
    resolve_numeric_authority,
)
from grading.numeric_evaluator import evaluate_numeric_scalar
from grading.numeric_evidence import admit_numeric_scalar


NUMERIC_CONDITION_SATISFIED_REASON_CODE = "NUMERIC_CONDITION_SATISFIED"
NUMERIC_CONDITION_NOT_SATISFIED_REASON_CODE = "NUMERIC_CONDITION_NOT_SATISFIED"
NUMERIC_CONDITION_SATISFIED_RATIONALE = "Approved numeric condition satisfied."
NUMERIC_CONDITION_NOT_SATISFIED_RATIONALE = "No approved numeric condition satisfied."


class NumericJudgmentCompositionError(Exception):
    """Base class for N4 NUMERIC judgment-composition failures."""


class NumericNotAuthorizedForQuestionError(NumericJudgmentCompositionError):
    """The exact ACTIVE question explicitly has no NUMERIC authority."""


class NumericCompositionInvariantError(NumericJudgmentCompositionError):
    """Trusted N1/N2/N3 outputs disagree on identity/provenance."""


def _require_resolved_result(value: object) -> ResolvedNumericAuthority:
    if type(value) is not ResolvedNumericAuthority:
        raise NumericCompositionInvariantError(
            "N1 resolver returned an unsupported NUMERIC authority state."
        )
    return value


def evaluate_numeric_question_to_judgments(
    *,
    active_authority: ResolvedQuestionAuthority,
    evidence: AnswerEvidenceBundle,
    binding_source: NumericExpectedBindingSource,
    authority_source: NumericAuthoritySource,
) -> tuple[EvaluatedCriterionJudgment, ...]:
    """Run N1 -> N2 -> N3 and project the approved whole-question N1 outcome.

    The function deliberately does not accept a caller-supplied N3 result.  It
    executes the trusted resolver, evidence admission, and deterministic
    evaluator in-process, then maps the resulting SATISFIED/NOT_SATISFIED state
    to the already-approved N1 complete criterion projection.  It does not
    calculate marks or bypass the existing S1/B2/B3 verification/scoring path.
    """

    resolved_or_not = resolve_numeric_authority(
        active_authority=active_authority,
        binding_source=binding_source,
        authority_source=authority_source,
    )
    if type(resolved_or_not) is NumericNotAuthorizedBinding:
        raise NumericNotAuthorizedForQuestionError(
            "The exact ACTIVE question is explicitly NOT_AUTHORIZED for NUMERIC evaluation."
        )
    resolved = _require_resolved_result(resolved_or_not)

    observation = admit_numeric_scalar(
        evidence=evidence,
        question_id=resolved.question_id,
    )
    evaluation = evaluate_numeric_scalar(
        resolved_authority=resolved,
        observation=observation,
    )
    validate_numeric_evaluation_result(evaluation)

    if (
        evaluation.grading_spec_ref != resolved.grading_spec_ref
        or evaluation.authority_fingerprint != resolved.authority_fingerprint
        or evaluation.question_id != resolved.question_id
    ):
        raise NumericCompositionInvariantError(
            "N3 evaluation identity does not match the exact resolved N1 authority."
        )
    if (
        evaluation.question_id != observation.question_id
        or evaluation.submission_ref != observation.submission_ref
        or evaluation.ocr_provenance != observation.ocr_provenance
        or evaluation.answer_scope_ref != observation.answer_scope_ref
        or evaluation.evidence_ref != observation.evidence_ref
        or evaluation.admission_profile_version != observation.admission_profile_version
    ):
        raise NumericCompositionInvariantError(
            "N3 evaluation provenance does not match the exact admitted N2 observation."
        )

    if evaluation.outcome is NumericConditionOutcome.SATISFIED:
        projection = resolved.authority.satisfied_projection
        reason_code = NUMERIC_CONDITION_SATISFIED_REASON_CODE
        rationale = NUMERIC_CONDITION_SATISFIED_RATIONALE
    elif evaluation.outcome is NumericConditionOutcome.NOT_SATISFIED:
        projection = resolved.authority.not_satisfied_projection
        reason_code = NUMERIC_CONDITION_NOT_SATISFIED_REASON_CODE
        rationale = NUMERIC_CONDITION_NOT_SATISFIED_RATIONALE
    else:  # validated exact enum above; defensive only
        raise NumericCompositionInvariantError(
            "N3 evaluation produced an unsupported NUMERIC outcome."
        )

    metadata = EvaluatorMetadata(
        evaluator_id=DETERMINISTIC_NUMERIC_EVALUATOR_ID,
        version=DETERMINISTIC_NUMERIC_EVALUATOR_VERSION,
    )
    return tuple(
        EvaluatedCriterionJudgment(
            criterion_id=item.criterion_id,
            selected_level=item.selected_level,
            evidence_refs=(evaluation.evidence_ref,),
            reason_codes=(reason_code,),
            concise_rationale=rationale,
            uncertainties=(),
            evaluator_metadata=metadata,
        )
        for item in projection
    )
