"""Structured telemetry tools and deterministic validation for investigations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gcp_observability_agent.domain.common.ids import InvestigationStepId, ObservationId
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.evidence.models import (
    EvidenceReference,
    EvidenceRelationship,
    Finding,
    Hypothesis,
    HypothesisStatus,
    Observation,
)
from gcp_observability_agent.domain.investigation.analysis import mean, trend_direction
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationStatus,
    ToolName,
    ToolResultStatus,
)
from gcp_observability_agent.domain.ports import TelemetryProvider
from gcp_observability_agent.domain.telemetry.models import Alert, MetricDescriptor, MonitoredResource, TimeSeries


class ToolError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] = Field(default_factory=dict)


class ResultMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    returned_count: int
    total_count_known: int | None = None
    truncated: bool = False
    transformed: bool = False
    transformation_summary: str | None = None


class ToolResponse(BaseModel):
    """Provider-neutral result exposed to the future controller/LLM boundary."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    tool_name: ToolName
    status: ToolResultStatus
    data: dict[str, object] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error: ToolError | None = None
    provenance: dict[str, object] = Field(default_factory=dict)


class ToolRequestEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1, max_length=200)
    tool_name: ToolName
    arguments: dict[str, object]


class MetricSelector(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = Field(min_length=1, max_length=300)
    labels: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ResourceSelector(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = Field(min_length=1, max_length=200)
    labels: dict[str, str | int | float | bool] = Field(default_factory=dict)


class IntervalArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def has_positive_duration(self) -> "IntervalArguments":
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be later than start_time")
        return self


class AggregationArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    alignment_period: str | None = Field(default=None, pattern=r"^[1-9][0-9]*[mhd]$")
    per_series_aligner: Literal["ALIGN_MEAN", "ALIGN_MIN", "ALIGN_MAX", "ALIGN_SUM"] | None = None
    cross_series_reducer: Literal["REDUCE_NONE", "REDUCE_MEAN", "REDUCE_MIN", "REDUCE_MAX", "REDUCE_SUM"] = "REDUCE_NONE"
    group_by_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def has_alignment_for_reduction(self) -> "AggregationArguments":
        if self.cross_series_reducer != "REDUCE_NONE" and not self.alignment_period:
            raise ValueError("cross-series reduction requires alignment_period")
        if self.alignment_period and not self.per_series_aligner:
            raise ValueError("alignment_period requires per_series_aligner")
        return self


class SearchMetricDescriptorsArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=200)
    project_id: str | None = Field(default=None, min_length=1, max_length=200)
    resource_type: str | None = Field(default=None, min_length=1, max_length=200)


class QueryMetricArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str | None = Field(default=None, min_length=1, max_length=200)
    metric: MetricSelector
    resource: ResourceSelector
    interval: IntervalArguments
    aggregation: AggregationArguments | None = None
    query_preferences: dict[str, str] = Field(default_factory=dict)


class ListResourcesArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str | None = Field(default=None, min_length=1, max_length=200)
    resource_type: str | None = Field(default=None, min_length=1, max_length=200)
    labels: dict[str, str | int | float | bool] = Field(default_factory=dict)
    limit: int | None = Field(default=None, ge=1)


class GetAlertsArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str | None = Field(default=None, min_length=1, max_length=200)
    resource: ResourceSelector | None = None
    interval: IntervalArguments
    severity: tuple[str, ...] = ()


class EvidenceReferenceArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=1, max_length=200)
    relationship: EvidenceRelationship = EvidenceRelationship.SUPPORTING


class FindingArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1, max_length=2000)
    evidence: tuple[EvidenceReferenceArguments, ...]
    confidence: float | None = Field(default=None, ge=0, le=1)
    significant_evidence_gap: bool = False
    causal_claim: bool = False
    temporal_correlation_only: bool = False


class HypothesisArguments(FindingArguments):
    status: HypothesisStatus = HypothesisStatus.OPEN


