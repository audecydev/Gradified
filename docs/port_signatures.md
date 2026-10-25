# Host-facing interface signatures

These declarations are extracted from the installed source so adapter authors can locate exact parameters and return types. This reference does **not** supply authentic actors, academic approvals, model credentials, durable transactions or issuer implementations.

A constructor may check additional invariant relationships beyond a signature. The implementation and its exceptions remain authoritative.

## `src/grading/integration/production_paper_operations.py`

### `ProductionPaperOperations`

```python
def __init__(self, *, admission: ProductionPaperAdmissionComposer, promotion: ProductionPaperPromotion, lifecycle: ProductionPaperLifecycle | None=None, retry: ProductionGradedPaperRetry | None=None, enabled_kinds: tuple[PaperOperationKind, ...], max_identifier_characters: int, max_questions: int): ...
```

```python
def execute(self, *, request: PaperAdmissionRequest, kind: PaperOperationKind) -> PaperOperationObservation: ...
```

## `src/grading/integration/paper_readiness_admission.py`

### `PaperAdmissionRequest`

Record fields:

```python
    tenant_ref: str
    session_ref: str
    grading_run_id: str
    submission_ref: str
    exam_ref: str
    paper_ref: str
    set_ref: str
    grading_spec_ref: GradingSpecRef
```

### `PaperSelectionAuthority`

```python
def authorize_paper(self, *, actor: AuthenticatedActor, request: PaperAdmissionRequest) -> ApprovedPaperSelection: ...
```

### `PaperAnswerAuthority`

```python
def resolve_paper_readiness(self, *, approval: ApprovedPaperSelection) -> PaperReadinessRecord: ...
```

### `PaperRevisionAuthority`

```python
def confirm_paper_revision(self, *, approval: ApprovedPaperSelection, readiness: PaperReadinessRecord) -> PaperRevisionConfirmation: ...
```

### `ProductionPaperAdmissionComposer`

```python
def __init__(self, *, identity: IdentityAuthority, selections: PaperSelectionAuthority, answers: PaperAnswerAuthority, revisions: PaperRevisionAuthority, max_identifier_characters: int, max_questions: int) -> None: ...
```

```python
def admit(self, *, request: PaperAdmissionRequest) -> AdmittedPaperPlan: ...
```

## `src/grading/integration/evidence_ingress.py`

### `NormalizedEvidenceAdmissionPolicy`

Record fields:

```python
    admission_policy_identity: str
    max_raw_bytes: int
    max_json_depth: int
    max_json_nodes: int
    max_json_number_characters: int
    max_identifier_characters: int
    max_metadata_text_characters: int
    max_block_content_characters: int
    max_total_content_characters: int
    max_questions: int
    max_blocks_per_question: int
    max_total_blocks: int
    max_warnings_per_question: int
    max_location_coordinates: int
```

### `parse_normalized_evidence_payload`

```python
def parse_normalized_evidence_payload(*, raw_payload: bytes, policy: NormalizedEvidenceAdmissionPolicy, source_artifact_ref: str | None=None) -> AdmittedNormalizedEvidence: ...
```

## `src/grading/integration/authorized_preparation.py`

### `IdentityAuthority`

```python
def current_actor(self) -> AuthenticatedActor: ...
```

## `src/grading/integration/joint_effect_authority.py`

### `QualifiedJointEffectOwner`

```python
def claim_if_current(self, *, request: ConditionalEffectClaim) -> ConditionalEffectClaimResponse: ...
```

```python
def commit_if_current(self, *, request: ConditionalScoredCAS) -> ConditionalCASResponse: ...
```

## `src/grading/integration/whole_paper_cas.py`

### `AtomicWholePaperResultStateAuditStore`

```python
def commit_whole_paper(self, *, transaction: PaperCASTransaction, custody: PaperAttemptCustody) -> PaperCASDecision: ...
```

```python
def reconcile_whole_paper(self, *, transaction: PaperCASTransaction) -> PaperCASRecovery: ...
```

## `src/grading/integration/official_result_release.py`

### `ProductionGovernedResultRelease`

```python
def __init__(self, *, recovery: ProductionRecoveredOriginalGovernance, teacher_review: ProductionRecoveredTeacherReviewCandidate, effect_owner: QualifiedConditionalResultRelease, max_identifier_characters: int, feedback_candidate: ProductionRecoveredFeedbackCandidate | None=None, release_history: QualifiedConditionalReleaseHistory | None=None, original_intent_source: QualifiedOriginalReleaseIntentSource | None=None, intent_custody: QualifiedReleaseIntentCustody | None=None, prepared_resolver: QualifiedPreparedReleaseResolver | None=None): ...
```

```python
def transition(self, *, purpose: ReleasePurpose) -> ResultReleaseObservation: ...
```

```python
def reconcile(self, *, purpose: ReleasePurpose) -> ResultReleaseObservation: ...
```

```python
def reconcile_original(self, *, release: ReleaseOperationIdentity) -> ResultReleaseObservation: ...
```

```python
def resolve_prepared(self, *, release: ReleaseOperationIdentity) -> ResultReleaseObservation: ...
```

### `QualifiedReleaseIntentCustody`

```python
def establish_original_intent(self, *, request: ConditionalReleaseIntent) -> ReleaseIntentEstablishmentReply: ...
```

### `QualifiedConditionalResultRelease`

```python
def commit_if_current(self, *, request: ConditionalReleaseIntent) -> ConditionalReleaseReply: ...
```

### `QualifiedOriginalReleaseIntentSource`

```python
def read_fixed_intent(self, *, release: ReleaseOperationIdentity) -> ConditionalReleaseIntent | None: ...
```

### `QualifiedPreparedReleaseResolver`

```python
def resolve_fixed_intent_if_current(self, *, request: ConditionalReleaseIntent) -> ConditionalReleaseReply: ...
```

## `src/grading/integration/teacher_review_journal.py`

### `ProductionTeacherReviewJournal`

```python
def __init__(self, *, original_source: QualifiedOriginalReviewSource, teacher_source: QualifiedTeacherDecisionSource, journal: QualifiedConditionalReviewJournal, legal_policy: LegalGradingTransitionPolicy, max_identifier_characters: int): ...
```

```python
def record(self) -> TeacherReviewObservation: ...
```

### `SchoolTeacherReviewDecision`

Record fields:

```python
    decision_ref: str
    teacher_ref: str
    tenant_ref: str
    grading_run_id: str
    submission_ref: str
    question_id: str
    original_result_ref: str
    original_commit_ref: str
    original_rubric_ref: str
    original_rubric_version: int
    approval_ref: str
    approval_version: int
    action: TeacherReviewAction
    proposed_mark: ScoringDecimal | None
    reason_ref: str | None
```

### `QualifiedConditionalReviewJournal`

```python
def append_teacher_review_if_current(self, *, request: ConditionalTeacherReviewAppend) -> TeacherReviewAppendReply: ...
```

## Integration verification

Copying these method shapes is not enough. The backend must prove authenticated school revisions and transaction durability; the provider must prove actual model activity and physical receipts; and release must enforce current policy and audience authorization. See [Integration ports](integration_ports.md) and [Acceptance checks](acceptance_checks.md).
