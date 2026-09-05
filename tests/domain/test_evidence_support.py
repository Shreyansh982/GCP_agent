from __future__ import annotations

from gcp_observability_agent.domain.evidence.models import (
    EvidenceReference,
    EvidenceRelationship,
    SupportLevel,
)
from gcp_observability_agent.domain.evidence.support import determine_support_level


def test_support_level_is_evidence_driven_not_confidence_driven() -> None:
    evidence = (EvidenceReference("obs-1"),)
    assert determine_support_level(evidence) is SupportLevel.SUPPORTED
    assert determine_support_level(()) is SupportLevel.UNSUPPORTED


def test_contradiction_and_significant_gap_produce_partial_support() -> None:
    supporting = EvidenceReference("obs-1")
    contradicting = EvidenceReference("obs-2", EvidenceRelationship.CONTRADICTING)

    assert determine_support_level((supporting, contradicting)) is SupportLevel.PARTIALLY_SUPPORTED
    assert determine_support_level((supporting,), significant_evidence_gap=True) is SupportLevel.PARTIALLY_SUPPORTED


def test_temporal_correlation_alone_cannot_support_causal_claim() -> None:
    assert (
        determine_support_level(
            (EvidenceReference("obs-1"),), causal_claim=True, temporal_correlation_only=True
        )
        is SupportLevel.PARTIALLY_SUPPORTED
    )

