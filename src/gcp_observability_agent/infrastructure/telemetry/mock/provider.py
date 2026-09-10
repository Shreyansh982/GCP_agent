"""Deterministic SQLite-backed implementation of the telemetry provider port."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.telemetry.models import (
    Alert,
    DataPoint,
    Metric,
    MetricDescriptor,
    MetricLabels,
    MetricType,
    MonitoredResource,
    ProjectId,
    ResourceId,
    ResourceLabels,
    ResourceType,
    TimeSeries,
)
from gcp_observability_agent.infrastructure.persistence.sqlite.database import apply_migrations, connect, transaction
from gcp_observability_agent.infrastructure.telemetry.mock.fixtures import load_scenario


class MockTelemetryProvider:
    """A read-only provider contract implementation over deterministic mock data."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        apply_migrations(self._database_path)

    def load_scenario(self, scenario_id: str) -> None:
        with connect(self._database_path) as connection, transaction(connection):
            load_scenario(connection, scenario_id)

    def search_metric_descriptors(self, request: Mapping[str, object]) -> Sequence[MetricDescriptor]:
        query = str(request.get("query", "")).strip().lower()
        resource_type = request.get("resource_type")
        with connect(self._database_path) as connection:
            rows = connection.execute("SELECT * FROM metric_descriptors ORDER BY metric_type").fetchall()
            descriptors = [self._descriptor(connection, row) for row in rows]
            if query:
                descriptors = [
                    descriptor for descriptor in descriptors
                    if query in descriptor.metric_type.value.lower() or query in descriptor.description.lower()
                ]
            if resource_type:
                metric_types = {
                    row["metric_type"]
                    for row in connection.execute(
                        """SELECT DISTINCT m.metric_type FROM time_series ts
                           JOIN metrics m ON m.metric_id = ts.metric_id
                           JOIN monitored_resources r ON r.resource_id = ts.resource_id
                           WHERE r.resource_type = ?""",
                        (str(resource_type),),
                    )
                }
                descriptors = [descriptor for descriptor in descriptors if descriptor.metric_type.value in metric_types]
            return tuple(descriptors)

    def list_resources(self, request: Mapping[str, object]) -> Sequence[MonitoredResource]:
        project_id = request.get("project_id")
        resource_type = request.get("resource_type")
        labels = self._mapping(request.get("labels"))
        sql = "SELECT * FROM monitored_resources WHERE 1 = 1"
        parameters: list[str] = []
        if project_id:
            sql += " AND project_id = ?"
            parameters.append(str(project_id))
        if resource_type:
            sql += " AND resource_type = ?"
            parameters.append(str(resource_type))
        for key, value in labels.items():
            sql += " AND EXISTS (SELECT 1 FROM resource_labels rl WHERE rl.resource_id = monitored_resources.resource_id AND rl.label_key = ? AND rl.label_value = ?)"
            parameters.extend((key, str(value)))
        sql += " ORDER BY resource_id"
        collection_limit = request.get("_collection_limit")
        if isinstance(collection_limit, int) and collection_limit > 0:
            sql += " LIMIT ?"
            parameters.append(collection_limit)
        with connect(self._database_path) as connection:
            return tuple(self._resource(connection, row) for row in connection.execute(sql, parameters))

    def query_metric(self, request: Mapping[str, object]) -> Sequence[TimeSeries]:
        metric_request = self._mapping(request.get("metric"))
        resource_request = self._mapping(request.get("resource"))
        interval_request = self._mapping(request.get("interval"))
        metric_type = str(metric_request["type"])
        metric_labels = self._mapping(metric_request.get("labels"))
        resource_labels = self._mapping(resource_request.get("labels"))
        start_time = self._timestamp(interval_request["start_time"])
        end_time = self._timestamp(interval_request["end_time"])
        interval = TimeInterval(start_time, end_time)
        project_id = request.get("project_id")
        resource_type = resource_request.get("type")

        sql = """
            SELECT ts.*, m.metric_type, r.project_id, r.resource_type
            FROM time_series ts
            JOIN metrics m ON m.metric_id = ts.metric_id
            JOIN monitored_resources r ON r.resource_id = ts.resource_id
            WHERE m.metric_type = ?
        """
        parameters: list[str] = [metric_type]
        if project_id:
            sql += " AND r.project_id = ?"
            parameters.append(str(project_id))
        if resource_type:
            sql += " AND r.resource_type = ?"
            parameters.append(str(resource_type))
        for key, value in resource_labels.items():
            sql += " AND EXISTS (SELECT 1 FROM resource_labels rl WHERE rl.resource_id = r.resource_id AND rl.label_key = ? AND rl.label_value = ?)"
            parameters.extend((key, str(value)))
        sql += " ORDER BY ts.time_series_id"
        with connect(self._database_path) as connection:
            series: list[TimeSeries] = []
            for row in connection.execute(sql, parameters):
                labels = json.loads(row["metric_labels_json"])
                if not self._matches(labels, metric_labels):
                    continue
                points = self._points(connection, row["time_series_id"], interval)
                if not points:
                    continue
                resource = self._resource(connection, row)
                series.append(TimeSeries(Metric(MetricType(metric_type), MetricLabels(labels)), resource, tuple(points)))
            return tuple(self._aggregate(series, request.get("aggregation")))

    def get_alerts(self, request: Mapping[str, object]) -> Sequence[Alert]:
        resource_request = self._mapping(request.get("resource"))
        interval_request = self._mapping(request.get("interval"))
        severity = {str(value) for value in request.get("severity", [])}
        start_time = self._timestamp(interval_request["start_time"])
        end_time = self._timestamp(interval_request["end_time"])
        project_id = request.get("project_id")
        sql = "SELECT * FROM alerts WHERE start_time < ? AND (end_time IS NULL OR end_time > ?)"
        parameters: list[str] = [end_time.isoformat(), start_time.isoformat()]
        if project_id:
            sql += " AND project_id = ?"
            parameters.append(str(project_id))
        if severity:
            sql += f" AND severity IN ({','.join('?' for _ in severity)})"
            parameters.extend(sorted(severity))
        collection_limit = request.get("_collection_limit")
        if isinstance(collection_limit, int) and collection_limit > 0:
            sql += " LIMIT ?"
            parameters.append(collection_limit)
        with connect(self._database_path) as connection:
            alerts: list[Alert] = []
            for row in connection.execute(sql, parameters):
                resource = self._resource_by_id(connection, row["resource_id"]) if row["resource_id"] else None
                if resource and resource_request:
                    if resource_request.get("type") and resource.resource_type.value != resource_request["type"]:
                        continue
                    if not self._matches(resource.labels.values, self._mapping(resource_request.get("labels"))):
                        continue
                alerts.append(
                    Alert(
                        row["alert_id"], ProjectId(row["project_id"]), row["condition_text"], row["severity"],
                        row["status"], self._timestamp(row["start_time"]),
                        self._timestamp(row["end_time"]) if row["end_time"] else None, resource, None,
                        json.loads(row["metadata_json"] or "{}"),
                    )
                )
            return tuple(alerts)

    def _descriptor(self, connection, row) -> MetricDescriptor:
        label_keys = frozenset(
            label["label_key"] for label in connection.execute(
                "SELECT label_key FROM metric_descriptor_labels WHERE metric_type = ?", (row["metric_type"],)
            )
        )
        return MetricDescriptor(MetricType(row["metric_type"]), row["description"], label_keys, row["metric_kind"], row["value_type"], row["unit"], json.loads(row["metadata_json"] or "{}"))

    def _resource_by_id(self, connection, resource_id: str) -> MonitoredResource:
        row = connection.execute("SELECT * FROM monitored_resources WHERE resource_id = ?", (resource_id,)).fetchone()
        assert row is not None
        return self._resource(connection, row)

    def _resource(self, connection, row) -> MonitoredResource:
        labels = {
            label["label_key"]: label["label_value"]
            for label in connection.execute("SELECT label_key, label_value FROM resource_labels WHERE resource_id = ?", (row["resource_id"],))
        }
        return MonitoredResource(ResourceId(row["resource_id"]), ProjectId(row["project_id"]), ResourceType(row["resource_type"]), ResourceLabels(labels), json.loads(row["metadata_json"] or "{}"))

    def _points(self, connection, series_id: str, interval: TimeInterval) -> list[DataPoint]:
        rows = connection.execute(
            """SELECT * FROM data_points WHERE time_series_id = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp""",
            (series_id, interval.start_time.isoformat(), interval.end_time.isoformat()),
        )
        return [DataPoint(row["numeric_value"], timestamp=self._timestamp(row["timestamp"])) for row in rows]

    def _aggregate(self, series: Sequence[TimeSeries], aggregation: object) -> Sequence[TimeSeries]:
        config = self._mapping(aggregation)
        if not config:
            return series
        reducer = str(config.get("cross_series_reducer", "REDUCE_NONE"))
        period = config.get("alignment_period")
        aligner = str(config.get("per_series_aligner", "ALIGN_NONE"))
        if reducer != "REDUCE_NONE" and not period:
            raise ValueError("cross-series reduction requires alignment_period")
        aligned = [self._align(item, str(period), aligner) if period else item for item in series]
        if reducer == "REDUCE_NONE":
            return aligned
        if reducer not in {"REDUCE_MEAN", "REDUCE_MIN", "REDUCE_MAX", "REDUCE_SUM"}:
            raise ValueError(f"unsupported cross-series reducer: {reducer}")
        return self._reduce(aligned, reducer, tuple(config.get("group_by_fields", ())))

    def _align(self, series: TimeSeries, period: str, aligner: str) -> TimeSeries:
        duration = self._duration(period)
        buckets: dict[datetime, list[float]] = defaultdict(list)
        origin = series.points[0].timestamp
        assert origin is not None
        for point in series.points:
            assert point.timestamp is not None
            bucket = origin + timedelta(seconds=((point.timestamp - origin).total_seconds() // duration.total_seconds()) * duration.total_seconds())
            buckets[bucket].append(float(point.value))
        operation = {"ALIGN_MEAN": lambda values: sum(values) / len(values), "ALIGN_MIN": min, "ALIGN_MAX": max, "ALIGN_SUM": sum}.get(aligner)
        if operation is None:
            raise ValueError(f"unsupported per-series aligner: {aligner}")
        return TimeSeries(series.metric, series.resource, tuple(DataPoint(operation(values), timestamp=bucket) for bucket, values in sorted(buckets.items())))

    def _reduce(self, series: Sequence[TimeSeries], reducer: str, group_by_fields: tuple[object, ...]) -> Sequence[TimeSeries]:
        groups: dict[tuple[object, ...], list[TimeSeries]] = defaultdict(list)
        for item in series:
            group = tuple(item.resource.labels.values.get(str(field)) for field in group_by_fields)
            groups[group].append(item)
        operation = {"REDUCE_MEAN": lambda values: sum(values) / len(values), "REDUCE_MIN": min, "REDUCE_MAX": max, "REDUCE_SUM": sum}[reducer]
        reduced: list[TimeSeries] = []
        for group, items in groups.items():
            buckets: dict[datetime, list[float]] = defaultdict(list)
            for item in items:
                for point in item.points:
                    assert point.timestamp is not None
                    buckets[point.timestamp].append(float(point.value))
            first = items[0]
            labels = {str(field): value for field, value in zip(group_by_fields, group) if value is not None}
            labels["aggregated"] = "true"
            resource = MonitoredResource(ResourceId(f"aggregate:{first.metric.metric_type.value}:{group}"), first.resource.project_id, first.resource.resource_type, ResourceLabels(labels))
            points = tuple(DataPoint(operation(values), timestamp=timestamp) for timestamp, values in sorted(buckets.items()))
            reduced.append(TimeSeries(first.metric, resource, points))
        return reduced

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _matches(candidate: Mapping[str, object], filters: Mapping[str, object]) -> bool:
        return all(str(candidate.get(key)) == str(value) for key, value in filters.items())

    @staticmethod
    def _timestamp(value: object) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def _duration(value: str) -> timedelta:
        units = {"m": 60, "h": 3600, "d": 86400}
        if len(value) < 2 or value[-1] not in units:
            raise ValueError(f"unsupported alignment period: {value}")
        return timedelta(seconds=int(value[:-1]) * units[value[-1]])
