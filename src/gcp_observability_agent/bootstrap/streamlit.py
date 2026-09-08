"""Composition helpers for the Phase 1 Streamlit entry point."""

from __future__ import annotations

from gcp_observability_agent.application.common.events import ProgressSink
from gcp_observability_agent.application.investigations.service import InvestigationApplicationService
from gcp_observability_agent.bootstrap.container import build_gemini_llm_provider, build_phase_one_container
from gcp_observability_agent.infrastructure.configuration.settings import Settings


def build_streamlit_application_service(
    progress_sink: ProgressSink | None = None,
) -> InvestigationApplicationService:
    """Build the application boundary used by the Streamlit adapter."""
    settings = Settings.from_environment()
    return build_phase_one_container(
        build_gemini_llm_provider(settings), settings=settings, progress_sink=progress_sink
    ).application_service
