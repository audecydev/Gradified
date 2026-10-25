"""Backend-owned authorization and independently approved normalized OCR evidence admission policy before PRE.

The application composition root supplies all five real, trusted adapters. Identifiers,
record types and this result do not independently authenticate a caller or grant grading.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import inspect
import io
from types import BuiltinFunctionType, FunctionType, MethodDescriptorType
from typing import BinaryIO, Callable, Protocol

from grading.contracts.paper_aggregation import GradingSpecRef
from grading.contracts.errors import ScoringError
from grading.integration.evidence_ingress import (
    NormalizedEvidenceAdmissionPolicy, NormalizedEvidenceIngressError,
    InvalidNormalizedEvidenceAdmissionPolicyError,
)
from grading.integration.evaluation_binding import QuestionEvaluationBindingError
from grading.integration.trusted_preparation import (
    PreparationRequest, PreparationSourceSnapshot, PreparationSourceUnavailable,
    PreparationResourceLimitError, PreparationScopeRejected,
    PreparationSourceContractError, PreparedWithSourceCustody,
    prepare_from_trusted_source,
)

__all__ = (
    "AuthenticatedActor", "PreparationAccessGrant", "ApprovedAdmissionPolicyRecord",
    "RevisionedPreparationRecord", "PreparationCustody", "AuthorizedPreparedQuestion",
    "IdentityAuthority", "PreparationAccessAuthority", "ApprovedPolicyAuthority",
    "RevisionedSourceAuthority", "AuthorizedEvidenceAuthority", "ProductionPreparationComposer",
    "PreparationAuthorizationRejected", "PreparationAuthorityUnavailable",
    "PreparationAuthorityContractError",
)


class PreparationAuthorizationRejected(ValueError):
    """Independent permission or required ownership/revision relationship mismatched."""


class PreparationAuthorityUnavailable(Exception):
    """An installed backend authority could not deliver its required fact."""


class PreparationAuthorityContractError(ValueError):
    """Installed authority returned malformed or unsupported structured facts."""


def _id(value: object, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum or value.strip() != value:
        raise PreparationAuthorityContractError("Authority identifier is missing or malformed.")
    return value


def _attr(value: object, name: str) -> object:
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        raise PreparationAuthorityContractError("Authority record is incomplete.") from None


def _request_copy(value: object, maximum: int) -> PreparationRequest:
    if type(value) is not PreparationRequest:
        raise PreparationAuthorityContractError("Preparation request has an invalid type.")
    spec = _attr(value, "grading_spec_ref")
    if type(spec) is not GradingSpecRef:
        raise PreparationAuthorityContractError("Grading specification has an invalid type.")
    try:
        versioned = GradingSpecRef(
            id=_id(_attr(spec, "id"), maximum), version=_attr(spec, "version"),
        )
        return PreparationRequest(
            tenant_ref=_id(_attr(value, "tenant_ref"), maximum),
            session_ref=_id(_attr(value, "session_ref"), maximum),
            grading_run_id=_id(_attr(value, "grading_run_id"), maximum),
            submission_ref=_id(_attr(value, "submission_ref"), maximum),
            exam_ref=_id(_attr(value, "exam_ref"), maximum),
            question_id=_id(_attr(value, "question_id"), maximum),
            grading_spec_ref=versioned,
        )
    except (TypeError, ValueError, ScoringError):
        raise PreparationAuthorityContractError("Preparation request is malformed.") from None


def _policy_copy(value: object, maximum: int) -> NormalizedEvidenceAdmissionPolicy:
    if type(value) is not NormalizedEvidenceAdmissionPolicy:
        raise PreparationAuthorityContractError("Approved policy has an invalid type.")
    try:
        data = {field.name: _attr(value, field.name) for field in fields(NormalizedEvidenceAdmissionPolicy)}
        _id(data["admission_policy_identity"], maximum)
        return NormalizedEvidenceAdmissionPolicy(**data)
    except (TypeError, ValueError):
        raise PreparationAuthorityContractError("Approved policy is malformed.") from None


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticatedActor:
    """Only the installed backend identity authority may supply this record."""

    actor_ref: str
    tenant_ref: str
    session_ref: str


@dataclass(frozen=True, slots=True, repr=False)
class PreparationAccessGrant:
    """Authorization at an exact source/policy revision; not a bearer credential."""

    actor_ref: str
    request: PreparationRequest
    source_artifact_ref: str
    source_revision: str
    admission_policy_identity: str
    policy_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedAdmissionPolicyRecord:
    """Independently approved versioned policy from the configured policy authority."""

    admission_policy_identity: str
    policy_revision: str
    policy: NormalizedEvidenceAdmissionPolicy


@dataclass(frozen=True, slots=True, repr=False)
class RevisionedPreparationRecord:
    """Source snapshot and revision returned by protected backend source access."""

    source_revision: str
    source: PreparationSourceSnapshot


@dataclass(frozen=True, slots=True, repr=False)
class PreparationCustody:
    actor_ref: str
    tenant_ref: str
    session_ref: str
    source_artifact_ref: str
    source_revision: str
    admission_policy_identity: str
    policy_revision: str


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedPreparedQuestion:
    """Prepared question plus audit references; NOT evaluator execution eligibility."""

    prepared: PreparedWithSourceCustody
    custody: PreparationCustody


class IdentityAuthority(Protocol):
    def current_actor(self) -> AuthenticatedActor: ...


class PreparationAccessAuthority(Protocol):
    def authorize_preparation(
        self, *, actor: AuthenticatedActor, request: PreparationRequest,
    ) -> PreparationAccessGrant: ...


class ApprovedPolicyAuthority(Protocol):
    def resolve_approved_policy(
        self, *, grant: PreparationAccessGrant,
    ) -> ApprovedAdmissionPolicyRecord: ...


class RevisionedSourceAuthority(Protocol):
    def resolve_revisioned_preparation(
        self, *, grant: PreparationAccessGrant,
    ) -> RevisionedPreparationRecord: ...


class AuthorizedEvidenceAuthority(Protocol):
    """Backend must recheck the exact grant/source revision at the actual read."""

    def open_authorized_evidence(self, *, grant: PreparationAccessGrant) -> BinaryIO: ...


def _actor_copy(value: object, maximum: int) -> AuthenticatedActor:
    if type(value) is not AuthenticatedActor:
        raise PreparationAuthorityContractError("Backend identity authority returned invalid actor facts.")
    return AuthenticatedActor(*(
        _id(_attr(value, name), maximum)
        for name in ("actor_ref", "tenant_ref", "session_ref")
    ))


def _grant_copy(value: object, maximum: int) -> PreparationAccessGrant:
    if type(value) is not PreparationAccessGrant:
        raise PreparationAuthorityContractError("Backend access authority returned an invalid grant.")
    return PreparationAccessGrant(
        actor_ref=_id(_attr(value, "actor_ref"), maximum),
        request=_request_copy(_attr(value, "request"), maximum),
        source_artifact_ref=_id(_attr(value, "source_artifact_ref"), maximum),
        source_revision=_id(_attr(value, "source_revision"), maximum),
        admission_policy_identity=_id(_attr(value, "admission_policy_identity"), maximum),
        policy_revision=_id(_attr(value, "policy_revision"), maximum),
    )


def _approved_copy(value: object, maximum: int) -> ApprovedAdmissionPolicyRecord:
    if type(value) is not ApprovedAdmissionPolicyRecord:
        raise PreparationAuthorityContractError("Backend policy authority returned an invalid record.")
    return ApprovedAdmissionPolicyRecord(
        admission_policy_identity=_id(_attr(value, "admission_policy_identity"), maximum),
        policy_revision=_id(_attr(value, "policy_revision"), maximum),
        policy=_policy_copy(_attr(value, "policy"), maximum),
    )


def _revisioned_copy(value: object, maximum: int) -> RevisionedPreparationRecord:
    if type(value) is not RevisionedPreparationRecord:
        raise PreparationAuthorityContractError("Backend source returned an invalid revisioned record.")
    source = _attr(value, "source")
    if type(source) is not PreparationSourceSnapshot:
        raise PreparationAuthorityContractError("Backend source returned an invalid PRE source.")
    return RevisionedPreparationRecord(
        source_revision=_id(_attr(value, "source_revision"), maximum),
        source=source,
    )


def _validated_port_method(port: object, operation: str) -> Callable:
    """Capture a supported backend method without invoking dynamic attribute lookup."""
    try:
        declared = inspect.getattr_static(port, operation, None)
        class_declared = inspect.getattr_static(type(port), operation, None)
    except Exception:
        declared = None
        class_declared = None
    if type(declared) is FunctionType:
        # Instance-assigned plain functions are already bound by the adapter;
        # class methods need native FunctionType binding, not getattr(port).
        if declared is class_declared:
            return declared.__get__(port, type(port))
        return declared
    if (type(declared) is staticmethod and declared is class_declared
            and type(declared.__func__) is FunctionType):
        return declared.__func__
    raise PreparationAuthorityContractError("A required backend authority port is missing.")


def _call(callback: Callable, *, allow_denial: bool = False, **kwargs: object) -> object:
    """Invoke the captured backend operation within one privacy-safe boundary.

    The access authority and privileged evidence opener may explicitly deny.
    Other backend failures are unavailable, never inferred permission results.
    """
    failed = False
    denied = False
    result: object = None
    try:
        result = callback(**kwargs)
    except PreparationAuthorizationRejected:
        if allow_denial:
            denied = True
        else:
            failed = True
    except Exception:
        failed = True
    # Raise outside the backend handler: never chain sensitive backend failures.
    if denied:
        raise PreparationAuthorizationRejected("Backend authorization denied preparation.") from None
    if failed:
        raise PreparationAuthorityUnavailable("A required backend authority was unavailable.") from None
    return result


def _validated_reader_method(reader: object, operation: str) -> Callable:
    """Bind an allowed operation once; never re-resolve mutable attributes at use.

    Backend-owned custom binary readers may expose ordinary Python class methods.
    Native built-in operations require an actual binary IO object, correct operation
    name, and matching method owner. Reader trust still belongs to the backend.
    """
    reader_type = type(reader)
    if inspect.getattr_static(reader_type, "__getattribute__", None) is not object.__getattribute__:
        raise PreparationAuthorityContractError("Protected evidence reader has an invalid method contract.")

    declared = inspect.getattr_static(reader, operation, None)
    class_declared = inspect.getattr_static(reader_type, operation, None)
    if type(declared) is FunctionType and declared is class_declared:
        # Never let __signature__ / __wrapped__ override the actual Python ABI.
        if (declared.__name__ != operation or "__signature__" in declared.__dict__
                or "__wrapped__" in declared.__dict__):
            raise PreparationAuthorityContractError("Protected evidence reader has an invalid method contract.")
        try:
            signature = inspect.signature(declared, follow_wrapped=False)
            if operation == "read":
                signature.bind(reader, 1)
            else:
                signature.bind(reader)
        except (TypeError, ValueError):
            raise PreparationAuthorityContractError("Protected evidence reader has an invalid method contract.") from None
        # Function.__get__ is Python's native binder; do not look up reader.read.
        return declared.__get__(reader, reader_type)

    is_binary_io = issubclass(reader_type, (io.BufferedIOBase, io.RawIOBase))
    if is_binary_io and type(declared) is MethodDescriptorType:
        owner = declared.__objclass__
        if (declared is class_declared and declared.__name__ == operation
                and owner in reader_type.__mro__):
            return declared.__get__(reader, reader_type)

    if is_binary_io and type(declared) is BuiltinFunctionType:
        if declared.__name__ == operation and declared.__self__ is reader:
            return declared

    raise PreparationAuthorityContractError("Protected evidence reader has an invalid method contract.")


class _RevocationAwareStream:
    """Call the exact admitted methods; mark explicit denial without re-lookup."""

    def __init__(self, read: Callable[[int], bytes], close: Callable[[], None], mark_denied: Callable[[], None]):
        self._read = read
        self._close = close
        self._mark_denied = mark_denied

    def read(self, size: int) -> bytes:
        try:
            return self._read(size)
        except PreparationAuthorizationRejected:
            self._mark_denied()
            raise

    def close(self) -> None:
        try:
            self._close()
        except PreparationAuthorizationRejected:
            self._mark_denied()
            raise


class _CapturedSource:
    """One already authorized snapshot; PRE must not requery backend authorities."""

    def __init__(self, snapshot: PreparationSourceSnapshot):
        self.snapshot = snapshot

    def resolve_preparation(self, *, request: PreparationRequest) -> PreparationSourceSnapshot:
        return self.snapshot


class ProductionPreparationComposer:
    """Configure ONLY at the trusted application composition root.

    The backend must guarantee real authenticated identity, authorization,
    immutable approved policy revisions, coherent source reads and deferred IO.
    Python ports cannot manufacture or independently prove these external facts.
    """

    def __init__(
        self, *, identity: IdentityAuthority, access: PreparationAccessAuthority,
        approved_policies: ApprovedPolicyAuthority, sources: RevisionedSourceAuthority,
        evidence: AuthorizedEvidenceAuthority, max_identifier_characters: int,
    ) -> None:
        try:
            if type(max_identifier_characters) is not int or max_identifier_characters <= 0:
                raise PreparationAuthorityContractError("Trusted identifier ceiling is required.")
            operations = {
                operation: _validated_port_method(port, operation)
                for port, operation in (
                    (identity, "current_actor"), (access, "authorize_preparation"),
                    (approved_policies, "resolve_approved_policy"),
                    (sources, "resolve_revisioned_preparation"),
                    (evidence, "open_authorized_evidence"),
                )
            }
        except PreparationAuthorityContractError as caught:
            # Sanitize even when constructed inside an ambient private exception handler.
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None
        self._operations = operations
        self._maximum = max_identifier_characters

    def prepare(self, *, request: PreparationRequest) -> AuthorizedPreparedQuestion:
        """Return a prepared result or a sanitized, non-authorizing failure."""
        try:
            return self._prepare_impl(request=request)
        except (
            PreparationAuthorizationRejected, PreparationAuthorityUnavailable,
            PreparationAuthorityContractError, PreparationScopeRejected,
            PreparationSourceUnavailable, PreparationSourceContractError,
            PreparationResourceLimitError, NormalizedEvidenceIngressError,
            InvalidNormalizedEvidenceAdmissionPolicyError,
            QuestionEvaluationBindingError,
        ) as caught:
            # Do not leak an ambient caller exception into a typed PRE error.
            caught.__cause__ = None
            caught.__context__ = None
            caught.__suppress_context__ = True
            raise caught from None

    def _prepare_impl(self, *, request: PreparationRequest) -> AuthorizedPreparedQuestion:
        """Require actor → grant → approved policy → matching source before IO."""
        maximum = self._maximum
        pinned_request = _request_copy(request, maximum)
        actor = _actor_copy(_call(self._operations["current_actor"]), maximum)
        if (actor.tenant_ref != pinned_request.tenant_ref or
                actor.session_ref != pinned_request.session_ref):
            raise PreparationAuthorizationRejected("Authenticated workflow scope differs from request.")

        grant = _grant_copy(_call(
            self._operations["authorize_preparation"], allow_denial=True,
            actor=_actor_copy(actor, maximum), request=_request_copy(pinned_request, maximum),
        ), maximum)
        if grant.actor_ref != actor.actor_ref or grant.request != pinned_request:
            raise PreparationAuthorizationRejected("Requested preparation source is not authorized.")

        approved = _approved_copy(_call(
            self._operations["resolve_approved_policy"], grant=_grant_copy(grant, maximum),
        ), maximum)
        if (approved.admission_policy_identity != grant.admission_policy_identity or
                approved.policy_revision != grant.policy_revision or
                approved.policy.admission_policy_identity != approved.admission_policy_identity):
            raise PreparationAuthorizationRejected("Original approved policy cannot be established.")

        resolved = _revisioned_copy(_call(
            self._operations["resolve_revisioned_preparation"], grant=_grant_copy(grant, maximum),
        ), maximum)
        source = resolved.source
        if resolved.source_revision != grant.source_revision:
            raise PreparationAuthorizationRejected("Source authority revision has changed.")
        # Canonicalize backend metadata *before* equality; otherwise a foreign
        # object or str subclass can spoof comparisons and be laundered below.
        source_tenant = _id(_attr(source, "tenant_ref"), maximum)
        source_session = _id(_attr(source, "session_ref"), maximum)
        source_artifact = _id(_attr(source, "source_artifact_ref"), maximum)
        if (source_tenant != pinned_request.tenant_ref or
                source_session != pinned_request.session_ref or
                source_artifact != grant.source_artifact_ref):
            raise PreparationAuthorizationRejected("Protected source ownership does not match authorization.")
        current_policy = _policy_copy(_attr(source, "admission_policy"), maximum)
        if current_policy != approved.policy:
            raise PreparationAuthorizationRejected("Source policy differs from independently approved values.")

        # PRE validates authority before opening this protected reader. PRE
        # normalizes stream failures; separately retain explicit revocations.
        reader_denied = False
        reader_invalid = False

        def mark_denied() -> None:
            nonlocal reader_denied
            reader_denied = True

        def open_authorized():
            nonlocal reader_invalid
            # Source-controlled evidence openers are never used.
            try:
                reader = _call(self._operations["open_authorized_evidence"],
                               allow_denial=True, grant=_grant_copy(grant, maximum))
            except PreparationAuthorizationRejected:
                mark_denied()
                raise
            # Reject unsupported declarations before transferring reader ownership.
            # Do not call read/close on a rejected handle: the storage adapter
            # remains responsible for its physical cleanup.
            try:
                if reader is None:
                    raise PreparationAuthorityContractError("Missing protected binary reader.")
                read = _validated_reader_method(reader, "read")
                close = _validated_reader_method(reader, "close")
            except (PreparationAuthorityContractError, AttributeError, TypeError, ValueError):
                # PRE normalizes opener faults; preserve malformed reader taxonomy.
                reader_invalid = True
                raise PreparationAuthorityContractError(
                    "Protected evidence authority returned an invalid binary reader."
                ) from None
            return _RevocationAwareStream(read, close, mark_denied)

        pinned_source = PreparationSourceSnapshot(
            tenant_ref=pinned_request.tenant_ref,
            session_ref=pinned_request.session_ref,
            context=_attr(source, "context"),
            paper_authority=_attr(source, "paper_authority"),
            question_authority=_attr(source, "question_authority"),
            admission_policy=approved.policy,
            source_artifact_ref=grant.source_artifact_ref,
            open_evidence=open_authorized,
        )
        unavailable = None
        try:
            prepared = prepare_from_trusted_source(
                request=_request_copy(pinned_request, maximum),
                source=_CapturedSource(pinned_source),
                max_identifier_characters=maximum,
            )
        except (PreparationSourceUnavailable, PreparationResourceLimitError) as caught:
            unavailable = caught
        if reader_denied:
            raise PreparationAuthorizationRejected("Protected evidence access was denied.") from None
        if reader_invalid:
            raise PreparationAuthorityContractError(
                "Protected evidence authority returned an invalid binary reader."
            ) from None
        if unavailable is not None:
            raise unavailable from None
        return AuthorizedPreparedQuestion(
            prepared=prepared,
            custody=PreparationCustody(
                actor_ref=actor.actor_ref, tenant_ref=actor.tenant_ref,
                session_ref=actor.session_ref,
                source_artifact_ref=grant.source_artifact_ref,
                source_revision=grant.source_revision,
                admission_policy_identity=approved.admission_policy_identity,
                policy_revision=approved.policy_revision,
            ),
        )
