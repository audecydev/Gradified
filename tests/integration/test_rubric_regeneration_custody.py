"""Source-qualified draft custody, bounded input and effect-time CAS tests."""
from dataclasses import replace

from grading.rubric.regeneration_custody import (
    AuthorizedRegenerationRead, ConditionalDraftWrite, CustodyState,
    DraftWriteReceipt, DraftWriteState, propose_and_persist_regeneration,
    recover_regeneration_write,
)
from grading.rubric.lifecycle import create_initial_version, revise_version, RubricLifecycleState
from grading.rubric.models import QuestionRubricAuthoringContent
from tests.support.rubric_authoring import simple_basis, simple_content, authoring_test_limits, criterion


class QualifiedSourceFixture:
    """TEST DOUBLE. Real teacher/ancestry/question authenticity is external."""
    def __init__(self, current=None, *, limits=None):
        self.base = simple_content()
        self.current = current or create_initial_version(simple_basis(), self.base)
        self.limits = limits or authoring_test_limits()
        self.calls = 0
        self.throw = False
        self.override = None

    def read_authorized(self, *, actor_ref, rubric_ref):
        self.calls += 1
        if self.throw: raise OSError('read unavailable')
        if self.override is not None: return self.override
        if actor_ref != 'teacher-1' or rubric_ref != 'R-Q1': return None
        return AuthorizedRegenerationRead(actor_ref, rubric_ref,
            f'current-{self.current.version}', 'original-generated-1', 'question-v4',
            self.base, self.current, simple_basis(), self.limits)


class AtomicStoreFixture:
    """TEST DOUBLE: effect-time revision/teacher/question comparison + op key."""
    def __init__(self):
        self.calls = 0
        self.lookups = 0
        self.current_ref = 'current-1'
        self.question_ref = 'question-v4'
        self.teacher_ref = 'teacher-1'
        self.baseline_ref = 'original-generated-1'
        self.operations = {}
        self.throw_after_commit = False
        self.bad_receipt = False
        self.raise_before = False

    def compare_and_persist(self, request):
        self.calls += 1
        if self.raise_before: raise OSError('unknown before/after contact')
        if request.operation_ref in self.operations:
            prior = self.operations[request.operation_ref]
            outcome = prior if prior.request == request else DraftWriteReceipt(DraftWriteState.STALE, request)
        elif (request.authority.current_revision_ref != self.current_ref
              or request.authority.question_revision_ref != self.question_ref
              or request.authority.actor_ref != self.teacher_ref
              or request.authority.baseline_revision_ref != self.baseline_ref):
            outcome = DraftWriteReceipt(DraftWriteState.STALE, request)
        else:
            outcome = DraftWriteReceipt(DraftWriteState.COMMITTED, request)
            self.operations[request.operation_ref] = outcome
            self.current_ref = f'current-{request.draft.version}'
        if self.throw_after_commit:
            raise TimeoutError('ack lost after effect')
        if self.bad_receipt:
            return DraftWriteReceipt(DraftWriteState.COMMITTED,
                                     replace(request, operation_ref='foreign-op'))
        return outcome

    def lookup_operation(self, request):
        self.lookups += 1
        return self.operations.get(request.operation_ref)


def regenerate(source=None, store=None, generated=None, **kwargs):
    src = source or QualifiedSourceFixture()
    db = store or AtomicStoreFixture()
    fresh = generated or replace(src.base, criteria=(
        replace(src.base.criteria[0], evidence_requirement='new generator requirement'),
        src.base.criteria[1]))
    return propose_and_persist_regeneration(source=src, store=db,
        actor_ref=kwargs.get('actor_ref','teacher-1'), rubric_ref=kwargs.get('rubric_ref','R-Q1'),
        operation_ref=kwargs.get('operation_ref','regen-op-1'), newly_generated=fresh,
        approved_limits=kwargs.get('approved_limits', src.limits))


def test_genuine_regeneration_persists_only_new_draft_and_no_approval():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    out=regenerate(src,db)
    assert out.state is CustodyState.STORED and db.calls==1
    assert out.request.authority.current_revision_ref == 'current-1'
    assert out.request.authority.question_revision_ref == 'question-v4'
    assert out.request.draft.version==2
    assert out.request.draft.state is RubricLifecycleState.DRAFT
    assert out.request.draft.approval is None and out.request.draft.compilation is None
    assert not out.authorizes_activation and not out.authorizes_grading


