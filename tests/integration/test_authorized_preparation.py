"""Independent identity, source authorization and approved-policy custody."""
from dataclasses import replace
import io

import pytest

from grading.integration.authorized_preparation import (
    AuthenticatedActor, PreparationAccessGrant, ApprovedAdmissionPolicyRecord,
    RevisionedPreparationRecord, ProductionPreparationComposer,
    PreparationAuthorizationRejected, PreparationAuthorityUnavailable,
    PreparationAuthorityContractError,
)
from tests.integration.test_trusted_preparation import _setup, _payload
from grading.integration.trusted_preparation import PreparationScopeRejected


class FixturePorts:
    def __init__(self, request, source):
        self.request = request
        self.source = source
        self.events = []
        self.actor = AuthenticatedActor("ACTOR-1", request.tenant_ref, request.session_ref)
        self.grant = PreparationAccessGrant(
            actor_ref="ACTOR-1", request=request, source_artifact_ref="ARTIFACT-1",
            source_revision="SOURCE-REV-1", admission_policy_identity=source.snapshot.admission_policy.admission_policy_identity,
            policy_revision="POLICY-REV-1",
        )
        self.policy = ApprovedAdmissionPolicyRecord(
            admission_policy_identity=self.grant.admission_policy_identity,
            policy_revision="POLICY-REV-1", policy=source.snapshot.admission_policy,
        )
        self.resolved = RevisionedPreparationRecord(
            source_revision="SOURCE-REV-1", source=source.snapshot,
        )

    def current_actor(self):
        self.events.append("identity")
        return self.actor

    def authorize_preparation(self, *, actor, request):
        self.events.append("authorize")
        return self.grant

    def resolve_approved_policy(self, *, grant):
        self.events.append("policy")
        return self.policy

    def resolve_revisioned_preparation(self, *, grant):
        self.events.append("source")
        return self.resolved

    def open_authorized_evidence(self, *, grant):
        self.events.append("open")
        return io.BytesIO(self.source.payload)


def _inputs(payload=None):
    request, source = _setup(payload)
    ports = FixturePorts(request, source)
    ports.resolved = replace(ports.resolved, source=source.snapshot)
    return request, source, ports



def _compose(ports):
    return ProductionPreparationComposer(
        identity=ports, access=ports, approved_policies=ports, sources=ports,
        evidence=ports, max_identifier_characters=64,
    )


def test_authorized_positive_path_carries_only_scoped_custody():
    request, source, ports = _inputs()
    output = _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]
    assert output.prepared.bound.context.submission_ref == request.submission_ref
    assert output.custody.source_revision == "SOURCE-REV-1"
    assert output.custody.policy_revision == "POLICY-REV-1"
    assert output.custody.actor_ref == "ACTOR-1"
    assert output.custody.admission_policy_identity == ports.grant.admission_policy_identity
    assert "execution" not in repr(output).lower()


def test_foreign_tenant_identity_prevents_all_authority_and_evidence_io():
    request, source, ports = _inputs()
    ports.actor = replace(ports.actor, tenant_ref="OTHER-TENANT")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity"]


def test_foreign_session_identity_prevents_io():
    request, source, ports = _inputs()
    ports.actor = replace(ports.actor, session_ref="OTHER-SESSION")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity"]


def test_unauthorized_access_is_denied_before_policy_and_source():
    request, source, ports = _inputs()
    def deny(*, actor, request):
        ports.events.append("authorize")
        raise RuntimeError("PRIVATE_CREDENTIAL_FROM_BACKEND")
    ports.authorize_preparation = deny
    with pytest.raises(PreparationAuthorityUnavailable) as failure:
        _compose(ports).prepare(request=request)
    assert "PRIVATE_CREDENTIAL_FROM_BACKEND" not in str(failure.value)
    assert ports.events == ["identity", "authorize"]


def test_wrong_authorized_request_prevents_policy_and_evidence():
    request, source, ports = _inputs()
    ports.grant = replace(ports.grant, request=replace(request, submission_ref="OTHER-SUBMISSION"))
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize"]


def test_missing_policy_fails_before_source_resolution_and_open():
    request, source, ports = _inputs()
    ports.resolve_approved_policy = lambda *, grant: None
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize"]


def test_original_five_question_policy_inflation_is_rejected_before_open():
    request, source, ports = _inputs(_payload(6))
    approved_max = ports.policy.policy.max_questions
    assert approved_max < 6
    ports.resolved = replace(ports.resolved, source=replace(
        ports.resolved.source, admission_policy=replace(ports.resolved.source.admission_policy, max_questions=6),
    ))
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_changed_policy_version_fails_before_source_resolution():
    request, source, ports = _inputs()
    ports.policy = replace(ports.policy, policy_revision="UNAPPROVED-REV")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy"]


def test_wrong_original_policy_identity_fails_before_source_resolution():
    request, source, ports = _inputs()
    ports.policy = replace(ports.policy, admission_policy_identity="OTHER-POLICY")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy"]


