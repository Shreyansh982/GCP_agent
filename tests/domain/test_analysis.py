from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.investigation.analysis import (
    TrendDirection,
    maximum,
    mean,
    minimum,
    percentage_change,
    temporal_overlap,
    trend_direction,
)


def test_numeric_analysis_primitives_are_deterministic() -> None:
    values = (10, 20, 30)
    assert minimum(values) == 10
    assert maximum(values) == 30
    assert mean(values) == 20
    assert percentage_change(20, 25) == 25
    assert trend_direction(values) is TrendDirection.INCREASING
    assert trend_direction((30, 20, 10)) is TrendDirection.DECREASING
    assert trend_direction((10, 30, 10)) is TrendDirection.STABLE


def test_percentage_change_rejects_zero_baseline() -> None:
    with pytest.raises(ValueError, match="zero baseline"):
        percentage_change(0, 10)


def test_temporal_overlap_distinguishes_touching_from_overlapping_intervals() -> None:
    start = datetime(2026, 8, 27, 10, tzinfo=UTC)
    first = TimeInterval(start, start + timedelta(minutes=10))
    overlapping = TimeInterval(start + timedelta(minutes=9), start + timedelta(minutes=20))
    touching = TimeInterval(start + timedelta(minutes=10), start + timedelta(minutes=20))

    assert temporal_overlap(first, overlapping)
    assert not temporal_overlap(first, touching)