def test_live_current_revision_changes_with_identical_content_before_write():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    db.current_ref='current-2'  # content hash is the SAME; version token is not.
    out=regenerate(src,db)
    assert out.state is CustodyState.BLOCKED and db.calls==1


def test_finalized_question_revision_changed_with_identical_question_content():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    db.question_ref='question-v5'
    assert regenerate(src,db).state is CustodyState.BLOCKED


def test_revoked_actor_or_mismatched_baseline_rejected_at_effect():
    for field,new in [('teacher_ref','revoked'),('baseline_ref','new-ancestry')]:
        src,db=QualifiedSourceFixture(),AtomicStoreFixture()
        setattr(db,field,new)
        assert regenerate(src,db).state is CustodyState.BLOCKED


def test_teacher_specific_edits_are_preserved_and_never_approved():
    base=simple_content()
    current=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,criteria=(replace(base.criteria[0],evidence_requirement='TEACHER'),base.criteria[1])))
    src=QualifiedSourceFixture(current)
    db=AtomicStoreFixture();db.current_ref='current-2'
    fresh=replace(base,criteria=(base.criteria[0],replace(base.criteria[1],operational_description='GENERATOR')))
    out=regenerate(src,db,fresh)
    assert out.state is CustodyState.STORED
    assert out.request.draft.version==3 and out.request.draft.approval is None
    assert out.request.draft.content.criteria[0].evidence_requirement=='TEACHER'
    assert out.request.draft.content.criteria[1].operational_description=='GENERATOR'


def test_generated_teacher_conflict_does_not_contact_store():
    base=simple_content()
    teacher=revise_version(create_initial_version(simple_basis(),base),simple_basis(),
        replace(base,criteria=(replace(base.criteria[0],evidence_requirement='TEACHER'),base.criteria[1])))
    src=QualifiedSourceFixture(teacher);db=AtomicStoreFixture()
    fresh=replace(base,criteria=(replace(base.criteria[0],evidence_requirement='GENERATOR'),base.criteria[1]))
    out=regenerate(src,db,fresh)
    assert out.state is CustodyState.CONFLICT and out.conflicts==('criterion:C1',)
    assert db.calls==0


def test_unchanged_content_does_not_contact_store():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    assert regenerate(src,db,src.base).state is CustodyState.UNCHANGED and db.calls==0


def test_oversize_inputs_rejected_before_merge_and_store():
    small_limits=replace(authoring_test_limits(),max_criteria=1)
    src,db=QualifiedSourceFixture(limits=small_limits),AtomicStoreFixture()
    assert regenerate(src,db).state is CustodyState.BLOCKED and db.calls==0


def test_oversize_generated_content_rejected_without_write():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    fresh=replace(src.base,criteria=tuple(criterion(f'N{x}',0) for x in range(21)))
    assert regenerate(src,db,fresh).state is CustodyState.BLOCKED and db.calls==0


def test_unauthorized_actor_returns_blocked_before_write():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    assert regenerate(src,db,actor_ref='foreign-teacher').state is CustodyState.BLOCKED
    assert db.calls==0


def test_malformed_source_record_is_not_authority():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    src.override=object()
    assert regenerate(src,db).state is CustodyState.BLOCKED and db.calls==0


def test_source_read_exception_is_unknown_and_write_uncontacted():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture();src.throw=True
    assert regenerate(src,db).state is CustodyState.SOURCE_UNAVAILABLE and db.calls==0


def test_lost_ack_preserves_request_and_read_only_recovers_original():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture();db.throw_after_commit=True
    out=regenerate(src,db)
    assert out.state is CustodyState.UNKNOWN and out.request is not None and db.calls==1
    recovered=recover_regeneration_write(store=db,original=out.request)
    assert recovered.state is CustodyState.STORED and recovered.request==out.request
    assert db.calls==1 and db.lookups==1


def test_ambiguous_store_exception_without_commit_is_never_retried():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture();db.raise_before=True
    out=regenerate(src,db)
    assert out.state is CustodyState.UNKNOWN and db.calls==1
    assert recover_regeneration_write(store=db,original=out.request).state is CustodyState.UNKNOWN
    assert db.calls==1


def test_mismatched_receipt_never_claims_commit():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture();db.bad_receipt=True
    out=regenerate(src,db)
    assert out.state is CustodyState.UNKNOWN and out.request is not None


