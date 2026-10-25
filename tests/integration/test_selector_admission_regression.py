"""Verify selector admission checks authority before reads and bounds before selection."""
from __future__ import annotations

from io import BytesIO

import pytest

from grading.active_question_authority import ContextPolicy
from grading.contracts.evaluator_selection import (
    EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION,
    QUESTION_EVALUATION_CLASSIFICATION_SCHEMA_VERSION,
    EvaluatorSelectionPolicyRef,
    EvaluatorSelectionRule,
    QuestionEvaluationClassification,
)
from grading.integration.selector_admission import (
    ConfiguredSelectionSources,
    SelectionAdmissionDenied,
    SelectionAdmissionUnavailable,
    SelectionSourceContractError,
    SelectorResourceLimitError,
    SelectorResourceLimits,
    bounded_source_bytes,
    select_with_admitted_sources,
)
from tests.integration.test_evaluator_selection_contract_regression import (
    _CapabilitySource,
    _ClassificationSource,
    _capability_record,
    _capability_ref,
    _question_authority,
)


class PolicyStream:
    def __init__(self, rules, *, policy_ref=None):
        self.rules = rules
        self.policy_ref = policy_ref or EvaluatorSelectionPolicyRef("routing-policy", 2)
        self.header_reads = 0
        self.yielded = 0

    def read_policy_header(self):
        self.header_reads += 1
        return (EVALUATOR_SELECTION_POLICY_SCHEMA_VERSION, self.policy_ref)

    def iter_policy_rules(self):
        for rule in self.rules:
            self.yielded += 1
            yield rule


class Admission:
    def __init__(self, approve=True, *, fingerprint="config-set-A", expected_sources=(), expected_limits=None):
        self.approve = approve
        self.fingerprint = fingerprint
        self.expected_sources = expected_sources
        self.expected_limits = expected_limits
        self.calls = []

    def authorize_selection_sources(self, *, context, config, limits, classification_source,
                                    policy_stream_source, capability_source):
        self.calls.append((context, config))
        if config.configuration_ref != self.fingerprint:
            return False
        if limits != self.expected_limits:
            return False
        if not all(actual is expected for actual, expected in zip(
            (classification_source, policy_stream_source, capability_source), self.expected_sources,
            strict=True,
        )):
            return False
        return self.approve


def rig(*, approved=True, fingerprint="config-set-A", classification=None, rules=None,
        limit_rules=3, limit_chars=1024, limit_field=128, expected_ref=None):
    question_authority = _question_authority(context_policy=ContextPolicy.DIRECT)
    classification = classification or QuestionEvaluationClassification(
        schema_version=QUESTION_EVALUATION_CLASSIFICATION_SCHEMA_VERSION,
        grading_spec_ref=question_authority.grading_spec_ref,
        question_id=question_authority.question_id,
        answer_type="SHORT_TEXT",
        language="en",
    )
    classification_source = _ClassificationSource(classification)
    rules = rules if rules is not None else [
        EvaluatorSelectionRule("SHORT_TEXT", "en", ContextPolicy.DIRECT, _capability_ref())
    ]
    policy_source = PolicyStream(rules)
    capability_source = _CapabilitySource((_capability_record(),))
    auth = Admission(approved, expected_sources=(classification_source, policy_source, capability_source))
    config = ConfiguredSelectionSources(
        grading_spec_ref=question_authority.grading_spec_ref,
        question_id=question_authority.question_id,
        classification_source_id="classification:revision-7",
        selection_policy_source_id="policy:revision-2",
        capability_source_id="capability:revision-3",
        configuration_ref=fingerprint,
        expected_policy_ref=expected_ref or policy_source.policy_ref,
    )
    limits = SelectorResourceLimits(
        schema_version="1",
        max_policy_rules=limit_rules,
        max_identifier_codepoints=limit_field,
        max_total_text_codepoints=limit_chars,
        max_source_bytes=1024,
    )
    auth.expected_limits = limits
    return question_authority, classification_source, policy_source, capability_source, auth, config, limits


