from __future__ import annotations

from dataclasses import dataclass

from grading.rubric.errors import RubricCompilationError
from grading.rubric.fingerprint import (
    authoring_content_fingerprint,
    compilation_limits_fingerprint,
    compiled_authority_canonical_bytes,
    compiled_authority_fingerprint,
    finalized_question_fingerprint,
)
from grading.rubric.linter import RubricLintResult, lint_rubric_content
from grading.rubric.models import (
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
    RubricCompilationLimits,
)
from grading.rubric.profile import RUBRIC_COMPILER_PROFILE_VERSION
from grading.rubric.projection import _build_reducer_authority
from grading.rubric.resources import require_resource_admission


def _require_sha256_hex(value: object, field_name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RubricCompilationError(
            f"{field_name} must be a lowercase SHA-256 hex digest."
        )


@dataclass(frozen=True, slots=True)
class CompiledRubricCandidate:
    """Validated deterministic candidate; not itself B2-admissible authority.

    Release 1 grading authority is exposed only from an ACTIVE lifecycle version.
    Reducer-facing contracts are deliberately not exposed on this pre-ACTIVE
    artifact. They can be deterministically reconstructed from the exact bound
    source content and finalized-question basis, and the reconstructed bytes
    must match ``compiled_authority_hash`` before ACTIVE authority is exposed.
    """

    finalized_question: FinalizedQuestionScoringBasis
    source_content: QuestionRubricAuthoringContent
    version: int
    finalized_question_hash: str
    source_content_hash: str
    compiled_authority_hash: str
    compiler_profile_version: str
    compilation_limits: RubricCompilationLimits
    compilation_limits_hash: str
    reconciliation_state_count: int
    lint_result: RubricLintResult

    def __post_init__(self) -> None:
        if type(self.finalized_question) is not FinalizedQuestionScoringBasis:
            raise RubricCompilationError(
                "finalized_question must be FinalizedQuestionScoringBasis."
            )
        if type(self.source_content) is not QuestionRubricAuthoringContent:
            raise RubricCompilationError(
                "source_content must be QuestionRubricAuthoringContent."
            )
        if type(self.version) is not int or self.version <= 0:
            raise RubricCompilationError("version must be a positive exact int.")
        _require_sha256_hex(self.finalized_question_hash, "finalized_question_hash")
        _require_sha256_hex(self.source_content_hash, "source_content_hash")
        _require_sha256_hex(self.compiled_authority_hash, "compiled_authority_hash")
        if type(self.compiler_profile_version) is not str:
            raise RubricCompilationError(
                "compiler_profile_version must be an exact str."
            )
        if self.compiler_profile_version != RUBRIC_COMPILER_PROFILE_VERSION:
            raise RubricCompilationError(
                "Compiled candidate uses an unsupported compiler profile."
            )
        if type(self.compilation_limits) is not RubricCompilationLimits:
            raise RubricCompilationError(
                "compilation_limits must be RubricCompilationLimits."
            )
        _require_sha256_hex(self.compilation_limits_hash, "compilation_limits_hash")
        if (
            type(self.reconciliation_state_count) is not int
            or self.reconciliation_state_count <= 0
        ):
            raise RubricCompilationError(
                "reconciliation_state_count must be a positive exact int."
            )
        if type(self.lint_result) is not RubricLintResult or not self.lint_result.is_valid:
            raise RubricCompilationError(
                "Compiled candidate requires a valid lint result."
            )

        recomputed_lint = lint_rubric_content(
            self.source_content,
            finalized_question=self.finalized_question,
            version=self.version,
            limits=self.compilation_limits,
        )
        if recomputed_lint != self.lint_result or not recomputed_lint.is_valid:
            raise RubricCompilationError(
                "Compiled candidate lint evidence does not match deterministic revalidation."
            )

        if (
            finalized_question_fingerprint(self.finalized_question)
            != self.finalized_question_hash
        ):
            raise RubricCompilationError(
                "finalized_question_hash does not match the exact finalized question basis."
            )
        if (
            authoring_content_fingerprint(self.source_content)
            != self.source_content_hash
        ):
            raise RubricCompilationError(
                "source_content_hash does not match the exact authoring content."
            )
        if (
            compilation_limits_fingerprint(self.compilation_limits)
            != self.compilation_limits_hash
        ):
            raise RubricCompilationError(
                "compilation_limits_hash does not match the exact resource policy."
            )
        expected_state_count = require_resource_admission(
            self.source_content,
            finalized_question=self.finalized_question,
            limits=self.compilation_limits,
        )
        if expected_state_count != self.reconciliation_state_count:
            raise RubricCompilationError(
                "reconciliation_state_count does not match the compiled rubric level space."
            )
        if expected_state_count > self.compilation_limits.max_reconciliation_states:
            raise RubricCompilationError(
                "Compiled candidate exceeds its recorded reconciliation state-space limit."
            )

        authority = _build_reducer_authority(
            self.source_content,
            finalized_question=self.finalized_question,
            version=self.version,
        )
        if (
            len(compiled_authority_canonical_bytes(authority))
            > self.compilation_limits.max_serialized_authority_bytes
        ):
            raise RubricCompilationError(
                "Compiled authority exceeds its recorded serialized-authority byte limit."
            )
        if compiled_authority_fingerprint(authority) != self.compiled_authority_hash:
            raise RubricCompilationError(
                "compiled_authority_hash does not match the exact compiled authority."
            )


def compile_rubric_content(
    content: QuestionRubricAuthoringContent,
    *,
    finalized_question: FinalizedQuestionScoringBasis,
    version: int,
    limits: RubricCompilationLimits,
) -> CompiledRubricCandidate:
    """Lint and deterministically compile candidate content against trusted input."""

    lint_result = lint_rubric_content(
        content,
        finalized_question=finalized_question,
        version=version,
        limits=limits,
    )
    if not lint_result.is_valid:
        raise RubricCompilationError(
            "Rubric authoring content failed deterministic linting.",
            lint_result=lint_result,
        )

    authority = _build_reducer_authority(
        content,
        finalized_question=finalized_question,
        version=version,
    )
    return CompiledRubricCandidate(
        finalized_question=finalized_question,
        source_content=content,
        version=version,
        finalized_question_hash=finalized_question_fingerprint(finalized_question),
        source_content_hash=authoring_content_fingerprint(content),
        compiled_authority_hash=compiled_authority_fingerprint(authority),
        compiler_profile_version=RUBRIC_COMPILER_PROFILE_VERSION,
        compilation_limits=limits,
        compilation_limits_hash=compilation_limits_fingerprint(limits),
        reconciliation_state_count=require_resource_admission(
            content,
            finalized_question=finalized_question,
            limits=limits,
        ),
        lint_result=lint_result,
    )