def test_inconsistent_source_revision_fails_before_evidence_open():
    request, source, ports = _inputs()
    ports.resolved = replace(ports.resolved, source_revision="SOURCE-REV-2")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_different_artifact_fails_before_evidence_open():
    request, source, ports = _inputs()
    ports.resolved = replace(ports.resolved, source=replace(ports.resolved.source, source_artifact_ref="OTHER-ARTIFACT"))
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_trusted_resolver_must_not_supply_foreign_tenant_evidence():
    request, source, ports = _inputs()
    ports.resolved = replace(ports.resolved, source=replace(ports.resolved.source, tenant_ref="OTHER-TENANT"))
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_unconfigured_identity_or_policy_port_is_not_authorized():
    request, source, ports = _inputs()
    with pytest.raises(PreparationAuthorityContractError):
        ProductionPreparationComposer(identity=None, access=ports, approved_policies=ports, sources=ports,
                                      evidence=ports, max_identifier_characters=64)
    with pytest.raises(PreparationAuthorityContractError):
        ProductionPreparationComposer(identity=ports, access=ports, approved_policies=None, sources=ports,
                                      evidence=ports, max_identifier_characters=64)
    assert ports.events == []


def test_callbacks_cannot_change_the_pinned_request_or_grant():
    request, source, ports = _inputs()
    def mutate_access(*, actor, request):
        ports.events.append("authorize")
        object.__setattr__(request, "submission_ref", "OTHER-SUBMISSION")
        object.__setattr__(actor, "tenant_ref", "OTHER-TENANT")
        return ports.grant
    ports.authorize_preparation = mutate_access
    def mutate_policy(*, grant):
        ports.events.append("policy")
        object.__setattr__(grant, "source_revision", "OTHER-REV")
        return ports.policy
    ports.resolve_approved_policy = mutate_policy
    result = _compose(ports).prepare(request=request)
    assert result.prepared.request.submission_ref == request.submission_ref
    assert result.custody.source_revision == "SOURCE-REV-1"
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]



def test_untrusted_mutation_after_policy_resolution_does_not_expand_pre_policy():
    request, source, ports = _inputs(_payload(6))
    original = ports.resolved.source.admission_policy
    def inflate_source(*, grant):
        ports.events.append("source")
        object.__setattr__(original, "max_questions", 6)
        return ports.resolved
    ports.resolve_revisioned_preparation = inflate_source
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_expected_auth_error_does_not_echo_original_private_traceback():
    import traceback
    request, source, ports = _inputs()
    secret = "STUDENT_PRIVATE_AUTH_TOKEN"
    def failed_policy(*, grant):
        ports.events.append("policy")
        raise RuntimeError(secret)
    ports.resolve_approved_policy = failed_policy
    with pytest.raises(PreparationAuthorityUnavailable) as info:
        _compose(ports).prepare(request=request)
    assert secret not in "".join(traceback.format_exception(info.value))


def test_source_supplied_unauthorized_opener_is_never_invoked():
    request, source, ports = _inputs()
    def trap():
        raise AssertionError("Untrusted source opener used")
    ports.resolved = replace(ports.resolved, source=replace(ports.resolved.source, open_evidence=trap))
    _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]


def test_open_receives_exact_versioned_grant_after_all_checks():
    request, source, ports = _inputs()
    observed = []
    def guarded_read(*, grant):
        ports.events.append("open")
        observed.append((grant.request.submission_ref, grant.source_revision, grant.policy_revision))
        return io.BytesIO(source.payload)
    ports.open_authorized_evidence = guarded_read
    _compose(ports).prepare(request=request)
    assert observed == [("SUB-1", "SOURCE-REV-1", "POLICY-REV-1")]


def test_missing_protected_reader_port_fails_closed_before_any_callback():
    request, source, ports = _inputs()
    with pytest.raises(PreparationAuthorityContractError):
        ProductionPreparationComposer(identity=ports, access=ports, approved_policies=ports,
                                      sources=ports, evidence=None, max_identifier_characters=64)
    assert ports.events == []


def test_mismatched_actor_in_grant_cannot_authorize_source():
    request, source, ports = _inputs()
    ports.grant = replace(ports.grant, actor_ref="OTHER-ACTOR")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize"]


def test_source_context_changed_without_revision_update_is_stopped_by_frozen_pre():
    request, source, ports = _inputs()
    ports.resolved = replace(ports.resolved, source=replace(
        ports.resolved.source,
        context=replace(ports.resolved.source.context, submission_ref="UNRELATED-SUBMISSION"),
    ))
    with pytest.raises(PreparationScopeRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_approved_policy_record_identity_must_match_its_policy():
    request, source, ports = _inputs()
    ports.policy = replace(ports.policy, policy=replace(
        ports.policy.policy, admission_policy_identity="FOREIGN-IDENTITY",
    ))
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy"]


def test_excessively_long_request_rejected_before_identity_lookup():
    request, source, ports = _inputs()
    object.__setattr__(request, "tenant_ref", "x" * 65)
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert ports.events == []


def test_original_request_change_during_backend_authorization_is_not_accepted():
    request, source, ports = _inputs()
    ports.grant = replace(ports.grant, request=replace(request))
    def alter_original(*, actor, request):
        ports.events.append("authorize")
        object.__setattr__(ports.request, "tenant_ref", "UNRELATED-TENANT")
        return ports.grant
    ports.authorize_preparation = alter_original
    response = _compose(ports).prepare(request=request)
    assert response.prepared.request.tenant_ref == "TENANT-1"
    assert response.custody.tenant_ref == "TENANT-1"
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]