def test_conflicting_idempotency_key_is_rejected_by_qualified_store():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    first=regenerate(src,db)
    assert first.state is CustodyState.STORED
    # stale source and same key but incompatible regenerated draft
    different=replace(src.base,criteria=(replace(src.base.criteria[0],operational_description='DIFFERENT'),src.base.criteria[1]))
    assert regenerate(src,db,different).state is CustodyState.BLOCKED
    assert len(db.operations)==1


def test_invalid_command_never_reads_source():
    src,db=QualifiedSourceFixture(),AtomicStoreFixture()
    assert regenerate(src,db,operation_ref='').state is CustodyState.BLOCKED
    assert src.calls==0 and db.calls==0


class MutatingStoreFixture(AtomicStoreFixture):
    """Hostile installed callback: frozen dataclasses can still be altered."""
    def __init__(self, field, *, unknown=False):
        super().__init__()
        self.field = field
        self.unknown = unknown

    def compare_and_persist(self, request):
        self.calls += 1
        if self.field == 'actor':
            object.__setattr__(request.authority, 'actor_ref', 'different-teacher')
        elif self.field == 'draft_version':
            object.__setattr__(request.draft, 'version', 999)
        elif self.field == 'current_revision':
            object.__setattr__(request.authority, 'current_revision_ref', 'foreign-current')
        if self.unknown:
            raise TimeoutError('write outcome not known')
        return DraftWriteReceipt(DraftWriteState.COMMITTED, request)


def test_write_callback_actor_mutation_cannot_claim_stored():
    out = regenerate(QualifiedSourceFixture(), MutatingStoreFixture('actor'))
    assert out.state is CustodyState.UNKNOWN
    assert out.request.authority.actor_ref == 'teacher-1'


def test_write_callback_draft_mutation_cannot_claim_stored():
    out = regenerate(QualifiedSourceFixture(), MutatingStoreFixture('draft_version'))
    assert out.state is CustodyState.UNKNOWN
    assert out.request.draft.version == 2


def test_ambiguous_write_callback_retains_original_revision_for_recovery():
    out = regenerate(QualifiedSourceFixture(), MutatingStoreFixture('current_revision', unknown=True))
    assert out.state is CustodyState.UNKNOWN
    assert out.request.authority.current_revision_ref == 'current-1'


class CommittedLookupFixture:
    def __init__(self, *, mutate=False):
        self.lookups = 0
        self.mutate = mutate

    def lookup_operation(self, request):
        self.lookups += 1
        if self.mutate:
            object.__setattr__(request.authority, 'baseline_revision_ref', 'foreign-ancestor')
        return DraftWriteReceipt(DraftWriteState.COMMITTED, request)


def _genuine_original_request():
    out = regenerate(QualifiedSourceFixture(), AtomicStoreFixture())
    assert out.state is CustodyState.STORED
    return out.request


def test_recovery_rejects_impossible_version_before_lookup():
    original = _genuine_original_request()
    altered = replace(original, draft=replace(original.draft, version=77))
    store = CommittedLookupFixture()
    assert recover_regeneration_write(store=store, original=altered).state is CustodyState.BLOCKED
    assert store.lookups == 0


def test_recovery_rejects_foreign_draft_before_lookup():
    original = _genuine_original_request()
    foreign = replace(original.draft.content, rubric_id='foreign-rubric')
    from grading.rubric.lifecycle import create_initial_version
    invalid = replace(original, draft=create_initial_version(simple_basis(), foreign))
    store = CommittedLookupFixture()
    assert recover_regeneration_write(store=store, original=invalid).state is CustodyState.BLOCKED
    assert store.lookups == 0


def test_recovery_callback_mutation_cannot_claim_stored():
    store = CommittedLookupFixture(mutate=True)
    out = recover_regeneration_write(store=store, original=_genuine_original_request())
    assert out.state is CustodyState.UNKNOWN
    assert out.request.authority.baseline_revision_ref == 'original-generated-1'


def test_genuine_original_read_only_recovery_control():
    store = CommittedLookupFixture()
    out = recover_regeneration_write(store=store, original=_genuine_original_request())
    assert out.state is CustodyState.STORED and store.lookups == 1


