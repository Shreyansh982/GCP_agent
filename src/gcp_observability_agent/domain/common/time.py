"""Time value objects used by the provider-independent domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def normalized_utc(value: datetime) -> datetime:
    """Validate an aware timestamp and normalize it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """An explicit, non-empty UTC interval."""

    start_time: datetime
    end_time: datetime

    def __post_init__(self) -> None:
        start_time = normalized_utc(self.start_time)
        end_time = normalized_utc(self.end_time)
        if start_time >= end_time:
            raise ValueError("end_time must be later than start_time")
        object.__setattr__(self, "start_time", start_time)
        object.__setattr__(self, "end_time", end_time)

    @property
    def duration(self) -> timedelta:
        return self.end_time - self.start_time

    def overlaps(self, other: "TimeInterval") -> bool:
        return self.start_time < other.end_time and other.start_time < self.end_time