def test_no_private_info_in_ambient_backend_error_traceback():
    import traceback
    request, source, ports = _inputs()
    secret = "PRIVATE_AMBIENT_SECRET_169"
    def fail(*, actor, request):
        ports.events.append("authorize")
        raise RuntimeError("PRIVATE_BACKEND_SECRET_187")
    ports.authorize_preparation = fail
    try:
        raise RuntimeError(secret)
    except RuntimeError:
        with pytest.raises(PreparationAuthorityUnavailable) as failure:
            _compose(ports).prepare(request=request)
    formatted = "".join(traceback.format_exception(failure.value))
    assert "PRIVATE_BACKEND_SECRET_187" not in formatted
    assert secret not in formatted


def test_ambient_private_exception_cannot_escape_with_rejected_scope():
    import traceback
    request, source, ports = _inputs()
    ports.actor = replace(ports.actor, tenant_ref="WRONG-TENANT")
    secret = "PRIVATE_STUDENT_CONTENT_IN_AMBIENT_HANDLER"
    try:
        raise RuntimeError(secret)
    except RuntimeError:
        with pytest.raises(PreparationAuthorizationRejected) as failure:
            _compose(ports).prepare(request=request)
    assert secret not in "".join(traceback.format_exception(failure.value))
    assert ports.events == ["identity"]


# Hostile boundary tests: canonical identity comparison, typed backend failures,
# and private traceback handling must not depend on Python optimization mode.
import traceback
from grading.integration.trusted_preparation import PreparationSourceUnavailable


class _SpoofedEqual:
    def __eq__(self, other):
        return True
    def __ne__(self, other):
        return False


class _SpoofedString(str):
    def __eq__(self, other):
        return True
    def __ne__(self, other):
        return False


class _RaisingCompare:
    def __eq__(self, other):
        raise RuntimeError("PRIVATE_BACKEND_IDENTIFIER")
    def __ne__(self, other):
        raise RuntimeError("PRIVATE_BACKEND_IDENTIFIER")


@pytest.mark.parametrize("field", ["tenant_ref", "session_ref", "source_artifact_ref"])
@pytest.mark.parametrize("value", [_SpoofedEqual(), _SpoofedString("FORGED"), _RaisingCompare()], ids=["object", "str-subclass", "raises"])
def test_noncanonical_backend_source_identity_never_reaches_protected_reader(field, value):
    request, _, ports = _inputs()
    object.__setattr__(ports.resolved.source, field, value)
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


@pytest.mark.parametrize("version", [0, -1, "INVALID", None, True, 1.0, [], {}])
def test_invalid_scoring_spec_version_is_sanitized_before_backend_calls(version):
    request, _, ports = _inputs()
    object.__setattr__(request.grading_spec_ref, "version", version)
    try:
        raise RuntimeError("PRIVATE_CALLER_EXCEPTION")
    except RuntimeError:
        with pytest.raises(PreparationAuthorityContractError) as caught:
            _compose(ports).prepare(request=request)
    assert ports.events == []
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_CALLER_EXCEPTION" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("operation,expected_events", [
    ("current_actor", []),
    ("authorize_preparation", ["identity"]),
    ("resolve_approved_policy", ["identity", "authorize"]),
    ("resolve_revisioned_preparation", ["identity", "authorize", "policy"]),
    ("open_authorized_evidence", ["identity", "authorize", "policy", "source"]),
])
def test_backend_method_resolution_failure_is_sanitized(operation, expected_events):
    request, source, _ = _inputs()
    class DynamicFixture(FixturePorts):
        bad_operation = None
        def __getattribute__(self, name):
            if name == object.__getattribute__(self, "bad_operation"):
                raise RuntimeError("PRIVATE_BACKEND_LOOKUP")
            return super().__getattribute__(name)
    ports = DynamicFixture(request, source)
    composer = _compose(ports)
    ports.bad_operation = operation
    # The validated class method is already captured: later dynamic lookup
    # must not execute the hostile __getattribute__ interceptor.
    result = composer.prepare(request=request)
    assert result.custody.actor_ref == "ACTOR-1"
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]


def test_explicit_authorization_denial_is_not_backend_unavailability():
    request, _, ports = _inputs()
    def denied(*, actor, request):
        ports.events.append("authorize")
        raise PreparationAuthorizationRejected("PRIVATE_GRANT_DIAGNOSTIC")
    ports.authorize_preparation = denied
    with pytest.raises(PreparationAuthorizationRejected) as caught:
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize"]
    assert "PRIVATE_GRANT_DIAGNOSTIC" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_approved_source_identity_cannot_be_laundered_to_expected_metadata():
    request, _, ports = _inputs()
    object.__setattr__(ports.resolved.source, "source_artifact_ref", "FOREIGN")
    with pytest.raises(PreparationAuthorizationRejected):
        _compose(ports).prepare(request=request)
    assert "open" not in ports.events


@pytest.mark.parametrize("version", [0, -1, "INVALID", None, True, 1.0, [], {}])
def test_malformed_backend_grant_spec_has_typed_private_failure(version):
    from grading.contracts.paper_aggregation import GradingSpecRef
    request, _, ports = _inputs()
    new_spec = GradingSpecRef(id=request.grading_spec_ref.id, version=request.grading_spec_ref.version)
    grant_request = replace(request, grading_spec_ref=new_spec)
    object.__setattr__(new_spec, "version", version)
    ports.grant = replace(ports.grant, request=grant_request)
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize"]


