from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from grading.contracts.authority import QuestionScoringAuthority
from grading.rubric.compiler import CompiledRubricCandidate, compile_rubric_content
from grading.rubric.errors import (
    InvalidRubricAuthoringInputError,
    RubricAuthoringError,
    NoMeaningfulRubricChangeError,
    RubricLifecycleError,
    RubricResourceLimitError,
)
from grading.rubric.fingerprint import (
    authoring_content_fingerprint,
    compilation_limits_fingerprint,
    compiled_authority_canonical_bytes,
    compiled_authority_fingerprint,
    finalized_question_fingerprint,
)
from grading.rubric.models import (
    FinalizedQuestionScoringBasis,
    QuestionRubricAuthoringContent,
    RubricCompilationLimits,
)
from grading.rubric.profile import SUPPORTED_RUBRIC_COMPILER_PROFILE_VERSIONS
from grading.rubric.projection import _build_reducer_authority
from grading.rubric.resources import RubricResourceIssue, require_resource_admission


class RubricLifecycleState(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


def _require_sha256_hex(value: object, field_name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RubricLifecycleError(
            f"{field_name} must be a lowercase SHA-256 hex digest."
        )


def _require_compiled_activation_resources(
    compilation: CompiledRubricCandidate,
    limits: RubricCompilationLimits,
) -> None:
    authority = _build_reducer_authority(
        compilation.source_content,
        finalized_question=compilation.finalized_question,
        version=compilation.version,
    )
    if (
        compiled_authority_fingerprint(authority)
        != compilation.compiled_authority_hash
    ):
        raise RubricLifecycleError(
            "Compiled candidate no longer reconstructs to its recorded authority hash."
        )
    if (
        len(compiled_authority_canonical_bytes(authority))
        > limits.max_serialized_authority_bytes
    ):
        raise RubricResourceLimitError(
            "Compiled authority exceeds activation-time serialized-authority limits.",
            issues=(
                RubricResourceIssue(
                    "MAX_SERIALIZED_AUTHORITY_BYTES_EXCEEDED",
                    "compiled_authority",
                    "Canonical compiled authority exceeds the activation-time serialized-authority byte limit.",
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class TeacherApproval:
    """Approval binding; caller authentication/teacher-role checks stay upstream."""

    teacher_ref: str
    rubric_id: str
    question_id: str
    version: int
    finalized_question_hash: str
    source_content_hash: str
    compiled_authority_hash: str
    compiler_profile_version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("teacher_ref", self.teacher_ref),
            ("approval rubric_id", self.rubric_id),
            ("approval question_id", self.question_id),
        ):
            if type(value) is not str or not value or value.strip() != value:
                raise RubricLifecycleError(
                    f"{field_name} must be a non-empty string without surrounding whitespace."
                )
        if type(self.version) is not int or self.version <= 0:
            raise RubricLifecycleError("approval version must be a positive exact int.")
        _require_sha256_hex(
            self.finalized_question_hash,
            "approval finalized_question_hash",
        )
        _require_sha256_hex(self.source_content_hash, "approval source_content_hash")
        _require_sha256_hex(
            self.compiled_authority_hash,
            "approval compiled_authority_hash",
        )
        if (
            type(self.compiler_profile_version) is not str
            or self.compiler_profile_version
            not in SUPPORTED_RUBRIC_COMPILER_PROFILE_VERSIONS
        ):
            raise RubricLifecycleError(
                "approval compiler_profile_version is not supported."
            )


@dataclass(frozen=True, slots=True)
class RubricAuthoringVersion:
    """One immutable rubric/policy revision and its activation lifecycle state."""

    finalized_question: FinalizedQuestionScoringBasis
    content: QuestionRubricAuthoringContent
    version: int
    state: RubricLifecycleState
    finalized_question_hash: str
    source_content_hash: str
    compilation: CompiledRubricCandidate | None = None
    approval: TeacherApproval | None = None
    activation_limits: RubricCompilationLimits | None = None
    activation_limits_hash: str | None = None

    def __post_init__(self) -> None:
        if type(self.finalized_question) is not FinalizedQuestionScoringBasis:
            raise InvalidRubricAuthoringInputError(
                "finalized_question must be FinalizedQuestionScoringBasis."
            )
        if type(self.content) is not QuestionRubricAuthoringContent:
            raise InvalidRubricAuthoringInputError(
                "content must be QuestionRubricAuthoringContent."
            )
        if type(self.version) is not int or self.version <= 0:
            raise RubricLifecycleError("version must be a positive integer.")
        if type(self.state) is not RubricLifecycleState:
            raise RubricLifecycleError("state must be a RubricLifecycleState.")

        _require_sha256_hex(
            self.finalized_question_hash,
            "finalized_question_hash",
        )
        expected_question_hash = finalized_question_fingerprint(self.finalized_question)
        if self.finalized_question_hash != expected_question_hash:
            raise RubricLifecycleError(
                "finalized_question_hash does not match the exact finalized question basis."
            )

        _require_sha256_hex(self.source_content_hash, "source_content_hash")
        expected_source_hash = authoring_content_fingerprint(self.content)
        if self.source_content_hash != expected_source_hash:
            raise RubricLifecycleError(
                "source_content_hash does not match the exact authoring content."
            )

        if self.state is RubricLifecycleState.DRAFT:
            if (
                self.compilation is not None
                or self.approval is not None
                or self.activation_limits is not None
                or self.activation_limits_hash is not None
            ):
                raise RubricLifecycleError(
                    "DRAFT versions cannot carry compilation, approval, or activation state."
                )
            return

        if self.compilation is None:
            raise RubricLifecycleError(
                "Validated/approved/active/retired versions require a compiled candidate."
            )
        if self.compilation.source_content_hash != self.source_content_hash:
            raise RubricLifecycleError(
                "Compiled candidate is not bound to this exact authoring content."
            )
        if self.compilation.source_content != self.content:
            raise RubricLifecycleError(
                "Compiled candidate does not contain this exact authoring content."
            )
        if self.compilation.finalized_question_hash != self.finalized_question_hash:
            raise RubricLifecycleError(
                "Compiled candidate is not bound to this exact finalized question basis."
            )
        if self.compilation.finalized_question != self.finalized_question:
            raise RubricLifecycleError(
                "Compiled candidate does not contain this exact finalized question basis."
            )
        if self.compilation.version != self.version:
            raise RubricLifecycleError(
                "Compiled candidate version must equal the authoring revision version."
            )

        if self.state is RubricLifecycleState.VALIDATED:
            if (
                self.approval is not None
                or self.activation_limits is not None
                or self.activation_limits_hash is not None
            ):
                raise RubricLifecycleError(
                    "VALIDATED versions must not carry teacher approval or activation state."
                )
            return

        if self.approval is None:
            raise RubricLifecycleError(
                "APPROVED/ACTIVE/RETIRED versions require teacher approval."
            )
        if (
            self.approval.rubric_id != self.content.rubric_id
            or self.approval.question_id != self.finalized_question.question_id
            or self.approval.version != self.version
            or self.approval.finalized_question_hash != self.finalized_question_hash
            or self.approval.source_content_hash != self.source_content_hash
            or self.approval.compiled_authority_hash
            != self.compilation.compiled_authority_hash
            or self.approval.compiler_profile_version
            != self.compilation.compiler_profile_version
        ):
            raise RubricLifecycleError(
                "Teacher approval is not bound to this exact question/rubric version/content, compiled authority, and compiler profile."
            )

        if self.state is RubricLifecycleState.APPROVED:
            if self.activation_limits is not None or self.activation_limits_hash is not None:
                raise RubricLifecycleError(
                    "APPROVED versions must not carry activation resource-policy provenance yet."
                )
            return

        if self.state in (RubricLifecycleState.ACTIVE, RubricLifecycleState.RETIRED):
            if type(self.activation_limits) is not RubricCompilationLimits:
                raise RubricLifecycleError(
                    "ACTIVE/RETIRED versions require the exact activation resource policy."
                )
            if self.activation_limits_hash is None:
                raise RubricLifecycleError(
                    "ACTIVE/RETIRED versions require activation resource-policy provenance."
                )
            _require_sha256_hex(
                self.activation_limits_hash,
                "activation_limits_hash",
            )
            if (
                compilation_limits_fingerprint(self.activation_limits)
                != self.activation_limits_hash
            ):
                raise RubricLifecycleError(
                    "activation_limits_hash does not match the exact activation resource policy."
                )
            require_resource_admission(
                self.content,
                finalized_question=self.finalized_question,
                limits=self.activation_limits,
            )
            _require_compiled_activation_resources(
                self.compilation,
                self.activation_limits,
            )
            return

        raise RubricLifecycleError("Unhandled rubric lifecycle state.")


def create_initial_version(
    finalized_question: FinalizedQuestionScoringBasis,
    content: QuestionRubricAuthoringContent,
) -> RubricAuthoringVersion:
    if type(finalized_question) is not FinalizedQuestionScoringBasis:
        raise InvalidRubricAuthoringInputError(
            "finalized_question must be FinalizedQuestionScoringBasis."
        )
    if type(content) is not QuestionRubricAuthoringContent:
        raise InvalidRubricAuthoringInputError(
            "content must be QuestionRubricAuthoringContent."
        )
    return RubricAuthoringVersion(
        finalized_question=finalized_question,
        content=content,
        version=1,
        state=RubricLifecycleState.DRAFT,
        finalized_question_hash=finalized_question_fingerprint(finalized_question),
        source_content_hash=authoring_content_fingerprint(content),
    )


def revise_version(
    previous: RubricAuthoringVersion,
    finalized_question: FinalizedQuestionScoringBasis,
    new_content: QuestionRubricAuthoringContent,
) -> RubricAuthoringVersion:
    if type(previous) is not RubricAuthoringVersion:
        raise RubricLifecycleError("previous must be a RubricAuthoringVersion.")
    if type(finalized_question) is not FinalizedQuestionScoringBasis:
        raise InvalidRubricAuthoringInputError(
            "finalized_question must be FinalizedQuestionScoringBasis."
        )
    if type(new_content) is not QuestionRubricAuthoringContent:
        raise InvalidRubricAuthoringInputError(
            "new_content must be QuestionRubricAuthoringContent."
        )
    if new_content.rubric_id != previous.content.rubric_id:
        raise RubricLifecycleError(
            "A revision must retain rubric_id; a new rubric identity starts at version 1."
        )
    if new_content.policy_id != previous.content.policy_id:
        raise RubricLifecycleError(
            "A revision must retain policy_id; a new policy identity starts a new lineage."
        )
    if finalized_question.question_id != previous.finalized_question.question_id:
        raise RubricLifecycleError(
            "A rubric revision cannot be rebound to a different finalized question_id."
        )

    new_source_hash = authoring_content_fingerprint(new_content)
    new_question_hash = finalized_question_fingerprint(finalized_question)
    if (
        new_source_hash == previous.source_content_hash
        and new_question_hash == previous.finalized_question_hash
    ):
        raise NoMeaningfulRubricChangeError(
            "A new version requires a meaningful canonical content or finalized-question change."
        )

    return RubricAuthoringVersion(
        finalized_question=finalized_question,
        content=new_content,
        version=previous.version + 1,
        state=RubricLifecycleState.DRAFT,
        finalized_question_hash=new_question_hash,
        source_content_hash=new_source_hash,
    )


def validate_version(
    version: RubricAuthoringVersion,
    *,
    limits: RubricCompilationLimits,
) -> RubricAuthoringVersion:
    if type(version) is not RubricAuthoringVersion:
        raise RubricLifecycleError("version must be a RubricAuthoringVersion.")
    if version.state is not RubricLifecycleState.DRAFT:
        raise RubricLifecycleError("Only a DRAFT rubric version can be validated.")

    compilation = compile_rubric_content(
        version.content,
        finalized_question=version.finalized_question,
        version=version.version,
        limits=limits,
    )
    return replace(
        version,
        state=RubricLifecycleState.VALIDATED,
        compilation=compilation,
    )


def approve_version(
    version: RubricAuthoringVersion,
    *,
    teacher_ref: str,
) -> RubricAuthoringVersion:
    if type(version) is not RubricAuthoringVersion:
        raise RubricLifecycleError("version must be a RubricAuthoringVersion.")
    if version.state is not RubricLifecycleState.VALIDATED:
        raise RubricLifecycleError("Only a VALIDATED rubric version can be approved.")
    if version.compilation is None:
        raise RubricLifecycleError("Validated version is missing compiled candidate.")

    approval = TeacherApproval(
        teacher_ref=teacher_ref,
        rubric_id=version.content.rubric_id,
        question_id=version.finalized_question.question_id,
        version=version.version,
        finalized_question_hash=version.finalized_question_hash,
        source_content_hash=version.source_content_hash,
        compiled_authority_hash=version.compilation.compiled_authority_hash,
        compiler_profile_version=version.compilation.compiler_profile_version,
    )
    return replace(
        version,
        state=RubricLifecycleState.APPROVED,
        approval=approval,
    )


def activate_version(
    version: RubricAuthoringVersion,
    *,
    limits: RubricCompilationLimits,
) -> RubricAuthoringVersion:
    if type(version) is not RubricAuthoringVersion:
        raise RubricLifecycleError("version must be a RubricAuthoringVersion.")
    if type(limits) is not RubricCompilationLimits:
        raise InvalidRubricAuthoringInputError(
            "limits must be RubricCompilationLimits; Release 1 has no implicit production defaults."
        )
    if version.state is not RubricLifecycleState.APPROVED:
        raise RubricLifecycleError(
            "Release 1 activation requires a teacher-approved rubric version."
        )
    require_resource_admission(
        version.content,
        finalized_question=version.finalized_question,
        limits=limits,
    )
    if version.compilation is None:
        raise RubricLifecycleError("APPROVED rubric version is missing compiled candidate.")
    _require_compiled_activation_resources(version.compilation, limits)
    return replace(
        version,
        state=RubricLifecycleState.ACTIVE,
        activation_limits=limits,
        activation_limits_hash=compilation_limits_fingerprint(limits),
    )


def _require_active_exposure_integrity(version: RubricAuthoringVersion) -> None:
    """Re-establish current ACTIVE lifecycle integrity before authority exposure.

    Frozen dataclasses prevent ordinary mutation but are not an integrity boundary.
    Re-run the existing lifecycle invariants from the current object graph instead
    of trusting construction history.  This intentionally does not re-run the
    full rubric linter/reconciliation campaign at grading time; compilation-time
    diagnostics that do not affect ACTIVE exposure remain compilation provenance.
    """

    if type(version.compilation) is not CompiledRubricCandidate:
        raise RubricLifecycleError(
            "ACTIVE rubric version is missing an exact compiled candidate."
        )
    if type(version.approval) is not TeacherApproval:
        raise RubricLifecycleError(
            "ACTIVE rubric version is missing exact teacher-approval evidence."
        )

    try:
        # TeacherApproval.__post_init__ owns the local shape/profile contract for
        # the approval object. RubricAuthoringVersion.__post_init__ then
        # recomputes current question/content fingerprints and re-establishes the
        # compilation, approval, activation-policy, and compiled-authority
        # relationships used by ACTIVE exposure.
        version.approval.__post_init__()
        version.__post_init__()
    except RubricAuthoringError:
        raise
    except Exception as exc:
        raise RubricLifecycleError(
            "ACTIVE rubric integrity revalidation failed on malformed current state."
        ) from exc

def get_active_scoring_authority(
    version: RubricAuthoringVersion,
) -> QuestionScoringAuthority:
    """Expose reducer authority only through the supported ACTIVE lifecycle path."""

    if type(version) is not RubricAuthoringVersion:
        raise RubricLifecycleError("version must be a RubricAuthoringVersion.")
    if version.state is not RubricLifecycleState.ACTIVE:
        raise RubricLifecycleError(
            "Reducer authority is available only from an ACTIVE rubric version."
        )

    _require_active_exposure_integrity(version)

    authority = _build_reducer_authority(
        version.content,
        finalized_question=version.finalized_question,
        version=version.version,
    )
    authority_hash = compiled_authority_fingerprint(authority)
    if authority_hash != version.compilation.compiled_authority_hash:
        raise RubricLifecycleError(
            "ACTIVE authority no longer matches the deterministically compiled candidate."
        )
    if authority_hash != version.approval.compiled_authority_hash:
        raise RubricLifecycleError(
            "ACTIVE authority no longer matches the exact teacher-approved compiled authority."
        )
    return authority


def retire_version(version: RubricAuthoringVersion) -> RubricAuthoringVersion:
    if type(version) is not RubricAuthoringVersion:
        raise RubricLifecycleError("version must be a RubricAuthoringVersion.")
    if version.state is not RubricLifecycleState.ACTIVE:
        raise RubricLifecycleError("Only an ACTIVE rubric version can be retired.")
    return replace(version, state=RubricLifecycleState.RETIRED)
