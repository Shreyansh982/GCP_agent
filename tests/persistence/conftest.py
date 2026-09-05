from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gcp_observability_agent.domain.common.ids import (
    AnalysisId,
    FindingId,
    HypothesisId,
    InvestigationStepId,
    ObservationId,
    ToolRequestId,
    ToolResultId,
)
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.evidence.models import (
    DeterministicAnalysis,
    EvidenceReference,
    Finding,
    Hypothesis,
    HypothesisStatus,
    Observation,
)
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationOutcome,
    InvestigationScope,
    InvestigationStep,
    OutcomeStatus,
    StepExecutionStatus,
    TemporalContext,
    TerminationReason,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolResultStatus,
    ValidationStatus,
)
from gcp_observability_agent.infrastructure.persistence.sqlite.repository import SQLiteInvestigationRepository


@pytest.fixture
def repository(tmp_path) -> SQLiteInvestigationRepository:
    return SQLiteInvestigationRepository(tmp_path / "investigations.sqlite3")


@pytest.fixture
def investigation() -> Investigation:
    start = datetime(2026, 8, 27, 14, tzinfo=UTC)
    investigation = Investigation.create(
        "Why did payments become slow?",
        InvestigationScope(service="payments", environment="production"),
        TemporalContext(start + timedelta(hours=1), TimeInterval(start, start + timedelta(hours=1))),
    )
    investigation.start()
    request = ToolRequest(ToolRequestId.new(), ToolName.QUERY_METRIC, {"metric": "latency"}, start)
    result = ToolResult(
        ToolResultId.new(), request.request_id, ToolName.QUERY_METRIC, ToolResultStatus.SUCCESS,
        data={"summary": {"maximum": 870}}, provenance={"provider": "mock"},
    )
    step = InvestigationStep(
        InvestigationStepId.new(), 1, request, start,
        ValidationStatus.VALID, StepExecutionStatus.EXECUTED, result, completed_at=start + timedelta(seconds=1),
    )
    investigation.record_step(step)
    observation = Observation(
        ObservationId.new(), investigation.investigation_id, "Latency reached 870 ms.",
        step_id=step.step_id, interval=TimeInterval(start, start + timedelta(minutes=5)), numeric_value=870.0,
        unit="ms", provenance={"provider": "mock"},
    )
    investigation.record_observation(observation)
    analysis = DeterministicAnalysis(
        AnalysisId.new(), investigation.investigation_id, "maximum", (observation.evidence_id,), 870.0,
        step_id=step.step_id, parameters={"statistic": "max"}, unit="ms", provenance={"input": observation.evidence_id},
    )
    investigation.record_analysis(analysis)
    investigation.record_hypothesis(
        Hypothesis(
            HypothesisId.new(), investigation.investigation_id, "CPU may have contributed.",
            (EvidenceReference(observation.evidence_id),), HypothesisStatus.UNRESOLVED,
        )
    )
    investigation.record_finding(
        Finding(
            FindingId.new(), investigation.investigation_id, "Latency was elevated.",
            (EvidenceReference(observation.evidence_id), EvidenceReference(analysis.evidence_id)),
        )
    )
    investigation.conclude(
        InvestigationOutcome(OutcomeStatus.COMPLETED, TerminationReason.SUFFICIENT_EVIDENCE, "Latency was elevated.")
    )
    return investigation