@pytest.mark.parametrize("operation,expected_events", [
    ("current_actor", ["identity"]),
    ("authorize_preparation", ["identity", "authorize"]),
    ("resolve_approved_policy", ["identity", "authorize", "policy"]),
    ("resolve_revisioned_preparation", ["identity", "authorize", "policy", "source"]),
    ("open_authorized_evidence", ["identity", "authorize", "policy", "source", "open"]),
])
def test_backend_invocation_faults_do_not_leak_private_diagnostics(operation, expected_events):
    request, _, ports = _inputs()
    original = getattr(ports, operation)
    def fail(*args, **kwargs):
        original_name = {
            "current_actor": "identity", "authorize_preparation": "authorize",
            "resolve_approved_policy": "policy", "resolve_revisioned_preparation": "source",
            "open_authorized_evidence": "open",
        }[operation]
        ports.events.append(original_name)
        raise RuntimeError("PRIVATE_BACKEND_INVOCATION_SECRET")
    setattr(ports, operation, fail)
    kind = PreparationSourceUnavailable if operation == "open_authorized_evidence" else PreparationAuthorityUnavailable
    with pytest.raises(kind) as caught:
        _compose(ports).prepare(request=request)
    assert ports.events == expected_events
    assert "PRIVATE_BACKEND_INVOCATION_SECRET" not in "".join(traceback.format_exception(caught.value))


# Constructor must never resolve a backend descriptor or expose ambient secrets.
@pytest.mark.parametrize("operation", [
    "current_actor", "authorize_preparation", "resolve_approved_policy",
    "resolve_revisioned_preparation", "open_authorized_evidence",
])
def test_constructor_defers_backend_properties_until_authorized_operation(operation):
    request, source, ports = _inputs()
    class LazyPort:
        def __init__(self):
            self.events = []
    # Deliberately put a property on the class; evaluating it would be an effect.
    def lookup(self):
        self.events.append("premature")
        raise RuntimeError("PRIVATE_DESCRIPTOR_DIAGNOSTIC")
    setattr(LazyPort, operation, property(lookup))
    lazy = LazyPort()
    configured = dict(identity=ports, access=ports, approved_policies=ports,
                      sources=ports, evidence=ports, max_identifier_characters=64)
    configured[{
        "current_actor": "identity", "authorize_preparation": "access",
        "resolve_approved_policy": "approved_policies",
        "resolve_revisioned_preparation": "sources",
        "open_authorized_evidence": "evidence",
    }[operation]] = lazy
    with pytest.raises(PreparationAuthorityContractError) as failure:
        ProductionPreparationComposer(**configured)
    assert lazy.events == []
    assert failure.value.__context__ is None and failure.value.__cause__ is None
    assert "PRIVATE_DESCRIPTOR_DIAGNOSTIC" not in str(failure.value)


@pytest.mark.parametrize("operation", [
    "current_actor", "authorize_preparation", "resolve_approved_policy",
    "resolve_revisioned_preparation", "open_authorized_evidence",
])
def test_constructor_rejects_noncallable_methods_without_touching_other_ports(operation):
    request, _, ports = _inputs()
    class InvalidPort:
        pass
    setattr(InvalidPort, operation, 42)
    configured = dict(identity=ports, access=ports, approved_policies=ports,
                      sources=ports, evidence=ports, max_identifier_characters=64)
    configured[{
        "current_actor": "identity", "authorize_preparation": "access",
        "resolve_approved_policy": "approved_policies",
        "resolve_revisioned_preparation": "sources",
        "open_authorized_evidence": "evidence",
    }[operation]] = InvalidPort()
    with pytest.raises(PreparationAuthorityContractError):
        ProductionPreparationComposer(**configured)
    assert ports.events == []


def test_constructor_ambient_private_error_is_not_chained():
    import traceback
    request, _, ports = _inputs()
    try:
        raise ValueError("PRIVATE_AMBIENT_STUDENT_CONTENT")
    except ValueError:
        with pytest.raises(PreparationAuthorityContractError) as caught:
            ProductionPreparationComposer(identity=None, access=ports,
                approved_policies=ports, sources=ports, evidence=ports,
                max_identifier_characters=64)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_AMBIENT_STUDENT_CONTENT" not in "".join(traceback.format_exception(caught.value))
    assert ports.events == []


def test_missing_final_port_does_not_trigger_earlier_properties():
    request, _, ports = _inputs()
    class ActiveProperty:
        events = []
        @property
        def current_actor(self):
            self.events.append("called")
            return lambda: object()
    identity = ActiveProperty()
    with pytest.raises(PreparationAuthorityContractError):
        ProductionPreparationComposer(identity=identity, access=ports,
            approved_policies=ports, sources=ports, evidence=None,
            max_identifier_characters=64)
    assert identity.events == [] and ports.events == []


@pytest.mark.parametrize("reader_exception, expected_type", [
    (PreparationAuthorizationRejected("PRIVATE_REVOKED_GRANT"), PreparationAuthorizationRejected),
    (OSError("PRIVATE_READER_OUTAGE"), PreparationSourceUnavailable),
])
def test_privileged_read_rejection_is_not_retryable_unavailability(reader_exception, expected_type):
    import traceback
    request, _, ports = _inputs()
    def reject(*, grant):
        ports.events.append("open")
        raise reader_exception
    ports.open_authorized_evidence = reject
    with pytest.raises(expected_type) as failure:
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]
    assert failure.value.__cause__ is None and failure.value.__context__ is None
    formatted = "".join(traceback.format_exception(failure.value))
    assert "PRIVATE_REVOKED_GRANT" not in formatted
    assert "PRIVATE_READER_OUTAGE" not in formatted


