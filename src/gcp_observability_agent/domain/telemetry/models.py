"""Provider-independent telemetry value types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, TypeAlias

from gcp_observability_agent.domain.common.time import TimeInterval, normalized_utc


ScalarValue: TypeAlias = int | float | str | bool


def _non_empty(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _frozen_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    for key in values:
        _non_empty(key, "label key")
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class ProjectId:
    value: str

    def __post_init__(self) -> None:
        _non_empty(self.value, "project_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MetricType:
    value: str

    def __post_init__(self) -> None:
        _non_empty(self.value, "metric type")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ResourceType:
    value: str

    def __post_init__(self) -> None:
        _non_empty(self.value, "resource type")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ResourceId:
    value: str

    def __post_init__(self) -> None:
        _non_empty(self.value, "resource_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MetricLabels:
    """Metric-label values, kept separate from resource labels."""

    values: Mapping[str, ScalarValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _frozen_mapping(self.values))


@dataclass(frozen=True, slots=True)
class ResourceLabels:
    """Monitored-resource-label values, kept separate from metric labels."""

    values: Mapping[str, ScalarValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _frozen_mapping(self.values))


@dataclass(frozen=True, slots=True)
class MetricDescriptor:
    metric_type: MetricType
    description: str
    label_keys: frozenset[str] = field(default_factory=frozenset)
    metric_kind: str | None = None
    value_type: str | None = None
    unit: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty(self.description, "metric description")
        for key in self.label_keys:
            _non_empty(key, "metric descriptor label key")
        object.__setattr__(self, "label_keys", frozenset(self.label_keys))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class Metric:
    metric_type: MetricType
    labels: MetricLabels = field(default_factory=MetricLabels)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class MonitoredResource:
    resource_id: ResourceId
    project_id: ProjectId
    resource_type: ResourceType
    labels: ResourceLabels = field(default_factory=ResourceLabels)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class DataPoint:
    value: ScalarValue
    timestamp: datetime | None = None
    interval: TimeInterval | None = None

    def __post_init__(self) -> None:
        if (self.timestamp is None) == (self.interval is None):
            raise ValueError("a data point must have exactly one timestamp or interval")
        if self.timestamp is not None:
            object.__setattr__(self, "timestamp", normalized_utc(self.timestamp))

    @property
    def sort_time(self) -> datetime:
        return self.timestamp if self.timestamp is not None else self.interval.start_time  # type: ignore[union-attr]


@dataclass(frozen=True, slots=True)
class TimeSeries:
    metric: Metric
    resource: MonitoredResource
    points: tuple[DataPoint, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        points = tuple(self.points)
        if any(right.sort_time <= left.sort_time for left, right in zip(points, points[1:])):
            raise ValueError("time-series points must be strictly ordered by time")
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    project_id: ProjectId
    condition: str
    severity: str
    status: str
    start_time: datetime
    end_time: datetime | None = None
    resource: MonitoredResource | None = None
    metric: Metric | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty(self.alert_id, "alert_id")
        _non_empty(self.condition, "alert condition")
        object.__setattr__(self, "start_time", normalized_utc(self.start_time))
        if self.end_time is not None:
            end_time = normalized_utc(self.end_time)
            if end_time < self.start_time:
                raise ValueError("alert end_time must not be earlier than start_time")
            object.__setattr__(self, "end_time", end_time)
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

