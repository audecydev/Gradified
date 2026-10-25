"""Bind admitted benchmark source *shape* to one claimed offline replay.

This is a local structural composition only.  Neither source declarations nor
teacher annotation references are authenticated, nor is a live evaluator or an
academic metric authorized by this module.  The existing FRESH claim remains the
sole authorization to read and replay, with all durability delegated to its issuer.
"""
from __future__ import annotations

from dataclasses import dataclass

from grading.benchmark.offline_trial import (
    ClaimedOfflineReplayTrial, OfflineTrialDenied, OfflineTrialEvidence,
    OfflineTrialRequest, _request,
)
from grading.benchmark.qualification import (
    BenchmarkCaseReference, BenchmarkSourceManifest,
    admit_benchmark_source_shape,
)


@dataclass(frozen=True, slots=True)
class SourceBoundOfflineReplayEvidence:
    """Digest-only replay tied to an *unverified* teacher-reference assertion."""
    observation: OfflineTrialEvidence
    benchmark_source_ref: str
    benchmark_source_revision: str
    benchmark_source_sha256: str
    source_policy_id: str
    source_policy_version: str
    split: str
    case_ref: str
    teacher_annotation_ref: str
    teacher_annotation_revision: str
    teacher_annotation_sha256: str
    evidence_type: str = 'STRUCTURALLY_BOUND_UNVERIFIED_OFFLINE_REPLAY'


def _bind(*, source: BenchmarkSourceManifest, request: OfflineTrialRequest,
          split: str, max_identifier_characters: int,
          max_cases: int) -> tuple[OfflineTrialRequest, BenchmarkSourceManifest, BenchmarkCaseReference]:
    admitted = admit_benchmark_source_shape(
        source=source, max_identifier_characters=max_identifier_characters,
        max_cases=max_cases,
    ).manifest
    trial = _request(request, max_identifier_characters)
    # The claim issuer independently authorizes the actual trial; this binding
    # must NEVER be accepted as issuer/protected-read authority.
    if (admitted.tenant_ref != trial.tenant_ref
            or admitted.benchmark_run_ref != trial.run_ref
            or admitted.dataset_ref != trial.dataset_ref
            or admitted.dataset_revision != trial.dataset_revision
            or admitted.dataset_sha256 != trial.dataset_sha256
            or admitted.evaluator_ref != trial.evaluator_ref
            or admitted.configuration_ref != trial.configuration_ref):
        raise OfflineTrialDenied('Trial and benchmark source scope disagree.')
    if type(split) is not str or split not in ('development', 'calibration', 'heldout'):
        raise OfflineTrialDenied('Unknown benchmark split.')
    selected = tuple(case for case in getattr(admitted, split)
                     if case.case_ref == trial.case_ref)
    if len(selected) != 1:
        raise OfflineTrialDenied('Trial case not admitted in requested split.')
    return trial, admitted, selected[0]


class SourceBoundOfflineReplayTrial:
    """Execute at most one *non-live* trial after exact source/attempt binding.

    The actual claim, read, replay and history operations belong to the
    already-reviewed ClaimedOfflineReplayTrial, not a new independent issuer.
    """
    __slots__ = ('_installation', '_trial')

    def __init__(self, *, source: BenchmarkSourceManifest,
                 request: OfflineTrialRequest, split: str,
                 claims: object, reader: object, executor: object, history: object,
                 max_identifier_characters: int, max_cases: int) -> None:
        try:
            trial_req, manifest, case = _bind(
                source=source, request=request, split=split,
                max_identifier_characters=max_identifier_characters, max_cases=max_cases)
            delegated = ClaimedOfflineReplayTrial(
                request=trial_req, claims=claims, reader=reader,
                executor=executor, history=history,
                max_identifier_characters=max_identifier_characters)
            object.__setattr__(self, '_installation', (trial_req, manifest, split, case))
            object.__setattr__(self, '_trial', delegated)
        except Exception:
            error = OfflineTrialDenied('Source-bound offline trial not admitted.')
            try:
                raise error
            finally:
                error.__context__ = None
                error.__cause__ = None
                error.__suppress_context__ = True

    def __setattr__(self, name: str, value: object) -> None:
        if name in ('_installation', '_trial'):
            raise AttributeError('Installed benchmark trial cannot be rebound.')
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in ('_installation', '_trial'):
            raise AttributeError('Installed benchmark trial cannot be deleted.')
        object.__delattr__(self, name)

    def run(self) -> SourceBoundOfflineReplayEvidence:
        request, source, split, case = self._installation
        observation = self._trial.run()
        # Trial outputs have no raw provider bytes.  The source/teacher-label
        # assertion is detached, not independently verified or scored.
        if (type(observation) is not OfflineTrialEvidence
                or observation.request != request
                or observation.evidence_type != 'NON_AUTHORITATIVE_OFFLINE_REPLAY'):
            error = OfflineTrialDenied('Foreign source-bound trial evidence.')
            try:
                raise error
            finally:
                error.__cause__ = None
                error.__context__ = None
                error.__suppress_context__ = True
        return SourceBoundOfflineReplayEvidence(
            observation, source.dataset_ref, source.dataset_revision,
            source.dataset_sha256, source.source_policy_id,
            source.source_policy_version, split, case.case_ref,
            case.teacher_annotation_ref, case.teacher_annotation_revision,
            case.teacher_annotation_sha256)