@pytest.mark.parametrize("stage", ["read", "close"])
def test_revocation_during_privileged_stream_is_a_denial_not_outage(stage):
    import traceback
    request, _, ports = _inputs()
    class RevokedStream:
        def read(self, amount):
            if stage == "read":
                raise PreparationAuthorizationRejected("PRIVATE_MIDSTREAM_REVOCATION")
            return b""
        def close(self):
            if stage == "close":
                raise PreparationAuthorizationRejected("PRIVATE_CLOSE_REVOCATION")
    def open_revoking(*, grant):
        ports.events.append("open")
        return RevokedStream()
    ports.open_authorized_evidence = open_revoking
    with pytest.raises(PreparationAuthorizationRejected) as caught:
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert "PRIVATE_" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("operation,expected_events", [
    ("current_actor", ["identity"]),
    ("resolve_approved_policy", ["identity", "authorize", "policy"]),
    ("resolve_revisioned_preparation", ["identity", "authorize", "policy", "source"]),
])
def test_non_authorization_ports_cannot_rename_failures_as_access_denials(operation, expected_events):
    request, _, ports = _inputs()
    event = {"current_actor": "identity", "resolve_approved_policy": "policy",
             "resolve_revisioned_preparation": "source"}[operation]
    def unexpected_denial(*args, **kwargs):
        ports.events.append(event)
        raise PreparationAuthorizationRejected("PRIVATE_NOT_ACCESS_AUTHORITY")
    setattr(ports, operation, unexpected_denial)
    with pytest.raises(PreparationAuthorityUnavailable) as caught:
        _compose(ports).prepare(request=request)
    assert ports.events == expected_events
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize("operation,port_name", [
    ("current_actor", "identity"),
    ("authorize_preparation", "access"),
    ("resolve_approved_policy", "approved_policies"),
    ("resolve_revisioned_preparation", "sources"),
    ("open_authorized_evidence", "evidence"),
])
def test_constructor_faulting_port_getter_never_leaks_ambient_or_backend_data(operation, port_name):
    import traceback
    request, _, ports = _inputs()
    class BadPort:
        @property
        def protected(self):
            raise RuntimeError("PRIVATE_BACKEND_PROPERTY_DIAGNOSTIC")
    setattr(BadPort, operation, BadPort.protected)
    kwargs = dict(identity=ports, access=ports, approved_policies=ports,
                  sources=ports, evidence=ports, max_identifier_characters=64)
    kwargs[port_name] = BadPort()
    try:
        raise ValueError("PRIVATE_AMBIENT_SUBMISSION")
    except ValueError:
        with pytest.raises(PreparationAuthorityContractError) as caught:
            ProductionPreparationComposer(**kwargs)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_" not in "".join(traceback.format_exception(caught.value))
    assert ports.events == []


