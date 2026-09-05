"""Evidence, hypotheses, and findings owned by an investigation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from gcp_observability_agent.domain.common.ids import (
    AnalysisId,
    FindingId,
    HypothesisId,
    InvestigationId,
    InvestigationStepId,
    ObservationId,
)
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.telemetry.models import MetricType, ResourceId, ScalarValue


def _frozen_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


class EvidenceRelationship(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"


class SupportLevel(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class HypothesisStatus(StrEnum):
    OPEN = "OPEN"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A reference to application-generated evidence in one investigation."""

    evidence_id: str
    relationship: EvidenceRelationship = EvidenceRelationship.SUPPORTING

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")


@dataclass(frozen=True, slots=True)
class Observation:
    """An investigation-facing fact with immutable provenance."""

    observation_id: ObservationId
    investigation_id: InvestigationId
    statement: str
    step_id: InvestigationStepId | None = None
    metric_type: MetricType | None = None
    resource_id: ResourceId | None = None
    interval: TimeInterval | None = None
    numeric_value: ScalarValue | None = None
    unit: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("observation statement must not be empty")
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance))

    @property
    def evidence_id(self) -> str:
        return str(self.observation_id)


@dataclass(frozen=True, slots=True)
class DeterministicAnalysis:
    """A reproducible calculation with recorded inputs and parameters."""

    analysis_id: AnalysisId
    investigation_id: InvestigationId
    operation: str
    input_evidence_ids: tuple[str, ...]
    result: ScalarValue | str | bool
    step_id: InvestigationStepId | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)
    unit: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("analysis operation must not be empty")
        inputs = tuple(self.input_evidence_ids)
        if not inputs or any(not evidence_id.strip() for evidence_id in inputs):
            raise ValueError("a deterministic analysis requires recorded input evidence")
        object.__setattr__(self, "input_evidence_ids", inputs)
        object.__setattr__(self, "parameters", _frozen_mapping(self.parameters))
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance))

    @property
    def evidence_id(self) -> str:
        return str(self.analysis_id)


def _validate_confidence(confidence: float | None) -> None:
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: HypothesisId
    investigation_id: InvestigationId
    statement: str
    evidence: tuple[EvidenceReference, ...] = ()
    status: HypothesisStatus = HypothesisStatus.OPEN
    confidence: float | None = None
    significant_evidence_gap: bool = False
    causal_claim: bool = False
    temporal_correlation_only: bool = False

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("hypothesis statement must not be empty")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        _validate_confidence(self.confidence)

    @property
    def support_level(self) -> SupportLevel:
        from gcp_observability_agent.domain.evidence.support import determine_support_level

        return determine_support_level(
            self.evidence,
            significant_evidence_gap=self.significant_evidence_gap,
            causal_claim=self.causal_claim,
            temporal_correlation_only=self.temporal_correlation_only,
        )


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: FindingId
    investigation_id: InvestigationId
    statement: str
    evidence: tuple[EvidenceReference, ...]
    confidence: float | None = None
    significant_evidence_gap: bool = False
    causal_claim: bool = False
    temporal_correlation_only: bool = False

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("finding statement must not be empty")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        _validate_confidence(self.confidence)

    @property
    def support_level(self) -> SupportLevel:
        from gcp_observability_agent.domain.evidence.support import determine_support_level

        return determine_support_level(
            self.evidence,
            significant_evidence_gap=self.significant_evidence_gap,
            causal_claim=self.causal_claim,
            temporal_correlation_only=self.temporal_correlation_only,
        )

