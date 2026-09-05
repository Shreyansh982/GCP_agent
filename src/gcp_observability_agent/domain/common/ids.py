"""Application-generated domain identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class UuidId:
    """A stable application-generated UUID identifier."""

    value: str
    prefix: ClassVar[str] = ""

    def __post_init__(self) -> None:
        candidate = self.value.removeprefix(self.prefix) if self.prefix else self.value
        try:
            UUID(candidate)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{type(self).__name__} must contain a UUID") from exc
        if self.prefix and not self.value.startswith(self.prefix):
            raise ValueError(f"{type(self).__name__} must start with {self.prefix!r}")

    @classmethod
    def new(cls):
        return cls(f"{cls.prefix}{uuid4()}")

    def __str__(self) -> str:
        return self.value


class InvestigationId(UuidId):
    """Identity of one investigation aggregate."""


class InvestigationStepId(UuidId):
    """Identity of one recorded investigation action."""


class ToolRequestId(UuidId):
    """Identity of one attempted tool request."""


class ToolResultId(UuidId):
    """Identity of one recorded tool result."""


class HypothesisId(UuidId):
    """Identity of one hypothesis."""


class FindingId(UuidId):
    """Identity of one finding."""


class ObservationId(UuidId):
    """Application-generated observation evidence ID."""

    prefix = "obs-"


class AnalysisId(UuidId):
    """Application-generated deterministic-analysis evidence ID."""

    prefix = "analysis-"