def test_revocation_on_close_remains_denial_when_source_also_exceeds_byte_budget():
    request, _, ports = _inputs()
    class OversizeAndRevoked:
        def read(self, amount):
            return b"X" * amount
        def close(self):
            raise PreparationAuthorizationRejected("PRIVATE_REVOKED_ON_CLOSE")
    def open_reader(*, grant):
        ports.events.append("open")
        return OversizeAndRevoked()
    ports.open_authorized_evidence = open_reader
    with pytest.raises(PreparationAuthorizationRejected) as caught:
        _compose(ports).prepare(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "PRIVATE_REVOKED_ON_CLOSE" not in str(caught.value)


# Final-boundary hostile controls: declared methods must not be arbitrary descriptors.
@pytest.mark.parametrize("operation,port_name", [
    ("current_actor", "identity"),
    ("authorize_preparation", "access"),
    ("resolve_approved_policy", "approved_policies"),
    ("resolve_revisioned_preparation", "sources"),
    ("open_authorized_evidence", "evidence"),
])
def test_constructor_rejects_callable_descriptor_without_executing_getter(operation, port_name):
    request, _, ports = _inputs()
    events = []

    class CallableDescriptor:
        def __call__(self, *args, **kwargs):
            events.append("called")
            return object()

        def __get__(self, instance, owner):
            events.append("resolved")
            return lambda **kwargs: object()

    class SpecialPort:
        pass

    setattr(SpecialPort, operation, CallableDescriptor())
    configured = dict(identity=ports, access=ports, approved_policies=ports,
                      sources=ports, evidence=ports, max_identifier_characters=64)
    configured[port_name] = SpecialPort()
    with pytest.raises(PreparationAuthorityContractError):
        ProductionPreparationComposer(**configured)
    assert events == []
    assert ports.events == []


def test_source_mutation_at_evidence_open_cannot_change_pinned_authority():
    request, _, ports = _inputs()
    source = ports.resolved.source
    original_submission = source.context.submission_ref
    original_question = source.question_authority.question_id
    original_max_questions = source.admission_policy.max_questions
    original_reader = ports.open_authorized_evidence

    def mutate_then_open(*, grant):
        # Happens after PRE must have completed its nested-authority snapshot.
        object.__setattr__(source.context, "submission_ref", "SUBSTITUTED")
        object.__setattr__(source.question_authority, "question_id", "FOREIGN-Q")
        object.__setattr__(source.admission_policy, "max_questions", original_max_questions + 1)
        return original_reader(grant=grant)

    ports.open_authorized_evidence = mutate_then_open
    prepared = _compose(ports).prepare(request=request)
    assert prepared.prepared.bound.context.submission_ref == original_submission
    assert prepared.prepared.bound.question_authority.question_id == original_question
    assert prepared.prepared.bound.admitted_evidence.effective_policy_snapshot.max_questions == original_max_questions


def test_constructor_accepts_plain_static_method_without_premature_invocation():
    request, source, ports = _inputs()
    actor = ports.actor
    observed = []

    class StaticIdentityPort:
        @staticmethod
        def current_actor():
            observed.append("identity")
            return actor

    composer = ProductionPreparationComposer(
        identity=StaticIdentityPort(), access=ports,
        approved_policies=ports, sources=ports, evidence=ports,
        max_identifier_characters=64,
    )
    assert observed == [] and ports.events == []
    result = composer.prepare(request=request)
    assert observed == ["identity"]
    assert result.custody.tenant_ref == request.tenant_ref
    assert ports.events == ["authorize", "policy", "source", "open"]

# Outward-facing PRE failures must remain private even inside an ambient handler.
@pytest.mark.parametrize("mode, expected", [
    ("read_error", "PreparationSourceUnavailable"),
    ("close_error", "PreparationSourceUnavailable"),
    ("raw_limit", "PreparationResourceLimitError"),
    ("bad_wire", "NormalizedEvidenceMalformedPayloadError"),
    ("wrong_scope", "PreparationScopeRejected"),
    ("bad_paper", "PreparationSourceContractError"),
])
def test_inherited_expected_pre_failures_have_no_private_exception_chain(mode, expected):
    import traceback
    from grading.integration import trusted_preparation as pre
    from grading.integration.evidence_ingress import NormalizedEvidenceMalformedPayloadError

    types = {
        "PreparationSourceUnavailable": pre.PreparationSourceUnavailable,
        "PreparationResourceLimitError": pre.PreparationResourceLimitError,
        "NormalizedEvidenceMalformedPayloadError": NormalizedEvidenceMalformedPayloadError,
        "PreparationScopeRejected": pre.PreparationScopeRejected,
        "PreparationSourceContractError": pre.PreparationSourceContractError,
    }
    request, _, ports = _inputs()
    if mode == "read_error":
        class Reader:
            def read(self, size):
                raise RuntimeError("SECRET_READ_FAILURE")
            def close(self):
                pass
        ports.open_authorized_evidence = lambda *, grant: Reader()
    elif mode == "close_error":
        class Reader:
            def read(self, size):
                return b""
            def close(self):
                raise RuntimeError("SECRET_CLOSE_FAILURE")
        ports.open_authorized_evidence = lambda *, grant: Reader()
    elif mode == "raw_limit":
        class Reader:
            def read(self, size):
                return b"X" * (size + 1)
            def close(self):
                pass
        ports.open_authorized_evidence = lambda *, grant: Reader()
    elif mode == "bad_wire":
        ports.open_authorized_evidence = lambda *, grant: io.BytesIO(b"NOT JSON")
    elif mode == "wrong_scope":
        original = ports.resolved.source
        ports.resolved = replace(ports.resolved, source=replace(
            original, context=replace(original.context, submission_ref="OTHER-SUBMISSION")))
    else:
        ports.resolved = replace(ports.resolved, source=replace(
            ports.resolved.source, paper_authority=object()))

    try:
        raise ValueError("SENSITIVE_STUDENT_AMBIENT_CONTENT")
    except ValueError:
        with pytest.raises(types[expected]) as observed:
            _compose(ports).prepare(request=request)
    failure = observed.value
    assert failure.__cause__ is None and failure.__context__ is None
    assert "SENSITIVE_STUDENT_AMBIENT_CONTENT" not in "".join(traceback.format_exception(failure))
    assert "SECRET_READ_FAILURE" not in "".join(traceback.format_exception(failure))
    assert "SECRET_CLOSE_FAILURE" not in "".join(traceback.format_exception(failure))


@pytest.mark.parametrize("invalid_reader", [None, object(), b"not a reader"])
def test_malformed_authorized_reader_is_typed_without_reading(invalid_reader):
    request, _, ports = _inputs()
    ports.open_authorized_evidence = lambda *, grant: invalid_reader
    with pytest.raises(PreparationAuthorityContractError) as caught:
        _compose(ports).prepare(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_reader_descriptor_is_not_executed_during_contract_validation():
    request, _, ports = _inputs()
    events = []
    class Reader:
        @property
        def read(self):
            events.append("executed")
            raise RuntimeError("PRIVATE_READER_DESCRIPTOR")
        def close(self):
            events.append("closed")
    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert not events


def test_original_source_drift_before_pre_reconstruction_is_rejected(monkeypatch):
    from grading.integration import authorized_preparation as authorized
    request, _, ports = _inputs()
    original = authorized._CapturedSource.resolve_preparation
    def drift(self, *, request):
        object.__setattr__(self.snapshot.context, "submission_ref", "CROSS-SUBMISSION")
        return original(self, request=request)
    monkeypatch.setattr(authorized._CapturedSource, "resolve_preparation", drift)
    with pytest.raises(PreparationScopeRejected):
        _compose(ports).prepare(request=request)
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_replaced_backend_method_after_configuration_cannot_change_captured_operation():
    request, _, ports = _inputs()
    composer = _compose(ports)
    def fail():
        ports.events.append("forged-identity")
        raise RuntimeError("PRIVATE_LATE_METHOD_REPLACEMENT")
    ports.current_actor = fail
    result = composer.prepare(request=request)
    assert result.custody.actor_ref == "ACTOR-1"
    assert ports.events == ["identity", "authorize", "policy", "source", "open"]


def test_revocation_on_close_precedes_malformed_evidence_rejection():
    request, _, ports = _inputs()
    class MalformedThenRevoked:
        def __init__(self):
            self.sent = False
        def read(self, size):
            if self.sent:
                return b""
            self.sent = True
            return b"NOT JSON"
        def close(self):
            raise PreparationAuthorizationRejected("PRIVATE_REVOCATION")
    ports.open_authorized_evidence = lambda *, grant: MalformedThenRevoked()
    with pytest.raises(PreparationAuthorizationRejected) as caught:
        _compose(ports).prepare(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_callable_reader_descriptor_is_rejected_without_execution():
    request, _, ports = _inputs()
    events = []

    class DeceptiveDescriptor:
        def __call__(self, *args):
            events.append("called")

        def __get__(self, instance, owner):
            events.append("descriptor_get")
            return None

    class Reader:
        read = DeceptiveDescriptor()

        def close(self):
            events.append("closed")

    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError) as caught:
        _compose(ports).prepare(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert events == []
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_callable_close_descriptor_is_rejected_without_execution():
    request, _, ports = _inputs()
    events = []

    class DeceptiveDescriptor:
        def __call__(self, *args):
            events.append("called")

        def __get__(self, instance, owner):
            events.append("descriptor_get")
            return None

    class Reader:
        def read(self, size):
            return b""

        close = DeceptiveDescriptor()

    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError) as caught:
        _compose(ports).prepare(request=request)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert events == []
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_regular_python_binary_reader_is_supported_and_closed():
    request, source, ports = _inputs()
    events = []

    class Reader:
        def __init__(self):
            self.stream = io.BytesIO(source.payload)

        def read(self, size):
            return self.stream.read(size)

        def close(self):
            events.append("closed")
            self.stream.close()

    ports.open_authorized_evidence = lambda *, grant: Reader()
    result = _compose(ports).prepare(request=request)
    assert result.prepared.bound.context.submission_ref == request.submission_ref
    assert events == ["closed"]


def test_standard_buffered_binary_file_is_supported_and_closed():
    import os
    import tempfile

    request, source, ports = _inputs()
    opened = []
    # tempfile.TemporaryFile() returns a dynamically delegated wrapper on
    # Windows; open() creates an actual buffered binary stream on both OSes.
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "evidence.bin")

        def make_reader(*, grant):
            file = open(path, "w+b")
            opened.append(file)
            file.write(source.payload)
            file.seek(0)
            return file

        ports.open_authorized_evidence = make_reader
        try:
            result = _compose(ports).prepare(request=request)
            assert result.prepared.bound.context.submission_ref == request.submission_ref
            assert len(opened) == 1 and opened[0].closed
        finally:
            for file in opened:
                file.close()


def test_dynamic_temporary_file_wrapper_is_rejected_with_adapter_cleanup():
    import tempfile

    request, source, ports = _inputs()
    opened = []

    def make_reader(*, grant):
        wrapper = tempfile.NamedTemporaryFile(mode="w+b")
        opened.append(wrapper)
        wrapper.write(source.payload)
        wrapper.seek(0)
        return wrapper

    ports.open_authorized_evidence = make_reader
    try:
        with pytest.raises(PreparationAuthorityContractError):
            _compose(ports).prepare(request=request)
        assert len(opened) == 1 and not opened[0].closed
        # The composer must not attempt delegated close() on rejected handles.
    finally:
        for wrapper in opened:
            wrapper.close()


def test_borrowed_builtin_stream_descriptor_is_rejected_before_reading():
    request, _, ports = _inputs()
    events = []

    class Reader:
        read = io.BytesIO.read  # Built-in descriptor cannot bind to this type.

        def close(self):
            events.append("closed")

    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert events == []
    assert ports.events == ["identity", "authorize", "policy", "source"]


def test_unrelated_builtin_function_is_not_a_binary_reader_operation():
    request, _, ports = _inputs()

    class Reader:
        read = len
        def close(self):
            pytest.fail('invalid reader must not transfer ownership')

    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)


