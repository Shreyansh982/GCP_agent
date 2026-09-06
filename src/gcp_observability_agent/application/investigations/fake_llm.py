"""Deterministic LLM provider used by investigation-engine tests."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from gcp_observability_agent.domain.investigation.models import ToolRequest


class FakeLLMProvider:
    """Returns a predefined action sequence and records each state-sync context."""

    def __init__(self, actions: Sequence[ToolRequest | Exception | Callable[[Mapping[str, object]], ToolRequest] | object]) -> None:
        self._actions = list(actions)
        self.contexts: list[Mapping[str, object]] = []

    def next_action(self, context: Mapping[str, object]) -> ToolRequest:
        self.contexts.append(context)
        if not self._actions:
            raise RuntimeError("FakeLLMProvider has no remaining actions")
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        if callable(action):
            return action(context)
        return action  # type: ignore[return-value]
