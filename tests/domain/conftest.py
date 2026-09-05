from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.investigation.models import (
    Investigation,
    InvestigationScope,
    TemporalContext,
)


@pytest.fixture
def interval() -> TimeInterval:
    start = datetime(2026, 8, 27, 14, tzinfo=UTC)
    return TimeInterval(start, start + timedelta(hours=1))


@pytest.fixture
def investigation(interval: TimeInterval) -> Investigation:
    return Investigation.create(
        "Why did payments become slow?",
        InvestigationScope(service="payments", environment="production"),
        TemporalContext(reference_time=interval.end_time, resolved_interval=interval),
    )

