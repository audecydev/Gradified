"""Adversarial tests for uncertain effect custody before whole-paper score commits."""
import pytest
from grading.integration.paper_lifecycle import PaperLifecycleState
from grading.integration.whole_paper_attempt_custody import PaperCustodyDenied
from tests.integration.test_paper_lifecycle_pre_effect import setup_lifecycle


def test_original_paper_issuance_survives_ambiguous_second_bound_f25_claim():
    svc, plan, physical, store, _ = setup_lifecycle()
    physical.timeout_second = True
    observed = svc._cas._custody._executor.execute(plan=plan)
    assert observed.state == 'INDETERMINATE'
    assert physical.claims == 2 and store.commits == 0
    assert observed.contact_trace[1].original_f25_request is not None
    assert observed.contact_trace[1].academic_preparation is not None
    assert observed.issued_paper is not None, 'Original academic paper disappeared despite C3b preclaim evidence.'


def test_c1_c2_preserves_original_f25_claim_trace_after_ambiguous_second_claim():
    svc, plan, physical, store, _ = setup_lifecycle()
    physical.timeout_second = True
    try:
        record = svc._cas._custody.execute_and_capture(plan=plan)
    except PaperCustodyDenied:
        pytest.fail('C1/C2 discarded a genuine partial result and original F25 binding after a lost claim response.')
    assert record.outcome.state == 'INDETERMINATE'
    assert len(record.questions) == 2
    assert record.questions[1].original_f25_request is not None
    assert record.questions[1].academic_preparation is not None
    assert physical.claims == 2 and store.commits == 0


def test_c4a_preserves_indeterminate_f25_claim_in_typed_lifecycle_outcome():
    svc, plan, physical, store, _ = setup_lifecycle()
    physical.timeout_second = True
    observed = svc.execute_first(plan=plan)
    assert observed.state is PaperLifecycleState.UNKNOWN
    assert observed.cas is not None, 'Recovery discarded available original attempt request facts.'
    assert observed.cas.custody.outcome.state == 'INDETERMINATE'
    assert observed.cas.custody.questions[1].original_f25_request is not None
    assert physical.claims == 2 and store.commits == 0
    assert not observed.authorizes_retry and not observed.authorizes_publication


def test_stable_bound_execution_remains_a_real_paper_cas_ack():
    svc, plan, physical, store, _ = setup_lifecycle()
    observed = svc.execute_first(plan=plan)
    assert observed.state is PaperLifecycleState.CAS_ACKNOWLEDGED
    assert observed.cas is not None and observed.cas.custody.outcome.state == 'COMPLETE'
    assert physical.claims == 2 and store.commits == 1


def test_unavailable_f57_authority_still_blocks_before_first_effect():
    svc, plan, physical, store, source = setup_lifecycle()
    source.mode = 'UNAVAILABLE'
    observed = svc.execute_first(plan=plan)
    assert observed.state is PaperLifecycleState.UNKNOWN and observed.cas is None
    assert physical.claims == 0 and store.commits == 0


def test_same_c4_instance_concurrent_entry_cannot_reach_second_f25():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from grading.integration.paper_lifecycle import ProductionPaperLifecycle
    from tests.integration.test_paper_lifecycle_pre_effect import POLICY, Permissions
    base, plan, physical, store, _ = setup_lifecycle()
    entered, resume = Event(), Event()
    class BlockingSource(Permissions):
        def resolve_paper_execution_permission(self, *, plan):
            entered.set()
            if not resume.wait(timeout=4):
                raise RuntimeError('test barrier timed out')
            return super().resolve_paper_execution_permission(plan=plan)
    service = ProductionPaperLifecycle(
        cas=base._cas, permission_source=BlockingSource(), legal_policy=POLICY,
        max_identifier_characters=128, max_questions=10)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(service.execute_first, plan=plan)
            assert entered.wait(timeout=3), 'test setup did not enter the lifecycle transition callback'
            with pytest.raises(ValueError, match='Nested/concurrent'):
                service.execute_first(plan=plan)
            assert physical.claims == 0 and store.commits == 0
            resume.set()
            result = running.result(timeout=8)
            assert result.state is PaperLifecycleState.CAS_ACKNOWLEDGED
            assert physical.claims == 2 and store.commits == 1
    finally:
        resume.set()
