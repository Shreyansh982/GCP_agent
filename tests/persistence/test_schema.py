from __future__ import annotations

import sqlite3

import pytest

from gcp_observability_agent.infrastructure.persistence.sqlite.database import connect, transaction


def test_initial_migration_creates_telemetry_and_investigation_schema(repository) -> None:
    with connect(repository._database_path) as connection:
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {
        "projects", "metric_descriptors", "monitored_resources", "metrics", "time_series", "data_points", "alerts",
        "investigations", "investigation_scopes", "investigation_steps", "tool_requests", "tool_results",
        "observations", "deterministic_analyses", "evidence_references", "hypotheses", "findings",
        "investigation_outcomes", "schema_migrations",
    } <= tables


def test_foreign_keys_are_enabled_and_enforced(repository) -> None:
    with connect(repository._database_path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO tool_requests(request_id, step_id, tool_name, arguments_json, requested_at, validation_status)
                VALUES ('bad-request', 'missing-step', 'query_metric', '{}', '2026-01-01T00:00:00+00:00', 'VALID')"""
            )


def test_migrations_are_idempotent(repository) -> None:
    from gcp_observability_agent.infrastructure.persistence.sqlite.repository import SQLiteInvestigationRepository

    SQLiteInvestigationRepository(repository._database_path)
    with connect(repository._database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_repository_transaction_rolls_back_all_rows_when_audit_insert_fails(repository, investigation) -> None:
    observation = investigation.observations[0]
    invalid = type(observation)(
        observation.observation_id, observation.investigation_id, observation.statement,
        step_id=type(observation.step_id).new(), provenance=observation.provenance,
    )
    investigation._observations[invalid.evidence_id] = invalid

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(investigation)
    with connect(repository._database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM investigations").fetchone()[0] == 0


def test_historical_tool_results_observations_and_analyses_cannot_be_rewritten(repository, investigation) -> None:
    repository.save(investigation)
    observation = investigation.observations[0]
    analysis = investigation.analyses[0]
    result = investigation.steps[0].tool_result
    assert result is not None
    with connect(repository._database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE tool_results SET status = 'timeout' WHERE result_id = ?", (str(result.result_id),))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE observations SET statement = 'changed' WHERE observation_id = ?", (str(observation.observation_id),))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE deterministic_analyses SET operation = 'changed' WHERE analysis_id = ?", (str(analysis.analysis_id),))

