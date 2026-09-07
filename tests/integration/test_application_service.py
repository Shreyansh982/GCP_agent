from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

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
    assert [event.name for event in events] == [
        "investigation_started",
        "step_started", "tool_completed",
        "step_started", "tool_completed", "evidence_created",
        "step_started", "tool_completed", "investigation_concluded",
    ]
    assert all(event.investigation_id == str(result.investigation_id) for event in events)


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

    settings = Settings.from_environment()

    assert settings.allowed_projects == ("project-a", "project-b")
    assert settings.max_tool_actions == 4
    assert settings.max_investigation_duration == timedelta(seconds=90)
    assert settings.mock_scenario == PROJECT