def run(r):
    q, c, p, cap, auth, config, limits = r
    return select_with_admitted_sources(
        question_authority=q,
        configured_sources=config,
        admission_authority=auth,
        classification_source=c,
        policy_stream_source=p,
        capability_source=cap,
        limits=limits,
    )


def test_admitted_bounded_selection_preserves_frozen_if2_and_if1():
    r = rig()
    selected = run(r)
    assert selected.policy_ref == r[5].expected_policy_ref
    assert selected.selected_capability_ref == _capability_ref()
    assert len(r[1].calls) == 1
    assert r[2].header_reads == 1 and r[2].yielded == 1
    assert len(r[3].calls) == 1
    assert len(r[4].calls) == 1


@pytest.mark.parametrize("approval", [False, None, "yes", 1])
def test_denied_or_nonboolean_admission_prevents_every_source_read(approval):
    r = rig()
    r[4].approve = approval
    with pytest.raises(SelectionAdmissionDenied):
        run(r)
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_exact_configuration_ref_mismatch_denied_before_source_access():
    r = rig(fingerprint="config-set-other")
    with pytest.raises(SelectionAdmissionDenied):
        run(r)
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_attempted_source_scope_mismatch_denied_before_source_access():
    from dataclasses import replace
    r = list(rig())
    r[5] = replace(r[5], question_id="Q-from-another-attempt")
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_too_many_streamed_rules_stops_at_first_disallowed_rule_without_if2():
    rule = EvaluatorSelectionRule("SHORT_TEXT", "en", ContextPolicy.DIRECT, _capability_ref())
    r = rig(rules=[rule] * 200, limit_rules=3)
    with pytest.raises(SelectorResourceLimitError):
        run(r)
    assert r[2].yielded == 4  # A lazy source is stopped without exhausting it.
    assert not r[3].calls


def test_oversized_classification_rejected_before_policy_read_and_if2():
    q = _question_authority(context_policy=ContextPolicy.DIRECT)
    classification = QuestionEvaluationClassification("1", q.grading_spec_ref, q.question_id, "X" * 129, "en")
    r = rig(classification=classification, limit_field=128)
    with pytest.raises(SelectorResourceLimitError):
        run(r)
    assert r[1].calls and not r[2].header_reads and not r[3].calls


def test_oversized_streamed_rule_rejected_before_if2():
    rule = EvaluatorSelectionRule("X" * 129, "en", ContextPolicy.DIRECT, _capability_ref())
    r = rig(rules=[rule], limit_field=128)
    with pytest.raises(SelectorResourceLimitError):
        run(r)
    assert not r[3].calls


def test_policy_identity_mismatch_fails_before_frozen_if2():
    r = rig(expected_ref=EvaluatorSelectionPolicyRef("routing-policy", 999))
    with pytest.raises(SelectionSourceContractError):
        run(r)
    assert not r[3].calls


def test_invalid_limits_fail_before_any_source_read():
    from dataclasses import replace
    r = list(rig())
    r[6] = replace(r[6], max_policy_rules=10**30)
    with pytest.raises(SelectorResourceLimitError):
        run(tuple(r))
    assert not r[4].calls and not r[1].calls and not r[2].header_reads


def test_bounded_binary_source_read_cannot_exceed_configured_limit():
    from dataclasses import replace
    base_limits = rig()[6]
    limited = replace(base_limits, max_source_bytes=9)
    stream = BytesIO(b"abcdefghij")
    with pytest.raises(SelectorResourceLimitError):
        bounded_source_bytes(stream, limits=limited)
    assert stream.tell() == 10
    assert bounded_source_bytes(BytesIO(b"abcd"), limits=replace(base_limits, max_source_bytes=4)) == b"abcd"


