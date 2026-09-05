"""Deterministic SQLite fixtures for mock observability scenarios."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta


SCENARIOS = frozenset({
    "scenario_cpu_saturation",
    "scenario_latency_without_cpu",
    "scenario_missing_data",
    "scenario_contradictory_evidence",
})


def load_scenario(connection: sqlite3.Connection, scenario_id: str) -> None:
    """Load a deterministic scenario without altering existing scenario records."""
    if scenario_id not in SCENARIOS:
        raise ValueError(f"unknown mock scenario: {scenario_id}")
    project_id = scenario_id
    base = datetime(2026, 8, 27, 14, tzinfo=UTC)
    _insert_descriptors(connection, base)
    connection.execute(
        "INSERT OR IGNORE INTO projects(project_id, display_name, created_at, metadata_json) VALUES (?, ?, ?, '{}')",
        (project_id, scenario_id, base.isoformat()),
    )
    resources = _scenario_resources(scenario_id)
    for resource_id, labels in resources:
        connection.execute(
            """INSERT OR IGNORE INTO monitored_resources(resource_id, project_id, resource_type, display_name, metadata_json, created_at)
               VALUES (?, ?, 'cloud_run_revision', ?, '{}', ?)""",
            (resource_id, project_id, resource_id, base.isoformat()),
        )
        for key, value in labels.items():
            connection.execute(
                "INSERT OR IGNORE INTO resource_labels(resource_id, label_key, label_value) VALUES (?, ?, ?)",
                (resource_id, key, value),
            )

    for metric_type, values_by_resource in _scenario_metrics(scenario_id).items():
        for resource_id, values in values_by_resource.items():
            metric_id = f"{scenario_id}:{metric_type}:{resource_id}"
            series_id = f"{metric_id}:series"
            connection.execute(
                "INSERT OR IGNORE INTO metrics(metric_id, metric_type, metadata_json) VALUES (?, ?, '{}')",
                (metric_id, metric_type),
            )
            connection.execute(
                """INSERT OR IGNORE INTO time_series(
                    time_series_id, metric_id, resource_id, metric_labels_json, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, '{}')""",
                (series_id, metric_id, resource_id, json.dumps({"route": "/charge"}), base.isoformat()),
            )
            for offset, value in enumerate(values):
                timestamp = (base + timedelta(minutes=5 * offset)).isoformat()
                point_id = f"{series_id}:{offset}"
                connection.execute(
                    """INSERT OR IGNORE INTO data_points(
                        data_point_id, time_series_id, timestamp, value_type, numeric_value
                    ) VALUES (?, ?, ?, 'DOUBLE', ?)""",
                    (point_id, series_id, timestamp, value),
                )
    if scenario_id == "scenario_cpu_saturation":
        connection.execute(
            """INSERT OR IGNORE INTO alerts(
                alert_id, project_id, policy_reference, condition_text, severity, status, start_time,
                resource_id, metadata_json, created_at
            ) VALUES (?, ?, 'high-cpu', 'CPU utilization above threshold', 'CRITICAL', 'OPEN', ?, ?, '{}', ?)""",
            (f"{scenario_id}:high-cpu", project_id, (base + timedelta(minutes=10)).isoformat(), resources[0][0], base.isoformat()),
        )


def _insert_descriptors(connection: sqlite3.Connection, created_at: datetime) -> None:
    descriptors = (
        ("example.googleapis.com/request_latency", "Request latency", "ms"),
        ("example.googleapis.com/request_count", "Request count", "1"),
        ("example.googleapis.com/cpu_utilization", "CPU utilization", "%"),
        ("example.googleapis.com/memory_utilization", "Memory utilization", "%"),
    )
    for metric_type, description, unit in descriptors:
        connection.execute(
            """INSERT OR IGNORE INTO metric_descriptors(
                metric_type, description, unit, value_type, metric_kind, metadata_json, created_at
            ) VALUES (?, ?, ?, 'DOUBLE', 'GAUGE', '{}', ?)""",
            (metric_type, description, unit, created_at.isoformat()),
        )
        connection.execute(
            """INSERT OR IGNORE INTO metric_descriptor_labels(metric_type, label_key, value_type, description)
               VALUES (?, 'route', 'STRING', 'HTTP route')""",
            (metric_type,),
        )


def _scenario_resources(scenario_id: str) -> tuple[tuple[str, dict[str, str]], ...]:
    primary = (f"{scenario_id}:payments-a", {"service": "payments", "environment": "production"})
    if scenario_id == "scenario_contradictory_evidence":
        return primary, (f"{scenario_id}:payments-b", {"service": "payments", "environment": "production"})
    return (primary,)


def _scenario_metrics(scenario_id: str) -> dict[str, dict[str, tuple[float, ...]]]:
    resources = [resource_id for resource_id, _ in _scenario_resources(scenario_id)]
    latency = (200.0, 220.0, 850.0, 900.0)
    normal_cpu = (35.0, 38.0, 36.0, 37.0)
    high_cpu = (40.0, 45.0, 91.0, 94.0)
    normal_memory = (55.0, 55.0, 56.0, 55.0)
    traffic = (100.0, 110.0, 310.0, 330.0)
    if scenario_id == "scenario_missing_data":
        return {"example.googleapis.com/request_latency": {resources[0]: latency}}
    if scenario_id == "scenario_latency_without_cpu":
        return {
            "example.googleapis.com/request_latency": {resources[0]: latency},
            "example.googleapis.com/cpu_utilization": {resources[0]: normal_cpu},
            "example.googleapis.com/memory_utilization": {resources[0]: normal_memory},
        }
    if scenario_id == "scenario_contradictory_evidence":
        return {
            "example.googleapis.com/request_latency": {resource: latency for resource in resources},
            "example.googleapis.com/cpu_utilization": {resources[0]: high_cpu, resources[1]: normal_cpu},
        }
    return {
        "example.googleapis.com/request_latency": {resources[0]: latency},
        "example.googleapis.com/request_count": {resources[0]: traffic},
        "example.googleapis.com/cpu_utilization": {resources[0]: high_cpu},
        "example.googleapis.com/memory_utilization": {resources[0]: normal_memory},
    }
