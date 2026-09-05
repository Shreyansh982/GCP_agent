"""Deterministic support-level evaluation."""

from __future__ import annotations

from collections.abc import Iterable

from gcp_observability_agent.domain.evidence.models import (
    EvidenceReference,
    EvidenceRelationship,
    SupportLevel,
)


def determine_support_level(
    evidence: Iterable[EvidenceReference],
    *,
    significant_evidence_gap: bool = False,
    causal_claim: bool = False,
    temporal_correlation_only: bool = False,
) -> SupportLevel:
    """Apply the Phase 1 support-level rules without using LLM confidence."""
    references = tuple(evidence)
    has_support = any(
        reference.relationship is EvidenceRelationship.SUPPORTING for reference in references
    )
    if not has_support:
        return SupportLevel.UNSUPPORTED

    has_contradiction = any(
        reference.relationship is EvidenceRelationship.CONTRADICTING for reference in references
    )
    if has_contradiction or significant_evidence_gap:
        return SupportLevel.PARTIALLY_SUPPORTED
    if causal_claim and temporal_correlation_only:
        return SupportLevel.PARTIALLY_SUPPORTED
    return SupportLevel.SUPPORTED

