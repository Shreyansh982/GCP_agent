from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from gcp_observability_agent.application.common.observability import StructuredLogger
from gcp_observability_agent.application.investigations.fake_llm import FakeLLMProvider
from gcp_observability_agent.bootstrap.container import build_phase_one_container
from gcp_observability_agent.domain.common.ids import ToolRequestId
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.investigation.models import (
    InvestigationScope,
    TemporalContext,
    ToolName,
    ToolRequest,
)
from gcp_observability_agent.domain.telemetry.models import ProjectId
from gcp_observability_agent.infrastructure.configuration.settings import Settings


PROJECT = "scenario_cpu_saturation"
INTERVAL = {"start_time": "2026-08-27T14:00:00Z", "end_time": "2026-08-27T14:20:00Z"}


def _action(tool_name: ToolName, arguments: dict[str, object]) -> ToolRequest:
    return ToolRequest(ToolRequestId.new(), tool_name, arguments, datetime(2026, 8, 27, 15, tzinfo=UTC))


def _conclusion(context) -> ToolRequest:
    evidence_id = context["evidence"]["observations"][0]["evidence_id"]
    return _action(
        ToolName.CONCLUDE_INVESTIGATION,
        {"findings": [{"statement": "CPU was elevated during the observed interval.", "evidence": [{"evidence_id": evidence_id}]}]},
    )


def _temporal_context() -> TemporalContext:
    start = datetime(2026, 8, 27, 14, tzinfo=UTC)
    return TemporalContext(start + timedelta(hours=1), TimeInterval(start, start + timedelta(hours=1)))


def test_phase_one_container_runs_fake_llm_mock_telemetry_and_sqlite_end_to_end(tmp_path) -> None:
    events = []
    llm = FakeLLMProvider([
        _action(ToolName.SEARCH_METRIC_DESCRIPTORS, {"query": "cpu"}),
        _action(
            ToolName.QUERY_METRIC,
            {
                "metric": {"type": "example.googleapis.com/cpu_utilization", "labels": {"route": "/charge"}},
                "resource": {"type": "cloud_run_revision", "labels": {"service": "payments"}},
                "interval": INTERVAL,
            },
        ),
        _conclusion,
    ])
    llm.last_usage = SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20)
    container = build_phase_one_container(
        llm,
        settings=Settings(
            database_path=str(tmp_path / "phase-one.sqlite3"),
            allowed_projects=(PROJECT,),
            mock_scenario=PROJECT,
        ),
        progress_sink=events.append,
    )

    result = container.application_service.investigate(
        "Why did payments become slow?",
        InvestigationScope(project_id=ProjectId(PROJECT), service="payments", environment="production"),
        _temporal_context(),
    )
    persisted = container.repository.get(result.investigation_id)

    assert result.outcome.status.value == "COMPLETED"
    assert len(result.observations) == 1
    assert len(result.findings) == 1
    assert persisted is not None and persisted.outcome == result.outcome
    assert [event.name for event in events if event.name not in {"persistence_succeeded", "llm_usage_recorded"}] == [
        "investigation_started",
        "step_started", "tool_completed",
        "step_started", "tool_completed", "evidence_created",
        "step_started", "tool_completed", "investigation_concluded",
    ]
    assert all(event.investigation_id == str(result.investigation_id) for event in events)
    assert all(event.step_id is not None for event in events if event.name in {"step_started", "tool_completed"})
    assert any(event.name == "persistence_succeeded" and event.details["terminal"] for event in events)
    assert [event.details["total_tokens"] for event in events if event.name == "llm_usage_recorded"] == [20, 20, 20]
    assert container.metrics.counters["tool_calls_total"] == 3
    assert container.metrics.counters["repository_write_total"] == 6
    assert container.metrics.counters["llm_usage_events_total"] == 3
    assert "investigation_duration_seconds" in container.metrics.timer_totals


def test_structured_logging_redacts_secret_fields(caplog) -> None:
    logger = StructuredLogger(logging.getLogger("test.gcp_observability_agent"))

    with caplog.at_level(logging.INFO, logger="test.gcp_observability_agent"):
        logger.info(
            "tool_completed",
            investigation_id="inv-1",
            access_token="do-not-log",
            nested={"database_password": "also-do-not-log"},
        )

    assert "do-not-log" not in caplog.text
    assert "also-do-not-log" not in caplog.text
    assert "[REDACTED]" in caplog.text
    assert '"event": "tool_completed"' in caplog.text


