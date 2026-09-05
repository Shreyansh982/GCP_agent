from __future__ import annotations

import pytest

from gcp_observability_agent.infrastructure.telemetry.mock.provider import MockTelemetryProvider


@pytest.fixture
def provider(tmp_path) -> MockTelemetryProvider:
    provider = MockTelemetryProvider(tmp_path / "mock-telemetry.sqlite3")
    provider.load_scenario("scenario_cpu_saturation")
    return provider

