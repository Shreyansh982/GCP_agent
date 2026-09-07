"""Application-facing entry point for a single investigation."""

from __future__ import annotations

from gcp_observability_agent.application.common.observability import StructuredLogger
from gcp_observability_agent.application.investigations.controller import InvestigationController
from gcp_observability_agent.domain.investigation.models import Investigation, InvestigationScope, TemporalContext


class InvestigationApplicationService:
    """Creates an aggregate and delegates bounded execution to the controller."""

    def __init__(self, controller: InvestigationController, logger: StructuredLogger | None = None) -> None:
        self._controller = controller
        self._logger = logger or StructuredLogger()

    def investigate(
        self,
        question: str,
        scope: InvestigationScope,
        temporal_context: TemporalContext,
    ) -> Investigation:
        investigation = Investigation.create(question, scope, temporal_context)
        self._logger.info("investigation_submitted", investigation_id=str(investigation.investigation_id))
        result = self._controller.run(investigation)
        self._logger.info(
            "investigation_finished",
            investigation_id=str(result.investigation_id),
            outcome_status=result.outcome.status.value if result.outcome else None,
            termination_reason=result.outcome.termination_reason.value if result.outcome else None,
        )
        return result
