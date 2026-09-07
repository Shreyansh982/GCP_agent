"""Non-authoritative progress notifications for application consumers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    name: str
    investigation_id: str
    step_id: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


ProgressSink = Callable[[ProgressEvent], None]
