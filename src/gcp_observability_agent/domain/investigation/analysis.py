"""Small, reproducible numerical analysis primitives."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from statistics import fmean

from gcp_observability_agent.domain.common.time import TimeInterval


class TrendDirection(StrEnum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"


def _numeric_values(values: Iterable[int | float]) -> tuple[float, ...]:
    normalized = tuple(float(value) for value in values)
    if not normalized:
        raise ValueError("at least one value is required")
    return normalized


def minimum(values: Iterable[int | float]) -> float:
    return min(_numeric_values(values))


def maximum(values: Iterable[int | float]) -> float:
    return max(_numeric_values(values))


def mean(values: Iterable[int | float]) -> float:
    return fmean(_numeric_values(values))


def percentage_change(baseline: int | float, current: int | float) -> float:
    """Return the percentage change from a non-zero baseline."""
    if baseline == 0:
        raise ValueError("percentage change is undefined for a zero baseline")
    return ((float(current) - float(baseline)) / float(baseline)) * 100


def trend_direction(values: Iterable[int | float]) -> TrendDirection:
    """Classify direction deterministically from the first and last observation."""
    normalized = _numeric_values(values)
    if normalized[-1] > normalized[0]:
        return TrendDirection.INCREASING
    if normalized[-1] < normalized[0]:
        return TrendDirection.DECREASING
    return TrendDirection.STABLE


def temporal_overlap(first: TimeInterval, second: TimeInterval) -> bool:
    return first.overlaps(second)

