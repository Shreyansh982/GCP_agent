"""Streamlit entry point for the Phase 1 investigation UI."""

from gcp_observability_agent.bootstrap.streamlit import build_streamlit_application_service
from gcp_observability_agent.presentation.streamlit.app import render


render(build_streamlit_application_service)
