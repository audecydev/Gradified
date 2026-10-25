"""Hostile contract tests: one-shot rubric generation without academic promotion."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from grading.contracts.scoring_decimal import ScoringDecimal
from grading.providers.rubric_generation import rubric_provider_request_fingerprint
from grading.providers.rubric_ingress import RubricProviderProvenance
from grading.providers.rubric_accounting import (
    OneShotRubricGenerationAccountingProvider, RubricAccountingDenied,
    RubricAccountingIndeterminate, RubricAccountingIdentity, RubricGenerationGrant,
    RubricGrantDisposition, RubricAccountingReceipt,
)
from grading.rubric.generator import RubricGenerationInput
from grading.rubric.models import FinalizedQuestionScoringBasis


def source():
    return RubricGenerationInput(FinalizedQuestionScoringBasis('Q1', ScoringDecimal.from_raw('5')),
                                'Explain addition', '2+3=5', 'R1', 'P1',
                                ScoringDecimal.from_raw('0'), None)


def identity(value=None):
    return RubricAccountingIdentity('tenant-1', 'generation-1', 'operation-1', 'event-1',
                                   'provider-1', 'model-1', 'config-1',
                                   rubric_provider_request_fingerprint(value or source()))


class Provider:
    def __init__(self, *, effect=None):
        self.provenance = RubricProviderProvenance('provider-1', 'model-1')
        self.calls = 0
        self.effect = effect

    def generate(self, *, source):
        self.calls += 1
        if self.effect is not None:
            return self.effect(source)
        return b'{"schema_version":"1"}'


class Authority:
    def __init__(self, *, disposition=RubricGrantDisposition.ALLOWED, effect=None):
        self.disposition = disposition
        self.effect = effect
        self.calls = 0

    def authorize_generation(self, *, identity):
        self.calls += 1
        if self.effect is not None:
            return self.effect(identity)
        if self.disposition is RubricGrantDisposition.ALLOWED:
            return RubricGenerationGrant(identity, self.disposition, 'approval-1', 'policy-1', 'v1')
        return RubricGenerationGrant(identity, self.disposition, None, None, None)


class Sink:
    def __init__(self, effect=None):
        self.calls = 0
        self.events = []
        self.effect = effect

    def record_rubric_generation(self, *, event):
        self.calls += 1
        self.events.append(event)
        if self.effect is not None:
            return self.effect(event)
        return RubricAccountingReceipt(event.identity.event_ref, event.identity.operation_ref,
                                       event.approval_ref, event.status)


def installed(*, value=None, provider=None, authority=None, sink=None):
    p = provider if provider is not None else Provider()
    a = authority if authority is not None else Authority()
    h = sink if sink is not None else Sink()
    wrapper = OneShotRubricGenerationAccountingProvider(identity=value or identity(),
                       provider=p, authority=a, sink=h,
                       max_identifier_characters=120, max_raw_response_bytes=2048)
    return wrapper, p, a, h


def test_happy_once_with_unknown_usage_and_immutable_provenance():
    w, p, a, h = installed()
    assert w.generate(source=source()) == b'{"schema_version":"1"}'
    assert (p.calls, a.calls, h.calls) == (1, 1, 1)
    assert h.events[0].physical_request_count is None
    assert h.events[0].sdk_retry_count is None
    assert w.provenance == p.provenance
    with pytest.raises(RubricAccountingDenied):
        w.generate(source=source())
    assert (p.calls, a.calls, h.calls) == (1, 1, 1)


def test_foreign_source_denied_before_authority_provider_and_history():
    w, p, a, h = installed()
    with pytest.raises(RubricAccountingDenied):
        w.generate(source=replace(source(), question_text='foreign student input'))
    assert (p.calls, a.calls, h.calls) == (0, 0, 0)


@pytest.mark.parametrize('disposition,expected', [
    (RubricGrantDisposition.DENIED, RubricAccountingDenied),
    (RubricGrantDisposition.UNKNOWN, RubricAccountingIndeterminate),
])
def test_nonallowed_authority_cannot_contact_provider(disposition, expected):
    w, p, a, h = installed(authority=Authority(disposition=disposition))
    with pytest.raises(expected):
        w.generate(source=source())
    assert (p.calls, a.calls, h.calls) == (0, 1, 0)


def test_foreign_grant_denied_before_provider_contact():
    auth = Authority(effect=lambda i: RubricGenerationGrant(replace(i, tenant_ref='foreign'),
                                   RubricGrantDisposition.ALLOWED, 'A', 'P', '1'))
    w, p, a, h = installed(authority=auth)
    with pytest.raises(RubricAccountingDenied):
        w.generate(source=source())
    assert p.calls == h.calls == 0


def test_grant_mutation_then_exception_precedes_refusal():
    def corrupt(i):
        object.__setattr__(i, 'tenant_ref', 'foreign')
        raise RubricAccountingDenied('private grant')
    w, p, a, h = installed(authority=Authority(effect=corrupt))
    with pytest.raises(RubricAccountingDenied) as result:
        w.generate(source=source())
    assert result.value.__context__ is None
    assert p.calls == h.calls == 0


def test_provider_timeout_is_indeterminate_and_not_blind_retried():
    def timeout(s):
        raise TimeoutError('PRIVATE key')
    w, p, a, h = installed(provider=Provider(effect=timeout))
    with pytest.raises(RubricAccountingIndeterminate) as result:
        w.generate(source=source())
    assert result.value.__context__ is None
    assert p.calls == h.calls == 1
    assert h.events[0].status == 'INDETERMINATE'
    with pytest.raises(RubricAccountingDenied):
        w.generate(source=source())
    assert p.calls == 1


def test_oversized_provider_payload_never_returned():
    w, p, a, h = installed(provider=Provider(effect=lambda s: b'x'*4000))
    with pytest.raises(RubricAccountingIndeterminate):
        w.generate(source=source())
    assert h.events[0].status == 'INDETERMINATE'


def test_foreign_receipt_fails_closed_after_possible_effect():
    h = Sink(effect=lambda e: RubricAccountingReceipt(e.identity.event_ref,
                                                      'foreign-operation', e.approval_ref, e.status))
    w, p, a, h = installed(sink=h)
    with pytest.raises(RubricAccountingIndeterminate):
        w.generate(source=source())
    assert p.calls == h.calls == 1


def test_sink_mutates_event_identity_and_raises_cannot_admit_payload():
    def corrupt(e):
        object.__setattr__(e.identity, 'event_ref', 'foreign')
        raise RuntimeError('PRIVATE')
    w, p, a, h = installed(sink=Sink(effect=corrupt))
    with pytest.raises(RubricAccountingIndeterminate) as result:
        w.generate(source=source())
    assert result.value.__context__ is None
    assert p.calls == h.calls == 1


def test_issuer_changes_installed_dispatch_callback_original_is_used():
    p = Provider()
    impostor = Provider()
    w, _, a, h = installed(provider=p)
    def corrupt(i):
        p.generate = impostor.generate
        return RubricGenerationGrant(i, RubricGrantDisposition.ALLOWED, 'A', 'P', '1')
    # Construct with original generation captured; after install replace issuer's behavior.
    a.effect = corrupt
    assert w.generate(source=source()) == b'{"schema_version":"1"}'
    assert p.calls == 1 and impostor.calls == 0


def test_two_threads_cannot_duplicate_generation():
    w, p, a, h = installed()
    barrier = Barrier(3)
    def run():
        barrier.wait()
        try:
            w.generate(source=source())
            return 'success'
        except RubricAccountingDenied:
            return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        x = pool.submit(run)
        y = pool.submit(run)
        barrier.wait()
        assert sorted((x.result(), y.result())) == ['denied','success']
    assert (p.calls, a.calls, h.calls) == (1, 1, 1)


def test_invalid_installation_does_not_expose_private_exception():
    try:
        raise RuntimeError('PRIVATE ambient')
    except RuntimeError:
        with pytest.raises(RubricAccountingDenied) as result:
            OneShotRubricGenerationAccountingProvider(identity=identity(), provider=None,
                authority=None, sink=None, max_identifier_characters=0, max_raw_response_bytes=0)
    assert result.value.__cause__ is None and result.value.__context__ is None


def test_real_frozen_rubric_provider_consumer_receives_only_accounted_bytes():
    import json
    from grading.providers.rubric_generation import generate_rubric_with_provider
    from grading.providers.rubric_ingress import RubricProviderIngressLimits
    from grading.rubric.models import RubricCompilationLimits
    payload = json.dumps({
        'schema_version':'1',
        'criteria':[{
            'criterion_id':'C1',
            'operational_description':'Award correct explanation.',
            'evidence_requirement':'Shows sum',
            'performance_levels':[
                {'level_id':'FULL','operational_description':'Complete','contribution':5},
                {'level_id':'NONE','operational_description':'Absent','contribution':0},
            ],
            'accepted_equivalents': [],
        }],
        'positive_credit_dependencies': [], 'gates': [], 'caps': [], 'deductions': [],
    }).encode()
    compiling = RubricCompilationLimits(20,10,20,50,20,10,2000,100000,1000)
    ingress = RubricProviderIngressLimits(20000, 32, 1000, 256, compiling)
    w,p,a,h = installed(provider=Provider(effect=lambda src:payload))
    candidate = generate_rubric_with_provider(source=source(),provider=w,ingress_limits=ingress)
    assert candidate.request_fingerprint == identity().source_fingerprint
    assert p.calls == a.calls == h.calls == 1
    assert candidate.admitted_proposal.provenance == w.provenance


def test_sink_mutates_approval_into_deceptive_comparison_object():
    class Tricky:
        def __eq__(self, _):
            return True
    def corrupt(e):
        object.__setattr__(e, 'approval_ref', Tricky())
        return RubricAccountingReceipt(e.identity.event_ref, e.identity.operation_ref,
                                       'approval-1', e.status)
    w,p,a,h = installed(sink=Sink(effect=corrupt))
    with pytest.raises(RubricAccountingIndeterminate):
        w.generate(source=source())
    assert p.calls == a.calls == h.calls == 1


def test_authority_retargets_original_provider_but_original_operation_remains_captured():
    provider = Provider()
    bad = Provider(effect=lambda _: b'foreign')
    issuer = Authority()
    sink = Sink()
    w,p,a,h = installed(provider=provider, authority=issuer, sink=sink)
    issuer.effect = lambda ident: (setattr(provider, 'generate', bad.generate)
                     or RubricGenerationGrant(ident, RubricGrantDisposition.ALLOWED, 'A','P','1'))
    assert w.generate(source=source()) == b'{"schema_version":"1"}'
    assert provider.calls == 1 and bad.calls == 0


def test_extreme_rubric_resource_limit_rejected_at_installation():
    with pytest.raises(RubricAccountingDenied):
        OneShotRubricGenerationAccountingProvider(identity=identity(), provider=Provider(),
            authority=Authority(), sink=Sink(), max_identifier_characters=120,
            max_raw_response_bytes=1<<4096)
