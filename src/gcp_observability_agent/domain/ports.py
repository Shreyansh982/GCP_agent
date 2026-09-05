"""Provider and repository abstractions owned by the core."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from gcp_observability_agent.domain.common.ids import InvestigationId
from gcp_observability_agent.domain.investigation.models import Investigation, ToolRequest
from gcp_observability_agent.domain.telemetry.models import Alert, MetricDescriptor, MonitoredResource, TimeSeries


class TelemetryProvider(Protocol):
    """The controlled, provider-neutral telemetry capabilities."""

    def search_metric_descriptors(self, request: Mapping[str, object]) -> Sequence[MetricDescriptor]: ...

    def query_metric(self, request: Mapping[str, object]) -> Sequence[TimeSeries]: ...

    def list_resources(self, request: Mapping[str, object]) -> Sequence[MonitoredResource]: ...

    def get_alerts(self, request: Mapping[str, object]) -> Sequence[Alert]: ...


class LLMProvider(Protocol):
    """Converts a bounded application-built context into a structured action."""

    def next_action(self, context: Mapping[str, object]) -> ToolRequest: ...


class InvestigationRepository(Protocol):
    """Persistence boundary for the investigation aggregate."""

    def save(self, investigation: Investigation) -> None: ...

    def get(self, investigation_id: InvestigationId) -> Investigation | None: ...

