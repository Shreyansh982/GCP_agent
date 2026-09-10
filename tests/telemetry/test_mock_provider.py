from __future__ import annotations

from gcp_observability_agent.infrastructure.telemetry.mock.fixtures import SCENARIOS
from gcp_observability_agent.infrastructure.telemetry.mock.provider import MockTelemetryProvider


PROJECT = "scenario_cpu_saturation"
INTERVAL = {"start_time": "2026-08-27T14:00:00Z", "end_time": "2026-08-27T14:20:00Z"}


def test_mock_provider_exposes_the_required_provider_capabilities(provider) -> None:
    assert all(
        callable(getattr(provider, method))
        for method in ("search_metric_descriptors", "query_metric", "list_resources", "get_alerts")
    )


def test_descriptor_and_resource_discovery_are_deterministic(provider) -> None:
    descriptors = provider.search_metric_descriptors({"query": "cpu", "resource_type": "cloud_run_revision"})
    resources = provider.list_resources(
        {"project_id": PROJECT, "resource_type": "cloud_run_revision", "labels": {"service": "payments"}}
    )

    assert [descriptor.metric_type.value for descriptor in descriptors] == ["example.googleapis.com/cpu_utilization"]
    assert descriptors[0].label_keys == frozenset({"route"})
    assert len(resources) == 1
    assert resources[0].labels.values["environment"] == "production"


def test_metric_query_preserves_metric_and_resource_labels_and_is_repeatable(provider) -> None:
    request = {
        "project_id": PROJECT,
        "metric": {"type": "example.googleapis.com/cpu_utilization", "labels": {"route": "/charge"}},
        "resource": {"type": "cloud_run_revision", "labels": {"service": "payments"}},
        "interval": INTERVAL,
    }
    first = provider.query_metric(request)
    second = provider.query_metric(request)

    assert first == second
    assert len(first) == 1
    assert [point.value for point in first[0].points] == [40.0, 45.0, 91.0, 94.0]
    assert first[0].metric.labels.values == {"route": "/charge"}
    assert first[0].resource.labels.values["service"] == "payments"


def test_alignment_and_cross_series_reduction_are_deterministic(tmp_path) -> None:
    provider = MockTelemetryProvider(tmp_path / "contradictory.sqlite3")
    provider.load_scenario("scenario_contradictory_evidence")
    result = provider.query_metric(
        {
            "project_id": "scenario_contradictory_evidence",
            "metric": {"type": "example.googleapis.com/cpu_utilization", "labels": {}},
            "resource": {"type": "cloud_run_revision", "labels": {"service": "payments"}},
            "interval": INTERVAL,
            "aggregation": {
                "alignment_period": "5m",
                "per_series_aligner": "ALIGN_MEAN",
                "cross_series_reducer": "REDUCE_MEAN",
                "group_by_fields": ["environment"],
            },
        }
    )

    assert len(result) == 1
    assert [point.value for point in result[0].points] == [37.5, 41.5, 63.5, 65.5]
    assert result[0].resource.labels.values == {"environment": "production", "aggregated": "true"}


def test_alert_retrieval_and_scenario_loading_are_deterministic(provider, tmp_path) -> None:
    alerts = provider.get_alerts({"project_id": PROJECT, "interval": INTERVAL, "severity": ["CRITICAL"]})
    missing = MockTelemetryProvider(tmp_path / "missing.sqlite3")
    missing.load_scenario("scenario_missing_data")
    no_cpu = missing.query_metric(
        {
            "project_id": "scenario_missing_data",
            "metric": {"type": "example.googleapis.com/cpu_utilization", "labels": {}},
            "resource": {"type": "cloud_run_revision", "labels": {}},
            "interval": INTERVAL,
        }
    )

    assert len(alerts) == 1
    assert alerts[0].severity == "CRITICAL"
    assert no_cpu == ()
    assert "scenario_missing_data" in SCENARIOS


def test_traffic_surge_fixture_is_available_and_contains_the_expected_metrics(tmp_path) -> None:
    provider = MockTelemetryProvider(tmp_path / "traffic.sqlite3")
    provider.load_scenario("scenario_traffic_surge")

    metrics = provider.search_metric_descriptors({"resource_type": "cloud_run_revision"})

    assert {metric.metric_type.value for metric in metrics} >= {
        "example.googleapis.com/request_count",
        "example.googleapis.com/cpu_utilization",
        "example.googleapis.com/request_latency",
    }


def test_invalid_aggregation_is_explicit(provider) -> None:
    request = {
        "project_id": PROJECT,
        "metric": {"type": "example.googleapis.com/cpu_utilization", "labels": {}},
        "resource": {"type": "cloud_run_revision", "labels": {}},
        "interval": INTERVAL,
        "aggregation": {"cross_series_reducer": "REDUCE_MEAN"},
    }
    import pytest

    with pytest.raises(ValueError, match="requires alignment"):
        provider.query_metric(request)
