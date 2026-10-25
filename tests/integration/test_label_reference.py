"""teacher-label reference read-only teacher-label reference continuity, never an academic result."""
from dataclasses import replace
from hashlib import sha256
import pytest

from grading.benchmark.label_reference import (
    LabelReferenceContinuity, LabelReferenceDenied, LabelReferenceFact,
    LabelReferenceIndeterminate, LabelReferenceQuery, LabelReferenceStatus,
    ReadOnlyTeacherLabelReferenceContinuity,
)
from grading.benchmark.source_bound_trial import SourceBoundOfflineReplayEvidence
from test_source_bound_trial import install


class Issuer:
    def __init__(self, *, status=LabelReferenceStatus.CURRENT, transform=None, error=None):
        self.calls = 0
        self.requests = []
        self.status = status
        self.transform = transform
        self.error = error

    def resolve_label_reference(self, *, query):
        self.calls += 1
        self.requests.append(query)
        if self.transform is not None:
            return self.transform(query)
        if self.error is not None:
            raise self.error
        if self.status is LabelReferenceStatus.CURRENT:
            return LabelReferenceFact(query, self.status, 'issuer-A', 'issuer-v1', 'assertion-01')
        return LabelReferenceFact(query, self.status, None, None, None)


def observation():
    trial, *_ = install()
    return trial.run()


def bound(*, value=None, issuer=None):
    a = issuer if issuer is not None else Issuer()
    q = ReadOnlyTeacherLabelReferenceContinuity(
        evidence=observation() if value is None else value,
        authority=a, max_identifier_characters=100)
    return q, a


def test_current_label_reference_is_not_academic_grade_or_mark():
    source = observation()
    reader = Issuer()
    q, _ = bound(value=source, issuer=reader)
    result = q.reconcile()
    assert type(result) is LabelReferenceContinuity
    assert result.evidence_type == 'ISSUER_REPORTED_REFERENCE_NONACADEMIC_OFFLINE_REPLAY'
    assert result.query.teacher_annotation_ref == 'label-1'
    assert result.query.teacher_annotation_sha256 == f'{1:064x}'
    assert result.output_sha256 == sha256(b'fixture-response').hexdigest()
    assert result.observation_event_ref == source.observation.event_ref
    assert result.issuer_ref == 'issuer-A' and result.attestation_ref == 'assertion-01'
    assert not hasattr(result, 'grade') and not hasattr(result, 'teacher_mark')
    assert reader.calls == 1
    with pytest.raises(LabelReferenceDenied): q.reconcile()
    assert reader.calls == 1


@pytest.mark.parametrize('status,exc',[
    (LabelReferenceStatus.REVOKED, LabelReferenceDenied),
    (LabelReferenceStatus.UNKNOWN, LabelReferenceIndeterminate),
])
def test_noncurrent_or_unknown_never_returns_positive_evidence(status, exc):
    q, issuer = bound(issuer=Issuer(status=status))
    with pytest.raises(exc):q.reconcile()
    assert issuer.calls == 1


@pytest.mark.parametrize('field,wrong', [
    ('tenant_ref', 'wrong-tenant'), ('run_ref', 'wrong-run'),
    ('trial_request_ref', 'wrong-trial'), ('trial_ref', 'wrong-claim'),
    ('dataset_ref', 'wrong-dataset'), ('dataset_revision', 'wrong-revision'),
    ('dataset_sha256', 'b'*64), ('read_scope_ref', 'wrong-grant'),
    ('case_ref', 'other-case'), ('split', 'heldout'),
    ('source_policy_id', 'wrong-policy'), ('source_policy_version', 'wrong-version'),
    ('teacher_annotation_ref', 'other-label'),
    ('teacher_annotation_revision', 'other-label-v'),
    ('teacher_annotation_sha256', 'b'*64),
])
def test_foreign_issuer_response_denied_on_every_critical_field(field, wrong):
    def wrong_fact(q):
        return LabelReferenceFact(replace(q, **{field: wrong}),
                                  LabelReferenceStatus.CURRENT, 'issuer', 'v1', 'ref')
    q, issuer = bound(issuer=Issuer(transform=wrong_fact))
    with pytest.raises(LabelReferenceDenied):q.reconcile()
    assert issuer.calls == 1