def test_environment_configuration_wires_safe_runtime_limits(monkeypatch) -> None:
    monkeypatch.setenv("GCP_AGENT_ALLOWED_PROJECTS", "project-a, project-b")
    monkeypatch.setenv("GCP_AGENT_MAX_TOOL_ACTIONS", "4")
    monkeypatch.setenv("GCP_AGENT_MAX_INVESTIGATION_SECONDS", "90")
    monkeypatch.setenv("GCP_AGENT_MOCK_SCENARIO", PROJECT)
    monkeypatch.setenv("GCP_AGENT_MAX_INVESTIGATION_QUESTION_LENGTH", "4000")
    monkeypatch.setenv("GCP_AGENT_MAX_TOOL_REQUEST_PAYLOAD_BYTES", "32768")
    monkeypatch.setenv("GCP_AGENT_MAX_LABEL_FILTER_ENTRIES", "50")
    monkeypatch.setenv("GCP_AGENT_MAX_COLLECTION_ITEMS", "100")

    settings = Settings.from_environment()

    assert settings.allowed_projects == ("project-a", "project-b")
    assert settings.max_tool_actions == 4
    assert settings.max_investigation_duration == timedelta(seconds=90)
    assert settings.mock_scenario == PROJECT
    assert settings.max_investigation_question_length == 4_000
    assert settings.max_tool_request_payload_bytes == 32 * 1024
    assert settings.max_label_filter_entries == 50
    assert settings.max_collection_items == 100


def test_application_service_enforces_the_configured_question_limit(tmp_path) -> None:
    container = build_phase_one_container(
        FakeLLMProvider([]),
        settings=Settings(
            database_path=str(tmp_path / "question-limit.sqlite3"),
            max_investigation_question_length=4_000,
        ),
    )

    with pytest.raises(ValueError, match="4000"):
        container.application_service.investigate(
            "x" * 4_001,
            InvestigationScope(),
            _temporal_context(),
        )


def test_observability_records_authorization_rejections_and_truncated_results(tmp_path) -> None:
    project = "scenario_contradictory_evidence"
    llm = FakeLLMProvider([
        _action(ToolName.LIST_RESOURCES, {"resource_type": "cloud_run_revision"}),
        _action(ToolName.CONCLUDE_INVESTIGATION, {}),
    ])
    events = []
    container = build_phase_one_container(
        llm,
        settings=Settings(
            database_path=str(tmp_path / "truncated.sqlite3"),
            allowed_projects=(project,),
            mock_scenario=project,
            max_result_items=1,
        ),
        progress_sink=events.append,
    )

    result = container.application_service.investigate(
        "List affected resources.",
        InvestigationScope(project_id=ProjectId(project)),
        _temporal_context(),
    )

    assert result.outcome.status.value == "INSUFFICIENT_EVIDENCE"
    assert next(event for event in events if event.name == "tool_completed").details["truncated"] is True
    assert container.metrics.counters["truncated_results_total"] == 1

    denied_llm = FakeLLMProvider([
        _action(
            ToolName.QUERY_METRIC,
            {
                "project_id": "other-project",
                "metric": {"type": "example.googleapis.com/cpu_utilization", "labels": {}},
                "resource": {"type": "cloud_run_revision", "labels": {}},
                "interval": INTERVAL,
            },
        ),
        _action(ToolName.CONCLUDE_INVESTIGATION, {}),
    ])
    denied_events = []
    denied = build_phase_one_container(
        denied_llm,
        settings=Settings(
            database_path=str(tmp_path / "denied.sqlite3"),
            allowed_projects=(PROJECT,),
            mock_scenario=PROJECT,
        ),
        progress_sink=denied_events.append,
    )

    denied.application_service.investigate(
        "Check another project.", InvestigationScope(project_id=ProjectId(PROJECT)), _temporal_context()
    )

    completed = next(event for event in denied_events if event.name == "tool_completed")
    assert completed.details["error_code"] == "PROJECT_NOT_AUTHORIZED"
    assert denied.metrics.counters["authorization_denied_total"] == 1
    assert denied.metrics.counters["policy_rejections_total"] == 1
