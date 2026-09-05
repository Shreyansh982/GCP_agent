"""Mapping between SQLite rows and provider-independent domain records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from gcp_observability_agent.domain.common.ids import (
    AnalysisId,
    FindingId,
    HypothesisId,
    InvestigationId,
    InvestigationStepId,
    ObservationId,
    ToolRequestId,
    ToolResultId,
)
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.evidence.models import (
    DeterministicAnalysis,
    EvidenceReference,
    EvidenceRelationship,
    Finding,
    Hypothesis,
    HypothesisStatus,
    Observation,
)
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationOutcome,
    InvestigationScope,
    InvestigationStatus,
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
from gcp_observability_agent.domain.telemetry.models import MetricType, ProjectId, ResourceId, ResourceType


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def as_json(value: object) -> str:
    return json.dumps(_json_compatible(value), sort_keys=True, separators=(",", ":"))


def _json_compatible(value: object) -> object:
    """Convert immutable domain containers into ordinary JSON-compatible values."""
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, datetime):
        return as_timestamp(value)
    if isinstance(value, Enum):
        return value.value
    return value


def from_json(value: str | None, default: Any) -> Any:
    return default if value is None else json.loads(value)


def as_timestamp(value: datetime) -> str:
    return value.isoformat()


def from_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def scope_from_row(row: sqlite3.Row) -> InvestigationScope:
    return InvestigationScope(
        project_id=ProjectId(row["project_id"]) if row["project_id"] else None,
        service=row["service"],
        environment=row["environment"],
        resource_type=ResourceType(row["resource_type"]) if row["resource_type"] else None,
        resource_id=ResourceId(row["resource_id"]) if row["resource_id"] else None,
        metadata=from_json(row["metadata_json"], {}),
    )


def temporal_context_from_row(row: sqlite3.Row) -> TemporalContext:
    return TemporalContext(
        reference_time=from_timestamp(row["reference_time"]),
        resolved_interval=TimeInterval(from_timestamp(row["interval_start"]), from_timestamp(row["interval_end"])),
        timezone=row["timezone"],
        requested_expression=row["requested_expression"],
    )


def tool_request_from_row(row: sqlite3.Row) -> ToolRequest:
    return ToolRequest(
        ToolRequestId(row["request_id"]),
        ToolName(row["tool_name"]),
        from_json(row["arguments_json"], {}),
        from_timestamp(row["requested_at"]),
    )


def tool_result_from_row(row: sqlite3.Row) -> ToolResult:
    return ToolResult(
        ToolResultId(row["result_id"]),
        ToolRequestId(row["request_id"]),
        ToolName(row["tool_name"]),
        ToolResultStatus(row["status"]),
        from_json(row["data_json"], {}),
        tuple(from_json(row["warnings_json"], [])),
        from_json(row["error_json"], None),
        from_json(row["provenance_json"], {}),
    )


def observation_from_row(row: sqlite3.Row) -> Observation:
    interval = None
    if row["interval_start"]:
        interval = TimeInterval(from_timestamp(row["interval_start"]), from_timestamp(row["interval_end"]))
    return Observation(
        ObservationId(row["observation_id"]),
        InvestigationId(row["investigation_id"]),
        row["statement"],
        InvestigationStepId(row["step_id"]) if row["step_id"] else None,
        MetricType(row["metric_type"]) if row["metric_type"] else None,
        ResourceId(row["resource_id"]) if row["resource_id"] else None,
        interval,
        from_json(row["numeric_value_json"], None),
        row["unit"],
        from_json(row["source_metadata_json"], {}),
    )


def analysis_from_row(row: sqlite3.Row) -> DeterministicAnalysis:
    return DeterministicAnalysis(
        AnalysisId(row["analysis_id"]),
        InvestigationId(row["investigation_id"]),
        row["operation"],
        tuple(from_json(row["input_evidence_ids_json"], [])),
        from_json(row["result_json"], None),
        InvestigationStepId(row["step_id"]) if row["step_id"] else None,
        from_json(row["parameters_json"], {}),
        row["unit"],
        from_json(row["provenance_json"], {}),
    )


def evidence_for(connection: sqlite3.Connection, table: str, owner_id: str) -> tuple[EvidenceReference, ...]:
    allowed = {"hypothesis_evidence": "hypothesis_id", "finding_evidence": "finding_id"}
    owner_column = allowed[table]
    rows = connection.execute(
        f"SELECT evidence_id, relationship FROM {table} WHERE {owner_column} = ? ORDER BY rowid",
        (owner_id,),
    )
    return tuple(EvidenceReference(row["evidence_id"], EvidenceRelationship(row["relationship"])) for row in rows)