def test_miswired_builtin_close_is_rejected_before_transferring_handle():
    request, source, ports = _inputs()
    opened = []

    class MiswiredBytesIO(io.BytesIO):
        close = io.BytesIO.read

    def opener(*, grant):
        reader = MiswiredBytesIO(source.payload)
        opened.append(reader)
        return reader

    ports.open_authorized_evidence = opener
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert len(opened) == 1 and not opened[0].closed
    # Rejected stream cleanup belongs to the privileged adapter (not arbitrary close()).
    io.BytesIO.close(opened[0])


@pytest.mark.parametrize('factory', [
    lambda: io.StringIO('not binary'),
    lambda: io.TextIOWrapper(io.BytesIO(b'not binary'), encoding='utf-8'),
])
def test_text_stream_is_rejected_before_materialization(factory):
    request, _, ports = _inputs()
    stream = factory()
    ports.open_authorized_evidence = lambda *, grant: stream
    try:
        with pytest.raises(PreparationAuthorityContractError):
            _compose(ports).prepare(request=request)
    finally:
        stream.close()


def test_list_methods_cannot_masquerade_as_binary_stream():
    request, _, ports = _inputs()

    class Reader(list):
        read = list.append
        close = list.clear

    reader = Reader()
    ports.open_authorized_evidence = lambda *, grant: reader
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert reader == []


