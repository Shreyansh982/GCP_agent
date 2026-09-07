"""Application configuration loaded at the composition root."""

from dataclasses import dataclass
from datetime import timedelta
from os import getenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret Phase 1 configuration defaults.

    Secret provider credentials are intentionally not represented here; adapters read
    them only from their secure runtime configuration when they are implemented.
    """

    max_tool_actions: int = 12
    max_result_items: int = 100
    max_query_interval: timedelta = timedelta(days=7)
    max_investigation_duration: timedelta = timedelta(minutes=5)
    max_llm_retries: int = 1
    max_tool_retries: int = 1
    max_context_evidence: int = 50
    max_prior_tool_results: int = 12
    database_path: str = "gcp_observability_agent.sqlite3"
    allowed_projects: tuple[str, ...] = ()
    mock_scenario: str | None = None
    log_level: str = "INFO"

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load safe operational settings without exposing secrets to core layers."""
        return cls(
            max_tool_actions=int(getenv("GCP_AGENT_MAX_TOOL_ACTIONS", "12")),
            max_result_items=int(getenv("GCP_AGENT_MAX_RESULT_ITEMS", "100")),
            max_query_interval=timedelta(days=int(getenv("GCP_AGENT_MAX_QUERY_INTERVAL_DAYS", "7"))),
            max_investigation_duration=timedelta(seconds=int(getenv("GCP_AGENT_MAX_INVESTIGATION_SECONDS", "300"))),
            max_llm_retries=int(getenv("GCP_AGENT_MAX_LLM_RETRIES", "1")),
            max_tool_retries=int(getenv("GCP_AGENT_MAX_TOOL_RETRIES", "1")),
            max_context_evidence=int(getenv("GCP_AGENT_MAX_CONTEXT_EVIDENCE", "50")),
            max_prior_tool_results=int(getenv("GCP_AGENT_MAX_PRIOR_TOOL_RESULTS", "12")),
            database_path=getenv("GCP_AGENT_DATABASE_PATH", "gcp_observability_agent.sqlite3"),
            allowed_projects=tuple(
                project.strip() for project in getenv("GCP_AGENT_ALLOWED_PROJECTS", "").split(",") if project.strip()
            ),
            mock_scenario=getenv("GCP_AGENT_MOCK_SCENARIO") or None,
            log_level=getenv("GCP_AGENT_LOG_LEVEL", "INFO"),
        )
