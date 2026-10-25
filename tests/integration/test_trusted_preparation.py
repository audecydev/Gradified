"""Trusted PRE root custody: identity and admitted policy precede source IO."""
import io
import json
from dataclasses import replace

import pytest

from grading.integration import evidence_ingress
from grading.integration.trusted_preparation import (
    PreparationRequest, PreparationSourceSnapshot, PreparationScopeRejected,
    PreparationSourceContractError, PreparationSourceUnavailable,
    PreparationResourceLimitError, PreparedWithSourceCustody,
    prepare_from_trusted_source,
)
from tests.integration.test_choice_binding import _prepared


def _payload(questions=1):
    return json.dumps({
        "schema_version": "1", "submission_ref": "SUB-1", "ocr_provenance": "fixture-ocr",
        "questions": [
            {"question_id": "Q1" if i == 0 else f"Q{i+1}", "answer_scope_ref": f"SCOPE-{i+1}",
             "warnings": [], "blocks": [{
                 "block_id": f"EVIDENCE-{i+1}", "type": "TEXT", "content": "B",
                 "language": "en", "confidence": None, "confidence_status": "UNAVAILABLE",
                 "state": "ACTIVE", "page": 1,
                 "location": {"status": "UNAVAILABLE", "bbox": None},
                 "reading_order": 1, "asset_ref": None,
             }]}
            for i in range(questions)
        ],
    }).encode()


class _Port:
    def __init__(self, snapshot, payload):
        self.snapshot = snapshot
        self.payload = payload
        self.calls = []

    def resolve_preparation(self, *, request):
        self.calls.append("resolve")
        return self.snapshot


def _setup(payload=None):
    bound = _prepared()
    context = bound.context
    request = PreparationRequest(
        tenant_ref="TENANT-1", session_ref="SESSION-1",
        grading_run_id=context.grading_run_id, submission_ref=context.submission_ref,
        exam_ref=context.exam_ref, grading_spec_ref=context.grading_spec_ref,
        question_id=bound.question_authority.question_id,
    )
    port = _Port(None, _payload() if payload is None else payload)

    def opener():
        port.calls.append("open")
        return io.BytesIO(port.payload)

    port.snapshot = PreparationSourceSnapshot(
        tenant_ref="TENANT-1", session_ref="SESSION-1", context=context,
        paper_authority=bound.paper_authority,
        question_authority=bound.question_authority,
        admission_policy=replace(
            bound.admitted_evidence.effective_policy_snapshot, max_json_nodes=1000,
        ),
        source_artifact_ref="ARTIFACT-1", open_evidence=opener,
    )
    return request, port


def test_valid_source_custody_and_real_p0a_p0b():
    request, port = _setup()
    receipt = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert type(receipt) is PreparedWithSourceCustody
    assert receipt.request is not request
    assert receipt.bound.context is not port.snapshot.context
    assert receipt.bound.context.submission_ref == "SUB-1"
    assert receipt.bound.admitted_evidence.effective_policy_snapshot is not port.snapshot.admission_policy
    assert receipt.bound.admitted_evidence.effective_policy_snapshot == port.snapshot.admission_policy
    assert receipt.bound.admitted_evidence.source_artifact_ref == "ARTIFACT-1"
    assert port.calls == ["resolve", "open"]


@pytest.mark.parametrize("field,value", [
    ("tenant_ref", "TENANT-FOREIGN"),
    ("session_ref", "SESSION-FOREIGN"),
])
def test_foreign_scope_rejected_before_evidence_open(field, value):
    request, port = _setup()
    port.snapshot = replace(port.snapshot, **{field: value})
    with pytest.raises(PreparationScopeRejected):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_context_scope_mismatch_rejected_before_read():
    request, port = _setup()
    new_context = replace(port.snapshot.context, submission_ref="SUB-SUBSTITUTED")
    port.snapshot = replace(port.snapshot, context=new_context)
    with pytest.raises(PreparationScopeRejected):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_missing_trusted_resolver_fails_closed():
    request, port = _setup()
    with pytest.raises(PreparationSourceUnavailable):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=None)
    assert port.calls == []


