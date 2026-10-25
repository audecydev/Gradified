"""Independent, purpose-scoped legal operation transition admission for actual physical retry claims.

The installer must obtain this frozen policy from the qualified institutional
policy owner. A general job-state policy does not grant RETRY_CLAIM permission.
No synthetic state edge or institutional policy value is defined here.
"""
from __future__ import annotations
from dataclasses import dataclass

from grading.contracts.job_state import GradingJobState
from grading.integration.attempt_lineage import LegalGradingTransitionPolicy
from grading.integration.execution_eligibility import _id

RETRY_CLAIM_PURPOSE = 'RETRY_CLAIM'

@dataclass(frozen=True, slots=True, repr=False)
class RetryPurposeTransitionPolicy:
    purpose: str
    approval_policy_id: str
    approval_policy_version: int
    legal_policy_id: str
    legal_policy_version: int
    permitted_edges: tuple[tuple[GradingJobState, GradingJobState], ...]


def retry_purpose_admitted(*, purpose_policy: RetryPurposeTransitionPolicy | None,
                           legal_policy: LegalGradingTransitionPolicy,
                           grant: object, maximum: int) -> bool:
    """Check the actual independently installed RETRY_CLAIM policy and grant.

    Strictly an engine-side consumer. This does not establish that the
    institution authenticated the policy or that a backend honors revocation.
    Missing qualification fails closed, including the legacy generic-only path.
    """
    try:
        if (type(purpose_policy) is not RetryPurposeTransitionPolicy
                or type(legal_policy) is not LegalGradingTransitionPolicy
                or type(purpose_policy.purpose) is not str
                or purpose_policy.purpose != RETRY_CLAIM_PURPOSE
                or _id(purpose_policy.approval_policy_id, maximum) == ''
                or type(purpose_policy.approval_policy_version) is not int
                or purpose_policy.approval_policy_version <= 0
                or _id(purpose_policy.legal_policy_id, maximum) != legal_policy.policy_id
                or type(purpose_policy.legal_policy_version) is not int
                or purpose_policy.legal_policy_version != legal_policy.policy_version
                or type(purpose_policy.permitted_edges) is not tuple
                or not purpose_policy.permitted_edges
                or len(purpose_policy.permitted_edges) > len(legal_policy.allowed_edges)):
            return False
        seen = set()
        for edge in purpose_policy.permitted_edges:
            if (type(edge) is not tuple or len(edge) != 2
                    or type(edge[0]) is not GradingJobState
                    or type(edge[1]) is not GradingJobState
                    or edge not in legal_policy.allowed_edges or edge in seen):
                return False
            seen.add(edge)
        return (type(grant.purpose_policy_id) is str
                and _id(grant.purpose_policy_id, maximum) == purpose_policy.approval_policy_id
                and type(grant.purpose_policy_version) is int
                and grant.purpose_policy_version == purpose_policy.approval_policy_version
                and type(grant.policy_id) is str
                and _id(grant.policy_id, maximum) == legal_policy.policy_id
                and type(grant.policy_version) is int
                and grant.policy_version == legal_policy.policy_version
                and type(grant.source_state) is GradingJobState
                and type(grant.target_state) is GradingJobState
                and (grant.source_state,grant.target_state) in seen)
    except (AttributeError, TypeError, ValueError):
        return False
