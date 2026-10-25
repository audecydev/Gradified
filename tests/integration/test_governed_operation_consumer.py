"""Real strict FIRST/physical attempt claim/scoring/CAS -> independently recovered governed result.

Synthetic qualified-port fixtures exercise Gradified-owned causal contracts only.
Neither model calls a real school backend nor publishes an official grade.
"""
from dataclasses import replace
import pytest

from grading.integration.production_paper_operations import PaperOperationKind
from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from grading.integration.governed_operation_consumer import (
    ProductionGovernedOperationConsumer, GovernedOperationState, ScoredOperationIdentity,
)
from grading.integration.governed_original_assessment import (
    GovernedOriginalFact, ProductionGovernedOriginalAssessment, GovernedOriginalKey,
)
from grading.integration.governed_paper_handoff import ProductionGovernedPaperHandoff
from grading.integration.assessment_readiness_views import (
    ProductionAssessmentReadiness, AssessmentViewFact, EvidenceView,
)
from grading.integration.governed_result_disposition import ResultDisposition
from tests.integration.test_production_paper_operations import _root
from tests.integration.test_family_first_scored_cas import connected, POLICY
from tests.integration.test_family_retry_accounting import connected_family_retry


class KeySource:
    def __init__(self):
        self.calls = 0
        self.foreign = None
        self.explode = False
        self.on_call = None
        self.keys = []

    def read_governed_original(self, *, operation):
        self.calls += 1
        self.keys.append(operation)
        assert type(operation) is ScoredOperationIdentity
        if self.on_call: self.on_call()
        if self.explode: raise TimeoutError('unknown backend result')
        key = GovernedOriginalKey(operation.tenant_ref, operation.grading_run_id,
            operation.original_scored_result_ref, operation.source_revision,
            'POLICY-ISSUED', 'POLICY-REV-1')
        return key if self.foreign is None else replace(key, **self.foreign)


class OriginalFactPort:
    def __init__(self, method, value=True):
        self.value = value
        self.calls = 0
        self.method = method
    def read_scored_original(self, *, original):
        self.calls += 1
        return GovernedOriginalFact(original, self.value)
    def read_academic_original(self, *, original):
        self.calls += 1
        return GovernedOriginalFact(original, self.value)
    def read_teacher_original(self, *, original):
        self.calls += 1
        return GovernedOriginalFact(original, self.value)
    def read_adverse_policy(self, *, original):
        self.calls += 1
        return GovernedOriginalFact(original, self.value)


class ViewPort:
    def __init__(self, view, value=True):
        self.view = view
        self.value = value
        self.calls = 0
    def read_ocr_view(self, *, origin):
        self.calls += 1
        return AssessmentViewFact(origin, self.view, 'SCHOOL-ISSUER', 'V1', self.value)
    def read_rubric_view(self, *, origin):
        self.calls += 1
        return AssessmentViewFact(origin, self.view, 'SCHOOL-ISSUER', 'V1', self.value)
    def read_grading_view(self, *, origin):
        self.calls += 1
        return AssessmentViewFact(origin, self.view, 'SCHOOL-ISSUER', 'V1', self.value)


def rig(*, family='DIRECT', academic=True, view=True):
    cas, plan, _, physical, _, f25, provider, store, conditional = connected(family)
    lifecycle = ProductionPaperLifecycle(cas=cas, permission_source=f25.f57_source,
        legal_policy=POLICY, max_identifier_characters=128, max_questions=10)
    root, school = _root(lifecycle=lifecycle, plan=plan,
        kinds=(PaperOperationKind.FIRST,), qualified=True)
    source = KeySource()
    originals = tuple(OriginalFactPort(name, academic) for name in range(4))
    assessment = ProductionGovernedOriginalAssessment(scored=originals[0],
        academic=originals[1], teacher=originals[2], adverse_policy=originals[3],
        max_identifier_characters=128)
    views = tuple(ViewPort(key, view) for key in EvidenceView)
    readiness = ProductionAssessmentReadiness(ocr=views[0], rubric=views[1],
        grading=views[2], max_identifier_characters=128)
    handoff = ProductionGovernedPaperHandoff(original=assessment, readiness=readiness)
    owner = ProductionGovernedOperationConsumer(operations=root, original_source=source,
        handoff=handoff, max_identifier_characters=128)
    return owner, source, originals, views, plan, school, physical, provider, store, conditional


@pytest.mark.parametrize('family,claims', [('DIRECT',1), ('NUMERIC',1), ('MIXED',2)])
def test_eligible_requires_actual_first_f25_and_scored_cas_and_all_independent_reads(family, claims):
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig(family=family)
    out = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert out.handoff.decision.disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
    assert out.operation.execution.cas.transaction.result_ref == source.keys[0].original_scored_result_ref
    assert (physical.claims, store.commits, conditional.contacts) == (claims, 1, 1)
    assert source.calls == 1
    assert all(r.calls == 1 for r in originals)
    assert all(v.calls == 1 for v in views)
    assert not out.authorizes_publication and not out.authorizes_retry
    assert not out.handoff.authorizes_publication


@pytest.mark.parametrize('change', [
    {'tenant_ref':'FOREIGN'}, {'grading_run_id':'OLD-RUN'},
    {'original_scored_result_ref':'OLD-SCORE'}, {'source_revision':'STALE'},
    {'policy_ref':''}, {'policy_revision':'UNKNOWN '},
])
def test_foreign_original_key_never_reaches_independent_governing_readers(change):
    owner, source, originals, views, plan, _, physical, _, store, _ = rig()
    source.foreign = change
    out = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.state is GovernedOperationState.UNKNOWN and out.handoff is None
    assert physical.claims == 1 and store.commits == 1
    assert source.calls == 1
    assert all(x.calls == 0 for x in originals + views)


