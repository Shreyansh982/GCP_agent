"""Phase 1 composition root for deterministic local investigations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from gcp_observability_agent.application.common.events import ProgressSink
from gcp_observability_agent.application.common.observability import OperationalMetrics, ProgressObserver, StructuredLogger
from gcp_observability_agent.application.investigations.controller import (
    ContextBuilder,
    ContextPolicy,
    ControllerPolicy,
    InvestigationController,
)
from gcp_observability_agent.application.investigations.service import InvestigationApplicationService
from gcp_observability_agent.application.investigations.tools import ToolPolicy, ToolRegistry
from gcp_observability_agent.domain.ports import LLMProvider
from gcp_observability_agent.infrastructure.configuration.settings import Settings
from gcp_observability_agent.infrastructure.llm.gemini import GeminiLLMConfig, GeminiLLMProvider
from gcp_observability_agent.infrastructure.persistence.sqlite.repository import SQLiteInvestigationRepository
from gcp_observability_agent.infrastructure.telemetry.mock.provider import MockTelemetryProvider


@dataclass(frozen=True, slots=True)
class PhaseOneContainer:
    application_service: InvestigationApplicationService
    telemetry_provider: MockTelemetryProvider
    repository: SQLiteInvestigationRepository
    metrics: OperationalMetrics


def build_phase_one_container(
    llm: LLMProvider,
    *,
    settings: Settings | None = None,
    progress_sink: ProgressSink | None = None,
) -> PhaseOneContainer:
    """Compose local Phase 1 dependencies without exposing them to the LLM."""
    resolved = settings or Settings.from_environment()
    logger = logging.getLogger("gcp_observability_agent")
    logger.setLevel(resolved.log_level)
    structured_logger = StructuredLogger(logger)
    metrics = OperationalMetrics()
    telemetry_provider = MockTelemetryProvider(resolved.database_path)
    if resolved.mock_scenario:
        telemetry_provider.load_scenario(resolved.mock_scenario)
    repository = SQLiteInvestigationRepository(resolved.database_path)
    tools = ToolRegistry(
        telemetry_provider,
        ToolPolicy(
            resolved.max_tool_actions,
            resolved.max_result_items,
            resolved.max_query_interval,
            resolved.max_tool_request_payload_bytes,
            resolved.max_label_filter_entries,
            resolved.max_collection_items,
        ),
    )
    controller = InvestigationController(
        llm,
        tools,
        repository,
        frozenset(resolved.allowed_projects),
        context_builder=ContextBuilder(ContextPolicy(resolved.max_context_evidence, resolved.max_prior_tool_results)),
        policy=ControllerPolicy(
            resolved.max_tool_actions,
            resolved.max_investigation_duration,
            resolved.max_llm_retries,
            resolved.max_tool_retries,
        ),
        progress_sink=ProgressObserver(structured_logger, progress_sink, metrics),
    )
    return PhaseOneContainer(
        InvestigationApplicationService(
            controller, structured_logger, max_question_length=resolved.max_investigation_question_length
        ),
        telemetry_provider,
        repository,
        metrics,
    )


def build_gemini_llm_provider(settings: Settings | None = None) -> GeminiLLMProvider:
    """Build the production LLM adapter from safe runtime settings and an environment secret."""
    resolved = settings or Settings.from_environment()
    return GeminiLLMProvider.from_environment(
        GeminiLLMConfig(
            model=resolved.gemini_model,
            temperature=resolved.gemini_temperature,
            timeout_seconds=resolved.gemini_timeout_seconds,
            max_retries=resolved.gemini_max_retries,
        )
    )
