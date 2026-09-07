"""Small structured logging helpers that avoid emitting sensitive values."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from gcp_observability_agent.application.common.events import ProgressEvent, ProgressSink


_SENSITIVE_KEY_PARTS = ("api_key", "authorization", "credential", "password", "private_key", "secret", "session", "token")


def redact(value: object) -> object:
    """Redact known secret-bearing fields while retaining useful event structure."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class StructuredLogger:
    """Emits compact JSON records without prompts, raw telemetry, or secrets."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("gcp_observability_agent")

    def info(self, event: str, **fields: object) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: object) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: object) -> None:
        self._emit(logging.ERROR, event, fields)

    def _emit(self, level: int, event: str, fields: Mapping[str, object]) -> None:
        self._logger.log(level, json.dumps({"event": event, **redact(fields)}, default=str, sort_keys=True))


class ProgressObserver:
    """Forwards progress to an optional consumer and records safe operational logs."""

    def __init__(self, logger: StructuredLogger, sink: ProgressSink | None = None) -> None:
        self._logger = logger
        self._sink = sink

    def __call__(self, event: ProgressEvent) -> None:
        self._logger.info(
            event.name,
            investigation_id=event.investigation_id,
            step_id=event.step_id,
            **dict(event.details),
        )
        if self._sink is not None:
            self._sink(event)