@pytest.mark.parametrize('malformed', [
    lambda q: LabelReferenceFact(q, 'CURRENT', 'issuer', 'v1', 'ref'),
    lambda q: LabelReferenceFact(q, LabelReferenceStatus.CURRENT, '', 'v1', 'ref'),
    lambda q: LabelReferenceFact(q, LabelReferenceStatus.REVOKED, 'issuer', None, None),
    lambda q: LabelReferenceFact(q, LabelReferenceStatus.UNKNOWN, None, None, 'false-ref'),
    lambda q: LabelReferenceFact(q, LabelReferenceStatus.CURRENT, 12, 'v1', 'ref'),
    lambda q: LabelReferenceFact(q, LabelReferenceStatus.CURRENT, 'issuer', 'v1', None),
])
def test_no_false_positive_from_invalid_fact_or_issuer(malformed):
    q, issuer = bound(issuer=Issuer(transform=malformed))
    with pytest.raises(LabelReferenceDenied):q.reconcile()
    assert issuer.calls == 1


def test_issuer_operation_captured_before_rebinding():
    issuer = Issuer()
    q, issuer = bound(issuer=issuer)
    issuer.resolve_label_reference = lambda **k: (_ for _ in ()).throw(AssertionError('REBOUND'))
    assert q.reconcile().issuer_ref == 'issuer-A'


@pytest.mark.parametrize('raising', [False, True])
def test_mutated_submitted_query_during_callback_never_accepted(raising):
    def mutate(query):
        object.__setattr__(query, 'teacher_annotation_ref', 'new-label')
        if raising:
            raise TimeoutError('SECRET issuer')
        return LabelReferenceFact(query, LabelReferenceStatus.CURRENT, 'issuer', 'v1', 'ref')
    q, issuer = bound(issuer=Issuer(transform=mutate))
    with pytest.raises(LabelReferenceIndeterminate) as caught:q.reconcile()
    assert issuer.calls == 1
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_timeout_always_uncertain_and_context_is_sanitized():
    q, issuer = bound(issuer=Issuer(error=RuntimeError('SENSITIVE-BACKEND-LABEL')))
    try:raise RuntimeError('PRIVATE_AMBIENT')
    except RuntimeError:
        with pytest.raises(LabelReferenceIndeterminate) as caught:q.reconcile()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert caught.value.__suppress_context__ is True
    assert issuer.calls == 1


def test_explicit_denial_is_not_confused_with_unknown():
    q, issuer = bound(issuer=Issuer(error=LabelReferenceDenied('sensitive rejection')))
    with pytest.raises(LabelReferenceDenied) as caught:q.reconcile()
    assert 'sensitive' not in str(caught.value)
    assert issuer.calls == 1


@pytest.mark.parametrize('field,wrong', [
    ('benchmark_source_ref','wrong'),('benchmark_source_revision','rev-wrong'),
    ('benchmark_source_sha256', 'a'*64),('case_ref','wrong'),
    ('split','DEVELOPMENT'), ('teacher_annotation_ref', ''),
    ('teacher_annotation_sha256','a'), ('evidence_type','ACADEMIC_GROUND_TRUTH'),
])
def test_forged_source_evidence_rejected_before_label_query(field, wrong):
    original = observation()
    issuer = Issuer()
    with pytest.raises(LabelReferenceDenied):
        bound(value=replace(original, **{field:wrong}),issuer=issuer)
    assert issuer.calls == 0


def test_failed_source_observation_no_academic_reference_upgrade():
    original = observation()
    issuer = Issuer()
    bad = replace(original,observation=replace(original.observation,
                          evidence_type='AUTHORITATIVE_LIVE'))
    with pytest.raises(LabelReferenceDenied):bound(value=bad,issuer=issuer)
    assert issuer.calls == 0


def test_foreign_str_equality_never_accepted():
    class MatchesEverything(str):
        def __eq__(self, other):return True
    def foreign(q):
        return LabelReferenceFact(replace(q,case_ref=MatchesEverything('foreign')),
                                  LabelReferenceStatus.CURRENT,'issuer','v1','ref')
    q, issuer = bound(issuer=Issuer(transform=foreign))
    with pytest.raises(LabelReferenceDenied):q.reconcile()
    assert issuer.calls == 1


def test_installation_cannot_rebind_installed_issuer():
    q, issuer = bound()
    with pytest.raises(AttributeError):q._installation = None
    with pytest.raises(AttributeError):del q._installation
    assert q.reconcile().issuer_ref == 'issuer-A'


def test_invalid_installation_does_not_call_external_authority():
    issuer = Issuer()
    with pytest.raises(LabelReferenceDenied):
        ReadOnlyTeacherLabelReferenceContinuity(evidence=None, authority=issuer,
                                                max_identifier_characters=100)
    assert issuer.calls == 0
