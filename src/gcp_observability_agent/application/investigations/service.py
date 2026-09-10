"""Application-facing entry point for a single investigation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from gcp_observability_agent.application.common.observability import StructuredLogger
from gcp_observability_agent.application.investigations.controller import InvestigationController
from gcp_observability_agent.domain.common.time import TimeInterval
from gcp_observability_agent.domain.investigation.models import Investigation, InvestigationScope, TemporalContext
from gcp_observability_agent.domain.telemetry.models import ProjectId


@dataclass(frozen=True, slots=True)
class InvestigationSubmission:
    """Primitive request data accepted from presentation adapters."""

    question: str
    start_time: str
    end_time: str
    project_id: str | None = None
    service: str | None = None
    environment: str | None = None


class InvestigationApplicationService:
    """Creates an aggregate and delegates bounded execution to the controller."""

    def __init__(
        self,
        controller: InvestigationController,
        logger: StructuredLogger | None = None,
        *,
        max_question_length: int = 4_000,
    ) -> None:
        self._controller = controller
        self._logger = logger or StructuredLogger()
        self._max_question_length = max_question_length

    def investigate(
        self,
        question: str,
        scope: InvestigationScope,
        temporal_context: TemporalContext,
    ) -> Investigation:
        if len(question) > self._max_question_length:
            raise ValueError(f"question must not exceed {self._max_question_length} characters")
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

    def investigate_submission(self, submission: InvestigationSubmission) -> Investigation:
        """Validate presentation input and execute the investigation use case."""
        start_time = self._timestamp(submission.start_time, "start_time")
        end_time = self._timestamp(submission.end_time, "end_time")
        scope = InvestigationScope(
            project_id=ProjectId(submission.project_id.strip()) if submission.project_id and submission.project_id.strip() else None,
            service=submission.service.strip() if submission.service and submission.service.strip() else None,
            environment=submission.environment.strip() if submission.environment and submission.environment.strip() else None,
        )
        return self.investigate(
            submission.question.strip(),
            scope,
            TemporalContext(datetime.now(UTC), TimeInterval(start_time, end_time), requested_expression="custom UTC interval"),
        )

    @staticmethod
    def _timestamp(value: str, field_name: str) -> datetime:
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from error
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError(f"{field_name} must include a timezone")
        return timestamp
