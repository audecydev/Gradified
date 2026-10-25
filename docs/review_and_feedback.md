# Review and feedback

The engine records bounded review decisions and can produce governed recommendations. Neither source evidence nor a risk signal grants permission to change official marks.

## Teacher decisions

`integration/teacher_review_journal.py` implements `ProductionTeacherReviewJournal.record(...)`, whose source resolves an exact original result and current teacher decision before journal contact. Supported actions include `ACCEPT_ORIGINAL` and `OVERRIDE_MARK`; the latter records a bounded proposed corrected amount with the original review record. **The journal does not update the official score.** A corrected official result requires a separately authorized result version and recalculated totals under the backend's agreed authority.

The journal must be atomic and idempotent by the original decision identity. Lost acknowledgment produces an uncertain outcome that is resolved from the original journal rather than appended again without proof.

## Risk and review routing

`grading.risk` extracts deterministic risk observations. `grading.risk_policy` consumes an approved policy fact to form a review recommendation. This is not proof of fully calibrated OCR/rubric/model confidence probabilities. Schools cannot enable an arbitrary automatic-clearance threshold without approved calibration and policy.

## Feedback

`integration/student_safe_feedback.py` and `integration/recovered_feedback_candidate.py` constrain feedback to original evidence and allowed result scope. An unverified model explanation must not be published as a finding about the student.

Test unknown criterion, foreign evidence, stale teacher approval, conflicting journal append, unknown reply, original result mismatch and publication of unreleased feedback. See [Official release](official_release.md) and [Capabilities](capabilities_and_limitations.md).