def test_recovery_rejects_unchanged_content_and_question_before_lookup():
    original = _genuine_original_request()
    current = original.authority.current_teacher
    impossible = replace(original.draft,
        content=current.content, source_content_hash=current.source_content_hash,
        finalized_question=current.finalized_question,
        finalized_question_hash=current.finalized_question_hash)
    store = CommittedLookupFixture()
    out = recover_regeneration_write(store=store, original=replace(original, draft=impossible))
    assert out.state is CustodyState.BLOCKED and store.lookups == 0


def test_recovery_rejects_noninteger_draft_version_before_lookup():
    from copy import deepcopy
    original = deepcopy(_genuine_original_request())
    object.__setattr__(original.draft, 'version', 2.0)
    store = CommittedLookupFixture()
    assert recover_regeneration_write(store=store, original=original).state is CustodyState.BLOCKED
    assert store.lookups == 0


def test_recovery_rejects_noninteger_predecessor_version_before_lookup():
    from copy import deepcopy
    original = deepcopy(_genuine_original_request())
    object.__setattr__(original.authority.current_teacher, 'version', 1.0)
    store = CommittedLookupFixture()
    assert recover_regeneration_write(store=store, original=original).state is CustodyState.BLOCKED
    assert store.lookups == 0


# Source-external locally provable continuity cases; the real record authority
# and durable effect atomicity remain separate adapter qualification gates.
def test_current_version_full_basis_must_match_separate_finalized_basis():
    from dataclasses import replace
    from grading.contracts.scoring_decimal import ScoringDecimal
    from decimal import Decimal
    src, db = QualifiedSourceFixture(), AtomicStoreFixture()
    good = src.read_authorized(actor_ref='teacher-1', rubric_ref='R-Q1')
    other_basis = replace(good.finalized_question, max_marks=ScoringDecimal(Decimal('99')))
    src.override = replace(good, finalized_question=other_basis)
    assert regenerate(src, db).state is CustodyState.BLOCKED
    assert db.calls == 0


def test_unqualified_or_permissive_source_resource_policy_rejected_before_write():
    from dataclasses import replace
    src, db = QualifiedSourceFixture(), AtomicStoreFixture()
    verified_limits = src.limits
    src.limits = replace(verified_limits, max_criteria=verified_limits.max_criteria + 10000)
    assert regenerate(src, db, approved_limits=verified_limits).state is CustodyState.BLOCKED
    assert db.calls == 0
    # No separately approved system policy means no positive operation.
    assert propose_and_persist_regeneration(source=src, store=db, actor_ref='teacher-1',
       rubric_ref='R-Q1', operation_ref='new-op',
       newly_generated=src.base).state is CustodyState.BLOCKED
    assert src.calls == 1


def test_source_callback_cannot_substitute_original_generator_input():
    src, db = QualifiedSourceFixture(), AtomicStoreFixture()
    fresh = replace(src.base, criteria=(replace(src.base.criteria[0],
        evidence_requirement='expected generator edit'), src.base.criteria[1]))
    original = fresh.criteria[0].evidence_requirement
    default_read = src.read_authorized
    def mutating_read(*, actor_ref, rubric_ref):
        object.__setattr__(fresh.criteria[0], 'evidence_requirement', 'unexpected mutation')
        return default_read(actor_ref=actor_ref, rubric_ref=rubric_ref)
    src.read_authorized = mutating_read
    outcome = regenerate(src, db, fresh)
    assert outcome.state is CustodyState.BLOCKED and db.calls == 0
    assert original != fresh.criteria[0].evidence_requirement


def test_source_read_failure_distinct_from_unknown_write_effect():
    src, db = QualifiedSourceFixture(), AtomicStoreFixture()
    src.throw = True
    outcome = regenerate(src, db)
    assert outcome.state is CustodyState.SOURCE_UNAVAILABLE
    assert outcome.request is None and db.calls == 0


def test_source_callback_cannot_mutate_approved_resource_policy():
    src, db = QualifiedSourceFixture(), AtomicStoreFixture()
    # Source and engine configuration may happen to refer to the same frozen
    # object: object.__setattr__ can still rewrite it during an installed call.
    trusted = src.limits
    base_read = src.read_authorized
    def mutating_read(*, actor_ref, rubric_ref):
        object.__setattr__(trusted, 'max_criteria', trusted.max_criteria + 10000)
        return base_read(actor_ref=actor_ref, rubric_ref=rubric_ref)
    src.read_authorized = mutating_read
    out = regenerate(src, db, approved_limits=trusted)
    assert out.state is CustodyState.BLOCKED and db.calls == 0
