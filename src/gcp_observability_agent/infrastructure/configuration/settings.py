"""Application configuration loaded at the composition root."""

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret Phase 1 configuration defaults.

    Secret provider credentials are intentionally not represented here; adapters read
    them only from their secure runtime configuration when they are implemented.
    """

    max_tool_actions: int = 12
    database_path: str = "gcp_observability_agent.sqlite3"
    log_level: str = "INFO"

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load safe operational settings without exposing secrets to core layers."""
        return cls(
            max_tool_actions=int(getenv("GCP_AGENT_MAX_TOOL_ACTIONS", "12")),
            database_path=getenv("GCP_AGENT_DATABASE_PATH", "gcp_observability_agent.sqlite3"),
            log_level=getenv("GCP_AGENT_LOG_LEVEL", "INFO"),
        )