def test_foreign_bound_builtin_methods_cannot_mix_stream_ownership():
    request, source, ports = _inputs()
    actual = io.BytesIO(source.payload)
    foreign = io.BytesIO()

    class Reader:
        def __init__(self):
            self.read = actual.read
            self.close = foreign.close

    ports.open_authorized_evidence = lambda *, grant: Reader()
    try:
        with pytest.raises(PreparationAuthorityContractError):
            _compose(ports).prepare(request=request)
        assert not actual.closed and not foreign.closed
    finally:
        actual.close()
        foreign.close()


@pytest.mark.parametrize('intercept', ['read', 'close'])
def test_dynamic_attribute_override_does_not_run_hostile_getter(intercept):
    request, _, ports = _inputs()
    events = []

    class Reader:
        def __getattribute__(self, name):
            if name == intercept:
                events.append(name)
                raise RuntimeError('PRIVATE reader interception')
            return object.__getattribute__(self, name)
        def read(self, size):
            events.append('read')
            return b''
        def close(self):
            events.append('close')

    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError) as caught:
        _compose(ports).prepare(request=request)
    assert events == []
    assert 'PRIVATE' not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_builtin_own_operation_on_binary_reader_is_cached_and_closes():
    request, source, ports = _inputs()
    stream = io.BytesIO(source.payload)
    ports.open_authorized_evidence = lambda *, grant: stream
    assert _compose(ports).prepare(request=request).prepared.bound.context.submission_ref == request.submission_ref
    assert stream.closed

# Reader-contract continuity: reject malformed declarations before consuming evidence.
def test_python_reader_missing_read_size_rejected_without_read():
    request, source, ports = _inputs()
    events = []
    class Reader:
        def read(self):
            events.append('read')
            return source.payload
        def close(self):
            events.append('close')
    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert events == []


def test_python_reader_required_close_argument_rejected_before_read():
    request, source, ports = _inputs()
    events = []
    class Reader:
        def read(self, size):
            events.append('read')
            return source.payload
        def close(self, token):
            events.append('close')
    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert events == []


def test_python_reader_read_alias_cannot_masquerade_as_close():
    request, source, ports = _inputs()
    stream = io.BytesIO(source.payload)
    class Reader:
        def read(self, size=65536):
            return stream.read(size)
        close = read
    ports.open_authorized_evidence = lambda *, grant: Reader()
    try:
        with pytest.raises(PreparationAuthorityContractError):
            _compose(ports).prepare(request=request)
        assert stream.tell() == 0
    finally:
        stream.close()


@pytest.mark.parametrize('operation', ['read', 'close'])
def test_reader_forged_signature_metadata_rejected_before_io(operation):
    import inspect
    request, source, ports = _inputs()
    observed = []
    class Reader:
        def read(self, size):
            observed.append('read')
            return source.payload
        def close(self):
            observed.append('close')
    function = getattr(Reader, operation)
    function.__signature__ = inspect.Signature([
        inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD),
        *([inspect.Parameter('size', inspect.Parameter.POSITIONAL_OR_KEYWORD)] if operation == 'read' else []),
    ])
    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert observed == []


def test_reader_keyword_only_size_rejected_before_io():
    request, source, ports = _inputs()
    observed = []
    class Reader:
        def read(self, *, size):
            observed.append('read')
            return source.payload
        def close(self):
            observed.append('close')
    ports.open_authorized_evidence = lambda *, grant: Reader()
    with pytest.raises(PreparationAuthorityContractError):
        _compose(ports).prepare(request=request)
    assert observed == []


def test_port_dynamic_getattribute_is_never_used_to_invoke_authority():
    request, source, ports = _inputs()
    class HostilePort(FixturePorts):
        def __getattribute__(self, name):
            if name in {'current_actor', 'authorize_preparation', 'resolve_approved_policy',
                        'resolve_revisioned_preparation', 'open_authorized_evidence'}:
                raise RuntimeError('PRIVATE_UNTRUSTED_DYNAMIC_LOOKUP')
            return super().__getattribute__(name)
    ports = HostilePort(request, source)
    result = _compose(ports).prepare(request=request)
    assert result.custody.actor_ref == 'ACTOR-1'
    assert ports.events == ['identity', 'authorize', 'policy', 'source', 'open']


def test_authority_method_reassignment_after_constructor_does_not_substitute_operation():
    request, source, ports = _inputs()
    composer = _compose(ports)
    ports.current_actor = lambda: (_ for _ in ()).throw(RuntimeError('PRIVATE_SUBSTITUTED_METHOD'))
    result = composer.prepare(request=request)
    assert result.custody.actor_ref == 'ACTOR-1'
    assert ports.events == ['identity', 'authorize', 'policy', 'source', 'open']
