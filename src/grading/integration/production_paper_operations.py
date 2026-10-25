"""Mandatory strict application entry for a source-admitted paper operation.

This is installation/admission composition, not another evaluator, ledger or
publication service. The hosting backend MUST expose this root instead of the
legacy-compatible individual paper lifecycle/CAS owners for production grading jobs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock

from grading.integration.paper_readiness_admission import (
    PaperAdmissionRequest, ProductionPaperAdmissionComposer, _request,
)
from grading.integration.paper_lifecycle import ProductionPaperLifecycle
from grading.integration.paper_retry_grading import ProductionGradedPaperRetry
from grading.integration.scored_paper_promotion import ProductionPaperPromotion
from grading.integration.whole_paper_cas import ProductionWholePaperCAS
from grading.integration.whole_paper_attempt_custody import ProductionPaperAttemptCustody
from grading.integration.whole_paper_family_execution import ProductionWholePaperFamilyExecutor
from grading.integration.whole_paper_choice_execution import ProductionWholePaperChoiceExecutor
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.direct_provider_route import ProductionDirectProviderRoute


PRODUCTION_PAPER_OPERATION_SCHEMA_VERSION = '1'


class PaperOperationKind(str, Enum):
    FIRST = 'FIRST'
    REGRADE = 'REGRADE'
    RETRY = 'RETRY'


@dataclass(frozen=True, slots=True, repr=False)
class PaperOperationObservation:
    kind: PaperOperationKind
    execution: object  # exact paper lifecycle or graded-authorized retry claim observation; never bearer authority

    @property
    def authorizes_publication(self):
        return False

    @property
    def authorizes_retry(self):
        return False


class ProductionPaperOperations:
    """One installed, nonpublishing gate for enabled FIRST/REGRADE/RETRY paths.

    It requires a genuinely installed *conditional* physical attempt claim and purpose-aware
    scored CAS owner, and sources official READY paper identity afresh for each
    operation. Backend source authentication and atomicity are NOT inferred
    from these Python object checks; adapters must independently qualify them.
    """
    __slots__ = ('_admission', '_lifecycle', '_retry', '_promotion', '_cas',
                 '_enabled', '_max', '_questions', '_gate')

    def __init__(self, *, admission: ProductionPaperAdmissionComposer,
                 promotion: ProductionPaperPromotion,
                 lifecycle: ProductionPaperLifecycle | None = None,
                 retry: ProductionGradedPaperRetry | None = None,
                 enabled_kinds: tuple[PaperOperationKind, ...],
                 max_identifier_characters: int, max_questions: int):
        if (type(admission) is not ProductionPaperAdmissionComposer
                or type(promotion) is not ProductionPaperPromotion
                or type(enabled_kinds) is not tuple or not enabled_kinds
                or any(type(k) is not PaperOperationKind for k in enabled_kinds)
                or len(set(enabled_kinds)) != len(enabled_kinds)
                or type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or type(max_questions) is not int or not 0 < max_questions <= 1000
                or admission._limit != max_identifier_characters
                or admission._max_questions != max_questions):
            raise ValueError('Exact bounded official paper admission and versioned operation selection required.')
        if (any(k in enabled_kinds for k in (PaperOperationKind.FIRST, PaperOperationKind.REGRADE))
                and type(lifecycle) is not ProductionPaperLifecycle):
            raise ValueError('FIRST and REGRADE require installed lifecycle authorization lifecycle custody.')
        if PaperOperationKind.RETRY in enabled_kinds and type(retry) is not ProductionGradedPaperRetry:
            raise ValueError('RETRY requires installed purpose-specific original-absence claim owner.')
        if lifecycle is not None and type(lifecycle) is not ProductionPaperLifecycle:
            raise ValueError('Foreign lifecycle authorization lifecycle owner.')
        if retry is not None and type(retry) is not ProductionGradedPaperRetry:
            raise ValueError('Foreign authorized retry owner.')
        cas = lifecycle._cas if lifecycle is not None else retry._cas
        executor = cas._custody._executor
        attempts = cas._custody._attempts
        if (type(cas) is not ProductionWholePaperCAS
                or type(cas._custody) is not ProductionPaperAttemptCustody
                or type(executor) not in (ProductionWholePaperFamilyExecutor,
                                          ProductionWholePaperChoiceExecutor)
                or type(attempts) is not ClaimedAttemptAllocator
                or attempts is not executor._attempts
                or attempts.academic_binding_enabled is not True
                or attempts._joint_effect is None
                or cas._joint_commit is not None
                or cas._purpose_commit is None
                or cas._require_academic is not True
                or cas._max != max_identifier_characters
                or cas._questions != max_questions
                or promotion._policy != cas._allowed
                or promotion._maximum != max_identifier_characters
                or promotion._questions != max_questions
                or (type(executor) is ProductionWholePaperFamilyExecutor
                    and (promotion._physical_accounting is None
                         or promotion._physical_accounting._applicability is None
                         or promotion._accounting._applicability is None))
                or (lifecycle is not None and (
                    lifecycle._cas is not cas or lifecycle._policy != cas._allowed))
                or (retry is not None and (
                    retry._cas is not cas or retry._executor is not executor
                    or retry._claims._joint_effect is None
                    or retry._claims._runtime_executor is not executor))):
            raise ValueError('Production operation requires one strict, purpose-bound attempt reservation and conditional score commit installation.')
        object.__setattr__(self, '_admission', admission)
        object.__setattr__(self, '_lifecycle', lifecycle)
        object.__setattr__(self, '_retry', retry)
        object.__setattr__(self, '_promotion', promotion)
        object.__setattr__(self, '_cas', cas)
        object.__setattr__(self, '_enabled', enabled_kinds)
        object.__setattr__(self, '_max', max_identifier_characters)
        object.__setattr__(self, '_questions', max_questions)
        object.__setattr__(self, '_gate', Lock())

    def __setattr__(self, name, value):
        raise AttributeError('Production paper operation installation is immutable.')

    def execute(self, *, request: PaperAdmissionRequest,
                kind: PaperOperationKind) -> PaperOperationObservation:
        if type(kind) is not PaperOperationKind or kind not in self._enabled:
            raise ValueError('Paper operation is not enabled by this installation.')
        if not self._gate.acquire(blocking=False):
            raise ValueError('Concurrent paper operation at this root is forbidden.')
        try:
                # Each operation re-admits real official answer readiness before
            # calling legal operation transition and before any possible physical attempt claim/provider contact.
            original = _request(request, self._max)
            plan = self._admission.admit(request=original)
            # DIRECT always invokes provider transport. Installing a metric-
            # names-only governed scored-paper handoff consumer is not a production-positive accounting
            # route even when a legacy runner could subsequently grade.
            if any(q.family == 'DIRECT' for q in plan.questions):
                # The actual installed family executor must enforce approval
                # before the first physical attempt claim and bind the issued attempt at dispatch.
                executor = self._cas._custody._executor
                if (type(executor) is not ProductionWholePaperFamilyExecutor
                        or type(executor._direct_route) is not ProductionDirectProviderRoute):
                    raise ValueError('DIRECT requires qualified installed provider route before grading-attempt.')
                physical = self._promotion._physical_accounting
                if physical._completeness is None or physical._measurements is None:
                    raise ValueError('DIRECT production operation needs installed physical usage evidence.')
            if kind is PaperOperationKind.FIRST:
                result = self._lifecycle.execute_first(plan=plan)
            elif kind is PaperOperationKind.REGRADE:
                result = self._lifecycle.execute_regrade(plan=plan)
            else:
                result = self._retry.execute_and_commit(plan=plan)
            return PaperOperationObservation(kind, result)
        finally:
            self._gate.release()
