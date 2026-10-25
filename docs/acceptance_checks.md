# Acceptance checks

This is the sign-off record for the **integrated system**, not a certificate issued by unit tests. The grading engine must not claim unsupported features or real-world trust it cannot independently observe.

| Check | Required evidence | Responsible owner | Current state |
|---|---|---|---|
| Source integrity | Exact final Git tree, full Linux and Windows/property pass | Engine + QA | Final-tree qualification pending |
| Approved paper and question | Authenticated, revisioned school source with effect-time revocation | Backend | Real adapter qualification pending |
| OCR mapping | Real scanned answer sheets, page/question mapping and uncertainty outcomes | OCR | Real capture evidence pending |
| Grading correctness | School-approved rubric and independent teacher-marked examples | Academic QA | Real benchmark evidence pending |
| Physical provider usage | Real request/receipt/billing correlation and unknown-outcome recovery | Provider + backend | Real provider evidence pending |
| Atomic scored result | Two-worker, process-restart and lost-acknowledgment database conformance | Backend | Live persistence tests pending |
| Teacher review | Real actor approval, journal append/recovery and official corrected-result ownership | Backend + product | Official revision path unresolved |
| Release | Durable original intent, current audience permission, restart-safe one-time effect | Backend | Real publication qualification pending |
| Broader academic coverage | Approved math, unit, diagram and all-family mixed-paper decisions | Product + engine | Not currently supported |

A check becomes accepted only after the named owner supplies a reproducible positive and negative test against its real implementation. Retain raw logs and sensitive evidence outside the public repository. A deferred gate must record its responsible owner and specific event that will reopen it; deferral does not imply implementation is unnecessary.