def test_invalid_policy_stream_shape_is_not_silent_denial_or_academic_failure():
    r = list(rig())
    r[2] = object()
    # The trusted root has explicitly admitted this exact (malformed) source;
    # now verify the source-contract failure rather than a source-swap denial.
    r[4].expected_sources = (r[1], r[2], r[3])
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls


def test_swapped_source_with_identical_claimed_ids_is_rejected_before_read():
    r = list(rig())
    original = r[1]
    r[1] = _ClassificationSource(original.value)
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_total_text_budget_applies_across_multiple_distinct_rules():
    refs = [_capability_ref(evaluator_id=f"cap-{i}") for i in range(3)]
    rules = [EvaluatorSelectionRule("SHORT_TEXT", "en", ContextPolicy.DIRECT, ref) for ref in refs]
    r = rig(rules=rules, limit_chars=44)
    with pytest.raises(SelectorResourceLimitError):
        run(r)
    assert not r[3].calls


def test_nonstreaming_prebuffered_rule_list_is_rejected_not_silently_converted():
    r = list(rig())
    class WrongPolicyStream(PolicyStream):
        def iter_policy_rules(self):
            return self.rules
    wrong = WrongPolicyStream(r[2].rules)
    r[4].expected_sources = (r[1], wrong, r[3])
    r[2] = wrong
    with pytest.raises(SelectionSourceContractError):
        run(tuple(r))
    assert not r[3].calls


def test_absent_admission_port_never_reads_protected_sources():
    r = list(rig())
    r[4] = None
    with pytest.raises(SelectionAdmissionUnavailable):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_admission_service_failure_is_unavailable_not_denied():
    r = list(rig())
    class Unavailable:
        def authorize_selection_sources(self, **kwargs):
            raise ConnectionError("configured trust service unavailable")
    r[4] = Unavailable()
    with pytest.raises(SelectionAdmissionUnavailable):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_byte_reader_rejects_malicious_overread_and_invalid_profile():
    class OverReader:
        def read(self, requested):
            return b"a" * (requested + 1)
    limits = rig()[6]
    with pytest.raises(SelectionSourceContractError):
        bounded_source_bytes(OverReader(), limits=limits)
    from dataclasses import replace
    with pytest.raises(SelectorResourceLimitError):
        bounded_source_bytes(BytesIO(b"a"), limits=replace(limits, max_source_bytes=10**20))


def test_caller_cannot_widen_limits_without_fresh_trusted_admission():
    from dataclasses import replace
    r = list(rig(limit_rules=3))
    r[6] = replace(r[6], max_policy_rules=256)  # Within global ceiling, not approved for this operation.
    with pytest.raises(SelectionAdmissionDenied):
        run(tuple(r))
    assert not r[1].calls and not r[2].header_reads and not r[3].calls


def test_exact_upper_rule_limit_is_finite_and_keeps_valid_path_available():
    rules = [EvaluatorSelectionRule("SHORT_TEXT" if i == 0 else f"TYPE_{i}",
                                    "en", ContextPolicy.DIRECT, _capability_ref())
             for i in range(256)]
    r = rig(rules=rules, limit_rules=256, limit_chars=16384)
    selected = run(r)
    assert selected.selected_capability_ref == _capability_ref()
    assert r[2].yielded == 256


def test_admitted_policy_reference_is_snapshotted_before_source_side_effects():
    r = list(rig())
    original_header = r[2].read_policy_header
    def mutate_callers_config_after_admission():
        # A frozen dataclass's object-level mutation is possible from shared
        # Python aliases. It must not rewrite the already-admitted operation.
        object.__setattr__(r[5], "expected_policy_ref", EvaluatorSelectionPolicyRef("wrong", 99))
        return original_header()
    r[2].read_policy_header = mutate_callers_config_after_admission
    selected = run(tuple(r))
    assert selected.policy_ref == EvaluatorSelectionPolicyRef("routing-policy", 2)
    assert r[5].expected_policy_ref == EvaluatorSelectionPolicyRef("wrong", 99)