@pytest.mark.parametrize('mode', ['failure', 'denied', 'unknown', 'review', 'view_unknown'])
def test_denial_uncertainty_and_review_never_convert_into_success(mode):
    owner, source, originals, views, plan, school, physical, provider, store, conditional = rig()
    if mode == 'failure':
        school.readiness = replace(school.readiness, answers=(
            replace(school.readiness.answers[0], status='UNKNOWN'),))
        from grading.integration.paper_readiness_admission import PaperAnswerNotReady
        with pytest.raises(PaperAnswerNotReady):
            owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
        assert source.calls == 0 and physical.claims == 0 and store.commits == 0
        return
    if mode == 'denied':
        conditional.revoke_at_commit = True
    elif mode == 'unknown':
        conditional.lost_ack = True
    elif mode == 'review':
        originals[1].value = False
    else:
        views[1].value = None
    out = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.state is {
        'denied': GovernedOperationState.BLOCKED,
        'unknown': GovernedOperationState.UNKNOWN,
        'review': GovernedOperationState.REVIEW,
        'view_unknown': GovernedOperationState.UNKNOWN,
    }[mode]
    assert source.calls == (0 if mode in ('denied','unknown') else 1)
    assert not out.authorizes_publication and not out.authorizes_retry


def test_governed_original_read_timeout_keeps_scored_history_without_reexecuting():
    owner, source, originals, views, plan, _, physical, _, store, conditional = rig()
    source.explode = True
    out = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.state is GovernedOperationState.UNKNOWN and out.handoff is None
    assert out.operation.execution.cas.state.name == 'COMMITTED'
    assert (source.calls, physical.claims, store.commits, conditional.contacts) == (1,1,1,1)
    assert all(x.calls==0 for x in originals+views)


def test_governed_source_mutating_caller_request_does_not_change_original_identity():
    owner, source, originals, views, plan, _, physical, _, store, _ = rig()
    # The original client request is not passed into any downstream source; the
    # engine snapshots and uses an exact detached request at the strict root.
    def change_source():
        object.__setattr__(plan.request, 'grading_run_id', 'REPLACED')
    source.on_call = change_source
    out = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.state is GovernedOperationState.UNKNOWN
    assert all(x.calls==0 for x in originals+views)
    assert physical.claims == 1 and store.commits == 1


def test_rejects_unqualified_consumer_installation_before_effect():
    owner, source, original, views, plan, _, physical, _, store, _ = rig()
    with pytest.raises(ValueError):
        ProductionGovernedOperationConsumer(operations=object(), original_source=source,
            handoff=owner._handoff, max_identifier_characters=128)
    assert physical.claims == 0 and store.commits == 0


@pytest.mark.parametrize('kind', [PaperOperationKind.REGRADE, PaperOperationKind.RETRY])
def test_original_scored_operation_is_consumed_for_regrade_and_retry(kind):
    if kind is PaperOperationKind.REGRADE:
        from tests.integration.test_family_first_scored_cas import connected_regrade
        lifecycle, plan, physical, _, _, _, store, conditional, old, _ = connected_regrade()
        root, _ = _root(lifecycle=lifecycle, plan=plan, kinds=(kind,), qualified=True)
        initial_commits = store.commits
    else:
        retry, plan, physical, _, store, _, _ = connected_family_retry()
        root, _ = _root(retry=retry, plan=plan, kinds=(kind,), qualified=True)
        initial_commits = store.commits
    reference, source, originals, views, _, _, _, _, _, _ = rig()
    owner = ProductionGovernedOperationConsumer(operations=root, original_source=source,
        handoff=reference._handoff, max_identifier_characters=128)
    out = owner.execute_and_assess(request=plan.request, kind=kind)
    assert out.state is GovernedOperationState.HANDOFF_ELIGIBLE
    assert out.operation.kind is kind
    assert source.keys[0].kind is kind
    assert source.keys[0].original_scored_result_ref == out.operation.execution.cas.transaction.result_ref
    assert physical.claims == 1 and store.commits == initial_commits + 1
    assert not out.authorizes_publication


def test_post_cas_caller_request_corruption_preserves_original_observation(monkeypatch):
    """A nonconforming backend cannot turn a committed CAS into lost history."""
    owner, source, originals, views, plan, _, physical, _, store, _ = rig()
    actual_commit = store.commit_whole_paper

    def commit_and_corrupt_original_client_input(*, transaction, custody):
        acknowledged = actual_commit(transaction=transaction, custody=custody)
        # Simulate external code wrongly retaining and corrupting a caller-owned
        # dataclass after the real CAS write, before the scored root returns.
        object.__setattr__(plan.request, 'tenant_ref', '')
        return acknowledged

    monkeypatch.setattr(store, 'commit_whole_paper',
                        commit_and_corrupt_original_client_input)
    out = owner.execute_and_assess(request=plan.request, kind=PaperOperationKind.FIRST)
    assert out.state is GovernedOperationState.UNKNOWN
    assert out.handoff is None
    assert out.operation.execution.cas.state.name == 'COMMITTED'
    assert physical.claims == 1 and store.commits == 1
    assert source.calls == 0
    assert not out.authorizes_publication and not out.authorizes_retry
