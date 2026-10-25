"""Nonpublishing governed assessment from four independent original-key readers.

A reader's exact-method shape is a local installation property, not issuer
authentication or proof of persistent/backend state. Each backend adapter must
qualify its own original key, revision, and revocation semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grading.integration.execution_eligibility import _capture
from grading.integration.governed_result_disposition import (
    GovernedResultDecision, GovernedResultDisposition, GovernedResultEvidence,
)


@dataclass(frozen=True, slots=True)
class GovernedOriginalKey:
    tenant_ref: str
    grading_run_id: str
    original_scored_result_ref: str
    source_revision: str
    policy_ref: str
    policy_revision: str


@dataclass(frozen=True, slots=True)
class GovernedOriginalFact:
    """One independently observed ternary fact tied to the entire original key."""
    original: GovernedOriginalKey
    current: bool | None


class ScoredOriginalReader(Protocol):
    def read_scored_original(self, *, original: GovernedOriginalKey) -> GovernedOriginalFact: ...


class AcademicOriginalReader(Protocol):
    def read_academic_original(self, *, original: GovernedOriginalKey) -> GovernedOriginalFact: ...


class TeacherOriginalReader(Protocol):
    def read_teacher_original(self, *, original: GovernedOriginalKey) -> GovernedOriginalFact: ...


class AdversePolicyReader(Protocol):
    def read_adverse_policy(self, *, original: GovernedOriginalKey) -> GovernedOriginalFact: ...


class ProductionGovernedOriginalAssessment:
    """Read-only, original-key decision composer; does not authorize publishing.

    Reader errors, missing/foreign facts, and conflicting originals stay UNKNOWN.
    The adapters must prove independent source qualification and original reads.
    """
    __slots__ = ('_readers', '_interpret', '_limit')

    def __init__(self, *, scored: ScoredOriginalReader,
                 academic: AcademicOriginalReader,
                 teacher: TeacherOriginalReader,
                 adverse_policy: AdversePolicyReader,
                 max_identifier_characters: int):
        if (type(max_identifier_characters) is not int
                or not 0 < max_identifier_characters <= 4096
                or len({id(scored), id(academic), id(teacher), id(adverse_policy)}) != 4):
            raise ValueError('Four independently installed original readers required.')
        operations = tuple(_capture(owner, name, ('original',)) for owner, name in (
            (scored, 'read_scored_original'),
            (academic, 'read_academic_original'),
            (teacher, 'read_teacher_original'),
            (adverse_policy, 'read_adverse_policy'),
        ))
        object.__setattr__(self, '_readers', operations)
        object.__setattr__(self, '_interpret', GovernedResultDisposition(
            max_identifier_characters=max_identifier_characters))
        object.__setattr__(self, '_limit', max_identifier_characters)

    def __setattr__(self, name, value):
        raise AttributeError('Original assessment installation is immutable.')

    def assess(self, *, original: GovernedOriginalKey) -> GovernedResultDecision:
        if type(original) is not GovernedOriginalKey:
            raise ValueError('Exact original key required.')
        names = ('tenant_ref', 'grading_run_id', 'original_scored_result_ref',
                 'source_revision', 'policy_ref', 'policy_revision')
        values = tuple(getattr(original, name) for name in names)
        if any(type(v) is not str or not v or v.strip() != v or len(v) > self._limit
               for v in values):
            raise ValueError('Bounded complete original identity required.')
        # New exact immutable root is passed to each reader, not caller memory.
        # Bind original consumers before entering any external source callback.
        # The public __setattr__ guard does not prevent unsupported reflective
        # mutation by an in-process source; a changed installation must never
        # turn absent or foreign evidence into an affirmative disposition.
        installed_readers = self._readers
        installed_interpreter = self._interpret
        installed_limit = self._limit
        facts: list[bool | None] = []
        for operation in installed_readers:
            try:
                fact = operation(original=GovernedOriginalKey(*values))
                if (type(fact) is not GovernedOriginalFact
                        or type(fact.original) is not GovernedOriginalKey
                        or tuple(getattr(fact.original, n) for n in names) != values
                        or (fact.current is not None and type(fact.current) is not bool)):
                    facts.append(None)
                else:
                    facts.append(fact.current)
            except Exception:
                facts.append(None)
        if (getattr(self, '_readers', None) is not installed_readers
                or getattr(self, '_interpret', None) is not installed_interpreter
                or getattr(self, '_limit', None) != installed_limit):
            # Fail closed using the original, pre-callback interpreter, not a
            # replacement installed by an external evidence reader.
            facts = [None, None, None, None]
        # Even an all-true decision only permits a *governed handoff*.
        return installed_interpreter.evaluate(evidence=GovernedResultEvidence(
            *values[:3], values[4], values[5], values[3],
            facts[1], facts[0], facts[2], facts[3]))