def test_policy_inflation_after_resolution_cannot_expand_admission():
    request, port = _setup(_payload(6))
    original = port.snapshot.admission_policy
    def inflate_and_open():
        port.calls.append("open")
        object.__setattr__(original, "max_questions", 6)
        return io.BytesIO(port.payload)
    port.snapshot = replace(port.snapshot, open_evidence=inflate_and_open)
    with pytest.raises(evidence_ingress.NormalizedEvidenceResourceError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve", "open"]


def test_original_request_drift_during_resolver_does_not_change_saved_scope():
    request, port = _setup()
    def drift(*, request):
        port.calls.append("resolve")
        object.__setattr__(request, "submission_ref", "SUB-CHANGED")
        return port.snapshot
    # The source receives a detached copy, so the submitted request is never changed.
    port.resolve_preparation = drift
    result = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert result.request.submission_ref == "SUB-1"
    assert result.bound.context.submission_ref == "SUB-1"
    assert request.submission_ref == "SUB-1"
    assert port.calls == ["resolve", "open"]


def test_drift_of_original_source_context_during_open_has_no_effect():
    request, port = _setup()
    context = port.snapshot.context
    def mutate_context():
        port.calls.append("open")
        object.__setattr__(context, "submission_ref", "WRONG")
        return io.BytesIO(port.payload)
    port.snapshot = replace(port.snapshot, open_evidence=mutate_context)
    result = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert result.bound.context.submission_ref == "SUB-1"
    assert result.request.submission_ref == "SUB-1"


def test_reader_never_requests_more_than_finite_chunk_and_closes():
    request, port = _setup()
    sizes = []
    class Reader(io.BytesIO):
        def read(self, size=-1):
            sizes.append(size)
            return super().read(size)
        def close(self):
            sizes.append("closed")
            super().close()
    port.snapshot = replace(port.snapshot, open_evidence=lambda: Reader(port.payload))
    prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert all(type(s) is int and 0 < s <= 65_536 for s in sizes[:-1])
    assert sizes[-1] == "closed"


def test_preflight_rejects_overlong_raw_stream_and_closes():
    request, port = _setup()
    policy = replace(port.snapshot.admission_policy, max_raw_bytes=50)
    port.snapshot = replace(port.snapshot, admission_policy=policy)
    with pytest.raises(PreparationResourceLimitError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve", "open"]


def test_reader_ignoring_length_rejected():
    request, port = _setup()
    class BrokenReader:
        def read(self, wanted):
            return b"x" * (wanted + 1)
        def close(self):
            pass
    port.snapshot = replace(port.snapshot, open_evidence=BrokenReader)
    with pytest.raises(PreparationResourceLimitError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)


def test_private_reader_error_is_not_in_user_exception_chain():
    request, port = _setup()
    secret = "PRIVATE_STUDENT_RESPONSE_9f8e"
    def broken_reader():
        raise RuntimeError(secret)
    port.snapshot = replace(port.snapshot, open_evidence=broken_reader)
    with pytest.raises(PreparationSourceUnavailable) as info:
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    err = info.value
    assert err.__cause__ is None and err.__context__ is None
    import traceback
    assert secret not in "".join(traceback.format_exception(err))


def test_bad_policy_rejected_before_evidence_open():
    request, port = _setup()
    policy = port.snapshot.admission_policy
    object.__setattr__(policy, "max_questions", None)
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_cannot_construct_receipt_directly():
    with pytest.raises(TypeError):
        PreparedWithSourceCustody()


def test_paper_question_missing_before_protected_evidence_read():
    request, port = _setup()
    paper = port.snapshot.paper_authority
    object.__setattr__(paper, "expected_questions", ())
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_corrupted_paper_collection_fails_before_open():
    request, port = _setup()
    paper = port.snapshot.paper_authority
    object.__setattr__(paper, "expected_questions", list(paper.expected_questions))
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_mutating_private_policy_after_open_does_not_alter_saved_policy():
    request, port = _setup()
    policy = port.snapshot.admission_policy
    expected_max = policy.max_questions
    def opener():
        port.calls.append("open")
        object.__setattr__(policy, "max_questions", expected_max + 3)
        return io.BytesIO(port.payload)
    port.snapshot = replace(port.snapshot, open_evidence=opener)
    receipt = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert receipt.bound.admitted_evidence.effective_policy_snapshot.max_questions == expected_max


def test_unavailable_resolver_does_not_open_private_source():
    request, port = _setup()
    secret = "PRIVATE_STUDENT_DATA_i39p"
    def broken(*, request):
        raise RuntimeError(secret)
    port.resolve_preparation = broken
    with pytest.raises(PreparationSourceUnavailable) as info:
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == []
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert secret not in str(info.value)


def test_poisoned_source_tenant_equality_never_invoked():
    request, port = _setup()
    class Poison:
        def __eq__(self, other):
            pytest.fail("hostile source equality must not execute")
    port.snapshot = replace(port.snapshot, tenant_ref=Poison())
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_poisoned_question_identity_equality_never_invoked():
    request, port = _setup()
    class Poison:
        def __eq__(self, other):
            pytest.fail("hostile question equality must not execute")
    object.__setattr__(port.snapshot.question_authority, "question_id", Poison())
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ["resolve"]


def test_source_authority_mutated_during_read_cannot_change_question_scope():
    request, port = _setup(_payload(2))
    question = port.snapshot.question_authority
    paper = port.snapshot.paper_authority
    original_question = question.question_id
    def swap_on_open():
        port.calls.append('open')
        object.__setattr__(question, 'question_id', 'Q2')
        from dataclasses import replace as dc_replace
        object.__setattr__(paper, 'expected_questions', (paper.expected_questions[0], dc_replace(paper.expected_questions[0], question_id='Q2')))
        return io.BytesIO(port.payload)
    port.snapshot = replace(port.snapshot, open_evidence=swap_on_open)
    result = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert result.request.question_id == original_question
    assert result.bound.question_authority.question_id == original_question
    assert result.bound.paper_authority is not paper
    assert result.bound.question_authority is not question


def test_source_scoring_authority_mutated_during_read_cannot_change_bound_graph():
    request, port = _setup()
    question = port.snapshot.question_authority
    original_text = question.question_text
    def mutate_on_open():
        port.calls.append('open')
        object.__setattr__(question, 'question_text', 'TAMPERED ON OPEN')
        return io.BytesIO(port.payload)
    port.snapshot = replace(port.snapshot, open_evidence=mutate_on_open)
    result = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert result.bound.question_authority.question_text == original_text


def test_paper_duplicate_nonselected_question_denied_before_protected_open():
    request, port = _setup()
    paper = port.snapshot.paper_authority
    second = replace(paper.expected_questions[0], question_id='Q2')
    object.__setattr__(paper, 'expected_questions', (paper.expected_questions[0], second, second))
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ['resolve']


def test_paper_contradictory_score_bounds_denied_before_open():
    from decimal import Decimal
    from grading.contracts.scoring_decimal import ScoringDecimal
    request, port = _setup()
    object.__setattr__(port.snapshot.paper_authority, 'minimum_score', ScoringDecimal(Decimal('6')))
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ['resolve']


@pytest.mark.parametrize('location,field', [
    ('request', 'tenant_ref'), ('request', 'question_id'),
    ('request', 'grading_spec_ref'), ('source', 'tenant_ref'),
    ('source', 'open_evidence'), ('context', 'submission_ref'),
    ('paper', 'expected_questions'), ('paper', 'grading_spec_ref'),
    ('question', 'question_id'), ('policy', 'max_raw_bytes'),
])
def test_missing_source_fields_are_typed_and_private(location, field):
    import traceback
    request, port = _setup()
    target = {
        'request': request, 'source': port.snapshot, 'context': port.snapshot.context,
        'paper': port.snapshot.paper_authority, 'question': port.snapshot.question_authority,
        'policy': port.snapshot.admission_policy,
    }[location]
    object.__delattr__(target, field)
    canary = 'PRIVATE_STUDENT_ANSWER_83c77'
    try:
        raise ValueError(canary)
    except ValueError:
        with pytest.raises(PreparationSourceContractError) as caught:
            prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    err = caught.value
    assert err.__cause__ is None and err.__context__ is None
    assert canary not in ''.join(traceback.format_exception(err))
    assert 'open' not in port.calls


@pytest.mark.parametrize('field', [
    'tenant_ref', 'session_ref', 'grading_run_id',
    'submission_ref', 'exam_ref', 'question_id',
])
def test_oversized_request_identifiers_rejected_before_resolver(field):
    request, port = _setup()
    object.__setattr__(request, field, 'A' * 65)
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == []


def test_request_identifier_accepted_at_exact_trusted_ceiling():
    request, port = _setup()
    object.__setattr__(request, 'tenant_ref', 'A' * 64)
    from dataclasses import replace
    port.snapshot = replace(port.snapshot, tenant_ref='A' * 64)
    result = prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert result.request.tenant_ref == 'A' * 64


@pytest.mark.parametrize('location,field', [
    ('source', 'tenant_ref'), ('source', 'session_ref'),
    ('context', 'grading_run_id'), ('context', 'submission_ref'),
    ('context', 'exam_ref'), ('question', 'question_id'),
    ('paper', 'expected_questions'),
])
def test_oversized_source_identifiers_denied_before_read(location, field):
    request, port = _setup()
    if location == 'paper':
        paper = port.snapshot.paper_authority
        object.__setattr__(paper, field, (replace(paper.expected_questions[0], question_id='A' * 65),))
    elif location == 'source':
        port.snapshot = replace(port.snapshot, **{field: 'A' * 65})
    else:
        target = port.snapshot.context if location == 'context' else port.snapshot.question_authority
        object.__setattr__(target, field, 'A' * 65)
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ['resolve']


def test_oversized_spec_identity_denied_before_resolver():
    request, port = _setup()
    object.__setattr__(request.grading_spec_ref, 'id', 'A' * 65)
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == []


@pytest.mark.parametrize('bad', [None, 0, -1, 64.0, True])
def test_no_untrusted_or_absent_identifier_ceiling(bad):
    request, port = _setup()
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=bad, request=request, source=port)
    assert port.calls == []


def test_selected_question_reference_mismatch_denied_before_read():
    request, port = _setup()
    question = port.snapshot.question_authority
    rubric = question.scoring_authority.rubric
    object.__setattr__(rubric, 'rubric_id', 'UNRELATED')
    with pytest.raises(PreparationScopeRejected):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ['resolve']


def test_size_limit_error_preserved_when_reader_close_also_fails():
    request, port = _setup()
    from dataclasses import replace
    port.snapshot = replace(port.snapshot, admission_policy=replace(port.snapshot.admission_policy, max_raw_bytes=50))
    class BrokenReader:
        def read(self, amount):
            return b'x' * (amount + 1)
        def close(self):
            raise RuntimeError('PRIVATE-CLEANUP-ERROR')
    port.snapshot = replace(port.snapshot, open_evidence=BrokenReader)
    with pytest.raises(PreparationResourceLimitError) as caught:
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    import traceback
    assert 'PRIVATE-CLEANUP-ERROR' not in ''.join(traceback.format_exception(caught.value))


@pytest.mark.parametrize('record', ['request', 'context', 'question', 'paper'])
def test_corrupted_grading_spec_ref_is_typed_before_read(record):
    request, port = _setup()
    if record == 'request':
        ref = request.grading_spec_ref
    else:
        ref = getattr(port.snapshot, {'context':'context', 'question':'question_authority', 'paper':'paper_authority'}[record]).grading_spec_ref
    object.__setattr__(ref, 'version', 0)
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert 'open' not in port.calls


def test_overlong_artifact_ref_denied_by_root_limit_before_open():
    request, port = _setup()
    port.snapshot = replace(port.snapshot, source_artifact_ref='A' * 65)
    with pytest.raises(PreparationSourceContractError):
        prepare_from_trusted_source(max_identifier_characters=64, request=request, source=port)
    assert port.calls == ['resolve']


@pytest.mark.parametrize("field", ["rubric_id", "policy_id"])
def test_authoring_identity_mismatch_rejected_before_protected_evidence_open(field):
    """Frozen question evidence binding also rejects this, but PRE must do so before private I/O."""
    import traceback

    request, port = _setup()
    question = port.snapshot.question_authority
    changed_content = replace(question.rubric_content, **{field: "OTHER-AUTHORITY"})
    port.snapshot = replace(
        port.snapshot, question_authority=replace(question, rubric_content=changed_content),
    )

    with pytest.raises(PreparationScopeRejected) as caught:
        prepare_from_trusted_source(
            request=request, source=port, max_identifier_characters=64,
        )

    assert port.calls == ["resolve"], "Private evidence must remain unopened"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "OTHER-AUTHORITY" not in "".join(traceback.format_exception(caught.value))


def test_consistent_authoring_identity_admits_and_binds():
    request, port = _setup()
    prepared = prepare_from_trusted_source(
        request=request, source=port, max_identifier_characters=64,
    ).bound
    assert port.calls == ["resolve", "open"]
    assert (prepared.question_authority.rubric_content.rubric_id
            == prepared.question_authority.scoring_authority.rubric.rubric_id)
    assert (prepared.question_authority.rubric_content.policy_id
            == prepared.question_authority.scoring_authority.policy.policy_id)


@pytest.mark.parametrize(("field", "bad_value"), [
    ("context_policy", "DIRECT"),
    ("context_policy", "NOT_A_POLICY"),
    ("question_text", 123),
    ("question_text", None),
])
def test_malformed_question_fields_never_open_protected_evidence(field, bad_value):
    """Reject source-owned fields already invalid under question evidence binding before evidence IO."""
    import traceback

    request, port = _setup()
    object.__setattr__(port.snapshot.question_authority, field, bad_value)

    with pytest.raises(PreparationSourceContractError) as caught:
        prepare_from_trusted_source(
            request=request, source=port, max_identifier_characters=64,
        )

    assert port.calls == ["resolve"]
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "PRIVATE_STUDENT_PAYLOAD" not in "".join(traceback.format_exception(caught.value))


def test_canonical_question_policy_and_text_remain_valid_before_open():
    from grading.active_question_authority import ContextPolicy

    request, port = _setup()
    question = port.snapshot.question_authority
    object.__setattr__(question, "context_policy", ContextPolicy.DIRECT)
    object.__setattr__(question, "question_text", "")  # question evidence binding permits exact empty str.
    result = prepare_from_trusted_source(
        request=request, source=port, max_identifier_characters=64,
    )
    assert result.bound.question_authority.context_policy is ContextPolicy.DIRECT
    assert result.bound.question_authority.question_text == ""
    assert port.calls == ["resolve", "open"]


def test_malformed_question_field_in_ambient_private_error_has_clean_traceback():
    import traceback

    request, port = _setup()
    object.__setattr__(port.snapshot.question_authority, "question_text", None)
    try:
        raise RuntimeError("PRIVATE_STUDENT_PAYLOAD_ambient")
    except RuntimeError:
        with pytest.raises(PreparationSourceContractError) as caught:
            prepare_from_trusted_source(
                request=request, source=port, max_identifier_characters=64,
            )
    assert port.calls == ["resolve"]
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "PRIVATE_STUDENT_PAYLOAD_ambient" not in "".join(
        traceback.format_exception(caught.value)
    )
