# Production paper wiring walkthrough

The engine ships the strict paper-operation class, not a pre-authenticated school deployment. The hosting backend must provide qualified sources, storage and provider adapters. The checked integration test below shows the **actual constructor shape** and execution sequence without inventing school authority.

## Run a supported paper demonstration

From the repository root, after installing `requirements-test.txt`:

Linux / macOS:

```sh
PYTHONPATH=src:. python docs/examples/paper_operation_demo.py
```

Windows CMD:

```bat
set "PYTHONPATH=src;."
python docs\examples\paper_operation_demo.py
```

Expected output:

```text
SYNTHETIC PAPER OPERATION PASS
Operation: FIRST
Q1: 5
Q2: 5
Paper candidate total: 10
Physical attempts: 2; conditional scored commits: 1
Publication authorized: False
```

This example executes the real `ProductionPaperOperations` root on one **supported
DIRECT + NUMERIC** paper. It demonstrates admission rechecks, deterministic
question marks and paper total, physical attempt recording and conditional
candidate commit. It uses the exact **synthetic host-port implementations in
the checked-in `tests/integration/` fixtures**. These dependencies are imported
by the example script; no hidden variables or manual fixture assembly is needed.
The test fixtures do **not** authenticate a real teacher, contact a real vendor,
or commit to a durable school database. The output is therefore a reproducible
source demonstration, **not** an authentic school result.

For the current supported production-paper constructor and its negative cases:

```sh
PYTHONPATH=src:. python -m pytest -q tests/integration/test_production_paper_operations.py
```

Windows CMD (the backslashes are literal separators):

```bat
set "PYTHONPATH=src;."
python -m pytest -q tests\integration\test_production_paper_operations.py
```

The exact constructor is `ProductionPaperOperations(admission=..., promotion=...,
lifecycle=..., retry=..., enabled_kinds=..., max_identifier_characters=...,
max_questions=...)`. See [Host-facing port signatures](port_signatures.md). Its
first `execute(request=..., kind=PaperOperationKind.FIRST)` call uses a
`PaperAdmissionRequest` with real backend identities and admitted current
source state in a connected system. The demonstration builds that request from
synthetic fixtures, not fabricated school permission.

## Demonstration assembly map

| Stage | Reusable source | Synthetic owner in demonstration | Production replacement |
|---|---|---|---|
| Actor, approved questions, answer readiness, revision | `ProductionPaperAdmissionComposer` | `installation(plan)` in `test_admitted_paper_family_effect_continuity.py` | Authenticated school identity, approved selection and revision sources |
| DIRECT and NUMERIC evaluation with guarded physical contact | Installed grading executor, `ProductionPaperLifecycle` | `connected("MIXED")` in `test_family_first_scored_cas.py` | Current authority, approved provider and original keyed transaction |
| DIRECT provider callback and receipt evidence | `integration/direct_provider_route.py` | `install(...)` from `test_direct_provider_route_connected.py` | Real approved model, measured request/receipt and accounting source |
| Candidate result commit | `ProductionWholePaperCAS` | Source `Store` and `ConditionalFamilyScoredBackend` | Real multiworker atomic conditional database transaction |
| Governed paper promotion reader | `ProductionPaperPromotion` | `recorded_handoff("DIRECT")` | Qualified current governed original-result consumer |
| School publication | Separate `ProductionGovernedResultRelease` | **Not invoked** | Real authorized conditional release and audience filtering |

The demonstration imports those fixtures deliberately to avoid duplicating
thousands of lines of test-only trust-source implementations. The example
provides a **single command**, while the implementation of each synthetic port
remains auditable in its named test module.

## What to replace for a real school

| Test fixture dependency | Required real implementation |
|---|---|
| `IdentityAuthority`, `PaperSelectionAuthority` | Authenticated actor and current school-approved paper selection |
| `PaperAnswerAuthority`, `PaperRevisionAuthority` | Actual OCR region readiness and current revision checks |
| Attempt and conditional effect owner | Durable original-keyed claim, exact issuer currentness and atomicity across workers |
| Provider route and accounting | Real approved model sender with measured transport/usage evidence |
| Scored CAS store | Durable conditional insert/update, original history and read-only reconciliation |
| Promotion and release | Independently qualified governed result and separately authorized publication |

Do not copy an in-memory fixture into the production backend or change a failed constructor check to a permissive guard. The real application must provide equivalent source facts and stronger external guarantees. For adapters and failure scenarios, continue with [Backend integration](backend_integration_guide.md), [Integration ports](integration_ports.md) and [Integration test plan](integration_test_plan.md).
