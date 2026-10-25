# Handoff checklist

## Grading-engine repository

- [ ] Confirm the exact candidate Git tree and inspect every intended file change.
- [ ] Run the complete test suite on Windows and Linux, including property tests; save full command logs.
- [ ] Confirm no generated cache, secret, private student record or environment-specific workspace path is staged.
- [ ] Verify the root README, documentation index, source maps and sample commands against the installed files.

## Backend and OCR

- [ ] Authenticate school, teacher, paper/rubric and current policy; test revocation during operation.
- [ ] Admit real normalized OCR evidence and prove paper-question mapping with actual scans.
- [ ] Install original-keyed attempt, provider and scored CAS ports on a real durable store.
- [ ] Demonstrate two-worker race, lost acknowledgment and restart recovery.

## Provider, frontend and school

- [ ] Verify actual provider/model identity and measured physical accounting.
- [ ] Compare real supported paper marks with independent teacher labels.
- [ ] Keep candidate and official result separate in backend and browser.
- [ ] Qualify teacher approval, safe feedback and publication audience independently.
- [ ] Record unsupported math, diagram, full-mixed-paper and official teacher-correction boundaries without claiming them complete.

The historical development archive and working ZIPs stay outside the Git repository. Publication of the integration branch requires separate review of Git ancestry, write permissions and exact staged-tree contents.
