"""Small structured logging helpers that avoid emitting sensitive values."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Mapping
from time import monotonic
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


class OperationalMetrics:
    """Small, process-local Phase 1 counters and timers without metric labels."""

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.timer_totals: dict[str, float] = {}
        self._started_at: dict[str, float] = {}

    def record(self, event: ProgressEvent) -> None:
        self.counters[f"{event.name}_total"] += 1
        if event.name == "investigation_started":
            self._started_at[event.investigation_id] = monotonic()
        elif event.name in {"investigation_concluded", "investigation_terminated"}:
            started_at = self._started_at.pop(event.investigation_id, None)
            if started_at is not None:
                self.timer_totals["investigation_duration_seconds"] = (
                    self.timer_totals.get("investigation_duration_seconds", 0.0) + monotonic() - started_at
                )
        elif event.name == "tool_completed":
            self.counters["tool_calls_total"] += 1
            if event.details.get("truncated"):
                self.counters["truncated_results_total"] += 1
            error_code = event.details.get("error_code")
            if error_code in {"PROJECT_NOT_AUTHORIZED", "PROJECT_SCOPE_MISMATCH"}:
                self.counters["authorization_denied_total"] += 1
            if event.details.get("status") == "policy_rejected":
                self.counters["policy_rejections_total"] += 1
        elif event.name == "persistence_succeeded":
            self.counters["repository_write_total"] += 1
        elif event.name == "persistence_failed":
            self.counters["repository_errors_total"] += 1
        elif event.name == "llm_usage_recorded":
            self.counters["llm_usage_events_total"] += 1


class ProgressObserver:
    """Forwards progress to an optional consumer and records safe operational logs."""

    def __init__(self, logger: StructuredLogger, sink: ProgressSink | None = None, metrics: OperationalMetrics | None = None) -> None:
        self._logger = logger
        self._sink = sink
        self._metrics = metrics

    def __call__(self, event: ProgressEvent) -> None:
        if self._metrics is not None:
            self._metrics.record(event)
        self._logger.info(
            event.name,
            investigation_id=event.investigation_id,
            step_id=event.step_id,
            **dict(event.details),
        )
        if self._sink is not None:
            self._sink(event)