class ConcludeInvestigationArguments(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[FindingArguments, ...] = ()
    hypotheses: tuple[HypothesisArguments, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


ArgumentsModel = (
    SearchMetricDescriptorsArguments
    | QueryMetricArguments
    | ListResourcesArguments
    | GetAlertsArguments
    | ConcludeInvestigationArguments
)


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    max_actions: int = 12
    max_result_items: int = 100
    max_query_interval: timedelta = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    investigation: Investigation
    allowed_projects: frozenset[str]
    step_id: InvestigationStepId | None = None


class RetryClassification(StrEnum):
    NEVER = "never"
    BOUNDED = "bounded"


def classify_retry(status: ToolResultStatus) -> RetryClassification:
    return (
        RetryClassification.BOUNDED
        if status in {ToolResultStatus.TIMEOUT, ToolResultStatus.PROVIDER_ERROR, ToolResultStatus.SYSTEM_ERROR}
        else RetryClassification.NEVER
    )


class ToolRegistry:
    """The only application path from structured actions to telemetry providers."""

    def __init__(self, provider: TelemetryProvider, policy: ToolPolicy = ToolPolicy()) -> None:
        self._provider = provider
        self._policy = policy
        self._attempts: dict[str, int] = {}
        self._replays: dict[tuple[str, str], ToolResponse] = {}

    def execute(self, raw_request: object, context: ToolExecutionContext, *, replay: bool = True) -> ToolResponse:
        try:
            request = ToolRequestEnvelope.model_validate(raw_request)
        except ValidationError as error:
            return self._unaddressed_error(raw_request, "MALFORMED_REQUEST", "Tool requests must use the registered structured envelope.", error)

        if context.investigation.status is not InvestigationStatus.RUNNING:
            return self._error(request, ToolResultStatus.INVALID_REQUEST, "INVESTIGATION_NOT_RUNNING", "The investigation is not running.")

        try:
            arguments = self._parse_arguments(request)
        except ValidationError as error:
            return self._error(request, ToolResultStatus.INVALID_REQUEST, "INVALID_ARGUMENTS", "Tool arguments do not match the registered schema.", error)

        authorization_error = self._authorize(request, arguments, context)
        if authorization_error:
            return authorization_error
        semantic_error = self._validate_semantics(request, arguments)
        if semantic_error:
            return semantic_error

        replay_key = (str(context.investigation.investigation_id), self._identity(request.tool_name, arguments))
        previous = self._replays.get(replay_key) if replay else None
        if previous is not None:
            return previous.model_copy(update={"request_id": request.request_id})

        attempts = self._attempts.get(str(context.investigation.investigation_id), 0)
        if attempts >= self._policy.max_actions:
            return self._error(request, ToolResultStatus.POLICY_REJECTED, "TOOL_BUDGET_EXHAUSTED", "The investigation action limit has been reached.")
        self._attempts[str(context.investigation.investigation_id)] = attempts + 1

        try:
            if request.tool_name is ToolName.QUERY_METRIC:
                descriptor_error = self._validate_metric_descriptor(request, arguments)
                if descriptor_error:
                    return descriptor_error
            response = self._execute(request, arguments, context)
        except TimeoutError:
            response = self._error(request, ToolResultStatus.TIMEOUT, "PROVIDER_TIMEOUT", "The telemetry provider timed out.", retryable=True)
        except Exception:
            response = self._error(request, ToolResultStatus.PROVIDER_ERROR, "PROVIDER_ERROR", "The telemetry provider could not complete the request.", retryable=True)

        if replay:
            self._replays[replay_key] = response
        return response

    def _parse_arguments(self, request: ToolRequestEnvelope) -> ArgumentsModel:
        models: dict[ToolName, type[BaseModel]] = {
            ToolName.SEARCH_METRIC_DESCRIPTORS: SearchMetricDescriptorsArguments,
            ToolName.QUERY_METRIC: QueryMetricArguments,
            ToolName.LIST_RESOURCES: ListResourcesArguments,
            ToolName.GET_ALERTS: GetAlertsArguments,
            ToolName.CONCLUDE_INVESTIGATION: ConcludeInvestigationArguments,
        }
        return models[request.tool_name].model_validate(request.arguments)  # type: ignore[return-value]

    def _authorize(self, request: ToolRequestEnvelope, arguments: ArgumentsModel, context: ToolExecutionContext) -> ToolResponse | None:
        requested_project = getattr(arguments, "project_id", None)
        scope_project = context.investigation.scope.project_id
        project = requested_project or (str(scope_project) if scope_project else None)
        if project and project not in context.allowed_projects:
            return self._error(request, ToolResultStatus.POLICY_REJECTED, "PROJECT_NOT_AUTHORIZED", "The requested project is outside the authorized scope.")
        if scope_project and project and project != str(scope_project):
            return self._error(request, ToolResultStatus.POLICY_REJECTED, "PROJECT_SCOPE_MISMATCH", "The requested project does not match the investigation scope.")
        return None

    def _validate_semantics(self, request: ToolRequestEnvelope, arguments: ArgumentsModel) -> ToolResponse | None:
        interval = getattr(arguments, "interval", None)
        if interval and interval.end_time - interval.start_time > self._policy.max_query_interval:
            return self._error(request, ToolResultStatus.POLICY_REJECTED, "QUERY_INTERVAL_TOO_LARGE", "The requested interval exceeds the application limit.")
        limit = getattr(arguments, "limit", None)
        if limit is not None and limit > self._policy.max_result_items:
            return self._error(request, ToolResultStatus.POLICY_REJECTED, "RESULT_LIMIT_TOO_LARGE", "The requested result limit exceeds the application limit.")
        return None

    def _validate_metric_descriptor(self, request: ToolRequestEnvelope, arguments: ArgumentsModel) -> ToolResponse | None:
        assert isinstance(arguments, QueryMetricArguments)
        descriptors = self._provider.search_metric_descriptors({"query": arguments.metric.type, "resource_type": arguments.resource.type})
        descriptor = next((item for item in descriptors if str(item.metric_type) == arguments.metric.type), None)
        if descriptor is None:
            return self._error(request, ToolResultStatus.NOT_FOUND, "METRIC_NOT_FOUND", "The selected metric is not available for the requested resource type.")
        invalid_labels = sorted(set(arguments.metric.labels) - descriptor.label_keys)
        if invalid_labels:
            return self._error(request, ToolResultStatus.INVALID_REQUEST, "INVALID_METRIC_LABEL", "Metric-label filters must be defined by the selected metric descriptor.", details={"invalid_labels": invalid_labels})
        return None

    def _execute(self, request: ToolRequestEnvelope, arguments: ArgumentsModel, context: ToolExecutionContext) -> ToolResponse:
        if request.tool_name is ToolName.SEARCH_METRIC_DESCRIPTORS:
            assert isinstance(arguments, SearchMetricDescriptorsArguments)
            descriptors = self._provider.search_metric_descriptors(self._provider_request(arguments, context))
            return self._descriptors_result(request, descriptors)
        if request.tool_name is ToolName.QUERY_METRIC:
            assert isinstance(arguments, QueryMetricArguments)
            series = self._provider.query_metric(self._provider_request(arguments, context))
            return self._series_result(request, series, context.investigation, context.step_id)
        if request.tool_name is ToolName.LIST_RESOURCES:
            assert isinstance(arguments, ListResourcesArguments)
            resources = self._provider.list_resources(self._provider_request(arguments, context))
            return self._resources_result(request, resources)
        if request.tool_name is ToolName.GET_ALERTS:
            assert isinstance(arguments, GetAlertsArguments)
            alerts = self._provider.get_alerts(self._provider_request(arguments, context))
            return self._alerts_result(request, alerts, context.investigation, context.step_id)
        assert isinstance(arguments, ConcludeInvestigationArguments)
        return self._conclusion_result(request, arguments, context.investigation)

    def _provider_request(self, arguments: BaseModel, context: ToolExecutionContext) -> dict[str, object]:
        values = arguments.model_dump(mode="json", exclude_none=True)
        scope_project = context.investigation.scope.project_id
        if "project_id" in type(arguments).model_fields and "project_id" not in values and scope_project:
            values["project_id"] = str(scope_project)
        return values

    def _descriptors_result(self, request: ToolRequestEnvelope, descriptors: Any) -> ToolResponse:
        items = list(descriptors)
        returned, metadata = self._bounded(items)
        data = {"metrics": [self._descriptor(item) for item in returned], "result_metadata": metadata}
        return self._result(request, ToolResultStatus.SUCCESS if returned else ToolResultStatus.NO_DATA, data, warnings=("No metric descriptors matched the request.",) if not returned else ())

    def _resources_result(self, request: ToolRequestEnvelope, resources: Any) -> ToolResponse:
        items = list(resources)
        returned, metadata = self._bounded(items)
        data = {"resources": [self._resource(item) for item in returned], "result_metadata": metadata}
        return self._result(request, ToolResultStatus.SUCCESS if returned else ToolResultStatus.NO_DATA, data, warnings=("No resources matched the request.",) if not returned else ())

    def _series_result(self, request: ToolRequestEnvelope, series: Any, investigation: Investigation, step_id: InvestigationStepId | None) -> ToolResponse:
        items = list(series)
        returned, metadata = self._bounded(items)
        observations = [self._record_series_observation(item, investigation, step_id) for item in returned]
        data = {"observations": observations, "summary": {"series_count": len(items), "point_count": sum(len(item.points) for item in items)}, "result_metadata": metadata}
        return self._result(request, ToolResultStatus.SUCCESS if observations else ToolResultStatus.NO_DATA, data, warnings=("No observations matched the requested scope and time interval.",) if not observations else ())

    def _alerts_result(self, request: ToolRequestEnvelope, alerts: Any, investigation: Investigation, step_id: InvestigationStepId | None) -> ToolResponse:
        items = list(alerts)
        returned, metadata = self._bounded(items)
        observations = [self._record_alert_observation(item, investigation, step_id) for item in returned]
        data = {"alerts": observations, "result_metadata": metadata}
        return self._result(request, ToolResultStatus.SUCCESS if observations else ToolResultStatus.NO_DATA, data, warnings=("No alerts matched the requested scope and time interval.",) if not observations else ())

    def _conclusion_result(self, request: ToolRequestEnvelope, arguments: ConcludeInvestigationArguments, investigation: Investigation) -> ToolResponse:
        valid_ids = investigation.evidence_ids
        all_references = [reference.evidence_id for candidate in (*arguments.findings, *arguments.hypotheses) for reference in candidate.evidence]
        invalid_ids = sorted(set(all_references) - valid_ids)
        if invalid_ids:
            return self._error(request, ToolResultStatus.INVALID_REQUEST, "INVALID_EVIDENCE_REFERENCE", "Evidence IDs must exist in the current investigation.", details={"invalid_evidence_ids": invalid_ids, "valid_evidence_ids": sorted(valid_ids)[:self._policy.max_result_items]})
        try:
            findings = [self._finding(candidate, investigation) for candidate in arguments.findings]
            hypotheses = [self._hypothesis(candidate, investigation) for candidate in arguments.hypotheses]
        except ValueError:
            return self._error(request, ToolResultStatus.INVALID_REQUEST, "INVALID_CONCLUSION", "The proposed conclusion does not satisfy evidence support rules.")
        if any(finding.support_level.value == "UNSUPPORTED" for finding in findings):
            return self._error(request, ToolResultStatus.INVALID_REQUEST, "INVALID_CONCLUSION", "Findings require supporting evidence.")
        return self._result(request, ToolResultStatus.SUCCESS, {"validated": True, "findings": [self._finding_data(item) for item in findings], "hypotheses": [self._hypothesis_data(item) for item in hypotheses], "unresolved_questions": list(arguments.unresolved_questions)})

    def _record_series_observation(self, series: TimeSeries, investigation: Investigation, step_id: InvestigationStepId | None) -> dict[str, object]:
        numeric_values = [float(point.value) for point in series.points if isinstance(point.value, (int, float)) and not isinstance(point.value, bool)]
        value: float | str = mean(numeric_values) if numeric_values else str(series.points[-1].value)
        start = series.points[0].sort_time
        end = series.points[-1].sort_time + timedelta(microseconds=1)
        interval = TimeInterval(start, end)
        unit = str(series.metric.metadata.get("unit", "")) or None
        observation = Observation(
            ObservationId.new(), investigation.investigation_id,
            f"Observed {series.metric.metric_type} on {series.resource.resource_id} across {len(series.points)} point(s).",
            step_id=step_id,
            metric_type=series.metric.metric_type, resource_id=series.resource.resource_id, interval=interval,
            numeric_value=value, unit=unit,
            provenance={"source": "telemetry", "metric_labels": dict(series.metric.labels.values), "resource_labels": dict(series.resource.labels.values), "point_count": len(series.points), "minimum": min(numeric_values) if numeric_values else None, "maximum": max(numeric_values) if numeric_values else None, "trend": trend_direction(numeric_values) if len(numeric_values) > 1 else None},
        )
        investigation.record_observation(observation)
        return {"observation_id": observation.evidence_id, "metric": {"type": str(series.metric.metric_type), "labels": dict(series.metric.labels.values)}, "resource": self._resource(series.resource), "value": value, "unit": unit, "interval": {"start_time": interval.start_time.isoformat(), "end_time": interval.end_time.isoformat()}}

    def _record_alert_observation(self, alert: Alert, investigation: Investigation, step_id: InvestigationStepId | None) -> dict[str, object]:
        end = alert.end_time or alert.start_time + timedelta(microseconds=1)
        observation = Observation(
            ObservationId.new(), investigation.investigation_id,
            f"Alert {alert.alert_id} was {alert.status} with severity {alert.severity}.",
            step_id=step_id,
            metric_type=alert.metric.metric_type if alert.metric else None,
            resource_id=alert.resource.resource_id if alert.resource else None,
            interval=TimeInterval(alert.start_time, max(end, alert.start_time + timedelta(microseconds=1))),
            provenance={"source": "telemetry", "alert_id": alert.alert_id, "condition": alert.condition, "metadata": dict(alert.metadata)},
        )
        investigation.record_observation(observation)
        return {"observation_id": observation.evidence_id, "alert_id": alert.alert_id, "condition": alert.condition, "severity": alert.severity, "status": alert.status}

    def _bounded(self, items: list[Any]) -> tuple[list[Any], dict[str, object]]:
        returned = items[:self._policy.max_result_items]
        return returned, ResultMetadata(returned_count=len(returned), total_count_known=len(items), truncated=len(returned) < len(items)).model_dump(mode="json")

    @staticmethod
    def _descriptor(descriptor: MetricDescriptor) -> dict[str, object]:
        return {"metric_type": str(descriptor.metric_type), "description": descriptor.description, "unit": descriptor.unit, "value_type": descriptor.value_type, "metric_kind": descriptor.metric_kind, "labels": sorted(descriptor.label_keys)}

    @staticmethod
    def _resource(resource: MonitoredResource) -> dict[str, object]:
        return {"resource_id": str(resource.resource_id), "type": str(resource.resource_type), "project_id": str(resource.project_id), "labels": dict(resource.labels.values)}

    @staticmethod
    def _references(values: tuple[EvidenceReferenceArguments, ...]) -> tuple[EvidenceReference, ...]:
        return tuple(EvidenceReference(item.evidence_id, item.relationship) for item in values)

    def _finding(self, candidate: FindingArguments, investigation: Investigation) -> Finding:
        from gcp_observability_agent.domain.common.ids import FindingId
        return Finding(FindingId.new(), investigation.investigation_id, candidate.statement, self._references(candidate.evidence), candidate.confidence, candidate.significant_evidence_gap, candidate.causal_claim, candidate.temporal_correlation_only)

    def _hypothesis(self, candidate: HypothesisArguments, investigation: Investigation) -> Hypothesis:
        from gcp_observability_agent.domain.common.ids import HypothesisId
        return Hypothesis(HypothesisId.new(), investigation.investigation_id, candidate.statement, self._references(candidate.evidence), candidate.status, candidate.confidence, candidate.significant_evidence_gap, candidate.causal_claim, candidate.temporal_correlation_only)

    @staticmethod
    def _finding_data(finding: Finding) -> dict[str, object]:
        return {"statement": finding.statement, "support_level": finding.support_level.value, "evidence": [{"evidence_id": item.evidence_id, "relationship": item.relationship.value} for item in finding.evidence]}

    @staticmethod
    def _hypothesis_data(hypothesis: Hypothesis) -> dict[str, object]:
        return {"statement": hypothesis.statement, "status": hypothesis.status.value, "support_level": hypothesis.support_level.value, "evidence": [{"evidence_id": item.evidence_id, "relationship": item.relationship.value} for item in hypothesis.evidence]}

    @staticmethod
    def _identity(tool_name: ToolName, arguments: BaseModel) -> str:
        return f"{tool_name}:{json.dumps(arguments.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))}"

    @staticmethod
    def _result(request: ToolRequestEnvelope, status: ToolResultStatus, data: dict[str, object], warnings: tuple[str, ...] = ()) -> ToolResponse:
        return ToolResponse(request_id=request.request_id, tool_name=request.tool_name, status=status, data=data, warnings=warnings, provenance={"tool": request.tool_name.value})

    def _error(self, request: ToolRequestEnvelope, status: ToolResultStatus, code: str, message: str, error: ValidationError | None = None, *, retryable: bool = False, details: dict[str, object] | None = None) -> ToolResponse:
        safe_details = details or {}
        if error is not None:
            safe_details = {"validation_errors": [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]}
        return ToolResponse(request_id=request.request_id, tool_name=request.tool_name, status=status, error=ToolError(code=code, message=message, retryable=retryable, details=safe_details))

    @staticmethod
    def _unaddressed_error(raw_request: object, code: str, message: str, error: ValidationError) -> ToolResponse:
        request_id = raw_request.get("request_id", "invalid") if isinstance(raw_request, dict) else "invalid"
        return ToolResponse(request_id=str(request_id), tool_name=ToolName.SEARCH_METRIC_DESCRIPTORS, status=ToolResultStatus.INVALID_REQUEST, error=ToolError(code=code, message=message, details={"validation_errors": [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]}))
