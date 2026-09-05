from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from gcp_observability_agent.domain.common.ids import AnalysisId, InvestigationId, ObservationId
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.telemetry.models import (
    DataPoint,
    Metric,
    MetricLabels,
    MetricType,
    MonitoredResource,
    ProjectId,
    ResourceId,
    ResourceLabels,
    ResourceType,
    TimeSeries,
)


def test_application_ids_are_unique_and_evidence_ids_are_namespaced() -> None:
    assert InvestigationId.new() != InvestigationId.new()
    assert str(ObservationId.new()).startswith("obs-")
    assert str(AnalysisId.new()).startswith("analysis-")


def test_time_interval_requires_aware_increasing_times_and_normalizes_to_utc() -> None:
    start = datetime(2026, 8, 27, 10, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    interval = TimeInterval(start, start + timedelta(minutes=15))

    assert interval.start_time.tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeInterval(datetime(2026, 8, 27, 10), datetime(2026, 8, 27, 11))
    with pytest.raises(ValueError, match="later"):
        TimeInterval(interval.end_time, interval.start_time)


def test_metric_and_resource_label_namespaces_remain_distinct_and_immutable() -> None:
    metric_labels = MetricLabels({"response_code": "500"})
    resource_labels = ResourceLabels({"service": "payments"})

    assert metric_labels.values != resource_labels.values
    with pytest.raises(TypeError):
        metric_labels.values["new"] = "value"  # type: ignore[index]


def test_data_point_requires_exactly_one_time_representation() -> None:
    timestamp = datetime(2026, 8, 27, 10, tzinfo=UTC)
    interval = TimeInterval(timestamp, timestamp + timedelta(minutes=1))

    with pytest.raises(ValueError, match="exactly one"):
        DataPoint(1.0)
    with pytest.raises(ValueError, match="exactly one"):
        DataPoint(1.0, timestamp=timestamp, interval=interval)


def test_time_series_preserves_metric_resource_identity_and_point_order() -> None:
    timestamp = datetime(2026, 8, 27, 10, tzinfo=UTC)
    metric = Metric(MetricType("example.googleapis.com/cpu"), MetricLabels({"state": "user"}))
    resource = MonitoredResource(
        ResourceId("instance-1"),
        ProjectId("production-project"),
        ResourceType("gce_instance"),
        ResourceLabels({"environment": "production"}),
    )
    later = DataPoint(2.0, timestamp=timestamp + timedelta(minutes=1))
    earlier = DataPoint(1.0, timestamp=timestamp)

    series = TimeSeries(metric, resource, (earlier, later))
    assert series.metric.labels.values["state"] == "user"
    assert series.resource.labels.values["environment"] == "production"
    with pytest.raises(ValueError, match="ordered"):
        TimeSeries(metric, resource, (later, earlier))

